"""
Rvoteview Scraper Module for Political Alignment Tool

This module handles data collection from Voteview.com, which provides valuable information
about representatives' voting records and ideological scores (NOMINATE scores).

Updated to use the correct API structure based on the Rvoteview R package.
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
    A class to scrape data from Voteview.com API using the same approach as the Rvoteview R package
    """
    
    def __init__(self, db_path, api_key=None):
        """
        Initialize the scraper with database path and optional API key
        
        Parameters:
        -----------
        db_path : str
            Path to the SQLite database
        api_key : str, optional
            API key for Voteview (if required)
        """
        self.db_path = db_path
        self.api_key = api_key
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
            # Search for votes related to gun policy
            policy_areas = ["gun", "firearm", "rifle"]
            policy_area = ", ".join(policy_areas)
            
            # Get votes related to gun policy
            votes_df = self.voteview_search(q=policy_area, congress=congress)
            
            if votes_df is not None and not votes_df.empty:
                # Download detailed vote data
                vote_data = self.voteview_download(votes_df['id'].tolist())
                
                # Extract member data from vote_data
                members_df = self._extract_members_from_vote_data(vote_data)
                
                # Update representatives with Voteview IDs and NOMINATE scores
                updated = self.update_representatives_with_voteview_data(members_df)
                results["representatives_updated"] = updated
                
                # Process and store votes
                votes_processed = self.process_votes(votes_df, vote_data)
                results["votes_collected"] = votes_processed
                
                # Create bill-question mappings
                mappings_created = self.create_bill_question_mappings(votes_df)
                results["bill_mappings_created"] = mappings_created
            
            return results
            
        except Exception as e:
            logger.error(f"Error running Voteview update: {e}")
            raise
    
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
            response = requests.post(url, data={'q': query_string, 'rapi': 1})
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
    
    def voteview_download(self, ids, perrequest=15):
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
                response = requests.post(url, data={'ids': ','.join(chunk), 'rapi': 1})
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
            # Get existing representatives from database
            self.cursor.execute("SELECT id, bioguide_id, last_name, first_name FROM representatives")
            representatives = self.cursor.fetchall()
            
            for rep in representatives:
                rep_id, bioguide_id, last_name, first_name = rep
                
                # Try to match by name
                if last_name and first_name:
                    # Create a normalized name for matching
                    rep_name = f"{last_name}, {first_name}".upper()
                    
                    # Find potential matches
                    matches = []
                    for _, member in members_df.iterrows():
                        if 'name' in member and member['name']:
                            member_name = member['name'].upper()
                            # Calculate similarity score
                            similarity = self._name_similarity(rep_name, member_name)
                            if similarity > 0.7:  # Threshold for considering a match
                                matches.append((similarity, member))
                    
                    # Sort by similarity score
                    matches.sort(reverse=True, key=lambda x: x[0])
                    
                    if matches:
                        # Get the best match
                        _, match = matches[0]
                        
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
            raise
    
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
        # Simple implementation - could be improved with more sophisticated algorithms
        name1 = name1.upper()
        name2 = name2.upper()
        
        # Check if last name matches
        last_name1 = name1.split(',')[0].strip() if ',' in name1 else name1.split()[-1].strip()
        last_name2 = name2.split(',')[0].strip() if ',' in name2 else name2.split()[-1].strip()
        
        if last_name1 == last_name2:
            return 0.8  # High score for last name match
        
        # Check for partial matches
        if last_name1 in last_name2 or last_name2 in last_name1:
            return 0.6  # Medium score for partial match
        
        # Check for initials match
        initials1 = ''.join([word[0] for word in name1.split() if word])
        initials2 = ''.join([word[0] for word in name2.split() if word])
        
        if initials1 == initials2:
            return 0.5  # Medium score for initials match
        
        # Low score for no match
        return 0.0
    
    def process_votes(self, votes_df, vote_data):
        """
        Process and store votes in the database
        
        Parameters:
        -----------
        votes_df : pandas.DataFrame
            DataFrame containing votes data from search
        vote_data : dict
            Detailed vote data from download
            
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
            representatives = {row[1]: row[0] for row in self.cursor.fetchall()}
            
            # Process vote data
            if 'votes' in vote_data and 'vote_data' in vote_data:
                votes_matrix = vote_data['votes']
                vote_metadata = pd.DataFrame(vote_data['vote_data'])
                
                # Process each vote
                for _, vote_info in votes_df.iterrows():
                    vote_id = vote_info.get('id')
                    
                    # Find vote in metadata
                    vote_meta = vote_metadata[vote_metadata['vname'] == vote_id].iloc[0] if not vote_metadata[vote_metadata['vname'] == vote_id].empty else {}
                    
                    # Process each member's vote
                    for member_id, member_votes in votes_matrix.items():
                        # Skip if we don't have this representative in our database
                        if member_id not in representatives:
                            continue
                        
                        rep_id = representatives[member_id]
                        
                        # Get vote position for this specific vote
                        vote_position = None
                        vote_index = vote_metadata.index[vote_metadata['vname'] == vote_id].tolist()
                        if vote_index:
                            vote_position = member_votes[vote_index[0]]
                        
                        if vote_position is not None:
                            # Store the vote in the database
                            self.cursor.execute("""
                                INSERT OR REPLACE INTO voting_records (
                                    representative_id, congress_number, chamber, session, 
                                    roll_call, vote_date, vote_position, bill_number, question, result
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                rep_id,
                                vote_meta.get('congress', ''),
                                vote_meta.get('chamber', ''),
                                '', # Session not available in this data
                                vote_meta.get('rollnumber', ''),
                                vote_meta.get('date', ''),
                                str(vote_position),
                                vote_meta.get('bill_number', ''),
                                vote_meta.get('question', ''),
                                vote_meta.get('vote_result', '')
                            ))
                            processed_count += 1
            
            self.conn.commit()
            logger.info(f"Processed {processed_count} votes")
            return processed_count
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error processing votes: {e}")
            raise
    
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
            # Get all questions from the database
            self.cursor.execute("SELECT id, question_text, policy_area_id FROM questions")
            questions = self.cursor.fetchall()
            
            for _, vote in votes_df.iterrows():
                bill_number = vote.get('bill_number', '')
                description = vote.get('description', '')
                short_description = vote.get('short_description', '')
                
                if not bill_number:
                    continue
                
                # Try to match the bill to relevant questions
                for question in questions:
                    question_id, question_text, policy_area_id = question
                    
                    # Simple keyword matching - this could be improved with NLP
                    relevance = self._calculate_relevance(description, short_description, question_text)
                    
                    if relevance > 0.5:  # Only create mappings for relevant bills
                        # Determine position values based on vote type
                        position_if_yes, position_if_no = self._determine_positions(vote)
                        
                        # Store the mapping in the database
                        self.cursor.execute("""
                            INSERT OR REPLACE INTO bill_question_mapping (
                                congress, bill_number, question_id, relevance,
                                position_if_yes, position_if_no, mapping_date
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            vote.get('congress', ''),
                            bill_number,
                            question_id,
                            relevance,
                            position_if_yes,
                            position_if_no,
                            datetime.now().strftime('%Y-%m-%d')
                        ))
                        mappings_created += 1
            
            self.conn.commit()
            logger.info(f"Created {mappings_created} bill-question mappings")
            return mappings_created
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error creating bill-question mappings: {e}")
            raise
    
    def _calculate_relevance(self, description, short_description, question_text):
        """
        Calculate relevance score between a vote and a question
        
        Parameters:
        -----------
        description : str
            Vote description
        short_description : str
            Short vote description
        question_text : str
            Question text
            
        Returns:
        --------
        float
            Relevance score (0-1)
        """
        # This is a simple implementation that could be improved with NLP
        vote_text = ' '.join([
            str(description),
            str(short_description)
        ]).lower()
        
        question_keywords = question_text.lower().split()
        
        # Count how many keywords from the question appear in the vote text
        matches = sum(1 for keyword in question_keywords if keyword in vote_text)
        
        # Calculate relevance score
        if len(question_keywords) > 0:
            return min(1.0, matches / len(question_keywords))
        else:
            return 0.0
    
    def _determine_positions(self, vote):
        """
        Determine position values for yes/no votes
        
        Parameters:
        -----------
        vote : pandas.Series
            Vote data
            
        Returns:
        --------
        tuple
            (position_if_yes, position_if_no)
        """
        # Default values
        position_if_yes = -1  # Favor (progressive)
        position_if_no = 1    # Oppose (conservative)
        
        # This is a simplified implementation
        # In a real system, you would need more sophisticated logic based on the bill content
        
        return position_if_yes, position_if_no
