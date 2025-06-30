#!/usr/bin/env python3
"""
Example script demonstrating the Policy Position Analyzer

This script shows how to use the PolicyPositionAnalyzer to analyze
legislators' positions on various policy issues.
"""

import os
import sys
import json
from datetime import datetime
from policy_position_analyzer import PolicyPositionAnalyzer, analyze_legislator_policy_position

def main():
    """Main function to demonstrate policy position analysis"""
    
    # Get API keys from environment variables
    congress_api_key = os.environ.get("CONGRESS_API_KEY")
    propublica_api_key = os.environ.get("PROPUBLICA_API_KEY")
    
    if not congress_api_key:
        print("Warning: CONGRESS_API_KEY not set. Some features may not work.")
    if not propublica_api_key:
        print("Warning: PROPUBLICA_API_KEY not set. Committee analysis may be limited.")
    
    # Define test cases
    test_cases = [
        {
            "bioguide_id": "S000148",  # Chuck Schumer
            "name": "Chuck Schumer",
            "policy_issues": ["gun_control", "immigration", "healthcare"]
        },
        {
            "bioguide_id": "M000355",  # Mitch McConnell
            "name": "Mitch McConnell", 
            "policy_issues": ["gun_control", "healthcare", "economy"]
        },
        {
            "bioguide_id": "W000817",  # Elizabeth Warren
            "name": "Elizabeth Warren",
            "policy_issues": ["healthcare", "economy", "climate_change"]
        },
        {
            "bioguide_id": "C001075",  # Ted Cruz
            "name": "Ted Cruz",
            "policy_issues": ["gun_control", "immigration", "abortion"]
        }
    ]
    
    # Analyze each test case
    all_results = []
    
    for test_case in test_cases:
        print(f"\n{'='*60}")
        print(f"Analyzing {test_case['name']} ({test_case['bioguide_id']})")
        print(f"{'='*60}")
        
        legislator_results = {
            "bioguide_id": test_case["bioguide_id"],
            "name": test_case["name"],
            "policy_analyses": []
        }
        
        for policy_issue in test_case["policy_issues"]:
            print(f"\nAnalyzing position on: {policy_issue.replace('_', ' ').title()}")
            print("-" * 40)
            
            try:
                # Analyze the policy position
                results = analyze_legislator_policy_position(
                    bioguide_id=test_case["bioguide_id"],
                    policy_issue=policy_issue,
                    congress_api_key=congress_api_key,
                    propublica_api_key=propublica_api_key
                )
                
                if results:
                    # Print summary
                    print(f"Overall Score: {results['overall_position']['score']} ({results['overall_position']['interpretation']})")
                    print(f"Confidence: {results['overall_position']['confidence']:.2f}")
                    
                    # Print component breakdown
                    bills = results['component_analysis']['bills']
                    statements = results['component_analysis']['statements']
                    committees = results['component_analysis']['committees']
                    
                    print(f"\nComponent Analysis:")
                    print(f"  Bills: {bills['bills_analyzed']} analyzed (Score: {bills['average_score']}, Confidence: {bills['confidence']:.2f})")
                    print(f"    - Sponsored: {bills['sponsored_count']}")
                    print(f"    - Cosponsored: {bills['cosponsored_count']}")
                    
                    print(f"  Statements: {statements['statements_analyzed']} analyzed (Score: {statements['average_score']}, Confidence: {statements['confidence']:.2f})")
                    
                    print(f"  Committees: {committees['relevant_committees']} relevant (Relevance: {committees['committee_relevance_score']:.2f})")
                    
                    # Show top bills if available
                    if bills['bills']:
                        print(f"\nTop Relevant Bills:")
                        for i, bill in enumerate(bills['bills'][:3], 1):
                            print(f"  {i}. {bill['bill_number']} ({bill['role']}) - Score: {bill['position_score']}")
                            print(f"     {bill['title'][:80]}...")
                    
                    # Show committee memberships if available
                    if committees['memberships']:
                        print(f"\nRelevant Committee Memberships:")
                        for membership in committees['memberships']:
                            role_text = f" ({membership['role']})" if membership['role'] != 'member' else ""
                            print(f"  - {membership['committee']}{role_text}")
                    
                    legislator_results["policy_analyses"].append(results)
                    
                else:
                    print("Analysis failed - no results returned")
                    
            except Exception as e:
                print(f"Error analyzing {policy_issue}: {e}")
                
        all_results.append(legislator_results)
    
    # Generate summary report
    print(f"\n{'='*60}")
    print("SUMMARY REPORT")
    print(f"{'='*60}")
    
    # Create summary table
    print(f"\n{'Legislator':<20} {'Issue':<15} {'Score':<6} {'Confidence':<10} {'Bills':<6} {'Statements':<10}")
    print("-" * 75)
    
    for legislator in all_results:
        for analysis in legislator["policy_analyses"]:
            name = legislator["name"][:19]
            issue = analysis["policy_issue"].replace("_", " ").title()[:14]
            score = analysis["overall_position"]["score"]
            confidence = f"{analysis['overall_position']['confidence']:.2f}"
            bills = analysis["component_analysis"]["bills"]["bills_analyzed"]
            statements = analysis["component_analysis"]["statements"]["statements_analyzed"]
            
            print(f"{name:<20} {issue:<15} {score:<6} {confidence:<10} {bills:<6} {statements:<10}")
    
    # Save detailed results to JSON
    output_file = f"policy_analysis_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    try:
        with open(output_file, 'w') as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"\nDetailed results saved to: {output_file}")
    except Exception as e:
        print(f"Error saving results: {e}")
    
    # Print interpretation guide
    print(f"\n{'='*60}")
    print("SCORE INTERPRETATION GUIDE")
    print(f"{'='*60}")
    print("Score | Interpretation")
    print("------|---------------")
    print("  -3  | Strongly supports the policy")
    print("  -2  | Moderately supports the policy")
    print("  -1  | Somewhat supports the policy")
    print("   0  | Neutral or mixed position")
    print("   1  | Somewhat opposes the policy")
    print("   2  | Moderately opposes the policy")
    print("   3  | Strongly opposes the policy")
    
    print(f"\nConfidence scores range from 0.0 to 1.0:")
    print("- 0.0-0.3: Low confidence (limited data)")
    print("- 0.3-0.7: Medium confidence (moderate data)")
    print("- 0.7-1.0: High confidence (robust data)")


def analyze_single_legislator():
    """Interactive function to analyze a single legislator"""
    
    print("Single Legislator Policy Analysis")
    print("=" * 40)
    
    # Get input from user
    bioguide_id = input("Enter Bioguide ID (e.g., S000148 for Chuck Schumer): ").strip()
    
    if not bioguide_id:
        print("Error: Bioguide ID is required")
        return
    
    print("\nAvailable policy issues:")
    issues = ["gun_control", "immigration", "healthcare", "climate_change", "abortion", "economy"]
    for i, issue in enumerate(issues, 1):
        print(f"{i}. {issue.replace('_', ' ').title()}")
    
    try:
        choice = int(input("\nSelect policy issue (1-6): ")) - 1
        if 0 <= choice < len(issues):
            policy_issue = issues[choice]
        else:
            print("Invalid choice")
            return
    except ValueError:
        print("Invalid input")
        return
    
    # Get API keys
    congress_api_key = os.environ.get("CONGRESS_API_KEY")
    propublica_api_key = os.environ.get("PROPUBLICA_API_KEY")
    
    print(f"\nAnalyzing {bioguide_id} on {policy_issue.replace('_', ' ').title()}...")
    
    try:
        results = analyze_legislator_policy_position(
            bioguide_id=bioguide_id,
            policy_issue=policy_issue,
            congress_api_key=congress_api_key,
            propublica_api_key=propublica_api_key
        )
        
        if results:
            # Print detailed results
            print(f"\n{'='*60}")
            print(f"ANALYSIS RESULTS")
            print(f"{'='*60}")
            
            rep = results["representative"]
            print(f"Legislator: {rep['name']} ({rep['party']}-{rep['state']})")
            print(f"Chamber: {rep['chamber']}")
            print(f"Policy Issue: {policy_issue.replace('_', ' ').title()}")
            
            pos = results["overall_position"]
            print(f"\nOverall Position:")
            print(f"  Score: {pos['score']} ({pos['interpretation']})")
            print(f"  Confidence: {pos['confidence']:.2f}")
            
            # Component details
            comp = results["component_analysis"]
            
            print(f"\nBills Analysis:")
            bills = comp["bills"]
            print(f"  Total Bills Analyzed: {bills['bills_analyzed']}")
            print(f"  Sponsored: {bills['sponsored_count']}")
            print(f"  Cosponsored: {bills['cosponsored_count']}")
            print(f"  Average Score: {bills['average_score']}")
            print(f"  Confidence: {bills['confidence']:.2f}")
            
            if bills["bills"]:
                print(f"\n  Most Relevant Bills:")
                for i, bill in enumerate(bills["bills"][:5], 1):
                    print(f"    {i}. {bill['bill_number']} ({bill['role']})")
                    print(f"       Score: {bill['position_score']}, Relevance: {bill['relevance_score']:.2f}")
                    print(f"       {bill['title'][:70]}...")
            
            print(f"\nPublic Statements Analysis:")
            statements = comp["statements"]
            print(f"  Statements Analyzed: {statements['statements_analyzed']}")
            print(f"  Average Score: {statements['average_score']}")
            print(f"  Average Sentiment: {statements['average_sentiment']:.2f}")
            print(f"  Confidence: {statements['confidence']:.2f}")
            
            print(f"\nCommittee Analysis:")
            committees = comp["committees"]
            print(f"  Relevant Committees: {committees['relevant_committees']}")
            print(f"  Committee Relevance Score: {committees['committee_relevance_score']:.2f}")
            
            if committees["memberships"]:
                print(f"\n  Committee Memberships:")
                for membership in committees["memberships"]:
                    role_text = f" ({membership['role']})" if membership['role'] != 'member' else ""
                    print(f"    - {membership['committee']}{role_text}")
                    if membership.get('subcommittee'):
                        print(f"      Subcommittee: {membership['subcommittee']}")
            
        else:
            print("Analysis failed - no results returned")
            
    except Exception as e:
        print(f"Error during analysis: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        analyze_single_legislator()
    else:
        main()