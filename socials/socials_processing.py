
import sys
from pathlib import Path


# Add project root to Python path
sys.path.append(str(Path(__file__).parent.parent))
from config import config_manager
config = config_manager.load_config()

import socials.bluesky as bs
import socials.telegram_msg_bot as tg
import socials.twitter as tw
import socials.threads as th
import socials.instagram as ig
import socials.linkedin as li
from utils.image_finder import get_first_image_url_jp, get_first_image_url_pp
import os
import requests
from loguru import logger
from log.logger_config import logger


async def call_socials(flight_data, interesting):
    logger.debug(f"Starting socials processing for flight {flight_data['flight_name']}")
    temp_image_path = None
    
    try:
        # Get the image URL
        logger.debug(f"Fetching image for registration {flight_data['registration']} from JetPhotos")
        image_url = None
        if flight_data['registration'] not in [None,'null']:
            image_url = get_first_image_url_jp(flight_data['registration'])
            if not image_url:
                logger.debug("No image found on JetPhotos, trying Planespotters")
                image_url = get_first_image_url_pp(flight_data['registration'])
        
        if image_url:
            logger.debug(f"Found image at {image_url}, downloading...")
            response = requests.get(image_url)
            if response.status_code == 200:
                logger.debug("Image download successful, saving temporarily")
                temp_image_path = "socials/temp_image.jpg"
                with open(temp_image_path, "wb+") as f:
                    f.write(response.content)
                    logger.debug(f"Image saved to {temp_image_path}")
        
        # Post to enabled social networks
        if config['social_networks'].get('telegram', False):
            logger.info(f"Sending Telegram post for flight {flight_data['flight_name']}")
            await tg.send_flight_update(config['telemetry']['chat_id'], flight_data, image_path=temp_image_path)
            logger.success(f"Successfully sent Telegram post for flight {flight_data['flight_name']}")
            
        if config['social_networks'].get('bluesky', False):
            logger.info(f"Sending Bluesky post for flight {flight_data['flight_name']}")
            bs.post_flight_to_bluesky(flight_data, image_path=temp_image_path)
            logger.success(f"Successfully sent Bluesky post for flight {flight_data['flight_name']}")
            
        if config['social_networks'].get('twitter', False):
            logger.info(f"Sending Twitter post for flight {flight_data['flight_name']}")
            await tw.post_to_twitter(flight_data, image_path=temp_image_path)
            logger.success(f"Successfully sent Twitter post for flight {flight_data['flight_name']}")
            
        if config['social_networks'].get('threads', False):
            logger.info(f"Sending Threads post for flight {flight_data['flight_name']}")
            await th.post_to_threads(flight_data, image_path=temp_image_path)
            logger.success(f"Successfully sent Threads post for flight {flight_data['flight_name']}")
            
        if config['social_networks'].get('instagram', False):
            logger.info(f"Sending Instagram post for flight {flight_data['flight_name']}")
            await ig.post_to_instagram(flight_data, image_path=temp_image_path)
            logger.success(f"Successfully sent Instagram post for flight {flight_data['flight_name']}")
            
        if config['social_networks'].get('linkedin', False):
            logger.info(f"Sending LinkedIn post for flight {flight_data['flight_name']}")
            await li.post_to_linkedin(flight_data, image_path=temp_image_path)
            logger.success(f"Successfully sent LinkedIn post for flight {flight_data['flight_name']}")
        
    finally:
        # Clean up temporary image
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)
            logger.debug(f"Removed temporary image {temp_image_path}")

if __name__ == "__main__":
    # Create dummy flight data for testing
    dummy_data = {
        'flight_name_iata': 'TEST FLIGHT',
        'flight_name': 'TEST FLIGHT',
        'registration': 'CS-TST',
        'aircraft_name': 'Airbus A320',
        'aircraft_icao': 'A320',
        'airline_name': 'TAP Air Portugal',
        'airline': 'TAP',
        'origin_name': 'Lisbon',
        'origin_icao': 'LPPT',
        'destination_name': 'Paris',
        'destination_icao': 'LFPG',
        'scheduled_time': '2024-01-01 12:00',
        'terminal': '1',
        'diverted': False
    }
    
    interesting_reasons = {
        "MODEL": True,  # Interesting aircraft model
        "REGISTRATION": True,  # Interesting registration
        "FIRST_SEEN": True,  # First time seeing this flight
        "DIVERTED": False  # Not diverted
    }
    # Send test message
    import asyncio
    asyncio.run(call_socials(flight_data=dummy_data, interesting=interesting_reasons))
    logger.info("Sent test Telegram message with dummy data")
