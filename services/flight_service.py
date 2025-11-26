
import asyncio
from typing import List
from datetime import datetime, timedelta
from loguru import logger
from services.notification_service import NotificationService
from core.interfaces import DatabaseProvider, FlightDataProvider
from services.filter_service import FilterService
from core.models import Flight

class FlightService:
    def __init__(
        self, 
        db_provider: DatabaseProvider, 
        data_providers: List[FlightDataProvider], 
        notification_service: NotificationService,
        filter_service: FilterService,
        debug: bool = False
    ):
        self.db_provider = db_provider
        self.data_providers = data_providers
        self.notification_service = notification_service
        self.filter_service = filter_service
        self.debug = debug

    async def process_cycle(self, config: dict):
        """
        Main execution cycle:
        1. Determine time window
        2. Fetch flights from all providers
        3. Deduplicate
        4. Process
        """
        logger.info("Starting flight processing cycle...")
        
        # 1. Determine Time Window
        # Fetch flights for the next X hours (default 24)
        hours_ahead = config['settings'].get('fetch_window_hours', 24)
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=hours_ahead)
        
        all_flights: List[Flight] = []
        
        # 2. Fetch from all providers
        for provider in self.data_providers:
            try:
                provider_name = provider.__class__.__name__
                logger.info(f"Fetching flights from {provider_name}...")
                flights = await provider.fetch_scheduled_flights(start_time, end_time, config)
                
                if self.debug:
                    logger.info(f"  > {provider_name} returned {len(flights)} flights")
                    # User requested to remove per-flight logging at this stage
                    # for f in flights:
                    #     logger.info(f"    - {f.flight_name_iata} ({f.registration}) {f.scheduled_time}")

                all_flights.extend(flights)
            except Exception as e:
                logger.error(f"Error fetching from {provider_name}: {e}")
        
        if not all_flights:
            logger.warning("No flights found from any provider.")
            return

        # 3. Deduplicate (Simple dedupe based on registration + approx time could be added here)
        # For now, we trust the database check to handle duplicates, but we can do a quick in-memory dedupe
        # based on flight number and day to avoid processing the exact same object twice if providers overlap.
        unique_flights = {f"{f.flight_name}_{f.scheduled_time}": f for f in all_flights}.values()
        
        logger.info(f"Processing {len(unique_flights)} unique flights...")
        
        # 4. Process
        airport_icao = config['settings']['airport']
        await self.process_flights_for_airport(list(unique_flights), airport_icao, config)
        
        logger.success("Cycle completed.")

    async def process_flights_for_airport(self, all_flights: List[Flight], airport_icao: str, config: dict):
        # 2. Process Each Flight
        for flight in all_flights:
            # Check if already processed
            # Check if already processed
            if await self.db_provider.is_flight_processed(flight.flight_id, airport_icao):
                if self.debug:
                    # Compact log for skipped flight: [DB:1]
                    logger.info(f"Skipped: {flight.flight_name_iata} ({flight.registration}) [DB:1]")
                continue

            # Check if interesting
            processed_flight = await self.filter_service.check_flight(flight, config)
            
            # Construct compact flags string
            # Start with DB:0 since we know it wasn't in DB
            flags_str = "DB:0"
            for key, val in processed_flight.check_flags.items():
                flags_str += f" {key}:{val}"
            
            if processed_flight.is_interesting:
                logger.info(f"Interesting: {flight.flight_name_iata} ({flight.registration}) [{flags_str}] - Reasons: {processed_flight.reasons}")
                
                # 4. Notify
                await self.notification_service.notify(processed_flight, config)
            else:
                if self.debug:
                    logger.info(f"Not interesting: {flight.flight_name_iata} ({flight.registration}) [{flags_str}]")
            
            # 5. Log as processed
            await self.db_provider.log_flight(flight, airport_icao)

