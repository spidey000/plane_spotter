import aiohttp
import asyncio
from loguru import logger
import json
from log.logger_config import logger
# Removed dotenv import as we will rely on environment variables passed to the container
# from dotenv import load_dotenv
import os
from config import config_manager
config = config_manager.load_config()



# delete for production
# Removed dotenv loading logic
# load_dotenv()

async def get_valid_aeroapi_key():
    """Return the first API key whose usage is below the threshold minus 10c, or None if all are exhausted."""
    import asyncio
    from datetime import datetime, timedelta

    async def cooldown_before_next_key():
        logger.info("Cooling off for 21 seconds before trying next API key...")
        await asyncio.sleep(21)

    url = "https://aeroapi.flightaware.com/aeroapi/account/usage"
    end_time_account = datetime.utcnow()
    start_time_account = end_time_account - timedelta(days=30)
    params1 = {
        "start": start_time_account.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end_time_account.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "all_keys": "False"
    }
    for idx, key_env in enumerate(['AEROAPI_KEY0','AEROAPI_KEY1','AEROAPI_KEY2']):
        api_key = os.getenv(key_env)
        if not api_key:
            logger.warning(f"No API key found for {key_env}")
            if idx < 2:
                await cooldown_before_next_key()
            continue
        headers = {
            "Accept": "application/json; charset=UTF-8",
            "x-apikey": api_key
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, params=params1) as response:
                    if response.status == 200:
                        data = await response.json()
                        total_cost = data.get('total_cost', 0)
                        cost_limit = config['settings']['aeroapi_cost_limit']
                        # Consider exhausted if within 10c of the limit
                        if total_cost >= (cost_limit - 0.20):
                            logger.warning(f"{key_env} cost at ${total_cost:.2f} - limit (${cost_limit:.2f}), considered exhausted.")
                            if idx < 2:
                                await cooldown_before_next_key()
                            continue  # Try next key
                        else:
                            logger.success(f"{key_env} cost at ${total_cost:.2f} - within acceptable limits")
                            return api_key  # Found a valid key
                    else:
                        logger.error(f"Failed to fetch account usage for {key_env}: {response.status}")
                        if idx < 2:
                            await cooldown_before_next_key()
            except Exception as e:
                logger.error(f"Error checking usage for {key_env}: {e}")
                if idx < 2:
                    await cooldown_before_next_key()
    logger.error("All API keys are exhausted or invalid.")
    return None

async def fetch_aeroapi_scheduled(move, start_time, end_time):

    headers = {
        "Accept": "application/json; charset=UTF-8",
        "x-apikey": await get_valid_aeroapi_key() #gets the first valid key within cost limit
    }
    base_url = f"https://aeroapi.flightaware.com/aeroapi/airports/{config['settings']['airport']}/flights/{move}"

    params = {
        "start": start_time,
        "end": end_time,
        "max_pages": 10
    }
    

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
                    #logger.info(f"Ratelimit delay: {base_delay}")
                    #await asyncio.sleep(base_delay)
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

