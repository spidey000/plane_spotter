import aiohttp
import asyncio
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger
from core.interfaces import FlightDataProvider
from core.models import Flight, FlightStatus

class AeroAPIClient(FlightDataProvider):
    def __init__(self, api_keys: List[str], airport_code: str, cost_limit: float = 5.0):
        self.api_keys = api_keys
        self.airport_code = airport_code
        self.cost_limit = cost_limit
        self.base_url = "https://aeroapi.flightaware.com/aeroapi"
        self._current_key_index = 0

    async def _get_valid_key(self) -> Optional[str]:
        """Finds a valid API key that hasn't exceeded the cost limit."""
        # Try current key first, then rotate if needed
        for _ in range(len(self.api_keys)):
            key = self.api_keys[self._current_key_index]
            if await self._check_usage(key):
                return key
            
            logger.warning(f"Key {self._current_key_index} exhausted or invalid. Rotating...")
            self._current_key_index = (self._current_key_index + 1) % len(self.api_keys)
            
        logger.error("All AeroAPI keys exhausted.")
        return None

    async def _check_usage(self, key: str) -> bool:
        """Checks if the key is within the cost limit."""
        url = f"{self.base_url}/account/usage"
        headers = {"x-apikey": key}
        
        # Check usage for the current calendar month (1st to now)
        # Subtract a small buffer from now to avoid "future" timestamp errors if clocks drift
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
                        total_cost = data.get('total_cost', 0)
                        # Buffer of 0.20 to be safe
                        if total_cost >= (self.cost_limit - 0.20):
                            logger.warning(f"Key cost ${total_cost:.2f} near limit ${self.cost_limit:.2f}")
                            return False
                        return True
                    elif response.status == 401:
                        logger.error("Invalid API Key")
                        return False
                    else:
                        logger.warning(f"Failed to check usage: {response.status}")
                        return True # Assume valid if check fails to avoid blocking, unless 401
            except Exception as e:
                logger.error(f"Error checking usage: {e}")
                return True # Fail open

    async def fetch_scheduled_flights(self, start_time: datetime, end_time: datetime, config: Dict[str, Any]) -> List[Flight]:
        # Try each key until we get data or run out of keys
        for _ in range(len(self.api_keys)):
            api_key = await self._get_valid_key()
            if not api_key:
                # If _get_valid_key returns None, it means all keys failed the local check
                # But we might want to force try them if we suspect local check is wrong?
                # For now, let's trust _get_valid_key's rotation logic or just force rotation here.
                # Actually, _get_valid_key rotates internally. If it returns None, we are done.
                break

            headers = {"x-apikey": api_key}
            # Fetch arrivals
            url = f"{self.base_url}/airports/{self.airport_code}/flights/scheduled_arrivals"
            params = {
                "start": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "max_pages": 10 
            }
            
            flights = []
            success = True
            async with aiohttp.ClientSession() as session:
                while url:
                    try:
                        data = await self._fetch_page_with_retry(session, url, headers, params)
                        if not data:
                            # Fetch failed (likely 429 or error), mark as failed to trigger rotation
                            success = False
                            break
                        
                        arrivals = data.get('scheduled_arrivals')
                        if arrivals:
                            for raw_flight in arrivals:
                                flights.append(self._map_to_flight(raw_flight))
                        
                        # Pagination
                        links = data.get('links')
                        if links and isinstance(links, dict):
                            next_link = links.get('next')
                            if next_link:
                                url = f"https://aeroapi.flightaware.com/aeroapi{next_link}"
                                params = None # Params are part of the next link
                            else:
                                url = None
                        else:
                            url = None
                    except Exception as e:
                        logger.error(f"Error during fetch loop: {e}")
                        success = False
                        break
            
            if success:
                logger.info(f"Fetched {len(flights)} flights from AeroAPI")
                return flights
            else:
                logger.warning(f"Key {self._current_key_index} failed during fetch. Rotating...")
                self._current_key_index = (self._current_key_index + 1) % len(self.api_keys)
        
        logger.error("All AeroAPI keys failed to fetch data.")
        return []

    async def _fetch_page_with_retry(self, session, url, headers, params=None, max_retries=3):
        for attempt in range(max_retries):
            try:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:
                        logger.warning(f"Rate limited (429). Headers: {response.headers}")
                        try:
                            body = await response.text()
                            logger.warning(f"Rate limit body: {body}")
                        except:
                            pass
                        # Do not wait, return None to trigger rotation
                        return None
                    else:
                        logger.error(f"AeroAPI error {response.status}: {await response.text()}")
                        return None
            except Exception as e:
                logger.error(f"Request failed: {e}")
                await asyncio.sleep(5)
        return None

    def _map_to_flight(self, raw: Dict[str, Any]) -> Flight:
        return Flight(
            flight_id=raw.get('fa_flight_id', 'unknown'),
            flight_name=raw.get('ident'),
            flight_name_iata=raw.get('ident_iata'),
            registration=raw.get('registration'),
            aircraft_icao=raw.get('aircraft_type'),
            airline_icao=raw.get('operator'),
            origin_icao=raw.get('origin', {}).get('code'),
            destination_icao=raw.get('destination', {}).get('code'),
            scheduled_time=datetime.fromisoformat(raw.get('scheduled_in').replace('Z', '+00:00')) if raw.get('scheduled_in') else None,
            status=FlightStatus.SCHEDULED,
            source="aeroapi",
            raw_data=raw
        )
