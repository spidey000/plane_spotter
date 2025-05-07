import cloudscraper
from bs4 import BeautifulSoup
import time
import random
from loguru import logger
from log.logger_config import logger


def get_first_image_url_jp(registration):
    params = {
        "aircraft": "all",
        "airline": "all",
        "category": "all",
        "country-location": "all",
        "genre": "all",
        "keywords-contain": "1",
        "keywords-type": "all",
        "keywords": registration,
        "photo-year": "all",
        "photographer-group": "all",
        "search-type": "Advanced",
        "sort-order": "0",
        "page": "1"
    }
    url = "https://www.jetphotos.com/showphotos.php"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.jetphotos.com/",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        scraper = cloudscraper.create_scraper()
        time.sleep(random.uniform(2, 5))  # Increased delay to reduce rate limiting
        
        # Add retry logic for 429 errors
        max_retries = 3
        for attempt in range(max_retries):
            response = scraper.get(url, headers=headers, params=params)
            
            if response.status_code == 429:
                if attempt < max_retries - 1:
                    retry_after = int(response.headers.get('Retry-After', 10)) + 5  # Add buffer
                    logger.warning(f"Rate limited. Retrying after {retry_after} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_after)
                    continue
                else:
                    logger.error("Max retries reached for rate limiting")
                    return None
            elif response.status_code != 200: #response.status_code
                logger.error(f"Failed: HTTP {response.status_code}")
                return None
            break

        if "CAPTCHA" in response.text:
            logger.debug("CAPTCHA detected. Manual intervention required.")
            return None

        soup = BeautifulSoup(response.text, 'lxml')
        img_tag = soup.find('img', class_='result__photo')
        
        if img_tag and img_tag.get('src'):
            img_url = f"https:{img_tag['src']}" if img_tag['src'].startswith('//') else img_tag['src']
            logger.success(f'Image found {img_url}')
            return img_url.replace('/400/', '/full/')
        
        logger.warning("JP No image found.")
        return None

    except Exception as e:
        logger.error(f"Error: {e}")
        return None
def get_first_image_url_pp(registration):
    params = {
         "sort": "latest"
    }
    url = f"https://www.planespotters.net/photos/reg/{registration}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.jetphotos.com/",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        scraper = cloudscraper.create_scraper()
        time.sleep(random.uniform(2, 5))  # Delay to mimic human behavior
        response = scraper.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            logger.error(f"Failed: HTTP {response.status_code}")
            return None

        if "CAPTCHA" in response.text:
            logger.debug("CAPTCHA detected. Manual intervention required.")
            return None

        soup = BeautifulSoup(response.text, 'lxml')
        img_tag = soup.find('img', class_='photo_card__photo')
        
        if img_tag and img_tag.get('src'):
            img_url = img_tag['src']
            logger.success(f'Image found {img_url}')
            return img_url
        
        logger.warning("PP No image found.")
        return None

    except Exception as e:
        logger.error(f"Error: {e}")
        return None
    

def main():
    registration = "ra78830"  # Replace with the desired registration code
    image_url = get_first_image_url_pp(registration)
    
    if image_url:
        print(f"First image URL for registration {registration}: {image_url}")
    else:
        get_first_image_url_jp(registration)
        print("No image URL found.")

if __name__ == "__main__":
    main()