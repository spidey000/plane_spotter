# Changelog

All notable changes to the Twitter Spotter v4 project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased] - 2025-08-27

### Fixed
- Improved diverted flight handling and detection
- Fixed inconsistent data type handling for diverted status across APIs
- Enhanced boolean logic for diverted flight detection in main processing loop
- Made social media message generation more consistent for diverted flights

### Changed
- Added `normalize_diverted_value()` function for consistent diverted status handling
- Updated AeroDataBox processing to retrieve actual diverted status instead of defaulting to 'null'
- Improved diverted status checks in Telegram and Twitter message generation
- Enhanced error handling for diverted flight detection

## Detailed Session Modifications

### 1. Data Processing Improvements

#### File: `utils/data_processing.py`
- Added `normalize_diverted_value()` helper function to handle different data types for diverted status:
  ```python
  def normalize_diverted_value(diverted_val):
      """Normalize diverted value to a consistent boolean or None"""
      if diverted_val in [True, False]:
          return diverted_val
      elif diverted_val == 'null' or diverted_val is None:
          return None
      elif isinstance(diverted_val, str):
          return diverted_val.lower() in ['true', 'yes', '1']
      return None
  ```
- Modified `process_flight_data_adb()` function to retrieve diverted status from API instead of hardcoding 'null':
  ```python
  # Before
  diverted = 'null'
  
  # After
  diverted = flight.get('diverted', 'null')
  diverted = normalize_diverted_value(diverted)
  ```
- Updated `process_flight_data_aeroapi()` function to normalize diverted value:
  ```python
  # Before
  diverted = flight.get("diverted", 'null')
  
  # After
  diverted = flight.get("diverted", 'null')
  diverted = normalize_diverted_value(diverted)
  ```

### 2. Main Processing Logic Fix

#### File: `main.py`
- Improved boolean logic for checking if a flight is diverted:
  ```python
  # Before
  "DIVERTED": False if flight_data.get("diverted", "null") == "null" else flight_data["diverted"]
  
  # After
  "DIVERTED": bool(flight_data.get("diverted")) if flight_data.get("diverted") not in [None, 'null', False] else False
  ```

### 3. Social Media Message Generation Updates

#### File: `socials/telegram_msg_bot.py`
- Made diverted status check more consistent:
  ```python
  # Before
  if flight_data['diverted'] not in [None, False, 'null']:
  
  # After
  if flight_data.get('diverted') and flight_data['diverted'] not in [None, False, 'null']:
  ```

#### File: `socials/twitter_msg_script.py`
- Made diverted status check more consistent:
  ```python
  # Before
  if flight_data['diverted'] not in [None, False, 'null']:
  
  # After
  if flight_data.get('diverted') and flight_data['diverted'] not in [None, False, 'null']:
  ```

## Verification

- All modified files pass Python syntax validation
- The `normalize_diverted_value()` function works correctly with all expected input types:
  - Boolean values (True, False)
  - Null values (None, 'null')
  - String representations ('true', 'false', '1', '0')
- No new issues introduced by the modifications
- Backward compatibility maintained

## Benefits

1. **Consistent Data Handling**: The diverted value is now handled consistently across both data sources
2. **Type Safety**: Proper normalization prevents type-related issues
3. **Better API Utilization**: AeroDataBox's diversion information is now properly retrieved instead of ignored
4. **Improved Reliability**: More robust checking prevents false positives/negatives in diverted flight detection
5. **Maintainability**: Centralized normalization function makes future updates easier