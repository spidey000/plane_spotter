import aiohttp
import asyncio
from loguru import logger
import json
import http.client
import os
from log.logger_config import logger
from config import config_manager # Keep import for type hinting or if other functions need it
# Removed dotenv import as we will rely on environment variables passed to the container
# from dotenv import load_dotenv

# delete for production
#load_dotenv()

async def get_valid_adb_key():
    """Return the first API key that successfully hits the health endpoint, or None if all are exhausted."""
    url = "https://prod.api.market/api/v1/aedbx/aerodatabox/health/services/feeds/FlightSchedules/airports"
    for key_env in ['ADBOX_KEY0', 'ADBOX_KEY1', 'ADBOX_KEY2']:
        api_key = os.getenv(key_env)
        if not api_key:
            logger.warning(f"No API key found for {key_env}")
            continue
        headers = {
            "Accept": "application/json",
            "x-magicapi-key": api_key,
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        logger.success(f"{key_env} is valid and responsive")
                        return api_key  # Found a valid key
                    else:
                        logger.warning(f"{key_env} failed with status code: {response.status}")
            except Exception as e:
                logger.error(f"Error checking health for {key_env}: {e}")
    logger.error("All API keys are exhausted or invalid.")
    return None

async def fetch_adb_data(move, start_time, end_time, config):
    if config is None:
        logger.error("Configuration (config) must be provided to fetch_adb_data.")
        raise ValueError("Configuration is missing.")

    querystring_arrival = {"withLeg":"true",
                           "direction":"Arrival",
                           "withCancelled":"false",
                           "withCodeshared":"false",
                           "withCargo":"true",
                           "withPrivate":"true",
                           "withLocation":"false"}
    
    querystring_departure = {"withLeg":"true",
                             "direction":"Departure",
                             "withCancelled":"false",
                             "withCodeshared":"false",
                             "withCargo":"true",
                             "withPrivate":"true",
                             "withLocation":"false"}
    
    querystring = querystring_arrival if move == 'arrivals' else querystring_departure

    headers = {
        "accept": "application/json",
        "x-magicapi-key": await get_valid_adb_key()
    }
    
    url = f"https://prod.api.market/api/v1/aedbx/aerodatabox/flights/airports/Icao/{config['settings']['airport']}/{start_time}/{end_time}"    
    logger.info(f"ADB {move} Fetching data from API")
    logger.debug(f"Final URL: {url}")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, params=querystring) as response:
                logger.debug(f"Received response with status: {response.status}")
                data = await response.json()
                if response.status == 200:
                    # Create data directory if it doesn't exist and save the data to a JSON file
                    os.makedirs('api/data', exist_ok=True)
                    file_path = f'api/data/adb_data_{move}.json'
                    with open(file_path, 'w') as f:
                        json.dump(data, f, indent=4)
                    logger.debug(f"Data saved to {file_path}")
                    logger.success(f"ADB {move} Total flights collected: {len(data[move])}")
                else:
                    logger.error(f"ADB API request failed with status code: {response.status}")
                return data
        except aiohttp.ClientError as e:
            logger.error(f"Client error occurred: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
