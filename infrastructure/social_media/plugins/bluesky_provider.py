import os
from typing import Dict, Any
from datetime import datetime
from loguru import logger
from atproto import Client, models
from PIL import Image, UnidentifiedImageError
from core.interfaces import SocialProvider
from core.models import ProcessedFlight

MAX_IMAGE_SIZE_BYTES = 1000000  # 1MB
TEMP_IMAGE_SUFFIX = "_compressed"
BLUESKY_PDS_URL = "https://bsky.social"

class BlueskyProvider(SocialProvider):
    def _compress_image(self, image_path, max_size_bytes=MAX_IMAGE_SIZE_BYTES):
        """Compress an image to fit within max_size_bytes."""
        if not os.path.exists(image_path):
            return None

        try:
            with Image.open(image_path) as img:
                if os.path.getsize(image_path) <= max_size_bytes:
                    return image_path

                base_path, ext = os.path.splitext(image_path)
                temp_path = f"{base_path}{TEMP_IMAGE_SUFFIX}.jpg"

                width, height = img.size
                if max(width, height) > 1080:
                    scale = 1080 / max(width, height)
                    new_width = int(width * scale)
                    new_height = int(height * scale)
                    img = img.resize((new_width, new_height), Image.LANCZOS)

                img.save(temp_path, "JPEG", quality=85, optimize=True)

                if os.path.getsize(temp_path) <= max_size_bytes:
                    return temp_path

                quality = 80
                while quality >= 50:
                    img.save(temp_path, "JPEG", quality=quality, optimize=True)
                    if os.path.getsize(temp_path) <= max_size_bytes:
                        return temp_path
                    quality -= 5

                return None
        except Exception as e:
            logger.error(f"Failed to compress image for Bluesky: {e}")
            return None

    def _generate_message(self, processed_flight: ProcessedFlight, config: Dict[str, Any], max_size=280):
        flight_data = processed_flight.flight
        scheduled_time = flight_data.scheduled_time
        time_alert = f"hoy día {scheduled_time.strftime('%d a las %H:%M')}"
        airline_text = flight_data.airline_name or flight_data.airline_icao

        airport_name = config['settings'].get('airport_name', 'Airport')
        airport_icao = config['settings'].get('airport', 'LEMD')
        
        move = 'llegada'
        if flight_data.origin == airport_icao:
            move = 'salida'

        flight_name = flight_data.flight_name_iata or flight_data.flight_id
        fr24_url = f"https://www.flightradar24.com/data/flights/{flight_name.replace(' ','')}"
        
        message = f"✈️ Track this flight\n\n"
        
        reasons_dict = {r.name: True for r in processed_flight.reasons}
        
        first_seen_part = f"Primera visita de {flight_data.registration}, " if "FIRST_SEEN" in reasons_dict else ""
        model_part = f"Un {flight_data.aircraft_type}. " if "MODEL" in reasons_dict else ""
        
        message += f"{first_seen_part}{model_part}{move.capitalize()} de {airline_text} {time_alert} en {airport_name}\n\n"
            
        if "REGISTRATION" in reasons_dict:
            # We don't have the specific reason text easily available in the enum list without details
            message += f"Interesante por su matrícula {flight_data.registration}.\n\n"
        if "DIVERTED" in reasons_dict:
            message += "Es un vuelo desviado. 🧭\n\n"

        message2 = f"""Flight: {flight_name}\n
                    Reg: {flight_data.registration}\n
                    Acft: {flight_data.aircraft_type or flight_data.aircraft_icao}\n
                    Route: {flight_data.origin} → {flight_data.destination}\n"""
        
        facets = [
            models.AppBskyRichtextFacet.Main(
                features=[models.AppBskyRichtextFacet.Link(uri=fr24_url)],
                index=models.AppBskyRichtextFacet.ByteSlice(
                    byteStart=0,
                    byteEnd=len("✈️ Track this flight".encode('utf-8'))
                )
            )
        ]

        social_shill = "Consulta nuestras redes: https://linktr.ee/ctrl_plataforma"
        if len(message) + len(social_shill) < max_size:
            message += f"\n\n{social_shill}"
        else:
            message += "\n\nSee Bio"

        if len(message) + len(message2) > max_size:
            message = message[:max_size-5] + "..."
        else:
            message += message2

        return message, facets

    async def post_flight(self, processed_flight: ProcessedFlight, config: Dict[str, Any]) -> bool:
        if not config['social_networks'].get('bluesky', False):
            return False

        handle = os.getenv('BLUESKY_HANDLE')
        password = os.getenv('BLUESKY_PASSWORD')
        if not handle or not password:
            logger.error("Bluesky credentials not configured.")
            return False

        try:
            client = Client(base_url=BLUESKY_PDS_URL)
            client.login(handle, password)

            image_path = None
            if processed_flight.flight.image_url and os.path.exists(processed_flight.flight.image_url):
                image_path = processed_flight.flight.image_url

            compressed_image_path = None
            if image_path:
                compressed_image_path = self._compress_image(image_path)
                if not compressed_image_path:
                    logger.warning("Bluesky image compression failed, posting without image")

            text, facets = self._generate_message(processed_flight, config)

            if compressed_image_path:
                with open(compressed_image_path, 'rb') as f:
                    img_data = f.read()
                upload = client.upload_blob(img_data)
                images = [models.AppBskyEmbedImages.Image(
                    alt=f"Flight {processed_flight.flight.flight_name_iata}",
                    image=upload.blob
                )]
                embed = models.AppBskyEmbedImages.Main(images=images)
                client.send_post(text=text, facets=facets, embed=embed)
                
                # Cleanup compressed image
                if compressed_image_path != image_path:
                    try:
                        os.remove(compressed_image_path)
                    except:
                        pass
            else:
                client.send_post(text=text, facets=facets)

            logger.success(f"Bluesky post sent for {processed_flight.flight.flight_name_iata}")
            return True

        except Exception as e:
            logger.error(f"Failed to post to Bluesky: {e}")
            return False
