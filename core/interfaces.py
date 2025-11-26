from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
from core.models import Flight, ProcessedFlight, InterestingReason

class DatabaseProvider(ABC):
    @abstractmethod
    async def get_interesting_models(self, airport_icao: str) -> Dict[str, Any]:
        """Retrieve interesting aircraft models."""
        pass

    @abstractmethod
    async def get_interesting_registrations(self, airport_icao: str) -> Dict[str, Any]:
        """Retrieve interesting aircraft registrations."""
        pass

    @abstractmethod
    async def get_registration_history(self, registration: str, airport_icao: str) -> Optional[Dict[str, Any]]:
        """Retrieve history for a specific registration."""
        pass

    @abstractmethod
    async def upsert_registration(self, registration_data: Dict[str, Any]) -> bool:
        """Update or insert a registration record."""
        pass

    @abstractmethod
    async def is_flight_processed(self, flight_id: str, airport_icao: str) -> bool:
        """Check if a flight has already been processed."""
        pass

    @abstractmethod
    async def log_flight(self, flight: Flight, airport_icao: str) -> bool:
        """Log a processed flight to prevent duplicates."""
        pass
class SocialProvider(ABC):
    @abstractmethod
    async def post_flight(self, processed_flight: ProcessedFlight, config: Dict[str, Any]) -> bool:
        """Post a flight to the social media platform."""
        pass

class FlightDataProvider(ABC):
    @abstractmethod
    async def fetch_scheduled_flights(self, start_time: datetime, end_time: datetime, config: Dict[str, Any]) -> List[Flight]:
        """Fetch scheduled flights for a given time range."""
        pass
