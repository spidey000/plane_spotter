import asyncio
import json
import sys
import yaml # For pretty printing config
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
from config import config_manager
# Removed dotenv import as we will rely on environment variables passed to the container
# from dotenv import load_dotenv
import os
from log.logger_config import logger
from pytz import timezone


# Add project root to Python path if necessary (adjust if your structure differs)
# sys.path.append(str(Path(__file__).parent.parent))

# Local imports
import utils.data_processing as dp
from api import api_handler_aeroapi, api_handler_aerodatabox
import database.baserow_manager as bm
import socials.socials_processing as sp


# Load initial config to get log settings (this line is kept for initial logger setup if needed, but config will be reloaded)
# config = config_manager.load_config() # This line is removed as config will be loaded in the loop

# --- Main Application Logic ---

async def fetch_and_process_flights(config):
    """Fetches flight data, processes it, checks for interesting flights, and posts to socials."""
    logger.info("Starting flight processing cycle...")
    all_flights = {} # Reset for each cycle

    # Get time range from config
    time_range_hours = config.get('flight', {}).get('time_range_hours', 2)
    use_preloaded = config.get('flight', {}).get('preview_data', False) # Default to False if not set

    now = datetime.utcnow()  # Use timezone-aware UTC time (UTC)
    utc_start_time_dt = now.replace(tzinfo=timezone('UTC'))  # Start from now
    utc_end_time_dt = (now + timedelta(hours=time_range_hours)).replace(tzinfo=timezone('UTC'))
    utc_start_time_str = utc_start_time_dt.strftime('%Y-%m-%dT%H:%M')
    utc_end_time_str = utc_end_time_dt.strftime('%Y-%m-%dT%H:%M')

    madrid_tz = timezone('Europe/Madrid')
    madrid_start_time_str = utc_start_time_dt.astimezone(madrid_tz).strftime('%Y-%m-%dT%H:%M')
    madrid_end_time_str = utc_end_time_dt.astimezone(madrid_tz).strftime('%Y-%m-%dT%H:%M')
    logger.info(f"Processing time range: {madrid_start_time_str} to {madrid_end_time_str} (Spain time)")

    for movement in ['arrivals', 'departures']:
        aeroapi_movement_key = 'scheduled_arrivals' if movement == 'arrivals' else 'scheduled_departures'
        temp_aeroapi_data = None
        temp_adb_data = None

        # --- Data Fetching ---
        if use_preloaded:
            logger.warning("Using preloaded data files (api.preloaded_data = true)")
            aeroapi_file = Path(f'api/data/aeroapi_data_{aeroapi_movement_key}.json')
            adb_file = Path(f'api/data/adb_data_{movement}.json')
            try:
                if aeroapi_file.exists():
                    with open(aeroapi_file, 'r') as f:
                        temp_aeroapi_data = json.load(f)
                    logger.info(f"Loaded preloaded AeroAPI data for {movement}")
                else:
                     logger.warning(f"Preloaded AeroAPI file not found: {aeroapi_file}")

                if adb_file.exists():
                    with open(adb_file, 'r') as f:
                        temp_adb_data = json.load(f)
                    logger.info(f"Loaded preloaded AeroDataBox data for {movement}")
                else:
                    logger.warning(f"Preloaded AeroDataBox file not found: {adb_file}")

            except Exception as e:
                logger.exception(f"Error loading preloaded data files for {movement}: {e}")
                # Decide if we should stop or continue without preloaded data
                # For now, let's try API if preloaded failed partially
                use_preloaded = False # Fallback to API if loading failed

        if not temp_aeroapi_data or not temp_adb_data: # Fetch if not preloaded or preloading failed
             logger.info(f"Fetching live API data for {movement}")
             try:
                 # Use await for async API calls
                 logger.info(f"Fetching AeroAPI data for {utc_start_time_str} to {utc_end_time_str}")
                 aero_task = api_handler_aeroapi.fetch_aeroapi_scheduled(aeroapi_movement_key, utc_start_time_str, utc_end_time_str, config)
                 logger.info(f"Fetching AeroDataBox data for {madrid_start_time_str} to {madrid_end_time_str}")
                 adb_task = api_handler_aerodatabox.fetch_adb_data(movement, madrid_start_time_str, madrid_end_time_str, config)
                 results = await asyncio.gather(aero_task, adb_task, return_exceptions=True)

                 if isinstance(results[0], Exception):
                     logger.error(f"Error fetching AeroAPI data: {results[0]}")
                 else:
                     temp_aeroapi_data = results[0]

                 if isinstance(results[1], Exception):
                     logger.error(f"Error fetching AeroDataBox data: {results[1]}")
                 else:
                     temp_adb_data = results[1]

             except Exception as e:
                 logger.exception(f"Critical error during API fetching for {movement}: {e}")
                 # Continue to next movement or stop cycle? For now, continue.

        # --- Data Processing ---
        if temp_adb_data and movement in temp_adb_data:
            logger.info(f"Processing {len(temp_adb_data[movement])} flights from AeroDataBox for {movement}")
            for flight in temp_adb_data[movement]:
                try:
                    processed_data = dp.process_flight_data_adb(flight, movement, config)
                    dp.check_existing(all_flights, processed_data) # Add/update in our combined dict
                except Exception as e:
                    logger.error(f"Error processing ADB flight {flight.get('number', 'N/A')}: {e}")
                    continue # Skip this flight

        if temp_aeroapi_data and aeroapi_movement_key in temp_aeroapi_data:
             logger.info(f"Processing {len(temp_aeroapi_data[aeroapi_movement_key])} flights from AeroAPI for {movement}")
             for flight in temp_aeroapi_data[aeroapi_movement_key]:
                 try:
                     processed_data = dp.process_flight_data_aeroapi(flight, config)
                     dp.check_existing(all_flights, processed_data) # Add/update
                 except Exception as e:
                     logger.error(f"Error processing AeroAPI flight {flight.get('ident', 'N/A')}: {e}\nError details: {str(e)}\nFlight data: {json.dumps(flight, indent=2)}")
                     continue # Skip this flight

    logger.info(f"Total unique flights identified in cycle: {len(all_flights)}")

    # Use os.path.join for cross-platform path handling
    with open(os.path.join(os.getcwd(), ".all_flights.json"), 'w') as f:
        json.dump(all_flights, f, indent=4, default=str)
    logger.info(f"Saved all flights data to .all_flights.json")

    # --- create a set with all common airlines ---
        # Create set of airline ICAO codes
    airline_icao_set = {flight.get('airline', '').upper() for flight in all_flights.values() if flight.get('airline') not in [None, 'null']}
    
    # Path to common_airlines file using os.path.join for cross-platform compatibility
    common_airlines_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'twitter_spotter_v4', 'database', 'common_airlines.json')
    try:
        # Load existing airlines if file exists
        existing_airlines = set()
        if not os.path.exists(common_airlines_path):
            # Create the directory if it does not exist
            os.makedirs(os.path.dirname(common_airlines_path), exist_ok=True)
            # Create the file and write an empty list to it
            with open(common_airlines_path, 'w') as f:
                json.dump([], f, indent=2)
        
        with open(common_airlines_path, 'r') as f:
            existing_airlines = set(json.load(f))
        # Combine existing airlines with the new ones
        combined_airlines = existing_airlines.union(airline_icao_set)

        logger.info(f"New airlines: {len(existing_airlines)-len(airline_icao_set)}")
        logger.info(f"Combined airlines: {len(combined_airlines)}")
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(common_airlines_path), exist_ok=True)
        
        # Save the combined set back to the file
        try:
            with open(common_airlines_path, 'w') as f:
                json.dump(list(combined_airlines), f, indent=2)
                logger.info(f"Updated common airlines file with {len(airline_icao_set)} new ICAO codes. Total unique airlines: {len(combined_airlines)}")
        except Exception as write_error:
            logger.error(f"Failed to write to common airlines file: {write_error}")
    except Exception as e:
        logger.error(f"Failed to update common airlines file: {e}")

    # --- Database Interaction and Social Posting ---
    if not all_flights:
        logger.info("No flights processed in this cycle.")
        return # Nothing more to do

    try:
        # Get DB data (consider caching this for short periods if performance is an issue)
        reg_table_id = config['baserow']['tables']['registrations']
        model_table_id = config['baserow']['tables']['models'] # we use the complete model table not the interesting ones
        model_table_key = config.get('database', {}).get('model_table_key', 'model') # Default key
        interesting_model_table_id = config['baserow']['tables']['interesting_models']
        interesting_reg_table_id = config['baserow']['tables']['interesting_registrations']

        if not reg_table_id or not model_table_id:
             logger.error("Database table IDs not configured. Cannot check flights.")
             return

        # Check if caching is enabled
        enable_caching = config.get('database', {}).get('enable_caching', True)
        cache_ttl = config.get('database', {}).get('cache_ttl_seconds', 300)
        
        if enable_caching:
            logger.info(f"Using cached database queries with TTL of {cache_ttl} seconds")
            reg_db_task = bm.get_cached_all_rows_as_dict(reg_table_id, config, ttl_seconds=cache_ttl)
            model_db_task = bm.get_cached_all_rows_as_dict(model_table_id, config, key=model_table_key, ttl_seconds=cache_ttl)
            interesting_model_table_task = bm.get_cached_all_rows_as_dict(interesting_model_table_id, config, key=model_table_key, ttl_seconds=cache_ttl)
            interesting_reg_table_task = bm.get_cached_all_rows_as_dict(interesting_reg_table_id, config, ttl_seconds=cache_ttl)
        else:
            logger.info("Caching disabled, using direct database queries")
            reg_db_task = bm.get_all_rows_as_dict(reg_table_id, config)
            model_db_task = bm.get_all_rows_as_dict(model_table_id, config, key=model_table_key)
            interesting_model_table_task = bm.get_all_rows_as_dict(interesting_model_table_id, config, key=model_table_key)
            interesting_reg_table_task = bm.get_all_rows_as_dict(interesting_reg_table_id, config)
            
        db_results = await asyncio.gather(reg_db_task, model_db_task, interesting_reg_table_task, interesting_model_table_task, return_exceptions=True)

        if isinstance(db_results[0], Exception):
            logger.error(f"Error fetching registration DB data: {db_results[0]}")
            reg_db_copy = {} # Proceed without DB check? Or stop? For now, empty dict.
        else:
            reg_db_copy = db_results[0]

        if isinstance(db_results[1], Exception):
            logger.error(f"Error fetching model DB data: {db_results[1]}")
            model_db_copy = {}
        else:
            model_db_copy = db_results[1]

        if isinstance(db_results[2], Exception):
            logger.error(f"Error fetching model DB data: {db_results[1]}")
            interesting_reg_db_copy = {}
        else:
            interesting_reg_db_copy = db_results[2]

        if isinstance(db_results[3], Exception):
            logger.error(f"Error fetching interesting model DB data: {db_results[3]}")
            interesting_model_db_copy = {}
        else:
            interesting_model_db_copy = db_results[3]

        # Log cache statistics
        try:
            from database.cache_manager import cache_manager
            cache_stats = cache_manager.get_stats()
            logger.info(f"Database cache statistics: {cache_stats}")
        except Exception as e:
            logger.debug(f"Could not retrieve cache statistics: {e}")

        logger.info(f"Checking {len(all_flights)} flights against database...")
        social_tasks = []

        for flight_key, flight_details in all_flights.items():
            try:
                # Check flight against DB rules
                flight_data, interesting_registration, interesting_model, first_seen, reason, seen_recently = await dp.check_flight(
                    flight_details, reg_db_copy, interesting_reg_db_copy, model_db_copy, interesting_model_db_copy, config
                )

                # Determine if interesting based on aircraft type, registration, or timing
                interesting_reasons = {
                    "MODEL": interesting_model,
                    "REGISTRATION": interesting_registration,
                    "FIRST_SEEN": first_seen,
                    "DIVERTED": bool(flight_data.get("diverted")) if flight_data.get("diverted") not in [None, 'null', False] else False,
                    "RETURNED_AFTER_6_MONTHS": not seen_recently and not first_seen,  # Aircraft hasn't been seen in 6+ months
                    "REASON": reason
                }
                
                # Check if we should post this aircraft
                should_post = (
                    first_seen or  # Always post new aircraft
                    interesting_registration or  # Always post interesting registrations
                    interesting_model or  # Always post interesting models
                    (interesting_reasons["DIVERTED"]) or  # Always post diverted flights
                    (not seen_recently and not first_seen)  # Post if not seen in 6+ months
                )

                # Handle posting decision
                if should_post:
                    reasons_str = ", ".join([k for k, v in interesting_reasons.items() if v and k != "REASON"])
                    if reason:
                        reasons_str += f", {reason}"
                    flight_name_display = flight_data.get('flight_name') if flight_data.get('flight_name') != 'null' else flight_data.get('flight_name_iata', 'N/A')
                    logger.info(f"Flight {flight_name_display} ({flight_data.get('registration', 'N/A')}) is interesting ({reasons_str}). Queueing social post.")
                    
                    # Queue the social media posting task
                    social_tasks.append(sp.call_socials(flight_data, interesting_reasons, config)) # Pass config
                elif seen_recently:
                    flight_name_display = flight_data.get('flight_name') if flight_data.get('flight_name') != 'null' else flight_data.get('flight_name_iata', 'N/A')
                    logger.info(f"Skipping {flight_name_display} ({flight_data.get('registration', 'N/A')}) - seen recently within 6 months")

            except Exception as e:
                logger.exception(f"Error checking flight {flight_key}: {e}")
                continue # Skip this flight

        if social_tasks:
            logger.info(f"Sending {len(social_tasks)} posts to social media...")
            # Run social posting tasks concurrently
            for task in social_tasks:
                try:
                    await task
                except Exception as e:
                    logger.exception(f"Error sending social media post: {e}")
            logger.info("Finished sending social media posts.")
        else:
            logger.info("No interesting flights found to post.")

    except Exception as e:
        logger.exception(f"Error during database check or social posting phase: {e}")

    logger.info("Finished flight processing cycle.")

async def sleep_until_4am(hour_24h_format):
    """Sleep until with a countdown display."""
    now = datetime.utcnow()

    # Calculate wake time for the target hour
    wake_time = now.replace(hour=hour_24h_format, minute=0, second=0, microsecond=0)
    # If current time is already past the target hour, schedule for next day
    # Calculate total seconds to sleep
    sleep_duration = (wake_time - now).total_seconds()

    logger.info(f"Sleeping until {hour_24h_format}UTC ({wake_time.strftime('%H:%M')})")
    print(f"Timecheck: {now.strftime('%H:%M')}")
    print(f"Total sleep duration: {timedelta(seconds=sleep_duration)}")

async def main_loop():
    """Runs the main flight processing cycle periodically with a pause between 0am and 4am."""
    while True:
        # current_hour = datetime.utcnow().hour
        # # hours are in utc time
        # hour_gap = config['settings']['hour_gap']
        # if hour_gap[0] <= current_hour < hour_gap[1]:
        #     await sleep_until_4am(hour_gap[1])
        #     continue
        # else:
        # Reload config inside the loop to pick up changes
        current_config = config_manager.load_config()
        await fetch_and_process_flights(current_config)

        # Get interval from config *inside* the loop to pick up changes
        interval = current_config['execution']['interval']
        if not isinstance(interval, (int, float)) or interval <= 0:
            logger.warning(f"Invalid or missing execution.interval in config. Using default 120 minutes.")
            interval = 7200  # Default to 120 minutes in seconds
        
        logger.info(f"Next processing cycle starts in {timedelta(seconds=interval)} at {(datetime.now()+timedelta(seconds=interval)).strftime('%H:%M')}")
        await asyncio.sleep(interval)
    
asyncio.run(main_loop())
