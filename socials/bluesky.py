# uswe https://docs.bsky.app/docs/get-started

# uses threads api https://developers.facebook.com/docs/threads
import os
import requests
import argparse
from utils.create_bsky_post import create_post
from utils.image_finder import get_first_image_url_jp, get_first_image_url_pp
from loguru import logger
from PIL import Image
import io

def generate_flight_message(flight_data):
    """Generate a formatted message from flight data"""
    logger.info(f"Generating Bluesky message for flight {flight_data['flight_name']}")
    message = f"✈️ Flight Information:\n\n"
    message += f"Flight: {flight_data['flight_name']}\n"
    message += f"Registration: {flight_data['registration']}\n"
    message += f"Aircraft: {flight_data['aircraft_name'] if flight_data['aircraft_name'] else flight_data['aircraft_icao']}\n"
    message += f"Airline: {flight_data['airline_name']} ({flight_data['airline']})\n"
    message += f"Route: {flight_data['origin_name']} ({flight_data['origin_icao']}) → "
    message += f"{flight_data['destination_name']} ({flight_data['destination_icao']})\n"
    message += f"Scheduled Time: {flight_data['scheduled_time']}\n"
    message += f"Terminal: {flight_data['terminal']}\n"
    if flight_data['diverted'] not in [None, False, 'null']:
        message += "\n⚠️ This flight has been diverted"
    message += "\n\n"
    message += "Check all our socials in https://linktr.ee/ctrl_plataforma"
    return message

def post_flight_to_bluesky(flight_data, image_path=None):
    """Post flight information to Bluesky"""
    logger.info(f"Posting flight {flight_data['flight_name']} to Bluesky")
    ATP_AUTH_HANDLE = 'lemdspotter.bsky.social'
    ATP_AUTH_PASSWORD = 'sdpMAD1217'
    message = generate_flight_message(flight_data)
    
    if image_path and flight_data['registration']:
        logger.info(f"Posting with image from {image_path}")
        try:
            # First check if original image is larger than 1MB
            if os.path.getsize(image_path) > 1000000:
                with Image.open(image_path) as img:
                    # Create BytesIO buffer for compression
                    # First attempt with 85% quality
                    output = io.BytesIO()
                    img.convert('RGB').save(output, format='JPEG', quality=85, optimize=True)
                    
                    # Check if compressed image is still too large
                    #if output.tell() > 1000000:
                    # Calculate half resolution
                    new_size = (img.width // 2, img.height // 2)
                    img = img.resize(new_size, Image.Resampling.LANCZOS)

                    # If still too large, reduce quality further
                    if output.tell() > 1000000:
                        quality = 80
                        while quality >= 50:  # Don't go below 50 quality
                            output.seek(0)
                            img.convert('RGB').save(output, format='JPEG', quality=quality, optimize=True)
                            if output.tell() <= 1000000:  # 1MB in bytes
                                break
                            quality -= 5
                
                # Save compressed image to temporary file
                    image_path = f"{image_path}_compressed.jpg"
                    with open(image_path, 'wb') as f:
                        f.write(output.getbuffer())
                
                    logger.debug(f"Compressed image to {output.tell()} bytes (resized to {new_size}, quality {quality})")

            args = argparse.Namespace(
                pds_url="https://bsky.social",
                handle=ATP_AUTH_HANDLE,
                password=ATP_AUTH_PASSWORD,
                text=message,
                image=[image_path],
                alt_text=f"Aircraft photo of {flight_data['registration']}",
                lang=None,
                reply_to=None,
                embed_url=f"https://www.flightradar24.com/{flight_data['flight_name']}",
                embed_ref=None
            )
            create_post(args)
            logger.success(f"Successfully posted flight {flight_data['flight_name']} with image to Bluesky")
        except Exception as e:
            logger.error(f"Failed to post flight with image: {e}")
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
                embed_url=f"https://www.flightradar24.com/{flight_data['flight_name']}",
                embed_ref=None
            )
            create_post(args)
            logger.success(f"Successfully posted flight {flight_data['flight_name']} without image to Bluesky")
        except Exception as e:
            logger.error(f"Failed to post flight without image: {e}")
            raise