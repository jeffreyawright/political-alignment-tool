import sqlite3
import logging
import json
from datetime import datetime
import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("position_estimation.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("position_estimation")

class PositionEstimationAlgorithm:
    """
    Algorithm for estimating representative positions using multiple data sources
    
    This class integrates data from voting records, bill sponsorships,
    public statements, and advocacy group ratings to provide comprehensive
    position estimates on policy questions.
    """
    
    def __init__(self, db_path):
        """
        Initialize the algorithm with database path
        
        Args:
            db_path (str): Path to SQLite database
        """
        self.db_path = db_path
        self.conn = self._create_db_connection()
        
        # Initialize database tables
        self._initialize_database_tables()
        
        # Define source weights
        self.source_weights = {
            "voting_records": 0.35,
            "bill_sponsorships": 0.25,
            "public_statements": 0.25,
            "advocacy_ratings": 0.15
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
        """Initialize database tables for position estimation"""
        try:
            cursor = self.conn.cursor()
            
            # Create integrated_positions table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS integrated_positions (
                id INTEGER PRIMARY KEY,
                representative_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                score INTEGER,
                confidence REAL,
                voting_records_score INTEGER,
                voting_records_confidence REAL,
                bill_sponsorships_score INTEGER,
                bill_sponsorships_confidence REAL,
                public_statements_score INTEGER,
                public_statements_confidence REAL,
                advocacy_ratings_score INTEGER,
                advocacy_ratings_confidence REAL,
                last_updated TEXT,
                FOREIGN KEY (representative_id) REFERENCES representatives (id),
                FOREIGN KEY (question_id) REFERENCES questions (id)
            )
            """)
            
            # Create position_estimation_logs table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS position_estimation_logs (
                id INTEGER PRIMARY KEY,
                representative_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                estimation_date TEXT,
                source_data TEXT,
                calculation_details TEXT,
                FOREIGN KEY (representative_id) REFERENCES representatives (id),
                FOREIGN KEY (question_id) REFERENCES questions (id)
            )
            """)
            
            self.conn.commit()
            logger.info("Database tables initialized")
        except Exception as e:
            logger.error(f"Error initializing database tables: {e}")
            raise
            
    def estimate_positions(self, rep_id, question_ids=None):
        """
        Estimate positions for a representative on all or specific questions
        
        Args:
            rep_id (int): Representative ID
            question_ids (list, optional): List of question IDs to estimate
            
        Returns:
            list: List of position dictionaries
        """
        try:
            cursor = self.conn.cursor()
            
            # Get questions to estimate
            if question_ids:
                placeholders = ','.join(['?'] * len(question_ids))
                cursor.execute(f"""
                SELECT q.id, q.question_text, pa.name as policy_area
                FROM questions q
                JOIN policy_areas pa ON q.policy_area_id = pa.id
                WHERE q.active = 1 AND q.id IN ({placeholders})
                """, question_ids)
            else:
                cursor.execute("""
                SELECT q.id, q.question_text, pa.name as policy_area
                FROM questions q
                JOIN policy_areas pa ON q.policy_area_id = pa.id
                WHERE q.active = 1
                """)
                
            questions = cursor.fetchall()
            
            # Get representative info
            cursor.execute("""
            SELECT bioguide_id, first_name, last_name, party
            FROM representatives
            WHERE id = ?
            """, (rep_id,))
            
            rep_info = cursor.fetchone()
            if not rep_info:
                logger.warning(f"Representative not found for ID {rep_id}")
                return []
                
            bioguide_id, first_name, last_name, party = rep_info
            
            # Estimate positions for each question
            positions = []
            
            for question_id, question_text, policy_area in questions:
                # Get positions from all sources
                source_positions = self._get_source_positions(rep_id, question_id)
                
                # Skip if no positions from any source
                if not any(source_positions.values()):
                    # Try fallback methods
                    fallback_position = self._estimate_position_fallback(
                        rep_id, question_id, question_text, policy_area, party
                    )
                    
                    if fallback_position:
                        positions.append(fallback_position)
                        
                    continue
                    
                # Integrate positions from all sources
                integrated_position = self._integrate_positions(
                    rep_id, question_id, source_positions
                )
                
                # Log estimation details
                self._log_estimation_details(
                    rep_id, question_id, source_positions, integrated_position
                )
                
                positions.append(integrated_position)
                
            logger.info(f"Estimated {len(positions)} positions for representative {bioguide_id}")
            return positions
        except Exception as e:
            logger.error(f"Error estimating positions: {e}")
            return []
            
    def _get_source_positions(self, rep_id, question_id):
        """
        Get positions from all sources for a representative and question
        
        Args:
            rep_id (int): Representative ID
            question_id (int): Question ID
            
        Returns:
            dict: Dictionary of positions by source
        """
        try:
            cursor = self.conn.cursor()
            
            # Initialize result
            source_positions = {
                "voting_records": None,
                "bill_sponsorships": None,
                "public_statements": None,
                "advocacy_ratings": None
            }
            
            # Get position from voting records
            cursor.execute("""
            SELECT score, confidence
            FROM representative_positions
            WHERE representative_id = ? AND question_id = ? AND source = 'voting_records'
            """, (rep_id, question_id))
            
            row = cursor.fetchone()
            if row:
                source_positions["voting_records"] = {
                    "score": row[0],
                    "confidence": row[1]
                }
                
            # Get position from bill sponsorships
            cursor.execute("""
            SELECT score, confidence
            FROM representative_positions
            WHERE representative_id = ? AND question_id = ? AND source = 'bill_sponsorships'
            """, (rep_id, question_id))
            
            row = cursor.fetchone()
            if row:
                source_positions["bill_sponsorships"] = {
                    "score": row[0],
                    "confidence": row[1]
                }
                
            # Get position from public statements
            cursor.execute("""
            SELECT score, confidence
            FROM representative_positions
            WHERE representative_id = ? AND question_id = ? AND source = 'public_statements'
            """, (rep_id, question_id))
            
            row = cursor.fetchone()
            if row:
                source_positions["public_statements"] = {
                    "score": row[0],
                    "confidence": row[1]
                }
                
            # Get position from advocacy ratings
            cursor.execute("""
            SELECT score, confidence
            FROM representative_positions
            WHERE representative_id = ? AND question_id = ? AND source = 'advocacy_ratings'
            """, (rep_id, question_id))
            
            row = cursor.fetchone()
            if row:
                source_positions["advocacy_ratings"] = {
                    "score": row[0],
                    "confidence": row[1]
                }
                
            return source_positions
        except Exception as e:
            logger.error(f"Error getting source positions: {e}")
            return {
                "voting_records": None,
                "bill_sponsorships": None,
                "public_statements": None,
                "advocacy_ratings": None
            }
            
    def _integrate_positions(self, rep_id, question_id, source_positions):
        """
        Integrate positions from all sources
        
        Args:
            rep_id (int): Representative ID
            question_id (int): Question ID
            source_positions (dict): Dictionary of positions by source
            
        Returns:
            dict: Integrated position
        """
        try:
            # Extract scores and confidences
            scores = []
            confidences = []
            source_weights = []
            
            for source, position in source_positions.items():
                if position:
                    scores.append(position["score"])
                    confidences.append(position["confidence"])
                    source_weights.append(self.source_weights[source])
                    
            # Skip if no scores
            if not scores:
                return None
                
            # Calculate weighted average score
            # Weight by both source weight and confidence
            combined_weights = [s * c for s, c in zip(source_weights, confidences)]
            weight_sum = sum(combined_weights)
            
            if weight_sum > 0:
                weighted_sum = sum(s * w for s, w in zip(scores, combined_weights))
                avg_score = round(weighted_sum / weight_sum)
                
                # Calculate overall confidence
                # Based on number of sources and their confidences
                source_count = len(scores)
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0
                
                # Adjust confidence based on source count and agreement
                source_factor = min(source_count / 4, 1.0)  # Max out at 4 sources
                
                # Calculate agreement factor (higher if sources agree)
                if len(scores) > 1:
                    score_array = np.array(scores).reshape(1, -1)
                    agreement = np.std(scores) / 3  # Normalize by scale range
                    agreement_factor = 1 - min(agreement, 1.0)  # Higher agreement = higher factor
                else:
                    agreement_factor = 0.7  # Default for single source
                    
                overall_confidence = avg_confidence * source_factor * agreement_factor
                
                # Create integrated position
                integrated_position = {
                    "representative_id": rep_id,
                    "question_id": question_id,
                    "score": avg_score,
                    "confidence": overall_confidence,
                    "voting_records_score": source_positions["voting_records"]["score"] if source_positions["voting_records"] else None,
                    "voting_records_confidence": source_positions["voting_records"]["confidence"] if source_positions["voting_records"] else None,
                    "bill_sponsorships_score": source_positions["bill_sponsorships"]["score"] if source_positions["bill_sponsorships"] else None,
                    "bill_sponsorships_confidence": source_positions["bill_sponsorships"]["confidence"] if source_positions["bill_sponsorships"] else None,
                    "public_statements_score": source_positions["public_statements"]["score"] if source_positions["public_statements"] else None,
                    "public_statements_confidence": source_positions["public_statements"]["confidence"] if source_positions["public_statements"] else None,
                    "advocacy_ratings_score": source_positions["advocacy_ratings"]["score"] if source_positions["advocacy_ratings"] else None,
                    "advocacy_ratings_confidence": source_positions["advocacy_ratings"]["confidence"] if source_positions["advocacy_ratings"] else None,
                    "last_updated": datetime.now().isoformat()
                }
                
                return integrated_position
                
            return None
        except Exception as e:
            logger.error(f"Error integrating positions: {e}")
            return None
            
    def _estimate_position_fallback(self, rep_id, question_id, question_text, policy_area, party):
        """
        Estimate position using fallback methods when no direct data is available
        
        Args:
            rep_id (int): Representative ID
            question_id (int): Question ID
            question_text (str): Question text
            policy_area (str): Policy area
            party (str): Representative party
            
        Returns:
            dict: Estimated position or None
        """
        try:
            cursor = self.conn.cursor()
            
            # Try different fallback methods in order of preference
            
            # 1. Similar questions for this representative
            similar_question_position = self._fallback_similar_questions(
                rep_id, question_id, question_text, policy_area
            )
            
            if similar_question_position:
                return similar_question_position
                
            # 2. Same question for similar representatives
            similar_rep_position = self._fallback_similar_representatives(
                rep_id, question_id, party
            )
            
            if similar_rep_position:
                return similar_rep_position
                
            # 3. Party-based estimate (last resort)
            party_position = self._fallback_party_based(
                rep_id, question_id, policy_area, party
            )
            
            if party_position:
                return party_position
                
            return None
        except Exception as e:
            logger.error(f"Error estimating position fallback: {e}")
            return None
            
    def _fallback_similar_questions(self, rep_id, question_id, question_text, policy_area):
        """
        Estimate position based on similar questions for this representative
        
        Args:
            rep_id (int): Representative ID
            question_id (int): Question ID
            question_text (str): Question text
            policy_area (str): Policy area
            
        Returns:
            dict: Estimated position or None
        """
        try:
            cursor = self.conn.cursor()
            
            # Get other questions in the same policy area
            cursor.execute("""
            SELECT q.id, q.question_text
            FROM questions q
            JOIN policy_areas pa ON q.policy_area_id = pa.id
            WHERE pa.name = ? AND q.id != ? AND q.active = 1
            """, (policy_area, question_id))
            
            other_questions = cursor.fetchall()
            
            if not other_questions:
                return None
                
            # Get positions for other questions
            positions = []
            
            for other_id, other_text in other_questions:
                cursor.execute("""
                SELECT score, confidence
                FROM integrated_positions
                WHERE representative_id = ? AND question_id = ?
                """, (rep_id, other_id))
                
                row = cursor.fetchone()
                if row:
                    positions.append({
                        "question_id": other_id,
                        "question_text": other_text,
                        "score": row[0],
                        "confidence": row[1]
                    })
                    
            if not positions:
                return None
                
            # Calculate text similarity
            similarities = []
            for position in positions:
                similarity = self._calculate_text_similarity(
                    question_text, position["question_text"]
                )
                similarities.append(similarity)
                
            # Weight by similarity and confidence
            weights = [s * p["confidence"] for s, p in zip(similarities, positions)]
            weight_sum = sum(weights)
            
            if weight_sum > 0:
                weighted_sum = sum(p["score"] * w for p, w in zip(positions, weights))
                avg_score = round(weighted_sum / weight_sum)
                
                # Calculate confidence (lower than direct sources)
                max_similarity = max(similarities)
                confidence = max_similarity * 0.7  # Cap at 70% of max confidence
                
                return {
                    "representative_id": rep_id,
                    "question_id": question_id,
                    "score": avg_score,
                    "confidence": confidence,
                    "voting_records_score": None,
                    "voting_records_confidence": None,
                    "bill_sponsorships_score": None,
                    "bill_sponsorships_confidence": None,
                    "public_statements_score": None,
                    "public_statements_confidence": None,
                    "advocacy_ratings_score": None,
                    "advocacy_ratings_confidence": None,
                    "last_updated": datetime.now().isoformat()
                }
                
            return None
        except Exception as e:
            logger.error(f"Error in fallback similar questions: {e}")
            return None
            
    def _fallback_similar_representatives(self, rep_id, question_id, party):
        """
        Estimate position based on similar representatives for this question
        
        Args:
            rep_id (int): Representative ID
            question_id (int): Question ID
            party (str): Representative party
            
        Returns:
            dict: Estimated position or None
        """
        try:
            cursor = self.conn.cursor()
            
            # Get positions from other representatives of the same party
            cursor.execute("""
            SELECT ip.score, ip.confidence
            FROM integrated_positions ip
            JOIN representatives r ON ip.representative_id = r.id
            WHERE ip.question_id = ? AND r.party = ? AND r.id != ?
            """, (question_id, party, rep_id))
            
            positions = cursor.fetchall()
            
            if not positions:
                return None
                
            # Calculate average score
            scores = [p[0] for p in positions]
            confidences = [p[1] for p in positions]
            
            # Weight by confidence
            weighted_sum = sum(s * c for s, c in zip(scores, confidences))
            weight_sum = sum(confidences)
            
            if weight_sum > 0:
                avg_score = round(weighted_sum / weight_sum)
                
                # Calculate confidence (lower than direct sources)
                confidence = min(weight_sum / len(positions), 0.6)  # Cap at 60%
                
                return {
                    "representative_id": rep_id,
                    "question_id": question_id,
                    "score": avg_score,
                    "confidence": confidence,
                    "voting_records_score": None,
                    "voting_records_confidence": None,
                    "bill_sponsorships_score": None,
                    "bill_sponsorships_confidence": None,
                    "public_statements_score": None,
                    "public_statements_confidence": None,
                    "advocacy_ratings_score": None,
                    "advocacy_ratings_confidence": None,
                    "last_updated": datetime.now().isoformat()
                }
                
            return None
        except Exception as e:
            logger.error(f"Error in fallback similar representatives: {e}")
            return None
            
    def _fallback_party_based(self, rep_id, question_id, policy_area, party):
        """
        Estimate position based on party (last resort)
        
        Args:
            rep_id (int): Representative ID
            question_id (int): Question ID
            policy_area (str): Policy area
            party (str): Representative party
            
        Returns:
            dict: Estimated position or None
        """
        try:
            # Skip if no party info
            if not party:
                return None
                
            # Define party-based estimates for different policy areas
            party_estimates = {
                "Gun Control": {"D": -2, "R": 2, "I": 0},
                "Immigration": {"D": -2, "R": 2, "I": 0},
                "Healthcare": {"D": -2, "R": 2, "I": 0},
                "Economy": {"D": -1, "R": 1, "I": 0},
                "Environment": {"D": -2, "R": 2, "I": 0},
                "Education": {"D": -1, "R": 1, "I": 0},
                "Foreign Policy": {"D": -1, "R": 1, "I": 0},
                "Civil Rights": {"D": -2, "R": 2, "I": 0},
                "Abortion": {"D": -2, "R": 2, "I": 0}
            }
            
            # Get estimate for this policy area and party
            if policy_area in party_estimates and party in party_estimates[policy_area]:
                score = party_estimates[policy_area][party]
                
                # Very low confidence for party-based estimates
                confidence = 0.3
                
                return {
                    "representative_id": rep_id,
                    "question_id": question_id,
                    "score": score,
                    "confidence": confidence,
                    "voting_records_score": None,
                    "voting_records_confidence": None,
                    "bill_sponsorships_score": None,
                    "bill_sponsorships_confidence": None,
                    "public_statements_score": None,
                    "public_statements_confidence": None,
                    "advocacy_ratings_score": None,
                    "advocacy_ratings_confidence": None,
                    "last_updated": datetime.now().isoformat()
                }
                
            return None
        except Exception as e:
            logger.error(f"Error in fallback party based: {e}")
            return None
            
    def _calculate_text_similarity(self, text1, text2):
        """
        Calculate similarity between two texts
        
        Args:
            text1 (str): First text
            text2 (str): Second text
            
        Returns:
            float: Similarity score (0-1)
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            
            # Handle empty texts
            if not text1 or not text2:
                return 0
                
            # Create TF-IDF vectorizer
            vectorizer = TfidfVectorizer(stop_words='english')
            
            # Fit vectorizer on both texts
            tfidf_matrix = vectorizer.fit_transform([text1, text2])
            
            # Calculate cosine similarity
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            
            return similarity
        except Exception as e:
            logger.error(f"Error calculating text similarity: {e}")
            return 0
            
    def _log_estimation_details(self, rep_id, question_id, source_positions, integrated_position):
        """
        Log details of position estimation for transparency
        
        Args:
            rep_id (int): Representative ID
            question_id (int): Question ID
            source_positions (dict): Dictionary of positions by source
            integrated_position (dict): Integrated position
        """
        try:
            cursor = self.conn.cursor()
            
            # Convert to JSON for storage
            source_data = json.dumps(source_positions)
            calculation_details = json.dumps(integrated_position)
            
            # Prepare SQL
            sql = """
            INSERT INTO position_estimation_logs (
                representative_id, question_id, estimation_date,
                source_data, calculation_details
            ) VALUES (?, ?, ?, ?, ?)
            """
            
            # Insert log
            cursor.execute(sql, (
                rep_id,
                question_id,
                datetime.now().isoformat(),
                source_data,
                calculation_details
            ))
            
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error logging estimation details: {e}")
            
    def save_positions_to_db(self, positions):
        """
        Save integrated positions to database
        
        Args:
            positions (list): List of position dictionaries
            
        Returns:
            int: Number of positions saved
        """
        try:
            cursor = self.conn.cursor()
            
            # Prepare SQL
            sql = """
            INSERT OR REPLACE INTO integrated_positions (
                representative_id, question_id, score, confidence,
                voting_records_score, voting_records_confidence,
                bill_sponsorships_score, bill_sponsorships_confidence,
                public_statements_score, public_statements_confidence,
                advocacy_ratings_score, advocacy_ratings_confidence,
                last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            # Insert positions
            count = 0
            for position in positions:
                if not position:
                    continue
                    
                cursor.execute(sql, (
                    position.get("representative_id"),
                    position.get("question_id"),
                    position.get("score"),
                    position.get("confidence"),
                    position.get("voting_records_score"),
                    position.get("voting_records_confidence"),
                    position.get("bill_sponsorships_score"),
                    position.get("bill_sponsorships_confidence"),
                    position.get("public_statements_score"),
                    position.get("public_statements_confidence"),
                    position.get("advocacy_ratings_score"),
                    position.get("advocacy_ratings_confidence"),
                    position.get("last_updated")
                ))
                count += 1
                
            self.conn.commit()
            logger.info(f"Saved {count} integrated positions to database")
            return count
        except Exception as e:
            logger.error(f"Error saving positions to database: {e}")
            raise
            
    def run_position_estimation(self, bioguide_ids=None):
        """
        Run position estimation for all or specific representatives
        
        Args:
            bioguide_ids (list, optional): List of bioguide IDs to process
            
        Returns:
            dict: Summary of estimation results
        """
        try:
            results = {
                "positions_estimated": 0,
                "representatives_processed": 0,
                "questions_processed": 0
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
            
            # Get active questions
            cursor.execute("SELECT COUNT(*) FROM questions WHERE active = 1")
            question_count = cursor.fetchone()[0]
            
            # Process each representative
            for rep_id, bioguide_id in representatives:
                logger.info(f"Estimating positions for representative {bioguide_id}")
                
                # Estimate positions
                positions = self.estimate_positions(rep_id)
                
                # Save positions
                if positions:
                    count = self.save_positions_to_db(positions)
                    results["positions_estimated"] += count
                    
                results["representatives_processed"] += 1
                
            results["questions_processed"] = question_count
            
            logger.info(f"Position estimation complete: {results}")
            return results
        except Exception as e:
            logger.error(f"Error running position estimation: {e}")
            raise
            
    def get_position_distribution(self):
        """
        Get distribution of positions across representatives
        
        Returns:
            dict: Distribution statistics
        """
        try:
            cursor = self.conn.cursor()
            
            # Get counts by score
            cursor.execute("""
            SELECT score, COUNT(*) as count
            FROM integrated_positions
            GROUP BY score
            ORDER BY score
            """)
            
            score_distribution = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Get counts by confidence range
            cursor.execute("""
            SELECT 
                CASE 
                    WHEN confidence < 0.3 THEN 'low'
                    WHEN confidence < 0.7 THEN 'medium'
                    ELSE 'high'
                END as confidence_range,
                COUNT(*) as count
            FROM integrated_positions
            GROUP BY confidence_range
            """)
            
            confidence_distribution = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Get counts by source availability
            cursor.execute("""
            SELECT 
                SUM(CASE WHEN voting_records_score IS NOT NULL THEN 1 ELSE 0 END) as voting_records_count,
                SUM(CASE WHEN bill_sponsorships_score IS NOT NULL THEN 1 ELSE 0 END) as bill_sponsorships_count,
                SUM(CASE WHEN public_statements_score IS NOT NULL THEN 1 ELSE 0 END) as public_statements_count,
                SUM(CASE WHEN advocacy_ratings_score IS NOT NULL THEN 1 ELSE 0 END) as advocacy_ratings_count,
                COUNT(*) as total_count
            FROM integrated_positions
            """)
            
            source_counts = cursor.fetchone()
            source_distribution = {
                "voting_records": source_counts[0] / source_counts[4] if source_counts[4] > 0 else 0,
                "bill_sponsorships": source_counts[1] / source_counts[4] if source_counts[4] > 0 else 0,
                "public_statements": source_counts[2] / source_counts[4] if source_counts[4] > 0 else 0,
                "advocacy_ratings": source_counts[3] / source_counts[4] if source_counts[4] > 0 else 0
            }
            
            # Get party distribution
            cursor.execute("""
            SELECT 
                r.party,
                AVG(ip.score) as avg_score,
                COUNT(*) as count
            FROM integrated_positions ip
            JOIN representatives r ON ip.representative_id = r.id
            GROUP BY r.party
            """)
            
            party_distribution = {row[0]: {"avg_score": row[1], "count": row[2]} for row in cursor.fetchall()}
            
            return {
                "score_distribution": score_distribution,
                "confidence_distribution": confidence_distribution,
                "source_distribution": source_distribution,
                "party_distribution": party_distribution
            }
        except Exception as e:
            logger.error(f"Error getting position distribution: {e}")
            return {}
            
    def get_position_quality_metrics(self):
        """
        Get quality metrics for position estimates
        
        Returns:
            dict: Quality metrics
        """
        try:
            cursor = self.conn.cursor()
            
            # Get average confidence
            cursor.execute("SELECT AVG(confidence) FROM integrated_positions")
            avg_confidence = cursor.fetchone()[0]
            
            # Get source coverage
            cursor.execute("""
            SELECT 
                AVG(CASE WHEN voting_records_score IS NOT NULL THEN 1 ELSE 0 END) as voting_records_coverage,
                AVG(CASE WHEN bill_sponsorships_score IS NOT NULL THEN 1 ELSE 0 END) as bill_sponsorships_coverage,
                AVG(CASE WHEN public_statements_score IS NOT NULL THEN 1 ELSE 0 END) as public_statements_coverage,
                AVG(CASE WHEN advocacy_ratings_score IS NOT NULL THEN 1 ELSE 0 END) as advocacy_ratings_coverage
            FROM integrated_positions
            """)
            
            coverage = cursor.fetchone()
            source_coverage = {
                "voting_records": coverage[0],
                "bill_sponsorships": coverage[1],
                "public_statements": coverage[2],
                "advocacy_ratings": coverage[3]
            }
            
            # Get average sources per position
            cursor.execute("""
            SELECT AVG(
                CASE WHEN voting_records_score IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN bill_sponsorships_score IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN public_statements_score IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN advocacy_ratings_score IS NOT NULL THEN 1 ELSE 0 END
            ) as avg_sources
            FROM integrated_positions
            """)
            
            avg_sources = cursor.fetchone()[0]
            
            # Get party correlation
            cursor.execute("""
            SELECT 
                CASE 
                    WHEN r.party = 'D' THEN -1
                    WHEN r.party = 'R' THEN 1
                    ELSE 0
                END as party_score,
                ip.score
            FROM integrated_positions ip
            JOIN representatives r ON ip.representative_id = r.id
            WHERE r.party IN ('D', 'R')
            """)
            
            party_scores = cursor.fetchall()
            
            if party_scores:
                party_correlation = np.corrcoef(
                    [row[0] for row in party_scores],
                    [row[1] for row in party_scores]
                )[0, 1]
            else:
                party_correlation = 0
                
            return {
                "avg_confidence": avg_confidence,
                "source_coverage": source_coverage,
                "avg_sources_per_position": avg_sources,
                "party_correlation": party_correlation
            }
        except Exception as e:
            logger.error(f"Error getting position quality metrics: {e}")
            return {}
            
    def close_connection(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
