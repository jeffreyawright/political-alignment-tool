import os
import sqlite3
import logging
import pandas as pd
import numpy as np
from scipy.spatial.distance import cosine
from sklearn.preprocessing import StandardScaler
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("alignment_scoring.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("alignment_scoring")

class AlignmentScoring:
    """
    Scoring system for calculating alignment between users and representatives
    
    This class handles calculating alignment scores based on various methods,
    including weighted scoring, cosine similarity, and MRP-adjusted scoring.
    """
    
    def __init__(self, db_path):
        """
        Initialize the scoring system with database path
        
        Args:
            db_path (str): Path to SQLite database
        """
        self.db_path = db_path
        self.conn = self._create_db_connection()
            
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
            
    def calculate_all_alignments(self, user_responses, method='weighted'):
        """
        Calculate alignment scores for all representatives
        
        Args:
            user_responses (list): List of user response dictionaries
                Each dict should have: question_id, score, importance (optional)
            method (str): Scoring method ('weighted', 'cosine', 'euclidean')
            
        Returns:
            list: List of representative dictionaries with alignment scores
        """
        try:
            # Get all representatives
            cursor = self.conn.cursor()
            cursor.execute("""
            SELECT id, first_name, last_name, state, district, party, chamber
            FROM representatives
            """)
            
            representatives = [
                {
                    "id": row[0],
                    "first_name": row[1],
                    "last_name": row[2],
                    "state": row[3],
                    "district": row[4],
                    "party": row[5],
                    "chamber": row[6]
                }
                for row in cursor.fetchall()
            ]
            
            # Get policy areas
            cursor.execute("""
            SELECT id, name
            FROM policy_areas
            WHERE active = 1
            """)
            
            policy_areas = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Get questions
            cursor.execute("""
            SELECT id, policy_area_id
            FROM questions
            WHERE active = 1
            """)
            
            questions = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Calculate alignment for each representative
            for rep in representatives:
                rep_id = rep["id"]
                
                # Get representative positions
                cursor.execute("""
                SELECT question_id, score, confidence
                FROM representative_positions
                WHERE representative_id = ?
                """, (rep_id,))
                
                rep_positions = {
                    row[0]: {"score": row[1], "confidence": row[2]}
                    for row in cursor.fetchall()
                }
                
                # Calculate alignment score based on method
                if method == 'cosine':
                    alignment_score, policy_scores = self._calculate_cosine_alignment(
                        user_responses, rep_positions, questions, policy_areas
                    )
                elif method == 'euclidean':
                    alignment_score, policy_scores = self._calculate_euclidean_alignment(
                        user_responses, rep_positions, questions, policy_areas
                    )
                else:  # Default to weighted
                    alignment_score, policy_scores = self._calculate_weighted_alignment(
                        user_responses, rep_positions, questions, policy_areas
                    )
                    
                rep["alignment_score"] = alignment_score
                rep["policy_area_scores"] = policy_scores
            
            # Sort by alignment score (higher is better match)
            representatives.sort(key=lambda x: x["alignment_score"], reverse=True)
            
            return representatives
        except Exception as e:
            logger.error(f"Error calculating alignments: {e}")
            raise
            
    def _calculate_weighted_alignment(self, user_responses, rep_positions, questions, policy_areas):
        """
        Calculate alignment using weighted average
        
        Args:
            user_responses (list): List of user response dictionaries
            rep_positions (dict): Dictionary of representative positions
            questions (dict): Dictionary of question IDs to policy area IDs
            policy_areas (dict): Dictionary of policy area IDs to names
            
        Returns:
            tuple: (overall_score, policy_scores)
        """
        # Initialize scores
        total_score = 0
        total_weight = 0
        policy_scores = {}
        
        # Initialize policy area scores
        for policy_id, policy_name in policy_areas.items():
            policy_scores[policy_name] = {
                "score": 0,
                "total_weight": 0,
                "question_count": 0
            }
        
        # Calculate scores for each question
        for response in user_responses:
            question_id = response.get("question_id")
            user_score = response.get("score")
            importance = response.get("importance", 1)  # Default importance is 1
            
            # Skip if no question ID or score
            if question_id is None or user_score is None:
                continue
                
            # Get representative position
            rep_position = rep_positions.get(question_id)
            
            # Skip if representative has no position
            if not rep_position:
                continue
                
            rep_score = rep_position.get("score")
            confidence = rep_position.get("confidence", 0.5)  # Default confidence is 0.5
            
            # Calculate question weight
            weight = importance * confidence
            
            # Calculate score difference (inverted so higher is better match)
            score_diff = 1 - (abs(user_score - rep_score) / 6)  # Scale from -3 to 3 (range of 6)
            
            # Update overall score
            total_score += score_diff * weight
            total_weight += weight
            
            # Update policy area score
            policy_id = questions.get(question_id)
            if policy_id:
                policy_name = policy_areas.get(policy_id)
                if policy_name:
                    policy_scores[policy_name]["score"] += score_diff * weight
                    policy_scores[policy_name]["total_weight"] += weight
                    policy_scores[policy_name]["question_count"] += 1
        
        # Calculate overall alignment score
        overall_score = total_score / total_weight if total_weight > 0 else 0
        
        # Calculate policy area scores
        for policy_name, data in policy_scores.items():
            if data["total_weight"] > 0:
                data["score"] = data["score"] / data["total_weight"]
            else:
                data["score"] = 0
                
        return overall_score, policy_scores
        
    def _calculate_cosine_alignment(self, user_responses, rep_positions, questions, policy_areas):
        """
        Calculate alignment using cosine similarity
        
        Args:
            user_responses (list): List of user response dictionaries
            rep_positions (dict): Dictionary of representative positions
            questions (dict): Dictionary of question IDs to policy area IDs
            policy_areas (dict): Dictionary of policy area IDs to names
            
        Returns:
            tuple: (overall_score, policy_scores)
        """
        # Get all question IDs
        all_question_ids = set(questions.keys())
        
        # Create user vector
        user_vector = {}
        for response in user_responses:
            question_id = response.get("question_id")
            user_score = response.get("score")
            
            if question_id is not None and user_score is not None:
                user_vector[question_id] = user_score
                
        # Create representative vector
        rep_vector = {}
        for question_id, position in rep_positions.items():
            rep_vector[question_id] = position.get("score")
            
        # Get common questions
        common_questions = set(user_vector.keys()) & set(rep_vector.keys())
        
        # Initialize policy area scores
        policy_scores = {}
        for policy_id, policy_name in policy_areas.items():
            policy_scores[policy_name] = {
                "score": 0,
                "question_count": 0
            }
            
        # Calculate overall cosine similarity
        if common_questions:
            # Create aligned vectors
            user_aligned = [user_vector[q] for q in common_questions]
            rep_aligned = [rep_vector[q] for q in common_questions]
            
            # Calculate cosine similarity
            similarity = 1 - cosine(user_aligned, rep_aligned)
            
            # Calculate policy area similarities
            for policy_id, policy_name in policy_areas.items():
                # Get questions for this policy area
                policy_questions = [q for q in common_questions if questions.get(q) == policy_id]
                
                if policy_questions:
                    # Create aligned vectors for this policy area
                    user_policy = [user_vector[q] for q in policy_questions]
                    rep_policy = [rep_vector[q] for q in policy_questions]
                    
                    # Calculate cosine similarity for this policy area
                    policy_similarity = 1 - cosine(user_policy, rep_policy)
                    
                    policy_scores[policy_name]["score"] = policy_similarity
                    policy_scores[policy_name]["question_count"] = len(policy_questions)
        else:
            similarity = 0
            
        return similarity, policy_scores
        
    def _calculate_euclidean_alignment(self, user_responses, rep_positions, questions, policy_areas):
        """
        Calculate alignment using Euclidean distance
        
        Args:
            user_responses (list): List of user response dictionaries
            rep_positions (dict): Dictionary of representative positions
            questions (dict): Dictionary of question IDs to policy area IDs
            policy_areas (dict): Dictionary of policy area IDs to names
            
        Returns:
            tuple: (overall_score, policy_scores)
        """
        # Get all question IDs
        all_question_ids = set(questions.keys())
        
        # Create user vector
        user_vector = {}
        for response in user_responses:
            question_id = response.get("question_id")
            user_score = response.get("score")
            
            if question_id is not None and user_score is not None:
                user_vector[question_id] = user_score
                
        # Create representative vector
        rep_vector = {}
        for question_id, position in rep_positions.items():
            rep_vector[question_id] = position.get("score")
            
        # Get common questions
        common_questions = set(user_vector.keys()) & set(rep_vector.keys())
        
        # Initialize policy area scores
        policy_scores = {}
        for policy_id, policy_name in policy_areas.items():
            policy_scores[policy_name] = {
                "score": 0,
                "question_count": 0
            }
            
        # Calculate overall Euclidean distance
        if common_questions:
            # Create aligned vectors
            user_aligned = [user_vector[q] for q in common_questions]
            rep_aligned = [rep_vector[q] for q in common_questions]
            
            # Calculate Euclidean distance
            distance = np.sqrt(np.sum([(u - r) ** 2 for u, r in zip(user_aligned, rep_aligned)]))
            
            # Convert to similarity score (higher is better match)
            max_distance = np.sqrt(len(common_questions) * 36)  # Maximum possible distance (6^2 for each question)
            similarity = 1 - (distance / max_distance)
            
            # Calculate policy area similarities
            for policy_id, policy_name in policy_areas.items():
                # Get questions for this policy area
                policy_questions = [q for q in common_questions if questions.get(q) == policy_id]
                
                if policy_questions:
                    # Create aligned vectors for this policy area
                    user_policy = [user_vector[q] for q in policy_questions]
                    rep_policy = [rep_vector[q] for q in policy_questions]
                    
                    # Calculate Euclidean distance for this policy area
                    policy_distance = np.sqrt(np.sum([(u - r) ** 2 for u, r in zip(user_policy, rep_policy)]))
                    
                    # Convert to similarity score
                    policy_max_distance = np.sqrt(len(policy_questions) * 36)
                    policy_similarity = 1 - (policy_distance / policy_max_distance)
                    
                    policy_scores[policy_name]["score"] = policy_similarity
                    policy_scores[policy_name]["question_count"] = len(policy_questions)
        else:
            similarity = 0
            
        return similarity, policy_scores
        
    def calculate_mrp_adjusted_alignments(self, user_demographics, user_responses):
        """
        Calculate MRP-adjusted alignment scores
        
        Args:
            user_demographics (dict): User demographic information
            user_responses (list): List of user response dictionaries
            
        Returns:
            list: List of representative dictionaries with alignment scores
        """
        try:
            # Get base alignments
            representatives = self.calculate_all_alignments(user_responses, method='weighted')
            
            # Apply MRP adjustments
            for rep in representatives:
                # Get demographic factors
                demographic_factor = self._calculate_demographic_factor(user_demographics, rep)
                
                # Adjust alignment score
                rep["alignment_score"] = (rep["alignment_score"] + demographic_factor) / 2
                
                # Adjust policy area scores
                for policy_name, data in rep["policy_area_scores"].items():
                    policy_demographic_factor = self._calculate_policy_demographic_factor(
                        user_demographics, rep, policy_name
                    )
                    
                    data["score"] = (data["score"] + policy_demographic_factor) / 2
            
            # Re-sort by adjusted alignment score
            representatives.sort(key=lambda x: x["alignment_score"], reverse=True)
            
            return representatives
        except Exception as e:
            logger.error(f"Error calculating MRP-adjusted alignments: {e}")
            raise
            
    def _calculate_demographic_factor(self, user_demographics, representative):
        """
        Calculate demographic adjustment factor
        
        Args:
            user_demographics (dict): User demographic information
            representative (dict): Representative information
            
        Returns:
            float: Demographic adjustment factor
        """
        # Initialize factor
        factor = 0
        
        # Get user demographics
        age_group = user_demographics.get("age_group")
        education = user_demographics.get("education")
        gender = user_demographics.get("gender")
        race = user_demographics.get("race")
        state = user_demographics.get("state")
        urban_rural = user_demographics.get("urban_rural")
        
        # Apply state matching
        if state and representative.get("state") == state:
            factor += 0.1
            
        # Apply party-demographic correlations
        party = representative.get("party")
        
        if party == "D":
            # Democratic party correlations
            if age_group == "18-29":
                factor += 0.05
            elif age_group == "65+":
                factor -= 0.05
                
            if education == "College" or education == "Graduate":
                factor += 0.05
                
            if gender == "Female":
                factor += 0.05
                
            if race != "White":
                factor += 0.05
                
            if urban_rural == "Urban":
                factor += 0.05
            elif urban_rural == "Rural":
                factor -= 0.05
        elif party == "R":
            # Republican party correlations
            if age_group == "18-29":
                factor -= 0.05
            elif age_group == "65+":
                factor += 0.05
                
            if education == "High School" or education == "Some College":
                factor += 0.05
                
            if gender == "Male":
                factor += 0.05
                
            if race == "White":
                factor += 0.05
                
            if urban_rural == "Rural":
                factor += 0.05
            elif urban_rural == "Urban":
                factor -= 0.05
                
        # Ensure factor is within bounds
        factor = max(-0.2, min(0.2, factor))
        
        return factor
        
    def _calculate_policy_demographic_factor(self, user_demographics, representative, policy_name):
        """
        Calculate policy-specific demographic adjustment factor
        
        Args:
            user_demographics (dict): User demographic information
            representative (dict): Representative information
            policy_name (str): Policy area name
            
        Returns:
            float: Policy-specific demographic adjustment factor
        """
        # Initialize factor
        factor = 0
        
        # Get user demographics
        age_group = user_demographics.get("age_group")
        education = user_demographics.get("education")
        gender = user_demographics.get("gender")
        race = user_demographics.get("race")
        
        # Apply policy-specific demographic correlations
        party = representative.get("party")
        
        if policy_name == "Immigration":
            if party == "D":
                if education == "College" or education == "Graduate":
                    factor += 0.05
                if race != "White":
                    factor += 0.05
            elif party == "R":
                if education == "High School":
                    factor += 0.05
                if race == "White":
                    factor += 0.05
        elif policy_name == "Abortion":
            if party == "D":
                if gender == "Female":
                    factor += 0.05
                if age_group == "18-29" or age_group == "30-44":
                    factor += 0.05
            elif party == "R":
                if gender == "Male":
                    factor += 0.05
                if age_group == "65+":
                    factor += 0.05
        elif policy_name == "Gun Control":
            if party == "D":
                if gender == "Female":
                    factor += 0.05
                if race != "White":
                    factor += 0.05
            elif party == "R":
                if gender == "Male":
                    factor += 0.05
                if race == "White":
                    factor += 0.05
                    
        # Ensure factor is within bounds
        factor = max(-0.1, min(0.1, factor))
        
        return factor

# Example usage
if __name__ == "__main__":
    # Create scoring system
    scoring = AlignmentScoring(db_path="political_alignment.db")
    
    # Sample user responses
    user_responses = [
        {"question_id": 1, "score": -2, "importance": 3},
        {"question_id": 2, "score": -1, "importance": 2},
        {"question_id": 3, "score": 0, "importance": 1},
        {"question_id": 4, "score": 1, "importance": 2},
        {"question_id": 5, "score": 2, "importance": 3}
    ]
    
    # Calculate alignments
    alignments = scoring.calculate_all_alignments(user_responses, method='weighted')
    
    # Print top 5 matches
    for i, rep in enumerate(alignments[:5]):
        print(f"{i+1}. {rep['first_name']} {rep['last_name']} ({rep['party']}-{rep['state']}): {rep['alignment_score']:.2f}")
        
    # Sample user demographics
    user_demographics = {
        "age_group": "30-44",
        "education": "College",
        "gender": "Female",
        "race": "White",
        "state": "CA",
        "urban_rural": "Urban"
    }
    
    # Calculate MRP-adjusted alignments
    mrp_alignments = scoring.calculate_mrp_adjusted_alignments(user_demographics, user_responses)
    
    # Print top 5 MRP-adjusted matches
    print("\nMRP-Adjusted Matches:")
    for i, rep in enumerate(mrp_alignments[:5]):
        print(f"{i+1}. {rep['first_name']} {rep['last_name']} ({rep['party']}-{rep['state']}): {rep['alignment_score']:.2f}")
        
    # Close connection
    scoring.close_connection()
