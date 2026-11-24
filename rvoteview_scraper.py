"""
Rvoteview Scraper Module for Political Alignment Tool

This module handles data collection from Voteview.com, which provides valuable information
about representatives' voting records and ideological scores (NOMINATE scores).

Fixed version that combines the best approaches from both implementations with
robust error handling and caching to handle API issues.
"""

import requests
import pandas as pd
import json
import logging
import sqlite3
from datetime import datetime
import time
import random
import os

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('rvoteview_scraper')

class RvoteviewScraper:
    """
    A class to scrape data from Voteview.com API with robust error handling
    """
    
    def __init__(self, db_path, api_key=None, metadata_path=None, auto_update=False):
        """
        Initialize the scraper with database path and optional API key
        
        Parameters:
        -----------
        db_path : str
            Path to the SQLite database
        api_key : str, optional
            API key for Voteview (if required)
        metadata_path : str, optional
            Path to Rvoteview metadata CSV file (from R package)
        auto_update : bool, optional
            Whether to auto-update metadata if it's older than 30 days
        """
        self.db_path = db_path
        self.api_key = api_key
        self.metadata_path = metadata_path
        self.auto_update = auto_update
        self.api_base_url = "https://voteview.com"
        self.headers = {
            'User-Agent': 'Political Alignment Tool/1.0',
            'Content-Type': 'application/json'
        }
        if api_key:
            self.headers['Authorization'] = f'Bearer {api_key}'
        
        # Create cache directory if it doesn't exist
        self.cache_dir = "voteview_cache"
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Check if metadata needs updating
        if self.metadata_path and self.auto_update:
            self.check_metadata_freshness()
        
        # Initialize database connection
        try:
            self.conn = sqlite3.connect(db_path)
            self.cursor = self.conn.cursor()
            logger.info(f"Connected to database at {db_path}")
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise
    
    def __del__(self):
        """
        Close database connection when object is destroyed
        """
        if hasattr(self, 'conn'):
            self.conn.close()
    
    def run_voteview_update(self, congress=None):
        """
        Run a complete update of Voteview data
        
        Parameters:
        -----------
        congress : int or list, optional
            Congress number(s) to update (defaults to current)
            
        Returns:
        --------
        dict
            Results of the update operation
        """
        results = {
            "votes_collected": 0,
            "bill_mappings_created": 0,
            "representatives_updated": 0
        }
        
        try:
            # If congress is not specified, use recent congresses
            if congress is None:
                congress = [117, 116]  # Use recent congresses that are more likely to have stable data
                logger.info(f"No congress specified, using congresses {congress}")
            
            # Try to get members first using the search method
            members_df = self.fetch_voteview_members(congress)
            
            if members_df is not None and not members_df.empty:
                # Update representatives with Voteview IDs and NOMINATE scores
                updated = self.update_representatives_with_voteview_data(members_df)
                results["representatives_updated"] = updated
            
            # Search for votes related to key policy areas
            policy_areas = ["gun", "firearm", "immigration", "healthcare", "economy", "environment"]

            all_votes_df = pd.DataFrame()
            all_vote_data = {'votes': [], 'legis_data': [], 'vote_data': []}

            # Search for each policy area separately to avoid overwhelming the API
            for policy_area in policy_areas:
                logger.info(f"Searching for votes related to '{policy_area}'")
                # Get votes related to this policy area
                votes_df = self.voteview_search(q=policy_area, congress=congress)
                if votes_df is not None and not votes_df.empty:
                    # Download detailed vote data
                    vote_data = self.voteview_download(votes_df['id'].tolist())

                    # Merge vote data
                    all_votes_df = pd.concat([all_votes_df, votes_df], ignore_index=True)
                    all_vote_data['votes'].extend(vote_data.get('votes', []))
                    all_vote_data['legis_data'].extend(vote_data.get('legis_data', []))
                    all_vote_data['vote_data'].extend(vote_data.get('vote_data', []))
                    
                    # Add a small delay to avoid overwhelming the API
                    time.sleep(random.uniform(1.0, 2.0))
            
            # Remove duplicates
            if not all_votes_df.empty:
                all_votes_df = all_votes_df.drop_duplicates(subset=['id'])
                
                # If we didn't get members earlier, extract them from vote data
                if members_df is None or members_df.empty:
                    members_df = self._extract_members_from_vote_data(all_vote_data)
                    
                    if members_df is not None and not members_df.empty:
                        # Update representatives with Voteview IDs and NOMINATE scores
                        updated = self.update_representatives_with_voteview_data(members_df)
                        results["representatives_updated"] = updated
                
                # Process and store votes
                votes_processed = self.process_votes(all_votes_df, all_vote_data)
                results["votes_collected"] = votes_processed
                
                # Create bill-question mappings
                mappings_created = self.create_bill_question_mappings(all_votes_df)
                results["bill_mappings_created"] = mappings_created
            
            return results
            
        except Exception as e:
            logger.error(f"Error running Voteview update: {e}")
            # Return partial results if available
            return results
    
    def load_members_from_metadata(self):
        """
        Load members data from Rvoteview metadata CSV file
        
        Returns:
        --------
        pandas.DataFrame
            DataFrame containing member data
        """
        if not self.metadata_path or not os.path.exists(self.metadata_path):
            logger.warning("No metadata file provided or file not found")
            return pd.DataFrame()
        
        try:
            logger.info(f"Loading Rvoteview metadata from {self.metadata_path}")
            
            # Load CSV file with low_memory=False to handle mixed types
            metadata_df = pd.read_csv(self.metadata_path, low_memory=False)
            
            # Print column names for debugging
            logger.info(f"CSV columns: {', '.join(metadata_df.columns)}")
            
            # Handle different possible column names (R export vs voteview direct download)
            id_column = 'icpsr' if 'icpsr' in metadata_df.columns else 'id'
            congress_column = 'congress' if 'congress' in metadata_df.columns else 'cong'
            
            # Select most recent session for each member
            if congress_column in metadata_df.columns:
                # Group by ICPSR ID and get the most recent congress for each member
                metadata_df = metadata_df.sort_values(congress_column, ascending=False)
                latest_members = metadata_df.drop_duplicates(subset=[id_column])
                
                # For members who served in multiple parties, keep the most recent record
                party_column = 'party_code' if 'party_code' in metadata_df.columns else 'party'
                if party_column in metadata_df.columns:
                    latest_members = latest_members.sort_values([id_column, congress_column], ascending=[True, False])
                    latest_members = latest_members.drop_duplicates(subset=[id_column])
            
            # Construct a dynamic mapping based on actual columns
            column_mapping = {}
            
            # ID columns
            if 'icpsr' in metadata_df.columns:
                column_mapping['icpsr'] = 'voteview_id'
            elif 'id' in metadata_df.columns:
                column_mapping['id'] = 'voteview_id'
                
            # Other identifiers
            if 'bioguide_id' in metadata_df.columns:
                column_mapping['bioguide_id'] = 'bioguide_id'
                
            # Name fields
            if 'bioname' in metadata_df.columns:
                column_mapping['bioname'] = 'name'
            elif 'name' in metadata_df.columns:
                column_mapping['name'] = 'name'
                
            # Party fields
            if 'party_code' in metadata_df.columns:
                column_mapping['party_code'] = 'party_code'
            elif 'party' in metadata_df.columns:
                column_mapping['party'] = 'party_code'
                
            # State fields
            if 'state_abbrev' in metadata_df.columns:
                column_mapping['state_abbrev'] = 'state'
            elif 'state' in metadata_df.columns:
                column_mapping['state'] = 'state'
                
            # NOMINATE scores
            if 'nominate_dim1' in metadata_df.columns:
                column_mapping['nominate_dim1'] = 'nominate_score1'
            elif 'nominate.dim1' in metadata_df.columns:
                column_mapping['nominate.dim1'] = 'nominate_score1'
                
            if 'nominate_dim2' in metadata_df.columns:
                column_mapping['nominate_dim2'] = 'nominate_score2'
            elif 'nominate.dim2' in metadata_df.columns:
                column_mapping['nominate.dim2'] = 'nominate_score2'
            
            logger.info(f"Column mapping: {column_mapping}")
            
            # Select and rename columns that exist in the dataframe
            existing_columns = [col for col in column_mapping.keys() if col in latest_members.columns]
            
            if not existing_columns:
                logger.error(f"No usable columns found in metadata file. Available columns: {latest_members.columns}")
                return pd.DataFrame()
                
            renamed_df = latest_members[existing_columns].rename(
                columns={col: column_mapping[col] for col in existing_columns}
            )
            
            # Convert voteview_id to string if it exists
            if 'voteview_id' in renamed_df.columns:
                renamed_df['voteview_id'] = renamed_df['voteview_id'].astype(str)
            
            logger.info(f"Loaded {len(renamed_df)} members from metadata file")
            return renamed_df
            
        except Exception as e:
            logger.error(f"Error loading Rvoteview metadata: {e}")
            return pd.DataFrame()

    def fetch_voteview_members(self, congress=None):
        """
        Fetch members data from Voteview API using multiple methods
        
        Parameters:
        -----------
        congress : int or list, optional
            Congress number(s) to fetch
            
        Returns:
        --------
        pandas.DataFrame
            DataFrame containing member data
        """
        # First try to load from metadata file if available
        if self.metadata_path:
            metadata_df = self.load_members_from_metadata()
            if not metadata_df.empty:
                return metadata_df
        
        # Fall back to API methods if metadata loading fails
        methods = [
            self._fetch_members_via_search,
            self._fetch_members_via_direct_api,
            self._fetch_members_from_cache
        ]
        
        for method in methods:
            try:
                logger.info(f"Attempting to fetch members using {method.__name__}")
                members_df = method(congress)
                
                if members_df is not None and not members_df.empty:
                    logger.info(f"Successfully fetched {len(members_df)} members using {method.__name__}")
                    return members_df
            except Exception as e:
                logger.warning(f"Failed to fetch members using {method.__name__}: {e}")
        
        logger.warning("All methods to fetch members failed")
        return pd.DataFrame()
    
    def _fetch_members_via_search(self, congress=None):
        """
        Fetch members by searching for votes and extracting member data
        
        Parameters:
        -----------
        congress : int or list, optional
            Congress number(s) to fetch
            
        Returns:
        --------
        pandas.DataFrame
            DataFrame containing member data
        """
        # Search for votes with high participation
        votes_df = self.voteview_search(congress=congress, minsupport=80)
        
        if votes_df is None or votes_df.empty:
            return pd.DataFrame()
        
        # Get a sample of votes to extract member data
        sample_size = min(5, len(votes_df))
        sample_votes = votes_df.sample(n=sample_size) if len(votes_df) > sample_size else votes_df
        
        # Download vote data
        vote_data = self.voteview_download(sample_votes['id'].tolist())
        
        # Extract member data
        return self._extract_members_from_vote_data(vote_data)
    
    def _fetch_members_via_direct_api(self, congress=None):
        """
        Fetch members directly from the API
        
        Parameters:
        -----------
        congress : int or list, optional
            Congress number(s) to fetch
            
        Returns:
        --------
        pandas.DataFrame
            DataFrame containing member data
        """
        # Determine congress number if not provided
        if congress is None:
            congress = 116  # Use a stable congress number
        
        # If congress is a list, use the first one
        if isinstance(congress, list):
            congress = congress[0]
        
        # Cache file path
        cache_file = os.path.join(self.cache_dir, f"members_congress_{congress}.json")
        
        try:
            # Try the POST method first (more reliable)
            url = f"{self.api_base_url}/api/download"
            
            # Use POST request with form data
            response = requests.post(
                url, 
                data={
                    'congress': congress,
                    'chamber': 'all',
                    'fields': 'bioguide_id,icpsr,state_abbrev,district_code,party_code,dim1,dim2',
                    'rapi': 1
                },
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Save to cache
            with open(cache_file, 'w') as f:
                json.dump(data, f)
            
            # Extract member data
            if 'legis_data' in data and data['legis_data']:
                return self._extract_members_from_vote_data(data)
            
            return pd.DataFrame()
            
        except Exception as e:
            logger.warning(f"Error fetching members via direct API: {e}")
            
            # Try the old GET method as fallback
            try:
                url = f"{self.api_base_url}/api/getmembersbycongress"
                params = {
                    "congress": congress,
                    "chamber": "all"
                }
                
                response = requests.get(url, params=params, headers=self.headers, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                
                # Save to cache
                with open(cache_file, 'w') as f:
                    json.dump(data, f)
                
                # Check if we have results
                if "results" not in data or not data["results"]:
                    return pd.DataFrame()
                
                # Convert to DataFrame
                members_df = pd.DataFrame(data["results"])
                return members_df
                
            except Exception as e2:
                logger.warning(f"Error fetching members via GET method: {e2}")
                return pd.DataFrame()
    
    def _fetch_members_from_cache(self, congress=None):
        """
        Fetch members from cache files
        
        Parameters:
        -----------
        congress : int or list, optional
            Congress number(s) to fetch
            
        Returns:
        --------
        pandas.DataFrame
            DataFrame containing member data
        """
        # Try to find any cache files with member data
        cache_files = []
        
        # Look for specific congress cache files
        if congress:
            congresses = [congress] if not isinstance(congress, list) else congress
            for c in congresses:
                cache_file = os.path.join(self.cache_dir, f"members_congress_{c}.json")
                if os.path.exists(cache_file):
                    cache_files.append(cache_file)
        
        # If no specific files found, look for any member cache files
        if not cache_files:
            for filename in os.listdir(self.cache_dir):
                if filename.startswith("members_") and filename.endswith(".json"):
                    cache_files.append(os.path.join(self.cache_dir, filename))
        
        # If still no files found, look for any search cache that might contain member data
        if not cache_files:
            for filename in os.listdir(self.cache_dir):
                if filename.startswith("search_") and filename.endswith(".json"):
                    cache_files.append(os.path.join(self.cache_dir, filename))
        
        # Try each cache file
        for cache_file in cache_files:
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    
                    # Check for different data formats
                    if "results" in data and data["results"]:
                        return pd.DataFrame(data["results"])
                    elif "legis_data" in data and data["legis_data"]:
                        return self._extract_members_from_vote_data(data)
                    elif "rollcalls" in data and data["rollcalls"]:
                        # This is a search result, try to download vote data
                        votes_df = pd.DataFrame(data["rollcalls"])
                        sample_size = min(5, len(votes_df))
                        sample_votes = votes_df.sample(n=sample_size) if len(votes_df) > sample_size else votes_df
                        
                        # Try to find vote data cache
                        vote_cache_file = os.path.join(self.cache_dir, f"votes_{hash(str(sorted(sample_votes['id'].tolist())))}.json")
                        if os.path.exists(vote_cache_file):
                            with open(vote_cache_file, 'r') as vf:
                                vote_data = json.load(vf)
                                return self._extract_members_from_vote_data(vote_data)
            except Exception as e:
                logger.warning(f"Error loading members from cache file {cache_file}: {e}")
        
        return pd.DataFrame()
    
    def voteview_search(self, q=None, startdate=None, enddate=None, congress=None, 
                        chamber=None, maxsupport=None, minsupport=None, keyvote=None):
        """
        Search for votes in Voteview using the same approach as the Rvoteview R package
        
        Parameters:
        -----------
        q : str, optional
            Search query
        startdate : str, optional
            Start date in YYYY-MM-DD format
        enddate : str, optional
            End date in YYYY-MM-DD format
        congress : int or list, optional
            Congress number(s) to search
        chamber : str, optional
            Chamber ('House' or 'Senate')
        maxsupport : int, optional
            Maximum support percentage (0-100)
        minsupport : int, optional
            Minimum support percentage (0-100)
        keyvote : bool or str, optional
            Whether to include only key votes
            
        Returns:
        --------
        pandas.DataFrame
            DataFrame containing search results
        """
        # Build query string following the Rvoteview package approach
        query_parts = []
        
        if q:
            query_parts.append(f"({q})")
        else:
            query_parts.append("()")
        
        if keyvote:
            if keyvote is True:
                query_parts.append("(keyvote:1)")
            elif keyvote in ["1", "CQ"]:
                query_parts.append(f"(keyvote:{keyvote})")
        
        if startdate:
            query_parts.append(f"(startdate:{startdate})")
        
        if enddate:
            query_parts.append(f"(enddate:{enddate})")
        
        if congress:
            if isinstance(congress, list):
                congress_str = " ".join(map(str, congress))
            else:
                congress_str = str(congress)
            query_parts.append(f"(congress:{congress_str})")
        
        if minsupport is not None or maxsupport is not None:
            min_val = 0 if minsupport is None else minsupport
            max_val = 100 if maxsupport is None else maxsupport
            query_parts.append(f"(support:[{min_val} to {max_val}])")
        
        if chamber:
            chamber = chamber.lower()
            if chamber not in ["house", "senate"]:
                raise ValueError("Chamber must be either 'House' or 'Senate'")
            query_parts.append(f"(chamber:{chamber})")
        
        # Join query parts with AND
        query_string = " AND ".join(query_parts)
        
        # Cache file path
        cache_key = "_".join([str(x) for x in [q, startdate, enddate, congress, chamber, maxsupport, minsupport, keyvote] if x is not None])
        cache_file = os.path.join(self.cache_dir, f"search_{hash(cache_key)}.json")
        
        try:
            # Check cache first
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    logger.info(f"Loading search results from cache: {cache_file}")
                    data = json.load(f)
                    if data.get('recordcount', 0) > 0:
                        return pd.DataFrame(data['rollcalls'])
            
            # If not in cache or empty, make API request
            logger.info(f"Searching Voteview with query: {query_string}")
            url = f"{self.api_base_url}/api/search"
            
            # Use POST request with form data as in the R package
            response = requests.post(url, data={'q': query_string, 'rapi': 1}, timeout=15)
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            
            # Save to cache
            with open(cache_file, 'w') as f:
                json.dump(data, f)
            
            # Check if we have results
            if data.get('recordcount', 0) == 0:
                logger.warning(f"No rollcalls found for query: {query_string}")
                return None
            
            # Convert to DataFrame
            result_df = pd.DataFrame(data['rollcalls'])
            logger.info(f"Found {len(result_df)} rollcalls for query: {query_string}")
            return result_df
            
        except Exception as e:
            logger.error(f"Error searching Voteview: {e}")
            # Try to load from cache if API fails
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r') as f:
                        logger.info(f"Loading search results from cache after API failure")
                        data = json.load(f)
                        if data.get('recordcount', 0) > 0:
                            return pd.DataFrame(data['rollcalls'])
                except Exception as cache_error:
                    logger.error(f"Error loading from cache: {cache_error}")
            
            # If everything fails, return None
            return None
    
    def voteview_download(self, ids, perrequest=10):
        """
        Download detailed vote data for specific vote IDs
        
        Parameters:
        -----------
        ids : list
            List of vote IDs to download
        perrequest : int, optional
            Number of votes to request at once
            
        Returns:
        --------
        dict
            Dictionary containing detailed vote data
        """
        if not isinstance(ids, list):
            ids = [ids]
        
        # Remove duplicates
        unique_ids = list(set(ids))
        if len(unique_ids) < len(ids):
            logger.info(f"Removed {len(ids) - len(unique_ids)} duplicate vote IDs")
        
        # Cache file path
        cache_file = os.path.join(self.cache_dir, f"votes_{hash(str(sorted(unique_ids)))}.json")
        
        try:
            # Check cache first
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    logger.info(f"Loading vote data from cache: {cache_file}")
                    return json.load(f)
            
            # If not in cache, make API requests
            logger.info(f"Downloading vote data for {len(unique_ids)} votes")
            
            # Split IDs into chunks to avoid overwhelming the API
            chunks = [unique_ids[i:i + perrequest] for i in range(0, len(unique_ids), perrequest)]
            
            all_data = {
                'votes': [],
                'legis_data': [],
                'vote_data': []
            }
            
            for chunk in chunks:
                url = f"{self.api_base_url}/api/download"
                
                # Use POST request with form data as in the R package
                response = requests.post(url, data={'ids': ','.join(map(str, chunk)), 'rapi': 1}, timeout=15)
                response.raise_for_status()
                
                # Parse response
                chunk_data = response.json()
                
                # Merge data
                all_data['votes'].extend(chunk_data.get('votes', []))
                all_data['legis_data'].extend(chunk_data.get('legis_data', []))
                all_data['vote_data'].extend(chunk_data.get('vote_data', []))
                
                # Add a small delay to avoid overwhelming the API
                time.sleep(random.uniform(0.5, 1.5))
            
            # Save to cache
            with open(cache_file, 'w') as f:
                json.dump(all_data, f)
            
            logger.info(f"Downloaded vote data for {len(unique_ids)} votes")
            return all_data
            
        except Exception as e:
            logger.error(f"Error downloading vote data: {e}")
            # Try to load from cache if API fails
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r') as f:
                        logger.info(f"Loading vote data from cache after API failure")
                        return json.load(f)
                except Exception as cache_error:
                    logger.error(f"Error loading from cache: {cache_error}")
            
            # If everything fails, return empty data
            return {'votes': [], 'legis_data': [], 'vote_data': []}
    
    def _extract_members_from_vote_data(self, vote_data):
        """
        Extract member data from vote data
        
        Parameters:
        -----------
        vote_data : dict
            Vote data from voteview_download
            
        Returns:
        --------
        pandas.DataFrame
            DataFrame containing member data
        """
        if not vote_data or 'legis_data' not in vote_data or not vote_data['legis_data']:
            return pd.DataFrame()
        
        # Convert to DataFrame
        members_df = pd.DataFrame(vote_data['legis_data'])
        
        # Rename columns to match our schema
        column_mapping = {
            'icpsr': 'voteview_id',
            'bioguide_id': 'bioguide_id',
            'name': 'name',
            'party_code': 'party_code',
            'state_abbrev': 'state',
            'dim1': 'nominate_score1',
            'dim2': 'nominate_score2'
        }
        
        # Select and rename columns
        members_df = members_df[[col for col in column_mapping.keys() if col in members_df.columns]]
        members_df = members_df.rename(columns=column_mapping)
        
        # Remove duplicates
        members_df = members_df.drop_duplicates(subset=['voteview_id'])
        
        logger.info(f"Extracted {len(members_df)} unique members from vote data")
        return members_df
    
    def update_representatives_with_voteview_data(self, members_df):
        """
        Update representatives table with Voteview IDs and NOMINATE scores
        
        Parameters:
        -----------
        members_df : pandas.DataFrame
            DataFrame containing member data from Voteview
            
        Returns:
        --------
        int
            Number of representatives updated
        """
        if members_df is None or members_df.empty:
            logger.warning("No members data to update representatives with")
            return 0
        
        updated_count = 0
        
        try:
            # Check if the representatives table has the necessary columns
            self.cursor.execute("PRAGMA table_info(representatives)")
            columns = {row[1] for row in self.cursor.fetchall()}
            
            # Add missing columns if needed
            if 'nominate_score1' not in columns:
                logger.info("Adding nominate_score1 column to representatives table")
                self.cursor.execute("ALTER TABLE representatives ADD COLUMN nominate_score1 REAL")
            
            if 'nominate_score2' not in columns:
                logger.info("Adding nominate_score2 column to representatives table")
                self.cursor.execute("ALTER TABLE representatives ADD COLUMN nominate_score2 REAL")
            
            # Get existing representatives from database
            self.cursor.execute("SELECT id, bioguide_id, last_name, first_name FROM representatives")
            representatives = self.cursor.fetchall()
            
            for rep in representatives:
                rep_id, bioguide_id, last_name, first_name = rep
                
                # Try to match by bioguide_id first
                if bioguide_id and 'bioguide_id' in members_df.columns:
                    matches = members_df[members_df['bioguide_id'] == bioguide_id]
                    
                    # If no match by bioguide_id, try name matching
                    if matches.empty and 'name' in members_df.columns:
                        # Try to match by last name and first name
                        for _, member in members_df.iterrows():
                            if 'name' in member and member['name']:
                                member_name = member['name'].upper()
                                rep_name = f"{last_name}, {first_name}".upper()
                                
                                # Calculate similarity score
                                similarity = self._name_similarity(rep_name, member_name)
                                if similarity > 0.7:  # Threshold for considering a match
                                    matches = pd.DataFrame([member])
                                    break
                    
                    if not matches.empty:
                        # Get the first match
                        match = matches.iloc[0]
                        
                        # Update the representative with Voteview data
                        self.cursor.execute("""
                            UPDATE representatives 
                            SET voteview_id = ?, nominate_score1 = ?, nominate_score2 = ?
                            WHERE id = ?
                        """, (
                            str(match.get('voteview_id', '')),
                            float(match.get('nominate_score1', 0)),
                            float(match.get('nominate_score2', 0)),
                            rep_id
                        ))
                        updated_count += 1
            
            self.conn.commit()
            logger.info(f"Updated {updated_count} representatives with Voteview data")
            return updated_count
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error updating representatives with Voteview data: {e}")
            return 0
    
    def check_metadata_freshness(self):
        """
        Check if metadata file exists and is recent (less than 30 days old)
        If not, try to download a fresh copy
        """
        if not self.metadata_path:
            return
            
        # Check if file exists
        if not os.path.exists(self.metadata_path):
            logger.info(f"Metadata file {self.metadata_path} does not exist. Attempting to download...")
            self.update_metadata()
            return
            
        # Check file age
        file_age_days = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(self.metadata_path))).days
        
        if file_age_days > 30:  # If older than 30 days
            logger.info(f"Metadata file is {file_age_days} days old. Attempting to update...")
            self.update_metadata()
        else:
            logger.info(f"Metadata file is {file_age_days} days old. No update needed.")
    
    def update_metadata(self):
        """
        Download fresh member data from Voteview.com
        
        This method downloads the comprehensive member dataset directly from 
        Voteview.com and saves it as a CSV file.
        """
        try:
            # Voteview members download URL - this downloads all members across all Congresses
            url = f"{self.api_base_url}/static/data/out/members/HSall_members.csv"
            
            logger.info(f"Downloading fresh member data from {url}...")
            
            # Use a browser-like user agent
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/csv,application/csv,application/octet-stream'
            }
            
            # Download the CSV
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()
            
            # Make sure it's member data by checking content
            content_sample = response.content[:1000].decode('utf-8', errors='ignore')
            if 'congress,chamber,icpsr,state_icpsr' not in content_sample and 'bioguide_id' not in content_sample:
                logger.error("Downloaded file does not appear to be member data")
                return False
                
            # Save to file
            with open(self.metadata_path, 'wb') as f:
                f.write(response.content)
                
            logger.info(f"Successfully updated member data file at {self.metadata_path}")
            return True
        except Exception as e:
            logger.error(f"Error updating member data: {e}")
            return False
    
    def _name_similarity(self, name1, name2):
        """
        Calculate similarity between two names
        
        Parameters:
        -----------
        name1 : str
            First name
        name2 : str
            Second name
            
        Returns:
        --------
        float
            Similarity score (0-1)
        """
        # Simple implementation using string matching
        # In a real system, this would use more sophisticated name matching
        
        # Convert to uppercase and remove punctuation
        name1 = ''.join(c for c in name1.upper() if c.isalnum() or c.isspace())
        name2 = ''.join(c for c in name2.upper() if c.isalnum() or c.isspace())
        
        # Split into words
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        # Calculate Jaccard similarity
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0
    
    def process_votes(self, votes_df, vote_data):
        """
        Process and store votes in the database
        
        Parameters:
        -----------
        votes_df : pandas.DataFrame
            DataFrame containing votes data
        vote_data : dict
            Dictionary containing detailed vote data
            
        Returns:
        --------
        int
            Number of votes processed
        """
        if votes_df is None or votes_df.empty or not vote_data:
            logger.warning("No votes data to process")
            return 0
        
        processed_count = 0
        
        try:
            # Get representatives with Voteview IDs
            self.cursor.execute("SELECT id, voteview_id FROM representatives WHERE voteview_id IS NOT NULL")
            representatives = {str(row[1]): row[0] for row in self.cursor.fetchall()}
            
            # Create a mapping from vote ID to vote details
            vote_details = {}
            for vote in vote_data.get('votes', []):
                vote_id = vote.get('id')
                if vote_id:
                    vote_details[vote_id] = vote
            
            # Create a mapping from vote ID to member votes
            vote_member_mapping = {}
            for vote_record in vote_data.get('vote_data', []):
                vote_id = vote_record.get('rollnumber')
                icpsr = str(vote_record.get('icpsr', ''))
                cast_code = vote_record.get('cast_code')
                
                if vote_id and icpsr and cast_code:
                    if vote_id not in vote_member_mapping:
                        vote_member_mapping[vote_id] = {}
                    vote_member_mapping[vote_id][icpsr] = cast_code
            
            # Process each vote
            for _, vote in votes_df.iterrows():
                vote_id = vote.get('id')
                
                if not vote_id or vote_id not in vote_member_mapping:
                    continue
                
                # Get vote details
                vote_detail = vote_details.get(vote_id, {})
                
                # Process each member's vote
                for icpsr, cast_code in vote_member_mapping[vote_id].items():
                    # Skip if we don't have this representative in our database
                    if icpsr not in representatives:
                        continue
                    
                    rep_id = representatives[icpsr]
                    
                    # Convert cast code to position
                    position = self._convert_cast_code_to_position(cast_code)
                    
                    # Store the vote in the database
                    self.cursor.execute("""
                        INSERT OR REPLACE INTO voting_records (
                            representative_id, congress_number, chamber, session, 
                            roll_call, vote_date, vote_position, bill_number, question, result
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        rep_id,
                        vote.get('congress', ''),
                        vote.get('chamber', ''),
                        vote.get('session', ''),
                        str(vote_id),
                        vote.get('date', ''),
                        position,
                        vote.get('bill_number', ''),
                        vote.get('question', ''),
                        vote.get('result', '')
                    ))
                    processed_count += 1
            
            self.conn.commit()
            logger.info(f"Processed {processed_count} votes")
            return processed_count
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error processing votes: {e}")
            return 0
    
    def _convert_cast_code_to_position(self, cast_code):
        """
        Convert Voteview cast code to vote position
        
        Parameters:
        -----------
        cast_code : str
            Voteview cast code
            
        Returns:
        --------
        str
            Vote position ('Yea', 'Nay', 'Present', 'Not Voting')
        """
        # Voteview cast codes:
        # 1 = Yea, 2 = Paired Yea, 3 = Announced Yea
        # 4 = Announced Nay, 5 = Paired Nay, 6 = Nay
        # 7 = Present, 8 = Not Voting, 9 = Not a Member
        
        cast_code_map = {
            '1': 'Yea',
            '2': 'Yea',
            '3': 'Yea',
            '4': 'Nay',
            '5': 'Nay',
            '6': 'Nay',
            '7': 'Present',
            '8': 'Not Voting',
            '9': 'Not a Member'
        }
        
        return cast_code_map.get(str(cast_code), 'Unknown')
    
    def create_bill_question_mappings(self, votes_df):
        """
        Create mappings between bills and survey questions
        
        Parameters:
        -----------
        votes_df : pandas.DataFrame
            DataFrame containing votes data
            
        Returns:
        --------
        int
            Number of mappings created
        """
        if votes_df is None or votes_df.empty:
            logger.warning("No votes data to create bill-question mappings")
            return 0
        
        mappings_created = 0
        
        try:
            # Get active questions
            self.cursor.execute("""
            SELECT q.id, q.question_text, pa.name as policy_area
            FROM questions q
            JOIN policy_areas pa ON q.policy_area_id = pa.id
            WHERE q.active = 1
            """)
            
            questions = self.cursor.fetchall()
            
            if not questions:
                logger.warning("No active questions found for bill-question mapping")
                return 0
            
            # Process each vote
            for _, vote in votes_df.iterrows():
                # Skip votes without bill numbers
                if not vote.get('bill_number'):
                    continue
                
                # Get vote details
                congress = vote.get('congress')
                bill_number = vote.get('bill_number')
                description = vote.get('description', '')
                question_text = vote.get('question', '')
                
                # Combine text for matching
                vote_text = f"{description} {question_text}".lower()
                
                # Find relevant questions
                for question_id, question_text, policy_area in questions:
                    # Calculate relevance score
                    relevance = self._calculate_bill_question_relevance(vote_text, question_text, policy_area)
                    
                    # Skip if not relevant
                    if relevance < 0.3:  # Threshold for relevance
                        continue
                    
                    # Determine yea/nay scores based on question text and vote description
                    yea_score, nay_score = self._determine_vote_scores(question_text, vote_text)
                    
                    # Create mapping
                    self.cursor.execute("""
                    INSERT OR REPLACE INTO bill_question_mapping (
                        bill_number, congress_number, question_id, yea_score, nay_score, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        bill_number,
                        congress,
                        question_id,
                        yea_score,
                        nay_score,
                        relevance
                    ))
                    
                    mappings_created += 1
            
            self.conn.commit()
            logger.info(f"Created {mappings_created} bill-question mappings")
            return mappings_created
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error creating bill-question mappings: {e}")
            return 0
    
    def _calculate_bill_question_relevance(self, bill_text, question_text, policy_area):
        """
        Calculate relevance between a bill and a question
        
        Parameters:
        -----------
        bill_text : str
            Bill text
        question_text : str
            Question text
        policy_area : str
            Policy area name
            
        Returns:
        --------
        float
            Relevance score (0-1)
        """
        # Simple keyword-based relevance calculation
        # In a real system, this would use more sophisticated text similarity
        
        # Define keywords for policy areas
        policy_keywords = {
            "Gun Control": ["gun", "firearm", "weapon", "second amendment", "background check", "assault weapon", "nra"],
            "Immigration": ["immigration", "immigrant", "border", "visa", "asylum", "refugee", "daca", "deportation"],
            "Healthcare": ["healthcare", "health care", "medicare", "medicaid", "affordable care act", "obamacare", "insurance"],
            "Economy": ["economy", "economic", "tax", "budget", "deficit", "spending", "jobs", "unemployment"],
            "Environment": ["environment", "climate", "pollution", "carbon", "emissions", "epa", "clean energy", "renewable"],
            "Education": ["education", "school", "student", "teacher", "college", "university", "loan", "tuition"],
            "Foreign Policy": ["foreign policy", "international", "diplomacy", "military", "defense", "war", "terrorism", "nato"],
            "Civil Rights": ["civil rights", "discrimination", "equality", "voting rights", "affirmative action", "lgbtq", "transgender"],
            "Abortion": ["abortion", "reproductive", "pro-choice", "pro-life", "planned parenthood", "roe v wade"]
        }
        
        # Get keywords for this policy area
        area_keywords = policy_keywords.get(policy_area, [])
        
        # Extract keywords from question
        question_keywords = set(question_text.lower().split())
        
        # Combine keywords
        all_keywords = question_keywords.union(area_keywords)
        
        # Count keyword matches
        keyword_matches = sum(1 for keyword in all_keywords if keyword in bill_text)
        
        # Calculate relevance score
        relevance = min(keyword_matches / len(all_keywords), 1.0) if all_keywords else 0
        
        return relevance
    
    def _determine_vote_scores(self, question_text, vote_text):
        """
        Determine yea and nay scores based on question text and vote text
        
        Parameters:
        -----------
        question_text : str
            Question text
        vote_text : str
            Vote text
            
        Returns:
        --------
        tuple
            (yea_score, nay_score)
        """
        # Default scores
        yea_score = 3  # Strongly favor
        nay_score = -3  # Strongly oppose
        
        # Check if question is about opposing something
        if "oppose" in question_text.lower():
            # Invert scores for oppose questions
            yea_score, nay_score = nay_score, yea_score
        
        # Check if vote is about prohibiting or restricting
        prohibit_keywords = ["prohibit", "restrict", "ban", "limit", "prevent", "deny"]
        if any(keyword in vote_text for keyword in prohibit_keywords):
            # Invert scores for prohibit votes
            yea_score, nay_score = nay_score, yea_score
        
        return yea_score, nay_score
