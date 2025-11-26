# Baserow Database Schema Helper Document

This document provides a comprehensive overview of the Baserow database schema used by the Twitter Spotter v4 application. It details each table's purpose, structure, and how they interact with the application.

## Table Overview

The database consists of several interconnected tables that store aircraft registration data, model information, and special interest aircraft. All tables use Baserow's row-based structure with unique IDs.

## 1. Registrations Table (ID: 441094)

**Purpose**: Primary table for tracking all aircraft registrations encountered by the system.

**Fields**:
- `registration` (string): Aircraft registration number (e.g., "N2345D", "EC-NJM")
- `first_seen` (date): Date when the aircraft was first observed
- `last_seen` (date): Date when the aircraft was last observed
- `times_seen` (integer): Count of how many times the aircraft has been observed
- `reason` (string): Optional notes about why the aircraft might be of interest

**Application Usage**:
- Tracks all aircraft that have been spotted by the system
- Used to determine if an aircraft is new (first_seen) or has been seen before
- Helps implement cooldown periods (not posting the same aircraft too frequently)
- Updated each time an aircraft is observed

## 2. Models Table (ID: 441095)

**Purpose**: Contains comprehensive list of aircraft models with their ICAO codes and full names.

**Fields**:
- `model` (string): ICAO aircraft type code (e.g., "A320", "B738", "C172")
- `name` (string): Full aircraft model name (e.g., "Airbus A320", "Boeing 737-800")

**Application Usage**:
- Used to identify standard aircraft models
- Helps determine if an aircraft is interesting based on its model type
- Referenced when checking against interesting models

## 3. Interesting Models Table (ID: 441097)

**Purpose**: Contains aircraft models that should always be considered interesting regardless of registration.

**Fields**:
- `model` (string): ICAO aircraft type code (e.g., "A388", "B77W")
- `name` (string): Full aircraft model name (e.g., "Airbus A380-800", "Boeing 777-300ER")

**Application Usage**:
- Any aircraft matching these models will always trigger a social media post
- Examples include rare or special aircraft types like the A380 or 747-8
- Provides a way to automatically highlight significant aircraft types

## 4. Interesting Registrations Table (ID: 441099)

**Purpose**: Contains specific aircraft registrations that should always be considered interesting.

**Fields**:
- `registration` (string): Aircraft registration number (e.g., "N2345D", "EC-OLE")
- `first_seen` (date): Date when the aircraft was first observed
- `last_seen` (date): Date when the aircraft was last observed
- `times_seen` (integer): Count of how many times the aircraft has been observed
- `reason` (string): Notes explaining why the aircraft is of interest

**Application Usage**:
- Any aircraft with these registrations will always trigger a social media post
- Used for aircraft with special significance (VIP, historical, or unique aircraft)
- The reason field provides context for why the aircraft is interesting

## 5. Excluded Registrations Table (ID: 532140)

**Purpose**: Contains aircraft registrations that should never be posted to social media.

**Fields**:
- `registration` (string): Aircraft registration number to exclude
- `reason` (string): Optional notes about why the aircraft is excluded

**Application Usage**:
- Prevents specific aircraft from being posted regardless of other criteria
- Useful for aircraft that might trigger false positives or are otherwise undesirable

## 6. Common Airlines Table (ID: 532127)

**Purpose**: Tracks airline ICAO codes that have been observed by the system.

**Fields**:
- `Name` (string): Airline name
- `Notes` (string): Additional information about the airline
- `Active` (boolean): Whether the airline is currently active

**Application Usage**:
- Maintains a list of all airlines that have operated flights to/from the tracked airport
- Currently appears to have limited data

## 7. All Models Database Table (ID: 532137)

**Purpose**: Appears to be a duplicate of the Models table (ID: 441095).

**Fields**:
- `model` (string): ICAO aircraft type code
- `name` (string): Full aircraft model name

**Note**: This table appears to be redundant with table ID 441095.

## 8. Table Table (ID: 532190)

**Purpose**: Additional aircraft model database with extended model coverage.

**Fields**:
- `model` (string): ICAO aircraft type code (e.g., "A10", "A124")
- `name` (string): Full aircraft model name (e.g., "Fairchild A10", "Antonov AN-124 Ruslan")

**Note**: This table contains additional aircraft models not found in the primary models table.

## Application Configuration References

The `config.json` file references these tables with the following IDs:
```json
"baserow": {
    "tables": {
        "registrations": 441094,
        "registrations_key": "registration",
        "models": 441095,
        "models_key": "name",
        "interesting_models": 441097,
        "interesting_models_key": "name",
        "interesting_registrations": 441099,
        "interesting_registrations_key": "registration"
    }
}
```

## Data Flow in the Application

1. **New Aircraft Detection**:
   - When a flight with a new registration is detected, it's added to the Registrations table (441094)
   - `first_seen`, `last_seen` are set to current date
   - `times_seen` is set to 1

2. **Existing Aircraft Tracking**:
   - When a previously seen aircraft is detected:
   - `last_seen` is updated to current date
   - `times_seen` is incremented

3. **Interesting Aircraft Identification**:
   - Aircraft are flagged as interesting if:
   - They appear in the Interesting Registrations table (441099)
   - Their model appears in the Interesting Models table (441097)
   - They haven't been seen in over 6 months (cooldown period)
   - They are diverted flights

4. **Exclusion Processing**:
   - Aircraft in the Excluded Registrations table (532140) are never posted

## Maintenance Considerations

1. **Database Cleanup**:
   - Regular review of the Interesting tables to ensure accuracy
   - Periodic review of the Excluded Registrations table to remove outdated entries

2. **Model Database Updates**:
   - The Models tables (441095, 532137, 532190) should be kept synchronized
   - Consider consolidating redundant model tables

3. **Performance Optimization**:
   - For large databases, consider indexing on frequently queried fields like `registration` and `model`

This schema provides a comprehensive system for tracking aircraft sightings and determining which ones should be highlighted on social media based on various criteria.