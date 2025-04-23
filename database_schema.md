# Database Schema for Political Alignment Tool

This document outlines the database schema for the political alignment tool that matches users with representatives based on their positions on various policy issues.

## Overview

The database is designed to efficiently store and query:
- Representatives' information and metadata
- Policy areas and specific questions
- Representatives' positions on each question
- User responses and their alignment scores

## Tables

### 1. Representatives

```sql
CREATE TABLE representatives (
    id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    state TEXT NOT NULL,
    district TEXT,  -- NULL for senators
    chamber TEXT NOT NULL,  -- 'House' or 'Senate'
    party TEXT NOT NULL,
    term_start DATE NOT NULL,
    term_end DATE NOT NULL,
    bioguide_id TEXT UNIQUE,  -- Congress.gov identifier
    voteview_id TEXT UNIQUE,  -- Rvoteview identifier
    official_website TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. PolicyAreas

```sql
CREATE TABLE policy_areas (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    active BOOLEAN DEFAULT TRUE
);
```

### 3. Questions

```sql
CREATE TABLE questions (
    id INTEGER PRIMARY KEY,
    policy_area_id INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    source TEXT,  -- e.g., 'GSS2022 LETIN1A'
    active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (policy_area_id) REFERENCES policy_areas(id)
);
```

### 4. ResponseOptions

```sql
CREATE TABLE response_options (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL,
    option_text TEXT NOT NULL,
    score INTEGER NOT NULL,  -- -3 to +3 scale
    FOREIGN KEY (question_id) REFERENCES questions(id)
);
```

### 5. RepresentativePositions

```sql
CREATE TABLE representative_positions (
    id INTEGER PRIMARY KEY,
    representative_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    response_option_id INTEGER,
    score INTEGER,  -- -3 to +3 scale
    confidence REAL,  -- 0.0 to 1.0 indicating confidence in the position assessment
    source_type TEXT,  -- 'vote', 'statement', 'inference', etc.
    source_url TEXT,
    source_date DATE,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (representative_id) REFERENCES representatives(id),
    FOREIGN KEY (question_id) REFERENCES questions(id),
    FOREIGN KEY (response_option_id) REFERENCES response_options(id),
    UNIQUE (representative_id, question_id)
);
```

### 6. VotingRecords

```sql
CREATE TABLE voting_records (
    id INTEGER PRIMARY KEY,
    representative_id INTEGER NOT NULL,
    congress_number INTEGER NOT NULL,
    bill_number TEXT NOT NULL,
    bill_title TEXT,
    vote_date DATE NOT NULL,
    vote TEXT NOT NULL,  -- 'Yea', 'Nay', 'Present', 'Not Voting'
    FOREIGN KEY (representative_id) REFERENCES representatives(id),
    UNIQUE (representative_id, congress_number, bill_number)
);
```

### 7. BillQuestionMapping

```sql
CREATE TABLE bill_question_mapping (
    id INTEGER PRIMARY KEY,
    bill_number TEXT NOT NULL,
    congress_number INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    yea_score INTEGER NOT NULL,  -- Score to assign if voted 'Yea'
    nay_score INTEGER NOT NULL,  -- Score to assign if voted 'Nay'
    confidence REAL NOT NULL,  -- 0.0 to 1.0 indicating confidence in this mapping
    FOREIGN KEY (question_id) REFERENCES questions(id),
    UNIQUE (bill_number, congress_number, question_id)
);
```

### 8. Users (Optional - for web application)

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    email TEXT UNIQUE,
    password_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 9. UserResponses (Optional - for web application)

```sql
CREATE TABLE user_responses (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    question_id INTEGER NOT NULL,
    response_option_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    importance INTEGER DEFAULT 1,  -- 1-5 scale for weighting
    response_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (question_id) REFERENCES questions(id),
    FOREIGN KEY (response_option_id) REFERENCES response_options(id)
);
```

### 10. UserRepresentativeAlignment (Optional - for web application)

```sql
CREATE TABLE user_representative_alignment (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    representative_id INTEGER NOT NULL,
    overall_alignment_score REAL,  -- -1.0 to 1.0 where 1.0 is perfect alignment
    policy_area_scores TEXT,  -- JSON string with scores by policy area
    calculation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (representative_id) REFERENCES representatives(id)
);
```

## Indexes

```sql
-- Indexes for faster queries
CREATE INDEX idx_rep_positions_rep_id ON representative_positions(representative_id);
CREATE INDEX idx_rep_positions_question_id ON representative_positions(question_id);
CREATE INDEX idx_questions_policy_area ON questions(policy_area_id);
CREATE INDEX idx_voting_records_rep_id ON voting_records(representative_id);
CREATE INDEX idx_voting_records_bill ON voting_records(congress_number, bill_number);
CREATE INDEX idx_bill_mapping_bill ON bill_question_mapping(congress_number, bill_number);
CREATE INDEX idx_bill_mapping_question ON bill_question_mapping(question_id);
```

## Initial Data Population

The database will be initially populated with:

1. Current representatives from the House and Senate
2. Policy areas from the example questions (Immigration, Vaccination, Abortion)
3. Questions and response options from the provided examples
4. Relevant voting records from Congress.gov API and Rvoteview

## Data Update Strategy

- Representatives table: Update after elections or when changes occur
- Voting records: Update when new votes are cast
- Representative positions: Update based on new votes or statements
- Bill-question mappings: Add manually or through semi-automated analysis

## Schema Flexibility

This schema is designed to be flexible and extensible:
- New policy areas can be added easily
- Questions can be marked as active/inactive without deletion
- The confidence field allows for representing uncertainty in position assessments
- Multiple data sources can be integrated through the source fields
