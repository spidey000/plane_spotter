import asyncio
import os
from loguru import logger
from config import config_manager
from infrastructure.database.supabase_provider import SupabaseProvider
from infrastructure.api.aeroapi_client import AeroAPIClient
from infrastructure.social_media.legacy_provider import LegacySocialProvider
from services.filter_service import FilterService
from services.flight_service import FlightService
from services.notification_service import NotificationService

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

async def main():
    logger.info("Starting Twitter Spotter v4 (Modular)")
    
    # 1. Load Config
    config = config_manager.load_config()
    
    # 2. Initialize Infrastructure
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.error("SUPABASE_URL and SUPABASE_KEY must be set in environment variables.")
        return

    db_provider = SupabaseProvider(supabase_url, supabase_key)
    
    # Initialize Flight Data Providers
    data_providers = []
    airport_code = config['settings']['airport']
    
    # AeroAPI
    aeroapi_keys = [os.getenv(f"AEROAPI_KEY{i}") for i in range(3) if os.getenv(f"AEROAPI_KEY{i}")]
    if aeroapi_keys:
        aeroapi_client = AeroAPIClient(aeroapi_keys, airport_code, cost_limit=config['settings'].get('aeroapi_cost_limit', 5.0))
        data_providers.append(aeroapi_client)
    else:
        logger.warning("No AEROAPI_KEYs found.")

    # Aerodatabox
    # Import here to avoid circular dependency if any (though unlikely)
    from infrastructure.api.aerodatabox_client import AerodataboxClient
    adbox_keys = [os.getenv(f"ADBOX_KEY{i}") for i in range(3) if os.getenv(f"ADBOX_KEY{i}")]
    if adbox_keys:
        adbox_client = AerodataboxClient(adbox_keys, airport_code)
        data_providers.append(adbox_client)
    else:
        logger.warning("No ADBOX_KEYs found.")
        
    if not data_providers:
        logger.error("No flight data providers available. Exiting.")
        return
    
    # 3. Initialize Services
    filter_service = FilterService(db_provider)
    notification_service = NotificationService() # Auto-loads plugins
    
    # Check for DEBUG mode
    debug_mode = config['settings'].get('debug', False)
    if debug_mode:
        logger.info("DEBUG mode enabled (via config)")

    flight_service = FlightService(
        db_provider=db_provider,
        data_providers=data_providers,
        notification_service=notification_service,
        filter_service=filter_service,
        debug=debug_mode
    )
    
    # 4. Run Loop
    interval = config['execution'].get('interval', 7200)
    
    while True:
        try:
            # Reload config if needed (optional, but good for dynamic updates)
            current_config = config_manager.load_config()
            
            await flight_service.process_cycle(current_config)
            
            logger.info(f"Sleeping for {interval} seconds...")
            await asyncio.sleep(interval)
            
        except KeyboardInterrupt:
            logger.info("Stopping...")
            break
        except Exception as e:
            logger.exception(f"Critical error in main loop: {e}")
            await asyncio.sleep(60) # Sleep a bit before retrying

if __name__ == "__main__":
    asyncio.run(main())
