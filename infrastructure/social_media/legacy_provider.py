from typing import Dict, Any
from core.interfaces import SocialProvider
from core.models import ProcessedFlight
from socials import socials_processing as sp
from loguru import logger

class LegacySocialProvider(SocialProvider):
    async def post_flight(self, processed_flight: ProcessedFlight, config: Dict[str, Any]) -> bool:
        """
        Delegates to the existing socials_processing.call_socials function.
        We need to reconstruct the 'flight_data' dictionary and 'interesting_reasons' 
        expected by the legacy function.
        """
        flight = processed_flight.flight
        
        # Reconstruct flight_data dict
        flight_data = {
            'flight_name': flight.flight_name,
            'flight_name_iata': flight.flight_name_iata,
            'registration': flight.registration,
            'aircraft_name': flight.aircraft_name,
            'aircraft_icao': flight.aircraft_icao,
            'airline_name': flight.airline_name,
            'airline': flight.airline_icao,
            'origin_name': flight.origin_name,
            'origin_icao': flight.origin_icao,
            'destination_name': flight.destination_name,
            'destination_icao': flight.destination_icao,
            'scheduled_time': flight.scheduled_time,
            'terminal': flight.terminal,
            'diverted': flight.diverted,
            # Add other fields if needed by legacy code
        }
        
        # Reconstruct interesting_reasons dict
        interesting_reasons = {}
        for reason in processed_flight.reasons:
            interesting_reasons[reason.reason_code] = True
            if reason.reason_code == "REASON":
                interesting_reasons["REASON"] = reason.details

        try:
            await sp.call_socials(flight_data, interesting_reasons, config)
            return True
        except Exception as e:
            logger.error(f"Error in legacy social provider: {e}")
            return False
