# Data Sources for Position Estimation

This document outlines the data sources and methodologies used for estimating lawmakers' positions on survey questions.

## Overview

The Political Alignment Tool uses multiple data sources to create a balanced, comprehensive estimation of lawmakers' positions on policy issues. Each data source contributes differently to the overall estimation, and the system is designed to avoid over-reliance on any single source, particularly partisanship.

## Data Sources

### 1. Voting Records (Existing)

**Source Implementation**: Congress.gov API and Rvoteview
- Collects actual votes on legislation
- Maps bills to relevant policy questions
- Analyzes voting patterns on similar issues

**Enhancements Needed**:
- Improve bill-to-question mapping with more sophisticated relevance scoring
- Implement confidence weighting based on how directly a vote relates to a question
- Expand historical vote collection for better pattern analysis

### 2. Bill Sponsorship/Cosponsorship (Partial Implementation)

**Source Implementation**: Congress.gov API
- Identifies bills sponsored or cosponsored by lawmakers
- Analyzes the content and intent of sponsored legislation
- Considers the strength of support (primary sponsor vs. cosponsor)

**Enhancements Needed**:
- Develop a more robust bill content analyzer to extract policy positions
- Implement weighting based on sponsorship role (primary sponsor vs. cosponsor)
- Create a comprehensive mapping between bill topics and survey questions

### 3. Public Statements Analysis (New Implementation)

**Source Implementation**: ProPublica Congress API, official websites, press releases
- Collects official statements, press releases, and speeches
- Analyzes content using natural language processing
- Extracts position indicators and sentiment on specific policy issues

**Implementation Plan**:
- Create a `public_statements_analyzer.py` module
- Implement web scraping for official websites and press releases
- Use NLP techniques (sentiment analysis, entity recognition, topic modeling)
- Develop a scoring system that maps statement content to survey questions
- Implement confidence scoring based on statement recency and relevance

### 4. Advocacy Group Ratings (New Implementation)

**Source Implementation**: Various advocacy organizations' scorecards and ratings
- Collects ratings from organizations across the political spectrum
- Normalizes ratings to a common scale
- Maps organization focus areas to survey questions

**Implementation Plan**:
- Create an `advocacy_ratings_collector.py` module
- Implement scrapers for major advocacy group websites:
  - Environmental: League of Conservation Voters, Sierra Club
  - Fiscal: Americans for Tax Reform, Committee for a Responsible Federal Budget
  - Gun Policy: NRA, Brady Campaign, Giffords
  - Civil Rights: ACLU, Human Rights Campaign
  - Others based on survey topics
- Develop a normalization system to convert diverse rating scales
- Create a mapping between organization focus areas and survey questions
- Implement confidence weighting based on organization relevance to specific questions

## Integration Methodology

The system will integrate these data sources using a weighted ensemble approach:

1. **Source-Specific Position Estimation**:
   - Each data source independently estimates positions on each question
   - Each estimate includes a confidence score based on data quality and relevance

2. **Weighted Ensemble**:
   - Combines estimates from all sources with weights based on confidence scores
   - Adjusts for source reliability on specific question types
   - Ensures no single source dominates the estimation

3. **Confidence Calculation**:
   - Overall confidence score for each position estimate
   - Identifies questions with insufficient data for reliable estimation
   - Flags estimates that require manual review

4. **Balanced Coverage**:
   - Monitors data availability across lawmakers to ensure balanced coverage
   - Implements fallback strategies for lawmakers with limited data in certain sources
   - Prevents systematic bias in estimation quality across different lawmakers

## Implementation Priorities

1. Complete the bill sponsorship/cosponsorship analysis
2. Implement public statements analyzer
3. Develop advocacy group ratings collector
4. Create the weighted ensemble integration system
5. Implement confidence scoring and quality monitoring

This approach will ensure that the position estimates are:
- Based on multiple independent data sources
- Not overly reliant on partisanship
- Consistently robust across all lawmakers
- Transparent in their derivation and confidence
