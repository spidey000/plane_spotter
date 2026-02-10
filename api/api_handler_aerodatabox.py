import aiohttp
import json
import os
import time

from loguru import logger

from monitoring.api_usage import record_api_event

async def fetch_adb_data(move, start_time, end_time, airport_icao="LEMD"):
    airport_icao = (airport_icao or "LEMD").upper()
    api_key = os.getenv("AERODATABOX_KEY")
    if not api_key:
        raise RuntimeError("AERODATABOX_KEY is not configured")

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
        "x-magicapi-key": api_key,
    }
    
    url = (
        "https://api.magicapi.dev/api/v1/aedbx/aerodatabox/flights/airports/"
        f"Icao/{airport_icao}/{start_time.replace(':', '%3A')}/{end_time.replace(':', '%3A')}"
    )
    logger.info(f"Fetching data from ADB API")
    async with aiohttp.ClientSession() as session:
        started = time.perf_counter()
        try:
            async with session.get(url, headers=headers, params=querystring) as response:
                duration_ms = (time.perf_counter() - started) * 1000.0
                logger.debug(f"Received response with status: {response.status}")
                data = await response.json()
                record_api_event(
                    provider="aerodatabox",
                    endpoint=f"GET /aerodatabox/flights/airports/Icao/{airport_icao}",
                    method="GET",
                    status_code=response.status,
                    success=200 <= response.status < 300,
                    duration_ms=duration_ms,
                    estimated_cost_usd=0.0,
                )
                if response.status == 200:
                    # Create data directory if it doesn't exist and save the data to a JSON file
                    os.makedirs('api/data', exist_ok=True)
                    file_path = f"api/data/{airport_icao.lower()}_adb_data_{move}.json"
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4)
                    logger.debug(f"Data saved to {file_path}")
                    logger.success(f"Total flights collected: {len(data[move])}")
                else:
                    logger.error(f"API request failed with status code: {response.status}")
                return data
        except aiohttp.ClientError as e:
            duration_ms = (time.perf_counter() - started) * 1000.0
            record_api_event(
                provider="aerodatabox",
                endpoint=f"GET /aerodatabox/flights/airports/Icao/{airport_icao}",
                method="GET",
                status_code=None,
                success=False,
                duration_ms=duration_ms,
                estimated_cost_usd=0.0,
                error=str(e),
            )
            logger.error(f"Client error occurred: {e}")
        except Exception as e:
            duration_ms = (time.perf_counter() - started) * 1000.0
            record_api_event(
                provider="aerodatabox",
                endpoint=f"GET /aerodatabox/flights/airports/Icao/{airport_icao}",
                method="GET",
                status_code=None,
                success=False,
                duration_ms=duration_ms,
                estimated_cost_usd=0.0,
                error=str(e),
            )
            logger.error(f"An unexpected error occurred: {e}")

#asyncio.run(fetch_adb_data('departures',  '2025-02-10T06:00', '2025-02-10T07:00'))
