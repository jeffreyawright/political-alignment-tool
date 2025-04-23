import sqlite3
import logging
import sys
import os
import json
from datetime import datetime
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from tabulate import tabulate

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import components
from congress_scraper_enhanced import CongressScraperEnhanced
from public_statements_analyzer import PublicStatementsAnalyzer
from advocacy_ratings_collector import AdvocacyRatingsCollector
from position_estimation import PositionEstimationAlgorithm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("test_position_estimation.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("test_position_estimation")

class PositionEstimationTester:
    """
    Tester for the position estimation system
    
    This class tests the position estimation system with sample lawmakers
    and generates reports on the results.
    """
    
    def __init__(self, db_path):
        """
        Initialize the tester with database path
        
        Args:
            db_path (str): Path to SQLite database
        """
        self.db_path = db_path
        self.conn = self._create_db_connection()
        
        # Initialize components
        self.congress_scraper = CongressScraperEnhanced(db_path)
        self.statements_analyzer = PublicStatementsAnalyzer(db_path)
        self.ratings_collector = AdvocacyRatingsCollector(db_path)
        self.position_estimator = PositionEstimationAlgorithm(db_path)
        
        # Define test lawmakers
        self.test_lawmakers = [
            # Democrats
            {"bioguide_id": "S000148", "name": "Chuck Schumer", "party": "D", "chamber": "Senate"},
            {"bioguide_id": "W000187", "name": "Elizabeth Warren", "party": "D", "chamber": "Senate"},
            {"bioguide_id": "M001111", "name": "Joe Manchin", "party": "D", "chamber": "Senate"},
            
            # Republicans
            {"bioguide_id": "M000355", "name": "Mitch McConnell", "party": "R", "chamber": "Senate"},
            {"bioguide_id": "C001075", "name": "Ted Cruz", "party": "R", "chamber": "Senate"},
            {"bioguide_id": "M001153", "name": "Lisa Murkowski", "party": "R", "chamber": "Senate"},
            
            # House members
            {"bioguide_id": "P000197", "name": "Nancy Pelosi", "party": "D", "chamber": "House"},
            {"bioguide_id": "J000294", "name": "Jim Jordan", "party": "R", "chamber": "House"},
            {"bioguide_id": "O000172", "name": "Alexandria Ocasio-Cortez", "party": "D", "chamber": "House"},
            {"bioguide_id": "C001084", "name": "Liz Cheney", "party": "R", "chamber": "House"}
        ]
        
        # Define test questions
        self.test_questions = self._get_test_questions()
        
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
            
    def _get_test_questions(self):
        """
        Get test questions from database
        
        Returns:
            list: List of question dictionaries
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
            
            questions = []
            for row in cursor.fetchall():
                questions.append({
                    "id": row[0],
                    "text": row[1],
                    "policy_area": row[2]
                })
                
            return questions
        except Exception as e:
            logger.error(f"Error getting test questions: {e}")
            return []
            
    def _get_representative_id(self, bioguide_id):
        """
        Get representative ID from bioguide ID
        
        Args:
            bioguide_id (str): Bioguide ID
            
        Returns:
            int: Representative ID or None
        """
        try:
            cursor = self.conn.cursor()
            
            cursor.execute(
                "SELECT id FROM representatives WHERE bioguide_id = ?",
                (bioguide_id,)
            )
            
            row = cursor.fetchone()
            if row:
                return row[0]
                
            return None
        except Exception as e:
            logger.error(f"Error getting representative ID: {e}")
            return None
            
    def run_test(self):
        """
        Run test with sample lawmakers
        
        Returns:
            dict: Test results
        """
        try:
            results = {
                "lawmakers": [],
                "questions": self.test_questions,
                "summary": {}
            }
            
            # Process each lawmaker
            for lawmaker in self.test_lawmakers:
                logger.info(f"Testing position estimation for {lawmaker['name']}")
                
                # Get representative ID
                rep_id = self._get_representative_id(lawmaker["bioguide_id"])
                if not rep_id:
                    logger.warning(f"Representative not found for {lawmaker['name']}")
                    continue
                    
                # Collect data from all sources
                self._collect_lawmaker_data(lawmaker["bioguide_id"])
                
                # Estimate positions
                positions = self.position_estimator.estimate_positions(rep_id)
                
                # Save positions
                if positions:
                    self.position_estimator.save_positions_to_db(positions)
                    
                # Get integrated positions
                lawmaker_positions = self._get_lawmaker_positions(rep_id)
                
                # Add to results
                lawmaker_result = {
                    "bioguide_id": lawmaker["bioguide_id"],
                    "name": lawmaker["name"],
                    "party": lawmaker["party"],
                    "chamber": lawmaker["chamber"],
                    "positions": lawmaker_positions
                }
                
                results["lawmakers"].append(lawmaker_result)
                
            # Generate summary
            results["summary"] = self._generate_summary(results["lawmakers"])
            
            # Generate reports
            self._generate_reports(results)
            
            return results
        except Exception as e:
            logger.error(f"Error running test: {e}")
            raise
            
    def _collect_lawmaker_data(self, bioguide_id):
        """
        Collect data for a lawmaker from all sources
        
        Args:
            bioguide_id (str): Bioguide ID
        """
        try:
            # Collect voting records and bill sponsorships
            self.congress_scraper.collect_voting_records(bioguide_id)
            self.congress_scraper.collect_bill_sponsorships(bioguide_id)
            
            # Collect public statements
            statements = self.statements_analyzer.fetch_statements(bioguide_id, limit=20)
            if statements:
                self.statements_analyzer.save_statements_to_db(statements)
                
                # Get representative ID
                rep_id = self._get_representative_id(bioguide_id)
                if rep_id:
                    self.statements_analyzer.analyze_statements_for_positions(rep_id)
                    
            # Collect advocacy ratings
            ratings = self.ratings_collector.collect_ratings(bioguide_id)
            if ratings:
                self.ratings_collector.save_ratings_to_db(ratings)
                
                # Get representative ID
                rep_id = self._get_representative_id(bioguide_id)
                if rep_id:
                    positions = self.ratings_collector.infer_positions_from_ratings(rep_id)
                    if positions:
                        self.ratings_collector.save_positions_to_db(positions)
                        
        except Exception as e:
            logger.error(f"Error collecting data for {bioguide_id}: {e}")
            
    def _get_lawmaker_positions(self, rep_id):
        """
        Get integrated positions for a lawmaker
        
        Args:
            rep_id (int): Representative ID
            
        Returns:
            list: List of position dictionaries
        """
        try:
            cursor = self.conn.cursor()
            
            # Get integrated positions
            cursor.execute("""
            SELECT 
                ip.question_id, 
                ip.score, 
                ip.confidence,
                ip.voting_records_score,
                ip.voting_records_confidence,
                ip.bill_sponsorships_score,
                ip.bill_sponsorships_confidence,
                ip.public_statements_score,
                ip.public_statements_confidence,
                ip.advocacy_ratings_score,
                ip.advocacy_ratings_confidence
            FROM integrated_positions ip
            WHERE ip.representative_id = ?
            """, (rep_id,))
            
            positions = []
            for row in cursor.fetchall():
                position = {
                    "question_id": row[0],
                    "score": row[1],
                    "confidence": row[2],
                    "sources": {
                        "voting_records": {
                            "score": row[3],
                            "confidence": row[4]
                        },
                        "bill_sponsorships": {
                            "score": row[5],
                            "confidence": row[6]
                        },
                        "public_statements": {
                            "score": row[7],
                            "confidence": row[8]
                        },
                        "advocacy_ratings": {
                            "score": row[9],
                            "confidence": row[10]
                        }
                    }
                }
                
                positions.append(position)
                
            return positions
        except Exception as e:
            logger.error(f"Error getting lawmaker positions: {e}")
            return []
            
    def _generate_summary(self, lawmakers):
        """
        Generate summary of test results
        
        Args:
            lawmakers (list): List of lawmaker results
            
        Returns:
            dict: Summary statistics
        """
        try:
            # Calculate average positions by party
            dem_scores = []
            rep_scores = []
            
            for lawmaker in lawmakers:
                for position in lawmaker.get("positions", []):
                    if lawmaker["party"] == "D":
                        dem_scores.append(position["score"])
                    elif lawmaker["party"] == "R":
                        rep_scores.append(position["score"])
                        
            dem_avg = sum(dem_scores) / len(dem_scores) if dem_scores else 0
            rep_avg = sum(rep_scores) / len(rep_scores) if rep_scores else 0
            
            # Calculate source coverage
            source_counts = {
                "voting_records": 0,
                "bill_sponsorships": 0,
                "public_statements": 0,
                "advocacy_ratings": 0
            }
            
            total_positions = 0
            
            for lawmaker in lawmakers:
                for position in lawmaker.get("positions", []):
                    total_positions += 1
                    
                    for source, data in position.get("sources", {}).items():
                        if data.get("score") is not None:
                            source_counts[source] += 1
                            
            source_coverage = {
                source: count / total_positions if total_positions > 0 else 0
                for source, count in source_counts.items()
            }
            
            # Calculate confidence distribution
            confidence_levels = {
                "low": 0,
                "medium": 0,
                "high": 0
            }
            
            for lawmaker in lawmakers:
                for position in lawmaker.get("positions", []):
                    confidence = position.get("confidence", 0)
                    
                    if confidence < 0.3:
                        confidence_levels["low"] += 1
                    elif confidence < 0.7:
                        confidence_levels["medium"] += 1
                    else:
                        confidence_levels["high"] += 1
                        
            confidence_distribution = {
                level: count / total_positions if total_positions > 0 else 0
                for level, count in confidence_levels.items()
            }
            
            return {
                "party_averages": {
                    "Democratic": dem_avg,
                    "Republican": rep_avg
                },
                "source_coverage": source_coverage,
                "confidence_distribution": confidence_distribution,
                "total_positions": total_positions,
                "lawmakers_processed": len(lawmakers)
            }
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return {}
            
    def _generate_reports(self, results):
        """
        Generate reports from test results
        
        Args:
            results (dict): Test results
        """
        try:
            # Generate lawmaker report
            self._generate_lawmaker_report(results)
            
            # Generate question report
            self._generate_question_report(results)
            
            # Generate summary report
            self._generate_summary_report(results)
            
            # Generate visualizations
            self._generate_visualizations(results)
        except Exception as e:
            logger.error(f"Error generating reports: {e}")
            
    def _generate_lawmaker_report(self, results):
        """
        Generate report for each lawmaker
        
        Args:
            results (dict): Test results
        """
        try:
            # Create report directory
            os.makedirs("reports", exist_ok=True)
            
            # Create report for each lawmaker
            for lawmaker in results["lawmakers"]:
                report_path = f"reports/{lawmaker['bioguide_id']}_report.md"
                
                with open(report_path, "w") as f:
                    # Write header
                    f.write(f"# Position Estimation Report: {lawmaker['name']}\n\n")
                    f.write(f"**Party:** {lawmaker['party']}\n")
                    f.write(f"**Chamber:** {lawmaker['chamber']}\n\n")
                    
                    # Write positions
                    f.write("## Estimated Positions\n\n")
                    
                    # Create table
                    table_data = []
                    headers = ["Question", "Score", "Confidence", "Sources Used"]
                    
                    for position in lawmaker.get("positions", []):
                        # Get question text
                        question_text = "Unknown"
                        for question in results["questions"]:
                            if question["id"] == position["question_id"]:
                                question_text = question["text"]
                                break
                                
                        # Get sources used
                        sources_used = []
                        for source, data in position.get("sources", {}).items():
                            if data.get("score") is not None:
                                sources_used.append(source)
                                
                        # Add to table
                        table_data.append([
                            question_text,
                            position["score"],
                            f"{position['confidence']:.2f}",
                            ", ".join(sources_used)
                        ])
                        
                    # Write table
                    f.write(tabulate(table_data, headers=headers, tablefmt="pipe"))
                    f.write("\n\n")
                    
                    # Write source details
                    f.write("## Source Details\n\n")
                    
                    for position in lawmaker.get("positions", []):
                        # Get question text
                        question_text = "Unknown"
                        for question in results["questions"]:
                            if question["id"] == position["question_id"]:
                                question_text = question["text"]
                                break
                                
                        f.write(f"### {question_text}\n\n")
                        
                        # Create source table
                        source_data = []
                        source_headers = ["Source", "Score", "Confidence"]
                        
                        for source, data in position.get("sources", {}).items():
                            if data.get("score") is not None:
                                source_data.append([
                                    source.replace("_", " ").title(),
                                    data["score"],
                                    f"{data['confidence']:.2f}"
                                ])
                                
                        # Write source table
                        f.write(tabulate(source_data, headers=source_headers, tablefmt="pipe"))
                        f.write("\n\n")
                        
                    # Write score interpretation
                    f.write("## Score Interpretation\n\n")
                    f.write("* **-3**: Favor a great deal\n")
                    f.write("* **-2**: Favor a moderate amount\n")
                    f.write("* **-1**: Favor a little\n")
                    f.write("* **0**: Neither favor nor oppose\n")
                    f.write("* **1**: Oppose a little\n")
                    f.write("* **2**: Oppose a moderate amount\n")
                    f.write("* **3**: Oppose a great deal\n\n")
                    
                    # Write confidence interpretation
                    f.write("## Confidence Interpretation\n\n")
                    f.write("* **0.0-0.3**: Low confidence (limited data)\n")
                    f.write("* **0.3-0.7**: Medium confidence (moderate data)\n")
                    f.write("* **0.7-1.0**: High confidence (robust data)\n")
                    
            logger.info(f"Generated lawmaker reports in reports/ directory")
        except Exception as e:
            logger.error(f"Error generating lawmaker report: {e}")
            
    def _generate_question_report(self, results):
        """
        Generate report for each question
        
        Args:
            results (dict): Test results
        """
        try:
            # Create report directory
            os.makedirs("reports", exist_ok=True)
            
            # Create report for each question
            for question in results["questions"]:
                report_path = f"reports/question_{question['id']}_report.md"
                
                with open(report_path, "w") as f:
                    # Write header
                    f.write(f"# Question Analysis Report\n\n")
                    f.write(f"**Question:** {question['text']}\n")
                    f.write(f"**Policy Area:** {question['policy_area']}\n\n")
                    
                    # Write positions
                    f.write("## Lawmaker Positions\n\n")
                    
                    # Create table
                    table_data = []
                    headers = ["Lawmaker", "Party", "Score", "Confidence", "Sources Used"]
                    
                    for lawmaker in results["lawmakers"]:
                        # Find position for this question
                        position = None
                        for pos in lawmaker.get("positions", []):
                            if pos["question_id"] == question["id"]:
                                position = pos
                                break
                                
                        if not position:
                            continue
                            
                        # Get sources used
                        sources_used = []
                        for source, data in position.get("sources", {}).items():
                            if data.get("score") is not None:
                                sources_used.append(source)
                                
                        # Add to table
                        table_data.append([
                            lawmaker["name"],
                            lawmaker["party"],
                            position["score"],
                            f"{position['confidence']:.2f}",
                            ", ".join(sources_used)
                        ])
                        
                    # Sort by party then score
                    table_data.sort(key=lambda x: (x[1], x[2]))
                    
                    # Write table
                    f.write(tabulate(table_data, headers=headers, tablefmt="pipe"))
                    f.write("\n\n")
                    
                    # Calculate party averages
                    dem_scores = [row[2] for row in table_data if row[1] == "D"]
                    rep_scores = [row[2] for row in table_data if row[1] == "R"]
                    
                    dem_avg = sum(dem_scores) / len(dem_scores) if dem_scores else "N/A"
                    rep_avg = sum(rep_scores) / len(rep_scores) if rep_scores else "N/A"
                    
                    # Write party averages
                    f.write("## Party Averages\n\n")
                    f.write(f"* **Democratic Average:** {dem_avg}\n")
                    f.write(f"* **Republican Average:** {rep_avg}\n\n")
                    
                    # Write score interpretation
                    f.write("## Score Interpretation\n\n")
                    f.write("* **-3**: Favor a great deal\n")
                    f.write("* **-2**: Favor a moderate amount\n")
                    f.write("* **-1**: Favor a little\n")
                    f.write("* **0**: Neither favor nor oppose\n")
                    f.write("* **1**: Oppose a little\n")
                    f.write("* **2**: Oppose a moderate amount\n")
                    f.write("* **3**: Oppose a great deal\n")
                    
            logger.info(f"Generated question reports in reports/ directory")
        except Exception as e:
            logger.error(f"Error generating question report: {e}")
            
    def _generate_summary_report(self, results):
        """
        Generate summary report
        
        Args:
            results (dict): Test results
        """
        try:
            # Create report directory
            os.makedirs("reports", exist_ok=True)
            
            # Create summary report
            report_path = "reports/summary_report.md"
            
            with open(report_path, "w") as f:
                # Write header
                f.write("# Position Estimation Summary Report\n\n")
                
                # Write overview
                f.write("## Overview\n\n")
                f.write(f"* **Lawmakers Processed:** {results['summary']['lawmakers_processed']}\n")
                f.write(f"* **Total Positions Estimated:** {results['summary']['total_positions']}\n")
                f.write(f"* **Democratic Average Score:** {results['summary']['party_averages']['Democratic']:.2f}\n")
                f.write(f"* **Republican Average Score:** {results['summary']['party_averages']['Republican']:.2f}\n\n")
                
                # Write source coverage
                f.write("## Source Coverage\n\n")
                
                for source, coverage in results['summary']['source_coverage'].items():
                    f.write(f"* **{source.replace('_', ' ').title()}:** {coverage:.2%}\n")
                    
                f.write("\n")
                
                # Write confidence distribution
                f.write("## Confidence Distribution\n\n")
                
                for level, percentage in results['summary']['confidence_distribution'].items():
                    f.write(f"* **{level.title()} Confidence:** {percentage:.2%}\n")
                    
                f.write("\n")
                
                # Write lawmaker summary
                f.write("## Lawmaker Summary\n\n")
                
                # Create table
                table_data = []
                headers = ["Lawmaker", "Party", "Positions", "Avg. Score", "Avg. Confidence"]
                
                for lawmaker in results["lawmakers"]:
                    positions = lawmaker.get("positions", [])
                    
                    if not positions:
                        continue
                        
                    # Calculate averages
                    avg_score = sum(p["score"] for p in positions) / len(positions)
                    avg_confidence = sum(p["confidence"] for p in positions) / len(positions)
                    
                    # Add to table
                    table_data.append([
                        lawmaker["name"],
                        lawmaker["party"],
                        len(positions),
                        f"{avg_score:.2f}",
                        f"{avg_confidence:.2f}"
                    ])
                    
                # Sort by party then name
                table_data.sort(key=lambda x: (x[1], x[0]))
                
                # Write table
                f.write(tabulate(table_data, headers=headers, tablefmt="pipe"))
                f.write("\n\n")
                
                # Write score interpretation
                f.write("## Score Interpretation\n\n")
                f.write("* **-3**: Favor a great deal\n")
                f.write("* **-2**: Favor a moderate amount\n")
                f.write("* **-1**: Favor a little\n")
                f.write("* **0**: Neither favor nor oppose\n")
                f.write("* **1**: Oppose a little\n")
                f.write("* **2**: Oppose a moderate amount\n")
                f.write("* **3**: Oppose a great deal\n")
                
            logger.info(f"Generated summary report at {report_path}")
        except Exception as e:
            logger.error(f"Error generating summary report: {e}")
            
    def _generate_visualizations(self, results):
        """
        Generate visualizations from test results
        
        Args:
            results (dict): Test results
        """
        try:
            # Create visualizations directory
            os.makedirs("reports/visualizations", exist_ok=True)
            
            # Generate party comparison visualization
            self._generate_party_comparison(results)
            
            # Generate source coverage visualization
            self._generate_source_coverage(results)
            
            # Generate lawmaker comparison visualization
            self._generate_lawmaker_comparison(results)
            
            # Generate confidence distribution visualization
            self._generate_confidence_distribution(results)
            
            logger.info(f"Generated visualizations in reports/visualizations/ directory")
        except Exception as e:
            logger.error(f"Error generating visualizations: {e}")
            
    def _generate_party_comparison(self, results):
        """
        Generate party comparison visualization
        
        Args:
            results (dict): Test results
        """
        try:
            # Collect data
            dem_scores = []
            rep_scores = []
            
            for lawmaker in results["lawmakers"]:
                for position in lawmaker.get("positions", []):
                    if lawmaker["party"] == "D":
                        dem_scores.append(position["score"])
                    elif lawmaker["party"] == "R":
                        rep_scores.append(position["score"])
                        
            # Create histogram
            plt.figure(figsize=(10, 6))
            
            bins = range(-4, 5)
            
            plt.hist(dem_scores, bins=bins, alpha=0.5, label="Democratic", color="blue")
            plt.hist(rep_scores, bins=bins, alpha=0.5, label="Republican", color="red")
            
            plt.xlabel("Position Score")
            plt.ylabel("Frequency")
            plt.title("Position Distribution by Party")
            plt.legend()
            plt.grid(True, alpha=0.3)
            
            # Add score interpretation
            plt.text(-3, 0, "Favor a great deal", rotation=90, va="bottom", fontsize=8)
            plt.text(-2, 0, "Favor a moderate amount", rotation=90, va="bottom", fontsize=8)
            plt.text(-1, 0, "Favor a little", rotation=90, va="bottom", fontsize=8)
            plt.text(0, 0, "Neither favor nor oppose", rotation=90, va="bottom", fontsize=8)
            plt.text(1, 0, "Oppose a little", rotation=90, va="bottom", fontsize=8)
            plt.text(2, 0, "Oppose a moderate amount", rotation=90, va="bottom", fontsize=8)
            plt.text(3, 0, "Oppose a great deal", rotation=90, va="bottom", fontsize=8)
            
            # Save figure
            plt.savefig("reports/visualizations/party_comparison.png", dpi=300, bbox_inches="tight")
            plt.close()
        except Exception as e:
            logger.error(f"Error generating party comparison: {e}")
            
    def _generate_source_coverage(self, results):
        """
        Generate source coverage visualization
        
        Args:
            results (dict): Test results
        """
        try:
            # Get source coverage
            source_coverage = results["summary"]["source_coverage"]
            
            # Create bar chart
            plt.figure(figsize=(10, 6))
            
            sources = list(source_coverage.keys())
            coverage = list(source_coverage.values())
            
            # Format source names
            sources = [s.replace("_", " ").title() for s in sources]
            
            plt.bar(sources, coverage, color="skyblue")
            
            plt.xlabel("Data Source")
            plt.ylabel("Coverage")
            plt.title("Data Source Coverage")
            plt.ylim(0, 1)
            
            # Add percentage labels
            for i, v in enumerate(coverage):
                plt.text(i, v + 0.02, f"{v:.1%}", ha="center")
                
            plt.grid(True, alpha=0.3, axis="y")
            
            # Save figure
            plt.savefig("reports/visualizations/source_coverage.png", dpi=300, bbox_inches="tight")
            plt.close()
        except Exception as e:
            logger.error(f"Error generating source coverage: {e}")
            
    def _generate_lawmaker_comparison(self, results):
        """
        Generate lawmaker comparison visualization
        
        Args:
            results (dict): Test results
        """
        try:
            # Collect data
            lawmaker_data = []
            
            for lawmaker in results["lawmakers"]:
                positions = lawmaker.get("positions", [])
                
                if not positions:
                    continue
                    
                # Calculate average score
                avg_score = sum(p["score"] for p in positions) / len(positions)
                
                lawmaker_data.append({
                    "name": lawmaker["name"],
                    "party": lawmaker["party"],
                    "avg_score": avg_score
                })
                
            # Sort by average score
            lawmaker_data.sort(key=lambda x: x["avg_score"])
            
            # Create bar chart
            plt.figure(figsize=(12, 8))
            
            names = [ld["name"] for ld in lawmaker_data]
            scores = [ld["avg_score"] for ld in lawmaker_data]
            colors = ["blue" if ld["party"] == "D" else "red" for ld in lawmaker_data]
            
            plt.barh(names, scores, color=colors)
            
            plt.xlabel("Average Position Score")
            plt.ylabel("Lawmaker")
            plt.title("Average Position by Lawmaker")
            plt.grid(True, alpha=0.3, axis="x")
            
            # Add vertical line at 0
            plt.axvline(x=0, color="black", linestyle="-", alpha=0.3)
            
            # Add score interpretation
            plt.text(-3, -0.5, "Favor a great deal", rotation=0, ha="center", fontsize=8)
            plt.text(-2, -0.5, "Favor a moderate amount", rotation=0, ha="center", fontsize=8)
            plt.text(-1, -0.5, "Favor a little", rotation=0, ha="center", fontsize=8)
            plt.text(0, -0.5, "Neither", rotation=0, ha="center", fontsize=8)
            plt.text(1, -0.5, "Oppose a little", rotation=0, ha="center", fontsize=8)
            plt.text(2, -0.5, "Oppose a moderate amount", rotation=0, ha="center", fontsize=8)
            plt.text(3, -0.5, "Oppose a great deal", rotation=0, ha="center", fontsize=8)
            
            # Save figure
            plt.savefig("reports/visualizations/lawmaker_comparison.png", dpi=300, bbox_inches="tight")
            plt.close()
        except Exception as e:
            logger.error(f"Error generating lawmaker comparison: {e}")
            
    def _generate_confidence_distribution(self, results):
        """
        Generate confidence distribution visualization
        
        Args:
            results (dict): Test results
        """
        try:
            # Collect confidence values
            confidence_values = []
            
            for lawmaker in results["lawmakers"]:
                for position in lawmaker.get("positions", []):
                    confidence_values.append(position["confidence"])
                    
            # Create histogram
            plt.figure(figsize=(10, 6))
            
            plt.hist(confidence_values, bins=10, color="green", alpha=0.7)
            
            plt.xlabel("Confidence Score")
            plt.ylabel("Frequency")
            plt.title("Confidence Distribution")
            plt.grid(True, alpha=0.3)
            
            # Add confidence level indicators
            plt.axvline(x=0.3, color="red", linestyle="--", alpha=0.7)
            plt.axvline(x=0.7, color="red", linestyle="--", alpha=0.7)
            
            plt.text(0.15, 0, "Low Confidence", rotation=90, va="bottom", fontsize=10)
            plt.text(0.5, 0, "Medium Confidence", rotation=90, va="bottom", fontsize=10)
            plt.text(0.85, 0, "High Confidence", rotation=90, va="bottom", fontsize=10)
            
            # Save figure
            plt.savefig("reports/visualizations/confidence_distribution.png", dpi=300, bbox_inches="tight")
            plt.close()
        except Exception as e:
            logger.error(f"Error generating confidence distribution: {e}")
            
    def close_connection(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            
        # Close component connections
        self.congress_scraper.close_connection()
        self.statements_analyzer.close_connection()
        self.ratings_collector.close_connection()
        self.position_estimator.close_connection()


if __name__ == "__main__":
    # Database path
    db_path = "political_alignment.db"
    
    # Create tester
    tester = PositionEstimationTester(db_path)
    
    try:
        # Run test
        results = tester.run_test()
        
        # Print summary
        print("\nTest Summary:")
        print(f"Lawmakers processed: {results['summary']['lawmakers_processed']}")
        print(f"Total positions estimated: {results['summary']['total_positions']}")
        print(f"Democratic average score: {results['summary']['party_averages']['Democratic']:.2f}")
        print(f"Republican average score: {results['summary']['party_averages']['Republican']:.2f}")
        
        print("\nSource Coverage:")
        for source, coverage in results['summary']['source_coverage'].items():
            print(f"{source.replace('_', ' ').title()}: {coverage:.2%}")
            
        print("\nConfidence Distribution:")
        for level, percentage in results['summary']['confidence_distribution'].items():
            print(f"{level.title()} confidence: {percentage:.2%}")
            
        print("\nReports and visualizations generated in reports/ directory")
    finally:
        # Close connection
        tester.close_connection()
