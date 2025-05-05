import asyncio
import json
import sys
import yaml # For pretty printing config
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
from config import config_manager
from dotenv import load_dotenv
import os



# Add project root to Python path if necessary (adjust if your structure differs)
# sys.path.append(str(Path(__file__).parent.parent))

# Local imports
import utils.data_processing as dp
from api import api_handler_aeroapi, api_handler_aerodatabox
import database.baserow_manager as bm
import socials.socials_processing as sp


# Load initial config to get log settings
# Load configuration
config = config_manager.load_config()
# Load environment variables from .env file
load_dotenv()

FLIGHT_TIME_RANGE_HOURS = config['flight']['time_range_hours']
DATABASE_REGISTRATION_TABLE_ID = config['baserow']['tables']['registrations'] # has all the registrations
DATABASE_MODEL_TABLE_ID = config['baserow']['tables']['interesting_models'] # has all the models
DATABASE_INTERESTING_REGISTRATIONS_TABLE_ID = config['baserow']['tables']['interesting_registrations'] # has only interesting registrations
EXECUTION_INTERVAL = config['execution']['interval']

# Get logger configuration from config
LOG_FILE = config['logging']['log_file']
WARN_LOG_FILE = config['logging']['warning_log_file']
LOG_LEVEL = config['logging']['log_level']
LOG_ROTATION = config['logging']['log_rotation']

# --- Logger Setup ---
try:
    logger.remove() # Remove default handler
    # Ensure logs directory exists
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    logger.add(LOG_FILE, level=LOG_LEVEL.upper(), enqueue=True, rotation=LOG_ROTATION)
    if WARN_LOG_FILE != LOG_FILE:
         Path(WARN_LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
         logger.add(WARN_LOG_FILE, level="WARNING", enqueue=True, rotation=LOG_ROTATION)
    logger.add(sys.stdout, level="INFO") # Keep console output for INFO+
    logger.info("Logger initialized.")

except Exception as e:
    print(f"Error initializing logger: {e}", file=sys.stderr)
    # Fallback basic logger
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.error("Failed to configure logger from config file.")
# --- End Logger Setup ---

# --- Main Application Logic ---

async def fetch_and_process_flights():
    """Fetches flight data, processes it, checks for interesting flights, and posts to socials."""
    logger.info("Starting flight processing cycle...")
    # Load fresh config for this cycle to get latest settings
    all_flights = {} # Reset for each cycle

    # Get time range from config
    time_range_hours = config.get('flight', {}).get('time_range_hours', 2)
    use_preloaded = config.get('flight', {}).get('preview_data', False) # Default to False if not set

    now = datetime.now()
    start_time_dt = now # Start from now
    end_time_dt = now + timedelta(hours=time_range_hours)
    start_time_str = start_time_dt.strftime('%Y-%m-%dT%H:%M')
    end_time_str = end_time_dt.strftime('%Y-%m-%dT%H:%M')

    logger.info(f"Processing time range: {start_time_str} to {end_time_str}")

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
             logger.info(f"Fetching live API data for {movement} ({start_time_str} to {end_time_str})")
             try:
                 # Use await for async API calls
                 aero_task = api_handler_aeroapi.fetch_aeroapi_scheduled(aeroapi_movement_key, start_time_str, end_time_str)
                 adb_task = api_handler_aerodatabox.fetch_adb_data(movement, start_time_str, end_time_str)
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
                    processed_data = dp.process_flight_data_adb(flight, movement)
                    dp.check_existing(all_flights, processed_data) # Add/update in our combined dict
                except Exception as e:
                    logger.error(f"Error processing ADB flight {flight.get('number', 'N/A')}: {e}")
                    continue # Skip this flight

        if temp_aeroapi_data and aeroapi_movement_key in temp_aeroapi_data:
             logger.info(f"Processing {len(temp_aeroapi_data[aeroapi_movement_key])} flights from AeroAPI for {movement}")
             for flight in temp_aeroapi_data[aeroapi_movement_key]:
                 try:
                     processed_data = dp.process_flight_data_aeroapi(flight)
                     dp.check_existing(all_flights, processed_data) # Add/update
                 except Exception as e:
                     logger.error(f"Error processing AeroAPI flight {flight.get('ident', 'N/A')}: {e}")
                     continue # Skip this flight

    logger.info(f"Total unique flights identified in cycle: {len(all_flights)}")

    # --- Database Interaction and Social Posting ---
    if not all_flights:
        logger.info("No flights processed in this cycle.")
        return # Nothing more to do

    try:
        # Get DB data (consider caching this for short periods if performance is an issue)
        reg_table_id = config['baserow']['tables']['registrations']
        model_table_id = config['baserow']['tables']['interesting_models']
        model_table_key = config.get('database', {}).get('model_table_key', 'model') # Default key

        DATABASE_REGISTRATION_TABLE_ID = config['baserow']['tables']['registrations']
        DATABASE_MODEL_TABLE_ID = config['baserow']['tables']['interesting_models']
        DATABASE_INTERESTING_REGISTRATIONS_TABLE_ID = config['baserow']['tables']['interesting_registrations']

        if not reg_table_id or not model_table_id:
             logger.error("Database table IDs not configured. Cannot check flights.")
             return

        reg_db_task = bm.get_all_rows_as_dict(reg_table_id)
        model_db_task = bm.get_all_rows_as_dict(model_table_id, key=model_table_key)
        db_results = await asyncio.gather(reg_db_task, model_db_task, return_exceptions=True)

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

        logger.info(f"Checking {len(all_flights)} flights against database...")
        social_tasks = []
        for flight_key, flight_details in all_flights.items():
            try:
                # Check flight against DB rules
                flight_data, interesting_registration, interesting_model, first_seen = await dp.check_flight(
                    flight_details, reg_db_copy, model_db_copy
                )

                # Determine if interesting
                interesting_reasons = {
                    "MODEL": interesting_model,
                    "REGISTRATION": interesting_registration,
                    "FIRST_SEEN": first_seen,
                    "DIVERTED": flight_data.get("diverted", False) # Assuming check_flight updates this
                }
                is_interesting = any(interesting_reasons.values())

                if is_interesting:
                    reasons_str = ", ".join([k for k, v in interesting_reasons.items() if v])
                    flight_name_display = flight_data.get('flight_name') or flight_data.get('flight_name_iata', 'N/A')
                    logger.info(f"Flight {flight_name_display} is interesting ({reasons_str}). Queueing social post.")
                    # Queue the social media posting task
                    social_tasks.append(sp.call_socials(flight_data, interesting_reasons, config)) # Pass config

            except Exception as e:
                logger.exception(f"Error checking flight {flight_key}: {e}")
                continue # Skip this flight

        if social_tasks:
            logger.info(f"Sending {len(social_tasks)} posts to social media...")
            # Run social posting tasks concurrently
            await asyncio.gather(*social_tasks, return_exceptions=True) # Add error handling for gather results if needed
            logger.info("Finished sending social media posts.")
        else:
            logger.info("No interesting flights found to post.")

    except Exception as e:
        logger.exception(f"Error during database check or social posting phase: {e}")

    logger.info("Finished flight processing cycle.")


async def main_loop():
    """Runs the main flight processing cycle periodically."""
    while True:
        try:
            await fetch_and_process_flights()
            # Get interval from config *inside* the loop to pick up changes
            interval = config['execution']['interval']
            if not isinstance(interval, (int, float)) or interval <= 0:
                logger.warning(f"Invalid or missing execution.interval in config. Using default 110 minutes.")
                interval = (2 * 60 * 60) - 600 # Default: 2 hours minus 10 minutes
            logger.info(f"Next processing cycle starts in {timedelta(seconds=interval)}.")
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
             logger.info("Main loop cancelled.")
             break
        except Exception as e:
            logger.exception("Unhandled error in main_loop:")
            logger.error("Waiting 60 seconds before retrying...")
            await asyncio.sleep(60) # Wait a bit before retrying after a major error


