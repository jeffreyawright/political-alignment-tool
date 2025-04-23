import os
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
    Scraper for collecting data from Congress.gov API and website
    
    This class handles fetching and processing data about representatives,
    their voting records, and bill information.
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
        
        if api_key:
            self.headers["X-API-Key"] = api_key
            
    def _create_db_connection(self):
        """Create a database connection to the SQLite database"""
        try:
            conn = sqlite3.connect(self.db_path)
            return conn
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise
            
    def close_connection(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
            
    def initialize_database(self, schema_file):
        """
        Initialize the database with schema
        
        Args:
            schema_file (str): Path to SQL schema file
        """
        try:
            cursor = self.conn.cursor()
            
            # Read schema file
            with open(schema_file, 'r') as f:
                schema_sql = f.read()
                
            # Execute schema SQL
            cursor.executescript(schema_sql)
            self.conn.commit()
            
            logger.info(f"Database initialized with schema from {schema_file}")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
            
    def fetch_current_members(self, chamber=None):
        """
        Fetch current members of Congress
        
        Args:
            chamber (str, optional): Chamber to filter by ('house' or 'senate')
            
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
                "congress": current_congress,
                "chamber": chamber,
                "format": "json",
                "limit": 250  # Maximum allowed by API
            }
            
            # Make API request
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            
            # Extract member data
            for member in data.get("members", []):
                member_data = {
                    "bioguide_id": member.get("bioguideId"),
                    "first_name": member.get("firstName"),
                    "last_name": member.get("lastName"),
                    "state": member.get("state"),
                    "district": member.get("district"),
                    "party": member.get("party"),
                    "chamber": chamber,
                    "congress_number": current_congress
                }
                
                members.append(member_data)
                
            return members
        except Exception as e:
            logger.error(f"Error fetching members from API: {e}")
            # Fall back to web scraping
            logger.info("Falling back to web scraping")
            return self._fetch_members_from_web(chamber)
            
    def _fetch_members_from_web(self, chamber):
        """
        Fetch members by scraping Congress.gov website
        
        Args:
            chamber (str): Chamber ('house' or 'senate')
            
        Returns:
            list: List of member dictionaries
        """
        members = []
        
        try:
            # Build URL
            url = f"{self.web_base_url}/{chamber}/members"
            
            # Make request
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract member data
            member_tables = soup.select("table.standard01")
            
            for table in member_tables:
                rows = table.select("tr")
                
                # Skip header row
                for row in rows[1:]:
                    cells = row.select("td")
                    
                    if len(cells) >= 5:
                        # Extract name and bioguide ID
                        name_cell = cells[0]
                        name_link = name_cell.select_one("a")
                        
                        if name_link:
                            profile_url = name_link.get("href", "")
                            bioguide_id = self._extract_bioguide_id(profile_url)
                            
                            # Extract name
                            full_name = name_link.text.strip()
                            name_parts = full_name.split(",")
                            
                            last_name = name_parts[0].strip() if len(name_parts) > 0 else ""
                            first_name = name_parts[1].strip() if len(name_parts) > 1 else ""
                            
                            # Extract state and district
                            state_district = cells[1].text.strip()
                            state = state_district[:2] if len(state_district) >= 2 else ""
                            
                            district = None
                            if chamber == "house" and len(state_district) > 2:
                                district_match = re.search(r'(\d+)', state_district[2:])
                                if district_match:
                                    district = district_match.group(1)
                            
                            # Extract party
                            party_text = cells[2].text.strip()
                            party = self._normalize_party(party_text)
                            
                            # Create member data
                            member_data = {
                                "bioguide_id": bioguide_id,
                                "first_name": first_name,
                                "last_name": last_name,
                                "state": state,
                                "district": district,
                                "party": party,
                                "chamber": chamber,
                                "congress_number": self._get_current_congress()
                            }
                            
                            members.append(member_data)
            
            return members
        except Exception as e:
            logger.error(f"Error fetching members from web: {e}")
            raise
            
    def _extract_bioguide_id(self, profile_url):
        """
        Extract bioguide ID from profile URL
        
        Args:
            profile_url (str): Profile URL
            
        Returns:
            str: Bioguide ID or None
        """
        if not profile_url:
            return None
            
        # Extract bioguide ID from URL
        match = re.search(r'/member/([A-Z]\d+)(?:/|$)', profile_url)
        if match:
            return match.group(1)
            
        return None
        
    def _normalize_party(self, party_text):
        """
        Normalize party abbreviation
        
        Args:
            party_text (str): Party text from website
            
        Returns:
            str: Normalized party abbreviation
        """
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
                "congress": current_congress,
                "format": "json",
                "limit": min(limit, 250)  # Maximum allowed by API
            }
            
            # Make API request
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            
            # Extract vote data
            for vote in data.get("votes", []):
                vote_data = {
                    "bioguide_id": bioguide_id,
                    "congress_number": vote.get("congress"),
                    "chamber": vote.get("chamber").lower(),
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
            # Fall back to web scraping
            logger.info("Falling back to web scraping")
            return self._fetch_votes_from_web(bioguide_id, limit)
            
    def _fetch_votes_from_web(self, bioguide_id, limit):
        """
        Fetch votes by scraping Congress.gov website
        
        Args:
            bioguide_id (str): Bioguide ID
            limit (int): Maximum number of votes to fetch
            
        Returns:
            list: List of vote dictionaries
        """
        votes = []
        
        try:
            # Build URL
            url = f"{self.web_base_url}/member/{bioguide_id}/votes"
            
            # Make request
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract vote data
            vote_tables = soup.select("table.item_table")
            
            for table in vote_tables:
                rows = table.select("tr")
                
                # Skip header row
                for row in rows[1:]:
                    if len(votes) >= limit:
                        break
                        
                    cells = row.select("td")
                    
                    if len(cells) >= 5:
                        # Extract date
                        date_text = cells[0].text.strip()
                        vote_date = self._parse_date(date_text)
                        
                        # Extract bill number
                        bill_cell = cells[1]
                        bill_link = bill_cell.select_one("a")
                        bill_number = bill_link.text.strip() if bill_link else None
                        
                        # Extract question
                        question = cells[2].text.strip()
                        
                        # Extract result
                        result = cells[3].text.strip()
                        
                        # Extract position
                        position = cells[4].text.strip()
                        
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
                amendment_number, question, result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    vote.get("amendment_number"),
                    vote.get("question"),
                    vote.get("result")
                ))
                count += 1
                
            self.conn.commit()
            logger.info(f"Saved {count} votes to database for representative {bioguide_id}")
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
            # Use API if key is available, otherwise scrape website
            if self.api_key:
                return self._fetch_bill_from_api(congress, bill_number)
            else:
                return self._fetch_bill_from_web(congress, bill_number)
        except Exception as e:
            logger.error(f"Error fetching bill details for {bill_number}: {e}")
            raise
            
    def _fetch_bill_from_api(self, congress, bill_number):
        """
        Fetch bill details from Congress.gov API
        
        Args:
            congress (int): Congress number
            bill_number (str): Bill number
            
        Returns:
            dict: Bill details
        """
        try:
            # Parse bill number to get type and number
            bill_type, number = self._parse_bill_number(bill_number)
            
            if not bill_type or not number:
                logger.warning(f"Invalid bill number format: {bill_number}")
                return {}
                
            # Build API URL
            url = f"{self.api_base_url}/bill/{congress}/{bill_type}/{number}"
            params = {
                "format": "json"
            }
            
            # Make API request
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            bill_data = data.get("bill", {})
            
            # Extract bill details
            bill_details = {
                "congress": congress,
                "bill_number": bill_number,
                "title": bill_data.get("title"),
                "summary": bill_data.get("summary", {}).get("text"),
                "sponsor": bill_data.get("sponsors", [{}])[0].get("fullName") if bill_data.get("sponsors") else None,
                "introduced_date": bill_data.get("introducedDate"),
                "latest_action_date": bill_data.get("latestAction", {}).get("actionDate"),
                "latest_action_text": bill_data.get("latestAction", {}).get("text"),
                "policy_area": bill_data.get("policyArea", {}).get("name"),
                "subjects": [s.get("name") for s in bill_data.get("subjects", [])]
            }
            
            return bill_details
        except Exception as e:
            logger.error(f"Error fetching bill from API: {e}")
            # Fall back to web scraping
            logger.info("Falling back to web scraping")
            return self._fetch_bill_from_web(congress, bill_number)
            
    def _fetch_bill_from_web(self, congress, bill_number):
        """
        Fetch bill details by scraping Congress.gov website
        
        Args:
            congress (int): Congress number
            bill_number (str): Bill number
            
        Returns:
            dict: Bill details
        """
        try:
            # Parse bill number to get type and number
            bill_type, number = self._parse_bill_number(bill_number)
            
            if not bill_type or not number:
                logger.warning(f"Invalid bill number format: {bill_number}")
                return {}
                
            # Build URL
            url = f"{self.web_base_url}/bill/{congress}th-congress/{bill_type}{number}"
            
            # Make request
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract bill details
            title_elem = soup.select_one("h1.legDetail")
            title = title_elem.text.strip() if title_elem else None
            
            summary_elem = soup.select_one("div.bill-summary")
            summary = summary_elem.text.strip() if summary_elem else None
            
            sponsor_elem = soup.select_one("table.standard01 a[href*='/member/']")
            sponsor = sponsor_elem.text.strip() if sponsor_elem else None
            
            # Extract dates
            introduced_date = None
            latest_action_date = None
            latest_action_text = None
            
            date_tables = soup.select("table.standard01")
            for table in date_tables:
                rows = table.select("tr")
                for row in rows:
                    cells = row.select("td")
                    if len(cells) >= 2:
                        label = cells[0].text.strip()
                        value = cells[1].text.strip()
                        
                        if "introduced" in label.lower():
                            introduced_date = self._parse_date(value)
                        elif "latest action" in label.lower():
                            latest_action_parts = value.split(" - ")
                            if len(latest_action_parts) >= 2:
                                latest_action_date = self._parse_date(latest_action_parts[0])
                                latest_action_text = latest_action_parts[1].strip()
            
            # Extract policy area and subjects
            policy_area = None
            subjects = []
            
            subject_divs = soup.select("div.bill-subjects div.plain")
            for div in subject_divs:
                text = div.text.strip()
                if "Policy Area:" in text:
                    policy_area = text.replace("Policy Area:", "").strip()
                elif "Legislative Subject:" in text:
                    subjects = [s.strip() for s in text.replace("Legislative Subject:", "").split(",")]
            
            # Create bill details
            bill_details = {
                "congress": congress,
                "bill_number": bill_number,
                "title": title,
                "summary": summary,
                "sponsor": sponsor,
                "introduced_date": introduced_date,
                "latest_action_date": latest_action_date,
                "latest_action_text": latest_action_text,
                "policy_area": policy_area,
                "subjects": subjects
            }
            
            return bill_details
        except Exception as e:
            logger.error(f"Error fetching bill from web: {e}")
            raise
            
    def _parse_bill_number(self, bill_number):
        """
        Parse bill number to get type and number
        
        Args:
            bill_number (str): Bill number (e.g., "H.R.1234")
            
        Returns:
            tuple: (bill_type, number)
        """
        if not bill_number:
            return None, None
            
        # Remove spaces
        bill_number = bill_number.replace(" ", "")
        
        # Match common bill types
        match = re.match(r'([A-Za-z\.]+)(\d+)', bill_number)
        if match:
            bill_type = match.group(1).lower()
            number = match.group(2)
            
            # Normalize bill type
            if bill_type in ["hr", "h.r.", "h.r"]:
                bill_type = "hr"
            elif bill_type in ["s", "s."]:
                bill_type = "s"
            elif bill_type in ["hjres", "h.j.res.", "h.j.res"]:
                bill_type = "hjres"
            elif bill_type in ["sjres", "s.j.res.", "s.j.res"]:
                bill_type = "sjres"
                
            return bill_type, number
            
        return None, None
        
    def infer_positions_from_votes(self, representative_id):
        """
        Infer policy positions from voting records
        
        Args:
            representative_id (int): Representative ID
            
        Returns:
            list: List of position dictionaries
        """
        try:
            cursor = self.conn.cursor()
            
            # Get voting records
            cursor.execute("""
            SELECT vr.bill_number, vr.vote_position, vr.question, vr.result,
                   bqm.question_id, bqm.relevance, bqm.position_if_yes, bqm.position_if_no
            FROM voting_records vr
            JOIN bill_question_mapping bqm ON vr.bill_number = bqm.bill_number
            WHERE vr.representative_id = ?
            """, (representative_id,))
            
            votes = cursor.fetchall()
            
            # Group votes by question
            question_votes = {}
            for vote in votes:
                bill_number, vote_position, question, result, question_id, relevance, pos_if_yes, pos_if_no = vote
                
                if not question_id:
                    continue
                    
                if question_id not in question_votes:
                    question_votes[question_id] = []
                    
                question_votes[question_id].append({
                    "bill_number": bill_number,
                    "vote_position": vote_position,
                    "question": question,
                    "result": result,
                    "relevance": relevance,
                    "position_if_yes": pos_if_yes,
                    "position_if_no": pos_if_no
                })
            
            # Infer positions
            positions = []
            for question_id, votes in question_votes.items():
                # Calculate weighted average position
                total_score = 0
                total_weight = 0
                
                for vote in votes:
                    # Determine position based on vote
                    position = None
                    if vote["vote_position"].lower() in ["yea", "yes", "aye"]:
                        position = vote["position_if_yes"]
                    elif vote["vote_position"].lower() in ["nay", "no"]:
                        position = vote["position_if_no"]
                        
                    if position is not None:
                        weight = vote["relevance"] if vote["relevance"] else 1
                        total_score += position * weight
                        total_weight += weight
                
                if total_weight > 0:
                    avg_position = total_score / total_weight
                    confidence = min(1.0, 0.5 + (total_weight / 10))  # Higher weight = higher confidence
                    
                    positions.append({
                        "representative_id": representative_id,
                        "question_id": question_id,
                        "score": avg_position,
                        "confidence": confidence,
                        "source": "voting_record",
                        "last_updated": datetime.now().isoformat()
                    })
            
            return positions
        except Exception as e:
            logger.error(f"Error inferring positions from votes: {e}")
            raise
            
    def save_positions_to_db(self, positions):
        """
        Save inferred positions to database
        
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
            logger.info(f"Saved {count} positions to database")
            return count
        except Exception as e:
            logger.error(f"Error saving positions to database: {e}")
            raise
            
    def map_bill_to_questions(self, congress, bill_number, bill_details, questions):
        """
        Map a bill to relevant questions
        
        Args:
            congress (int): Congress number
            bill_number (str): Bill number
            bill_details (dict): Bill details
            questions (list): List of question dictionaries
            
        Returns:
            list: List of mapping dictionaries
        """
        try:
            mappings = []
            
            # Extract keywords from bill
            bill_keywords = self._extract_bill_keywords(bill_details)
            
            # For each question, calculate relevance
            for question in questions:
                question_id = question.get("id")
                question_text = question.get("question_text")
                policy_area = question.get("policy_area_name")
                
                # Skip if no question text
                if not question_text:
                    continue
                    
                # Calculate relevance based on keyword matching
                relevance = self._calculate_relevance(bill_keywords, question_text, policy_area)
                
                # Skip if not relevant
                if relevance <= 0:
                    continue
                    
                # Determine positions if voting yes/no
                position_if_yes, position_if_no = self._determine_positions(bill_details, question_text, policy_area)
                
                # Create mapping
                mapping = {
                    "congress": congress,
                    "bill_number": bill_number,
                    "question_id": question_id,
                    "relevance": relevance,
                    "position_if_yes": position_if_yes,
                    "position_if_no": position_if_no,
                    "mapping_date": datetime.now().isoformat()
                }
                
                mappings.append(mapping)
            
            return mappings
        except Exception as e:
            logger.error(f"Error mapping bill to questions: {e}")
            raise
            
    def _extract_bill_keywords(self, bill_details):
        """
        Extract keywords from bill details
        
        Args:
            bill_details (dict): Bill details
            
        Returns:
            dict: Dictionary of keywords
        """
        keywords = {
            "title": [],
            "summary": [],
            "policy_area": [],
            "subjects": []
        }
        
        # Extract from title
        if bill_details.get("title"):
            keywords["title"] = self._extract_keywords_from_text(bill_details["title"])
            
        # Extract from summary
        if bill_details.get("summary"):
            keywords["summary"] = self._extract_keywords_from_text(bill_details["summary"])
            
        # Extract from policy area
        if bill_details.get("policy_area"):
            keywords["policy_area"] = self._extract_keywords_from_text(bill_details["policy_area"])
            
        # Extract from subjects
        if bill_details.get("subjects"):
            for subject in bill_details["subjects"]:
                keywords["subjects"].extend(self._extract_keywords_from_text(subject))
                
        return keywords
        
    def _extract_keywords_from_text(self, text):
        """
        Extract keywords from text
        
        Args:
            text (str): Text to extract keywords from
            
        Returns:
            list: List of keywords
        """
        if not text:
            return []
            
        # Convert to lowercase
        text = text.lower()
        
        # Remove punctuation
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Split into words
        words = text.split()
        
        # Remove stop words
        stop_words = [
            "the", "and", "a", "an", "in", "on", "at", "to", "for", "of", "by",
            "with", "about", "as", "from", "be", "is", "are", "was", "were",
            "will", "would", "should", "can", "could", "may", "might", "must",
            "shall", "have", "has", "had", "do", "does", "did", "this", "that",
            "these", "those", "it", "its", "they", "them", "their", "there"
        ]
        
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        return keywords
        
    def _calculate_relevance(self, bill_keywords, question_text, policy_area):
        """
        Calculate relevance of bill to question
        
        Args:
            bill_keywords (dict): Bill keywords
            question_text (str): Question text
            policy_area (str): Policy area
            
        Returns:
            float: Relevance score (0-1)
        """
        # Extract question keywords
        question_keywords = self._extract_keywords_from_text(question_text)
        policy_keywords = self._extract_keywords_from_text(policy_area)
        
        # Calculate matches
        title_matches = self._count_matches(bill_keywords["title"], question_keywords)
        summary_matches = self._count_matches(bill_keywords["summary"], question_keywords)
        policy_matches = self._count_matches(bill_keywords["policy_area"], policy_keywords)
        subject_matches = self._count_matches(bill_keywords["subjects"], question_keywords)
        
        # Calculate relevance score
        relevance = 0
        
        # Title matches are most important
        if title_matches > 0:
            relevance += 0.4 * min(1.0, title_matches / len(question_keywords) if question_keywords else 0)
            
        # Summary matches
        if summary_matches > 0:
            relevance += 0.3 * min(1.0, summary_matches / len(question_keywords) if question_keywords else 0)
            
        # Policy area matches
        if policy_matches > 0:
            relevance += 0.2 * min(1.0, policy_matches / len(policy_keywords) if policy_keywords else 0)
            
        # Subject matches
        if subject_matches > 0:
            relevance += 0.1 * min(1.0, subject_matches / len(question_keywords) if question_keywords else 0)
            
        return relevance
        
    def _count_matches(self, keywords1, keywords2):
        """
        Count matches between two keyword lists
        
        Args:
            keywords1 (list): First list of keywords
            keywords2 (list): Second list of keywords
            
        Returns:
            int: Number of matches
        """
        if not keywords1 or not keywords2:
            return 0
            
        # Count exact matches
        exact_matches = len(set(keywords1) & set(keywords2))
        
        # Count partial matches
        partial_matches = 0
        for k1 in keywords1:
            for k2 in keywords2:
                if k1 in k2 or k2 in k1:
                    partial_matches += 1
                    
        return exact_matches + (partial_matches * 0.5)
        
    def _determine_positions(self, bill_details, question_text, policy_area):
        """
        Determine positions if voting yes/no on bill
        
        Args:
            bill_details (dict): Bill details
            question_text (str): Question text
            policy_area (str): Policy area
            
        Returns:
            tuple: (position_if_yes, position_if_no)
        """
        # Default neutral positions
        position_if_yes = 0
        position_if_no = 0
        
        # Extract keywords
        title_keywords = self._extract_keywords_from_text(bill_details.get("title", ""))
        summary_keywords = self._extract_keywords_from_text(bill_details.get("summary", ""))
        question_keywords = self._extract_keywords_from_text(question_text)
        
        # Check for keywords indicating position
        positive_keywords = ["support", "promote", "establish", "increase", "expand", "protect", "strengthen"]
        negative_keywords = ["restrict", "limit", "reduce", "repeal", "prohibit", "ban", "prevent"]
        
        # Count positive and negative keywords in title and summary
        positive_count = 0
        negative_count = 0
        
        for keyword in positive_keywords:
            if keyword in title_keywords:
                positive_count += 2
            if keyword in summary_keywords:
                positive_count += 1
                
        for keyword in negative_keywords:
            if keyword in title_keywords:
                negative_count += 2
            if keyword in summary_keywords:
                negative_count += 1
                
        # Determine positions based on keyword counts
        if positive_count > negative_count:
            # Bill is generally positive/supportive
            position_if_yes = -2  # Favor
            position_if_no = 2    # Oppose
        elif negative_count > positive_count:
            # Bill is generally negative/restrictive
            position_if_yes = 2   # Oppose
            position_if_no = -2   # Favor
        else:
            # Neutral or unclear
            position_if_yes = -1  # Slight favor
            position_if_no = 1    # Slight oppose
            
        return position_if_yes, position_if_no
        
    def save_bill_mappings_to_db(self, mappings):
        """
        Save bill-question mappings to database
        
        Args:
            mappings (list): List of mapping dictionaries
            
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
            logger.info(f"Saved {count} bill-question mappings to database")
            return count
        except Exception as e:
            logger.error(f"Error saving bill mappings to database: {e}")
            raise

# Example usage
if __name__ == "__main__":
    # Create scraper
    scraper = CongressDataScraper(db_path="political_alignment.db")
    
    # Fetch current members
    members = scraper.fetch_current_members(chamber="senate")
    
    # Save members to database
    scraper.save_members_to_db(members)
    
    # Fetch votes for a member
    votes = scraper.fetch_member_votes(members[0]["bioguide_id"], limit=10)
    
    # Save votes to database
    scraper.save_votes_to_db(members[0]["bioguide_id"], votes)
    
    # Close connection
    scraper.close_connection()
