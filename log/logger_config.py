from loguru import logger
import sys
from config import config_manager

# Load configuration
config = config_manager.load_config()

# Configure logger from config
LOG_FILE = config['logging']['log_file']
WARN_LOG_FILE = config['logging']['warning_log_file']
LOG_LEVEL = config['logging']['log_level']
LOG_ROTATION = config['logging']['log_rotation']

# Initialize logger
logger.remove() # Remove default handler
logger.add(LOG_FILE, level=LOG_LEVEL.upper(), enqueue=True, rotation=LOG_ROTATION)
if WARN_LOG_FILE != LOG_FILE:
    logger.add(WARN_LOG_FILE, level="WARNING", enqueue=True, rotation=LOG_ROTATION)
logger.add(sys.stdout, level="INFO") # Keep console output for INFO+