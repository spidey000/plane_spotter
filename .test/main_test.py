# -*- coding: utf-8 -*-
import asyncio
import json
import sys
import yaml  # For pretty printing config (can be removed if not needed elsewhere)
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
from typing import Dict, Any, Tuple, Optional, List

# --- Load Configuration and Environment Variables ---
# Load early to potentially configure logging paths based on config
try:
    from config import config_manager
    from dotenv import load_dotenv
    import os

    # Load .env file first
    load_dotenv()

    # Load config.json
    config = config_manager.load_config()

    # Access configuration parameters (use .get for resilience)
    FLIGHT_TIME_RANGE_HOURS = config.get('flight', {}).get('time_range_hours', 2) # Default 2 hours
    USE_PRELOADED_DATA = config.get('flight', {}).get('preview_data', False)
    EXECUTION_INTERVAL_SECONDS = config.get('execution', {}).get('interval', 6600) # Default 110 mins

    DB_REG_TABLE_ID = config.get('baserow', {}).get('tables', {}).get('registrations')
    DB_MODEL_TABLE_ID = config.get('baserow', {}).get('tables', {}).get('interesting_models')
    DB_INTERESTING_REG_TABLE_ID = config.get('baserow', {}).get('tables', {}).get('interesting_registrations')
    DB_MODEL_KEY_FIELD = config.get('baserow', {}).get('model_key_field', 'model') # Key field in model table

    LOG_FILE = config.get('logging', {}).get('log_file', 'logs/app.log')
    WARN_LOG_FILE = config.get('logging', {}).get('warning_log_file', 'logs/app.warn.log')
    LOG_LEVEL = config.get('logging', {}).get('log_level', 'INFO')
    LOG_ROTATION = config.get('logging', {}).get('log_rotation', '10 MB')

except ImportError as e:
    print(f"Error importing required modules: {e}. Ensure config_manager and dotenv are available.", file=sys.stderr)
    sys.exit(1)
except KeyError as e:
    print(f"Error: Missing expected key in configuration: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Error during initial configuration loading: {e}", file=sys.stderr)
    sys.exit(1)

# --- Local Imports (After ensuring config is loaded) ---
try:
    import utils.data_processing as dp
    from api import api_handler_aeroapi, api_handler_aerodatabox
    import database.baserow_manager as bm
    import socials.socials_processing as sp
except ImportError as e:
    # Logger might not be initialized yet, print to stderr
    print(f"Error importing local modules (utils, api, database, socials): {e}", file=sys.stderr)
    sys.exit(1)

# --- Logger Setup ---
def setup_logging(log_file: str, warn_log_file: str, level: str, rotation: str):
    """Configures the Loguru logger."""
    try:
        logger.remove() # Remove default handler
        log_dir = Path(log_file).parent
        warn_log_dir = Path(warn_log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        warn_log_dir.mkdir(parents=True, exist_ok=True)

        logger.add(log_file, level=level.upper(), enqueue=True, rotation=rotation, backtrace=True, diagnose=True)
        if warn_log_file != log_file:
            logger.add(warn_log_file, level="WARNING", enqueue=True, rotation=rotation, backtrace=True, diagnose=True)
        logger.add(sys.stdout, level="INFO") # Keep console output for INFO+
        logger.info("Logger initialized successfully.")

    except Exception as e:
        # Fallback basic logger if setup fails
        print(f"CRITICAL Error initializing logger: {e}", file=sys.stderr)
        logger.remove()
        logger.add(sys.stderr, level="INFO")
        logger.error("Failed to configure logger from config file. Using stderr.")

# Call logger setup immediately after defining it
setup_logging(LOG_FILE, WARN_LOG_FILE, LOG_LEVEL, LOG_ROTATION)
# --- End Logger Setup ---


# --- Helper Functions (Copied from previous version, unchanged) ---

def calculate_time_range(time_range_hours: float) -> Tuple[datetime, datetime, str, str]:
    """Calculates the start and end datetime objects and formatted strings."""
    now = datetime.now()
    start_time_dt = now
    end_time_dt = now + timedelta(hours=time_range_hours)
    start_time_str = start_time_dt.strftime('%Y-%m-%dT%H:%M')
    end_time_str = end_time_dt.strftime('%Y-%m-%dT%H:%M')
    return start_time_dt, end_time_dt, start_time_str, end_time_str

async def fetch_specific_flight_data(
    movement: str,
    start_time_str: str,
    end_time_str: str,
    use_preloaded: bool
) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Fetches flight data for a specific movement (arrivals/departures)
    from preloaded files or live APIs.

    Returns:
        Tuple[Optional[Dict], Optional[Dict]]: (aeroapi_data, adb_data)
    """
    aeroapi_movement_key = 'scheduled_arrivals' if movement == 'arrivals' else 'scheduled_departures'
    aeroapi_data: Optional[Dict] = None
    adb_data: Optional[Dict] = None

    # --- Attempt Preloaded Data ---
    if use_preloaded:
        logger.warning(f"Attempting to use preloaded data files for {movement}")
        aeroapi_file = Path(f'api/data/aeroapi_data_{aeroapi_movement_key}.json')
        adb_file = Path(f'api/data/adb_data_{movement}.json')
        try:
            if aeroapi_file.exists():
                with open(aeroapi_file, 'r') as f:
                    aeroapi_data = json.load(f)
                logger.info(f"Loaded preloaded AeroAPI data for {movement}")
            else:
                logger.warning(f"Preloaded AeroAPI file not found: {aeroapi_file}")

            if adb_file.exists():
                with open(adb_file, 'r') as f:
                    adb_data = json.load(f)
                logger.info(f"Loaded preloaded AeroDataBox data for {movement}")
            else:
                logger.warning(f"Preloaded AeroDataBox file not found: {adb_file}")

        except Exception as e:
            logger.exception(f"Error loading preloaded data files for {movement}: {e}. Will attempt live API.")
            aeroapi_data = None # Reset on error to trigger API fetch
            adb_data = None

    # --- Fetch Live API Data (if needed) ---
    if aeroapi_data is None or adb_data is None:
        if use_preloaded:
            logger.warning(f"Preloaded data incomplete or failed loading for {movement}. Fetching live API data.")
        else:
            logger.info(f"Fetching live API data for {movement} ({start_time_str} to {end_time_str})")

        try:
            aero_task = asyncio.create_task(api_handler_aeroapi.fetch_aeroapi_scheduled(aeroapi_movement_key, start_time_str, end_time_str))
            adb_task = asyncio.create_task(api_handler_aerodatabox.fetch_adb_data(movement, start_time_str, end_time_str))
            results = await asyncio.gather(aero_task, adb_task, return_exceptions=True)

            # Process AeroAPI results
            if isinstance(results[0], Exception):
                logger.error(f"Error fetching AeroAPI data for {movement}: {results[0]}")
            elif results[0] is not None: # Check if API returned data
                aeroapi_data = results[0] # Assign successful API result
                logger.debug(f"Successfully fetched AeroAPI data for {movement}")
            else:
                logger.warning(f"AeroAPI returned no data for {movement}")


            # Process AeroDataBox results
            if isinstance(results[1], Exception):
                logger.error(f"Error fetching AeroDataBox data for {movement}: {results[1]}")
            elif results[1] is not None: # Check if API returned data
                adb_data = results[1] # Assign successful API result
                logger.debug(f"Successfully fetched AeroDataBox data for {movement}")
            else:
                 logger.warning(f"AeroDataBox returned no data for {movement}")


        except Exception as e:
            logger.exception(f"Critical error during API fetching for {movement}: {e}")
            # Ensure data is None if fetching failed critically
            if aeroapi_data is None: aeroapi_data = None
            if adb_data is None: adb_data = None

    return aeroapi_data, adb_data

def process_raw_flight_data(
    all_flights: Dict[str, Dict],
    aeroapi_data: Optional[Dict],
    adb_data: Optional[Dict],
    movement: str
) -> None:
    """
    Processes raw flight data from AeroAPI and AeroDataBox sources
    and updates the all_flights dictionary.
    """
    aeroapi_movement_key = 'scheduled_arrivals' if movement == 'arrivals' else 'scheduled_departures'

    # --- Process AeroDataBox Data ---
    if adb_data and movement in adb_data:
        adb_flight_list = adb_data.get(movement, [])
        logger.info(f"Processing {len(adb_flight_list)} flights from AeroDataBox for {movement}")
        for flight in adb_flight_list:
            try:
                processed_data = dp.process_flight_data_adb(flight, movement)
                if processed_data: # Ensure processing was successful
                    dp.check_existing(all_flights, processed_data) # Add/update
            except Exception as e:
                flight_num = flight.get('number', 'N/A')
                logger.error(f"Error processing ADB flight {flight_num} for {movement}: {e}", exc_info=True)
                continue # Skip this flight

    # --- Process AeroAPI Data ---
    if aeroapi_data and aeroapi_movement_key in aeroapi_data:
        aeroapi_flight_list = aeroapi_data.get(aeroapi_movement_key, [])
        logger.info(f"Processing {len(aeroapi_flight_list)} flights from AeroAPI for {movement}")
        for flight in aeroapi_flight_list:
            try:
                processed_data = dp.process_flight_data_aeroapi(flight)
                if processed_data: # Ensure processing was successful
                    dp.check_existing(all_flights, processed_data) # Add/update
            except Exception as e:
                flight_ident = flight.get('ident', 'N/A')
                logger.error(f"Error processing AeroAPI flight {flight_ident} for {movement}: {e}", exc_info=True)
                continue # Skip this flight

async def fetch_database_lookups(
    reg_table_id: Optional[int],
    model_table_id: Optional[int],
    model_key_field: str
) -> Tuple[Dict, Dict]:
    """
    Fetches registration and model lookup data from Baserow.

    Returns:
        Tuple[Dict, Dict]: (registration_data, model_data)
                           Returns empty dicts if fetching fails or IDs are missing.
    """
    if not reg_table_id or not model_table_id:
        logger.error("Database table IDs (registrations, interesting_models) not configured. Cannot fetch lookups.")
        return {}, {}

    reg_db_data = {}
    model_db_data = {}

    try:
        reg_db_task = asyncio.create_task(bm.get_all_rows_as_dict(reg_table_id))
        # Use the configured key field for the model table dictionary
        model_db_task = asyncio.create_task(bm.get_all_rows_as_dict(model_table_id, key=model_key_field))

        results = await asyncio.gather(reg_db_task, model_db_task, return_exceptions=True)

        if isinstance(results[0], Exception):
            logger.error(f"Error fetching registration DB data (Table ID: {reg_table_id}): {results[0]}")
        elif results[0] is not None: # Check if data was returned
            reg_db_data = results[0]
            logger.info(f"Fetched {len(reg_db_data)} entries from registration table.")
        else:
             logger.warning(f"Baserow returned no data for registration table (ID: {reg_table_id}).")


        if isinstance(results[1], Exception):
            logger.error(f"Error fetching model DB data (Table ID: {model_table_id}): {results[1]}")
        elif results[1] is not None: # Check if data was returned
            model_db_data = results[1]
            logger.info(f"Fetched {len(model_db_data)} entries from model table (keyed by '{model_key_field}').")
        else:
            logger.warning(f"Baserow returned no data for model table (ID: {model_table_id}).")


    except Exception as e:
        logger.exception(f"Critical error during database lookup fetching: {e}")

    return reg_db_data, model_db_data

async def analyze_flights_and_trigger_socials(
    all_flights: Dict[str, Dict],
    reg_db_data: Dict,
    model_db_data: Dict
) -> None:
    """
    Analyzes processed flights against database lookups and triggers social media posts.
    """
    if not all_flights:
        logger.info("No flights processed; skipping analysis and social posting.")
        return
    if not reg_db_data and not model_db_data:
         logger.warning("Database lookup data is empty; flight analysis might be incomplete.")
         # Decide if you want to proceed or return here based on requirements

    logger.info(f"Analyzing {len(all_flights)} unique flights against database lookups...")
    social_tasks = []

    for flight_key, flight_details in all_flights.items():
        try:
            # Check flight against DB rules (dp.check_flight handles the logic)
            # It should return the updated flight data AND the reasons it's interesting
            flight_data, interesting_registration, interesting_model, first_seen = await dp.check_flight(
                flight_details, reg_db_data, model_db_data
            )

            # Determine if interesting based on the flags returned by check_flight
            interesting_reasons = {
                "MODEL": interesting_model,
                "REGISTRATION": interesting_registration,
                "FIRST_SEEN": first_seen,
                "DIVERTED": flight_data.get("diverted", False) # Assuming check_flight updates this
                # Add other reasons if check_flight provides them
            }
            is_interesting = any(interesting_reasons.values())

            if is_interesting:
                reasons_str = ", ".join([k for k, v in interesting_reasons.items() if v])
                flight_name_display = flight_data.get('flight_name') or flight_data.get('ident', 'N/A') # Use 'ident' as fallback
                logger.info(f"Flight {flight_name_display} ({flight_key}) is interesting ({reasons_str}). Queueing social post.")

                # Queue the social media posting task - Ensure sp.call_socials is async
                # Pass the global config object to socials processing
                social_tasks.append(
                    asyncio.create_task(sp.call_socials(flight_data, interesting_reasons, config))
                 )

        except Exception as e:
            logger.exception(f"Error analyzing flight {flight_key}: {e}")
            continue # Skip this flight

    if social_tasks:
        logger.info(f"Sending {len(social_tasks)} posts to social media...")
        results = await asyncio.gather(*social_tasks, return_exceptions=True)
        # Optional: Log results/errors from social posting
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Finding corresponding flight data for better logging can be complex here
                # We only know the task index 'i'
                 logger.error(f"Error sending social post (task index {i}): {result}")
        logger.info("Finished sending social media posts.")
    else:
        logger.info("No interesting flights found to post in this cycle.")


# --- Main Processing Cycle Function (Unchanged) ---

async def fetch_and_process_flights():
    """
    Orchestrates a single cycle of fetching, processing, analyzing flights,
    and triggering social posts.
    """
    logger.info("=" * 20 + " Starting Flight Processing Cycle " + "=" * 20)

    # 1. Calculate Time Range
    start_time_dt, end_time_dt, start_time_str, end_time_str = calculate_time_range(FLIGHT_TIME_RANGE_HOURS)
    logger.info(f"Processing time range: {start_time_str} to {end_time_str}")

    # 2. Fetch Database Lookups (can be run concurrently, but simpler sequentially here)
    reg_db_data, model_db_data = await fetch_database_lookups(DB_REG_TABLE_ID, DB_MODEL_TABLE_ID, DB_MODEL_KEY_FIELD)

    # 3. Fetch and Process Data for Arrivals and Departures
    all_flights: Dict[str, Dict] = {} # Combined dictionary for all processed flights

    for movement in ['arrivals', 'departures']:
        logger.info(f"--- Processing {movement.capitalize()} ---")
        # Fetch raw data
        aeroapi_raw_data, adb_raw_data = await fetch_specific_flight_data(
            movement, start_time_str, end_time_str, USE_PRELOADED_DATA
        )
        # Process fetched data
        process_raw_flight_data(all_flights, aeroapi_raw_data, adb_raw_data, movement)

    logger.info(f"Total unique flights identified after processing: {len(all_flights)}")

    # 4. Analyze Flights and Trigger Social Posts
    await analyze_flights_and_trigger_socials(all_flights, reg_db_data, model_db_data)

    logger.info("=" * 20 + " Finished Flight Processing Cycle " + "=" * 20)


# --- Main Execution Loop (Unchanged) ---

async def main_loop():
    """Runs the main flight processing cycle periodically."""
    while True:
        try:
            await fetch_and_process_flights()

            # Use the globally loaded interval
            interval = EXECUTION_INTERVAL_SECONDS
            if not isinstance(interval, (int, float)) or interval <= 0:
                logger.warning(f"Invalid or missing execution.interval in config. Using default 110 minutes (6600s).")
                interval = 6600

            logger.info(f"Next processing cycle starts in {timedelta(seconds=interval)}.")
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            logger.info("Main loop task cancelled.")
            break
        except Exception as e:
            # Log detailed exception info
            logger.exception("Unhandled error in main_loop:")
            logger.error("Waiting 60 seconds before retrying...")
            await asyncio.sleep(60) # Wait a bit before retrying

# --- Main Application Entry Point (Simplified) ---

async def main():
    """Sets up the application and starts the main processing loop."""
    logger.info("Application starting...")
    # Directly run the main processing loop
    await main_loop()
    logger.info("Application finished main loop.") # This line might only be reached if main_loop breaks


if __name__ == "__main__":
    try:
        # Setup logging first
        # Note: Logging setup is now done globally after imports
        # setup_logging(LOG_FILE, WARN_LOG_FILE, LOG_LEVEL, LOG_ROTATION)
        
        # Run the main async function
        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("Application interrupted by user (Ctrl+C). Exiting.")
    except Exception as e:
        # Use logger if available, otherwise print to stderr
        try:
            logger.exception("Fatal error during application startup or runtime:")
        except NameError: # logger might not be initialized if error happened very early
             print(f"Fatal error during application startup or runtime: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        logger.info("Application shutting down.") # Log shutdown attempt