import os
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger
from supabase import create_client, Client
from core.interfaces import DatabaseProvider
from core.models import Flight

class SupabaseProvider(DatabaseProvider):
    def __init__(self, url: str, key: str):
        self.supabase: Client = create_client(url, key)

    async def get_interesting_models(self, airport_icao: str) -> Dict[str, Any]:
        try:
            response = self.supabase.table("interesting_models").select("*").eq("is_active", True).eq("airport_icao", airport_icao).execute()
            # Convert list to dict keyed by icao_code for O(1) lookup
            return {item['icao_code']: item for item in response.data}
        except Exception as e:
            logger.error(f"Error fetching interesting models: {e}")
            return {}

    async def get_interesting_registrations(self, airport_icao: str) -> Dict[str, Any]:
        try:
            response = self.supabase.table("interesting_registrations").select("*").eq("is_active", True).eq("airport_icao", airport_icao).execute()
            # Convert list to dict keyed by registration
            return {item['registration']: item for item in response.data}
        except Exception as e:
            logger.error(f"Error fetching interesting registrations: {e}")
            return {}

    async def get_registration_history(self, registration: str, airport_icao: str) -> Optional[Dict[str, Any]]:
        try:
            response = self.supabase.table("registrations").select("*").eq("registration", registration).eq("airport_icao", airport_icao).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error fetching registration history for {registration}: {e}")
            return None

    async def upsert_registration(self, registration_data: Dict[str, Any]) -> bool:
        try:
            # Check if exists first to update last_seen_at
            # registration_data MUST contain 'airport_icao'
            if 'airport_icao' not in registration_data:
                logger.error("airport_icao missing in registration_data")
                return False

            existing = await self.get_registration_history(registration_data['registration'], registration_data['airport_icao'])
            
            data = {
                "airport_icao": registration_data['airport_icao'],
                "registration": registration_data['registration'],
                "last_seen_at": datetime.utcnow().isoformat(),
            }
            
            if 'aircraft_type_icao' in registration_data:
                data['aircraft_type_icao'] = registration_data['aircraft_type_icao']
            if 'airline_icao' in registration_data:
                data['airline_icao'] = registration_data['airline_icao']
            if 'image_url' in registration_data:
                data['image_url'] = registration_data['image_url']

            if existing:
                self.supabase.table("registrations").update(data).eq("id", existing['id']).execute()
            else:
                data['first_seen_at'] = datetime.utcnow().isoformat()
                self.supabase.table("registrations").insert(data).execute()
            return True
        except Exception as e:
            logger.error(f"Error upserting registration {registration_data.get('registration')}: {e}")
            return False

    async def is_flight_processed(self, flight_id: str, airport_icao: str) -> bool:
        try:
            response = self.supabase.table("flight_history").select("id").eq("flight_id_external", flight_id).eq("airport_icao", airport_icao).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error checking flight history for {flight_id}: {e}")
            return False

    async def log_flight(self, flight: Flight, airport_icao: str) -> bool:
        try:
            data = {
                "airport_icao": airport_icao,
                "flight_id_external": flight.flight_id,
                "registration": flight.registration,
                "flight_number": flight.flight_name_iata,
                "processed_at": datetime.utcnow().isoformat()
            }
            self.supabase.table("flight_history").insert(data).execute()
            return True
        except Exception as e:
            logger.error(f"Error logging flight {flight.flight_id}: {e}")
            return False
