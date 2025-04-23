import sqlite3
import logging
import requests
from datetime import datetime
import json
import re
import time
import random
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("congress_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("congress_scraper")

class CongressDataScraper:
    """
    Enhanced scraper for collecting data from Congress.gov API and website
    
    This class handles fetching and processing data about representatives,
    their voting records, bill information, and sponsorship/cosponsorship.
    """
    
    def __init__(self, db_path, api_key=None):
        """
        Initialize the scraper with database path and API key
        
        Args:
            db_path (str): Path to SQLite database
            api_key (str, optional): API key for Congress.gov API
        """
        self.db_path = db_path
        self.api_key = api_key
        self.conn = self._create_db_connection()
        self.api_base_url = "https://api.congress.gov/v3"
        self.web_base_url = "https://www.congress.gov"
        
        # Define headers for API requests
        self.headers = {
            "User-Agent": "Political Alignment Tool/1.0",
            "Accept": "application/json"
        }
        
        # Initialize TF-IDF vectorizer for text similarity
        self.vectorizer = TfidfVectorizer(stop_words='english')
        
    def _create_db_connection(self):
        """
        Create database connection
        
        Returns:
            sqlite3.Connection: Database connection
        """
        try:
            conn = sqlite3.connect(self.db_path)
            return conn
        except sqlite3.Error as e:
            logger.error(f"Error connecting to database: {e}")
            raise
            
    def initialize_database(self, schema_file):
        """
        Initialize database with schema
        
        Args:
            schema_file (str): Path to SQL schema file
        """
        try:
            with open(schema_file, 'r') as f:
                schema = f.read()
                
            self.conn.executescript(schema)
            self.conn.commit()
            logger.info(f"Database initialized with schema from {schema_file}")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
            
    def fetch_current_members(self, chamber=None):
        """
        Fetch current members of Congress
        
        Args:
            chamber (str, optional): Chamber ('house' or 'senate')
            
        Returns:
            list: List of member dictionaries
        """
        try:
            members = []
            
            # Determine chambers to fetch
            chambers = []
            if chamber:
                chambers = [chamber.lower()]
            else:
                chambers = ['house', 'senate']
                
            # Fetch members for each chamber
            for c in chambers:
                logger.info(f"Fetching current members of {c}")
                
                # Use API if key is available, otherwise scrape website
                if self.api_key:
                    members.extend(self._fetch_members_from_api(c))
                else:
                    members.extend(self._fetch_members_from_web(c))
                    
                # Add small delay to avoid rate limiting
                time.sleep(1)
                
            logger.info(f"Fetched {len(members)} members")
            return members
        except Exception as e:
            logger.error(f"Error fetching current members: {e}")
            raise
            
    def _fetch_members_from_api(self, chamber):
        """
        Fetch members from Congress.gov API
        
        Args:
            chamber (str): Chamber ('house' or 'senate')
            
        Returns:
            list: List of member dictionaries
        """
        members = []
        
        try:
            # Determine current congress number
            current_congress = self._get_current_congress()
            
            # Build API URL
            url = f"{self.api_base_url}/member"
            params = {
                "api_key": self.api_key,
                "congress": current_congress,
                "chamber": chamber,
                "format": "json",
                "limit": 250  # Maximum allowed
            }
            
            # Make request
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Process members
            for member in data.get("members", []):
                member_data = {
                    "bioguide_id": member.get("bioguideId"),
                    "first_name": member.get("firstName"),
                    "last_name": member.get("lastName"),
                    "state": member.get("state"),
                    "district": member.get("district"),
                    "party": self._normalize_party(member.get("party")),
                    "chamber": chamber,
                    "congress_number": current_congress
                }
                
                members.append(member_data)
                
            return members
        except Exception as e:
            logger.error(f"Error fetching members from API: {e}")
            raise
            
    def _fetch_members_from_web(self, chamber):
        """
        Fetch members from Congress.gov website
        
        Args:
            chamber (str): Chamber ('house' or 'senate')
            
        Returns:
            list: List of member dictionaries
        """
        members = []
        
        try:
            # Determine current congress number
            current_congress = self._get_current_congress()
            
            # Build URL
            url = f"{self.web_base_url}/members?chamber={chamber}&congress={current_congress}"
            
            # Make request
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find member table
            member_table = soup.find('table', class_='table')
            if not member_table:
                logger.warning(f"No member table found for {chamber}")
                return members
                
            # Process rows
            for row in member_table.find_all('tr')[1:]:  # Skip header row
                cols = row.find_all('td')
                if len(cols) < 3:
                    continue
                    
                # Extract data
                name_col = cols[0]
                party_state_col = cols[1]
                district_col = cols[2] if len(cols) > 2 else None
                
                # Get name
                name_link = name_col.find('a')
                if not name_link:
                    continue
                    
                name_text = name_link.text.strip()
                name_parts = name_text.split(',')
                last_name = name_parts[0].strip() if name_parts else ""
                first_name = name_parts[1].strip() if len(name_parts) > 1 else ""
                
                # Get bioguide ID from URL
                bioguide_id = None
                href = name_link.get('href', '')
                bioguide_match = re.search(r'/member/(\w+)(?:\?|$)', href)
                if bioguide_match:
                    bioguide_id = bioguide_match.group(1)
                    
                # Get party and state
                party_state_text = party_state_col.text.strip()
                party_match = re.search(r'([A-Z]+)-([A-Z]{2})', party_state_text)
                
                party = None
                state = None
                if party_match:
                    party = self._normalize_party(party_match.group(1))
                    state = party_match.group(2)
                    
                # Get district
                district = None
                if district_col:
                    district_text = district_col.text.strip()
                    if district_text and district_text.isdigit():
                        district = district_text
                        
                # Create member data
                if bioguide_id and last_name:
                    member_data = {
                        "bioguide_id": bioguide_id,
                        "first_name": first_name,
                        "last_name": last_name,
                        "state": state,
                        "district": district,
                        "party": party,
                        "chamber": chamber,
                        "congress_number": current_congress
                    }
                    
                    members.append(member_data)
                    
            return members
        except Exception as e:
            logger.error(f"Error fetching members from web: {e}")
            raise
            
    def _normalize_party(self, party_text):
        """
        Normalize party text
        
        Args:
            party_text (str): Party text
            
        Returns:
            str: Normalized party code
        """
        if not party_text:
            return None
            
        party_text = party_text.upper()
        
        if "DEMOCRAT" in party_text or party_text == "D":
            return "D"
        elif "REPUBLICAN" in party_text or party_text == "R":
            return "R"
        elif "INDEPENDENT" in party_text or party_text == "I":
            return "I"
        else:
            return party_text[:1] if party_text else "Unknown"
            
    def _get_current_congress(self):
        """
        Get the current Congress number
        
        Returns:
            int: Current Congress number
        """
        # Calculate current Congress number based on year
        current_year = datetime.now().year
        return ((current_year - 1789) // 2) + 1
        
    def save_members_to_db(self, members):
        """
        Save members to database
        
        Args:
            members (list): List of member dictionaries
            
        Returns:
            int: Number of members saved
        """
        try:
            cursor = self.conn.cursor()
            
            # Prepare SQL
            sql = """
            INSERT OR REPLACE INTO representatives (
                bioguide_id, first_name, last_name, state, district, 
                party, chamber, congress_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            # Insert members
            count = 0
            for member in members:
                cursor.execute(sql, (
                    member.get("bioguide_id"),
                    member.get("first_name"),
                    member.get("last_name"),
                    member.get("state"),
                    member.get("district"),
                    member.get("party"),
                    member.get("chamber"),
                    member.get("congress_number")
                ))
                count += 1
                
            self.conn.commit()
            logger.info(f"Saved {count} members to database")
            return count
        except Exception as e:
            logger.error(f"Error saving members to database: {e}")
            raise
            
    def fetch_member_votes(self, bioguide_id, limit=100):
        """
        Fetch voting record for a member
        
        Args:
            bioguide_id (str): Bioguide ID
            limit (int, optional): Maximum number of votes to fetch
            
        Returns:
            list: List of vote dictionaries
        """
        try:
            votes = []
            
            # Use API if key is available, otherwise scrape website
            if self.api_key:
                votes = self._fetch_votes_from_api(bioguide_id, limit)
            else:
                votes = self._fetch_votes_from_web(bioguide_id, limit)
                
            logger.info(f"Fetched {len(votes)} votes for member {bioguide_id}")
            return votes
        except Exception as e:
            logger.error(f"Error fetching votes for member {bioguide_id}: {e}")
            raise
            
    def _fetch_votes_from_api(self, bioguide_id, limit):
        """
        Fetch votes from Congress.gov API
        
        Args:
            bioguide_id (str): Bioguide ID
            limit (int): Maximum number of votes to fetch
            
        Returns:
            list: List of vote dictionaries
        """
        votes = []
        
        try:
            # Determine current congress number
            current_congress = self._get_current_congress()
            
            # Build API URL
            url = f"{self.api_base_url}/member/{bioguide_id}/votes"
            params = {
                "api_key": self.api_key,
                "format": "json",
                "limit": min(limit, 250),  # Maximum allowed by API
                "offset": 0
            }
            
            # Make request
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Process votes
            for vote in data.get("votes", []):
                vote_data = {
                    "bioguide_id": bioguide_id,
                    "congress_number": vote.get("congress"),
                    "chamber": vote.get("chamber", "").lower(),
                    "session": vote.get("session"),
                    "roll_call": vote.get("rollCall"),
                    "vote_date": vote.get("date"),
                    "vote_position": vote.get("position"),
                    "bill_number": vote.get("billNumber"),
                    "amendment_number": vote.get("amendmentNumber"),
                    "question": vote.get("question"),
                    "result": vote.get("result")
                }
                
                votes.append(vote_data)
                
            return votes
        except Exception as e:
            logger.error(f"Error fetching votes from API: {e}")
            raise
            
    def _fetch_votes_from_web(self, bioguide_id, limit):
        """
        Fetch votes from Congress.gov website
        
        Args:
            bioguide_id (str): Bioguide ID
            limit (int): Maximum number of votes to fetch
            
        Returns:
            list: List of vote dictionaries
        """
        votes = []
        
        try:
            # Determine current congress number
            current_congress = self._get_current_congress()
            
            # Build URL
            url = f"{self.web_base_url}/member/{bioguide_id}/votes"
            
            # Make request
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find vote tables
            vote_tables = soup.find_all('table', class_='item_table')
            
            for table in vote_tables:
                # Process rows
                for row in table.find_all('tr')[1:]:  # Skip header row
                    cols = row.find_all('td')
                    if len(cols) < 5:
                        continue
                        
                    # Extract data
                    date_col = cols[0]
                    bill_col = cols[1]
                    question_col = cols[2]
                    result_col = cols[3]
                    position_col = cols[4]
                    
                    # Get date
                    vote_date = self._parse_date(date_col.text.strip())
                    
                    # Get bill number
                    bill_link = bill_col.find('a')
                    bill_number = bill_link.text.strip() if bill_link else None
                    
                    # Get question
                    question = question_col.text.strip()
                    
                    # Get result
                    result = result_col.text.strip()
                    
                    # Get position
                    position = position_col.text.strip()
                    
                    # Extract congress and session from URL
                    congress_session = self._extract_congress_session(bill_link.get("href") if bill_link else "")
                    
                    # Create vote data
                    vote_data = {
                        "bioguide_id": bioguide_id,
                        "congress_number": congress_session.get("congress"),
                        "chamber": "house" if "house" in url.lower() else "senate",
                        "session": congress_session.get("session"),
                        "roll_call": None,  # Not available from this page
                        "vote_date": vote_date,
                        "vote_position": position,
                        "bill_number": bill_number,
                        "amendment_number": None,  # Not available from this page
                        "question": question,
                        "result": result
                    }
                    
                    votes.append(vote_data)
                    
                if len(votes) >= limit:
                    break
            
            return votes
        except Exception as e:
            logger.error(f"Error fetching votes from web: {e}")
            raise
            
    def _parse_date(self, date_text):
        """
        Parse date from text
        
        Args:
            date_text (str): Date text
            
        Returns:
            str: ISO format date or None
        """
        try:
            # Try different date formats
            for fmt in ["%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"]:
                try:
                    return datetime.strptime(date_text, fmt).isoformat()
                except ValueError:
                    continue
                    
            return None
        except Exception:
            return None
            
    def _extract_congress_session(self, url):
        """
        Extract congress and session from URL
        
        Args:
            url (str): URL
            
        Returns:
            dict: Congress and session
        """
        result = {
            "congress": self._get_current_congress(),
            "session": 1
        }
        
        if not url:
            return result
            
        # Extract congress
        congress_match = re.search(r'/(\d+)(?:st|nd|rd|th)/congress/', url)
        if congress_match:
            result["congress"] = int(congress_match.group(1))
            
        # Extract session
        session_match = re.search(r'/(\d+)/session', url)
        if session_match:
            result["session"] = int(session_match.group(1))
            
        return result
        
    def save_votes_to_db(self, bioguide_id, votes):
        """
        Save votes to database
        
        Args:
            bioguide_id (str): Bioguide ID
            votes (list): List of vote dictionaries
            
        Returns:
            int: Number of votes saved
        """
        try:
            cursor = self.conn.cursor()
            
            # Get representative ID
            cursor.execute(
                "SELECT id FROM representatives WHERE bioguide_id = ?",
                (bioguide_id,)
            )
            
            rep_row = cursor.fetchone()
            if not rep_row:
                logger.warning(f"Representative not found for bioguide_id {bioguide_id}")
                return 0
                
            rep_id = rep_row[0]
            
            # Prepare SQL
            sql = """
            INSERT OR REPLACE INTO voting_records (
                representative_id, congress_number, chamber, session,
                roll_call, vote_date, vote_position, bill_number,
                question, result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            # Insert votes
            count = 0
            for vote in votes:
                cursor.execute(sql, (
                    rep_id,
                    vote.get("congress_number"),
                    vote.get("chamber"),
                    vote.get("session"),
                    vote.get("roll_call"),
                    vote.get("vote_date"),
                    vote.get("vote_position"),
                    vote.get("bill_number"),
                    vote.get("question"),
                    vote.get("result")
                ))
                count += 1
                
            self.conn.commit()
            logger.info(f"Saved {count} votes for representative {bioguide_id}")
            return count
        except Exception as e:
            logger.error(f"Error saving votes to database: {e}")
            raise
            
    def fetch_bill_details(self, congress, bill_number):
        """
        Fetch details for a bill
        
        Args:
            congress (int): Congress number
            bill_number (str): Bill number
            
        Returns:
            dict: Bill details
        """
        try:
            # Extract bill type and number
            bill_match = re.match(r'([A-Z]+)(\d+)', bill_number)
            if not bill_match:
                logger.warning(f"Invalid bill number format: {bill_number}")
                return {}
                
            bill_type = bill_match.group(1).lower()
            number = bill_match.group(2)
            
            # Use API if key is available, otherwise scrape website
            if self.api_key:
                return self._fetch_bill_from_api(congress, bill_type, number)
            else:
                return self._fetch_bill_from_web(congress, bill_type, number)
        except Exception as e:
            logger.error(f"Error fetching bill details: {e}")
            return {}
            
    def _fetch_bill_from_api(self, congress, bill_type, number):
        """
        Fetch bill from Congress.gov API
        
        Args:
            congress (int): Congress number
            bill_type (str): Bill type
            number (str): Bill number
            
        Returns:
            dict: Bill details
        """
        try:
            # Build API URL
            url = f"{self.api_base_url}/bill/{congress}/{bill_type}/{number}"
            params = {
                "api_key": self.api_key,
                "format": "json"
            }
            
            # Make request
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            bill = data.get("bill", {})
            
            # Extract bill details
            bill_details = {
                "congress": congress,
                "bill_type": bill_type,
                "bill_number": f"{bill_type.upper()}{number}",
                "title": bill.get("title"),
                "summary": bill.get("summary", {}).get("text"),
                "introduced_date": bill.get("introducedDate"),
                "sponsor": bill.get("sponsors", [{}])[0].get("bioguideId") if bill.get("sponsors") else None,
                "cosponsors": [cosponsor.get("bioguideId") for cosponsor in bill.get("cosponsors", [])],
                "subjects": [subject.get("name") for subject in bill.get("subjects", [])],
                "latest_action": bill.get("latestAction", {}).get("text"),
                "latest_action_date": bill.get("latestAction", {}).get("actionDate")
            }
            
            return bill_details
        except Exception as e:
            logger.error(f"Error fetching bill from API: {e}")
            return {}
            
    def _fetch_bill_from_web(self, congress, bill_type, number):
        """
        Fetch bill from Congress.gov website
        
        Args:
            congress (int): Congress number
            bill_type (str): Bill type
            number (str): Bill number
            
        Returns:
            dict: Bill details
        """
        try:
            # Build URL
            url = f"{self.web_base_url}/bill/{congress}th-congress/{bill_type}{number}"
            
            # Make request
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract bill details
            title = soup.find('h1', class_='legDetail')
            title_text = title.text.strip() if title else None
            
            # Get summary
            summary_div = soup.find('div', id='bill-summary')
            summary_text = summary_div.text.strip() if summary_div else None
            
            # Get sponsor
            sponsor_div = soup.find('div', class_='sponsor')
            sponsor_link = sponsor_div.find('a') if sponsor_div else None
            sponsor_id = None
            if sponsor_link:
                sponsor_href = sponsor_link.get('href', '')
                sponsor_match = re.search(r'/member/(\w+)(?:\?|$)', sponsor_href)
                if sponsor_match:
                    sponsor_id = sponsor_match.group(1)
                    
            # Get cosponsors
            cosponsor_div = soup.find('div', id='cosponsors')
            cosponsors = []
            if cosponsor_div:
                for link in cosponsor_div.find_all('a'):
                    href = link.get('href', '')
                    cosponsor_match = re.search(r'/member/(\w+)(?:\?|$)', href)
                    if cosponsor_match:
                        cosponsors.append(cosponsor_match.group(1))
                        
            # Get subjects
            subjects_div = soup.find('div', id='subjects')
            subjects = []
            if subjects_div:
                for li in subjects_div.find_all('li'):
                    subjects.append(li.text.strip())
                    
            # Get latest action
            action_div = soup.find('div', class_='latestAction')
            latest_action = action_div.text.strip() if action_div else None
            
            # Get introduced date
            intro_div = soup.find('div', class_='introduced')
            intro_date = None
            if intro_div:
                date_text = intro_div.text.strip()
                date_match = re.search(r'(\d{2}/\d{2}/\d{4})', date_text)
                if date_match:
                    intro_date = date_match.group(1)
                    
            # Create bill details
            bill_details = {
                "congress": congress,
                "bill_type": bill_type,
                "bill_number": f"{bill_type.upper()}{number}",
                "title": title_text,
                "summary": summary_text,
                "introduced_date": intro_date,
                "sponsor": sponsor_id,
                "cosponsors": cosponsors,
                "subjects": subjects,
                "latest_action": latest_action,
                "latest_action_date": None  # Not easily available from the page
            }
            
            return bill_details
        except Exception as e:
            logger.error(f"Error fetching bill from web: {e}")
            return {}
            
    def fetch_bill_sponsorships(self, bioguide_id, limit=100):
        """
        Fetch bills sponsored or cosponsored by a member
        
        Args:
            bioguide_id (str): Bioguide ID
            limit (int, optional): Maximum number of bills to fetch
            
        Returns:
            dict: Dictionary with sponsored and cosponsored bills
        """
        try:
            result = {
                "sponsored": [],
                "cosponsored": []
            }
            
            # Use API if key is available, otherwise scrape website
            if self.api_key:
                result["sponsored"] = self._fetch_sponsored_bills_from_api(bioguide_id, limit)
                result["cosponsored"] = self._fetch_cosponsored_bills_from_api(bioguide_id, limit)
            else:
                result["sponsored"] = self._fetch_sponsored_bills_from_web(bioguide_id, limit)
                result["cosponsored"] = self._fetch_cosponsored_bills_from_web(bioguide_id, limit)
                
            logger.info(f"Fetched {len(result['sponsored'])} sponsored and {len(result['cosponsored'])} cosponsored bills for member {bioguide_id}")
            return result
        except Exception as e:
            logger.error(f"Error fetching bill sponsorships: {e}")
            return {"sponsored": [], "cosponsored": []}
            
    def _fetch_sponsored_bills_from_api(self, bioguide_id, limit):
        """
        Fetch sponsored bills from Congress.gov API
        
        Args:
            bioguide_id (str): Bioguide ID
            limit (int): Maximum number of bills to fetch
            
        Returns:
            list: List of bill dictionaries
        """
        try:
            # Build API URL
            url = f"{self.api_base_url}/member/{bioguide_id}/sponsored-legislation"
            params = {
                "api_key": self.api_key,
                "format": "json",
                "limit": min(limit, 250),  # Maximum allowed by API
                "offset": 0
            }
            
            # Make request
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Process bills
            bills = []
            for bill in data.get("sponsoredLegislation", []):
                bill_data = {
                    "congress": bill.get("congress"),
                    "bill_type": bill.get("type", "").lower(),
                    "bill_number": bill.get("number"),
                    "title": bill.get("title"),
                    "introduced_date": bill.get("introducedDate"),
                    "latest_action": bill.get("latestAction", {}).get("text"),
                    "latest_action_date": bill.get("latestAction", {}).get("actionDate"),
                    "url": bill.get("url")
                }
                
                bills.append(bill_data)
                
            return bills
        except Exception as e:
            logger.error(f"Error fetching sponsored bills from API: {e}")
            return []
            
    def _fetch_cosponsored_bills_from_api(self, bioguide_id, limit):
        """
        Fetch cosponsored bills from Congress.gov API
        
        Args:
            bioguide_id (str): Bioguide ID
            limit (int): Maximum number of bills to fetch
            
        Returns:
            list: List of bill dictionaries
        """
        try:
            # Build API URL
            url = f"{self.api_base_url}/member/{bioguide_id}/cosponsored-legislation"
            params = {
                "api_key": self.api_key,
                "format": "json",
                "limit": min(limit, 250),  # Maximum allowed by API
                "offset": 0
            }
            
            # Make request
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Process bills
            bills = []
            for bill in data.get("cosponsoredLegislation", []):
                bill_data = {
                    "congress": bill.get("congress"),
                    "bill_type": bill.get("type", "").lower(),
                    "bill_number": bill.get("number"),
                    "title": bill.get("title"),
                    "introduced_date": bill.get("introducedDate"),
                    "latest_action": bill.get("latestAction", {}).get("text"),
                    "latest_action_date": bill.get("latestAction", {}).get("actionDate"),
                    "url": bill.get("url"),
                    "sponsor": bill.get("sponsor", {}).get("bioguideId")
                }
                
                bills.append(bill_data)
                
            return bills
        except Exception as e:
            logger.error(f"Error fetching cosponsored bills from API: {e}")
            return []
            
    def _fetch_sponsored_bills_from_web(self, bioguide_id, limit):
        """
        Fetch sponsored bills from Congress.gov website
        
        Args:
            bioguide_id (str): Bioguide ID
            limit (int): Maximum number of bills to fetch
            
        Returns:
            list: List of bill dictionaries
        """
        try:
            # Build URL
            url = f"{self.web_base_url}/member/{bioguide_id}/sponsored-legislation"
            
            # Make request
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find bill table
            bill_table = soup.find('table', class_='item_table')
            if not bill_table:
                logger.warning(f"No bill table found for {bioguide_id}")
                return []
                
            # Process rows
            bills = []
            for row in bill_table.find_all('tr')[1:]:  # Skip header row
                cols = row.find_all('td')
                if len(cols) < 3:
                    continue
                    
                # Extract data
                bill_col = cols[0]
                title_col = cols[1]
                date_col = cols[2]
                
                # Get bill number
                bill_link = bill_col.find('a')
                if not bill_link:
                    continue
                    
                bill_text = bill_link.text.strip()
                bill_href = bill_link.get('href', '')
                
                # Extract congress and bill info from URL
                congress_match = re.search(r'/(\d+)(?:st|nd|rd|th)/congress/([a-z]+)(\d+)', bill_href)
                if not congress_match:
                    continue
                    
                congress = int(congress_match.group(1))
                bill_type = congress_match.group(2)
                bill_number = congress_match.group(3)
                
                # Get title
                title = title_col.text.strip()
                
                # Get date
                date = self._parse_date(date_col.text.strip())
                
                # Create bill data
                bill_data = {
                    "congress": congress,
                    "bill_type": bill_type,
                    "bill_number": f"{bill_type.upper()}{bill_number}",
                    "title": title,
                    "introduced_date": date,
                    "latest_action": None,  # Not available from this page
                    "latest_action_date": None,
                    "url": f"{self.web_base_url}{bill_href}"
                }
                
                bills.append(bill_data)
                
                if len(bills) >= limit:
                    break
                    
            return bills
        except Exception as e:
            logger.error(f"Error fetching sponsored bills from web: {e}")
            return []
            
    def _fetch_cosponsored_bills_from_web(self, bioguide_id, limit):
        """
        Fetch cosponsored bills from Congress.gov website
        
        Args:
            bioguide_id (str): Bioguide ID
            limit (int): Maximum number of bills to fetch
            
        Returns:
            list: List of bill dictionaries
        """
        try:
            # Build URL
            url = f"{self.web_base_url}/member/{bioguide_id}/cosponsored-legislation"
            
            # Make request
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find bill table
            bill_table = soup.find('table', class_='item_table')
            if not bill_table:
                logger.warning(f"No bill table found for {bioguide_id}")
                return []
                
            # Process rows
            bills = []
            for row in bill_table.find_all('tr')[1:]:  # Skip header row
                cols = row.find_all('td')
                if len(cols) < 4:
                    continue
                    
                # Extract data
                bill_col = cols[0]
                title_col = cols[1]
                sponsor_col = cols[2]
                date_col = cols[3]
                
                # Get bill number
                bill_link = bill_col.find('a')
                if not bill_link:
                    continue
                    
                bill_text = bill_link.text.strip()
                bill_href = bill_link.get('href', '')
                
                # Extract congress and bill info from URL
                congress_match = re.search(r'/(\d+)(?:st|nd|rd|th)/congress/([a-z]+)(\d+)', bill_href)
                if not congress_match:
                    continue
                    
                congress = int(congress_match.group(1))
                bill_type = congress_match.group(2)
                bill_number = congress_match.group(3)
                
                # Get title
                title = title_col.text.strip()
                
                # Get sponsor
                sponsor_link = sponsor_col.find('a')
                sponsor_id = None
                if sponsor_link:
                    sponsor_href = sponsor_link.get('href', '')
                    sponsor_match = re.search(r'/member/(\w+)(?:\?|$)', sponsor_href)
                    if sponsor_match:
                        sponsor_id = sponsor_match.group(1)
                        
                # Get date
                date = self._parse_date(date_col.text.strip())
                
                # Create bill data
                bill_data = {
                    "congress": congress,
                    "bill_type": bill_type,
                    "bill_number": f"{bill_type.upper()}{bill_number}",
                    "title": title,
                    "introduced_date": date,
                    "latest_action": None,  # Not available from this page
                    "latest_action_date": None,
                    "url": f"{self.web_base_url}{bill_href}",
                    "sponsor": sponsor_id
                }
                
                bills.append(bill_data)
                
                if len(bills) >= limit:
                    break
                    
            return bills
        except Exception as e:
            logger.error(f"Error fetching cosponsored bills from web: {e}")
            return []
            
    def save_bill_sponsorships_to_db(self, bioguide_id, sponsorships):
        """
        Save bill sponsorships to database
        
        Args:
            bioguide_id (str): Bioguide ID
            sponsorships (dict): Dictionary with sponsored and cosponsored bills
            
        Returns:
            dict: Number of sponsored and cosponsored bills saved
        """
        try:
            cursor = self.conn.cursor()
            
            # Get representative ID
            cursor.execute(
                "SELECT id FROM representatives WHERE bioguide_id = ?",
                (bioguide_id,)
            )
            
            rep_row = cursor.fetchone()
            if not rep_row:
                logger.warning(f"Representative not found for bioguide_id {bioguide_id}")
                return {"sponsored": 0, "cosponsored": 0}
                
            rep_id = rep_row[0]
            
            # Create bill_sponsorships table if it doesn't exist
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS bill_sponsorships (
                id INTEGER PRIMARY KEY,
                representative_id INTEGER NOT NULL,
                congress INTEGER,
                bill_type TEXT,
                bill_number TEXT,
                sponsorship_type TEXT,
                introduced_date TEXT,
                FOREIGN KEY (representative_id) REFERENCES representatives (id)
            )
            """)
            
            # Create bills table if it doesn't exist
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY,
                congress INTEGER,
                bill_type TEXT,
                bill_number TEXT,
                title TEXT,
                summary TEXT,
                introduced_date TEXT,
                sponsor_id INTEGER,
                latest_action TEXT,
                latest_action_date TEXT,
                UNIQUE(congress, bill_type, bill_number)
            )
            """)
            
            # Prepare SQL for bill_sponsorships
            sponsorship_sql = """
            INSERT OR REPLACE INTO bill_sponsorships (
                representative_id, congress, bill_type, bill_number,
                sponsorship_type, introduced_date
            ) VALUES (?, ?, ?, ?, ?, ?)
            """
            
            # Prepare SQL for bills
            bill_sql = """
            INSERT OR REPLACE INTO bills (
                congress, bill_type, bill_number, title,
                introduced_date, latest_action, latest_action_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            
            # Insert sponsored bills
            sponsored_count = 0
            for bill in sponsorships.get("sponsored", []):
                # Insert bill
                cursor.execute(bill_sql, (
                    bill.get("congress"),
                    bill.get("bill_type"),
                    bill.get("bill_number"),
                    bill.get("title"),
                    bill.get("introduced_date"),
                    bill.get("latest_action"),
                    bill.get("latest_action_date")
                ))
                
                # Insert sponsorship
                cursor.execute(sponsorship_sql, (
                    rep_id,
                    bill.get("congress"),
                    bill.get("bill_type"),
                    bill.get("bill_number"),
                    "sponsor",
                    bill.get("introduced_date")
                ))
                
                sponsored_count += 1
                
            # Insert cosponsored bills
            cosponsored_count = 0
            for bill in sponsorships.get("cosponsored", []):
                # Insert bill
                cursor.execute(bill_sql, (
                    bill.get("congress"),
                    bill.get("bill_type"),
                    bill.get("bill_number"),
                    bill.get("title"),
                    bill.get("introduced_date"),
                    bill.get("latest_action"),
                    bill.get("latest_action_date")
                ))
                
                # Insert sponsorship
                cursor.execute(sponsorship_sql, (
                    rep_id,
                    bill.get("congress"),
                    bill.get("bill_type"),
                    bill.get("bill_number"),
                    "cosponsor",
                    bill.get("introduced_date")
                ))
                
                cosponsored_count += 1
                
            self.conn.commit()
            logger.info(f"Saved {sponsored_count} sponsored and {cosponsored_count} cosponsored bills for representative {bioguide_id}")
            
            return {
                "sponsored": sponsored_count,
                "cosponsored": cosponsored_count
            }
        except Exception as e:
            logger.error(f"Error saving bill sponsorships to database: {e}")
            raise
            
    def map_bill_to_questions(self, congress, bill_number, bill_details, questions):
        """
        Map a bill to survey questions
        
        Args:
            congress (int): Congress number
            bill_number (str): Bill number
            bill_details (dict): Bill details
            questions (list): List of question dictionaries
            
        Returns:
            list: List of bill-question mapping dictionaries
        """
        try:
            mappings = []
            
            # Extract bill text for similarity comparison
            bill_text = ""
            if bill_details.get("title"):
                bill_text += bill_details.get("title") + " "
            if bill_details.get("summary"):
                bill_text += bill_details.get("summary") + " "
            if bill_details.get("subjects"):
                bill_text += " ".join(bill_details.get("subjects")) + " "
                
            # Skip if no text available
            if not bill_text.strip():
                logger.warning(f"No text available for bill {bill_number}")
                return mappings
                
            # Process each question
            for question in questions:
                question_id = question.get("id")
                question_text = question.get("question_text")
                policy_area = question.get("policy_area_name")
                
                # Calculate relevance score using TF-IDF and cosine similarity
                relevance = self._calculate_text_similarity(bill_text, question_text)
                
                # Determine position mapping based on bill content and question
                position_mapping = self._determine_position_mapping(bill_text, question_text)
                
                # Only include mappings with sufficient relevance
                if relevance >= 0.1:  # Threshold for relevance
                    mapping = {
                        "congress": congress,
                        "bill_number": bill_number,
                        "question_id": question_id,
                        "relevance": relevance,
                        "position_if_yes": position_mapping.get("position_if_yes"),
                        "position_if_no": position_mapping.get("position_if_no"),
                        "mapping_date": datetime.now().isoformat()
                    }
                    
                    mappings.append(mapping)
                    
            logger.info(f"Created {len(mappings)} mappings for bill {bill_number}")
            return mappings
        except Exception as e:
            logger.error(f"Error mapping bill to questions: {e}")
            return []
            
    def _calculate_text_similarity(self, text1, text2):
        """
        Calculate similarity between two texts using TF-IDF and cosine similarity
        
        Args:
            text1 (str): First text
            text2 (str): Second text
            
        Returns:
            float: Similarity score (0-1)
        """
        try:
            # Handle empty texts
            if not text1 or not text2:
                return 0
                
            # Fit vectorizer on both texts
            tfidf_matrix = self.vectorizer.fit_transform([text1, text2])
            
            # Calculate cosine similarity
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            
            return similarity
        except Exception as e:
            logger.error(f"Error calculating text similarity: {e}")
            return 0
            
    def _determine_position_mapping(self, bill_text, question_text):
        """
        Determine position mapping based on bill content and question
        
        Args:
            bill_text (str): Bill text
            question_text (str): Question text
            
        Returns:
            dict: Position mapping
        """
        # This is a simplified implementation
        # In a real system, this would use more sophisticated NLP
        # to determine the position mapping based on bill content
        
        # Default mapping (neutral)
        mapping = {
            "position_if_yes": 0,
            "position_if_no": 0
        }
        
        # Look for keywords indicating support or opposition
        support_keywords = ["support", "favor", "approve", "increase", "expand", "strengthen"]
        oppose_keywords = ["oppose", "against", "prohibit", "restrict", "limit", "reduce"]
        
        bill_text_lower = bill_text.lower()
        question_text_lower = question_text.lower()
        
        # Check for support keywords
        support_in_bill = any(keyword in bill_text_lower for keyword in support_keywords)
        support_in_question = any(keyword in question_text_lower for keyword in support_keywords)
        
        # Check for oppose keywords
        oppose_in_bill = any(keyword in bill_text_lower for keyword in oppose_keywords)
        oppose_in_question = any(keyword in question_text_lower for keyword in oppose_keywords)
        
        # Determine mapping based on keyword presence
        if support_in_bill and support_in_question:
            mapping["position_if_yes"] = -2  # Favor
            mapping["position_if_no"] = 2    # Oppose
        elif support_in_bill and oppose_in_question:
            mapping["position_if_yes"] = 2   # Oppose
            mapping["position_if_no"] = -2   # Favor
        elif oppose_in_bill and support_in_question:
            mapping["position_if_yes"] = 2   # Oppose
            mapping["position_if_no"] = -2   # Favor
        elif oppose_in_bill and oppose_in_question:
            mapping["position_if_yes"] = -2  # Favor
            mapping["position_if_no"] = 2    # Oppose
            
        return mapping
        
    def save_bill_mappings_to_db(self, mappings):
        """
        Save bill-question mappings to database
        
        Args:
            mappings (list): List of bill-question mapping dictionaries
            
        Returns:
            int: Number of mappings saved
        """
        try:
            cursor = self.conn.cursor()
            
            # Prepare SQL
            sql = """
            INSERT OR REPLACE INTO bill_question_mapping (
                congress, bill_number, question_id, relevance,
                position_if_yes, position_if_no, mapping_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            
            # Insert mappings
            count = 0
            for mapping in mappings:
                cursor.execute(sql, (
                    mapping.get("congress"),
                    mapping.get("bill_number"),
                    mapping.get("question_id"),
                    mapping.get("relevance"),
                    mapping.get("position_if_yes"),
                    mapping.get("position_if_no"),
                    mapping.get("mapping_date")
                ))
                count += 1
                
            self.conn.commit()
            logger.info(f"Saved {count} bill-question mappings")
            return count
        except Exception as e:
            logger.error(f"Error saving bill mappings to database: {e}")
            raise
            
    def infer_positions_from_votes(self, rep_id):
        """
        Infer representative positions from voting records
        
        Args:
            rep_id (int): Representative ID
            
        Returns:
            list: List of position dictionaries
        """
        try:
            cursor = self.conn.cursor()
            
            # Get voting records for representative
            cursor.execute("""
            SELECT vr.bill_number, vr.vote_position, vr.vote_date
            FROM voting_records vr
            WHERE vr.representative_id = ?
            ORDER BY vr.vote_date DESC
            """, (rep_id,))
            
            votes = cursor.fetchall()
            
            # Get bill-question mappings
            cursor.execute("""
            SELECT bqm.bill_number, bqm.question_id, bqm.relevance,
                   bqm.position_if_yes, bqm.position_if_no
            FROM bill_question_mapping bqm
            """)
            
            mappings = cursor.fetchall()
            
            # Create mapping dictionary for quick lookup
            mapping_dict = {}
            for bill_number, question_id, relevance, pos_yes, pos_no in mappings:
                if bill_number not in mapping_dict:
                    mapping_dict[bill_number] = []
                    
                mapping_dict[bill_number].append({
                    "question_id": question_id,
                    "relevance": relevance,
                    "position_if_yes": pos_yes,
                    "position_if_no": pos_no
                })
                
            # Infer positions
            positions = []
            position_scores = {}  # Dictionary to track scores by question
            
            for bill_number, vote_position, vote_date in votes:
                # Skip if no mapping for this bill
                if bill_number not in mapping_dict:
                    continue
                    
                # Process each question mapping for this bill
                for mapping in mapping_dict[bill_number]:
                    question_id = mapping["question_id"]
                    relevance = mapping["relevance"]
                    
                    # Determine score based on vote position
                    score = None
                    confidence = relevance  # Base confidence on relevance
                    
                    if vote_position == "Yes":
                        score = mapping["position_if_yes"]
                    elif vote_position == "No":
                        score = mapping["position_if_no"]
                    else:
                        # Skip non-yes/no votes
                        continue
                        
                    # Skip if no score determined
                    if score is None:
                        continue
                        
                    # Add to position scores, weighted by relevance
                    if question_id not in position_scores:
                        position_scores[question_id] = {
                            "scores": [],
                            "weights": [],
                            "dates": []
                        }
                        
                    position_scores[question_id]["scores"].append(score)
                    position_scores[question_id]["weights"].append(relevance)
                    position_scores[question_id]["dates"].append(vote_date)
                    
            # Calculate weighted average scores
            for question_id, data in position_scores.items():
                scores = data["scores"]
                weights = data["weights"]
                dates = data["dates"]
                
                if not scores:
                    continue
                    
                # Calculate weighted average
                weighted_sum = sum(s * w for s, w in zip(scores, weights))
                weight_sum = sum(weights)
                
                if weight_sum > 0:
                    avg_score = round(weighted_sum / weight_sum)
                    
                    # Calculate confidence based on number of votes and recency
                    vote_count_factor = min(len(scores) / 5, 1.0)  # Max out at 5 votes
                    
                    # Get most recent vote date
                    most_recent = max(dates) if dates else None
                    
                    # Create position
                    position = {
                        "representative_id": rep_id,
                        "question_id": question_id,
                        "score": avg_score,
                        "confidence": min(weight_sum * vote_count_factor, 1.0),
                        "source": "voting_records",
                        "last_updated": datetime.now().isoformat()
                    }
                    
                    positions.append(position)
                    
            logger.info(f"Inferred {len(positions)} positions for representative {rep_id}")
            return positions
        except Exception as e:
            logger.error(f"Error inferring positions from votes: {e}")
            return []
            
    def infer_positions_from_sponsorships(self, rep_id):
        """
        Infer representative positions from bill sponsorships
        
        Args:
            rep_id (int): Representative ID
            
        Returns:
            list: List of position dictionaries
        """
        try:
            cursor = self.conn.cursor()
            
            # Get bill sponsorships for representative
            cursor.execute("""
            SELECT bs.bill_number, bs.sponsorship_type, bs.introduced_date
            FROM bill_sponsorships bs
            WHERE bs.representative_id = ?
            ORDER BY bs.introduced_date DESC
            """, (rep_id,))
            
            sponsorships = cursor.fetchall()
            
            # Get bill-question mappings
            cursor.execute("""
            SELECT bqm.bill_number, bqm.question_id, bqm.relevance,
                   bqm.position_if_yes, bqm.position_if_no
            FROM bill_question_mapping bqm
            """)
            
            mappings = cursor.fetchall()
            
            # Create mapping dictionary for quick lookup
            mapping_dict = {}
            for bill_number, question_id, relevance, pos_yes, pos_no in mappings:
                if bill_number not in mapping_dict:
                    mapping_dict[bill_number] = []
                    
                mapping_dict[bill_number].append({
                    "question_id": question_id,
                    "relevance": relevance,
                    "position_if_yes": pos_yes,
                    "position_if_no": pos_no
                })
                
            # Infer positions
            positions = []
            position_scores = {}  # Dictionary to track scores by question
            
            for bill_number, sponsorship_type, introduced_date in sponsorships:
                # Skip if no mapping for this bill
                if bill_number not in mapping_dict:
                    continue
                    
                # Process each question mapping for this bill
                for mapping in mapping_dict[bill_number]:
                    question_id = mapping["question_id"]
                    relevance = mapping["relevance"]
                    
                    # Determine score based on sponsorship type
                    # Sponsors have stronger positions than cosponsors
                    score = mapping["position_if_yes"]  # Assume support for sponsored bills
                    
                    # Adjust confidence based on sponsorship type
                    confidence = relevance  # Base confidence on relevance
                    if sponsorship_type == "sponsor":
                        confidence *= 1.5  # Higher confidence for sponsors
                        score = int(score * 1.5)  # Stronger position for sponsors
                    else:
                        confidence *= 1.0  # Normal confidence for cosponsors
                        
                    # Ensure score is within range
                    score = max(-3, min(3, score))
                    
                    # Add to position scores, weighted by confidence
                    if question_id not in position_scores:
                        position_scores[question_id] = {
                            "scores": [],
                            "weights": [],
                            "dates": []
                        }
                        
                    position_scores[question_id]["scores"].append(score)
                    position_scores[question_id]["weights"].append(confidence)
                    position_scores[question_id]["dates"].append(introduced_date)
                    
            # Calculate weighted average scores
            for question_id, data in position_scores.items():
                scores = data["scores"]
                weights = data["weights"]
                dates = data["dates"]
                
                if not scores:
                    continue
                    
                # Calculate weighted average
                weighted_sum = sum(s * w for s, w in zip(scores, weights))
                weight_sum = sum(weights)
                
                if weight_sum > 0:
                    avg_score = round(weighted_sum / weight_sum)
                    
                    # Calculate confidence based on number of sponsorships and recency
                    count_factor = min(len(scores) / 3, 1.0)  # Max out at 3 sponsorships
                    
                    # Get most recent date
                    most_recent = max(dates) if dates else None
                    
                    # Create position
                    position = {
                        "representative_id": rep_id,
                        "question_id": question_id,
                        "score": avg_score,
                        "confidence": min(weight_sum * count_factor, 1.0),
                        "source": "bill_sponsorships",
                        "last_updated": datetime.now().isoformat()
                    }
                    
                    positions.append(position)
                    
            logger.info(f"Inferred {len(positions)} positions from sponsorships for representative {rep_id}")
            return positions
        except Exception as e:
            logger.error(f"Error inferring positions from sponsorships: {e}")
            return []
            
    def save_positions_to_db(self, positions):
        """
        Save representative positions to database
        
        Args:
            positions (list): List of position dictionaries
            
        Returns:
            int: Number of positions saved
        """
        try:
            cursor = self.conn.cursor()
            
            # Prepare SQL
            sql = """
            INSERT OR REPLACE INTO representative_positions (
                representative_id, question_id, score, confidence,
                source, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?)
            """
            
            # Insert positions
            count = 0
            for position in positions:
                cursor.execute(sql, (
                    position.get("representative_id"),
                    position.get("question_id"),
                    position.get("score"),
                    position.get("confidence"),
                    position.get("source"),
                    position.get("last_updated")
                ))
                count += 1
                
            self.conn.commit()
            logger.info(f"Saved {count} representative positions")
            return count
        except Exception as e:
            logger.error(f"Error saving positions to database: {e}")
            raise
            
    def close_connection(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
