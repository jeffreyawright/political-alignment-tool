# Political Alignment Tool Documentation

## Overview

The Political Alignment Tool is a comprehensive system for estimating lawmakers' positions on policy questions based on multiple data sources. The tool analyzes voting records, bill sponsorships, public statements, and advocacy group ratings to provide balanced, evidence-based position estimates without relying too heavily on partisanship.

This documentation provides detailed information on the system architecture, installation, usage, and underlying algorithms.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Installation](#installation)
3. [Usage Guide](#usage-guide)
4. [Data Sources](#data-sources)
5. [Position Estimation Algorithm](#position-estimation-algorithm)
6. [Database Schema](#database-schema)
7. [API Reference](#api-reference)
8. [Troubleshooting](#troubleshooting)
9. [Future Enhancements](#future-enhancements)

## System Architecture

The Political Alignment Tool consists of several integrated components:

1. **Congress Scraper**: Collects voting records and bill sponsorships from Congress.gov and other legislative data sources.
2. **Public Statements Analyzer**: Gathers and analyzes lawmakers' public statements, press releases, and speeches.
3. **Advocacy Ratings Collector**: Collects ratings from advocacy organizations across the political spectrum.
4. **Position Estimation Algorithm**: Integrates data from all sources to estimate positions on policy questions.
5. **Database**: Stores lawmaker information, policy questions, and position estimates.
6. **Testing Framework**: Validates the system with sample lawmakers and generates reports.

The system uses a SQLite database for data storage and Python for all components. The architecture is designed to be modular, allowing each component to be updated or replaced independently.

## Installation

### Prerequisites

- Python 3.8 or higher
- SQLite 3
- Required Python packages (see requirements.txt)

### Setup Instructions

1. Clone the repository:
   ```
   git clone https://github.com/your-organization/political-alignment-tool.git
   cd political-alignment-tool
   ```

2. Create a virtual environment (recommended):
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Run the setup script:
   ```
   bash setup.sh
   ```

5. Initialize the database:
   ```
   python init_database.py
   ```

## Usage Guide

### Basic Usage

The Political Alignment Tool can be used in several ways:

1. **Command Line Interface**:
   ```
   python app.py --lawmaker "John Smith" --questions "gun_control,immigration"
   ```

2. **Python API**:
   ```python
   from political_alignment_tool import PositionEstimator
   
   estimator = PositionEstimator("database.db")
   positions = estimator.estimate_positions("S000148")  # Chuck Schumer
   ```

3. **Web Interface**:
   ```
   python app.py --server
   # Then open http://localhost:5000 in your browser
   ```

### Estimating Positions

To estimate positions for a lawmaker:

1. Ensure the lawmaker exists in the database:
   ```
   python manage_lawmakers.py --add --bioguide "S000148" --name "Chuck Schumer" --party "D" --state "NY" --chamber "Senate"
   ```

2. Run the position estimation:
   ```
   python estimate_positions.py --bioguide "S000148"
   ```

3. Generate reports:
   ```
   python generate_reports.py --bioguide "S000148" --output "reports/"
   ```

### Testing the System

To test the system with sample lawmakers:

```
python test_position_estimation.py
```

This will:
1. Collect data for sample lawmakers
2. Estimate positions on all active questions
3. Generate detailed reports and visualizations
4. Output summary statistics

## Data Sources

The Political Alignment Tool uses multiple data sources to estimate positions:

### 1. Voting Records

- **Source**: Congress.gov API and web scraping
- **Data Collected**: Roll call votes, vote positions, bill information
- **Processing**: Maps bills to policy questions using TF-IDF and cosine similarity
- **Weight in Algorithm**: 35%

### 2. Bill Sponsorships

- **Source**: Congress.gov API and web scraping
- **Data Collected**: Sponsored and cosponsored bills
- **Processing**: Analyzes primary sponsorship and cosponsorship separately
- **Weight in Algorithm**: 25%

### 3. Public Statements

- **Source**: ProPublica Congress API and official websites
- **Data Collected**: Press releases, statements, speeches
- **Processing**: Uses NLP and sentiment analysis to determine positions
- **Weight in Algorithm**: 25%

### 4. Advocacy Group Ratings

- **Source**: Various advocacy organizations (NRA, LCV, ACLU, etc.)
- **Data Collected**: Ratings, endorsements, scorecards
- **Processing**: Normalizes diverse rating scales to a common -3 to 3 scale
- **Weight in Algorithm**: 15%

## Position Estimation Algorithm

The Position Estimation Algorithm integrates data from all sources to estimate lawmakers' positions on policy questions.

### Algorithm Overview

1. **Data Collection**: Gather data from all sources for a lawmaker
2. **Source-Specific Position Inference**: Infer positions from each data source
3. **Confidence Calculation**: Calculate confidence for each source-specific position
4. **Weighted Integration**: Combine positions using weighted average
5. **Fallback Methods**: Use alternative methods when direct data is unavailable
6. **Quality Assessment**: Calculate quality metrics for position estimates

### Weighting System

The algorithm uses a sophisticated weighting system that considers:

- **Source Importance**: Predefined weights for each data source
- **Confidence Level**: Higher confidence positions have more influence
- **Agreement Factor**: Sources that agree receive higher weight
- **Recency**: More recent data receives higher weight

### Confidence Calculation

Confidence is calculated based on:

- **Data Quantity**: More data points increase confidence
- **Data Quality**: Higher quality sources increase confidence
- **Source Agreement**: Agreement between sources increases confidence
- **Recency**: More recent data increases confidence

### Fallback Methods

When direct data is unavailable, the algorithm uses these fallback methods:

1. **Similar Questions**: Estimate based on similar questions for the same lawmaker
2. **Similar Lawmakers**: Estimate based on similar lawmakers for the same question
3. **Party-Based Estimate**: Use party as a last resort with appropriately low confidence

## Database Schema

The Political Alignment Tool uses a SQLite database with the following schema:

### Core Tables

- **representatives**: Stores lawmaker information
- **questions**: Stores policy questions
- **policy_areas**: Stores policy areas for questions

### Data Source Tables

- **votes**: Stores voting records
- **bill_sponsorships**: Stores bill sponsorship information
- **public_statements**: Stores public statements
- **advocacy_ratings**: Stores advocacy group ratings

### Position Tables

- **representative_positions**: Stores positions from individual sources
- **integrated_positions**: Stores integrated positions from all sources
- **position_estimation_logs**: Stores detailed logs of position estimation

See [database_schema.md](database_schema.md) for the complete schema.

## API Reference

### Python API

The Political Alignment Tool provides a Python API for programmatic access:

```python
from political_alignment_tool import PositionEstimator

# Initialize estimator
estimator = PositionEstimator("database.db")

# Estimate positions for a lawmaker
positions = estimator.estimate_positions("S000148")

# Get position for a specific question
position = estimator.get_position("S000148", 1)  # Question ID 1

# Get quality metrics
metrics = estimator.get_quality_metrics()
```

### REST API

The web interface provides a REST API:

- `GET /api/lawmakers`: List all lawmakers
- `GET /api/lawmakers/{bioguide_id}`: Get lawmaker details
- `GET /api/questions`: List all questions
- `GET /api/positions/{bioguide_id}`: Get positions for a lawmaker
- `POST /api/estimate`: Estimate positions for a lawmaker

## Troubleshooting

### Common Issues

1. **API Rate Limiting**: Congress.gov and other APIs may impose rate limits. The system includes retry logic and caching to mitigate this.

2. **Missing Data**: Some lawmakers may have limited data available. The system uses fallback methods to provide estimates even with limited data.

3. **Database Errors**: If you encounter database errors, try:
   ```
   python repair_database.py
   ```

4. **Performance Issues**: For large datasets, consider:
   - Using the `--limit` option to process fewer lawmakers
   - Running components separately with `--component` option
   - Increasing cache size in `config.py`

### Logging

The system generates detailed logs for troubleshooting:

- **Main Log**: `political_alignment_tool.log`
- **Component Logs**: `congress_scraper.log`, `public_statements_analyzer.log`, etc.
- **Error Log**: `error.log`

## Future Enhancements

Planned enhancements for future versions:

1. **Additional Data Sources**:
   - Social media analysis
   - Committee hearing transcripts
   - Campaign finance data

2. **Advanced Algorithms**:
   - Machine learning for position inference
   - Topic modeling for better question mapping
   - Entity recognition for improved statement analysis

3. **System Improvements**:
   - Distributed processing for faster analysis
   - Real-time updates for new votes and statements
   - Advanced visualization and reporting tools

4. **Integration Options**:
   - API integrations with other political analysis tools
   - Export options for various data formats
   - Webhook notifications for position changes
