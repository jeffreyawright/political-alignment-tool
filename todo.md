# Political Alignment Tool Implementation Todo

## Current Status
The Political Alignment Tool currently has partial implementation of data collection from Congress.gov API and Rvoteview for voting records and bill sponsorships. We need to enhance these components and implement new data sources to create a comprehensive position estimation system.

## Tasks

### Data Sources Definition
- [x] Define comprehensive data sources for position estimation
- [x] Document integration methodology for multiple data sources
- [x] Outline implementation priorities

### Congress API Integration Enhancement
- [ ] Improve bill-to-question mapping with better relevance scoring
- [ ] Implement confidence weighting for votes based on relevance
- [ ] Enhance bill sponsorship/cosponsorship analysis
- [ ] Expand historical vote collection for better pattern analysis

### Public Statements Analyzer
- [ ] Create public_statements_analyzer.py module
- [ ] Implement web scraping for official websites and press releases
- [ ] Implement NLP techniques for content analysis
- [ ] Develop scoring system to map statements to questions
- [ ] Implement confidence scoring based on statement relevance

### Advocacy Group Ratings Collector
- [ ] Create advocacy_ratings_collector.py module
- [ ] Implement scrapers for major advocacy group websites
- [ ] Develop normalization system for diverse rating scales
- [ ] Create mapping between organization focus and survey questions
- [ ] Implement confidence weighting based on organization relevance

### Position Estimation Algorithm
- [ ] Develop weighted ensemble approach for data integration
- [ ] Implement source-specific position estimation
- [ ] Create confidence calculation system
- [ ] Ensure balanced coverage across lawmakers
- [ ] Build fallback strategies for lawmakers with limited data

### Testing and Validation
- [ ] Test with sample lawmakers from different parties
- [ ] Validate estimation accuracy against known positions
- [ ] Ensure balanced quality across all lawmakers
- [ ] Verify system works without relying heavily on partisanship

### Documentation
- [ ] Update README with new components
- [ ] Document API usage for new data sources
- [ ] Create usage examples for the enhanced system
- [ ] Provide guidance on customization and extension
