import aiohttp
import asyncio
from loguru import logger
import json
import http.client
import os
from log.logger_config import logger


async def fetch_adb_data(move, start_time, end_time):

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
        "x-magicapi-key": "cm6nng5bg0001kw03izfzi9ua"
    }
    
    url = f"https://api.magicapi.dev/api/v1/aedbx/aerodatabox/flights/airports/Icao/LEMD/{start_time.replace(':', '%3A')}/{end_time.replace(':', '%3A')}"
    logger.info(f"Fetching data from ADB API")
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
                    logger.success(f"Total flights collected: {len(data[move])}")
                else:
                    logger.error(f"API request failed with status code: {response.status}")
                return data
        except aiohttp.ClientError as e:
            logger.error(f"Client error occurred: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")

#asyncio.run(fetch_adb_data('departures',  '2025-02-10T06:00', '2025-02-10T07:00'))
