
import sys
from pathlib import Path


# Add project root to Python path
sys.path.append(str(Path(__file__).parent.parent))
from config import config_manager
config = config_manager.load_config()

import socials.bluesky2 as bs
import socials.telegram_msg_bot as tg
import socials.twitter_msg_script as tw
import socials.threads as th
import socials.instagram as ig
import socials.linkedin as li
from utils.image_finder import get_first_image_url_jp, get_first_image_url_pp
import os
import requests
from loguru import logger
from log.logger_config import logger
from PIL import Image, ImageDraw, ImageFont


async def call_socials(flight_data, interesting_reasons):
    logger.debug(f"Starting socials processing for flight {flight_data['flight_name']}")
    temp_image_path = None
    
    try:
        # Get the image URL
        logger.debug(f"Fetching image for registration {flight_data['registration']} from JetPhotos")
        image_url = None
        if flight_data['registration'] not in [None,'null']:
            image_url, photographer = get_first_image_url_jp(flight_data['registration'])
            add_photographer = False
            if not image_url:
                add_photographer = True
                logger.debug("No image found on JetPhotos, trying Planespotters")
                image_url, photographer = get_first_image_url_pp(flight_data['registration'])
        
        if image_url:
            image_url = image_url.replace("/400/","/full/")
            logger.debug(f"Found image at {image_url}, downloading...")
            response = requests.get(image_url)
            if response.status_code == 200:
                logger.debug("Image download successful, saving temporarily")
                temp_image_path = "socials/temp_image.jpg"
                with open(temp_image_path, "wb+") as f:
                    f.write(response.content)
                    logger.debug(f"Image saved to {temp_image_path}")

        if temp_image_path and photographer and add_photographer:
            try:
                # Open the image
                img = Image.open(temp_image_path)
                width, height = img.size
                
                # Create a new image with space for the bar
                new_height = height + 30  # Add 30px for the bar
                new_img = Image.new('RGB', (width, new_height), color=(0, 0, 0))
                
                # Paste the original image
                new_img.paste(img, (0, 0))
                
                # Add the copyright bar
                draw = ImageDraw.Draw(new_img)
                try:
                    font = ImageFont.truetype("arial.ttf", 14)
                except:
                    font = ImageFont.load_default()
                
                # Calculate text position
                text = f"{photographer}"
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                x = width - text_width - 10  # 10px padding from right
                y = height + 5  # 5px padding from bottom
                
                # Draw the text
                draw.text((x, y), text, font=font, fill=(255, 255, 255))
                
                # Save the new image
                new_img.save(temp_image_path)
                logger.debug(f"Added copyright bar for photographer {photographer}")
            except Exception as e:
                logger.error(f"Error adding copyright bar: {e}")

        if flight_data['registration'] in [None,'null']:
            logger.warning(f"No registration found for flight {flight_data['flight_name']}")
            temp_image_path = "socials/no_reg.jpg"

        # Post to enabled social networks with individual error handling
        if config['social_networks'].get('telegram', False):
            try:
                logger.info(f"Sending Telegram post for flight {flight_data['flight_name']}")
                await tg.send_flight_update(config['telemetry']['chat_id'], flight_data, temp_image_path, interesting_reasons)
                logger.success(f"Successfully sent Telegram post for flight {flight_data['flight_name']}")
            except Exception as e:
                logger.error(f"Failed to send Telegram post: {e}")

        if config['social_networks'].get('bluesky', False):
            try:
                logger.info(f"Sending Bluesky post for flight {flight_data['flight_name']}")
                bs.post_flight_to_bluesky(flight_data, temp_image_path, interesting_reasons)
                logger.success(f"Successfully sent Bluesky post for flight {flight_data['flight_name']}")
            except Exception as e:
                logger.error(f"Failed to send Bluesky post: {e}")

        if config['social_networks'].get('twitter', False):
            try:
                logger.info(f"Sending Twitter post for flight {flight_data['flight_name']}")
                await tw.create_tweet(flight_data, temp_image_path, interesting_reasons)
                logger.success(f"Successfully sent Twitter post for flight {flight_data['flight_name']}")
            except Exception as e:
                logger.error(f"Failed to send Twitter post: {e}")

        if config['social_networks'].get('threads', False):
            try:
                logger.info(f"Sending Threads post for flight {flight_data['flight_name']}")
                await th.post_to_threads(flight_data, image_path=temp_image_path)
                logger.success(f"Successfully sent Threads post for flight {flight_data['flight_name']}")
            except Exception as e:
                logger.error(f"Failed to send Threads post: {e}")

        if config['social_networks'].get('instagram', False):
            try:
                logger.info(f"Sending Instagram post for flight {flight_data['flight_name']}")
                await ig.post_to_instagram(flight_data, image_path=temp_image_path)
                logger.success(f"Successfully sent Instagram post for flight {flight_data['flight_name']}")
            except Exception as e:
                logger.error(f"Failed to send Instagram post: {e}")

        if config['social_networks'].get('linkedin', False):
            try:
                logger.info(f"Sending LinkedIn post for flight {flight_data['flight_name']}")
                await li.post_to_linkedin(flight_data, image_path=temp_image_path)
                logger.success(f"Successfully sent LinkedIn post for flight {flight_data['flight_name']}")
            except Exception as e:
                logger.error(f"Failed to send LinkedIn post: {e}")
        
    finally:
        # Clean up temporary image
        if temp_image_path and os.path.exists(temp_image_path) and temp_image_path != "socials/no_reg.jpg":
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
        "DIVERTED": False , # Not diverted
        "REASON": "es el Airbus A321 Más antiguo del mundo aún en vuelo y uno de los más antiguos de la familia A320"  # Reason for interesting
    }
    # Send test message
    import asyncio
    asyncio.run(call_socials(dummy_data, interesting_reasons))
    logger.info("Sent test message with dummy data")
