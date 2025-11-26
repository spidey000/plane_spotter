import asyncio
from services.notification_service import NotificationService
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

async def verify():
    logger.info("Initializing NotificationService...")
    service = NotificationService()
    
    logger.info(f"Loaded {len(service.social_providers)} plugins:")
    for provider in service.social_providers:
        logger.info(f"- {provider.__class__.__name__}")

    if len(service.social_providers) > 0:
        logger.success("Plugin loading successful!")
    else:
        logger.error("No plugins loaded.")

if __name__ == "__main__":
    asyncio.run(verify())
