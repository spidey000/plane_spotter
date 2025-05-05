import sys
from pathlib import Path
from config import config_manager

config = config_manager.load_config()

# Add project root to Python path
sys.path.append(str(Path(__file__).parent.parent))

import socials.bluesky as bs
import socials.telegram as tg
import socials.twitter as tw
import socials.threads as th
import socials.instagram as ig
import socials.linkedin as li
from utils.image_finder import get_first_image_url_jp, get_first_image_url_pp
import os
import requests
from loguru import logger

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
        if config.get('social_networks.telegram'):
            telegram_task = await tg.schedule_telegram(flight_data, image_path=temp_image_path)
            await telegram_task
            
        if config['social_networks'].get('bluesky', False):
            await bs.post_flight_to_bluesky(flight_data, image_path=temp_image_path)
            
        if config['social_networks'].get('twitter', False):
            await tw.post_to_twitter(flight_data, image_path=temp_image_path)
            
        if config['social_networks'].get('threads', False):
            await th.post_to_threads(flight_data, image_path=temp_image_path)
            
        if config['social_networks'].get('instagram', False):
            await ig.post_to_instagram(flight_data, image_path=temp_image_path)
            
        if config['social_networks'].get('linkedin', False):
            await li.post_to_linkedin(flight_data, image_path=temp_image_path)
        
    finally:
        # Clean up temporary image
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)
            logger.debug(f"Removed temporary image {temp_image_path}")

