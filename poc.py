import os
import sqlite3
import logging
import pandas as pd
import numpy as np
from datetime import datetime
import json

# Import our modules
from congress_scraper import CongressDataScraper
from rvoteview_scraper import RvoteviewScraper
from alignment_scoring import AlignmentScoring

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("poc.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("poc")

class PoliticalAlignmentPOC:
    """
    Proof of Concept for the Political Alignment Tool
    
    This class demonstrates the core functionality of the system with
    a simplified workflow and sample data.
    """
    
    def __init__(self, db_path="political_alignment.db"):
        """
        Initialize the POC with database path
        
        Args:
            db_path (str): Path to SQLite database
        """
        self.db_path = db_path
        self.conn = None
        
        # Initialize components
        self.congress_scraper = CongressDataScraper(
            db_path=db_path,
            api_key=os.environ.get("CONGRESS_API_KEY")
        )
        
        self.rvoteview_scraper = RvoteviewScraper(db_path=db_path)
        self.scoring_system = AlignmentScoring(db_path=db_path)
        
    def initialize_database(self, schema_file="schema.sql"):
        """
        Initialize the database with schema and sample data
        
        Args:
            schema_file (str): Path to SQL schema file
        """
        try:
            # Create database connection
            self.conn = sqlite3.connect(self.db_path)
            
            # Initialize schema
            logger.info(f"Initializing database schema from {schema_file}...")
            self.congress_scraper.initialize_database(schema_file)
            
            # Initialize sample data
            logger.info("Initializing sample data...")
            self._initialize_sample_data()
            
            logger.info("Database initialization complete")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
            
    def _initialize_sample_data(self):
        """Initialize sample data for policy areas and questions"""
        cursor = self.conn.cursor()
        
        # Check if policy areas already exist
        cursor.execute("SELECT COUNT(*) FROM policy_areas")
        count = cursor.fetchone()[0]
        
        if count > 0:
            logger.info("Sample data already exists, skipping initialization")
            return
            
        # Add policy areas
        policy_areas = [
            (1, "Gun Control", "Gun control and firearms regulation", 1),
            (2, "Immigration", "Immigration policy and border security", 1),
            (3, "Abortion", "Abortion rights and reproductive health", 1)
        ]
        
        cursor.executemany("""
        INSERT OR REPLACE INTO policy_areas (id, name, description, active)
        VALUES (?, ?, ?, ?)
        """, policy_areas)
        
        # Add sample questions
        questions = [
            # Gun Control questions
            (1, 1, "Do you favor, oppose, or neither favor nor oppose requiring background checks for gun purchases at gun shows or other private sales?", "User Survey", 1),
            (2, 1, "Do you favor, oppose, or neither favor nor oppose a mandatory program where the government would buy back semi-automatic assault-style rifles from citizens who currently own them?", "User Survey", 1),
            (3, 1, "Do you favor, oppose, or neither favor nor oppose banning the sale of semi-automatic 'assault-style' rifles?", "User Survey", 1),
            
            # Immigration questions
            (4, 2, "Do you think the number of immigrants to America nowadays should be increased, remain the same, or reduced?", "GSS2022", 1),
            (5, 2, "Do you think immigrants living in the U.S. should adopt U.S. culture, keep their own culture, or do both?", "GSS2020", 1),
            (6, 2, "What should be done about immigrants who are currently living in the U.S. illegally?", "GSS2022", 1),
            
            # Abortion questions
            (7, 3, "Which of the following best represents your beliefs about abortion?", "GSS2022", 1),
            (8, 3, "Should it be possible for a pregnant woman to obtain a legal abortion if the woman's own health is seriously endangered by the pregnancy?", "GSS2022", 1),
            (9, 3, "Should it be possible for a pregnant woman to obtain a legal abortion if the woman wants it for any reason?", "GSS2022", 1)
        ]
        
        cursor.executemany("""
        INSERT OR REPLACE INTO questions (id, policy_area_id, question_text, source, active)
        VALUES (?, ?, ?, ?, ?)
        """, questions)
        
        # Add response options
        response_options = [
            # Gun Control Q1
            (1, 1, "Favor a great deal", -3),
            (2, 1, "Favor a moderate amount", -2),
            (3, 1, "Favor a little", -1),
            (4, 1, "Neither favor nor oppose", 0),
            (5, 1, "Oppose a little", 1),
            (6, 1, "Oppose a moderate amount", 2),
            (7, 1, "Oppose a great deal", 3),
            
            # Gun Control Q2
            (8, 2, "Favor a great deal", -3),
            (9, 2, "Favor a moderate amount", -2),
            (10, 2, "Favor a little", -1),
            (11, 2, "Neither favor nor oppose", 0),
            (12, 2, "Oppose a little", 1),
            (13, 2, "Oppose a moderate amount", 2),
            (14, 2, "Oppose a great deal", 3),
            
            # Gun Control Q3
            (15, 3, "Favor a great deal", -3),
            (16, 3, "Favor a moderate amount", -2),
            (17, 3, "Favor a little", -1),
            (18, 3, "Neither favor nor oppose", 0),
            (19, 3, "Oppose a little", 1),
            (20, 3, "Oppose a moderate amount", 2),
            (21, 3, "Oppose a great deal", 3),
            
            # Immigration Q1
            (22, 4, "Increased", -3),
            (23, 4, "Increased a little", -2),
            (24, 4, "Remain the same as it is", 0),
            (25, 4, "Reduced a little", 2),
            (26, 4, "Reduced a lot", 3),
            
            # Immigration Q2
            (27, 5, "Adopt U.S. culture", 1),
            (28, 5, "Keep their own culture", -1),
            (29, 5, "Do both", 0),
            
            # Immigration Q3
            (30, 6, "Become citizens", -3),
            (31, 6, "Become permanent legal residents", -1),
            (32, 6, "Identified and deported", 3),
            
            # Abortion Q1
            (33, 7, "Strongly pro-choice", -3),
            (34, 7, "Slightly pro-choice", -1),
            (35, 7, "Both pro-choice and pro-life", 0),
            (36, 7, "Neither pro-choice nor pro-life", 0),
            (37, 7, "Slightly pro-life", 1),
            (38, 7, "Strongly pro-life", 3),
            
            # Abortion Q2
            (39, 8, "Yes", -3),
            (40, 8, "No", 3),
            
            # Abortion Q3
            (41, 9, "Yes", -3),
            (42, 9, "No", 3)
        ]
        
        cursor.executemany("""
        INSERT OR REPLACE INTO response_options (id, question_id, option_text, score)
        VALUES (?, ?, ?, ?)
        """, response_options)
        
        # Add sample representatives
        representatives = [
            # Democrats
            (1, "S001197", "Schumer", "Charles", "NY", None, "D", "senate", 118, None, -0.4, 0.1),
            (2, "D000622", "Durbin", "Richard", "IL", None, "D", "senate", 118, None, -0.3, 0.2),
            (3, "W000805", "Warren", "Elizabeth", "MA", None, "D", "senate", 118, None, -0.7, 0.1),
            (4, "S000148", "Sanders", "Bernard", "VT", None, "I", "senate", 118, None, -0.8, 0.0),
            (5, "B001230", "Brown", "Sherrod", "OH", None, "D", "senate", 118, None, -0.3, 0.3),
            
            # Republicans
            (6, "M000355", "McConnell", "Mitch", "KY", None, "R", "senate", 118, None, 0.5, 0.1),
            (7, "C001075", "Cruz", "Ted", "TX", None, "R", "senate", 118, None, 0.8, -0.1),
            (8, "R000595", "Rubio", "Marco", "FL", None, "R", "senate", 118, None, 0.6, 0.0),
            (9, "P000612", "Paul", "Rand", "KY", None, "R", "senate", 118, None, 0.7, -0.2),
            (10, "G000555", "Graham", "Lindsey", "SC", None, "R", "senate", 118, None, 0.4, 0.2)
        ]
        
        cursor.executemany("""
        INSERT OR REPLACE INTO representatives (
            id, bioguide_id, last_name, first_name, state, district, 
            party, chamber, congress_number, voteview_id, nominate_score1, nominate_score2
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, representatives)
        
        # Add sample positions
        positions = [
            # Gun Control positions for Democrats
            (1, 1, -3, 0.9, "inferred", datetime.now().isoformat()),
            (1, 2, -2, 0.8, "inferred", datetime.now().isoformat()),
            (1, 3, -3, 0.9, "inferred", datetime.now().isoformat()),
            
            (2, 1, -3, 0.9, "inferred", datetime.now().isoformat()),
            (2, 2, -1, 0.7, "inferred", datetime.now().isoformat()),
            (2, 3, -3, 0.9, "inferred", datetime.now().isoformat()),
            
            (3, 1, -3, 0.9, "inferred", datetime.now().isoformat()),
            (3, 2, -3, 0.9, "inferred", datetime.now().isoformat()),
            (3, 3, -3, 0.9, "inferred", datetime.now().isoformat()),
            
            (4, 1, -3, 0.9, "inferred", datetime.now().isoformat()),
            (4, 2, -3, 0.9, "inferred", datetime.now().isoformat()),
            (4, 3, -3, 0.9, "inferred", datetime.now().isoformat()),
            
            (5, 1, -3, 0.9, "inferred", datetime.now().isoformat()),
            (5, 2, -2, 0.8, "inferred", datetime.now().isoformat()),
            (5, 3, -3, 0.9, "inferred", datetime.now().isoformat()),
            
            # Gun Control positions for Republicans
            (6, 1, 3, 0.9, "inferred", datetime.now().isoformat()),
            (6, 2, 3, 0.9, "inferred", datetime.now().isoformat()),
            (6, 3, 3, 0.9, "inferred", datetime.now().isoformat()),
            
            (7, 1, 3, 0.9, "inferred", datetime.now().isoformat()),
            (7, 2, 3, 0.9, "inferred", datetime.now().isoformat()),
            (7, 3, 3, 0.9, "inferred", datetime.now().isoformat()),
            
            (8, 1, 3, 0.9, "inferred", datetime.now().isoformat()),
            (8, 2, 3, 0.9, "inferred", datetime.now().isoformat()),
            (8, 3, 3, 0.9, "inferred", datetime.now().isoformat()),
            
            (9, 1, 3, 0.9, "inferred", datetime.now().isoformat()),
            (9, 2, 3, 0.9, "inferred", datetime.now().isoformat()),
            (9, 3, 3, 0.9, "inferred", datetime.now().isoformat()),
            
            (10, 1, 3, 0.9, "inferred", datetime.now().isoformat()),
            (10, 2, 3, 0.9, "inferred", datetime.now().isoformat()),
            (10, 3, 3, 0.9, "inferred", datetime.now().isoformat()),
            
            # Immigration positions for Democrats
            (1, 4, -2, 0.8, "inferred", datetime.now().isoformat()),
            (1, 5, 0, 0.6, "inferred", datetime.now().isoformat()),
            (1, 6, -3, 0.9, "inferred", datetime.now().isoformat()),
            
            (2, 4, -2, 0.8, "inferred", datetime.now().isoformat()),
            (2, 5, 0, 0.6, "inferred", datetime.now().isoformat()),
            (2, 6, -2, 0.8, "inferred", datetime.now().isoformat()),
            
            # Immigration positions for Republicans
            (6, 4, 3, 0.9, "inferred", datetime.now().isoformat()),
            (6, 5, 1, 0.7, "inferred", datetime.now().isoformat()),
            (6, 6, 3, 0.9, "inferred", datetime.now().isoformat()),
            
            (7, 4, 3, 0.9, "inferred", datetime.now().isoformat()),
            (7, 5, 1, 0.7, "inferred", datetime.now().isoformat()),
            (7, 6, 3, 0.9, "inferred", datetime.now().isoformat()),
            
            # Abortion positions for Democrats
            (1, 7, -3, 0.9, "inferred", datetime.now().isoformat()),
            (1, 8, -3, 0.9, "inferred", datetime.now().isoformat()),
            (1, 9, -3, 0.9, "inferred", datetime.now().isoformat()),
            
            (3, 7, -3, 0.9, "inferred", datetime.now().isoformat()),
            (3, 8, -3, 0.9, "inferred", datetime.now().isoformat()),
            (3, 9, -3, 0.9, "inferred", datetime.now().isoformat()),
            
            # Abortion positions for Republicans
            (6, 7, 3, 0.9, "inferred", datetime.now().isoformat()),
            (6, 8, -1, 0.7, "inferred", datetime.now().isoformat()),
            (6, 9, 3, 0.9, "inferred", datetime.now().isoformat()),
            
            (7, 7, 3, 0.9, "inferred", datetime.now().isoformat()),
            (7, 8, 0, 0.6, "inferred", datetime.now().isoformat()),
            (7, 9, 3, 0.9, "inferred", datetime.now().isoformat())
        ]
        
        cursor.executemany("""
        INSERT OR REPLACE INTO representative_positions (
            representative_id, question_id, score, confidence,
            source, last_updated
        ) VALUES (?, ?, ?, ?, ?, ?)
        """, positions)
        
        self.conn.commit()
        logger.info("Sample data initialization complete")
        
    def run_demo(self):
        """
        Run a demonstration of the system
        
        Returns:
            dict: Results of the demonstration
        """
        try:
            # 1. Get survey questions
            survey_questions = self._get_survey_questions()
            
            # 2. Generate sample user responses
            user_responses = self._generate_sample_responses(survey_questions)
            
            # 3. Calculate alignment scores
            alignment_results = self._calculate_alignment(user_responses)
            
            # 4. Generate sample user with demographics
            user_with_demographics = self._generate_sample_user_with_demographics()
            
            # 5. Calculate MRP-adjusted alignment scores
            mrp_results = self._calculate_mrp_alignment(
                user_with_demographics["demographics"],
                user_with_demographics["responses"]
            )
            
            # 6. Prepare results
            results = {
                "survey_questions": survey_questions,
                "sample_user": {
                    "responses": user_responses
                },
                "alignment_results": alignment_results[:3],  # Top 3 matches
                "sample_user_with_demographics": user_with_demographics,
                "mrp_results": mrp_results[:3]  # Top 3 matches
            }
            
            return results
        except Exception as e:
            logger.error(f"Error running demo: {e}")
            raise
            
    def _get_survey_questions(self):
        """
        Get survey questions from database
        
        Returns:
            list: List of question dictionaries
        """
        cursor = self.conn.cursor()
        
        # Get policy areas
        cursor.execute("SELECT id, name FROM policy_areas WHERE active = 1")
        policy_areas = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Get questions for each policy area
        questions = []
        for policy_id, policy_name in policy_areas.items():
            cursor.execute("""
            SELECT id, question_text, source
            FROM questions
            WHERE active = 1 AND policy_area_id = ?
            """, (policy_id,))
            
            policy_questions = []
            for q_row in cursor.fetchall():
                question_id, question_text, source = q_row
                
                # Get response options for this question
                cursor.execute("""
                SELECT id, option_text, score
                FROM response_options
                WHERE question_id = ?
                ORDER BY id
                """, (question_id,))
                
                options = [
                    {"id": row[0], "text": row[1], "score": row[2]}
                    for row in cursor.fetchall()
                ]
                
                policy_questions.append({
                    "id": question_id,
                    "text": question_text,
                    "source": source,
                    "options": options
                })
            
            questions.append({
                "policy_area": policy_name,
                "policy_id": policy_id,
                "questions": policy_questions
            })
            
        return questions
        
    def _generate_sample_responses(self, survey_questions):
        """
        Generate sample user responses
        
        Args:
            survey_questions (list): List of question dictionaries
            
        Returns:
            list: List of response dictionaries
        """
        # Generate responses with a liberal leaning
        responses = []
        
        for policy_area in survey_questions:
            for question in policy_area["questions"]:
                # Find option with score -2 (moderate liberal) or closest to it
                closest_option = None
                closest_distance = float('inf')
                
                for option in question["options"]:
                    distance = abs(option["score"] - (-2))
                    if distance < closest_distance:
                        closest_distance = distance
                        closest_option = option
                
                if closest_option:
                    responses.append({
                        "question_id": question["id"],
                        "score": closest_option["score"],
                        "importance": 3  # High importance
                    })
                    
        return responses
        
    def _calculate_alignment(self, user_responses):
        """
        Calculate alignment scores
        
        Args:
            user_responses (list): List of user response dictionaries
            
        Returns:
            list: List of representative dictionaries with alignment scores
        """
        return self.scoring_system.calculate_all_alignments(
            user_responses, method='weighted'
        )
        
    def _generate_sample_user_with_demographics(self):
        """
        Generate sample user with demographics
        
        Returns:
            dict: User information with demographics and responses
        """
        # Get survey questions
        survey_questions = self._get_survey_questions()
        
        # Generate responses with a moderate conservative leaning
        responses = []
        
        for policy_area in survey_questions:
            for question in policy_area["questions"]:
                # Find option with score 1 (slight conservative) or closest to it
                closest_option = None
                closest_distance = float('inf')
                
                for option in question["options"]:
                    distance = abs(option["score"] - 1)
                    if distance < closest_distance:
                        closest_distance = distance
                        closest_option = option
                
                if closest_option:
                    responses.append({
                        "question_id": question["id"],
                        "score": closest_option["score"],
                        "importance": 2  # Medium importance
                    })
        
        # Create user with demographics
        user = {
            "demographics": {
                "age_group": "45-64",
                "education": "Some College",
                "gender": "Male",
                "race": "White",
                "state": "TX",
                "urban_rural": "Suburban"
            },
            "responses": responses
        }
        
        return user
        
    def _calculate_mrp_alignment(self, user_demographics, user_responses):
        """
        Calculate MRP-adjusted alignment scores
        
        Args:
            user_demographics (dict): User demographic information
            user_responses (list): List of user response dictionaries
            
        Returns:
            list: List of representative dictionaries with alignment scores
        """
        return self.scoring_system.calculate_mrp_adjusted_alignments(
            user_demographics, user_responses
        )
        
    def export_results(self, results, output_file):
        """
        Export results to a JSON file
        
        Args:
            results (dict): Results dictionary
            output_file (str): Output file path
        """
        try:
            # Convert any non-serializable objects
            serializable_results = results.copy()
            
            # Handle alignment scores
            if "alignment_results" in serializable_results:
                alignment_results = []
                for rep in serializable_results["alignment_results"]:
                    # Convert policy area scores dict to a list for better readability
                    policy_scores = []
                    for policy_name, data in rep["policy_area_scores"].items():
                        policy_scores.append({
                            "policy_area": policy_name,
                            "score": data["score"],
                            "question_count": data.get("question_count", 0)
                        })
                    
                    serializable_rep = {
                        "id": rep["id"],
                        "name": f"{rep['first_name']} {rep['last_name']}",
                        "state": rep["state"],
                        "party": rep["party"],
                        "alignment_score": rep["alignment_score"],
                        "policy_area_scores": policy_scores
                    }
                    
                    alignment_results.append(serializable_rep)
                    
                serializable_results["alignment_results"] = alignment_results
                
            # Handle MRP results
            if "mrp_results" in serializable_results:
                mrp_results = []
                for rep in serializable_results["mrp_results"]:
                    # Convert policy area scores dict to a list for better readability
                    policy_scores = []
                    for policy_name, data in rep["policy_area_scores"].items():
                        policy_scores.append({
                            "policy_area": policy_name,
                            "score": data["score"],
                            "question_count": data.get("question_count", 0)
                        })
                    
                    serializable_rep = {
                        "id": rep["id"],
                        "name": f"{rep['first_name']} {rep['last_name']}",
                        "state": rep["state"],
                        "party": rep["party"],
                        "alignment_score": rep["alignment_score"],
                        "policy_area_scores": policy_scores
                    }
                    
                    mrp_results.append(serializable_rep)
                    
                serializable_results["mrp_results"] = mrp_results
            
            # Write to file
            with open(output_file, 'w') as f:
                json.dump(serializable_results, f, indent=2)
                
            logger.info(f"Results exported to {output_file}")
        except Exception as e:
            logger.error(f"Error exporting results: {e}")
            raise
            
    def close_connections(self):
        """Close all database connections"""
        if self.conn:
            self.conn.close()
            
        self.congress_scraper.close_connection()
        self.rvoteview_scraper.close_connection()
        self.scoring_system.close_connection()
        
        logger.info("All connections closed")

# Example usage
if __name__ == "__main__":
    # Create the POC
    poc = PoliticalAlignmentPOC()
    
    # Initialize the database
    poc.initialize_database()
    
    # Run the demo
    results = poc.run_demo()
    
    # Export results
    poc.export_results(results, "poc_results.json")
    
    # Print summary
    print("\nPOC Demo Results:")
    print(f"Survey questions: {sum(len(pa['questions']) for pa in results['survey_questions'])} questions across {len(results['survey_questions'])} policy areas")
    
    print("\nTop alignment matches:")
    for i, rep in enumerate(results["alignment_results"]):
        print(f"{i+1}. {rep['name']} ({rep['party']}-{rep['state']}): {rep['alignment_score']:.2f}")
        
    print("\nTop MRP-adjusted matches:")
    for i, rep in enumerate(results["mrp_results"]):
        print(f"{i+1}. {rep['name']} ({rep['party']}-{rep['state']}): {rep['alignment_score']:.2f}")
    
    # Close connections
    poc.close_connections()
    
    print("\nPOC demo completed. Results saved to poc_results.json")
