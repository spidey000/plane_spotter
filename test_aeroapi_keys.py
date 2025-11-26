import os
import asyncio
import aiohttp
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

async def test_key(key, index):
    print(f"\n--- Testing Key {index}: {key[:5]}... ---")
    headers = {"x-apikey": key}
    
    async with aiohttp.ClientSession() as session:
        # 1. Check Usage
        usage_url = "https://aeroapi.flightaware.com/aeroapi/account/usage"
        try:
            async with session.get(usage_url, headers=headers) as response:
                print(f"Usage Endpoint Status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print(f"  Total Cost (Lifetime/Window): ${data.get('total_cost', 'N/A')}")
                else:
                    print(f"  Error Body: {await response.text()}")
        except Exception as e:
            print(f"  Usage Check Failed: {e}")

        # 2. Try Real Fetch (Scheduled Arrivals for LEMD)
        # Match main.py: 24 hours, 10 pages
        start = datetime.utcnow()
        end = start + timedelta(hours=24)
        fetch_url = "https://aeroapi.flightaware.com/aeroapi/airports/LEMD/flights/scheduled_arrivals"
        params = {
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "max_pages": 10
        }
        
        try:
            async with session.get(fetch_url, headers=headers, params=params) as response:
                print(f"Fetch Endpoint Status: {response.status}")
                print(f"  Headers:")
                for k, v in response.headers.items():
                    if k.lower().startswith('x-rate') or k.lower() == 'retry-after':
                        print(f"    {k}: {v}")
                
                if response.status == 200:
                    data = await response.json()
                    flights = data.get('scheduled_arrivals', [])
                    print(f"  Success! Fetched {len(flights)} flights.")
                elif response.status == 429:
                    print(f"  RATE LIMITED!")
                    print(f"  Body: {await response.text()}")
                else:
                    print(f"  Error Body: {await response.text()}")
        except Exception as e:
            print(f"  Fetch Failed: {e}")

async def main():
    print("Starting AeroAPI Key Diagnostic...")
    for i in range(3):
        key = os.getenv(f"AEROAPI_KEY{i}")
        if key:
            await test_key(key, i)
        else:
            print(f"\nKey {i}: Not set in .env")

if __name__ == "__main__":
    asyncio.run(main())
