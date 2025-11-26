# How to Create a New Social Media Plugin

The Twitter Spotter v4 bot uses a plugin system for social media integrations. This allows you to add support for new platforms (like Mastodon, Discord, etc.) simply by adding a Python file to the plugins directory.

## 1. Location
Create a new Python file (e.g., `my_platform_provider.py`) in:
`infrastructure/social_media/plugins/`

## 2. Structure
Your file must define a class that inherits from `SocialProvider` and implements the `post_flight` method.

### Template
```python
from typing import Dict, Any
from loguru import logger
from core.interfaces import SocialProvider
from core.models import ProcessedFlight

class MyPlatformProvider(SocialProvider):
    async def post_flight(self, processed_flight: ProcessedFlight, config: Dict[str, Any]) -> bool:
        """
        Post flight details to MyPlatform.
        
        Args:
            processed_flight: Object containing flight data and interesting reasons.
            config: The full configuration dictionary.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        
        # 1. Check if enabled in config
        if not config['social_networks'].get('my_platform', False):
            return False

        # 2. Extract Data
        flight = processed_flight.flight
        flight_name = flight.flight_name_iata
        registration = flight.registration
        
        # 3. Get Image (Optional)
        # The system automatically fetches and processes the image before calling this method.
        # The local path to the image is stored in flight.image_url
        image_path = flight.image_url
        
        # 4. Generate Message
        message = f"Interesting flight detected: {flight_name} ({registration})"
        
        # 5. Send to API
        try:
            # Your API logic here...
            # client.post(message, image=image_path)
            logger.success(f"Posted to MyPlatform: {flight_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to post to MyPlatform: {e}")
            return False
```

## 3. Inputs & Logic

### `processed_flight` (ProcessedFlight)
Contains all the information about the flight and why it was flagged.
-   **`processed_flight.flight`**: The raw flight data.
    -   `flight.flight_name_iata` (e.g., "IB1234")
    -   `flight.registration` (e.g., "EC-MEO")
    -   `flight.aircraft_type` (e.g., "Airbus A350-900")
    -   `flight.origin`, `flight.destination` (ICAO codes)
    -   `flight.image_url`: **Important!** This will contain the **absolute local path** to the downloaded and processed image file (with copyright bar), or `None` if no image was found.
-   **`processed_flight.reasons`**: A list of `InterestingReason` enums explaining why the flight is interesting (e.g., `MODEL`, `REGISTRATION`, `FIRST_SEEN`).

### `config` (Dict)
The full configuration dictionary loaded from `config.json` (and environment variables).
-   Use `config['social_networks']` to check if your provider is enabled.
-   Use `os.getenv()` to retrieve API keys and credentials. **Do not hardcode credentials.**

## 4. Activation
1.  Save your file in `infrastructure/social_media/plugins/`.
2.  Restart the bot (`python main.py`).
3.  The bot will automatically discover and load your plugin. You will see a log message: `Loaded social plugin: MyPlatformProvider`.
