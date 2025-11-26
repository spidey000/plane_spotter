import os
import random
import asyncio
from typing import Dict, Any
from datetime import datetime
from loguru import logger
from telegram.ext import ApplicationBuilder
import telegram.error
from core.interfaces import SocialProvider
from core.models import ProcessedFlight

class TelegramProvider(SocialProvider):
    def __init__(self):
        self._application = None

    def _get_application(self):
        if self._application:
            return self._application
        
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not token:
            logger.error("TELEGRAM_BOT_TOKEN not found in environment variables.")
            return None
            
        try:
            self._application = ApplicationBuilder().token(token).build()
            return self._application
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            return None

    def _generate_message(self, processed_flight: ProcessedFlight, config: Dict[str, Any]) -> str:
        flight_data = processed_flight.flight.dict() # Assuming Pydantic model has dict() or we access fields directly
        # Actually Flight model fields are accessible directly.
        # But legacy code uses dict access. Let's adapt to object access or convert to dict.
        # Flight model is Pydantic, so .model_dump() or .dict() works.
        # Let's use object access for cleaner code, or convert to dict to reuse legacy logic easily.
        # Reusing legacy logic is safer for now to preserve message format.
        fd = {
            'flight_name_iata': processed_flight.flight.flight_name_iata,
            'flight_name': processed_flight.flight.flight_name_iata, # Fallback
            'registration': processed_flight.flight.registration,
            'aircraft_name': processed_flight.flight.aircraft_type, # Mapping might be needed
            'aircraft_icao': processed_flight.flight.aircraft_icao,
            'airline_name': processed_flight.flight.airline_name,
            'airline': processed_flight.flight.airline_icao,
            'origin_name': processed_flight.flight.origin, # Simplified
            'origin_icao': processed_flight.flight.origin,
            'destination_name': processed_flight.flight.destination,
            'destination_icao': processed_flight.flight.destination,
            'scheduled_time': processed_flight.flight.scheduled_time.strftime("%Y-%m-%d %H:%M"),
            'terminal': "N/A", # Not in Flight model?
            'callsign': processed_flight.flight.flight_id, # Maybe?
            'diverted': False # Not in Flight model?
        }
        
        # Extract interesting reasons for legacy format
        reasons_dict = {}
        for r in processed_flight.reasons:
            reasons_dict[r.name] = True
            # if r.details: reasons_dict['REASON'] = r.details # If we had details in enum... we don't.
        
        # Legacy message generation logic
        airport_name = config['settings'].get('airport_name', 'Airport')
        
        scheduled_time = processed_flight.flight.scheduled_time
        time_alert = f"hoy día {scheduled_time.strftime('%d a las %H:%M')}"
        airline_text = fd['airline_name'] or fd['airline']

        move = 'llegada' # Default, logic was check origin == airport
        # We need airport_icao from config to check origin
        airport_icao = config['settings'].get('airport', 'LEMD')
        if fd['origin_icao'] == airport_icao:
            move = 'salida'

        introducciones = [
            f"📡 ¡Atentos spotters! {airport_name} trae sorpresas con un tráfico de {move} {time_alert} con {airline_text}",
            f"✈️ Algo curioso se ha dejado ver por {airport_name}, {move} de {airline_text} {time_alert}",
            f"📸 Spotters, sacad las cámaras que esta {move} de {airline_text} merece foto {time_alert}",
            f"🚨 ¡Ojo al cielo! Tráfico de {move} de {airline_text} {time_alert} Tenemos visitas interesantes en {airport_name}",
            f"🤯 {airport_name} nos regala joyitas, Tráfico de {move} de {airline_text} {time_alert}, atentos",
            f"👁️ ¡Spotting del bueno en {airport_name}! con esta {move} de {airline_text} {time_alert}",
            f"🗞️ Noticias frescas desde las pistas de {move} de {airline_text} {airport_name} {time_alert}",
            f"🛬 {airport_name} recibe un vuelo interesante de {move} de {airline_text} {time_alert}",
            f"🌤️ El cielo de {airport_name} viene cargado de cosas interesantes, Tráfico de {move} de {airline_text} {time_alert}",
            f"📷 ¡Preparad teleobjetivo, hay material jugoso {time_alert} de {move} de {airline_text}!",
            f"📍 Desde las pistas de {airport_name} podremos ver la {move} de {airline_text} {time_alert}… ¡mirad esto!",
            f"⏱️ Un momento interesante para los spotters en {airport_name}. Tráfico de {move} de {airline_text} {time_alert}",
            f"🔔 Atención torre, Tráfico de {airline_text} de {move} {time_alert}: tráfico especial entrando en escena"
        ]

        message = random.choice(introducciones) + "\n\n"

        if "MODEL" in reasons_dict:
            message += f"Se deja ver un {fd['aircraft_name'] or fd['aircraft_icao']} de {airline_text} que siempre da gusto ver.\n"
        if "REGISTRATION" in reasons_dict:
            message += f"Es interesante por su matrícula {fd['registration']}.\n"
        if "FIRST_SEEN" in reasons_dict:
            message += f"Es la primera vez que vemos este avión en {airport_name} con matrícula {fd['registration']}.\n"

        message += f"\n\nFlight: {fd['flight_name']}\n"
        message += f"Registration: {fd['registration']}\n"
        message += f"Aircraft: {fd['aircraft_name'] or fd['aircraft_icao']}\n"
        message += f"Airline: {airline_text}\n"
        message += f"Route: {fd['origin_name']} → {fd['destination_name']}\n"
        message += f"Scheduled Time: {fd['scheduled_time']}\n"
        
        flight_name_clean = fd['flight_name'].replace(' ', '')
        message += f"https://www.flightradar24.com/data/flights/{flight_name_clean}"
        message += "\n\n"
        message += "Consulta nuestras redes en https://linktr.ee/ctrl_plataforma"
        
        return message

    async def post_flight(self, processed_flight: ProcessedFlight, config: Dict[str, Any]) -> bool:
        if not config['social_networks'].get('telegram', False):
            return False

        chat_id = config['telemetry'].get('chat_id')
        if not chat_id:
            logger.error("Telegram chat_id not configured.")
            return False

        app = self._get_application()
        if not app:
            return False

        message = self._generate_message(processed_flight, config)
        image_path = processed_flight.flight.image_url # Assuming we store local path here for now, or we need to pass it differently.
        # Wait, Flight.image_url is usually a URL. 
        # The NotificationService will handle image fetching via ImageService and pass the LOCAL path?
        # The interface says `post_flight(self, processed_flight: ProcessedFlight, config: Dict[str, Any])`
        # Where does the local image path come from?
        # Option A: NotificationService fetches image, sets `processed_flight.flight.image_url` to local path (hacky).
        # Option B: Update interface to accept `image_path` (better).
        # Let's stick to the interface for now. If `image_url` is a local path, we use it.
        
        # Check if image_url is a local path
        local_image_path = None
        if processed_flight.flight.image_url and os.path.exists(processed_flight.flight.image_url):
            local_image_path = processed_flight.flight.image_url

        retries = 3
        flight_name = processed_flight.flight.flight_name_iata.replace(' ', '')

        for attempt in range(retries):
            try:
                if local_image_path:
                    with open(local_image_path, 'rb') as photo_file:
                        await app.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo_file,
                            caption=message,
                            reply_markup={
                                'inline_keyboard': [[{
                                    'text': 'Flightradar',
                                    'url': f"https://www.flightradar24.com/data/flights/{flight_name}"
                                }]]
                            }
                        )
                else:
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        disable_web_page_preview=True,
                        reply_markup={
                            'inline_keyboard': [[{
                                'text': 'Flightradar',
                                'url': f"https://www.flightradar24.com/data/flights/{flight_name}"
                            }]]
                        }
                    )
                logger.success(f"Telegram sent for {flight_name}")
                return True
            except telegram.error.TimedOut:
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.error("Telegram timeout")
            except Exception as e:
                logger.error(f"Telegram failed: {e}")
                return False
        return False
