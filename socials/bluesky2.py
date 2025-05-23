import unittest
from unittest.mock import patch, MagicMock, mock_open, ANY
import os
import argparse
from PIL import Image, UnidentifiedImageError
import io
from pathlib import Path
import sys
from datetime import datetime
from atproto import Client, models
# Project-specific imports (assuming they exist in your project structure)
try:
    from log.logger_config import logger
except ImportError:
    print("No logger found")

from config import config_manager
config = config_manager.load_config()

# Constants
MAX_IMAGE_SIZE_BYTES = 1000000  # 1MB
TEMP_IMAGE_SUFFIX = "_compressed"
BLUESKY_PDS_URL = "https://bsky.social"

# Dummy flight data for tests
FLIGHT_DATA_SAMPLE = {
    'flight_name_iata': 'AA100', 'flight_name': 'AA100', 'registration': 'N123AA',
    'aircraft_name': 'Boeing 737', 'aircraft_icao': 'B738',
    'airline_name': 'American Airlines', 'airline': 'AA',
    'origin_name': 'New York JFK', 'origin_icao': 'KJFK',
    'destination_name': 'Los Angeles LAX', 'destination_icao': 'KLAX',
    'scheduled_time': '2023-01-01 10:00', 'terminal': '8', 'diverted': False
}

class BlueskyPostError(Exception):
    pass

class ImageProcessingError(Exception):
    pass

def generate_flight_message_bluesky(flight_data, interesting_reasons, max_size=280):
    """Generate a formatted message with rich text for Bluesky"""
    scheduled_time = datetime.strptime(flight_data['scheduled_time'], "%Y-%m-%d %H:%M")
    time_alert = f"hoy día {scheduled_time.strftime('%d a las %H:%M')}"
    airline_text = f"{flight_data['airline_name'] if flight_data['airline_name'] not in [None, 'null'] else flight_data['airline']}"

    if flight_data['origin_name'] == config['settings']['airport_name']:
        move = 'salida'
    else:
        move = 'llegada'

    flight_name = flight_data['flight_name_iata'] if flight_data['flight_name_iata'] not in [None, 'null'] else flight_data['flight_name']
    fr24_url = f"https://www.flightradar24.com/data/flights/{flight_name.replace(' ','')}"
    
    # Base message construction (same as original)
    message = f"✈️ Track this flight\n\n"  # This will be our clickable text
    
    first_seen_part = f"Primera visita de {flight_data['registration'] if flight_data['registration'] not in [None, 'null'] else 'Unkown'}, " if interesting_reasons.get("FIRST_SEEN", False) else ""
    model_part = f"Un {flight_data['aircraft_name']}"#deploy if flight_data['aircraft_name'] else flight_data['aircraft_icao']}. " if interesting_reasons.get("MODEL", False) else ""
    message += f"{first_seen_part}{model_part}{move.capitalize()} de {airline_text} {time_alert} en {config['settings']['airport_name']}\n\n"
        
    if interesting_reasons.get("REGISTRATION", False):
        message += f"Interesante porque {interesting_reasons.get('REASON')}.\n\n"
    if interesting_reasons.get("DIVERTED", False):
        message += "Es un vuelo desviado. 🧭\n\n"

    message2 = f"""Flight: {flight_data['flight_name_iata']}{'/' + flight_data['flight_name'] if flight_data['flight_name'] not in [None, 'null'] else ''}\n
                    Callsign: {flight_data['callsign']} {flight_data['flight_name'][3:] if flight_data.get('flight_name') else ''}\n
                    Reg: {flight_data['registration'] if flight_data['registration'] not in [None, 'null'] else 'Unkown'}\n
                    Acft: {flight_data['aircraft_name'] if flight_data['aircraft_name'] else flight_data['aircraft_icao']}\n
                    Route: {flight_data['origin_name']} → {flight_data['destination_name']}\n
                    Terminal: {flight_data['terminal']}\n"""
    
    if flight_data['diverted'] not in [None, False, 'null']:
        message += "\n⚠️ This flight has been diverted"

    # Create rich text facets for the Flightradar24 link
    facets = [
        models.AppBskyRichtextFacet.Main(
            features=[models.AppBskyRichtextFacet.Link(uri=fr24_url)],
            index=models.AppBskyRichtextFacet.ByteSlice(
                byteStart=0,  # "✈️ Track this flight" starts at beginning
                byteEnd=len("✈️ Track this flight".encode('utf-8'))
            )
        )
    ]

    # Handle social links (same as original)
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

def _compress_image(image_path, max_size_bytes=MAX_IMAGE_SIZE_BYTES):
    """Compress an image to fit within max_size_bytes (1MB by default).
    
    Args:
        image_path (str): Path to the input image.
        max_size_bytes (int): Target max size in bytes (default: 1MB).
    
    Returns:
        str: Path to the compressed image, or None if compression fails.
    
    Raises:
        ImageProcessingError: If the image is invalid or cannot be compressed.
    """
    if not os.path.exists(image_path):
        raise ImageProcessingError("Image file not found")

    try:
        with Image.open(image_path) as img:
            # Check if the image is already small enough
            if os.path.getsize(image_path) <= max_size_bytes:
                return image_path

            # Create a temporary path for the compressed image
            base_path, ext = os.path.splitext(image_path)
            temp_path = f"{base_path}{TEMP_IMAGE_SUFFIX}.jpg"  # Force JPEG output

            # Resize to 1080px on the longest side (preserve aspect ratio)
            width, height = img.size
            if max(width, height) > 1080:
                scale = 1080 / max(width, height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                img = img.resize((new_width, new_height), Image.LANCZOS)

            # Save the resized image with default quality (85)
            img.save(temp_path, "JPEG", quality=85, optimize=True)

            # Check if the resized image meets the size requirement
            if os.path.getsize(temp_path) <= max_size_bytes:
                return temp_path

            # If still too large, reduce quality incrementally
            quality = 80  # Start from 80 (since 85 was already tried)
            while quality >= 50:
                img.save(temp_path, "JPEG", quality=quality, optimize=True)
                if os.path.getsize(temp_path) <= max_size_bytes:
                    return temp_path
                quality -= 5  # Reduce quality in steps of 5

            # If all attempts fail, return None
            return None

    except UnidentifiedImageError as e:
        raise ImageProcessingError(f"Cannot identify image file: {e}")
    except Exception as e:
        raise ImageProcessingError(f"Failed to compress image: {e}")



# def generate_flight_message(flight_data, image_path=None):
#     """Generate a message for the flight post."""
#     return f"Flight {flight_data['flight_name']} from {flight_data['origin_name']} to {flight_data['destination_name']}"

def post_flight_to_bluesky(flight_data, image_path, interesting_reasons):
    """Post flight data to Bluesky with proper formatting"""
    if image_path and not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    # Validate environment variables
    handle = os.getenv('BLUESKY_HANDLE')
    password = os.getenv('BLUESKY_PASSWORD')
    if not handle or not password:
        raise BlueskyPostError("Bluesky credentials (handle/password) not configured.")

    # Initialize client
    client = Client(base_url=BLUESKY_PDS_URL)
    try:
        # Login
        client.login(handle, password)

        # Compress image if provided
        compressed_image_path = None
        if image_path:
            compressed_image_path = _compress_image(image_path)
            if not compressed_image_path:
                print("Image compression failed, posting without image")

        # Generate message and facets
        text, facets = generate_flight_message_bluesky(flight_data, interesting_reasons)

        # Create post (with or without image)
        if compressed_image_path:
            with open(compressed_image_path, 'rb') as f:
                img_data = f.read()
            upload = client.upload_blob(img_data)
            images = [models.AppBskyEmbedImages.Image(
                alt=f"Flight {flight_data['flight_name']}",
                image=upload.blob
            )]
            embed = models.AppBskyEmbedImages.Main(images=images)
            response = client.send_post(text=text, facets=facets, embed=embed)
        else:
            response = client.send_post(text=text, facets=facets)

        return {"uri": response.uri, "cid": response.cid}

    except Exception as e:
        raise BlueskyPostError(f"Failed to post to Bluesky: {e}")


class TestBlueskyImageCompression(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("test_temp_files_compression")
        self.test_dir.mkdir(exist_ok=True)
        self.test_image_path = str(self.test_dir / "test_image.jpg")
        self.compressed_image_path = str(self.test_dir / f"test_image{TEMP_IMAGE_SUFFIX}")
        
        # Create a small dummy image file
        img = Image.new('RGB', (60, 30), color='red')
        img.save(self.test_image_path, "JPEG")

    def tearDown(self):
        for item in self.test_dir.iterdir():
            item.unlink()
        self.test_dir.rmdir()

    @patch('os.path.getsize')
    @patch('PIL.Image.open') # To prevent actual file read if getsize says it's small
    def test_compress_image_already_small(self, mock_pil_image_open, mock_os_getsize):
        mock_os_getsize.return_value = MAX_IMAGE_SIZE_BYTES - 100
        
        result_path = _compress_image(self.test_image_path)
        
        self.assertEqual(result_path, self.test_image_path)
        mock_pil_image_open.assert_not_called() # Should not open if already small

    @patch('os.path.getsize')
    @patch('PIL.Image.open')
    def test_compress_image_resize_only(self, mock_img_open, mock_getsize):
        # Simulate a resized image that meets the size requirement
        mock_getsize.side_effect = [5_000_000, 900_000]  # Original → Resized
        mock_img = MagicMock()
        mock_img.size = (4000, 3000)
        mock_img_open.return_value.__enter__.return_value = mock_img

        result = _compress_image("large_image.jpg")
        self.assertIsNotNone(result)
        self.assertTrue(result.endswith(TEMP_IMAGE_SUFFIX + ".jpg"))

    @patch('os.path.getsize')
    @patch('PIL.Image.open')
    def test_compress_image_resize_and_quality(self, mock_img_open, mock_getsize):
        # Simulate a resized image that needs quality reduction
        mock_getsize.side_effect = [5_000_000, 1_800_000, 1_300_000, 900_000]  # Original → Resized → Quality steps
        mock_img = MagicMock()
        mock_img.size = (4000, 3000)
        mock_img_open.return_value.__enter__.return_value = mock_img

        result = _compress_image("large_image.jpg")
        self.assertIsNotNone(result)
        self.assertTrue(result.endswith(TEMP_IMAGE_SUFFIX + ".jpg"))

    @patch('os.path.getsize')
    @patch('PIL.Image.open')
    def test_compress_image_fails_to_compress_small_enough(self, mock_pil_image_open, mock_os_getsize):
        mock_os_getsize.return_value = MAX_IMAGE_SIZE_BYTES + 100 # Initial size check
        
        mock_img_instance = MagicMock(spec=Image.Image)
        mock_img_instance.format = 'JPEG'
        mock_img_instance.mode = 'RGB'
        mock_img_instance.width = 5000
        mock_img_instance.height = 5000
        mock_img_instance.copy.return_value = mock_img_instance
        mock_pil_image_open.return_value.__enter__.return_value = mock_img_instance

        mock_byte_io_instance = MagicMock(spec=io.BytesIO)
        # All attempts result in size > MAX_IMAGE_SIZE_BYTES
        mock_byte_io_instance.tell.return_value = MAX_IMAGE_SIZE_BYTES + 10 
        
        with patch('io.BytesIO', return_value=mock_byte_io_instance):
            result_path = _compress_image(self.test_image_path)

        self.assertIsNone(result_path)

    def test_compress_image_source_file_not_found(self):
        # Test _compress_image's internal FileNotFoundError handling
        with self.assertRaises(ImageProcessingError) as context: # It re-raises as ImageProcessingError
            _compress_image("non_existent_file.jpg")
        self.assertIn("Image file not found", str(context.exception))

    @patch('os.path.getsize', return_value=MAX_IMAGE_SIZE_BYTES + 100) # Needs compression
    @patch('PIL.Image.open', side_effect=UnidentifiedImageError("bad image"))
    def test_compress_image_unidentified_image_error(self, mock_pil_image_open, mock_os_getsize):
        with self.assertRaises(ImageProcessingError) as context:
            _compress_image(self.test_image_path)
        self.assertIn("Cannot identify image file", str(context.exception))
        mock_pil_image_open.assert_called_once_with(self.test_image_path)


class TestPostFlightToBluesky(unittest.TestCase):

    def setUp(self):
        self.flight_data = FLIGHT_DATA_SAMPLE.copy()
        
        self.test_dir = Path("test_temp_files_post")
        self.test_dir.mkdir(exist_ok=True)
        self.test_image_path = str(self.test_dir / "test_post_image.jpg")
        self.compressed_image_path = str(self.test_dir / f"test_post_image{TEMP_IMAGE_SUFFIX}")

        img = Image.new('RGB', (50,50), color='blue')
        img.save(self.test_image_path, "JPEG")

        self.env_patcher = patch.dict(os.environ, {'BLUESKY_HANDLE': 'testhandle', 'BLUESKY_PASSWORD': 'testpass'})
        self.env_patcher.start()
        
    def tearDown(self):
        self.env_patcher.stop()
        for item in self.test_dir.iterdir():
            item.unlink()
        self.test_dir.rmdir()

    @patch('bluesky_poster.create_post_on_bluesky')
    @patch('bluesky_poster._compress_image')
    @patch('bluesky_poster.generate_flight_message') # Mocking this for simplicity
    def test_post_with_image_no_compression_needed(
        self, mock_generate_message, mock_compress_image, mock_create_post
    ):
        mock_generate_message.return_value = "Test message"
        mock_compress_image.return_value = self.test_image_path # Simulates image is small or already compressed
        mock_create_post.return_value = {"uri": "some_uri", "cid": "some_cid"}

        result = post_flight_to_bluesky(self.flight_data, image_path=self.test_image_path)

        mock_generate_message.assert_called_once_with(self.flight_data, None)
        mock_compress_image.assert_called_once_with(self.test_image_path, MAX_IMAGE_SIZE_BYTES)
        mock_create_post.assert_called_once()
        args_sent = mock_create_post.call_args[0][0]
        self.assertEqual(args_sent.text, "Test message")
        self.assertEqual(args_sent.image, self.test_image_path)
        self.assertTrue(args_sent.alt_text.startswith("Image related to flight"))
        self.assertEqual(result, {"uri": "some_uri", "cid": "some_cid"})

    @patch('bluesky_poster.create_post_on_bluesky')
    @patch('bluesky_poster._compress_image')
    @patch('bluesky_poster.generate_flight_message')
    @patch('os.remove') # To check cleanup of temp compressed file
    def test_post_with_image_compression_successful_and_cleanup(
        self, mock_os_remove, mock_generate_message, mock_compress_image, mock_create_post
    ):
        mock_generate_message.return_value = "Test message"
        # Simulate _compress_image returning the path to a NEWLY compressed file
        mock_compress_image.return_value = self.compressed_image_path 
        mock_create_post.return_value = {"uri": "some_uri", "cid": "some_cid"}

        # Need to ensure the compressed file actually exists for os.remove to be called on it in finally
        with open(self.compressed_image_path, 'w') as f: f.write("dummy_data") # Create dummy compressed file

        result = post_flight_to_bluesky(self.flight_data, image_path=self.test_image_path)

        mock_compress_image.assert_called_once_with(self.test_image_path, MAX_IMAGE_SIZE_BYTES)
        mock_create_post.assert_called_once()
        args_sent = mock_create_post.call_args[0][0]
        self.assertEqual(args_sent.image, self.compressed_image_path)
        self.assertEqual(result, {"uri": "some_uri", "cid": "some_cid"})
        mock_os_remove.assert_called_once_with(self.compressed_image_path) # Check cleanup

    @patch('bluesky_poster.create_post_on_bluesky')
    @patch('bluesky_poster._compress_image', return_value=None) # Simulate compression failure
    @patch('bluesky_poster.generate_flight_message')
    def test_post_with_image_compression_failed_posts_without_image(
        self, mock_generate_message, mock_compress_image, mock_create_post
    ):
        mock_generate_message.return_value = "Test message"
        mock_create_post.return_value = {"uri": "some_uri", "cid": "some_cid"}

        post_flight_to_bluesky(self.flight_data, image_path=self.test_image_path)

        mock_create_post.assert_called_once()
        args_sent = mock_create_post.call_args[0][0]
        self.assertIsNone(args_sent.image) # Posted without image
        self.assertIsNone(args_sent.alt_text)

    @patch('bluesky_poster.create_post_on_bluesky')
    @patch('bluesky_poster.generate_flight_message')
    @patch('bluesky_poster._compress_image') # Ensure it's mocked so no real file ops
    def test_post_without_image_path(self, mock_compress_image, mock_generate_message, mock_create_post):
        mock_generate_message.return_value = "Test message"
        mock_create_post.return_value = {"uri": "some_uri", "cid": "some_cid"}

        post_flight_to_bluesky(self.flight_data, image_path=None)
        
        mock_compress_image.assert_not_called() # _compress_image should not be called if no image_path
        mock_create_post.assert_called_once()
        args_sent = mock_create_post.call_args[0][0]
        self.assertIsNone(args_sent.image)
        self.assertIsNone(args_sent.alt_text)

    def test_post_image_path_not_found_raises_file_not_found(self):
        # Test the initial os.path.exists check in post_flight_to_bluesky
        with self.assertRaises(FileNotFoundError):
            post_flight_to_bluesky(self.flight_data, image_path="non_existent.jpg")

    @patch('bluesky_poster.create_post_on_bluesky', side_effect=Exception("API Boom!"))
    @patch('bluesky_poster.generate_flight_message', return_value="Test")
    def test_post_api_failure_raises_bluesky_post_error(self, mock_generate_message, mock_create_post):
        with self.assertRaises(BlueskyPostError) as context:
            post_flight_to_bluesky(self.flight_data, image_path=None)
        self.assertIn("API Boom!", str(context.exception.args[0])) # Check original exception message is preserved

    def test_post_missing_credentials_raises_bluesky_post_error(self):
        with patch.dict(os.environ, {}, clear=True): # Temporarily unset env vars
            with self.assertRaises(BlueskyPostError) as context:
                post_flight_to_bluesky(self.flight_data, image_path=None)
            self.assertIn("credentials not configured", str(context.exception).lower())
            
    @patch('bluesky_poster.create_post_on_bluesky')
    @patch('bluesky_poster._compress_image', side_effect=ImageProcessingError("Image proc error"))
    @patch('bluesky_poster.generate_flight_message', return_value="Test")
    def test_post_image_processing_error_posts_without_image(
        self, mock_generate_message, mock_compress_image, mock_create_post
    ):
        # If _compress_image raises ImageProcessingError, post should proceed without image
        mock_create_post.return_value = {"uri": "some_uri", "cid": "some_cid"}
        
        post_flight_to_bluesky(self.flight_data, image_path=self.test_image_path)

        mock_create_post.assert_called_once()
        args_sent = mock_create_post.call_args[0][0]
        self.assertIsNone(args_sent.image) # Posted without image due to processing error

if __name__ == '__main__':
    # Test posting with FLIGHT_DATA_SAMPLE
    try:
        # Ensure environment variables are set
        if not os.getenv('BLUESKY_HANDLE') or not os.getenv('BLUESKY_PASSWORD'):
            raise ValueError("BLUESKY_HANDLE and BLUESKY_PASSWORD must be set in the environment.")

        # Post a test flight
        print("Posting test flight to Bluesky...")
        result = post_flight_to_bluesky(FLIGHT_DATA_SAMPLE, None, None)
        print(f"Post successful! URI: {result['uri']}, CID: {result['cid']}")

    except Exception as e:
        print(f"Error during test post: {e}")