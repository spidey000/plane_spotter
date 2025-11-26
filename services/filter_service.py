from typing import List, Dict, Any
from core.models import Flight, ProcessedFlight, InterestingReason
from core.interfaces import DatabaseProvider
from loguru import logger

class FilterService:
    def __init__(self, db_provider: DatabaseProvider):
        self.db_provider = db_provider

    async def check_flight(self, flight: Flight, config: Dict[str, Any]) -> ProcessedFlight:
        """
        Check if a flight is interesting.
        This is a placeholder implementation. Real logic would check database for interesting models/registrations.
        """
        reasons = []
        is_interesting = False
        
        # Initialize flags
        check_flags = {
            "REG": 0, # Registration check
            "MOD": 0, # Model check
            "DIV": 0  # Diversion check
        }

        # Example Logic: Check if registration is in interesting list (mocked)
        # In real app, we would query self.db_provider.get_interesting_registrations()
        
        # For now, let's just say everything is interesting for testing purposes if configured
        # or implement basic logic.
        
        # Check for diversion (example)
        # if flight.status == "DIVERTED":
        #    reasons.append(InterestingReason(reason_code="DIVERTED", description="Flight diverted"))
        #    is_interesting = True
        #    check_flags["DIV"] = 1
            
        return ProcessedFlight(
            flight=flight,
            is_interesting=is_interesting,
            reasons=reasons,
            check_flags=check_flags
        )
