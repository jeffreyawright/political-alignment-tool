"""
Rvoteview Scraper Module for Political Alignment Tool

This module handles data collection from Voteview.com, which provides valuable information
about representatives' voting records and ideological scores (NOMINATE scores).

Updated to use the correct API endpoints based on Voteview source code.
"""

import requests
import pandas as pd
import json
import logging
import sqlite3
from datetime import datetime
import time
import random

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('rvoteview_scraper')

class RvoteviewScraper:
    """
    A class to scrape data from Voteview.com API
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
        self.api_base_url = "https://voteview.com/api"
        self.headers = {
            'User-Agent': 'Political Alignment Tool/1.0',
        }
        if api_key:
            self.headers['Authorization'] = f'Bearer {api_key}'
        
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
        congress : int, optional
            Congress number to update (defaults to current)
            
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
            # Fetch Voteview members
            members_df = self.fetch_voteview_members(congress)
            
            # Update representatives with Voteview IDs and NOMINATE scores
            updated = self.update_representatives_with_voteview_data(members_df)
            results["representatives_updated"] = updated
            
            # Fetch votes for policy-relevant bills
            votes_df = self.fetch_voteview_votes(congress)
            
            # Process and store votes
            if not votes_df.empty:
                votes_processed = self.process_votes(votes_df)
                results["votes_collected"] = votes_processed
                
                # Create bill-question mappings
                mappings_created = self.create_bill_question_mappings(votes_df)
                results["bill_mappings_created"] = mappings_created
            
            return results
            
        except Exception as e:
            logger.error(f"Error running Voteview update: {e}")
            raise
    
    def fetch_voteview_members(self, congress=None):
        """
        Fetch members data from Voteview API
        
        Parameters:
        -----------
        congress : int, optional
            Congress number to fetch (defaults to current)
            
        Returns:
        --------
        pandas.DataFrame
            DataFrame containing member data
        """
        # Determine congress number if not provided
        if not congress:
            # Use 118th Congress (most recent complete data in Voteview)
            congress = 118
        
        # Build API URL and parameters
        url = f"{self.api_base_url}/getmembersbycongress"
        params = {
            "congress": congress,
            "chamber": ""  # Empty for both chambers
        }
        
        try:
            logger.info(f"Fetching members from Voteview for congress {congress}")
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Check if we have results
            if "results" not in data or not data["results"]:
                logger.warning(f"No members found for congress {congress}")
                return pd.DataFrame()
            
            # Convert to DataFrame
            members_df = pd.DataFrame(data["results"])
            logger.info(f"Fetched {len(members_df)} members from Voteview")
            return members_df
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"Error fetching members from Voteview: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching members: {e}")
            raise
    
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
        if members_df.empty:
            logger.warning("No members data to update representatives with")
            return 0
        
        updated_count = 0
        
        try:
            # Get existing representatives from database
            self.cursor.execute("SELECT id, bioguide_id, last_name, first_name FROM representatives")
            representatives = self.cursor.fetchall()
            
            for rep in representatives:
                rep_id, bioguide_id, last_name, first_name = rep
                
                # Try to match by bioguide_id first
                if bioguide_id:
                    matches = members_df[members_df['bioguide_id'] == bioguide_id]
                    
                    # If no match by bioguide_id, try name matching
                    if matches.empty:
                        # Try to match by last name and first name
                        matches = members_df[(members_df['lastname'].str.lower() == last_name.lower()) & 
                                           (members_df['firstname'].str.lower() == first_name.lower())]
                    
                    if not matches.empty:
                        # Get the first match
                        match = matches.iloc[0]
                        
                        # Update the representative with Voteview data
                        self.cursor.execute("""
                            UPDATE representatives 
                            SET voteview_id = ?, nominate_score1 = ?, nominate_score2 = ?
                            WHERE id = ?
                        """, (
                            str(match.get('icpsr', '')),
                            float(match.get('nominate_dim1', 0)),
                            float(match.get('nominate_dim2', 0)),
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
    
    def fetch_voteview_votes(self, congress=None, limit=100):
        """
        Fetch votes data from Voteview API
        
        Parameters:
        -----------
        congress : int, optional
            Congress number to fetch (defaults to current)
        limit : int, optional
            Maximum number of votes to fetch
            
        Returns:
        --------
        pandas.DataFrame
            DataFrame containing votes data
        """
        # Determine congress number if not provided
        if not congress:
            # Use 118th Congress (most recent complete data in Voteview)
            congress = 118
        
        # Build API URL
        url = f"{self.api_base_url}/getrollcalls"
        
        # Parameters for the API request
        params = {
            "congress": congress,
            "limit": limit,
            "sort": "date",
            "order": "desc"
        }
        
        try:
            logger.info(f"Fetching votes from Voteview for congress {congress}")
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Check if we have results
            if "rollcalls" not in data or not data["rollcalls"]:
                logger.warning(f"No votes found for congress {congress}")
                return pd.DataFrame()
            
            # Convert to DataFrame
            votes_df = pd.DataFrame(data["rollcalls"])
            logger.info(f"Fetched {len(votes_df)} votes from Voteview")
            return votes_df
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"Error fetching votes from Voteview: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching votes: {e}")
            raise
    
    def fetch_vote_details(self, vote_id):
        """
        Fetch details for a specific vote
        
        Parameters:
        -----------
        vote_id : str
            Vote ID in Voteview
            
        Returns:
        --------
        dict
            Vote details
        """
        url = f"{self.api_base_url}/getrollcall/{vote_id}"
        
        try:
            logger.info(f"Fetching vote details for vote {vote_id}")
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            return data
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"Error fetching vote details: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching vote details: {e}")
            raise
    
    def fetch_member_votes(self, voteview_id, congress=None):
        """
        Fetch votes for a specific member
        
        Parameters:
        -----------
        voteview_id : str
            Voteview ID (ICPSR) for the member
        congress : int, optional
            Congress number to fetch (defaults to current)
            
        Returns:
        --------
        pandas.DataFrame
            DataFrame containing member's votes
        """
        # Determine congress number if not provided
        if not congress:
            # Use 118th Congress (most recent complete data in Voteview)
            congress = 118
        
        url = f"{self.api_base_url}/getmembersvotes"
        
        # Parameters for the API request
        params = {
            "icpsr": voteview_id,
            "congress": congress
        }
        
        try:
            logger.info(f"Fetching votes for member {voteview_id} in congress {congress}")
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Check if we have results
            if "votes" not in data or not data["votes"]:
                logger.warning(f"No votes found for member {voteview_id}")
                return pd.DataFrame()
            
            # Convert to DataFrame
            member_votes_df = pd.DataFrame(data["votes"])
            logger.info(f"Fetched {len(member_votes_df)} votes for member {voteview_id}")
            return member_votes_df
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"Error fetching member votes: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching member votes: {e}")
            raise
    
    def process_votes(self, votes_df):
        """
        Process and store votes in the database
        
        Parameters:
        -----------
        votes_df : pandas.DataFrame
            DataFrame containing votes data
            
        Returns:
        --------
        int
            Number of votes processed
        """
        if votes_df.empty:
            logger.warning("No votes data to process")
            return 0
        
        processed_count = 0
        
        try:
            # Get representatives with Voteview IDs
            self.cursor.execute("SELECT id, voteview_id FROM representatives WHERE voteview_id IS NOT NULL")
            representatives = {row[1]: row[0] for row in self.cursor.fetchall()}
            
            for _, vote in votes_df.iterrows():
                # Fetch vote details to get individual member votes
                vote_details = self.fetch_vote_details(vote['rollnumber'])
                
                if not vote_details or 'votes' not in vote_details:
                    continue
                
                # Process each member's vote
                for member_vote in vote_details['votes']:
                    voteview_id = str(member_vote.get('icpsr', ''))
                    
                    # Skip if we don't have this representative in our database
                    if voteview_id not in representatives:
                        continue
                    
                    rep_id = representatives[voteview_id]
                    
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
                        vote.get('rollnumber', ''),
                        vote.get('date', ''),
                        member_vote.get('cast_code', ''),
                        vote.get('bill_number', ''),
                        vote.get('question', ''),
                        vote.get('result', '')
                    ))
                    processed_count += 1
                
                # Add a small delay to avoid overwhelming the API
                time.sleep(random.uniform(0.5, 1.5))
            
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
        if votes_df.empty:
            logger.warning("No votes data to create bill-question mappings")
            return 0
        
        mappings_created = 0
        
        try:
            # Get all questions from the database
            self.cursor.execute("SELECT id, question_text, policy_area_id FROM questions")
            questions = self.cursor.fetchall()
            
            for _, vote in votes_df.iterrows():
                bill_number = vote.get('bill_number', '')
                question_text = vote.get('question', '')
                
                if not bill_number or not question_text:
                    continue
                
                # Try to match the bill to relevant questions
                for question in questions:
                    question_id, question_text, policy_area_id = question
                    
                    # Simple keyword matching - this could be improved with NLP
                    relevance = self._calculate_relevance(vote, question_text)
                    
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
    
    def _calculate_relevance(self, vote, question_text):
        """
        Calculate relevance score between a vote and a question
        
        Parameters:
        -----------
        vote : pandas.Series
            Vote data
        question_text : str
            Question text
            
        Returns:
        --------
        float
            Relevance score (0-1)
        """
        # This is a simple implementation that could be improved with NLP
        vote_text = ' '.join([
            str(vote.get('bill_number', '')),
            str(vote.get('question', '')),
            str(vote.get('short_description', ''))
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
