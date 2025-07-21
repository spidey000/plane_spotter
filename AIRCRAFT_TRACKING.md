# Aircraft Tracking System Documentation

## Overview
This system tracks aircraft arrivals and departures at a specific airport and posts interesting sightings to social media platforms. The core principle is to track individual aircraft by their registration (tail number), not by flight number.

## Expected Behavior

### Aircraft Tracking Logic
1. **Registration-Based Tracking**: Each aircraft is uniquely identified by its registration number
2. **First Sighting**: When an aircraft with a new registration is detected, it's marked as "FIRST_SEEN" and posted to social media
3. **Subsequent Sightings**: When the same aircraft is seen again:
   - The system tracks each sighting in the database
   - Updates `last_seen` timestamp and increments `times_seen` counter
   - Posts to social media only if it hasn't been seen in the last 6 months

### Interesting Aircraft Override
- Aircraft in the "interesting registrations" table are posted EVERY time they're seen
- This allows manual curation of special aircraft (VIP jets, rare planes, etc.)
- Useful for tracking specific high-value aircraft movements

## System Flow

### 1. Data Collection
- Fetches flight data from AeroDataBox and AeroAPI
- Processes arrivals and departures for configured time window
- Merges data from both APIs to get complete flight information

### 2. Flight Processing
- Deduplicates flights within the current processing cycle
- Extracts aircraft registration, flight details, and aircraft type
- Handles cases where registration might be missing

### 3. Database Checking
- Queries Baserow database for known registrations
- Checks if aircraft is in "interesting registrations" table
- Checks if aircraft model is interesting or unknown
- Checks when aircraft was last posted to prevent duplicates

### 4. Decision Logic
Aircraft is posted if ANY of these conditions are met AND cooldown rules allow:
- **FIRST_SEEN**: Registration not in database (new aircraft)
- **INTERESTING_REGISTRATION**: Aircraft manually marked as interesting (always posted)
- **INTERESTING_MODEL**: Aircraft type is rare or not in model database
- **DIVERTED**: Flight has been diverted from original destination

### 5. Cooldown System
- **Regular Aircraft**: Posted only if not seen in the last 6 months (configurable)
- **Interesting Registrations**: Always posted, regardless of when last seen
- **Last Seen Tracking**: Database tracks when each aircraft was last detected

### 6. Social Media Posting
- Posts to enabled platforms (Twitter, Telegram, Instagram, etc.)
- Downloads aircraft photo if available
- Formats message with flight details and tracking reasons

### 7. Database Updates
- Creates new record for first-seen aircraft
- Updates `last_seen` and `times_seen` for known aircraft
- Maintains historical tracking data for long-term analysis

## Key Features

### Multi-API Integration
- **AeroDataBox**: Live flight tracking data
- **AeroAPI**: Scheduled flight information
- Combines data sources for comprehensive coverage

### Smart Deduplication
- Within-cycle: Prevents same flight from multiple APIs being processed twice
- Cross-cycle: Prevents same aircraft being posted multiple times per day
- Registration-based: Tracks aircraft, not flight numbers

### Flexible Social Media Support
- Twitter, Telegram, Instagram, Threads, LinkedIn, Bluesky
- Individual platform error handling
- Automatic image fetching and attribution

### Aircraft Photo Integration
- Searches JetPhotos and Planespotters automatically
- Downloads and processes images
- Adds photographer attribution

### Configurable Operation
- Time windows for flight data
- Social platform enabling/disabling
- Airport and timezone configuration
- Execution intervals

## Data Storage

### Baserow Database Tables
1. **registrations**: All seen aircraft with tracking data
2. **interesting_registrations**: Manually curated aircraft to always post
3. **models**: Known aircraft types
4. **interesting_models**: Rare or noteworthy aircraft types

### Temporary Files
- `.all_flights.json`: Current cycle flight data (debugging)
- API cache files: Reduce API calls during development
- `temp_image.jpg`: Downloaded aircraft photos

## Configuration
The system behavior is controlled through `config/config.json`:
- Airport settings (ICAO code, timezone)
- Social media platform credentials and settings
- Database table IDs
- Processing intervals and time windows
- Posting cooldown period (`posting_cooldown_hours` - default 4320 = 6 months)
- Feature flags (preview data, debug modes)

## Error Handling
- Graceful degradation when APIs are unavailable
- Individual social media platform error isolation
- Database connection retry logic
- Comprehensive logging for troubleshooting