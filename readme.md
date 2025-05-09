# Twitter Spotter v4

## Project Overview

Twitter Spotter v4 is a Python application designed to track flights and post updates to various social media platforms. It integrates with multiple flight data APIs, processes the data, and schedules posts with relevant information and images.

## File Tree

```
twitter_spotter_v4/
├── main.py
├── master.py
├── readme.md
├── requirements.txt
├── api/
│   ├── api_handler_aeroapi.py
│   ├── api_handler_aerodatabox.py
│   └── data/
├── bot/
│   ├── __init__.py
│   └── handlers.py
├── config/
│   ├── config_manager.py
│   └── config.json
├── database/
│   ├── airlines.json
│   ├── baserow_manager.py
│   └── common_airlines.json
├── log/
│   └── logger_config.py
├── logs/
├── socials/
│   ├── bluesky.py
│   ├── instagram.py
│   ├── linkedin.py
│   ├── socials_processing.py
│   ├── telegram_msg_bot.py
│   ├── threads.py
│   └── twitter.py
├── utils/
│   ├── create_bsky_post.py
│   ├── data_processing.py
│   └── image_finder.py
```

## Key Features

-   Fetches flight data from AeroAPI and AeroDataBox.
-   Processes and merges data from multiple sources.
-   Stores flight and aircraft information in a Baserow database.
-   Generates and schedules posts for Telegram, Bluesky, Twitter, Threads, Instagram, and LinkedIn.
-   Finds relevant aircraft images using cloudscraper and BeautifulSoup.
-   Configurable via a JSON file.
-   Comprehensive logging using Loguru.

## API Integrations

### AeroAPI Handler (`api/api_handler_aeroapi.py`)

-   Fetches scheduled flight data (arrivals and departures).
-   Uses `aiohttp` for asynchronous requests.
-   Handles API pagination and rate limiting.
-   Saves raw API responses to JSON files.

### AeroDataBox API Handler (`api/api_handler_aerodatabox.py`)

-   Fetches flight data (arrivals and departures).
-   Uses `aiohttp` for asynchronous requests.
-   Supports comprehensive query parameters.
-   Saves raw API responses to JSON files.

## Social Media Integrations

### Socials Processing (`socials/socials_processing.py`)

-   Orchestrates posting to various social media platforms.
-   Fetches aircraft images using `utils/image_finder.py`.

### Telegram (`socials/telegram_msg_bot.py`)

-   Sends flight updates to a Telegram chat.
-   Uses the `python-telegram-bot` library.

### Bluesky (`socials/bluesky.py`)

-   Creates posts on Bluesky.
-   Uses the `atproto` library.

### Twitter (`socials/twitter.py`)

-   Schedules tweets with flight information.
-   Uses the `twikit` library.

### Threads (`socials/threads.py`)

-   Generates messages for Threads.

### Instagram (`socials/instagram.py`)

-   (Placeholder for Instagram integration)

### LinkedIn (`socials/linkedin.py`)

-   (Placeholder for LinkedIn integration)

## Database (`database/baserow_manager.py`)

-   Manages interaction with a Baserow database.
-   Uses `aiohttp` for asynchronous API calls to Baserow.
-   Stores and retrieves flight and aircraft data.

## Configuration (`config/config_manager.py`)

-   Loads configuration from `config/config.json`.
-   Allows modification of configuration values.

## Logging (`log/logger_config.py`)

-   Configures Loguru for application-wide logging.
-   Supports log rotation and different log levels.

## Testing

-   (No dedicated test files found in the current structure, but testing is crucial for ensuring application stability.)

## Utilities

### Data Processing (`utils/data_processing.py`)

-   Cleans, processes, and merges flight data from various APIs.
-   Interacts with the Baserow database.

### Image Finder (`utils/image_finder.py`)

-   Finds aircraft images from JetPhotos and Planespotters.net.
-   Uses `cloudscraper` and `BeautifulSoup`.

### Bluesky Post Creation (`utils/create_bsky_post.py`)

-   Helper utility for creating Bluesky posts.

## Setup and Usage

1.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
2.  **Configure the application:**
    -   Copy `config/config.example.json` to `config/config.json`.
    -   Update `config/config.json` with your API keys, Baserow details, and social media credentials.
    -   Alternatively, set environment variables for sensitive data (e.g., `BASEROW_API_URL`, `TELEGRAM_CHAT_ID`).
3.  **Run the application:**
    ```bash
    python master.py
    ```

## Docker Deployment

This project can be deployed using Docker, providing a consistent environment for the application.

### Using Dockerfile directly

A `Dockerfile` is provided for containerizing the application.

1.  **Build the Docker image:**
    ```bash
    docker build -t twitter-spotter-v4 .
    ```
2.  **Run the Docker container:**
    Ensure you pass all necessary environment variables.
    ```bash
    docker run -d \
      -e BASEROW_API_URL="your_baserow_api_url" \
      -e TELEGRAM_CHAT_ID="your_telegram_chat_id" \
      -e AEROAPI_KEY="your_aeroapi_key" \
      --name twitter_spotter_container \
      twitter-spotter-v4
    ```
    (Add other necessary environment variables as required by `config/config.json`.)
    To view logs:
    ```bash
    docker logs -f twitter_spotter_container
    ```

### Using Docker Compose

A `docker-compose.yml` file is also provided to simplify the deployment and management, especially for handling environment variables and volumes.

1.  **Environment Variables:**
    It is highly recommended to create a `.env` file in the project root directory (alongside `docker-compose.yml`) to store your sensitive credentials and configuration. Docker Compose will automatically load variables from this file.
    Create a file named `.env` with the following content, replacing placeholder values with your actual credentials.
    The `config_manager.py` expects environment variables for nested JSON structures to be formatted as `PARENTKEY__CHILDKEY__GRANDCHILDKEY`.
    For example, if your `config.json` has `{"baserow": {"db_id": "value"}}`, the corresponding environment variable is `BASEROW__DB_ID`.

    ```env
    # Baserow (assuming these are under a "baserow" key in config.json)
    BASEROW__DB_ID=your_baserow_db_id
    BASEROW__TABLE_ID_AIRCRAFT=your_baserow_aircraft_table_id
    BASEROW__TABLE_ID_FLIGHTS=your_baserow_flights_table_id
    BASEROW__TABLE_ID_AIRLINES=your_baserow_airlines_table_id
    BASEROW__API_URL=your_baserow_api_url
    BASEROW__USER=your_baserow_user
    BASEROW__PASSWORD=your_baserow_password
    BASEROW__JWT_TOKEN=your_baserow_jwt_token # If using JWT

    # Telegram (assuming these are under a "telegram" key in config.json)
    TELEGRAM__BOT_TOKEN=your_telegram_bot_token
    TELEGRAM__CHAT_ID=your_telegram_chat_id

    # Social Media APIs (e.g., under "social_media":"bluesky" in config.json)
    SOCIAL_MEDIA__BLUESKY__HANDLE=your_bsky_handle
    SOCIAL_MEDIA__BLUESKY__APP_PASSWORD=your_bsky_app_password
    # Add other social media API keys following the PARENT__CHILD__KEY convention
    # Example: SOCIAL_MEDIA__TWITTER__API_KEY=your_twitter_api_key

    # API Keys (e.g., under "api_keys" in config.json)
    API_KEYS__AEROAPI=your_aeroapi_key
    # If AeroDataBox keys are nested, e.g., "api_keys":{"aerodatabox":{"key":"...", "app_id":"..."}}
    API_KEYS__AERODATABOX__KEY=your_aerodatabox_api_key 
    API_KEYS__AERODATABOX__APP_ID=your_aerodatabox_app_id

    # Other configurations (if they are top-level in config.json, use their direct name)
    # Example: PYTHON_ENV=production (if "python_env" is a top-level key)
    # If nested, e.g. "settings":{"python_env":"production"}, use SETTINGS__PYTHON_ENV=production
    ```
    The `config_manager.py` is now set up to load values from `config/config.json` and then override them with any matching environment variables found.
    Docker Compose will automatically load variables from the `.env` file and make them available to the application container.

2.  **Build and run the application:**
    To build the Docker image (if it doesn't exist or if the `Dockerfile` has changed) and start the service:
    ```bash
    docker-compose up --build
    ```
    To run in detached mode (in the background):
    ```bash
    docker-compose up -d --build
    ```
    If the image is already built and up-to-date, you can omit `--build`:
    ```bash
    docker-compose up -d
    ```

3.  **View logs (if running in detached mode):**
    The service name in `docker-compose.yml` is `app`.
    ```bash
    docker-compose logs -f app
    ```

4.  **Stop the application:**
    This will stop and remove the containers, networks, and volumes created by `up`.
    ```bash
    docker-compose down
    ```
    To stop without removing volumes (if you have persistent data volumes defined and want to keep them):
    ```bash
    docker-compose stop
    ```
