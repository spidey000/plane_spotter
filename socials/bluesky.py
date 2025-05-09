# uswe https://docs.bsky.app/docs/get-started

# uses threads api https://developers.facebook.com/docs/threads
import sys
from pathlib import Path
# Add project root to Python path
sys.path.append(str(Path(__file__).parent.parent))

import os
import requests
import argparse
from utils.create_bsky_post import create_post
from utils.image_finder import get_first_image_url_jp, get_first_image_url_pp
from loguru import logger
from PIL import Image
import io
from config import config_manager
from log.logger_config import logger
from socials.telegram_msg_bot import generate_flight_message

# def generate_flight_message(flight_data):
#     flight_name = flight_data['flight_name_iata'] if flight_data['flight_name_iata'] not in [None, 'null'] else flight_data['flight_name']
#     """Generate a formatted message from flight data"""
#     logger.info(f"Generating Bluesky message for flight {flight_name}")
#     message = f"✈️ Flight Information:\n\n"
#     message += f"Flight: {flight_name}\n"
#     message += f"Registration: {flight_data['registration']}\n"
#     message += f"Aircraft: {flight_data['aircraft_name'] if flight_data['aircraft_name'] else flight_data['aircraft_icao']}\n"
#     message += f"Airline: {flight_data['airline_name']} ({flight_data['airline']})\n"
#     message += f"Route: {flight_data['origin_name']} ({flight_data['origin_icao']}) → "
#     message += f"{flight_data['destination_name']} ({flight_data['destination_icao']})\n"
#     message += f"Scheduled Time: {flight_data['scheduled_time']}\n"
#     message += f"Terminal: {flight_data['terminal']}\n"
#     if flight_data['diverted'] not in [None, False, 'null']:
#         message += "\n⚠️ This flight has been diverted"
#     message += "\n\n"
#     message += "Check all our socials in https://linktr.ee/ctrl_plataforma"
#     return message

def post_flight_to_bluesky(flight_data, image_path=None, interesting_reasons=None):
    """Post flight information to Bluesky"""
    flight_name = flight_data['flight_name_iata'] if flight_data['flight_name_iata'] not in [None, 'null'] else flight_data['flight_name']
    logger.info(f"Posting flight {flight_name} to Bluesky")
    config = config_manager.load_config()
    ATP_AUTH_HANDLE = os.getenv('BLUESKY_HANDLE')
    ATP_AUTH_PASSWORD = os.getenv('BLUESKY_PASSWORD')
    message = generate_flight_message(flight_data, interesting_reasons)
    
    if os.path.getsize(image_path) > 1000000:
        with Image.open(image_path) as img:
            # Create BytesIO buffer for compression
            output = io.BytesIO()
            
            # First attempt with 85% quality
            img.convert('RGB').save(output, format='JPEG', quality=85, optimize=True)
            
            # If the image is already below 1MB, save it and exit
            if output.tell() <= 1000000:
                compression_successful = True
            else:
                # If still too large, reduce resolution
                new_size = (img.width // 2, img.height // 2)
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Reduce quality further if needed
                q = 80  # Initialize q
                compression_successful = False
                while q >= 50:  # Don't go below 50 quality
                    output.seek(0)
                    img.convert('RGB').save(output, format='JPEG', quality=q, optimize=True)
                    if output.tell() <= 1000000:  # 1MB in bytes
                        compression_successful = True
                        break
                    q -= 10

            # Save the compressed image if successful
            if compression_successful:
                # Save compressed image to temporary file
                image_path = f"{image_path}_compressed.jpg"
                with open(image_path, 'wb') as f:
                    f.write(output.getbuffer())
                logger.debug(f"Compressed image to {output.tell()} bytes (resized to {new_size}, quality {q})")

            else:
                logger.error("Unable to compress image below 1MB even at minimum quality")

                logger.info("Posting without image")
                try:
                    args = argparse.Namespace(
                        pds_url="https://bsky.social",
                        handle=ATP_AUTH_HANDLE,
                        password=ATP_AUTH_PASSWORD,
                        text=message,
                        image=None,
                        alt_text=None,
                        lang=None,
                        reply_to=None,
                        embed_url="",
                        embed_ref=None
                    )
                    create_post(args)
                    logger.success(f"Successfully posted flight {flight_name} without image to Bluesky")
                except Exception as e:
                    logger.error(f"Failed to post flight without image: {e}")
                    raise

    else:
        logger.info("Posting without image")
        try:
            args = argparse.Namespace(
                pds_url="https://bsky.social",
                handle=ATP_AUTH_HANDLE,
                password=ATP_AUTH_PASSWORD,
                text=message,
                image=None,
                alt_text=None,
                lang=None,
                reply_to=None,
                embed_url="",
                embed_ref=None
            )
            create_post(args)
            logger.success(f"Successfully posted flight {flight_name} without image to Bluesky")
        except Exception as e:
            logger.error(f"Failed to post flight without image: {e}")
            raise
