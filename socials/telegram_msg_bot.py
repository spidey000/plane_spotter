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
from config import config_manager # Keep import for type hinting or if other functions need it


# Initialize Telegram application with longer timeout
# Relying on TELEGRAM_BOT_TOKEN being set as an environment variable
if 'SSL_CERT_FILE' in os.environ:
    try:
        # Intenta verificar si es un archivo válido, si no, elimínala
        # Esta es una verificación simple, podría ser más robusta
        if not os.path.isfile(os.environ['SSL_CERT_FILE']):
            logger.warning(f"SSL_CERT_FILE environment variable points to a non-existent file: {os.environ['SSL_CERT_FILE']}. Unsetting it.")
            del os.environ['SSL_CERT_FILE']
        # Podrías añadir más chequeos aquí si fuera necesario
    except Exception as e:
        logger.warning(f"Error checking SSL_CERT_FILE, unsetting it: {e}")
        del os.environ['SSL_CERT_FILE']

_application = None

def get_application():
    global _application
    if _application:
        return _application
    
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables.")
        return None
        
    try:
        _application = ApplicationBuilder().token(token).build()
        return _application
    except Exception as e:
        logger.error(f"Failed to initialize Telegram bot: {e}")
        return None

def generate_flight_message(flight_data, interesting_reasons, config):
    """Generate a formatted message from flight data"""
    scheduled_time = datetime.strptime(flight_data['scheduled_time'], "%Y-%m-%d %H:%M")
    time_alert = f"hoy día {scheduled_time.strftime('%d a las %H:%M')}"
    airline_text = f"{flight_data['airline_name'] if flight_data['airline_name'] not in [None, 'null'] else flight_data['airline']}"

    if flight_data['origin_name'] == config['settings']['airport_name']:
        move = 'salida'
    else:
        move = 'llegada'
        
    introducciones = [
    f"📡 ¡Atentos spotters! {config['settings']['airport_name']} trae sorpresas con un tráfico de {move} {time_alert} con {airline_text}",
    f"✈️ Algo curioso se ha dejado ver por {config['settings']['airport_name']}, {move} de {airline_text} {time_alert}",
    f"📸 Spotters, sacad las cámaras que esta {move} de {airline_text} merece foto {time_alert}",
    f"🚨 ¡Ojo al cielo! Tráfico de {move} de {airline_text} {time_alert} Tenemos visitas interesantes en {config['settings']['airport_name']}",
    f"🤯 {config['settings']['airport_name']} nos regala joyitas, Tráfico de {move} de {airline_text} {time_alert}, atentos",
    f"👁️ ¡Spotting del bueno en {config['settings']['airport_name']}! con esta {move} de {airline_text} {time_alert}",
    f"🗞️ Noticias frescas desde las pistas de {move} de {airline_text} {config['settings']['airport_name']} {time_alert}",
    f"🛬 {config['settings']['airport_name']} recibe un vuelo interesante de {move} de {airline_text} {time_alert}",
    f"🌤️ El cielo de {config['settings']['airport_name']} viene cargado de cosas interesantes, Tráfico de {move} de {airline_text} {time_alert}",
    f"📷 ¡Preparad teleobjetivo, hay material jugoso {time_alert} de {move} de {airline_text}!",
    f"📍 Desde las pistas de {config['settings']['airport_name']} podremos ver la {move} de {airline_text} {time_alert}… ¡mirad esto!",
    f"⏱️ Un momento interesante para los spotters en {config['settings']['airport_name']}. Tráfico de {move} de {airline_text} {time_alert}",
    f"🔔 Atención torre, Tráfico de {airline_text} de {move} {time_alert}: tráfico especial entrando en escena"
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
        message = random.choice(introducciones) + "\n\n"

        if interesting_reasons.get("MODEL", False):
            message += f"Se deja ver un {flight_data['aircraft_name'] if flight_data['aircraft_name'] else flight_data['aircraft_icao']} de {flight_data['airline_name'] if flight_data['airline_name'] not in [None, 'null'] else flight_data['airline']} que siempre da gusto ver.\n"
            
        if interesting_reasons.get("REGISTRATION", False):
            message += f"Es interesante porque {interesting_reasons.get('REASON')}.\n"
            
        if interesting_reasons.get("FIRST_SEEN", False):
            message += f"Es la primera vez que vemos este avión en {config['settings']['airport_name']} con matrícula {flight_data['registration'] if flight_data['registration'] not in [None, 'null'] else 'Unkown'}.\n"
            
        if interesting_reasons.get("DIVERTED", False):
            message += "Este vuelo ha llegado aquí por un desvío inesperado. 🧭\n\n"

    message += f"\n\nFlight: {flight_data['flight_name_iata']}{'/' + flight_data['flight_name'] if flight_data['flight_name'] not in [None, 'null'] else ''}\n"
    message += f"Callsign: {flight_data['callsign']} {flight_data['flight_name'][3:] if flight_data.get('flight_name') else ''}\n" if flight_data.get('callsign') not in [None, 'null'] else ''
    message += f"Registration: {flight_data['registration'] if flight_data['registration'] not in [None, 'null'] else 'Unkown'}\n"
    message += f"Aircraft: {flight_data['aircraft_name'] if flight_data['aircraft_name'] else flight_data['aircraft_icao']}\n"
    message += f"Airline: {flight_data['airline_name']} ({flight_data['airline']})\n"
    message += f"Route: {flight_data['origin_name']} ({flight_data['origin_icao']}) → "
    message += f"{flight_data['destination_name']} ({flight_data['destination_icao']})\n"
    message += f"Scheduled Time: {flight_data['scheduled_time']}\n"
    message += f"Terminal: {flight_data['terminal']}\n"
    if flight_data.get('diverted') and flight_data['diverted'] not in [None, False, 'null']:
        message += "\n⚠️ This flight has been diverted"
    
    flight_name = flight_data['flight_name_iata'] if flight_data['flight_name_iata'] not in [None, 'null'] else flight_data['flight_name']
    message += f"https://www.flightradar24.com/data/flights/{flight_name.replace(' ','')}"
    message += "\n\n"
    message += "Consulta nuestras redes en https://linktr.ee/ctrl_plataforma"
    return message

async def send_flight_update(chat_id, flight_data, image_path=None, interesting_reasons=None, config=None):
    """Send flight update to specified chat with retry logic"""
    if config is None:
        logger.error("Configuration (config) must be provided to send_flight_update.")
        raise ValueError("Configuration is missing.")

    message = generate_flight_message(flight_data, interesting_reasons, config)
    retries = 3
    flight_name = flight_data['flight_name_iata'] if flight_data['flight_name_iata'] not in [None, 'null'] else flight_data['flight_name']
    app = get_application()
    if not app:
        logger.warning("Telegram application not initialized, skipping message.")
        return

    for attempt in range(retries):
        try:
            # image path is a local image path
            if image_path:
                # Send message with photo
                with open(image_path, 'rb') as photo_file:
                    await app.bot.send_photo(
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
                await app.bot.send_message(
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
    # Load a dummy config for testing purposes in the __main__ block
    test_config = config_manager.load_config()
    print(test_config['telemetry']['chat_id'])
    print(os.getenv('TELEGRAM_BOT_TOKEN'))
    
    asyncio.run(send_flight_update(chat_id=test_config['telemetry']['chat_id'], flight_data=dummy_data, config=test_config))
    logger.info("Sent test Telegram message with dummy data")
