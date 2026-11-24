import os
import sqlite3
import logging
import pandas as pd
import json

from datetime import datetime

# Import our modules
from congress_scraper import CongressDataScraper
from rvoteview_scraper import RvoteviewScraper
from alignment_scoring import AlignmentScoring

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("political_alignment_app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("political_alignment_app")

class PoliticalAlignmentApp:
    """
    Main application class for the Political Alignment Tool
    
    This class integrates all components of the system and provides
    a simple interface for running the application.
    """
    
    def __init__(self, db_path="political_alignment.db", voteview_metadata_path=None, auto_update_metadata=False):
        """
        Initialize the application with database path
        
        Args:
            db_path (str): Path to SQLite database
            voteview_metadata_path (str, optional): Path to Rvoteview metadata CSV file
            auto_update_metadata (bool, optional): Whether to auto-update metadata if older than 30 days
        """
        self.db_path = db_path
        self.conn = None
        
        # Initialize components
        self.congress_scraper = CongressDataScraper(
            db_path=db_path,
            api_key=os.environ.get("CONGRESS_API_KEY")
        )
        
        self.rvoteview_scraper = RvoteviewScraper(
            db_path=db_path, 
            metadata_path=voteview_metadata_path,
            auto_update=auto_update_metadata
        )
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
            (1, "Immigration", "Immigration policy and border security", 1),
            (2, "Vaccination", "Vaccination policy and public health", 1),
            (3, "Abortion", "Abortion rights and reproductive health", 1)
        ]
        
        cursor.executemany("""
        INSERT OR REPLACE INTO policy_areas (id, name, description, active)
        VALUES (?, ?, ?, ?)
        """, policy_areas)
        
        # Add sample questions from the GSS surveys
        questions = [
            # Immigration questions
            (1, 1, "Do you think the number of immigrants to America nowadays should be increased, remain the same, or reduced?", "GSS2022 LETIN1A", 1),
            (2, 1, "Do you think the number of immigrants from Latin America who are permitted to come to the United States to live should be increased, decreased, or left the same?", "GSS2022 LETINHSP1", 1),
            (3, 1, "Do you think the number of immigrants from Asia who are permitted to come to the United States to live should be increased, decreased, or left the same?", "GSS2022 LETINASN1", 1),
            (4, 1, "Do you think immigrants living in the U.S. should adopt U.S. culture, keep their own culture, or do both?", "GSS2020 ADOPTUS", 1),
            (5, 1, "What should be done about immigrants who are currently living in the U.S. illegally?", "GSS2022 IMMFATE", 1),
            
            # Vaccination questions
            (6, 2, "It is better to develop immunity by getting ill than having a vaccination.", "GSS2022 IMMUNBETR", 1),
            (7, 2, "Overall, vaccinations do more harm than good.", "GSS2022 VAXDOHARM", 1),
            (8, 2, "During the past 12 months, how often have you used the internet to look for information on vaccinations?", "GSS2022 HLTHWBVAX", 1),
            (9, 2, "Parents should be able to refuse to vaccinate their children against measles, mumps, and rubella.", "GSS2022 VAXHSTNCY", 1),
            (10, 2, "Vaccines are important for children to have.", "GSS2022 VAXKIDS", 1),
            (11, 2, "Vaccines are safe.", "GSS2022 VAXSAFE", 1),
            
            # Abortion questions
            (12, 3, "Which of the following best represents your beliefs about abortion?", "GSS2022 ABBELIEF", 1),
            (13, 3, "Should it be possible for a pregnant woman to obtain a legal abortion if she is beyond 4.5 months, that is, about halfway through the pregnancy?", "GSS2022 GESTATE", 1),
            (14, 3, "Should it be possible for a pregnant woman to obtain a legal abortion if there is a strong chance of serious defect in the baby?", "GS2022 ABDEFECT", 1),
            (15, 3, "Should it be possible for a pregnant woman to obtain a legal abortion if she is pregnant with a boy but wants a girl, or is pregnant with a girl but wants a boy?", "GSS2022 ABGENDER", 1),
            (16, 3, "Should it be possible for a pregnant woman to obtain a legal abortion if she is married and does not want any more children?", "GSS2022 ABNOMORE", 1),
            (17, 3, "Should it be possible for a pregnant woman to obtain a legal abortion if the woman's own health is seriously endangered by the pregnancy?", "GSS2022 ABHLTH", 1),
            (18, 3, "Should it be possible for a pregnant woman to obtain a legal abortion if the family has a very low income and cannot afford any more children?", "GSS2022 ABPOOR", 1),
            (19, 3, "Should it be possible for a pregnant woman to obtain a legal abortion if she becomes pregnant as a result of rape?", "GSS2022 ABRAPE", 1),
            (20, 3, "Should it be possible for a pregnant woman to obtain a legal abortion if she is not married and does not want to marry the man?", "GSS2022 ABSINGLE", 1),
            (21, 3, "Should it be possible for a pregnant woman to obtain a legal abortion if the woman wants it for any reason?", "GSS2022 ABANY", 1)
        ]
        
        cursor.executemany("""
        INSERT OR REPLACE INTO questions (id, policy_area_id, question_text, source, active)
        VALUES (?, ?, ?, ?, ?)
        """, questions)
        
        # Add response options
        response_options = [
            # Immigration Q1
            (1, 1, "Increased", -3),
            (2, 1, "Increased a little", -2),
            (3, 1, "Remain the same as it is", 0),
            (4, 1, "Reduced a little", 2),
            (5, 1, "Reduced a lot", 3),
            
            # Immigration Q2
            (6, 2, "Increased", -3),
            (7, 2, "Decreased", 3),
            (8, 2, "Left the same", 0),
            
            # Immigration Q3
            (9, 3, "Increased", -3),
            (10, 3, "Decreased", 3),
            (11, 3, "Left the same", 0),
            
            # Immigration Q4
            (12, 4, "Adopt U.S. culture", 1),
            (13, 4, "Keep their own culture", -1),
            (14, 4, "Do both", 0),
            
            # Immigration Q5
            (15, 5, "Become citizens", -3),
            (16, 5, "Become permanent legal residents", -1),
            (17, 5, "Identified and deported", 3),
            
            # Vaccination Q1
            (18, 6, "Strongly agree", 3),
            (19, 6, "Agree", 2),
            (20, 6, "Neither agree nor disagree", 0),
            (21, 6, "Disagree", -2),
            (22, 6, "Strongly disagree", -3),
            
            # Vaccination Q2
            (23, 7, "Strongly agree", 3),
            (24, 7, "Agree", 2),
            (25, 7, "Neither agree nor disagree", 0),
            (26, 7, "Disagree", -2),
            (27, 7, "Strongly disagree", -3),
            
            # Vaccination Q3
            (28, 8, "Never", 0),
            (29, 8, "Seldom", 0),
            (30, 8, "Sometimes", 1),
            (31, 8, "Often", 2),
            (32, 8, "Very often", 3),
            
            # Vaccination Q4
            (33, 9, "Strongly agree", 3),
            (34, 9, "Agree", 2),
            (35, 9, "Neither agree nor disagree", 0),
            (36, 9, "Disagree", -2),
            (37, 9, "Strongly disagree", -3),
            
            # Vaccination Q5
            (38, 10, "Strongly agree", -3),
            (39, 10, "Agree", -2),
            (40, 10, "Neither agree nor disagree", 0),
            (41, 10, "Disagree", 2),
            (42, 10, "Strongly disagree", 3),
            
            # Vaccination Q6
            (43, 11, "Strongly agree", -3),
            (44, 11, "Agree", -2),
            (45, 11, "Neither agree nor disagree", 0),
            (46, 11, "Disagree", 2),
            (47, 11, "Strongly disagree", 3),
            
            # Abortion Q1
            (48, 12, "Strongly pro-choice", -3),
            (49, 12, "Slightly pro-choice", -1),
            (50, 12, "Both pro-choice and pro-life", 0),
            (51, 12, "Neither pro-choice nor pro-life", 0),
            (52, 12, "Slightly pro-life", 1),
            (53, 12, "Strongly pro-life", 3),
            
            # Abortion Q2-Q10
            (54, 13, "Yes", -3),
            (55, 13, "No", 3),
            (56, 14, "Yes", -3),
            (57, 14, "No", 3),
            (58, 15, "Yes", -3),
            (59, 15, "No", 3),
            (60, 16, "Yes", -3),
            (61, 16, "No", 3),
            (62, 17, "Yes", -3),
            (63, 17, "No", 3),
            (64, 18, "Yes", -3),
            (65, 18, "No", 3),
            (66, 19, "Yes", -3),
            (67, 19, "No", 3),
            (68, 20, "Yes", -3),
            (69, 20, "No", 3),
            (70, 21, "Yes", -3),
            (71, 21, "No", 3)
        ]
        
        cursor.executemany("""
        INSERT OR REPLACE INTO response_options (id, question_id, option_text, score)
        VALUES (?, ?, ?, ?)
        """, response_options)
        
        self.conn.commit()
        logger.info("Sample data initialization complete")
        
    def collect_data(self, limit_representatives=None, limit_bills=None):
        """
        Collect data from Congress.gov API and Rvoteview
        
        Args:
            limit_representatives (int, optional): Limit number of representatives to process
            limit_bills (int, optional): Limit number of bills to process
            
        Returns:
            dict: Summary of collection results
        """
        results = {
            "representatives_collected": 0,
            "votes_collected": 0,
            "positions_inferred": 0,
            "bill_mappings_created": 0
        }
        
        try:
            # 1. Fetch representatives from Congress.gov
            logger.info("Fetching representatives from Congress.gov API...")
            members = self.congress_scraper.fetch_current_members()
            
            # Limit the number of representatives if specified
            if limit_representatives:
                members = members[:limit_representatives]
                
            # 2. Save representatives to database
            results["representatives_collected"] = self.congress_scraper.save_members_to_db(members)
            
            # 3. Update with Voteview IDs
            logger.info("Updating representatives with Voteview IDs...")
            members_df = self.rvoteview_scraper.fetch_voteview_members()
            self.rvoteview_scraper.update_representatives_with_voteview_data(members_df)
            
            # 4. For each representative, collect votes and infer positions
            cursor = self.conn.cursor()
            if limit_representatives:
                cursor.execute("SELECT id, bioguide_id FROM representatives LIMIT ?", (limit_representatives,))
            else:
                cursor.execute("SELECT id, bioguide_id FROM representatives")
                
            representatives = cursor.fetchall()
            
            for rep_id, bioguide_id in representatives:
                # Fetch and save votes from Congress.gov
                logger.info(f"Collecting votes for representative {bioguide_id}...")
                votes = self.congress_scraper.fetch_member_votes(bioguide_id)
                vote_count = self.congress_scraper.save_votes_to_db(bioguide_id, votes)
                results["votes_collected"] += vote_count
                
                # Infer positions from votes
                logger.info(f"Inferring positions for representative {bioguide_id}...")
                positions = self.congress_scraper.infer_positions_from_votes(rep_id)
                position_count = self.congress_scraper.save_positions_to_db(positions)
                results["positions_inferred"] += position_count
                
            # 5. Process bills for mapping
            logger.info("Processing bills for question mapping...")
            
            # Get policy areas
            cursor.execute("SELECT name FROM policy_areas WHERE active = 1")
            policy_areas = [row[0] for row in cursor.fetchall()]
            
            # Get questions for mapping
            cursor.execute("""
            SELECT q.id, q.question_text, pa.name as policy_area_name
            FROM questions q
            JOIN policy_areas pa ON q.policy_area_id = pa.id
            WHERE q.active = 1
            """)
            
            questions = [
                {"id": row[0], "question_text": row[1], "policy_area_name": row[2]}
                for row in cursor.fetchall()
            ]
            
            # Get a sample of recent bills
            if limit_bills:
                cursor.execute("""
                SELECT DISTINCT congress_number, bill_number
                FROM voting_records
                ORDER BY vote_date DESC
                LIMIT ?
                """, (limit_bills,))
            else:
                cursor.execute("""
                SELECT DISTINCT congress_number, bill_number
                FROM voting_records
                ORDER BY vote_date DESC
                LIMIT 20
                """)
                
            bills = cursor.fetchall()
            
            # Process each bill
            for congress, bill_number in bills:
                logger.info(f"Processing bill {bill_number} from congress {congress}...")
                
                # Fetch bill details
                bill_details = self.congress_scraper.fetch_bill_details(congress, bill_number)
                
                # Map bill to questions
                mappings = self.congress_scraper.map_bill_to_questions(
                    congress, bill_number, bill_details, questions
                )
                
                # Save mappings
                mapping_count = self.congress_scraper.save_bill_mappings_to_db(mappings)
                results["bill_mappings_created"] += mapping_count
                
            # 6. Collect additional data from Rvoteview
            logger.info("Collecting additional data from Rvoteview...")
            rvoteview_results = self.rvoteview_scraper.run_voteview_update(
                policy_areas=policy_areas
            )
            
            # Update results with Rvoteview data
            results["votes_collected"] += rvoteview_results.get("votes_collected", 0)
            results["bill_mappings_created"] += rvoteview_results.get("bill_mappings_created", 0)
            
            logger.info("Data collection complete")
            return results
        except Exception as e:
            logger.error(f"Error collecting data: {e}")
            raise
            
    def get_questions_for_survey(self, policy_area=None):
        """
        Get questions and response options for a survey
        
        Args:
            policy_area (str, optional): Filter questions by policy area
            
        Returns:
            list: List of question dictionaries with response options
        """
        try:
            cursor = self.conn.cursor()
            
            # Get policy areas
            if policy_area:
                cursor.execute("""
                SELECT id, name FROM policy_areas 
                WHERE active = 1 AND name = ?
                """, (policy_area,))
            else:
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
        except Exception as e:
            logger.error(f"Error getting survey questions: {e}")
            raise
            
    def process_user_survey(self, user_responses, user_demographics=None):
        """
        Process user survey responses and calculate alignment with representatives
        
        Args:
            user_responses (list): List of user response dictionaries
                Each dict should have: question_id, score, importance (optional)
            user_demographics (dict, optional): User demographic information
                
        Returns:
            dict: Dictionary with alignment results
        """
        try:
            # Calculate alignment scores
            if user_demographics:
                logger.info("Calculating MRP-adjusted alignment scores...")
                alignment_results = self.scoring_system.calculate_mrp_adjusted_alignments(
                    user_demographics, user_responses
                )
            else:
                logger.info("Calculating alignment scores...")
                alignment_results = self.scoring_system.calculate_all_alignments(
                    user_responses, method='weighted'
                )
            
            # Get policy areas for context
            cursor = self.conn.cursor()
            cursor.execute("SELECT id, name FROM policy_areas WHERE active = 1")
            policy_areas = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Format results
            formatted_results = {
                "timestamp": datetime.now().isoformat(),
                "total_representatives": len(alignment_results),
                "top_matches": alignment_results[:10],  # Top 10 matches
                "policy_areas": list(policy_areas.values())
            }
            
            return formatted_results
        except Exception as e:
            logger.error(f"Error processing user survey: {e}")
            raise
            
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
            if "top_matches" in serializable_results:
                top_matches = []
                for rep in serializable_results["top_matches"]:
                    # Convert policy area scores dict to a list for better readability
                    policy_scores = []
                    for policy_name, data in rep["policy_area_scores"].items():
                        policy_scores.append({
                            "policy_area": policy_name,
                            "score": data["score"],
                            "question_count": data["question_count"]
                        })
                    
                    serializable_rep = {
                        "id": rep["id"],
                        "name": f"{rep['first_name']} {rep['last_name']}",
                        "state": rep["state"],
                        "district": rep["district"],
                        "chamber": rep["chamber"],
                        "party": rep["party"],
                        "alignment_score": rep["alignment_score"],
                        "policy_area_scores": policy_scores
                    }
                    
                    top_matches.append(serializable_rep)
                    
                serializable_results["top_matches"] = top_matches
            
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
    # Check for Voteview members file - use HSall_members.csv for member data
    default_metadata_path = "HSall_members.csv"
    metadata_path = default_metadata_path  # Always use this path, auto-update will create if missing
    
    # Parse command-line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Political Alignment Tool')
    parser.add_argument('--force-update', action='store_true', help='Force update of Rvoteview metadata')
    parser.add_argument('--auto-update', action='store_true', help='Auto-update metadata if older than 30 days')
    args = parser.parse_args()
    
    # Handle metadata
    if args.force_update:
        print("Forcing update of Rvoteview metadata...")
        # Create a temporary scraper just to update metadata
        temp_scraper = RvoteviewScraper(db_path="political_alignment.db", metadata_path=metadata_path)
        temp_scraper.update_metadata()
    
    print(f"Using Rvoteview metadata path: {metadata_path}")
    if not os.path.exists(metadata_path):
        print("Metadata file not found. It will be downloaded automatically if auto-update is enabled.")
    
    # Create the application with metadata and auto-update if specified
    app = PoliticalAlignmentApp(
        voteview_metadata_path=metadata_path,
        auto_update_metadata=args.auto_update
    )
    
    # Initialize the database
    app.initialize_database()
    
    # Collect data (limited for demonstration)
    collection_results = app.collect_data(limit_representatives=5, limit_bills=3)
    print(f"Data collection results: {collection_results}")
    
    # Get survey questions
    survey_questions = app.get_questions_for_survey()
    print(f"Retrieved {sum(len(pa['questions']) for pa in survey_questions)} questions across {len(survey_questions)} policy areas")
    
    # Generate sample user responses
    user_responses = []
    for policy_area in survey_questions:
        for question in policy_area["questions"]:
            # Pick the first option for demonstration
            if question["options"]:
                user_responses.append({
                    "question_id": question["id"],
                    "score": question["options"][0]["score"],
                    "importance": 3  # Medium importance
                })
    
    # Sample user demographics
    user_demographics = {
        "age_group": "30-44",
        "education": "College",
        "gender": "Female",
        "race": "White",
        "state": "TX",
        "urban_rural": "Urban"
    }
    
    # Process survey
    alignment_results = app.process_user_survey(user_responses, user_demographics)
    
    # Export results
    app.export_results(alignment_results, "alignment_results.json")
    
    # Close connections
    app.close_connections()
    
    print("Application demo completed. Results saved to alignment_results.json")
