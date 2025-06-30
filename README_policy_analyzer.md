# Policy Position Analyzer

## Overview

The Policy Position Analyzer is a comprehensive tool that analyzes a legislator's position on specific policy issues by examining their legislative activity, committee memberships, and public statements. It provides a scoring system from -3 to 3 that gauges support or opposition to policy issues.

## Features

- **Comprehensive Analysis**: Examines bills sponsored/cosponsored, committee memberships, and public statements
- **Multi-Source Data**: Integrates data from Congress.gov API, ProPublica Congress API, and other sources
- **Scoring System**: Provides position scores from -3 (strongly supports) to 3 (strongly opposes)
- **Confidence Metrics**: Includes confidence scores based on data quality and quantity
- **Policy Coverage**: Supports analysis of major policy issues including gun control, immigration, healthcare, climate change, abortion, and economy

## Installation

1. Install required dependencies:
```bash
pip install requests beautifulsoup4 pandas numpy scikit-learn nltk
```

2. Download NLTK data:
```python
import nltk
nltk.download('punkt')
nltk.download('vader_lexicon')
```

3. Set up API keys (optional but recommended):
```bash
export CONGRESS_API_KEY="your_congress_api_key"
export PROPUBLICA_API_KEY="your_propublica_api_key"
```

## Usage

### Basic Usage

```python
from policy_position_analyzer import analyze_legislator_policy_position

# Analyze Chuck Schumer's position on gun control
results = analyze_legislator_policy_position(
    bioguide_id="S000148",
    policy_issue="gun_control"
)

print(f"Overall Score: {results['overall_position']['score']}")
print(f"Interpretation: {results['overall_position']['interpretation']}")
print(f"Confidence: {results['overall_position']['confidence']:.2f}")
```

### Advanced Usage

```python
from policy_position_analyzer import PolicyPositionAnalyzer

# Create analyzer instance
analyzer = PolicyPositionAnalyzer(
    db_path="political_alignment.db",
    congress_api_key="your_api_key",
    propublica_api_key="your_api_key"
)

# Analyze multiple issues
issues = ["gun_control", "immigration", "healthcare"]
for issue in issues:
    results = analyzer.analyze_policy_position("S000148", issue)
    print(f"{issue}: {results['overall_position']['score']}")

analyzer.close_connection()
```

### Command Line Usage

```bash
# Run comprehensive analysis on multiple legislators
python example_policy_analysis.py

# Interactive single legislator analysis
python example_policy_analysis.py --interactive
```

## Supported Policy Issues

- **gun_control**: Gun control and firearms regulation
- **immigration**: Immigration policy and border security
- **healthcare**: Healthcare policy and insurance
- **climate_change**: Climate change and environmental policy
- **abortion**: Abortion rights and reproductive health
- **economy**: Economic policy, taxes, and budget

## Scoring System

### Position Scores (-3 to 3)
- **-3**: Strongly supports the policy
- **-2**: Moderately supports the policy
- **-1**: Somewhat supports the policy
- **0**: Neutral or mixed position
- **1**: Somewhat opposes the policy
- **2**: Moderately opposes the policy
- **3**: Strongly opposes the policy

### Confidence Scores (0.0 to 1.0)
- **0.0-0.3**: Low confidence (limited data available)
- **0.3-0.7**: Medium confidence (moderate data available)
- **0.7-1.0**: High confidence (robust data available)

## Analysis Components

### 1. Bills Analysis (50% weight)
- Examines bills sponsored and cosponsored by the legislator
- Analyzes bill titles, summaries, and content for policy relevance
- Weights sponsored bills more heavily than cosponsored bills
- Determines position based on bill content and intent

### 2. Public Statements Analysis (30% weight)
- Analyzes press releases, speeches, and public statements
- Uses natural language processing for sentiment analysis
- Identifies policy-specific language and position indicators
- Considers statement recency and relevance

### 3. Committee Membership Analysis (20% weight)
- Evaluates membership on policy-relevant committees
- Considers committee roles (chair, ranking member, member)
- Provides context and boosts confidence in other analyses
- Maps committee jurisdictions to policy areas

## Data Sources

- **Congress.gov API**: Official source for bills, votes, and member information
- **ProPublica Congress API**: Committee memberships and additional member data
- **Public Statements**: Press releases and official statements (when available)
- **Database Cache**: Stores analyzed data for faster subsequent queries

## Output Format

```json
{
  "representative": {
    "bioguide_id": "S000148",
    "name": "Chuck Schumer",
    "party": "D",
    "chamber": "Senate",
    "state": "NY"
  },
  "policy_issue": "gun_control",
  "overall_position": {
    "score": -2,
    "confidence": 0.85,
    "interpretation": "Moderately supports"
  },
  "component_analysis": {
    "bills": {
      "bills_analyzed": 15,
      "sponsored_count": 8,
      "cosponsored_count": 7,
      "average_score": -2,
      "confidence": 0.9
    },
    "statements": {
      "statements_analyzed": 5,
      "average_score": -2,
      "confidence": 0.7
    },
    "committees": {
      "relevant_committees": 2,
      "committee_relevance_score": 0.8
    }
  }
}
```

## Database Schema

The analyzer creates several database tables to store analysis results:

- **policy_bills**: Stores analyzed bills with relevance and position scores
- **committee_memberships**: Stores committee membership information
- **policy_statements**: Stores analyzed public statements
- **policy_analysis_results**: Stores overall analysis results

## Customization

### Adding New Policy Issues

```python
# Add to policy_keywords in PolicyPositionAnalyzer.__init__
self.policy_keywords["new_issue"] = {
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "committees": ["relevant_committee1", "relevant_committee2"]
}
```

### Adjusting Component Weights

```python
# Modify weights in _calculate_overall_position method
weights = {
    "bills": 0.6,      # Increase bills weight
    "statements": 0.25, # Decrease statements weight
    "committees": 0.15  # Decrease committee weight
}
```

## Limitations

- Requires API keys for full functionality
- Analysis quality depends on data availability
- Some older legislators may have limited digital records
- Committee data may not be complete for all members
- Public statements analysis is limited by available sources

## Error Handling

The analyzer includes comprehensive error handling:
- Graceful degradation when API keys are missing
- Fallback methods when data sources are unavailable
- Detailed logging for debugging
- Confidence scores reflect data quality limitations

## Performance Considerations

- API rate limiting is implemented to avoid service disruption
- Results are cached in the database to improve performance
- Analysis can be run incrementally for large datasets
- Memory usage is optimized for processing large numbers of bills

## Contributing

To contribute to the Policy Position Analyzer:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.