# Political Alignment Tool - README

## Overview

The Political Alignment Tool is a comprehensive system designed to match users with political representatives based on their positions on various policy issues. This tool collects data on representatives' positions from multiple sources, processes user survey responses, and calculates alignment scores to identify which representatives most closely match a user's political views.

## Features

- **Multi-source Data Collection**: Gathers representatives' positions from Congress.gov API and Rvoteview
- **Comprehensive Database**: Stores representatives, policy areas, questions, and voting records
- **Advanced Scoring System**: Multiple alignment calculation methods including weighted scoring and MRP adjustments
- **Demographic Adjustments**: Incorporates user demographics for more accurate matching
- **Flexible Survey System**: Supports multiple policy areas with customizable questions
- **Detailed Results**: Provides overall and policy-area-specific alignment scores

## System Architecture

The system consists of four main components:

1. **Database**: SQLite database with a schema designed for storing representatives, policy areas, questions, and voting records
2. **Data Collection**: Web scraping frameworks for collecting data from Congress.gov API and Rvoteview
3. **Scoring System**: Advanced algorithms for calculating alignment between users and representatives
4. **Application Interface**: Main application class that integrates all components

## Installation

### Prerequisites

- Python 3.8 or higher
- Required Python packages:
  - requests
  - beautifulsoup4
  - pandas
  - numpy
  - scipy
  - scikit-learn

### Setup

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/political-alignment-tool.git
   cd political-alignment-tool
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up environment variables (optional):
   ```
   export CONGRESS_API_KEY=your_api_key_here
   ```

## Usage

### Basic Usage

1. Initialize the database:
   ```python
   from app import PoliticalAlignmentApp
   
   app = PoliticalAlignmentApp()
   app.initialize_database()
   ```

2. Collect data:
   ```python
   collection_results = app.collect_data()
   print(f"Data collection results: {collection_results}")
   ```

3. Get survey questions:
   ```python
   survey_questions = app.get_questions_for_survey()
   ```

4. Process user survey:
   ```python
   user_responses = [
       {"question_id": 1, "score": -2, "importance": 3},
       {"question_id": 2, "score": -1, "importance": 2},
       # Add more responses...
   ]
   
   user_demographics = {
       "age_group": "30-44",
       "education": "College",
       "gender": "Female",
       "race": "White",
       "state": "TX",
       "urban_rural": "Urban"
   }
   
   alignment_results = app.process_user_survey(user_responses, user_demographics)
   ```

5. Export results:
   ```python
   app.export_results(alignment_results, "alignment_results.json")
   ```

6. Close connections:
   ```python
   app.close_connections()
   ```

### Running the Demo

To run a complete demonstration of the system:

```
python app.py
```

This will:
1. Initialize the database with sample data
2. Collect data for a limited number of representatives
3. Generate sample user responses
4. Calculate alignment scores
5. Export results to `alignment_results.json`

## Customization

### Adding New Policy Areas

To add new policy areas, insert them into the `policy_areas` table:

```python
cursor.execute("""
INSERT INTO policy_areas (name, description, active)
VALUES (?, ?, ?)
""", ("Trade Policy", "International trade and tariffs", 1))
```

### Adding New Questions

To add new questions, insert them into the `questions` table and add corresponding response options:

```python
cursor.execute("""
INSERT INTO questions (policy_area_id, question_text, source, active)
VALUES (?, ?, ?, ?)
""", (policy_area_id, "Your question text", "Source", 1))

question_id = cursor.lastrowid

# Add response options
cursor.execute("""
INSERT INTO response_options (question_id, option_text, score)
VALUES (?, ?, ?)
""", (question_id, "Strongly agree", -3))
```

## Scaling Considerations

The system is designed to be scalable in several ways:

1. **Database**: SQLite is used for simplicity, but can be replaced with PostgreSQL or MySQL for larger deployments
2. **Data Collection**: The scraping framework includes rate limiting and error handling for reliable operation
3. **Processing**: The scoring system can handle large numbers of representatives and questions
4. **Deployment**: The application can be deployed as a standalone service or integrated into a web application

For very large deployments, consider:
- Implementing a job queue for data collection tasks
- Adding caching for frequently accessed data
- Distributing the database across multiple servers
- Implementing a web API for client applications

## Technical Details

### Database Schema

The database schema includes the following main tables:
- `representatives`: Information about political representatives
- `policy_areas`: Policy areas covered by the system
- `questions`: Survey questions for each policy area
- `response_options`: Possible responses for each question
- `representative_positions`: Representatives' positions on questions
- `voting_records`: Representatives' voting records
- `bill_question_mapping`: Mapping between bills and questions

### Scoring Methods

The system supports multiple scoring methods:
- **Simple**: Basic distance-based scoring
- **Weighted**: Weighted by question importance
- **Cosine**: Cosine similarity between user and representative vectors
- **MRP-adjusted**: Adjusted based on demographic factors

### Data Sources

The system collects data from:
- **Congress.gov API**: Official source for congressional data
- **Rvoteview**: Academic database of congressional voting records
- **Representative websites**: Scraped for additional position information

## Future Enhancements

Potential future enhancements include:
- Integration with additional data sources
- More sophisticated NLP for position inference
- Real-time updates based on new votes and statements
- Mobile application for user surveys
- Interactive visualization of alignment results
- API for third-party integrations

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Data provided by Congress.gov API and Voteview
- Survey questions adapted from GSS (General Social Survey)
- MRP methodology inspired by academic research in political science
