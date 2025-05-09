import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from loguru import logger
from telegram.ext import ApplicationBuilder
import telegram.error
import asyncio
from datetime import datetime, timedelta
from utils.image_finder import get_first_image_url_jp, get_first_image_url_pp
import os
# Removed dotenv import as we will rely on environment variables passed to the container
# from dotenv import load_dotenv
from log.logger_config import logger
import random


# Initialize Telegram application with longer timeout
# Relying on TELEGRAM_BOT_TOKEN being set as an environment variable
application = ApplicationBuilder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

def generate_flight_message(flight_data, interesting_reasons):
    """Generate a formatted message from flight data"""
    introducciones = [
    "📡 ¡Atentos spotters! Hoy Barajas trae sorpresas:",
    "✈️ Algo curioso se ha dejado ver por Barajas hoy:",
    "📸 Spotters, sacad las cámaras que esto merece foto:",
    "🚨 ¡Ojo al cielo! Tenemos visitas interesantes en Barajas:",
    "🤯 Barajas nos regala joyitas hoy, atentos:",
    "👁️ ¡Spotting del bueno hoy en Barajas!",
    "🗞️ Noticias frescas desde las pistas de Barajas:",
    "🛬 Barajas recibe vuelos interesantes hoy:",
    "🌤️ El cielo de Madrid viene cargado de cosas interesantes hoy:",
    "📷 ¡Preparad teleobjetivo que hay material jugoso!",
    "📍 Desde las pistas de Barajas… ¡mirad esto!",
    "💥 Barajas está on fire con lo que ha llegado hoy:",
    "⏱️ Un momento interesante para los spotters en Barajas:",
    "🔔 Atención torre: tráfico especial entrando en escena."
]

    message = ""
    # #                interesting_reasons = {
    #                 "MODEL": interesting_model,
    #                 "REGISTRATION": interesting_registration,
    #                 "FIRST_SEEN": first_seen,
    #                 "DIVERTED": False if flight_data.get("diverted", "null") == "null" else flight_data["diverted"],
    #                 "REASON": reason
    #             }

    if interesting_reasons:
        message = random.choice(introducciones) + "\n"

        if interesting_reasons.get("MODEL", False):
            message += f"- Se deja ver un {flight_data['aircraft_name'] if flight_data['aircraft_name'] else flight_data['aircraft_icao']} de {flight_data['airline_name'] if flight_data['airline_name'] not in [None, 'null'] else flight_data['airline']} que siempre da gusto ver.\n"
            
        if interesting_reasons.get("REGISTRATION", False):
            message += f"- Es un avion interesante porque {interesting_reasons.get('REASON')}.\n"
            
        if interesting_reasons.get("FIRST_SEEN", False):
            message += f"- Es la primera vez que vemos este avión de {flight_data['airline_name'] if flight_data['airline_name'] not in [None, 'null'] else flight_data['airline']} en Barajas con matrícula {flight_data['registration']}.\n"
            
        if interesting_reasons.get("DIVERTED", False):
            message += "- Este vuelo ha llegado aquí por desvío inesperado. 🧭\n\n"

    message += f"\n\nFlight: {flight_data['flight_name_iata']}{'/' + flight_data['flight_name'] if flight_data['flight_name'] not in [None, 'null'] else ''}\n"
    message += f"Registration: {flight_data['registration'] if flight_data['registration'] not in [None, 'null'] else 'Unkown'}\n"
    message += f"Aircraft: {flight_data['aircraft_name'] if flight_data['aircraft_name'] else flight_data['aircraft_icao']}\n"
    message += f"Airline: {flight_data['airline_name']} ({flight_data['airline']})\n"
    message += f"Route: {flight_data['origin_name']} ({flight_data['origin_icao']}) → "
    message += f"{flight_data['destination_name']} ({flight_data['destination_icao']})\n"
    message += f"Scheduled Time: {flight_data['scheduled_time']}\n"
    message += f"Terminal: {flight_data['terminal']}\n"
    if flight_data['diverted'] not in [None, False, 'null']:
        message += "\n⚠️ This flight has been diverted"
    
    flight_name = flight_data['flight_name'] if flight_data['flight_name'] not in [None, 'null'] else flight_data['flight_name_iata']
    message += f"https://www.flightradar24.com/data/flights/{flight_name.replace(' ','')}"
    message += "\n\n"
    message += "Consulta nuestras redes en https://linktr.ee/ctrl_plataforma"
    return message

async def send_flight_update(chat_id, flight_data, image_path=None, interesting_reasons=None):
    """Send flight update to specified chat with retry logic"""
    message = generate_flight_message(flight_data, interesting_reasons)
    retries = 3
    flight_name = flight_data['flight_name_iata'] if flight_data['flight_name_iata'] not in [None, 'null'] else flight_data['flight_name']
    for attempt in range(retries):
        try:
            # image path is a local image path
            if image_path and flight_data['registration']:
                # Send message with photo
                with open(image_path, 'rb') as photo_file:
                    await application.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_file,
                        caption=message,
                        reply_markup={
                            'inline_keyboard': [[{
                                'text': 'Flightradar',
                                'url': f"https://www.flightradar24.com/data/flights/{flight_name.replace(' ','')}"
                            }]]
                        }
                    )
            else:
                # Send message without photo if no image found
                logger.warning(f"No valid image file found at {image_path}, sending text only")
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    disable_web_page_preview=True,
                    reply_markup={
                        'inline_keyboard': [[{
                            'text': 'Flightradar',
                            'url': f"https://www.flightradar24.com/data/flights/{flight_name.replace(' ','')}"
                        }]]
                    }
                )
            logger.success(f"Successfully sent Telegram message for flight {flight_name.replace(' ','')}")
            return
        except telegram.error.TimedOut:
            if attempt < retries - 1:  # Don't wait on the last attempt
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Timeout occurred. Retrying in {wait_time} seconds... (Attempt {attempt + 1}/{retries})")
                await asyncio.sleep(wait_time)
                continue
            raise  # Re-raise the exception if all retries fail
        except telegram.error.RetryAfter as e:
            logger.warning(f"Rate limit hit. Retrying in {e.retry_after} seconds...")
            await asyncio.sleep(e.retry_after)
            continue
        except Exception as e:
            logger.error(f"Failed to send Telegram message for flight {flight_data['flight_name']}: {e}")
            raise

async def schedule_telegram(flight_data, image_path=None):
    """Send a Telegram message with flight data to the channel"""
    chat_id = '-1002116996158'  # Telegram channel ID
    flight_name = flight_data['flight_name_iata'] if flight_data['flight_name_iata'] not in [None, 'null'] else flight_data['flight_name']
    logger.info(f"Scheduling Telegram message for flight {flight_name}")
    
    async def send_message_task():
        try:
            # Parse scheduled time and calculate send time (2 hours before)
            scheduled_time = datetime.strptime(flight_data['scheduled_time'], "%Y-%m-%d %H:%M")
            send_time = scheduled_time - timedelta(hours=2)
            
            # Calculate delay in seconds
            now = datetime.now()
            delay = (send_time - now).total_seconds()
            
            # If the time has already passed, send immediately
            if delay < 0:
                logger.warning(f"Scheduled time for flight {flight_name} is in the past, sending immediately")
                delay = 0
            else:
                logger.debug(f"Message for flight {flight_name} will be sent in {delay} seconds")
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    logger.warning(f"Task for flight {flight_name} was cancelled, sending immediately")
            
            
            await send_flight_update(chat_id, flight_data, image_path)
        except Exception as e:
            logger.error(f"Failed to send Telegram message for flight {flight_name}: {e}")
            logger.exception(f"Exception details:{e}")
    
    # Create a background task that won't block the main execution
    task = asyncio.create_task(send_message_task())
    return task  # Return the task so it can be awaited if needed

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
    
    # Send test message
    import asyncio
    asyncio.run(send_flight_update(chat_id='-1002116996158', flight_data=dummy_data))
    logger.info("Sent test Telegram message with dummy data")
