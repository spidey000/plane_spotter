from typing import List, Dict, Any
from loguru import logger
from core.models import ProcessedFlight
from infrastructure.social_media.plugin_loader import PluginLoader
from services.image_service import ImageService

class NotificationService:
    def __init__(self, plugin_dir: str = "infrastructure/social_media/plugins"):
        self.plugin_loader = PluginLoader(plugin_dir)
        self.social_providers = self.plugin_loader.load_plugins()
        self.image_service = ImageService()
        logger.info(f"NotificationService initialized with {len(self.social_providers)} plugins")

    async def notify(self, processed_flight: ProcessedFlight, config: Dict[str, Any]):
        """
        Sends notifications to all configured social media providers.
        """
        logger.info(f"Processing notifications for {processed_flight.flight.flight_name_iata}")

        # 1. Fetch and Process Image
        # We store the local path in image_url temporarily so plugins can access it
        # This is a bit of a hack, but fits the current interface.
        # Ideally, we'd pass image_path separately.
        local_image_path = self.image_service.fetch_and_process_image(processed_flight.flight.registration)
        if local_image_path:
            processed_flight.flight.image_url = local_image_path
        
        # 2. Notify all providers
        for provider in self.social_providers:
            try:
                provider_name = provider.__class__.__name__
                logger.debug(f"Notifying {provider_name}")
                await provider.post_flight(processed_flight, config)
            except Exception as e:
                logger.error(f"Error in social provider {provider.__class__.__name__}: {e}")
