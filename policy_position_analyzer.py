import sqlite3
import logging
import requests
from datetime import datetime, timedelta
import json
import re
import time
import random
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("policy_position_analyzer.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("policy_position_analyzer")

class PolicyPositionAnalyzer:
    """
    Analyzer for determining a legislator's position on a specific policy issue
    based on their legislative activity, committee membership, and public statements.
    """
    
    def __init__(self, db_path, congress_api_key=None, propublica_api_key=None):
        """
        Initialize the analyzer
        
        Args:
            db_path (str): Path to SQLite database
            congress_api_key (str, optional): Congress.gov API key
            propublica_api_key (str, optional): ProPublica Congress API key
        """
        self.db_path = db_path
        self.congress_api_key = congress_api_key
        self.propublica_api_key = propublica_api_key
        self.conn = self._create_db_connection()
        
        # API endpoints
        self.congress_api_base = "https://api.congress.gov/v3"
        self.propublica_api_base = "https://api.propublica.org/congress/v1"
        
        # Headers for API requests
        self.congress_headers = {
            "User-Agent": "Political Alignment Tool/1.0",
            "Accept": "application/json"
        }
        if congress_api_key:
            self.congress_headers["X-API-Key"] = congress_api_key
            
        self.propublica_headers = {
            "User-Agent": "Political Alignment Tool/1.0",
            "Accept": "application/json"
        }
        if propublica_api_key:
            self.propublica_headers["X-API-Key"] = propublica_api_key
        
        # Initialize NLP components
        self._initialize_nlp()
        
        # Initialize database tables
        self._initialize_database_tables()
        
        # Define policy keywords for common issues
        self.policy_keywords = {
            "gun_control": {
                "keywords": ["gun", "firearm", "weapon", "second amendment", "background check", 
                           "assault weapon", "rifle", "pistol", "ammunition", "nra", "brady",
                           "gun violence", "mass shooting", "gun safety", "concealed carry"],
                "committees": ["judiciary", "public safety"]
            },
            "immigration": {
                "keywords": ["immigration", "immigrant", "border", "visa", "asylum", "refugee",
                           "daca", "deportation", "citizenship", "naturalization", "ice",
                           "border security", "undocumented", "illegal immigration"],
                "committees": ["judiciary", "homeland security", "foreign affairs"]
            },
            "healthcare": {
                "keywords": ["healthcare", "health care", "medicare", "medicaid", "obamacare",
                           "affordable care act", "aca", "insurance", "prescription drug",
                           "hospital", "doctor", "medical", "health insurance"],
                "committees": ["health", "energy and commerce", "ways and means"]
            },
            "climate_change": {
                "keywords": ["climate", "environment", "carbon", "emissions", "greenhouse gas",
                           "renewable energy", "solar", "wind", "fossil fuel", "epa",
                           "global warming", "clean energy", "pollution"],
                "committees": ["environment", "energy", "natural resources"]
            },
            "abortion": {
                "keywords": ["abortion", "reproductive", "pro-choice", "pro-life", "roe v wade",
                           "planned parenthood", "contraception", "birth control", "fetus",
                           "pregnancy", "reproductive rights"],
                "committees": ["judiciary", "health"]
            },
            "economy": {
                "keywords": ["economy", "economic", "tax", "budget", "deficit", "spending",
                           "jobs", "unemployment", "inflation", "recession", "stimulus",
                           "fiscal", "monetary", "trade", "tariff"],
                "committees": ["ways and means", "budget", "financial services", "banking"]
            }
        }
        
    def _create_db_connection(self):
        """Create database connection"""
        try:
            conn = sqlite3.connect(self.db_path)
            return conn
        except sqlite3.Error as e:
            logger.error(f"Error connecting to database: {e}")
            raise
            
    def _initialize_nlp(self):
        """Initialize NLP components"""
        try:
            # Download necessary NLTK data
            try:
                nltk.data.find('tokenizers/punkt')
            except LookupError:
                nltk.download('punkt')
                
            try:
                nltk.data.find('sentiment/vader_lexicon.zip')
            except LookupError:
                nltk.download('vader_lexicon')
            
            # Initialize sentiment analyzer
            self.sentiment_analyzer = SentimentIntensityAnalyzer()
            
            # Initialize TF-IDF vectorizer
            self.vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
            
            logger.info("NLP components initialized")
        except Exception as e:
            logger.error(f"Error initializing NLP components: {e}")
            raise
            
    def _initialize_database_tables(self):
        """Initialize database tables for policy analysis"""
        try:
            cursor = self.conn.cursor()
            
            # Create policy_bills table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_bills (
                id INTEGER PRIMARY KEY,
                representative_id INTEGER NOT NULL,
                policy_issue TEXT NOT NULL,
                congress_number INTEGER,
                bill_number TEXT,
                bill_title TEXT,
                bill_summary TEXT,
                role TEXT, -- 'sponsor', 'cosponsor'
                introduced_date TEXT,
                relevance_score REAL,
                position_score INTEGER, -- -3 to 3
                confidence REAL,
                source_url TEXT,
                last_updated TEXT,
                FOREIGN KEY (representative_id) REFERENCES representatives (id)
            )
            """)
            
            # Create committee_memberships table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS committee_memberships (
                id INTEGER PRIMARY KEY,
                representative_id INTEGER NOT NULL,
                committee_name TEXT,
                subcommittee_name TEXT,
                role TEXT, -- 'member', 'chair', 'ranking_member'
                congress_number INTEGER,
                start_date TEXT,
                end_date TEXT,
                FOREIGN KEY (representative_id) REFERENCES representatives (id)
            )
            """)
            
            # Create policy_statements table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_statements (
                id INTEGER PRIMARY KEY,
                representative_id INTEGER NOT NULL,
                policy_issue TEXT NOT NULL,
                statement_date TEXT,
                title TEXT,
                content TEXT,
                source_url TEXT,
                relevance_score REAL,
                sentiment_score REAL,
                position_score INTEGER, -- -3 to 3
                confidence REAL,
                FOREIGN KEY (representative_id) REFERENCES representatives (id)
            )
            """)
            
            # Create policy_analysis_results table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_analysis_results (
                id INTEGER PRIMARY KEY,
                representative_id INTEGER NOT NULL,
                policy_issue TEXT NOT NULL,
                overall_score INTEGER, -- -3 to 3
                confidence REAL,
                bills_analyzed INTEGER,
                statements_analyzed INTEGER,
                committee_relevance REAL,
                analysis_date TEXT,
                details TEXT, -- JSON with breakdown
                FOREIGN KEY (representative_id) REFERENCES representatives (id)
            )
            """)
            
            self.conn.commit()
            logger.info("Database tables initialized")
        except Exception as e:
            logger.error(f"Error initializing database tables: {e}")
            raise
            
    def analyze_policy_position(self, bioguide_id, policy_issue, years_back=6):
        """
        Analyze a legislator's position on a specific policy issue
        
        Args:
            bioguide_id (str): Bioguide ID of the legislator
            policy_issue (str): Policy issue to analyze (e.g., 'gun_control', 'immigration')
            years_back (int): Number of years to look back for analysis
            
        Returns:
            dict: Analysis results with position score and breakdown
        """
        try:
            # Get representative info
            cursor = self.conn.cursor()
            cursor.execute("""
            SELECT id, first_name, last_name, party, chamber, state
            FROM representatives
            WHERE bioguide_id = ?
            """, (bioguide_id,))
            
            rep_row = cursor.fetchone()
            if not rep_row:
                logger.error(f"Representative not found for bioguide_id {bioguide_id}")
                return None
                
            rep_id, first_name, last_name, party, chamber, state = rep_row
            
            logger.info(f"Analyzing {policy_issue} position for {first_name} {last_name}")
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=years_back * 365)
            
            # Analyze different components
            bills_analysis = self._analyze_bills(rep_id, bioguide_id, policy_issue, start_date, end_date)
            committee_analysis = self._analyze_committee_membership(rep_id, policy_issue)
            statements_analysis = self._analyze_public_statements(rep_id, bioguide_id, policy_issue, start_date, end_date)
            
            # Calculate overall position
            overall_analysis = self._calculate_overall_position(
                bills_analysis, committee_analysis, statements_analysis
            )
            
            # Save results
            self._save_analysis_results(rep_id, policy_issue, overall_analysis)
            
            # Format results
            results = {
                "representative": {
                    "bioguide_id": bioguide_id,
                    "name": f"{first_name} {last_name}",
                    "party": party,
                    "chamber": chamber,
                    "state": state
                },
                "policy_issue": policy_issue,
                "analysis_period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "years_analyzed": years_back
                },
                "overall_position": {
                    "score": overall_analysis["score"],
                    "confidence": overall_analysis["confidence"],
                    "interpretation": self._interpret_score(overall_analysis["score"])
                },
                "component_analysis": {
                    "bills": bills_analysis,
                    "committees": committee_analysis,
                    "statements": statements_analysis
                },
                "analysis_date": datetime.now().isoformat()
            }
            
            logger.info(f"Analysis complete for {first_name} {last_name} on {policy_issue}")
            return results
            
        except Exception as e:
            logger.error(f"Error analyzing policy position: {e}")
            raise
            
    def _analyze_bills(self, rep_id, bioguide_id, policy_issue, start_date, end_date):
        """
        Analyze bills sponsored/cosponsored by the representative
        
        Args:
            rep_id (int): Representative ID
            bioguide_id (str): Bioguide ID
            policy_issue (str): Policy issue
            start_date (datetime): Start date for analysis
            end_date (datetime): End date for analysis
            
        Returns:
            dict: Bills analysis results
        """
        try:
            # Get policy keywords
            policy_config = self.policy_keywords.get(policy_issue, {})
            keywords = policy_config.get("keywords", [])
            
            # Fetch bills from Congress.gov API
            sponsored_bills = self._fetch_sponsored_bills(bioguide_id, start_date, end_date)
            cosponsored_bills = self._fetch_cosponsored_bills(bioguide_id, start_date, end_date)
            
            # Analyze sponsored bills
            sponsored_analysis = []
            for bill in sponsored_bills:
                relevance = self._calculate_bill_relevance(bill, keywords)
                if relevance > 0.3:  # Only analyze relevant bills
                    position_score = self._determine_bill_position(bill, policy_issue)
                    confidence = self._calculate_bill_confidence(bill, relevance, "sponsor")
                    
                    bill_analysis = {
                        "bill_number": bill.get("number"),
                        "title": bill.get("title"),
                        "role": "sponsor",
                        "relevance_score": relevance,
                        "position_score": position_score,
                        "confidence": confidence,
                        "introduced_date": bill.get("introducedDate")
                    }
                    
                    sponsored_analysis.append(bill_analysis)
                    
                    # Save to database
                    self._save_bill_analysis(rep_id, policy_issue, bill, "sponsor", 
                                           relevance, position_score, confidence)
                    
            # Analyze cosponsored bills
            cosponsored_analysis = []
            for bill in cosponsored_bills:
                relevance = self._calculate_bill_relevance(bill, keywords)
                if relevance > 0.3:  # Only analyze relevant bills
                    position_score = self._determine_bill_position(bill, policy_issue)
                    confidence = self._calculate_bill_confidence(bill, relevance, "cosponsor")
                    
                    bill_analysis = {
                        "bill_number": bill.get("number"),
                        "title": bill.get("title"),
                        "role": "cosponsor",
                        "relevance_score": relevance,
                        "position_score": position_score,
                        "confidence": confidence,
                        "introduced_date": bill.get("introducedDate")
                    }
                    
                    cosponsored_analysis.append(bill_analysis)
                    
                    # Save to database
                    self._save_bill_analysis(rep_id, policy_issue, bill, "cosponsor", 
                                           relevance, position_score, confidence)
                    
            # Calculate weighted average
            all_bills = sponsored_analysis + cosponsored_analysis
            
            if not all_bills:
                return {
                    "bills_analyzed": 0,
                    "sponsored_count": 0,
                    "cosponsored_count": 0,
                    "average_score": 0,
                    "confidence": 0,
                    "bills": []
                }
                
            # Weight sponsored bills more heavily than cosponsored
            weighted_scores = []
            weights = []
            
            for bill in all_bills:
                weight = bill["confidence"] * (2.0 if bill["role"] == "sponsor" else 1.0)
                weighted_scores.append(bill["position_score"] * weight)
                weights.append(weight)
                
            if sum(weights) > 0:
                average_score = sum(weighted_scores) / sum(weights)
                overall_confidence = min(sum(weights) / (len(all_bills) * 2), 1.0)
            else:
                average_score = 0
                overall_confidence = 0
                
            return {
                "bills_analyzed": len(all_bills),
                "sponsored_count": len(sponsored_analysis),
                "cosponsored_count": len(cosponsored_analysis),
                "average_score": round(average_score),
                "confidence": overall_confidence,
                "bills": all_bills[:10]  # Top 10 most relevant bills
            }
            
        except Exception as e:
            logger.error(f"Error analyzing bills: {e}")
            return {
                "bills_analyzed": 0,
                "sponsored_count": 0,
                "cosponsored_count": 0,
                "average_score": 0,
                "confidence": 0,
                "bills": []
            }
            
    def _fetch_sponsored_bills(self, bioguide_id, start_date, end_date):
        """Fetch bills sponsored by the representative"""
        try:
            bills = []
            
            # Get current congress number
            current_congress = self._get_current_congress()
            
            # Fetch from multiple congresses if needed
            for congress in range(max(current_congress - 3, 115), current_congress + 1):
                url = f"{self.congress_api_base}/member/{bioguide_id}/sponsored-legislation"
                params = {
                    "congress": congress,
                    "format": "json",
                    "limit": 250
                }
                
                response = requests.get(url, headers=self.congress_headers, params=params)
                if response.status_code == 200:
                    data = response.json()
                    congress_bills = data.get("sponsoredLegislation", [])
                    
                    # Filter by date
                    for bill in congress_bills:
                        introduced_date = bill.get("introducedDate")
                        if introduced_date:
                            bill_date = datetime.fromisoformat(introduced_date.replace('Z', '+00:00')).replace(tzinfo=None)
                            if start_date <= bill_date <= end_date:
                                bills.append(bill)
                                
                # Add delay to avoid rate limiting
                time.sleep(0.5)
                
            return bills
            
        except Exception as e:
            logger.error(f"Error fetching sponsored bills: {e}")
            return []
            
    def _fetch_cosponsored_bills(self, bioguide_id, start_date, end_date):
        """Fetch bills cosponsored by the representative"""
        try:
            bills = []
            
            # Get current congress number
            current_congress = self._get_current_congress()
            
            # Fetch from multiple congresses if needed
            for congress in range(max(current_congress - 3, 115), current_congress + 1):
                url = f"{self.congress_api_base}/member/{bioguide_id}/cosponsored-legislation"
                params = {
                    "congress": congress,
                    "format": "json",
                    "limit": 250
                }
                
                response = requests.get(url, headers=self.congress_headers, params=params)
                if response.status_code == 200:
                    data = response.json()
                    congress_bills = data.get("cosponsoredLegislation", [])
                    
                    # Filter by date
                    for bill in congress_bills:
                        introduced_date = bill.get("introducedDate")
                        if introduced_date:
                            bill_date = datetime.fromisoformat(introduced_date.replace('Z', '+00:00')).replace(tzinfo=None)
                            if start_date <= bill_date <= end_date:
                                bills.append(bill)
                                
                # Add delay to avoid rate limiting
                time.sleep(0.5)
                
            return bills
            
        except Exception as e:
            logger.error(f"Error fetching cosponsored bills: {e}")
            return []
            
    def _calculate_bill_relevance(self, bill, keywords):
        """Calculate how relevant a bill is to the policy issue"""
        try:
            # Get bill text
            title = bill.get("title", "").lower()
            summary = bill.get("summary", {}).get("text", "").lower() if bill.get("summary") else ""
            
            # Combine text
            bill_text = f"{title} {summary}"
            
            # Count keyword matches
            keyword_matches = 0
            for keyword in keywords:
                if keyword.lower() in bill_text:
                    keyword_matches += 1
                    
            # Calculate relevance score
            if keywords:
                relevance = min(keyword_matches / len(keywords) * 2, 1.0)
            else:
                relevance = 0
                
            # Boost relevance for exact phrase matches
            if any(keyword.lower() in title for keyword in keywords):
                relevance = min(relevance * 1.5, 1.0)
                
            return relevance
            
        except Exception as e:
            logger.error(f"Error calculating bill relevance: {e}")
            return 0
            
    def _determine_bill_position(self, bill, policy_issue):
        """Determine the position score for a bill"""
        try:
            title = bill.get("title", "").lower()
            summary = bill.get("summary", {}).get("text", "").lower() if bill.get("summary") else ""
            
            # Combine text
            bill_text = f"{title} {summary}"
            
            # Define position indicators for different policy issues
            position_indicators = {
                "gun_control": {
                    "support": ["gun safety", "background check", "assault weapon ban", "gun violence prevention",
                              "firearm regulation", "gun control", "safe storage", "red flag"],
                    "oppose": ["second amendment protection", "gun rights", "constitutional carry",
                             "firearm freedom", "gun owner rights", "concealed carry"]
                },
                "immigration": {
                    "support": ["pathway to citizenship", "immigration reform", "daca protection",
                              "refugee assistance", "asylum protection", "comprehensive immigration"],
                    "oppose": ["border security", "immigration enforcement", "deportation",
                             "illegal immigration", "border wall", "immigration restriction"]
                },
                "healthcare": {
                    "support": ["affordable care act", "medicare expansion", "healthcare access",
                              "prescription drug", "public option", "universal healthcare"],
                    "oppose": ["repeal obamacare", "healthcare freedom", "market-based healthcare",
                             "health savings account"]
                },
                "climate_change": {
                    "support": ["clean energy", "renewable energy", "carbon reduction", "climate action",
                              "green new deal", "environmental protection", "emissions reduction"],
                    "oppose": ["fossil fuel", "energy independence", "coal protection", "oil drilling",
                             "regulatory relief", "energy freedom"]
                },
                "abortion": {
                    "support": ["reproductive rights", "pro-choice", "abortion access", "planned parenthood",
                              "women's health", "reproductive freedom"],
                    "oppose": ["pro-life", "unborn protection", "life begins", "abortion restriction",
                             "conscience protection", "religious freedom"]
                }
            }
            
            indicators = position_indicators.get(policy_issue, {"support": [], "oppose": []})
            
            # Count support and oppose indicators
            support_count = sum(1 for phrase in indicators["support"] if phrase in bill_text)
            oppose_count = sum(1 for phrase in indicators["oppose"] if phrase in bill_text)
            
            # Determine position
            if support_count > oppose_count:
                # More support indicators - negative score (liberal position)
                if support_count >= 3:
                    return -3
                elif support_count >= 2:
                    return -2
                else:
                    return -1
            elif oppose_count > support_count:
                # More oppose indicators - positive score (conservative position)
                if oppose_count >= 3:
                    return 3
                elif oppose_count >= 2:
                    return 2
                else:
                    return 1
            else:
                # Neutral or unclear
                return 0
                
        except Exception as e:
            logger.error(f"Error determining bill position: {e}")
            return 0
            
    def _calculate_bill_confidence(self, bill, relevance, role):
        """Calculate confidence in the bill position assessment"""
        try:
            confidence = relevance  # Base confidence on relevance
            
            # Adjust for role
            if role == "sponsor":
                confidence *= 1.0  # Full confidence for sponsored bills
            else:  # cosponsor
                confidence *= 0.7  # Lower confidence for cosponsored bills
                
            # Adjust for bill summary availability
            if bill.get("summary"):
                confidence *= 1.2  # Higher confidence with summary
            else:
                confidence *= 0.8  # Lower confidence without summary
                
            # Ensure confidence is between 0 and 1
            confidence = min(max(confidence, 0), 1)
            
            return confidence
            
        except Exception as e:
            logger.error(f"Error calculating bill confidence: {e}")
            return 0.5
            
    def _analyze_committee_membership(self, rep_id, policy_issue):
        """Analyze committee membership relevance to policy issue"""
        try:
            # Get policy-relevant committees
            policy_config = self.policy_keywords.get(policy_issue, {})
            relevant_committees = policy_config.get("committees", [])
            
            # Fetch committee memberships
            committee_memberships = self._fetch_committee_memberships(rep_id)
            
            # Calculate relevance
            relevant_memberships = []
            total_relevance = 0
            
            for membership in committee_memberships:
                committee_name = membership.get("committee_name", "").lower()
                relevance = 0
                
                # Check if committee is relevant to policy issue
                for relevant_committee in relevant_committees:
                    if relevant_committee.lower() in committee_name:
                        relevance = 1.0
                        break
                        
                # Partial matches
                if relevance == 0:
                    for relevant_committee in relevant_committees:
                        if any(word in committee_name for word in relevant_committee.split()):
                            relevance = 0.5
                            break
                            
                if relevance > 0:
                    # Adjust for role
                    role_multiplier = {
                        "chair": 2.0,
                        "ranking_member": 1.5,
                        "member": 1.0
                    }.get(membership.get("role", "member"), 1.0)
                    
                    relevance *= role_multiplier
                    total_relevance += relevance
                    
                    relevant_memberships.append({
                        "committee": membership.get("committee_name"),
                        "subcommittee": membership.get("subcommittee_name"),
                        "role": membership.get("role"),
                        "relevance": relevance
                    })
                    
            # Calculate overall committee relevance
            if relevant_memberships:
                committee_score = min(total_relevance / 2, 1.0)  # Normalize to 0-1
            else:
                committee_score = 0
                
            return {
                "relevant_committees": len(relevant_memberships),
                "committee_relevance_score": committee_score,
                "memberships": relevant_memberships
            }
            
        except Exception as e:
            logger.error(f"Error analyzing committee membership: {e}")
            return {
                "relevant_committees": 0,
                "committee_relevance_score": 0,
                "memberships": []
            }
            
    def _fetch_committee_memberships(self, rep_id):
        """Fetch committee memberships for the representative"""
        try:
            cursor = self.conn.cursor()
            
            # Check if we have committee data in database
            cursor.execute("""
            SELECT committee_name, subcommittee_name, role, congress_number
            FROM committee_memberships
            WHERE representative_id = ?
            """, (rep_id,))
            
            memberships = []
            for row in cursor.fetchall():
                memberships.append({
                    "committee_name": row[0],
                    "subcommittee_name": row[1],
                    "role": row[2],
                    "congress_number": row[3]
                })
                
            # If no data in database, try to fetch from API
            if not memberships:
                # Get bioguide_id
                cursor.execute("SELECT bioguide_id FROM representatives WHERE id = ?", (rep_id,))
                bioguide_row = cursor.fetchone()
                
                if bioguide_row:
                    bioguide_id = bioguide_row[0]
                    memberships = self._fetch_committee_memberships_from_api(bioguide_id)
                    
                    # Save to database
                    for membership in memberships:
                        self._save_committee_membership(rep_id, membership)
                        
            return memberships
            
        except Exception as e:
            logger.error(f"Error fetching committee memberships: {e}")
            return []
            
    def _fetch_committee_memberships_from_api(self, bioguide_id):
        """Fetch committee memberships from ProPublica API"""
        try:
            memberships = []
            
            if not self.propublica_api_key:
                logger.warning("ProPublica API key not available for committee data")
                return memberships
                
            # Get current congress
            current_congress = self._get_current_congress()
            
            # Fetch from ProPublica API
            url = f"{self.propublica_api_base}/members/{bioguide_id}.json"
            
            response = requests.get(url, headers=self.propublica_headers)
            if response.status_code == 200:
                data = response.json()
                member_data = data.get("results", [{}])[0]
                
                # Get committee assignments
                committees = member_data.get("committees", [])
                for committee in committees:
                    membership = {
                        "committee_name": committee.get("name"),
                        "subcommittee_name": None,
                        "role": committee.get("title", "member").lower(),
                        "congress_number": current_congress
                    }
                    memberships.append(membership)
                    
                # Get subcommittee assignments
                subcommittees = member_data.get("subcommittees", [])
                for subcommittee in subcommittees:
                    membership = {
                        "committee_name": subcommittee.get("parent_committee_id"),
                        "subcommittee_name": subcommittee.get("name"),
                        "role": subcommittee.get("title", "member").lower(),
                        "congress_number": current_congress
                    }
                    memberships.append(membership)
                    
            return memberships
            
        except Exception as e:
            logger.error(f"Error fetching committee memberships from API: {e}")
            return []
            
    def _analyze_public_statements(self, rep_id, bioguide_id, policy_issue, start_date, end_date):
        """Analyze public statements related to the policy issue"""
        try:
            # Get policy keywords
            policy_config = self.policy_keywords.get(policy_issue, {})
            keywords = policy_config.get("keywords", [])
            
            # Fetch statements from database or API
            statements = self._fetch_policy_statements(rep_id, bioguide_id, policy_issue, keywords, start_date, end_date)
            
            if not statements:
                return {
                    "statements_analyzed": 0,
                    "average_sentiment": 0,
                    "average_score": 0,
                    "confidence": 0,
                    "statements": []
                }
                
            # Analyze each statement
            analyzed_statements = []
            sentiment_scores = []
            position_scores = []
            
            for statement in statements:
                # Calculate sentiment
                sentiment = self._analyze_statement_sentiment(statement["content"], policy_issue)
                
                # Calculate position score
                position_score = self._determine_statement_position(statement["content"], policy_issue)
                
                # Calculate confidence
                confidence = self._calculate_statement_confidence(statement, keywords)
                
                analyzed_statement = {
                    "title": statement["title"],
                    "date": statement["date"],
                    "sentiment_score": sentiment,
                    "position_score": position_score,
                    "confidence": confidence,
                    "relevance": statement.get("relevance", 0)
                }
                
                analyzed_statements.append(analyzed_statement)
                sentiment_scores.append(sentiment)
                position_scores.append(position_score)
                
                # Save to database
                self._save_statement_analysis(rep_id, policy_issue, statement, 
                                            sentiment, position_score, confidence)
                
            # Calculate averages
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
            
            # Weight position scores by confidence
            weighted_scores = []
            weights = []
            
            for stmt in analyzed_statements:
                weight = stmt["confidence"]
                weighted_scores.append(stmt["position_score"] * weight)
                weights.append(weight)
                
            if sum(weights) > 0:
                avg_position = sum(weighted_scores) / sum(weights)
                overall_confidence = min(sum(weights) / len(analyzed_statements), 1.0)
            else:
                avg_position = 0
                overall_confidence = 0
                
            return {
                "statements_analyzed": len(analyzed_statements),
                "average_sentiment": avg_sentiment,
                "average_score": round(avg_position),
                "confidence": overall_confidence,
                "statements": analyzed_statements[:5]  # Top 5 most relevant statements
            }
            
        except Exception as e:
            logger.error(f"Error analyzing public statements: {e}")
            return {
                "statements_analyzed": 0,
                "average_sentiment": 0,
                "average_score": 0,
                "confidence": 0,
                "statements": []
            }
            
    def _fetch_policy_statements(self, rep_id, bioguide_id, policy_issue, keywords, start_date, end_date):
        """Fetch statements related to the policy issue"""
        try:
            statements = []
            
            # Check database first
            cursor = self.conn.cursor()
            cursor.execute("""
            SELECT title, content, statement_date, source_url, relevance_score
            FROM policy_statements
            WHERE representative_id = ? AND policy_issue = ?
            AND statement_date BETWEEN ? AND ?
            """, (rep_id, policy_issue, start_date.isoformat(), end_date.isoformat()))
            
            for row in cursor.fetchall():
                statements.append({
                    "title": row[0],
                    "content": row[1],
                    "date": row[2],
                    "source_url": row[3],
                    "relevance": row[4]
                })
                
            # If no statements in database, try to fetch from public sources
            if not statements:
                statements = self._fetch_statements_from_sources(bioguide_id, keywords, start_date, end_date)
                
            return statements
            
        except Exception as e:
            logger.error(f"Error fetching policy statements: {e}")
            return []
            
    def _analyze_statement_sentiment(self, content, policy_issue):
        """Analyze sentiment of a statement"""
        try:
            if not content:
                return 0
                
            # Use VADER sentiment analyzer
            sentiment_scores = self.sentiment_analyzer.polarity_scores(content)
            
            # Return compound score
            return sentiment_scores["compound"]
            
        except Exception as e:
            logger.error(f"Error analyzing statement sentiment: {e}")
            return 0
            
    def _determine_statement_position(self, content, policy_issue):
        """Determine position score from statement content"""
        try:
            if not content:
                return 0
                
            content_lower = content.lower()
            
            # Use same position indicators as bills
            position_indicators = {
                "gun_control": {
                    "support": ["gun safety", "background check", "assault weapon ban", "gun violence prevention",
                              "firearm regulation", "gun control", "safe storage", "red flag"],
                    "oppose": ["second amendment protection", "gun rights", "constitutional carry",
                             "firearm freedom", "gun owner rights", "concealed carry"]
                },
                "immigration": {
                    "support": ["pathway to citizenship", "immigration reform", "daca protection",
                              "refugee assistance", "asylum protection", "comprehensive immigration"],
                    "oppose": ["border security", "immigration enforcement", "deportation",
                             "illegal immigration", "border wall", "immigration restriction"]
                },
                "healthcare": {
                    "support": ["affordable care act", "medicare expansion", "healthcare access",
                              "prescription drug", "public option", "universal healthcare"],
                    "oppose": ["repeal obamacare", "healthcare freedom", "market-based healthcare",
                             "health savings account"]
                },
                "climate_change": {
                    "support": ["clean energy", "renewable energy", "carbon reduction", "climate action",
                              "green new deal", "environmental protection", "emissions reduction"],
                    "oppose": ["fossil fuel", "energy independence", "coal protection", "oil drilling",
                             "regulatory relief", "energy freedom"]
                },
                "abortion": {
                    "support": ["reproductive rights", "pro-choice", "abortion access", "planned parenthood",
                              "women's health", "reproductive freedom"],
                    "oppose": ["pro-life", "unborn protection", "life begins", "abortion restriction",
                             "conscience protection", "religious freedom"]
                }
            }
            
            indicators = position_indicators.get(policy_issue, {"support": [], "oppose": []})
            
            # Count support and oppose indicators
            support_count = sum(1 for phrase in indicators["support"] if phrase in content_lower)
            oppose_count = sum(1 for phrase in indicators["oppose"] if phrase in content_lower)
            
            # Get sentiment for additional context
            sentiment = self.sentiment_analyzer.polarity_scores(content)["compound"]
            
            # Determine position
            if support_count > oppose_count:
                # More support indicators - negative score (liberal position)
                if support_count >= 3 or sentiment < -0.5:
                    return -3
                elif support_count >= 2 or sentiment < -0.2:
                    return -2
                else:
                    return -1
            elif oppose_count > support_count:
                # More oppose indicators - positive score (conservative position)
                if oppose_count >= 3 or sentiment > 0.5:
                    return 3
                elif oppose_count >= 2 or sentiment > 0.2:
                    return 2
                else:
                    return 1
            else:
                # Use sentiment as tiebreaker
                if sentiment < -0.3:
                    return -1
                elif sentiment > 0.3:
                    return 1
                else:
                    return 0
                    
        except Exception as e:
            logger.error(f"Error determining statement position: {e}")
            return 0
            
    def _calculate_overall_position(self, bills_analysis, committee_analysis, statements_analysis):
        """Calculate overall position score from all components"""
        try:
            # Define weights for different components
            weights = {
                "bills": 0.5,  # Bills are most important
                "statements": 0.3,  # Statements are second
                "committees": 0.2   # Committee membership provides context
            }
            
            # Calculate weighted score
            total_score = 0
            total_weight = 0
            
            # Bills component
            if bills_analysis["confidence"] > 0:
                bill_weight = weights["bills"] * bills_analysis["confidence"]
                total_score += bills_analysis["average_score"] * bill_weight
                total_weight += bill_weight
                
            # Statements component
            if statements_analysis["confidence"] > 0:
                statement_weight = weights["statements"] * statements_analysis["confidence"]
                total_score += statements_analysis["average_score"] * statement_weight
                total_weight += statement_weight
                
            # Committee component (provides boost to confidence, not direct score)
            committee_boost = committee_analysis["committee_relevance_score"] * weights["committees"]
            
            # Calculate final score and confidence
            if total_weight > 0:
                final_score = round(total_score / total_weight)
                base_confidence = total_weight / (weights["bills"] + weights["statements"])
                final_confidence = min(base_confidence + committee_boost, 1.0)
            else:
                final_score = 0
                final_confidence = committee_boost  # Only committee relevance
                
            return {
                "score": final_score,
                "confidence": final_confidence,
                "component_weights": {
                    "bills_weight": bills_analysis["confidence"] * weights["bills"],
                    "statements_weight": statements_analysis["confidence"] * weights["statements"],
                    "committee_boost": committee_boost
                }
            }
            
        except Exception as e:
            logger.error(f"Error calculating overall position: {e}")
            return {"score": 0, "confidence": 0, "component_weights": {}}
            
    def _interpret_score(self, score):
        """Interpret the position score"""
        interpretations = {
            -3: "Strongly supports",
            -2: "Moderately supports", 
            -1: "Somewhat supports",
            0: "Neutral or mixed position",
            1: "Somewhat opposes",
            2: "Moderately opposes",
            3: "Strongly opposes"
        }
        
        return interpretations.get(score, "Unknown position")
        
    def _get_current_congress(self):
        """Get current Congress number"""
        current_year = datetime.now().year
        return ((current_year - 1789) // 2) + 1
        
    def _save_bill_analysis(self, rep_id, policy_issue, bill, role, relevance, position_score, confidence):
        """Save bill analysis to database"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
            INSERT OR REPLACE INTO policy_bills (
                representative_id, policy_issue, congress_number, bill_number,
                bill_title, bill_summary, role, introduced_date, relevance_score,
                position_score, confidence, source_url, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rep_id, policy_issue, bill.get("congress"),
                bill.get("number"), bill.get("title"),
                bill.get("summary", {}).get("text") if bill.get("summary") else None,
                role, bill.get("introducedDate"), relevance,
                position_score, confidence, bill.get("url"),
                datetime.now().isoformat()
            ))
            
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error saving bill analysis: {e}")
            
    def _save_committee_membership(self, rep_id, membership):
        """Save committee membership to database"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
            INSERT OR REPLACE INTO committee_memberships (
                representative_id, committee_name, subcommittee_name,
                role, congress_number, start_date, end_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                rep_id, membership.get("committee_name"),
                membership.get("subcommittee_name"), membership.get("role"),
                membership.get("congress_number"), None, None
            ))
            
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error saving committee membership: {e}")
            
    def _save_statement_analysis(self, rep_id, policy_issue, statement, sentiment, position_score, confidence):
        """Save statement analysis to database"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
            INSERT OR REPLACE INTO policy_statements (
                representative_id, policy_issue, statement_date, title,
                content, source_url, relevance_score, sentiment_score,
                position_score, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rep_id, policy_issue, statement.get("date"),
                statement.get("title"), statement.get("content"),
                statement.get("source_url"), statement.get("relevance", 0),
                sentiment, position_score, confidence
            ))
            
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error saving statement analysis: {e}")
            
    def _save_analysis_results(self, rep_id, policy_issue, analysis):
        """Save overall analysis results to database"""
        try:
            cursor = self.conn.cursor()
            
            # Get counts from analysis components
            bills_count = 0
            statements_count = 0
            committee_relevance = 0
            
            # Create details JSON
            details = json.dumps(analysis)
            
            cursor.execute("""
            INSERT OR REPLACE INTO policy_analysis_results (
                representative_id, policy_issue, overall_score, confidence,
                bills_analyzed, statements_analyzed, committee_relevance,
                analysis_date, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rep_id, policy_issue, analysis["score"], analysis["confidence"],
                bills_count, statements_count, committee_relevance,
                datetime.now().isoformat(), details
            ))
            
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error saving analysis results: {e}")
            
    def _fetch_statements_from_sources(self, bioguide_id, keywords, start_date, end_date):
        """Fetch statements from various sources (placeholder implementation)"""
        # This would implement fetching from press releases, social media, etc.
        # For now, return empty list
        return []
        
    def _calculate_statement_confidence(self, statement, keywords):
        """Calculate confidence in statement analysis"""
        try:
            confidence = statement.get("relevance", 0.5)
            
            # Adjust based on content length
            content_length = len(statement.get("content", ""))
            if content_length > 500:
                confidence *= 1.2
            elif content_length < 100:
                confidence *= 0.8
                
            # Adjust based on recency
            if statement.get("date"):
                try:
                    stmt_date = datetime.fromisoformat(statement["date"])
                    days_old = (datetime.now() - stmt_date).days
                    recency_factor = max(1.0 - (days_old / 365), 0.5)
                    confidence *= recency_factor
                except:
                    pass
                    
            return min(max(confidence, 0), 1)
            
        except Exception as e:
            logger.error(f"Error calculating statement confidence: {e}")
            return 0.5
            
    def close_connection(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


# Example usage function
def analyze_legislator_policy_position(bioguide_id, policy_issue, db_path="political_alignment.db", 
                                     congress_api_key=None, propublica_api_key=None):
    """
    Convenience function to analyze a legislator's position on a policy issue
    
    Args:
        bioguide_id (str): Bioguide ID of the legislator
        policy_issue (str): Policy issue to analyze
        db_path (str): Path to database
        congress_api_key (str, optional): Congress.gov API key
        propublica_api_key (str, optional): ProPublica API key
        
    Returns:
        dict: Analysis results
    """
    analyzer = PolicyPositionAnalyzer(db_path, congress_api_key, propublica_api_key)
    
    try:
        results = analyzer.analyze_policy_position(bioguide_id, policy_issue)
        return results
    finally:
        analyzer.close_connection()


if __name__ == "__main__":
    # Example usage
    import os
    
    # Get API keys from environment variables
    congress_api_key = os.environ.get("CONGRESS_API_KEY")
    propublica_api_key = os.environ.get("PROPUBLICA_API_KEY")
    
    # Analyze Chuck Schumer's position on gun control
    results = analyze_legislator_policy_position(
        bioguide_id="S000148",
        policy_issue="gun_control",
        congress_api_key=congress_api_key,
        propublica_api_key=propublica_api_key
    )
    
    if results:
        print(f"\nPolicy Position Analysis for {results['representative']['name']}")
        print(f"Issue: {results['policy_issue'].replace('_', ' ').title()}")
        print(f"Overall Score: {results['overall_position']['score']} ({results['overall_position']['interpretation']})")
        print(f"Confidence: {results['overall_position']['confidence']:.2f}")
        
        print(f"\nComponent Analysis:")
        print(f"Bills: {results['component_analysis']['bills']['bills_analyzed']} analyzed, avg score: {results['component_analysis']['bills']['average_score']}")
        print(f"Statements: {results['component_analysis']['statements']['statements_analyzed']} analyzed, avg score: {results['component_analysis']['statements']['average_score']}")
        print(f"Committee Relevance: {results['component_analysis']['committees']['committee_relevance_score']:.2f}")
    else:
        print("Analysis failed")