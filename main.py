import asyncio
import json
from datetime import datetime, timedelta
import sys
from pathlib import Path

import config.config as cfg
import socials.socials_processing as sp
import socials.telegram as tg
import utils.data_processing as dp
from api.aeroapi_key_manager import get_aeroapi_usage_snapshot
from api import api_handler_aeroapi, api_handler_aerodatabox
from database import get_database_provider
from dotenv import load_dotenv
from loguru import logger
from monitoring.api_usage import log_monthly_usage_summary

# Add project root to Python path
sys.path.append(str(Path(__file__).parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "config" / ".env")

# Load configuration
config = cfg.load_config()

# initialize the logger and log into a file in /logs folder with the current date and time in the format of "YYYY-MM-DD_HH-MM-SS" 
logger.remove()
logger.add(f"logs/lemd_spotter.log", level="DEBUG", enqueue=True, rotation="10 MB")
logger.add(f"logs/lemd_spotter_warning.log", level="WARNING", enqueue=True, rotation="10 MB")
logger.add(sys.stdout,level="INFO")

all_flights = {}


# loads the flight information from the api
async def main(all_flights):
    database_provider = get_database_provider()
    airport_icao = (
        cfg.get_config("api.airport_icao")
        or cfg.get_config("database.airport_icao")
        or "LEMD"
    )
    airport_icao = str(airport_icao).upper()
    preloaded_data = bool(cfg.get_config("api.preloaded_data"))
    time_range_hours = int(cfg.get_config("api.time_range_hours") or 2)

    now = datetime.now()
    start_time = now.strftime("%Y-%m-%dT%H:%M")
    end_time = (now + timedelta(hours=time_range_hours)).strftime("%Y-%m-%dT%H:%M")

    for movement in ['arrivals', 'departures']:
        # fetch the data from the api

        if preloaded_data:
            logger.info("Loading data from preloaded files")
            airport_prefix = airport_icao.lower()
            aeroapi_candidates = [
                f"api/data/{airport_prefix}_aeroapi_data_scheduled_{movement}.json",
                f"api/data/aeroapi_data_scheduled_{movement}.json",
            ]
            try:
                temp_aeroapi_data = None
                for aeroapi_file in aeroapi_candidates:
                    try:
                        with open(aeroapi_file, "r", encoding="utf-8") as f:
                            temp_aeroapi_data = json.load(f)
                            logger.info(f"Loaded aeroapi data from {aeroapi_file}")
                            break
                    except FileNotFoundError:
                        continue
                if temp_aeroapi_data is None:
                    raise FileNotFoundError("No preloaded aeroapi file found")
            except Exception:
                logger.info("Preloaded files not found")
                break
            # Check if aerodatabox data file exists
            adb_candidates = [
                f"api/data/{airport_prefix}_adb_data_{movement}.json",
                f"api/data/adb_data_{movement}.json",
            ]
            try:
                temp_adb_data = None
                for adb_file in adb_candidates:
                    try:
                        with open(adb_file, "r", encoding="utf-8") as f:
                            temp_adb_data = json.load(f)
                            logger.info(f"Loaded aerodatabox data from {adb_file}")
                            break
                    except FileNotFoundError:
                        continue
                if temp_adb_data is None:
                    raise FileNotFoundError("No preloaded aerodatabox file found")
            except Exception:
                logger.info("Preloaded files not found")
                break
        else:
            logger.info(f"Fetching data from API between {start_time} and {end_time}")
            temp_aeroapi_data = await api_handler_aeroapi.fetch_aeroapi_scheduled(
                movement,
                start_time,
                end_time,
                airport_icao=airport_icao,
            )
            temp_adb_data = await api_handler_aerodatabox.fetch_adb_data(
                movement,
                start_time,
                end_time,
                airport_icao=airport_icao,
            )

        # iterate over every flight and merge sources
        logger.info(f"Processing ADB data for {movement}")
        logger.info(f"Vuelos {len(temp_adb_data.get(movement, []))}")

        for flight in temp_adb_data.get(movement, []):
            try:
                processed_data = dp.process_flight_data_adb(flight, movement)
                flight_name = processed_data.get("flight_name_iata", processed_data.get("flight_name", None))
                logger.debug(f"Parsed {movement} flight {flight_name}")
            except Exception as e:
                logger.error(f"Error procesando vuelo {e}")
                continue

            dp.check_existing(all_flights, processed_data)

        logger.info(f"Total vuelos {len(all_flights)}")

        logger.info(f"Processing AeroAPI data for {movement}")
        scheduled_key = f"scheduled_{movement}"
        logger.info(f"Vuelos {len(temp_aeroapi_data.get(scheduled_key, []))}")
        for flight in temp_aeroapi_data.get(scheduled_key, []):
            try:
                processed_data = dp.process_flight_data_aeroapi(flight)
                if not processed_data:
                    continue
                flight_name = processed_data.get("flight_name_iata", processed_data.get("flight_name", None))
                logger.debug(f"Parsed {movement} flight {flight_name}", color="yellow")
            except Exception as e:
                logger.error(f"Error procesando vuelo {e}")
                continue

            dp.check_existing(all_flights, processed_data)

        logger.info(f"Total vuelos {len(all_flights)}")

    if not preloaded_data:
        try:
            usage_snapshots = await get_aeroapi_usage_snapshot(force_refresh=False)
            logger.info(f"AeroAPI usage snapshot: {usage_snapshots}")
        except Exception as exc:
            logger.warning(f"Unable to fetch AeroAPI usage snapshot: {exc}")

    reg_db_copy = await database_provider.get_registrations_index(airport_icao)
    interesting_reg_db = await database_provider.get_interesting_registrations_index(airport_icao)
    model_db_copy = await database_provider.get_interesting_models_index(airport_icao)

    for flight_key, raw_flight_data in all_flights.items():
        logger.debug(f"Processing flight {flight_key} in configured database provider")
        flight_data, interesting_registration, interesting_model, first_seen = await dp.check_flight(
            raw_flight_data,
            reg_db_copy,
            interesting_reg_db,
            model_db_copy,
            database_provider,
            airport_icao=airport_icao,
        )

        await database_provider.record_flight_history(flight_data, airport_icao=airport_icao)

        interesting = {
            "MODEL": interesting_model,
            "REGISTRATION": interesting_registration,
            "FIRST_SEEN": first_seen,
            "DIVERTED": False if flight_data.get("diverted") == "null" else bool(flight_data.get("diverted")),
        }

        if any(interesting.values()):
            logger.level("INFO", color="<red>")
            logger.info(
                f"Flight {flight_data['flight_name'] if flight_data['flight_name'] not in [None, 'null'] else flight_data['flight_name_iata']} "
                f"is interesting - generating socials message because of {interesting}"
            )
            logger.level("INFO", color="<white>")
            logger.debug(flight_data)
            await sp.call_socials(flight_data, interesting)

    log_monthly_usage_summary()
    all_flights.clear()


async def run_periodically():
    interval_seconds = int(cfg.get_config("execution.interval") or ((2 * 60 * 60) - 600))

    try:
        await tg.ensure_command_listener()
        while True:
            await main(all_flights)
            next_round = datetime.now() + timedelta(seconds=interval_seconds)
            logger.info("Next round at " + next_round.strftime("%Y-%m-%d %H:%M"))
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        logger.info("Periodic runner cancelled")
        raise
    finally:
        await tg.shutdown_command_listener()


if __name__ == "__main__":
    try:
        asyncio.run(run_periodically())
    except KeyboardInterrupt:
        logger.info("Program stopped by user")
