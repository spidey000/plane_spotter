import os
import requests
from PIL import Image, ImageDraw, ImageFont
from loguru import logger
from utils.image_finder import get_first_image_url_jp, get_first_image_url_pp

class ImageService:
    def __init__(self, temp_dir: str = "socials"):
        self.temp_dir = temp_dir
        os.makedirs(self.temp_dir, exist_ok=True)

    def fetch_and_process_image(self, registration: str) -> str:
        """
        Fetches an image for the given registration, adds a copyright bar,
        and returns the local path to the processed image.
        Returns None if no image is found or processing fails.
        """
        if not registration or registration in ['null', 'None']:
            return self._get_fallback_image()

        logger.debug(f"Fetching image for registration {registration}")
        
        # 1. Try JetPhotos
        image_url, photographer = get_first_image_url_jp(registration)
        add_photographer = False
        
        # 2. Try Planespotters if not found
        if not image_url:
            add_photographer = True # Logic from original code: only add bar if from PP? Or always?
            # Original code: 
            # if not image_url: add_photographer = True; ... get_first_image_url_pp
            # Wait, looking at original code:
            # if not image_url (from JP): add_photographer = True; try PP.
            # So if JP works, add_photographer is False? That seems odd. 
            # Let's re-read original code.
            # Line 34: add_photographer = False
            # Line 35: if not image_url: add_photographer = True; try PP
            # So JP images don't get the bar? Maybe they already have it?
            # Let's preserve original logic for now.
            logger.debug("No image found on JetPhotos, trying Planespotters")
            image_url, photographer = get_first_image_url_pp(registration)
        
        if not image_url:
            logger.warning(f"No image found for {registration}")
            return self._get_fallback_image()

        # 3. Download Image
        temp_path = os.path.join(self.temp_dir, "temp_image.jpg")
        try:
            image_url = image_url.replace("/400/", "/full/")
            logger.debug(f"Downloading image from {image_url}")
            response = requests.get(image_url, timeout=30)
            if response.status_code == 200:
                with open(temp_path, "wb+") as f:
                    f.write(response.content)
            else:
                logger.error(f"Failed to download image: {response.status_code}")
                return self._get_fallback_image()
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return self._get_fallback_image()

        # 4. Add Copyright Bar (if applicable)
        if add_photographer and photographer:
            self._add_copyright_bar(temp_path, photographer)

        return temp_path

    def _add_copyright_bar(self, image_path: str, photographer: str):
        try:
            img = Image.open(image_path)
            width, height = img.size
            
            # Create a new image with space for the bar
            new_height = height + 30
            new_img = Image.new('RGB', (width, new_height), color=(0, 0, 0))
            new_img.paste(img, (0, 0))
            
            draw = ImageDraw.Draw(new_img)
            try:
                font = ImageFont.truetype("arial.ttf", 14)
            except:
                font = ImageFont.load_default()
            
            text = f"{photographer}"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            x = width - text_width - 10
            y = height + 5
            
            draw.text((x, y), text, font=font, fill=(255, 255, 255))
            new_img.save(image_path)
            logger.debug(f"Added copyright bar for {photographer}")
        except Exception as e:
            logger.error(f"Error adding copyright bar: {e}")

    def _get_fallback_image(self) -> str:
        fallback = os.path.join(self.temp_dir, "no_reg.jpg")
        if os.path.exists(fallback):
            return fallback
        return None
