import os
import json
import aiohttp
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

async def check_key(key, index, limit):
    url = "https://aeroapi.flightaware.com/aeroapi/account/usage"
    headers = {"x-apikey": key}
    
    # Calculate start/end time for current month
    end_time = datetime.utcnow() - timedelta(seconds=10)
    start_time = end_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    params = {
        "start": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    cost = data.get('total_cost', 0)
                    status = "VALID" if cost < limit else "EXHAUSTED"
                    print(f"Key {index} ({key[:5]}...): MTD Cost ${cost:.2f} / Limit ${limit:.2f} -> {status}")
                else:
                    print(f"Key {index} ({key[:5]}...): Error {response.status} - {await response.text()}")
        except Exception as e:
            print(f"Key {index}: Exception {e}")

async def main():
    # Load limit from config
    try:
        with open('config/config.json', 'r') as f:
            config = json.load(f)
            limit = config['settings'].get('aeroapi_cost_limit', 5.0)
    except:
        limit = 5.0
        
    print(f"--- Checking AeroAPI Keys (Month-to-Date) against Limit: ${limit:.2f} ---")
    
    for i in range(3):
        key = os.getenv(f"AEROAPI_KEY{i}")
        if key:
            await check_key(key, i, limit)
        else:
            print(f"Key {i}: Not set")

if __name__ == "__main__":
    asyncio.run(main())
