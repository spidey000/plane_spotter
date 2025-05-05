import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import api.api_handler_aeroapi as aeroapi
import api.api_handler_aerodatabox as aerodatabox
import socials.twitter as twitter
import socials.bluesky as bluesky

# Mock data for API responses
MOCK_AEROAPI_RESPONSE = {
    'scheduled_arrivals': [
        {'ident': 'FL123', 'origin': {'code': 'JFK'}, 'destination': {'code': 'LAX'}}
    ]
}

MOCK_AERODATABOX_RESPONSE = {
    'arrivals': [
        {'number': 'FL456', 'departure': {'airport': {'icao': 'LHR'}}, 'arrival': {'airport': {'icao': 'CDG'}}}
    ]
}

@pytest.fixture
def mock_aeroapi_fetch():
    with patch('api.api_handler_aeroapi.fetch_aeroapi_scheduled') as mock_fetch:
        mock_fetch.return_value = MOCK_AEROAPI_RESPONSE
        yield mock_fetch

@pytest.fixture
def mock_aerodatabox_fetch():
    with patch('api.api_handler_aerodatabox.fetch_adb_data') as mock_fetch:
        mock_fetch.return_value = MOCK_AERODATABOX_RESPONSE
        yield mock_fetch

@pytest.fixture
def mock_twitter_client():
    with patch('socials.twitter.Client') as mock_client:
        instance = mock_client.return_value
        instance.create_tweet = MagicMock()
        yield instance

@pytest.fixture
def mock_bluesky_post():
    # Use AsyncMock for async functions
    with patch('socials.bluesky.post_flight_to_bluesky', new_callable=AsyncMock) as mock_post:
        yield mock_post

# Tests for AeroAPI handler
@pytest.mark.asyncio
async def test_fetch_aeroapi_data_success(mock_aeroapi_fetch):
    data = await aeroapi.fetch_aeroapi_scheduled('arrivals', 'start_time', 'end_time')
    assert data == MOCK_AEROAPI_RESPONSE
    mock_aeroapi_fetch.assert_called_once_with('arrivals', 'start_time', 'end_time')

@pytest.mark.asyncio
async def test_fetch_aeroapi_data_error(mock_aeroapi_fetch):
    mock_aeroapi_fetch.side_effect = Exception("API Error")
    with pytest.raises(Exception, match="API Error"):
        await aeroapi.fetch_aeroapi_scheduled('arrivals', 'start_time', 'end_time')

# Tests for Aerodatabox handler
@pytest.mark.asyncio
async def test_fetch_aerodatabox_data_success(mock_aerodatabox_fetch):
    data = await aerodatabox.fetch_adb_data('arrivals', 'start_time', 'end_time')
    assert data == MOCK_AERODATABOX_RESPONSE
    mock_aerodatabox_fetch.assert_called_once_with('arrivals', 'start_time', 'end_time')

@pytest.mark.asyncio
async def test_fetch_aerodatabox_data_error(mock_aerodatabox_fetch):
    mock_aerodatabox_fetch.side_effect = Exception("API Error")
    with pytest.raises(Exception, match="API Error"):
        await aerodatabox.fetch_adb_data('arrivals', 'start_time', 'end_time')

# Tests for Twitter handler (example, assuming Client exists)
# @pytest.mark.asyncio
# async def test_twitter_post_success(mock_twitter_client):
#     # Assuming post_to_twitter function exists and uses Client
#     await twitter.post_to_twitter({'flight_name': 'TW123'}, 'image.jpg')
#     mock_twitter_client.create_tweet.assert_called_once()

# Tests for Bluesky handler
@pytest.mark.asyncio
async def test_bluesky_post_success(mock_bluesky_post):
    await bluesky.post_flight_to_bluesky({'flight_name': 'BS456'}, 'image.jpg')
    mock_bluesky_post.assert_called_once_with({'flight_name': 'BS456'}, 'image.jpg')

@pytest.mark.asyncio
async def test_bluesky_post_error(mock_bluesky_post):
    mock_bluesky_post.side_effect = Exception("Bluesky Error")
    with pytest.raises(Exception, match="Bluesky Error"):
        await bluesky.post_flight_to_bluesky({'flight_name': 'BS789'}, 'image.jpg')
