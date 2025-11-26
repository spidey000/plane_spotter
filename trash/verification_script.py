import asyncio
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime
from core.models import Flight, FlightStatus
from services.flight_service import FlightService
from services.filter_service import FilterService

async def run_verification():
    print("Starting verification...")

    # 1. Mock Database Provider
    mock_db = MagicMock()
    mock_db.get_interesting_models = AsyncMock(return_value={'A388': {'name': 'Airbus A380', 'reason': 'Big plane'}})
    mock_db.get_interesting_registrations = AsyncMock(return_value={'CS-TSE': {'reason': 'Special Livery'}})
    mock_db.get_registration_history = AsyncMock(return_value=None) # Always new
    mock_db.is_flight_processed = AsyncMock(return_value=False)
    mock_db.log_flight = AsyncMock(return_value=True)
    mock_db.upsert_registration = AsyncMock(return_value=True)

    # 2. Mock Data Provider
    mock_api = MagicMock()
    mock_flight = Flight(
        flight_id="test_123",
        flight_name="TP123",
        registration="CS-TSE",
        aircraft_icao="A320",
        source="mock",
        status=FlightStatus.SCHEDULED
    )
    mock_api.fetch_scheduled_flights = AsyncMock(return_value=[mock_flight])

    # 3. Mock Social Provider
    mock_social = MagicMock()
    mock_social.post_flight = AsyncMock(return_value=True)

    # 4. Initialize Services
    filter_service = FilterService(mock_db)
    flight_service = FlightService(
        db_provider=mock_db,
        data_providers=[mock_api],
        social_providers=[mock_social],
        filter_service=filter_service
    )

    # 5. Run Cycle
    config = {'flight': {'time_range_hours': 2}}
    await flight_service.process_cycle(config)

    # 6. Verify Interactions
    print("Verifying interactions...")
    
    # Check if flight was fetched
    mock_api.fetch_scheduled_flights.assert_called_once()
    print("✅ Flight fetched")

    # Check if interesting rules were checked
    # CS-TSE is interesting by registration
    mock_social.post_flight.assert_called_once()
    print("✅ Interesting flight posted")

    # Check if flight was logged
    mock_db.log_flight.assert_called_once()
    print("✅ Flight logged to DB")

    print("Verification successful!")

if __name__ == "__main__":
    asyncio.run(run_verification())
