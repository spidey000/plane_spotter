import aiohttp
import asyncio
from loguru import logger
import json
from log.logger_config import logger
from dotenv import load_dotenv
import os


# delete for production
load_dotenv()

async def fetch_aeroapi_scheduled(move, start_time, end_time):

    headers = {
        "Accept": "application/json; charset=UTF-8",
        "x-apikey": os.getenv('AEROAPI_KEY')
    }
    base_url = f"https://aeroapi.flightaware.com/aeroapi/airports/lemd/flights/{move}"
    params = {
        "start": start_time,
        "end": end_time,
        "max_pages": 10
    }
    logger.info(f"AEROAPI {move} Fetching data from API")
    async def fetch_page(session, url):
        n = 0
        retry_count = 0
        max_retries = 5
        base_delay = 20  # Starting delay in seconds
        
        while retry_count < max_retries:
            try:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 429:
                        retry_after = int(response.headers.get('Retry-After', base_delay))
                        wait_time = min(retry_after * (2 ** retry_count), 60)  # Cap at 60 seconds
                        logger.warning(f"Rate limited. Retrying in {wait_time} seconds (attempt {retry_count + 1})")
                        await asyncio.sleep(wait_time)
                        retry_count += 1
                        continue
                    
                    logger.debug(f"Received response iteration {n+1} with status: {response.status}")
                    data = await response.json()
                    logger.info(f"Ratelimit delay: {base_delay}")
                    await asyncio.sleep(base_delay)
                    n += 1
                    return data
                    
            except aiohttp.ClientError as e:
                logger.error(f"Client error occurred: {e}")
                print(f"Client error occurred: {e}")
                return None

            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
                print(f"Client error occurred: {e}")
                return None

        logger.error(f"Max retries ({max_retries}) reached for URL: {url}")
        return None

    
    async with aiohttp.ClientSession() as session:
        all_data = {move: []}
        url = f"{base_url}"
        logger.debug(f"Starting data fetch from {url}")
        while url:
            logger.debug(f"Fetching data from {url}")
            data = await fetch_page(session, url)
            params = None
            if len(data.get(move, [])) > 0:
                logger.success(f"Received {len(data.get(move, []))} flights in this batch aeropai {move}")
                all_data[move].extend(data.get(move, []))
                try:
                    next_url = data.get("links", {})["next"]
                    logger.debug(f"Next URL found: {next_url}")
                except Exception as e:
                    logger.warning(f"No next URL: {e}")
                    next_url = None
                url = f"https://aeroapi.flightaware.com/aeroapi{next_url}" if next_url else None
                if url:
                    logger.debug(f"Proceeding to next page: {url}")
            else:
                logger.warning("No data received, stopping pagination")
                break
        logger.success(f"AEROAPI {move} Total flights collected: {len(all_data[move])}")
        with open(f'api/data/aeroapi_data_{move}.json', 'w') as f:
            json.dump(all_data, f, indent=4)
            logger.debug(f"Data saved to api/data/aeroapi_data_{move}.json")
        return all_data

#asyncio.run(fetch_aeroapi_scheduled('departures',  '2025-02-13T00:01', '2025-02-13T23:59'))
