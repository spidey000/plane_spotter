import aiohttp
import asyncio
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger
from core.interfaces import FlightDataProvider
from core.models import Flight, FlightStatus

class AerodataboxClient(FlightDataProvider):
    def __init__(self, api_keys: List[str], airport_code: str):
        self.api_keys = api_keys
        self.airport_code = airport_code
        self.base_url = "https://prod.api.market/api/v1/aedbx/aerodatabox"
        self._current_key_index = 0

    async def _get_valid_key(self) -> Optional[str]:
        """Returns the current API key. Rotation happens on failure during fetch."""
        if not self.api_keys:
            return None
        return self.api_keys[self._current_key_index]

    def _rotate_key(self):
        """Rotates to the next available key."""
        if not self.api_keys:
            return
        self._current_key_index = (self._current_key_index + 1) % len(self.api_keys)
        logger.info(f"Rotated to Aerodatabox key index {self._current_key_index}")

    async def fetch_scheduled_flights(self, start_time: datetime, end_time: datetime, config: Dict[str, Any]) -> List[Flight]:
        api_key = await self._get_valid_key()
        if not api_key:
            return []

        headers = {"x-magicapi-key": api_key, "Accept": "application/json"}
        
        # Aerodatabox uses a time range in the URL
        # Format: YYYY-MM-DDTHH:MM
        start_str = start_time.strftime("%Y-%m-%dT%H:%M")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M")
        
        url = f"{self.base_url}/flights/airports/Icao/{self.airport_code}/{start_str}/{end_str}"
        
        # We only care about arrivals for now, based on legacy code usage
        params = {
            "withLeg": "true",
            "direction": "Arrival",
            "withCancelled": "false",
            "withCodeshared": "false",
            "withCargo": "true",
            "withPrivate": "true",
            "withLocation": "false"
        }
        
        flights = []
        
        # Try up to len(api_keys) times to find a working key
        for _ in range(len(self.api_keys)):
            api_key = await self._get_valid_key()
            headers = {"x-magicapi-key": api_key, "Accept": "application/json"}
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(url, headers=headers, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            for raw_flight in data.get('arrivals', []):
                                flights.append(self._map_to_flight(raw_flight))
                            logger.info(f"Fetched {len(flights)} flights from Aerodatabox")
                            return flights # Success
                        elif response.status in [401, 403, 429]:
                            logger.warning(f"Aerodatabox key {self._current_key_index} failed: {response.status}. Rotating...")
                            self._rotate_key()
                        else:
                            logger.error(f"Aerodatabox error: {response.status} - {await response.text()}")
                            return [] # Non-auth error, probably bad request or server error
                except Exception as e:
                    logger.error(f"Aerodatabox exception: {e}")
                    return []
                    
        logger.error("All Aerodatabox keys exhausted.")
        return []

    def _map_to_flight(self, raw: Dict[str, Any]) -> Flight:
        # Map Aerodatabox format to internal Flight model
        arrival = raw.get('arrival', {})
        departure = raw.get('departure', {})
        airline = raw.get('airline', {})
        aircraft = raw.get('aircraft', {})
        
        scheduled_time_str = arrival.get('scheduledTimeLocal')
        scheduled_time = None
        if scheduled_time_str:
            # ADB returns local time usually, but we need to be careful. 
            # Assuming the input string is ISO-like.
            try:
                scheduled_time = datetime.fromisoformat(scheduled_time_str)
            except ValueError:
                pass

        return Flight(
            flight_id=f"adb_{raw.get('number')}_{scheduled_time_str}", # Synthesize an ID
            flight_name=raw.get('number'),
            flight_name_iata=raw.get('number'), # ADB often gives just one number
            registration=aircraft.get('reg'),
            aircraft_icao=aircraft.get('model'),
            airline_icao=airline.get('name'), # ADB gives name, not always ICAO. This might need refinement.
            origin_icao=departure.get('airport', {}).get('icao'),
            destination_icao=self.airport_code,
            scheduled_time=scheduled_time,
            status=FlightStatus.SCHEDULED,
            source="aerodatabox",
            raw_data=raw
        )
