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
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer
from nltk.tokenize import sent_tokenize

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("public_statements_analyzer.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("public_statements_analyzer")

class PublicStatementsAnalyzer:
    """
    Analyzer for collecting and processing public statements from lawmakers
    
    This class handles fetching and analyzing official statements, press releases,
    and speeches to infer positions on policy issues.
    """
    
    def __init__(self, db_path, propublica_api_key=None):
        """
        Initialize the analyzer with database path and API key
        
        Args:
            db_path (str): Path to SQLite database
            propublica_api_key (str, optional): API key for ProPublica Congress API
        """
        self.db_path = db_path
        self.propublica_api_key = propublica_api_key
        self.conn = self._create_db_connection()
        self.propublica_base_url = "https://api.propublica.org/congress/v1"
        self.web_base_url = "https://www.congress.gov"
        
        # Define headers for API requests
        self.headers = {
            "User-Agent": "Political Alignment Tool/1.0",
            "Accept": "application/json"
        }
        
        if propublica_api_key:
            self.propublica_headers = {
                "X-API-Key": propublica_api_key,
                "User-Agent": "Political Alignment Tool/1.0",
                "Accept": "application/json"
            }
        
        # Initialize NLP components
        self._initialize_nlp()
        
        # Initialize database tables
        self._initialize_database_tables()
        
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
            
            # Initialize TF-IDF vectorizer for text similarity
            self.vectorizer = TfidfVectorizer(stop_words='english')
            
            logger.info("NLP components initialized")
        except Exception as e:
            logger.error(f"Error initializing NLP components: {e}")
            raise
            
    def _initialize_database_tables(self):
        """Initialize database tables for public statements"""
        try:
            cursor = self.conn.cursor()
            
            # Create public_statements table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS public_statements (
                id INTEGER PRIMARY KEY,
                representative_id INTEGER NOT NULL,
                statement_date TEXT,
                title TEXT,
                content TEXT,
                source_url TEXT,
                source_type TEXT,
                FOREIGN KEY (representative_id) REFERENCES representatives (id)
            )
            """)
            
            # Create statement_topics table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS statement_topics (
                id INTEGER PRIMARY KEY,
                statement_id INTEGER NOT NULL,
                topic TEXT,
                relevance REAL,
                FOREIGN KEY (statement_id) REFERENCES public_statements (id)
            )
            """)
            
            # Create statement_positions table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS statement_positions (
                id INTEGER PRIMARY KEY,
                statement_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                score INTEGER,
                confidence REAL,
                sentiment_score REAL,
                relevance_score REAL,
                FOREIGN KEY (statement_id) REFERENCES public_statements (id),
                FOREIGN KEY (question_id) REFERENCES questions (id)
            )
            """)
            
            self.conn.commit()
            logger.info("Database tables initialized")
        except Exception as e:
            logger.error(f"Error initializing database tables: {e}")
            raise
            
    def fetch_statements(self, bioguide_id, limit=50):
        """
        Fetch public statements for a representative
        
        Args:
            bioguide_id (str): Bioguide ID
            limit (int, optional): Maximum number of statements to fetch
            
        Returns:
            list: List of statement dictionaries
        """
        try:
            statements = []
            
            # Get representative ID
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT id FROM representatives WHERE bioguide_id = ?",
                (bioguide_id,)
            )
            
            rep_row = cursor.fetchone()
            if not rep_row:
                logger.warning(f"Representative not found for bioguide_id {bioguide_id}")
                return statements
                
            rep_id = rep_row[0]
            
            # Use ProPublica API if key is available
            if self.propublica_api_key:
                api_statements = self._fetch_statements_from_propublica(bioguide_id, limit)
                statements.extend(api_statements)
                
            # Fetch from official website regardless of API availability
            website_statements = self._fetch_statements_from_website(bioguide_id, limit)
            statements.extend(website_statements)
            
            # Remove duplicates based on title and date
            unique_statements = []
            seen_titles = set()
            
            for statement in statements:
                title_date = f"{statement.get('title')}_{statement.get('statement_date')}"
                if title_date not in seen_titles:
                    seen_titles.add(title_date)
                    statement['representative_id'] = rep_id
                    unique_statements.append(statement)
                    
                if len(unique_statements) >= limit:
                    break
                    
            logger.info(f"Fetched {len(unique_statements)} statements for representative {bioguide_id}")
            return unique_statements
        except Exception as e:
            logger.error(f"Error fetching statements for representative {bioguide_id}: {e}")
            return []
            
    def _fetch_statements_from_propublica(self, bioguide_id, limit):
        """
        Fetch statements from ProPublica Congress API
        
        Args:
            bioguide_id (str): Bioguide ID
            limit (int): Maximum number of statements to fetch
            
        Returns:
            list: List of statement dictionaries
        """
        statements = []
        
        try:
            # Build API URL for statements
            url = f"{self.propublica_base_url}/members/{bioguide_id}/statements/116"
            
            # Make request
            response = requests.get(url, headers=self.propublica_headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Process statements
            for statement in data.get("results", []):
                statement_data = {
                    "statement_date": statement.get("date"),
                    "title": statement.get("title"),
                    "content": statement.get("statement_type"),  # Limited content in API
                    "source_url": statement.get("url"),
                    "source_type": "press_release"
                }
                
                # Fetch full content if URL is available
                if statement_data["source_url"]:
                    try:
                        full_content = self._fetch_statement_content(statement_data["source_url"])
                        if full_content:
                            statement_data["content"] = full_content
                    except Exception as e:
                        logger.warning(f"Error fetching full content: {e}")
                
                statements.append(statement_data)
                
                if len(statements) >= limit:
                    break
                    
            return statements
        except Exception as e:
            logger.error(f"Error fetching statements from ProPublica: {e}")
            return []
            
    def _fetch_statements_from_website(self, bioguide_id, limit):
        """
        Fetch statements from representative's official website
        
        Args:
            bioguide_id (str): Bioguide ID
            limit (int): Maximum number of statements to fetch
            
        Returns:
            list: List of statement dictionaries
        """
        statements = []
        
        try:
            # First, get the representative's website URL
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT first_name, last_name, state, chamber FROM representatives WHERE bioguide_id = ?",
                (bioguide_id,)
            )
            
            rep_info = cursor.fetchone()
            if not rep_info:
                logger.warning(f"Representative info not found for bioguide_id {bioguide_id}")
                return statements
                
            first_name, last_name, state, chamber = rep_info
            
            # Try to find website URL from Congress.gov
            website_url = self._get_representative_website(bioguide_id)
            
            if not website_url:
                logger.warning(f"Website URL not found for representative {bioguide_id}")
                return statements
                
            # Find press releases or statements section
            press_url = self._find_press_releases_url(website_url)
            
            if not press_url:
                logger.warning(f"Press releases URL not found for representative {bioguide_id}")
                return statements
                
            # Fetch press releases
            statements = self._scrape_press_releases(press_url, limit)
            
            return statements
        except Exception as e:
            logger.error(f"Error fetching statements from website: {e}")
            return []
            
    def _get_representative_website(self, bioguide_id):
        """
        Get representative's official website URL
        
        Args:
            bioguide_id (str): Bioguide ID
            
        Returns:
            str: Website URL or None
        """
        try:
            # Build URL for member page
            url = f"{self.web_base_url}/member/{bioguide_id}"
            
            # Make request
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find website link
            website_link = soup.find('a', href=lambda href: href and ('house.gov' in href or 'senate.gov' in href))
            
            if website_link:
                return website_link.get('href')
                
            return None
        except Exception as e:
            logger.error(f"Error getting representative website: {e}")
            return None
            
    def _find_press_releases_url(self, website_url):
        """
        Find URL for press releases section
        
        Args:
            website_url (str): Representative's website URL
            
        Returns:
            str: Press releases URL or None
        """
        try:
            # Make request
            response = requests.get(website_url, headers=self.headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for common press release link patterns
            press_links = soup.find_all('a', href=lambda href: href and any(term in href.lower() for term in [
                'press', 'news', 'release', 'media', 'statement', 'newsroom'
            ]))
            
            if press_links:
                # Get the first matching link
                press_href = press_links[0].get('href')
                
                # Handle relative URLs
                if press_href.startswith('/'):
                    return website_url.rstrip('/') + press_href
                elif not press_href.startswith(('http://', 'https://')):
                    return website_url.rstrip('/') + '/' + press_href
                else:
                    return press_href
                    
            return None
        except Exception as e:
            logger.error(f"Error finding press releases URL: {e}")
            return None
            
    def _scrape_press_releases(self, press_url, limit):
        """
        Scrape press releases from website
        
        Args:
            press_url (str): Press releases URL
            limit (int): Maximum number of releases to fetch
            
        Returns:
            list: List of statement dictionaries
        """
        statements = []
        
        try:
            # Make request
            response = requests.get(press_url, headers=self.headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find press release links
            # This is challenging because each website has different structure
            # We'll look for common patterns
            
            # Try to find a list of articles or press items
            articles = soup.find_all(['article', 'div', 'li'], class_=lambda c: c and any(term in c.lower() for term in [
                'press', 'release', 'news-item', 'media', 'post', 'article'
            ]))
            
            if not articles:
                # Try a more general approach
                articles = soup.find_all('a', href=True)
                
            # Process each potential press release
            for article in articles:
                # Try to find title and link
                title_elem = article.find(['h1', 'h2', 'h3', 'h4', 'strong', 'a'])
                
                if not title_elem:
                    continue
                    
                title = title_elem.get_text().strip()
                
                # Skip if title is too short or generic
                if len(title) < 10 or title.lower() in ['press releases', 'news', 'media']:
                    continue
                    
                # Find link
                link = None
                if title_elem.name == 'a' and title_elem.has_attr('href'):
                    link = title_elem['href']
                else:
                    link_elem = article.find('a')
                    if link_elem and link_elem.has_attr('href'):
                        link = link_elem['href']
                        
                if not link:
                    continue
                    
                # Handle relative URLs
                if link.startswith('/'):
                    base_url = '/'.join(press_url.split('/')[:3])  # Get domain
                    link = base_url + link
                elif not link.startswith(('http://', 'https://')):
                    link = '/'.join(press_url.split('/')[:-1]) + '/' + link
                    
                # Try to find date
                date_elem = article.find(['time', 'span', 'div'], class_=lambda c: c and any(term in c.lower() for term in [
                    'date', 'time', 'published', 'posted'
                ]))
                
                date_text = None
                if date_elem:
                    date_text = date_elem.get_text().strip()
                    
                # If no date element found, try to extract from text
                if not date_text:
                    text = article.get_text()
                    date_match = re.search(r'(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\w+ \d{1,2},? \d{4})', text)
                    if date_match:
                        date_text = date_match.group(1)
                        
                # Parse date
                statement_date = self._parse_date(date_text) if date_text else None
                
                # Fetch full content
                content = self._fetch_statement_content(link)
                
                # Create statement data
                statement_data = {
                    "statement_date": statement_date,
                    "title": title,
                    "content": content,
                    "source_url": link,
                    "source_type": "press_release"
                }
                
                statements.append(statement_data)
                
                if len(statements) >= limit:
                    break
                    
            return statements
        except Exception as e:
            logger.error(f"Error scraping press releases: {e}")
            return []
            
    def _fetch_statement_content(self, url):
        """
        Fetch full content of a statement
        
        Args:
            url (str): Statement URL
            
        Returns:
            str: Statement content or None
        """
        try:
            # Make request
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove navigation, header, footer, etc.
            for element in soup.find_all(['nav', 'header', 'footer', 'aside', 'script', 'style']):
                element.decompose()
                
            # Try to find main content
            content_elem = soup.find(['article', 'main', 'div'], class_=lambda c: c and any(term in c.lower() for term in [
                'content', 'body', 'text', 'article', 'press-release', 'statement'
            ]))
            
            if not content_elem:
                # Try more generic approach
                content_elem = soup.find('body')
                
            if content_elem:
                # Extract text
                content = content_elem.get_text()
                
                # Clean up whitespace
                content = re.sub(r'\s+', ' ', content).strip()
                
                return content
                
            return None
        except Exception as e:
            logger.error(f"Error fetching statement content: {e}")
            return None
            
    def _parse_date(self, date_text):
        """
        Parse date from text
        
        Args:
            date_text (str): Date text
            
        Returns:
            str: ISO format date or None
        """
        try:
            if not date_text:
                return None
                
            # Try different date formats
            for fmt in ["%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"]:
                try:
                    return datetime.strptime(date_text, fmt).isoformat()
                except ValueError:
                    continue
                    
            return None
        except Exception:
            return None
            
    def save_statements_to_db(self, statements):
        """
        Save statements to database
        
        Args:
            statements (list): List of statement dictionaries
            
        Returns:
            int: Number of statements saved
        """
        try:
            cursor = self.conn.cursor()
            
            # Prepare SQL
            sql = """
            INSERT OR REPLACE INTO public_statements (
                representative_id, statement_date, title, content,
                source_url, source_type
            ) VALUES (?, ?, ?, ?, ?, ?)
            """
            
            # Insert statements
            count = 0
            for statement in statements:
                cursor.execute(sql, (
                    statement.get("representative_id"),
                    statement.get("statement_date"),
                    statement.get("title"),
                    statement.get("content"),
                    statement.get("source_url"),
                    statement.get("source_type")
                ))
                
                # Get statement ID
                statement_id = cursor.lastrowid
                
                # Extract and save topics
                if statement.get("content"):
                    topics = self._extract_topics(statement.get("content"))
                    self._save_statement_topics(statement_id, topics)
                    
                count += 1
                
            self.conn.commit()
            logger.info(f"Saved {count} statements to database")
            return count
        except Exception as e:
            logger.error(f"Error saving statements to database: {e}")
            raise
            
    def _extract_topics(self, content):
        """
        Extract topics from statement content
        
        Args:
            content (str): Statement content
            
        Returns:
            list: List of topic dictionaries
        """
        try:
            # This is a simplified implementation
            # In a real system, this would use more sophisticated topic modeling
            
            # Define common policy topics and related keywords
            policy_topics = {
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
            
            # Convert content to lowercase for matching
            content_lower = content.lower()
            
            # Count keyword occurrences for each topic
            topic_counts = {}
            for topic, keywords in policy_topics.items():
                count = sum(content_lower.count(keyword) for keyword in keywords)
                if count > 0:
                    topic_counts[topic] = count
                    
            # Calculate relevance scores
            total_matches = sum(topic_counts.values())
            topics = []
            
            if total_matches > 0:
                for topic, count in topic_counts.items():
                    relevance = count / total_matches
                    topics.append({
                        "topic": topic,
                        "relevance": relevance
                    })
                    
            # Sort by relevance
            topics.sort(key=lambda x: x["relevance"], reverse=True)
            
            return topics
        except Exception as e:
            logger.error(f"Error extracting topics: {e}")
            return []
            
    def _save_statement_topics(self, statement_id, topics):
        """
        Save statement topics to database
        
        Args:
            statement_id (int): Statement ID
            topics (list): List of topic dictionaries
            
        Returns:
            int: Number of topics saved
        """
        try:
            cursor = self.conn.cursor()
            
            # Prepare SQL
            sql = """
            INSERT INTO statement_topics (
                statement_id, topic, relevance
            ) VALUES (?, ?, ?)
            """
            
            # Insert topics
            count = 0
            for topic in topics:
                cursor.execute(sql, (
                    statement_id,
                    topic.get("topic"),
                    topic.get("relevance")
                ))
                count += 1
                
            return count
        except Exception as e:
            logger.error(f"Error saving statement topics: {e}")
            return 0
            
    def analyze_statements_for_positions(self, rep_id):
        """
        Analyze statements to infer positions on questions
        
        Args:
            rep_id (int): Representative ID
            
        Returns:
            list: List of position dictionaries
        """
        try:
            cursor = self.conn.cursor()
            
            # Get statements for representative
            cursor.execute("""
            SELECT id, title, content, statement_date
            FROM public_statements
            WHERE representative_id = ?
            ORDER BY statement_date DESC
            """, (rep_id,))
            
            statements = cursor.fetchall()
            
            # Get questions
            cursor.execute("""
            SELECT q.id, q.question_text, pa.name as policy_area
            FROM questions q
            JOIN policy_areas pa ON q.policy_area_id = pa.id
            WHERE q.active = 1
            """)
            
            questions = cursor.fetchall()
            
            # Analyze statements for each question
            positions = []
            
            for question_id, question_text, policy_area in questions:
                # Find relevant statements for this question
                relevant_statements = self._find_relevant_statements(statements, question_text, policy_area)
                
                if not relevant_statements:
                    continue
                    
                # Analyze statements to determine position
                position_data = self._analyze_position_from_statements(relevant_statements, question_text)
                
                if position_data:
                    position = {
                        "representative_id": rep_id,
                        "question_id": question_id,
                        "score": position_data.get("score"),
                        "confidence": position_data.get("confidence"),
                        "source": "public_statements",
                        "last_updated": datetime.now().isoformat()
                    }
                    
                    positions.append(position)
                    
                    # Save statement positions
                    self._save_statement_positions(relevant_statements, question_id, position_data)
                    
            logger.info(f"Inferred {len(positions)} positions from statements for representative {rep_id}")
            return positions
        except Exception as e:
            logger.error(f"Error analyzing statements for positions: {e}")
            return []
            
    def _find_relevant_statements(self, statements, question_text, policy_area):
        """
        Find statements relevant to a question
        
        Args:
            statements (list): List of statement tuples
            question_text (str): Question text
            policy_area (str): Policy area name
            
        Returns:
            list: List of relevant statement dictionaries
        """
        try:
            relevant_statements = []
            
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
            question_keywords = set(re.findall(r'\b\w+\b', question_text.lower()))
            
            # Combine keywords
            all_keywords = question_keywords.union(area_keywords)
            
            # Check each statement for relevance
            for statement_id, title, content, statement_date in statements:
                if not content:
                    continue
                    
                # Check for keyword matches
                content_lower = content.lower()
                title_lower = title.lower() if title else ""
                
                # Count keyword matches
                keyword_matches = sum(1 for keyword in all_keywords if keyword in content_lower or keyword in title_lower)
                
                # Calculate relevance score
                relevance = min(keyword_matches / len(all_keywords), 1.0) if all_keywords else 0
                
                # Calculate text similarity
                similarity = self._calculate_text_similarity(question_text, content)
                
                # Combine scores
                combined_relevance = (relevance + similarity) / 2
                
                # Include if sufficiently relevant
                if combined_relevance >= 0.1:  # Threshold for relevance
                    relevant_statements.append({
                        "statement_id": statement_id,
                        "title": title,
                        "content": content,
                        "statement_date": statement_date,
                        "relevance": combined_relevance
                    })
                    
            # Sort by relevance
            relevant_statements.sort(key=lambda x: x["relevance"], reverse=True)
            
            return relevant_statements
        except Exception as e:
            logger.error(f"Error finding relevant statements: {e}")
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
            
    def _analyze_position_from_statements(self, statements, question_text):
        """
        Analyze statements to determine position on a question
        
        Args:
            statements (list): List of statement dictionaries
            question_text (str): Question text
            
        Returns:
            dict: Position data or None
        """
        try:
            # Extract key parts of the question
            question_parts = self._extract_question_parts(question_text)
            
            # Analyze each statement
            statement_scores = []
            
            for statement in statements:
                content = statement.get("content")
                if not content:
                    continue
                    
                # Split into sentences
                sentences = sent_tokenize(content)
                
                # Find sentences relevant to the question
                relevant_sentences = []
                for sentence in sentences:
                    # Check if sentence contains question keywords
                    if any(keyword in sentence.lower() for keyword in question_parts["keywords"]):
                        relevant_sentences.append(sentence)
                        
                # Skip if no relevant sentences
                if not relevant_sentences:
                    continue
                    
                # Analyze sentiment of relevant sentences
                sentiments = []
                for sentence in relevant_sentences:
                    sentiment = self.sentiment_analyzer.polarity_scores(sentence)
                    sentiments.append(sentiment)
                    
                # Calculate average sentiment
                avg_sentiment = sum(s["compound"] for s in sentiments) / len(sentiments) if sentiments else 0
                
                # Determine position based on sentiment and question type
                score = self._sentiment_to_position(avg_sentiment, question_parts["position_type"])
                
                # Calculate confidence based on relevance and recency
                confidence = statement.get("relevance", 0.5)
                
                # Adjust confidence based on statement date if available
                if statement.get("statement_date"):
                    try:
                        statement_date = datetime.fromisoformat(statement.get("statement_date"))
                        days_old = (datetime.now() - statement_date).days
                        recency_factor = max(1.0 - (days_old / 365), 0.1)  # Reduce confidence for older statements
                        confidence *= recency_factor
                    except:
                        pass
                        
                statement_scores.append({
                    "score": score,
                    "confidence": confidence,
                    "sentiment": avg_sentiment
                })
                
            # Skip if no scores
            if not statement_scores:
                return None
                
            # Calculate weighted average score
            weighted_sum = sum(s["score"] * s["confidence"] for s in statement_scores)
            weight_sum = sum(s["confidence"] for s in statement_scores)
            
            if weight_sum > 0:
                avg_score = round(weighted_sum / weight_sum)
                
                # Calculate overall confidence
                overall_confidence = min(weight_sum / 3, 1.0)  # Max out at 3 statements
                
                return {
                    "score": avg_score,
                    "confidence": overall_confidence,
                    "sentiment_score": sum(s["sentiment"] for s in statement_scores) / len(statement_scores)
                }
                
            return None
        except Exception as e:
            logger.error(f"Error analyzing position from statements: {e}")
            return None
            
    def _extract_question_parts(self, question_text):
        """
        Extract key parts from a question
        
        Args:
            question_text (str): Question text
            
        Returns:
            dict: Question parts
        """
        # Convert to lowercase
        question_lower = question_text.lower()
        
        # Determine position type (favor/oppose)
        position_type = "favor"  # Default
        if "oppose" in question_lower:
            position_type = "oppose"
            
        # Extract keywords
        # Remove common words and punctuation
        stop_words = ["do", "you", "favor", "oppose", "neither", "nor", "a", "an", "the", "for", "in", "on", "at", "by", "to", "of"]
        words = re.findall(r'\b\w+\b', question_lower)
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        return {
            "position_type": position_type,
            "keywords": keywords
        }
        
    def _sentiment_to_position(self, sentiment, position_type):
        """
        Convert sentiment score to position score
        
        Args:
            sentiment (float): Sentiment score (-1 to 1)
            position_type (str): Position type ('favor' or 'oppose')
            
        Returns:
            int: Position score (-3 to 3)
        """
        # Scale sentiment from -1..1 to -3..3
        scaled = round(sentiment * 3)
        
        # Adjust based on position type
        if position_type == "oppose":
            scaled = -scaled  # Invert for oppose questions
            
        return scaled
        
    def _save_statement_positions(self, statements, question_id, position_data):
        """
        Save statement positions to database
        
        Args:
            statements (list): List of statement dictionaries
            question_id (int): Question ID
            position_data (dict): Position data
            
        Returns:
            int: Number of positions saved
        """
        try:
            cursor = self.conn.cursor()
            
            # Prepare SQL
            sql = """
            INSERT OR REPLACE INTO statement_positions (
                statement_id, question_id, score, confidence,
                sentiment_score, relevance_score
            ) VALUES (?, ?, ?, ?, ?, ?)
            """
            
            # Insert positions
            count = 0
            for statement in statements:
                cursor.execute(sql, (
                    statement.get("statement_id"),
                    question_id,
                    position_data.get("score"),
                    position_data.get("confidence"),
                    position_data.get("sentiment_score"),
                    statement.get("relevance")
                ))
                count += 1
                
            self.conn.commit()
            return count
        except Exception as e:
            logger.error(f"Error saving statement positions: {e}")
            return 0
            
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
            
    def run_public_statements_update(self, bioguide_ids=None, limit_per_rep=50):
        """
        Run a complete update of public statements and positions
        
        Args:
            bioguide_ids (list, optional): List of bioguide IDs to update
            limit_per_rep (int, optional): Maximum number of statements per representative
            
        Returns:
            dict: Summary of update results
        """
        try:
            results = {
                "statements_collected": 0,
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
                logger.info(f"Processing public statements for representative {bioguide_id}")
                
                # Fetch statements
                statements = self.fetch_statements(bioguide_id, limit_per_rep)
                
                # Save statements
                if statements:
                    count = self.save_statements_to_db(statements)
                    results["statements_collected"] += count
                    
                # Analyze statements for positions
                positions = self.analyze_statements_for_positions(rep_id)
                
                # Save positions
                if positions:
                    count = self.save_positions_to_db(positions)
                    results["positions_inferred"] += count
                    
                results["representatives_processed"] += 1
                
            logger.info(f"Public statements update complete: {results}")
            return results
        except Exception as e:
            logger.error(f"Error running public statements update: {e}")
            raise
            
    def close_connection(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
