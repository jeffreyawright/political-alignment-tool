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
from sklearn.preprocessing import MinMaxScaler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("advocacy_ratings_collector.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("advocacy_ratings_collector")

class AdvocacyRatingsCollector:
    """
    Collector for advocacy group ratings of lawmakers
    
    This class handles fetching and processing ratings from various
    advocacy organizations across the political spectrum.
    """
    
    def __init__(self, db_path):
        """
        Initialize the collector with database path
        
        Args:
            db_path (str): Path to SQLite database
        """
        self.db_path = db_path
        self.conn = self._create_db_connection()
        
        # Define headers for web requests
        self.headers = {
            "User-Agent": "Political Alignment Tool/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }
        
        # Initialize database tables
        self._initialize_database_tables()
        
        # Define advocacy groups by policy area
        self.advocacy_groups = {
            "Gun Control": [
                {
                    "name": "NRA",
                    "full_name": "National Rifle Association",
                    "url": "https://www.nrapvf.org/grades/",
                    "position": "conservative",
                    "rating_type": "letter",
                    "rating_scale": {"A+": 3, "A": 3, "A-": 2, "B+": 2, "B": 1, "B-": 1, "C+": 0, "C": 0, "C-": -1, "D+": -1, "D": -2, "D-": -2, "F": -3}
                },
                {
                    "name": "Brady Campaign",
                    "full_name": "Brady Campaign to Prevent Gun Violence",
                    "url": "https://www.bradyunited.org/",
                    "position": "liberal",
                    "rating_type": "percentage",
                    "rating_scale": "inverse"  # Higher percentage = more conservative
                },
                {
                    "name": "Giffords",
                    "full_name": "Giffords Law Center to Prevent Gun Violence",
                    "url": "https://giffords.org/",
                    "position": "liberal",
                    "rating_type": "letter",
                    "rating_scale": {"A": -3, "B": -2, "C": -1, "D": 1, "F": 3}
                }
            ],
            "Immigration": [
                {
                    "name": "NumbersUSA",
                    "full_name": "NumbersUSA",
                    "url": "https://www.numbersusa.com/",
                    "position": "conservative",
                    "rating_type": "letter",
                    "rating_scale": {"A+": 3, "A": 3, "A-": 2, "B+": 2, "B": 1, "B-": 1, "C+": 0, "C": 0, "C-": -1, "D+": -1, "D": -2, "D-": -2, "F": -3}
                },
                {
                    "name": "ACLU",
                    "full_name": "American Civil Liberties Union",
                    "url": "https://www.aclu.org/",
                    "position": "liberal",
                    "rating_type": "percentage",
                    "rating_scale": "direct"  # Higher percentage = more liberal
                }
            ],
            "Environment": [
                {
                    "name": "LCV",
                    "full_name": "League of Conservation Voters",
                    "url": "https://www.lcv.org/",
                    "position": "liberal",
                    "rating_type": "percentage",
                    "rating_scale": "direct"  # Higher percentage = more liberal
                },
                {
                    "name": "Sierra Club",
                    "full_name": "Sierra Club",
                    "url": "https://www.sierraclub.org/",
                    "position": "liberal",
                    "rating_type": "endorsement",
                    "rating_scale": {"endorsed": -3, "not_endorsed": 0}
                }
            ],
            "Economy": [
                {
                    "name": "AFP",
                    "full_name": "Americans for Prosperity",
                    "url": "https://americansforprosperity.org/",
                    "position": "conservative",
                    "rating_type": "percentage",
                    "rating_scale": "direct"  # Higher percentage = more conservative
                },
                {
                    "name": "ATR",
                    "full_name": "Americans for Tax Reform",
                    "url": "https://www.atr.org/",
                    "position": "conservative",
                    "rating_type": "pledge",
                    "rating_scale": {"signed": 3, "not_signed": 0}
                }
            ],
            "Civil Rights": [
                {
                    "name": "ACLU",
                    "full_name": "American Civil Liberties Union",
                    "url": "https://www.aclu.org/",
                    "position": "liberal",
                    "rating_type": "percentage",
                    "rating_scale": "direct"  # Higher percentage = more liberal
                },
                {
                    "name": "HRC",
                    "full_name": "Human Rights Campaign",
                    "url": "https://www.hrc.org/",
                    "position": "liberal",
                    "rating_type": "percentage",
                    "rating_scale": "direct"  # Higher percentage = more liberal
                },
                {
                    "name": "NAACP",
                    "full_name": "National Association for the Advancement of Colored People",
                    "url": "https://www.naacp.org/",
                    "position": "liberal",
                    "rating_type": "percentage",
                    "rating_scale": "direct"  # Higher percentage = more liberal
                }
            ],
            "Abortion": [
                {
                    "name": "NARAL",
                    "full_name": "NARAL Pro-Choice America",
                    "url": "https://www.prochoiceamerica.org/",
                    "position": "liberal",
                    "rating_type": "percentage",
                    "rating_scale": "direct"  # Higher percentage = more liberal
                },
                {
                    "name": "SBA List",
                    "full_name": "Susan B. Anthony List",
                    "url": "https://www.sba-list.org/",
                    "position": "conservative",
                    "rating_type": "endorsement",
                    "rating_scale": {"endorsed": 3, "not_endorsed": 0}
                }
            ]
        }
        
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
            
    def _initialize_database_tables(self):
        """Initialize database tables for advocacy ratings"""
        try:
            cursor = self.conn.cursor()
            
            # Create advocacy_groups table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS advocacy_groups (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                full_name TEXT,
                url TEXT,
                position TEXT,
                policy_area TEXT,
                rating_type TEXT
            )
            """)
            
            # Create advocacy_ratings table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS advocacy_ratings (
                id INTEGER PRIMARY KEY,
                representative_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                rating TEXT,
                normalized_score INTEGER,
                year INTEGER,
                source_url TEXT,
                FOREIGN KEY (representative_id) REFERENCES representatives (id),
                FOREIGN KEY (group_id) REFERENCES advocacy_groups (id)
            )
            """)
            
            # Create advocacy_positions table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS advocacy_positions (
                id INTEGER PRIMARY KEY,
                representative_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                score INTEGER,
                confidence REAL,
                source TEXT,
                last_updated TEXT,
                FOREIGN KEY (representative_id) REFERENCES representatives (id),
                FOREIGN KEY (question_id) REFERENCES questions (id)
            )
            """)
            
            self.conn.commit()
            logger.info("Database tables initialized")
            
            # Populate advocacy_groups table if empty
            cursor.execute("SELECT COUNT(*) FROM advocacy_groups")
            count = cursor.fetchone()[0]
            
            if count == 0:
                self._populate_advocacy_groups()
                
        except Exception as e:
            logger.error(f"Error initializing database tables: {e}")
            raise
            
    def _populate_advocacy_groups(self):
        """Populate advocacy_groups table with predefined groups"""
        try:
            cursor = self.conn.cursor()
            
            # Prepare SQL
            sql = """
            INSERT INTO advocacy_groups (
                name, full_name, url, position, policy_area, rating_type
            ) VALUES (?, ?, ?, ?, ?, ?)
            """
            
            # Insert groups
            count = 0
            for policy_area, groups in self.advocacy_groups.items():
                for group in groups:
                    cursor.execute(sql, (
                        group.get("name"),
                        group.get("full_name"),
                        group.get("url"),
                        group.get("position"),
                        policy_area,
                        group.get("rating_type")
                    ))
                    count += 1
                    
            self.conn.commit()
            logger.info(f"Populated {count} advocacy groups")
        except Exception as e:
            logger.error(f"Error populating advocacy groups: {e}")
            raise
            
    def collect_ratings(self, bioguide_id):
        """
        Collect ratings for a representative from all advocacy groups
        
        Args:
            bioguide_id (str): Bioguide ID
            
        Returns:
            list: List of rating dictionaries
        """
        try:
            # Get representative ID and info
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT id, first_name, last_name, state, chamber, party
                FROM representatives
                WHERE bioguide_id = ?
                """,
                (bioguide_id,)
            )
            
            rep_row = cursor.fetchone()
            if not rep_row:
                logger.warning(f"Representative not found for bioguide_id {bioguide_id}")
                return []
                
            rep_id, first_name, last_name, state, chamber, party = rep_row
            
            # Get advocacy groups
            cursor.execute("SELECT id, name, policy_area, position, rating_type FROM advocacy_groups")
            groups = cursor.fetchall()
            
            # Collect ratings for each group
            ratings = []
            
            for group_id, group_name, policy_area, position, rating_type in groups:
                logger.info(f"Collecting {group_name} ratings for {first_name} {last_name}")
                
                # Get group details
                group_details = None
                for area_groups in self.advocacy_groups.values():
                    for group in area_groups:
                        if group["name"] == group_name:
                            group_details = group
                            break
                    if group_details:
                        break
                        
                if not group_details:
                    logger.warning(f"Group details not found for {group_name}")
                    continue
                    
                # Collect rating based on group
                rating_data = self._collect_group_rating(
                    group_details, 
                    first_name, 
                    last_name, 
                    state, 
                    chamber,
                    party
                )
                
                if rating_data:
                    # Add representative and group IDs
                    rating_data["representative_id"] = rep_id
                    rating_data["group_id"] = group_id
                    
                    # Normalize rating to -3 to 3 scale
                    normalized_score = self._normalize_rating(
                        rating_data["rating"],
                        group_details
                    )
                    
                    rating_data["normalized_score"] = normalized_score
                    
                    ratings.append(rating_data)
                    
            logger.info(f"Collected {len(ratings)} ratings for representative {bioguide_id}")
            return ratings
        except Exception as e:
            logger.error(f"Error collecting ratings for representative {bioguide_id}: {e}")
            return []
            
    def _collect_group_rating(self, group, first_name, last_name, state, chamber, party):
        """
        Collect rating from a specific advocacy group
        
        Args:
            group (dict): Group details
            first_name (str): Representative first name
            last_name (str): Representative last name
            state (str): Representative state
            chamber (str): Representative chamber
            party (str): Representative party
            
        Returns:
            dict: Rating data or None
        """
        try:
            # Different collection methods based on group
            if group["name"] == "NRA":
                return self._collect_nra_rating(group, last_name, state, chamber)
            elif group["name"] == "LCV":
                return self._collect_lcv_rating(group, last_name, state, chamber)
            elif group["name"] == "ACLU":
                return self._collect_aclu_rating(group, last_name, state, chamber)
            elif group["name"] == "HRC":
                return self._collect_hrc_rating(group, last_name, state, chamber)
            elif group["name"] == "NARAL":
                return self._collect_naral_rating(group, last_name, state, chamber)
            else:
                # For groups without specific collectors, use party as a proxy
                # This is a fallback method when direct data isn't available
                return self._estimate_rating_from_party(group, party)
                
        except Exception as e:
            logger.error(f"Error collecting {group['name']} rating: {e}")
            return None
            
    def _collect_nra_rating(self, group, last_name, state, chamber):
        """
        Collect NRA rating
        
        Args:
            group (dict): Group details
            last_name (str): Representative last name
            state (str): Representative state
            chamber (str): Representative chamber
            
        Returns:
            dict: Rating data or None
        """
        try:
            # NRA ratings are typically available on their PVF website
            # This is a simplified implementation
            
            # In a real implementation, this would scrape the NRA-PVF website
            # For this example, we'll use a simulated approach
            
            # Simulate web request with delay
            time.sleep(random.uniform(1, 3))
            
            # For demonstration purposes, generate a simulated rating
            # In a real implementation, this would parse actual data
            ratings = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]
            weights = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.1]
            
            # Adjust weights based on chamber (senators tend to have more polarized ratings)
            if chamber.lower() == "senate":
                weights = [0.15, 0.15, 0.1, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.15]
                
            rating = random.choices(ratings, weights=weights)[0]
            
            return {
                "rating": rating,
                "year": datetime.now().year - 1,  # Previous year
                "source_url": f"https://www.nrapvf.org/grades/{state.lower()}"
            }
        except Exception as e:
            logger.error(f"Error collecting NRA rating: {e}")
            return None
            
    def _collect_lcv_rating(self, group, last_name, state, chamber):
        """
        Collect League of Conservation Voters rating
        
        Args:
            group (dict): Group details
            last_name (str): Representative last name
            state (str): Representative state
            chamber (str): Representative chamber
            
        Returns:
            dict: Rating data or None
        """
        try:
            # LCV ratings are typically available on their scorecard
            # This is a simplified implementation
            
            # In a real implementation, this would scrape the LCV website
            # For this example, we'll use a simulated approach
            
            # Simulate web request with delay
            time.sleep(random.uniform(1, 3))
            
            # For demonstration purposes, generate a simulated rating
            # In a real implementation, this would parse actual data
            rating = random.randint(0, 100)
            
            return {
                "rating": str(rating),
                "year": datetime.now().year - 1,  # Previous year
                "source_url": "https://www.lcv.org/scorecard/"
            }
        except Exception as e:
            logger.error(f"Error collecting LCV rating: {e}")
            return None
            
    def _collect_aclu_rating(self, group, last_name, state, chamber):
        """
        Collect ACLU rating
        
        Args:
            group (dict): Group details
            last_name (str): Representative last name
            state (str): Representative state
            chamber (str): Representative chamber
            
        Returns:
            dict: Rating data or None
        """
        try:
            # ACLU ratings are typically available on their legislative scorecard
            # This is a simplified implementation
            
            # In a real implementation, this would scrape the ACLU website
            # For this example, we'll use a simulated approach
            
            # Simulate web request with delay
            time.sleep(random.uniform(1, 3))
            
            # For demonstration purposes, generate a simulated rating
            # In a real implementation, this would parse actual data
            rating = random.randint(0, 100)
            
            return {
                "rating": str(rating),
                "year": datetime.now().year - 1,  # Previous year
                "source_url": "https://www.aclu.org/scorecard/"
            }
        except Exception as e:
            logger.error(f"Error collecting ACLU rating: {e}")
            return None
            
    def _collect_hrc_rating(self, group, last_name, state, chamber):
        """
        Collect Human Rights Campaign rating
        
        Args:
            group (dict): Group details
            last_name (str): Representative last name
            state (str): Representative state
            chamber (str): Representative chamber
            
        Returns:
            dict: Rating data or None
        """
        try:
            # HRC ratings are typically available on their congressional scorecard
            # This is a simplified implementation
            
            # In a real implementation, this would scrape the HRC website
            # For this example, we'll use a simulated approach
            
            # Simulate web request with delay
            time.sleep(random.uniform(1, 3))
            
            # For demonstration purposes, generate a simulated rating
            # In a real implementation, this would parse actual data
            rating = random.randint(0, 100)
            
            return {
                "rating": str(rating),
                "year": datetime.now().year - 1,  # Previous year
                "source_url": "https://www.hrc.org/resources/congressional-scorecard"
            }
        except Exception as e:
            logger.error(f"Error collecting HRC rating: {e}")
            return None
            
    def _collect_naral_rating(self, group, last_name, state, chamber):
        """
        Collect NARAL rating
        
        Args:
            group (dict): Group details
            last_name (str): Representative last name
            state (str): Representative state
            chamber (str): Representative chamber
            
        Returns:
            dict: Rating data or None
        """
        try:
            # NARAL ratings are typically available on their congressional record
            # This is a simplified implementation
            
            # In a real implementation, this would scrape the NARAL website
            # For this example, we'll use a simulated approach
            
            # Simulate web request with delay
            time.sleep(random.uniform(1, 3))
            
            # For demonstration purposes, generate a simulated rating
            # In a real implementation, this would parse actual data
            rating = random.randint(0, 100)
            
            return {
                "rating": str(rating),
                "year": datetime.now().year - 1,  # Previous year
                "source_url": "https://www.prochoiceamerica.org/laws-policy/congressional-record/"
            }
        except Exception as e:
            logger.error(f"Error collecting NARAL rating: {e}")
            return None
            
    def _estimate_rating_from_party(self, group, party):
        """
        Estimate rating based on party affiliation
        
        This is a fallback method when direct data isn't available
        
        Args:
            group (dict): Group details
            party (str): Representative party
            
        Returns:
            dict: Rating data or None
        """
        try:
            # This is a simplified approach for demonstration
            # In a real implementation, this would be more sophisticated
            
            # Skip if no party info
            if not party:
                return None
                
            # Determine if party alignment matches group position
            party_alignment = "conservative" if party == "R" else "liberal" if party == "D" else "moderate"
            group_position = group.get("position")
            
            # Generate rating based on alignment
            rating = None
            
            if group.get("rating_type") == "letter":
                # Letter ratings
                if party_alignment == group_position:
                    # Aligned - higher rating
                    rating = random.choice(["A+", "A", "A-", "B+"])
                elif party_alignment == "moderate":
                    # Moderate - middle rating
                    rating = random.choice(["B", "B-", "C+", "C"])
                else:
                    # Opposed - lower rating
                    rating = random.choice(["C-", "D+", "D", "D-", "F"])
            elif group.get("rating_type") == "percentage":
                # Percentage ratings
                if party_alignment == group_position:
                    # Aligned - higher percentage
                    rating = str(random.randint(70, 100))
                elif party_alignment == "moderate":
                    # Moderate - middle percentage
                    rating = str(random.randint(40, 70))
                else:
                    # Opposed - lower percentage
                    rating = str(random.randint(0, 40))
            elif group.get("rating_type") == "endorsement":
                # Endorsement
                if party_alignment == group_position:
                    # Aligned - likely endorsed
                    rating = "endorsed" if random.random() > 0.3 else "not_endorsed"
                else:
                    # Not aligned - likely not endorsed
                    rating = "not_endorsed"
            elif group.get("rating_type") == "pledge":
                # Pledge
                if party_alignment == group_position:
                    # Aligned - likely signed
                    rating = "signed" if random.random() > 0.3 else "not_signed"
                else:
                    # Not aligned - likely not signed
                    rating = "not_signed"
                    
            if rating:
                return {
                    "rating": rating,
                    "year": datetime.now().year - 1,  # Previous year
                    "source_url": "estimated"
                }
                
            return None
        except Exception as e:
            logger.error(f"Error estimating rating from party: {e}")
            return None
            
    def _normalize_rating(self, rating, group):
        """
        Normalize rating to -3 to 3 scale
        
        Args:
            rating (str): Rating value
            group (dict): Group details
            
        Returns:
            int: Normalized score (-3 to 3)
        """
        try:
            rating_type = group.get("rating_type")
            rating_scale = group.get("rating_scale")
            
            if rating_type == "letter":
                # Direct mapping from letter to score
                return rating_scale.get(rating, 0)
            elif rating_type == "percentage":
                # Convert percentage to -3 to 3 scale
                try:
                    percentage = int(rating)
                    
                    # Scale based on direction
                    if rating_scale == "direct":
                        # Higher percentage = more liberal
                        return round((percentage - 50) * 6 / 100)
                    elif rating_scale == "inverse":
                        # Higher percentage = more conservative
                        return round((50 - percentage) * 6 / 100)
                except:
                    return 0
            elif rating_type == "endorsement" or rating_type == "pledge":
                # Direct mapping
                return rating_scale.get(rating, 0)
                
            return 0
        except Exception as e:
            logger.error(f"Error normalizing rating: {e}")
            return 0
            
    def save_ratings_to_db(self, ratings):
        """
        Save ratings to database
        
        Args:
            ratings (list): List of rating dictionaries
            
        Returns:
            int: Number of ratings saved
        """
        try:
            cursor = self.conn.cursor()
            
            # Prepare SQL
            sql = """
            INSERT OR REPLACE INTO advocacy_ratings (
                representative_id, group_id, rating, normalized_score,
                year, source_url
            ) VALUES (?, ?, ?, ?, ?, ?)
            """
            
            # Insert ratings
            count = 0
            for rating in ratings:
                cursor.execute(sql, (
                    rating.get("representative_id"),
                    rating.get("group_id"),
                    rating.get("rating"),
                    rating.get("normalized_score"),
                    rating.get("year"),
                    rating.get("source_url")
                ))
                count += 1
                
            self.conn.commit()
            logger.info(f"Saved {count} ratings to database")
            return count
        except Exception as e:
            logger.error(f"Error saving ratings to database: {e}")
            raise
            
    def map_ratings_to_questions(self):
        """
        Map advocacy group ratings to survey questions
        
        Returns:
            dict: Mapping dictionary
        """
        try:
            cursor = self.conn.cursor()
            
            # Get questions
            cursor.execute("""
            SELECT q.id, q.question_text, pa.name as policy_area
            FROM questions q
            JOIN policy_areas pa ON q.policy_area_id = pa.id
            WHERE q.active = 1
            """)
            
            questions = cursor.fetchall()
            
            # Get advocacy groups
            cursor.execute("""
            SELECT id, name, policy_area, position
            FROM advocacy_groups
            """)
            
            groups = cursor.fetchall()
            
            # Create mapping
            mapping = {}
            
            for question_id, question_text, question_area in questions:
                mapping[question_id] = []
                
                # Find relevant groups for this question's policy area
                for group_id, group_name, group_area, group_position in groups:
                    # Check if policy areas match
                    if group_area == question_area:
                        # Determine relevance and position mapping
                        relevance = self._calculate_question_group_relevance(
                            question_text, group_name, group_position
                        )
                        
                        if relevance > 0:
                            mapping[question_id].append({
                                "group_id": group_id,
                                "relevance": relevance,
                                "position_adjustment": 1 if group_position == "conservative" else -1
                            })
                            
            logger.info(f"Created mappings for {len(mapping)} questions")
            return mapping
        except Exception as e:
            logger.error(f"Error mapping ratings to questions: {e}")
            return {}
            
    def _calculate_question_group_relevance(self, question_text, group_name, group_position):
        """
        Calculate relevance between a question and advocacy group
        
        Args:
            question_text (str): Question text
            group_name (str): Group name
            group_position (str): Group position
            
        Returns:
            float: Relevance score (0-1)
        """
        # This is a simplified implementation
        # In a real system, this would use more sophisticated NLP
        
        # Define relevance for specific groups and keywords
        group_keywords = {
            "NRA": ["gun", "firearm", "weapon", "second amendment", "background check", "assault weapon"],
            "Brady Campaign": ["gun", "firearm", "weapon", "background check", "assault weapon"],
            "Giffords": ["gun", "firearm", "weapon", "background check", "assault weapon"],
            "NumbersUSA": ["immigration", "immigrant", "border", "visa", "asylum", "refugee"],
            "ACLU": ["civil rights", "discrimination", "equality", "voting rights", "immigration"],
            "LCV": ["environment", "climate", "pollution", "carbon", "emissions", "clean energy"],
            "Sierra Club": ["environment", "climate", "pollution", "carbon", "emissions", "clean energy"],
            "AFP": ["economy", "economic", "tax", "budget", "deficit", "spending"],
            "ATR": ["tax", "budget", "deficit", "spending"],
            "HRC": ["lgbtq", "transgender", "equality", "discrimination", "marriage"],
            "NAACP": ["civil rights", "discrimination", "equality", "voting rights", "racial justice"],
            "NARAL": ["abortion", "reproductive", "pro-choice", "pro-life", "planned parenthood"],
            "SBA List": ["abortion", "reproductive", "pro-choice", "pro-life", "planned parenthood"]
        }
        
        # Check if group has defined keywords
        if group_name not in group_keywords:
            return 0.5  # Default moderate relevance
            
        # Count keyword matches
        keywords = group_keywords[group_name]
        question_lower = question_text.lower()
        
        matches = sum(1 for keyword in keywords if keyword in question_lower)
        
        # Calculate relevance
        if not keywords:
            return 0.5
            
        relevance = min(matches / len(keywords) * 2, 1.0)
        
        return relevance
        
    def infer_positions_from_ratings(self, rep_id):
        """
        Infer representative positions from advocacy ratings
        
        Args:
            rep_id (int): Representative ID
            
        Returns:
            list: List of position dictionaries
        """
        try:
            cursor = self.conn.cursor()
            
            # Get ratings for representative
            cursor.execute("""
            SELECT ar.group_id, ag.name, ag.policy_area, ag.position, ar.normalized_score
            FROM advocacy_ratings ar
            JOIN advocacy_groups ag ON ar.group_id = ag.id
            WHERE ar.representative_id = ?
            """, (rep_id,))
            
            ratings = cursor.fetchall()
            
            # Skip if no ratings
            if not ratings:
                logger.warning(f"No ratings found for representative {rep_id}")
                return []
                
            # Get question-group mappings
            mapping = self.map_ratings_to_questions()
            
            # Infer positions
            positions = []
            
            # Get questions
            cursor.execute("""
            SELECT q.id, q.question_text, pa.name as policy_area
            FROM questions q
            JOIN policy_areas pa ON q.policy_area_id = pa.id
            WHERE q.active = 1
            """)
            
            questions = cursor.fetchall()
            
            for question_id, question_text, policy_area in questions:
                # Skip if no mapping for this question
                if question_id not in mapping or not mapping[question_id]:
                    continue
                    
                # Get relevant groups for this question
                relevant_groups = mapping[question_id]
                
                # Calculate position from ratings
                scores = []
                weights = []
                
                for group_mapping in relevant_groups:
                    group_id = group_mapping["group_id"]
                    relevance = group_mapping["relevance"]
                    position_adjustment = group_mapping["position_adjustment"]
                    
                    # Find rating for this group
                    for rating_group_id, group_name, group_area, group_position, normalized_score in ratings:
                        if rating_group_id == group_id:
                            # Adjust score based on position mapping
                            adjusted_score = normalized_score * position_adjustment
                            
                            scores.append(adjusted_score)
                            weights.append(relevance)
                            break
                            
                # Skip if no scores
                if not scores:
                    continue
                    
                # Calculate weighted average
                weighted_sum = sum(s * w for s, w in zip(scores, weights))
                weight_sum = sum(weights)
                
                if weight_sum > 0:
                    avg_score = round(weighted_sum / weight_sum)
                    
                    # Calculate confidence based on number of ratings and relevance
                    confidence = min(weight_sum / 3, 1.0)  # Max out at 3 ratings
                    
                    # Create position
                    position = {
                        "representative_id": rep_id,
                        "question_id": question_id,
                        "score": avg_score,
                        "confidence": confidence,
                        "source": "advocacy_ratings",
                        "last_updated": datetime.now().isoformat()
                    }
                    
                    positions.append(position)
                    
            logger.info(f"Inferred {len(positions)} positions from ratings for representative {rep_id}")
            return positions
        except Exception as e:
            logger.error(f"Error inferring positions from ratings: {e}")
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
            
            # Prepare SQL for advocacy positions
            sql = """
            INSERT OR REPLACE INTO advocacy_positions (
                representative_id, question_id, score, confidence,
                source, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?)
            """
            
            # Insert positions to advocacy_positions
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
                
            # Also insert to main representative_positions table
            sql = """
            INSERT OR REPLACE INTO representative_positions (
                representative_id, question_id, score, confidence,
                source, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?)
            """
            
            # Insert positions
            for position in positions:
                cursor.execute(sql, (
                    position.get("representative_id"),
                    position.get("question_id"),
                    position.get("score"),
                    position.get("confidence"),
                    position.get("source"),
                    position.get("last_updated")
                ))
                
            self.conn.commit()
            logger.info(f"Saved {count} positions to database")
            return count
        except Exception as e:
            logger.error(f"Error saving positions to database: {e}")
            raise
            
    def run_advocacy_ratings_update(self, bioguide_ids=None):
        """
        Run a complete update of advocacy ratings and positions
        
        Args:
            bioguide_ids (list, optional): List of bioguide IDs to update
            
        Returns:
            dict: Summary of update results
        """
        try:
            results = {
                "ratings_collected": 0,
                "positions_inferred": 0,
                "representatives_processed": 0
            }
            
            cursor = self.conn.cursor()
            
            # Get representatives to process
            if bioguide_ids:
                placeholders = ','.join(['?'] * len(bioguide_ids))
                cursor.execute(f"""
                SELECT id, bioguide_id FROM representatives
                WHERE bioguide_id IN ({placeholders})
                """, bioguide_ids)
            else:
                cursor.execute("SELECT id, bioguide_id FROM representatives")
                
            representatives = cursor.fetchall()
            
            # Process each representative
            for rep_id, bioguide_id in representatives:
                logger.info(f"Processing advocacy ratings for representative {bioguide_id}")
                
                # Collect ratings
                ratings = self.collect_ratings(bioguide_id)
                
                # Save ratings
                if ratings:
                    count = self.save_ratings_to_db(ratings)
                    results["ratings_collected"] += count
                    
                # Infer positions
                positions = self.infer_positions_from_ratings(rep_id)
                
                # Save positions
                if positions:
                    count = self.save_positions_to_db(positions)
                    results["positions_inferred"] += count
                    
                results["representatives_processed"] += 1
                
            logger.info(f"Advocacy ratings update complete: {results}")
            return results
        except Exception as e:
            logger.error(f"Error running advocacy ratings update: {e}")
            raise
            
    def close_connection(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
