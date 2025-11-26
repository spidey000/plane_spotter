import os
from dotenv import load_dotenv
import aiohttp
import asyncio

load_dotenv()

async def check_key(key):
    url = "https://aeroapi.flightaware.com/aeroapi/account/usage"
    headers = {"x-apikey": key}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as response:
                print(f"Key: {key[:5]}... Status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print(f"  Usage: {data}")
                else:
                    print(f"  Error: {await response.text()}")
        except Exception as e:
            print(f"  Exception: {e}")

async def main():
    print("--- Loaded Environment Variables ---")
    keys = []
    for i in range(3):
        key = os.getenv(f"AEROAPI_KEY{i}")
        if key:
            print(f"AEROAPI_KEY{i}: {key}")
            keys.append(key)
        else:
            print(f"AEROAPI_KEY{i}: Not set")
            
    print("\n--- Checking Keys ---")
    for key in keys:
        await check_key(key)

if __name__ == "__main__":
    asyncio.run(main())
