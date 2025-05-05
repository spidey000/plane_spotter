import cloudscraper
from bs4 import BeautifulSoup
import os

def download_images(url, save_dir='test/images'):
    # Create a Cloudscraper instance
    scraper = cloudscraper.create_scraper()
    
    # Create save directory if it doesn't exist
    os.makedirs(save_dir, exist_ok=True)
    
    try:
        # Get the page content
        response = scraper.get(url)
        response.raise_for_status()
        
        # Parse the HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all image tags with class 'photo_card__photo'
        img_tags = soup.find_all('img', class_='photo_card__photo')
        
        # Download each image
        for i, img in enumerate(img_tags):
            img_url = img['src']
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif not img_url.startswith('http'):
                img_url = 'https://www.planespotters.net' + img_url
                
            # Get the image content
            img_response = scraper.get(img_url)
            img_response.raise_for_status()
            
            # Save the image
            file_name = f"image_{i+1}.jpg"
            file_path = os.path.join(save_dir, file_name)
            with open(file_path, 'wb') as f:
                f.write(img_response.content)
            print(f"Downloaded {file_name}")
            
        print("All images downloaded successfully!")
        
    except Exception as e:
        print(f"Error: {e}")

# Usage
url = "https://www.planespotters.net/photos/reg/HB-AYP?sort=latest"
download_images(url)