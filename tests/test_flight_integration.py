import asyncio
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock
from services.flight_service import FlightService
from infrastructure.api.aeroapi_client import AeroAPIClient
from infrastructure.api.aerodatabox_client import AerodataboxClient
from core.models import Flight, FlightStatus

# Mock Config
config = {
    'settings': {
        'airport': 'LEBL',
        'fetch_window_hours': 24,
        'aeroapi_cost_limit': 5.0
    }
}

async def test_flight_service():
    print("Testing FlightService...")
    
    # Mock Dependencies
    db_provider = AsyncMock()
    db_provider.is_flight_processed.return_value = False
    
    notification_service = AsyncMock()
    filter_service = AsyncMock()
    filter_service.check_flight.return_value = MagicMock(is_interesting=True, reasons=["Test Reason"])
    
    # Mock Providers
    aero_client = AsyncMock(spec=AeroAPIClient)
    aero_client.fetch_scheduled_flights.return_value = [
        Flight(flight_id="aero1", flight_name="AERO1", scheduled_time=datetime.utcnow(), status=FlightStatus.SCHEDULED, source="aeroapi", 
               flight_name_iata="AERO1", registration="REG1", aircraft_icao="A320", airline_icao="VLG", origin_icao="LEMD", destination_icao="LEBL", raw_data={})
    ]
    
    adb_client = AsyncMock(spec=AerodataboxClient)
    adb_client.fetch_scheduled_flights.return_value = [
        Flight(flight_id="adb1", flight_name="ADB1", scheduled_time=datetime.utcnow(), status=FlightStatus.SCHEDULED, source="aerodatabox",
               flight_name_iata="ADB1", registration="REG2", aircraft_icao="B738", airline_icao="RYR", origin_icao="EGLL", destination_icao="LEBL", raw_data={})
    ]
    
    flight_service = FlightService(
        db_provider=db_provider,
        data_providers=[aero_client, adb_client],
        notification_service=notification_service,
        filter_service=filter_service
    )
    
    # Run Cycle
    await flight_service.process_cycle(config)
    
    # Verify
    assert aero_client.fetch_scheduled_flights.called
    assert adb_client.fetch_scheduled_flights.called
    assert db_provider.log_flight.call_count == 2
    assert notification_service.notify.call_count == 2
    print("FlightService Test Passed!")

async def test_aeroapi_client():
    print("\nTesting AeroAPIClient Key Rotation...")
    # This is a partial test since we can't easily mock aiohttp here without more setup, 
    # but we can test the logic if we mock the internal methods.
    
    client = AeroAPIClient(api_keys=["key1", "key2"], airport_code="LEBL")
    
    # Mock _check_usage to fail first key, pass second
    client._check_usage = AsyncMock(side_effect=[False, True])
    
    valid_key = await client._get_valid_key()
    assert valid_key == "key2"
    print("AeroAPIClient Key Rotation Test Passed!")

if __name__ == "__main__":
    asyncio.run(test_flight_service())
    asyncio.run(test_aeroapi_client())
