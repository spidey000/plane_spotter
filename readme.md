# Twitter Spotter v4

## File Tree
```
twitter_spotter_v4/
├── main.py
├── readme.md
├── requirements.txt
├── twikit_documentation.md
├── api/
│   ├── api_handler_aeroapi.py
│   ├── api_handler_aerodatabox.py
│   └── data/
├── config/
│   └── config.yaml
├── database/
│   ├── database.md
│   ├── flights.db
│   ├── planes.db
│   └── scheduled_messages.db
├── logs/
├── socials/
│   ├── bluesky.py
│   ├── instagram.py
│   ├── linkedin.py
│   ├── socials_processing.py
│   ├── telegram.py
│   ├── threads.py
│   └── twitter.py
├── test/
│   ├── adb_test_data.json
│   ├── test_apis.py
│   ├── test_database.py
│   └── test_processing.py
└── utils/
    ├── data_processing.py
    └── image_finder.py
```

## File Contexts

### API Integrations

#### AeroAPI Handler
The AeroAPI handler (api_handler_aeroapi.py) provides functionality to fetch scheduled flight data. Key features:

- Uses aiohttp for asynchronous HTTP requests
- Fetches arrival/departure data for specified time range
- Handles pagination of API responses
- Implements rate limiting with 11-second delays between requests
- Saves raw API responses to JSON files
- Uses logging for error handling and debugging

#### Example Usage
```python
from api.api_handler_aeroapi import fetch_scheduled

# Fetch arrivals data
arrivals = await fetch_scheduled("arrivals", start_time, end_time)

# Fetch departures data
departures = await fetch_scheduled("departures", start_time, end_time)
```

#### AeroDataBox API Handler
The AeroDataBox handler (api_handler_aerodatabox.py) provides functionality to fetch flight data. Key features:

- Uses aiohttp for asynchronous HTTP requests
- Supports both arrival and departure data
- Includes comprehensive query parameters for filtering flights
- Saves raw API responses to JSON files
- Implements robust error handling and logging

#### Example Usage
```python
from api.api_handler_aerodatabox import fetch_data

# Fetch arrival data
arrivals = await fetch_data("arrival", start_time, end_time)

# Fetch departure data
departures = await fetch_data("departure", start_time, end_time)
```

# Twitter Spotter v4

## File Tree
```
twitter_spotter_v4/
├── main.py
├── readme.md
├── requirements.txt
├── twikit_documentation.md
├── api/
│   ├── api_handler_aeroapi.py
│   ├── api_handler_aerodatabox.py
│   └── data/
├── config/
│   └── config.yaml
├── database/
│   ├── database.md
│   ├── flights.db
│   ├── planes.db
│   └── scheduled_messages.db
├── logs/
├── socials/
│   ├── bluesky.py
│   ├── instagram.py
│   ├── linkedin.py
│   ├── socials_processing.py
│   ├── telegram.py
│   ├── threads.py
│   └── twitter.py
├── test/
│   ├── adb_test_data.json
│   ├── test_apis.py
│   ├── test_database.py
│   └── test_processing.py
└── utils/
    ├── data_processing.py
    └── image_finder.py
```

## File Contexts

### Main Application Workflow

The main.py file orchestrates the following workflow:

1. Load flight information from APIs
2. For each flight:
   - Clean and process data using utils.data_processing
   - Store flight data in database
   - Check if plane exists in database
     - If not, store plane information
   - Generate social media messages using socials_processing
   - Schedule messages and store in scheduled_messages.db

The application integrates with multiple APIs and social media platforms to track flights and schedule relevant posts.

### Twitter Integration

The Twitter functionality uses the Twikit library for scheduling tweets. Key features:

- Tweets are scheduled based on flight data
- Includes flight information and a follow prompt
- Automatically attaches relevant images when available
- Uses Twikit's async client for scheduling

#### Dependencies
- twikit (see twikit_documentation.md for setup)
- socials_processing.py for text generation
- utils.image_finder.py for image selection

#### Example Usage
```python
from socials.twitter import schedule_tweet

# Initialize with flight data
await schedule_tweet(client, flight_data)
```

### Testing

The test directory contains test data and test scripts to verify the application's functionality.

#### Test Data
The test/adb_test_data.json file contains sample flight data used for testing the AeroDataBox API handler. The data structure includes:

- Flight movements (arrivals/departures)
- Airport information (ICAO, IATA, name, timezone)
- Scheduled and revised times
- Aircraft details (registration, model)
- Airline information
- Flight status and codeshare information

This test data allows for comprehensive testing of the flight data processing pipeline without making actual API calls.

#### Test Scripts
The test directory includes several test scripts:

- test_apis.py: Tests API handlers and data processing
- test_database.py: Tests database operations and schemas
- test_processing.py: Tests data processing utilities

### Data Processing Utilities

The utils/data_processing.py file contains functions for processing flight data:

- Loads flight data from multiple APIs
- Compares flights by flight_name across different API responses
- Merges the most complete information from different sources
- Stores the processed data in the database
- Handles data normalization and cleaning

These utilities ensure consistent and accurate flight data is stored in the database, even when information comes from different sources.

### Database Schemas

#### flights.db
```sql
CREATE TABLE flights (
    flight_name TEXT PRIMARY KEY,
    registration TEXT,
    aircraft TEXT,
    airline TEXT,
    origin_icao TEXT,
    destination_icao TEXT,
    scheduled_time DATETIME,
    last_update DATETIME
);
```

#### planes.db
```sql
CREATE TABLE planes (
    registration TEXT PRIMARY KEY,
    first_seen DATETIME,
    last_seen DATETIME,
    times_seen INTEGER,
    interest_reason TEXT
);
```

#### scheduled_messages.db
```sql
CREATE TABLE scheduled_messages (
    flight_name+shceduled_time TEXT PRIMARY KEY,
    platform TEXT,
    scheduled_time DATETIME,
    text TEXT
);
```
