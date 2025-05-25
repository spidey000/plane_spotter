import os
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import random


# Twikit imports
from twikit import Client
from twikit.errors import (
    TwitterException,
    DuplicateTweet,
    InvalidMedia,
    AccountLocked,
    Unauthorized,
    Forbidden,
    NotFound,
    CouldNotTweet
)

# Project-specific imports (assuming they exist in your project structure)
try:
    from log.logger_config import logger
except ImportError:
    print("No logger found")

# The following imports are based on your original code.
# Their functionality will be stubbed or used with placeholders
# as their actual implementation is not provided.
import utils.image_finder as image_finder
from config import config_manager # Keep import for type hinting or if other functions need it

# --- Helper Functions ---

def _get_env_var(var_name: str) -> str:
    """
    Retrieves an environment variable. Raises ValueError if not set.
    """
    value = os.getenv(var_name)
    if value is None:
        msg = f"Missing required environment variable: {var_name}"
        logger.error(msg)
        raise ValueError(msg)
    return value

async def _initialize_and_login_client() -> Client:
    """
    Initializes the Twikit client, handles login with credential fallbacks,
    and manages cookie loading/saving for session persistence.
    """

    COOKIES_FILE_PATH = 'utils/cookies.json'

    client = Client(language='en-US') # As per documentation and original code

    # 1. Attempt to load cookies and verify session
    if os.path.exists(COOKIES_FILE_PATH):
        logger.info(f"Found cookies file at {COOKIES_FILE_PATH}. Attempting to load.")
        try:
            client.load_cookies(COOKIES_FILE_PATH)
            # Verify if cookies are valid by fetching user ID (a lightweight API call)
            await client.user_id()
            logger.info("Successfully logged in using saved cookies.")
            return client
        except AccountLocked as e_lock:
            logger.warning(f"Account locked with saved cookies: {e_lock}. Attempting fresh login.")
        except (Unauthorized, Forbidden) as e_auth:
            logger.warning(f"Cookie authentication failed (Unauthorized/Forbidden): {e_auth}. Attempting fresh login.")
        except TwitterException as e_twitter: # Catch other Twitter API errors
            logger.warning(f"Cookie login failed due to Twitter API error: {e_twitter}. Attempting fresh login.")
        except Exception as e_exc: # Catch other errors like file corruption
            logger.warning(f"Error processing cookies file: {e_exc}. Attempting fresh login.")
    else:
        logger.info("Cookies file not found. Proceeding with credential-based login.")

    # 2. If cookie login fails or cookies don't exist, proceed with credential login
    try:
        twitter_user = _get_env_var('TWITTER_USER')
        twitter_email = os.getenv('TWITTER_EMAIL') # Optional, can be None
        twitter_password = _get_env_var('TWITTER_PASS')

        logger.info("Attempting to login with username/email and password...")
        await client.login(
            auth_info_1=twitter_user,
            auth_info_2=twitter_email, # twikit handles if this is None
            password=twitter_password
            # The 'cookies_file' parameter in client.login() is not in the provided docs.
            # Using client.save_cookies() / client.load_cookies() instead.
        )
        logger.info("Login successful with credentials.")

        # 3. Save cookies for future sessions
        try:
            client.save_cookies(COOKIES_FILE_PATH)
            logger.info(f"Cookies saved successfully to {COOKIES_FILE_PATH}")
        except Exception as e_save:
            logger.warning(f"Failed to save cookies: {e_save}")
        
        return client

    except ValueError: # Raised by _get_env_var for missing essential credentials
        raise # Re-raise to be caught by the calling function
    except (AccountLocked, Unauthorized, Forbidden) as e_login_auth:
        logger.error(f"Login failed due to account/auth issue: {e_login_auth}")
        raise
    except TwitterException as e_login_twitter:
        logger.error(f"A Twitter API error occurred during login: {e_login_twitter}")
        raise
    except Exception as e_login_unexpected:
        logger.error(f"An unexpected error occurred during login: {e_login_unexpected}")
        raise

def generate_flight_message_twitter(flight_data, interesting_reasons, config, max_size=280):
    """Generate a formatted message from flight data"""
    scheduled_time = datetime.strptime(flight_data['scheduled_time'], "%Y-%m-%d %H:%M")
    time_alert = f"hoy día {scheduled_time.strftime('%d a las %H:%M')}"
    airline_text = f"{flight_data['airline_name'] if flight_data['airline_name'] not in [None, 'null'] else flight_data['airline']}"

    if flight_data['origin_name'] == config['settings']['airport_name']:
        move = 'salida'
    else:
        move = 'llegada'
        
    introducciones = [
    f"📡 ¡Atentos! Tráfico de {move} {time_alert} con {airline_text} en {config['settings']['airport_name']}",
    f"✈️ Curioso avistamiento: {move} de {airline_text} {time_alert} en {config['settings']['airport_name']}",
    f"📸 Spotters, esta {move} de {airline_text} merece foto {time_alert}",
    f"🚨 Tráfico de {move} de {airline_text} {time_alert} en {config['settings']['airport_name']}",
    f"🤯 Joyita en {config['settings']['airport_name']}: {move} de {airline_text} {time_alert}",
    f"👁️ Spotting top: {move} de {airline_text} {time_alert} en {config['settings']['airport_name']}",
    f"🗞️ Desde pista: {move} de {airline_text} en {config['settings']['airport_name']} {time_alert}",
    f"🛬 Vuelo interesante: {move} de {airline_text} {time_alert} en {config['settings']['airport_name']}",
    f"🌤️ Cielo movido en {config['settings']['airport_name']}: {move} de {airline_text} {time_alert}",
    f"📷 Teleobjetivo listo: {move} de {airline_text} {time_alert}",
    f"📍 Desde pista en {config['settings']['airport_name']}: {move} de {airline_text} {time_alert}",
    f"⏱️ Momento spotter: {move} de {airline_text} {time_alert} en {config['settings']['airport_name']}",
    f"🔔 Atención: {move} de {airline_text} {time_alert} en {config['settings']['airport_name']}",
]


    message = ""
    # #                interesting_reasons = {
    #                 "MODEL": interesting_model,
    #                 "REGISTRATION": interesting_registration,
    #                 "FIRST_SEEN": first_seen,
    #                 "DIVERTED": False if flight_data.get("diverted", "null") == "null" else flight_data["diverted"],
    #                 "REASON": reason
    #             }

    flight_name = flight_data['flight_name_iata'] if flight_data['flight_name_iata'] not in [None, 'null'] else flight_data['flight_name']
    message = f"https://www.flightradar24.com/data/flights/{flight_name.replace(' ','')}\n\n"
    
    first_seen_part = f"Primera visita de {flight_data['registration'] if flight_data['registration'] not in [None, 'null'] else 'Unkown'}, " if interesting_reasons.get("FIRST_SEEN", False) else ""
    model_part = f"Un {flight_data['aircraft_name'] if flight_data['aircraft_name'] else flight_data['aircraft_icao']}. " if interesting_reasons.get("MODEL", False) else ""
    message += f"{first_seen_part}{model_part} {move} de {airline_text} {time_alert} en {config['settings']['airport_name']}\n\n"
        
    # if interesting_reasons.get("REGISTRATION", False):
    #     message += f"{interesting_reasons.get('REASON')}.\n"
        
    # if interesting_reasons.get("FIRST_SEEN", False):
    #     message += f"Primera visita de {flight_data['registration'] if flight_data['registration'] not in [None, 'null'] else 'Unkown'}.\n"
    if interesting_reasons.get("REGISTRATION", False):
        message += f"Interesante porque {interesting_reasons.get('REASON')}.\n\n"
    if interesting_reasons.get("DIVERTED", False):
        message += "Es un vuelo desviado. 🧭\n\n"

    message += f"\nFlight: {flight_data['flight_name_iata']}{'/' + flight_data['flight_name'] if flight_data['flight_name'] not in [None, 'null'] else ''}\n"
    message += f"Callsign: {flight_data['callsign']} {flight_data['flight_name'][3:] if flight_data.get('flight_name') else ''}\n" if flight_data.get('callsign') not in [None, 'null'] else ''
    message += f"Registration: {flight_data['registration'] if flight_data['registration'] not in [None, 'null'] else 'Unkown'}\n"
    message += f"Aircraft: {flight_data['aircraft_name'] if flight_data['aircraft_name'] else flight_data['aircraft_icao']}\n"
    # message += f"Airline: {flight_data['airline_name']} ({flight_data['airline']})\n"
    message += f"Route: {flight_data['origin_name']} → "
    message += f"{flight_data['destination_name']} \n"
    # message += f"Scheduled Time: {flight_data['scheduled_time']}\n"
    message += f"Terminal: {flight_data['terminal']}\n"
    if flight_data['diverted'] not in [None, False, 'null']:
        message += "\n⚠️ This flight has been diverted"
    
    
    message += "\n\n"

    social_shill_1 = "Consulta nuestras redes en"
    social_shill_2 = "https://linktr.ee/ctrl_plataforma"
    print(f"Message: {len(message)}")
    if len(message) + len(social_shill_1) + len(social_shill_2) < max_size:
        message += social_shill_1 + " " + social_shill_2
    elif len(message) + len(social_shill_2) < max_size:
        message += social_shill_2
    else:
        message += "\n See Bio"

    if len(message) > max_size:
        message = message[:275] + "..."
    print(f"Message: {len(message)}")
    print(message)
    return message

async def _upload_image(client: Client, image_path: str) -> Optional[str]:
    """Handles image uploading and returns media ID."""
    if not os.path.exists(image_path):
        logger.error(f"Image file not found at specified path: {image_path}")
        raise FileNotFoundError(f"Image file not found: {image_path}")

    logger.info(f"Uploading media from {image_path}...")
    try:
        # wait_for_completion=True is good practice for media uploads, especially larger files/videos
        # media_category might be needed for specific types like GIFs ('tweet_gif')
        media_id = await client.upload_media(image_path, wait_for_completion=True)
        logger.info(f"Media uploaded successfully. Media ID: {media_id}")
        return media_id
    except InvalidMedia as e_inv_media:
        logger.error(f"Invalid media error during upload of {image_path}: {e_inv_media}")
        raise
    except TwitterException as e_twitter_up:
        logger.error(f"Twitter API error during media upload of {image_path}: {e_twitter_up}")
        raise
    except Exception as e_up_unexpected:
        logger.error(f"Unexpected error during media upload of {image_path}: {e_up_unexpected}")
        raise


# --- Main Handler ---

async def create_tweet(flight_data: Dict[str, Any], image_path_override: Optional[str] = None, interesting_reasons: Optional[List[str]] = None, config: Dict[str, Any] = None) -> Optional[str]:
    """
    Creates a tweet using Twikit with enhanced error handling, logging,
    cookie management, and placeholder integration for image finding and text formatting.

    Args:
        flight_data (Dict[str, Any]): Data about the flight to include in the tweet.
                                      Must be a non-empty dictionary.
        image_path_override (Optional[str]): Path to an image to attach. If None,
                                             `utils.image_finder` will be attempted.
        config (Dict[str, Any]): The configuration dictionary.

    Returns:
        Optional[str]: The ID of the created tweet if successful, otherwise None.

    Raises:
        ValueError: If flight_data is missing/invalid or required environment variables are not set.
        FileNotFoundError: If a specified image file (either override or found) does not exist.
        TwitterException: For various Twitter API errors (e.g., DuplicateTweet, AccountLocked).
        Exception: For other unexpected errors during the process.
    """
    if not flight_data or not isinstance(flight_data, dict):
        msg = "Flight data must be a non-empty dictionary."
        logger.error(msg)
        raise ValueError(msg)

    if config is None:
        logger.error("Configuration (config) must be provided to create_tweet.")
        raise ValueError("Configuration is missing.")

    logger.info("Starting tweet creation process...")
    # Create the tweet text
    tweet_text = generate_flight_message_twitter(flight_data, interesting_reasons, config)


    client = None # Initialize to None for robust error handling in finally block (if needed)

    try:
        client = await _initialize_and_login_client()

        # Determine image path
        actual_image_path = image_path_override
        if not actual_image_path:
            logger.info("No image_path_override provided. Attempting to use image_finder.")
            try:
                # Placeholder: Attempt to use a dedicated image finding function
                if hasattr(image_finder, 'find_image_for_flight') and callable(image_finder.find_image_for_flight):
                    # This is where you'd call your actual image finder function:
                    # actual_image_path = await image_finder.find_image_for_flight(flight_data) # if async
                    # actual_image_path = image_finder.find_image_for_flight(flight_data) # if sync
                    pass # Replace with actual call logic
                    if actual_image_path:
                        logger.info(f"Image found by image_finder: {actual_image_path}")
                    else:
                        logger.info("image_finder did not return an image path.")
                else:
                    logger.info("utils.image_finder.find_image_for_flight not available.")
            except Exception as e_img_find:
                logger.warning(f"Error calling image_finder: {e_img_find}. Proceeding without image from finder.")
                actual_image_path = None # Ensure it's None if finder fails

        # Upload media if an image path is determined and valid
        media_ids: List[str] = []
        if actual_image_path:
            media_id = await _upload_image(client, actual_image_path)
            if media_id:
                media_ids.append(media_id)
        
        logger.info(f"Creating tweet with text: \"{tweet_text}\"")
        if media_ids:
            logger.info(f"Attaching media IDs: {media_ids}")

        # Create the tweet using twikit's built-in function
        created_tweet_obj = await client.create_tweet(
            text=tweet_text,
            media_ids=media_ids if media_ids else None # Pass None if list is empty, as per docs
        )
        
        tweet_url = f"https://twitter.com/{created_tweet_obj.user.screen_name if created_tweet_obj.user else 'user'}/status/{created_tweet_obj.id}"
        logger.info(f"Tweet created successfully! ID: {created_tweet_obj.id}, URL: {tweet_url}")
        return created_tweet_obj.id

    except ValueError as e_val: # From _get_env_var or initial flight_data check
        logger.error(f"Input validation or configuration error: {e_val}")
        raise
    except FileNotFoundError as e_fnf: # From _upload_image
        logger.error(f"File not found error: {e_fnf}")
        raise
    except (DuplicateTweet, InvalidMedia, AccountLocked, Unauthorized, Forbidden, NotFound, CouldNotTweet) as e_twitter_specific:
        logger.error(f"A specific Twitter API error occurred: {e_twitter_specific}")
        raise
    except TwitterException as e_twitter_general: # Catch-all for other Twikit errors
        logger.error(f"A general Twitter API error occurred: {e_twitter_general}")
        raise
    except Exception as e_unexpected:
        logger.error(f"An unexpected error occurred in create_tweet: {e_unexpected}", exc_info=True)
        raise
    # No explicit return None here, as exceptions should cover failure paths.
    # If execution reaches here without an exception but no tweet_id, it's an anomaly.

# --- Example Usage ---

async def main_example() -> None:
    """
    Main function to demonstrate the usage of `create_tweet`.
    This requires environment variables (TWITTER_USER, TWITTER_PASSWORD, optionally TWITTER_EMAIL)
    to be set.
    """
    logger.info("--- Starting Twikit create_tweet Demo ---")
    
    # Example flight data (more comprehensive)
    flight_data_example = {
        'flight_name_iata': 'LH990',
        'flight_name': 'Lufthansa Frankfurt-Berlin',
        'registration': 'D-AINX',
        'aircraft_name': 'Airbus A320neo',
        'aircraft_icao': 'A20N',
        'airline_name': 'Lufthansa',
        'airline': 'LH', # Often used for hashtags
        'origin_name': 'Frankfurt (FRA)',
        'origin_icao': 'EDDF',
        'destination_name': 'Berlin (BER)',
        'destination_icao': 'EDDB',
        'scheduled_time': '2024-07-16 10:00 CEST',
        'status': 'On Time',
        'terminal': 'A26',
        'diverted': False
    }
        
    interesting_reasons = {
        "MODEL": True,  # Interesting aircraft model
        "REGISTRATION": True,  # Interesting registration
        "FIRST_SEEN": True,  # First time seeing this flight
        "DIVERTED": False  # Not diverted
    }
    
    # Example image path (optional). 
    # Replace with an actual path to a JPG or PNG file for testing image uploads.
    # If None, it will try the image_finder placeholder or post without an image.
    image_path_example: Optional[str] = None
    # image_path_example = "path/to/your/sample_image.jpg" 

    # For testing, create a dummy image if no real one is provided
    use_dummy_image = False # Set to True to generate and use a dummy image
    dummy_image_filename = "socials/image.jpg"

    if use_dummy_image and not image_path_example:
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (800, 450), color = (29, 161, 242)) # Twitter blue-ish
            draw = ImageDraw.Draw(img)
            draw.text((50, 50), f"Test Flight: {flight_data_example['flight_name_iata']}\n{flight_data_example['origin_name']} -> {flight_data_example['destination_name']}", fill=(255,255,255), font_size=30)
            img.save(dummy_image_filename)
            image_path_example = dummy_image_filename
            logger.info(f"Created dummy image for testing: {dummy_image_filename}")
        except ImportError:
            logger.warning("Pillow library not installed (pip install Pillow). Cannot create dummy image.")
        except Exception as e_pil:
            logger.warning(f"Failed to create dummy image: {e_pil}")

    try:
        # Load a dummy config for testing purposes in the __main__ block
        test_config = config_manager.load_config()
        tweet_id = await create_tweet(flight_data_example, image_path_example, interesting_reasons, test_config)
        if tweet_id:
            logger.info(f"Demo tweet successfully posted. Tweet ID: {tweet_id}")
        else:
            # This case should ideally not be reached if error handling is comprehensive
            logger.warning("Demo tweet creation finished, but no tweet ID was returned. Check logs for errors.")
    except Exception as e:
        # Errors are logged within create_tweet, this is a final catch for the demo
        logger.error(f"Error during main_example execution: {e}")
    finally:
        if use_dummy_image and image_path_example == dummy_image_filename and os.path.exists(dummy_image_filename):
            try:
                os.remove(dummy_image_filename)
                logger.info(f"Cleaned up dummy image: {dummy_image_filename}")
            except Exception as e_clean:
                logger.warning(f"Could not remove dummy image {dummy_image_filename}: {e_clean}")
        logger.info("--- Twikit create_tweet Demo Finished ---")

if __name__ == "__main__":
    # Basic logging configuration if not already set up by logger_config
    # This helps if running the script standalone for testing.
    import logging
    if not logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        logger.info("Basic logging configured for standalone script execution.")
    
    # Load .env file if you are using one for environment variables
    # from dotenv import load_dotenv
    # load_dotenv()
    # logger.info("Attempted to load .env file (if python-dotenv is used).")

    asyncio.run(main_example())
