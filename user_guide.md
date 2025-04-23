# Political Alignment Tool User Guide

## Introduction

The Political Alignment Tool is designed to estimate lawmakers' positions on policy questions using multiple data sources. This guide provides step-by-step instructions for using the tool, from installation to generating reports.

## Quick Start

### Installation

1. Clone the repository and navigate to the directory:
   ```bash
   git clone https://github.com/your-organization/political-alignment-tool.git
   cd political-alignment-tool
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the setup script:
   ```bash
   bash setup.sh
   ```

### Basic Usage

1. **Estimate positions for a lawmaker:**
   ```bash
   python estimate_positions.py --bioguide "S000148"
   ```

2. **Generate reports:**
   ```bash
   python generate_reports.py --bioguide "S000148" --output "reports/"
   ```

3. **Run the test suite with sample lawmakers:**
   ```bash
   python test_position_estimation.py
   ```

## Understanding Position Scores

The tool uses a 7-point scale to represent positions:

* **-3**: Favor a great deal
* **-2**: Favor a moderate amount
* **-1**: Favor a little
* **0**: Neither favor nor oppose
* **1**: Oppose a little
* **2**: Oppose a moderate amount
* **3**: Oppose a great deal

Each position estimate also includes a confidence score (0.0-1.0) indicating the reliability of the estimate.

## Data Sources

The tool uses four primary data sources:

1. **Voting Records** (35% weight): How lawmakers voted on relevant legislation
2. **Bill Sponsorships** (25% weight): Bills sponsored or cosponsored by lawmakers
3. **Public Statements** (25% weight): Press releases, speeches, and other public statements
4. **Advocacy Group Ratings** (15% weight): Ratings from organizations across the political spectrum

## Working with Reports

The tool generates several types of reports:

1. **Lawmaker Reports**: Detailed position estimates for individual lawmakers
2. **Question Reports**: How different lawmakers responded to specific questions
3. **Summary Report**: Overall statistics and trends
4. **Visualizations**: Charts and graphs showing position distributions

Reports are generated in Markdown format and visualizations as PNG files.

## Advanced Usage

### Adding New Lawmakers

```bash
python manage_lawmakers.py --add --bioguide "S000148" --name "Chuck Schumer" --party "D" --state "NY" --chamber "Senate"
```

### Adding New Questions

```bash
python manage_questions.py --add --text "Do you favor, oppose, or neither favor nor oppose requiring background checks for gun purchases at gun shows or other private sales?" --policy_area "Gun Control"
```

### Customizing Data Sources

You can adjust the weight of different data sources in `config.py`:

```python
SOURCE_WEIGHTS = {
    "voting_records": 0.35,
    "bill_sponsorships": 0.25,
    "public_statements": 0.25,
    "advocacy_ratings": 0.15
}
```

### Running the Web Interface

```bash
python app.py --server
# Then open http://localhost:5000 in your browser
```

## Troubleshooting

### Common Issues

1. **Missing data for a lawmaker**: Try running with the `--force-fallback` option
   ```bash
   python estimate_positions.py --bioguide "S000148" --force-fallback
   ```

2. **API rate limiting**: Use the `--delay` option to add time between requests
   ```bash
   python estimate_positions.py --bioguide "S000148" --delay 2
   ```

3. **Database errors**: Repair the database
   ```bash
   python repair_database.py
   ```

### Getting Help

For more detailed information, refer to the full [documentation.md](documentation.md) file or run:

```bash
python app.py --help
```

## Example Workflow

1. Initialize the database with sample questions:
   ```bash
   python init_database.py --sample-questions
   ```

2. Add lawmakers of interest:
   ```bash
   python manage_lawmakers.py --add-from-file lawmakers.csv
   ```

3. Collect data for all lawmakers:
   ```bash
   python collect_data.py --all
   ```

4. Estimate positions:
   ```bash
   python estimate_positions.py --all
   ```

5. Generate comprehensive reports:
   ```bash
   python generate_reports.py --all --output reports/
   ```

6. View the summary report:
   ```bash
   open reports/summary_report.md
   ```
