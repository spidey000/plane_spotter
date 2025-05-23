import subprocess
import time
import sys
from loguru import logger
from config import config_manager
# Removed dotenv import as we will rely on environment variables passed to the container
from dotenv import load_dotenv
from log.logger_config import logger
import os
# logger.info("--- All Environment Variables from os.environ ---")
# for key, value in os.environ.items():
#     logger.info(f"OS ENV: {key} = {value}")
# logger.info("--- Loaded Configuration ---")

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

# Export the logger for reuse in other modules
global_logger = logger


def start_process(command):
    """Start a subprocess and return the process object."""
    return subprocess.Popen(command, shell=True)

def stop_process(process):
    """Stop a subprocess gracefully."""
    process.terminate()
    process.wait()
#test commit
def main():
    load_dotenv()

    main_process = start_process("python main.py")
    logger.info("Main application started.")

    # Start the Telegram bot
    bot_process = start_process("python bot/handlers.py")
    logger.info("Telegram bot started.")

    try:
        while True:
            # Check if either process has exited
            if main_process.poll() is not None:
                logger.warning("Main application has stopped. Restarting...")
                main_process = start_process("python main.py")
                #main_process = start_process("python -c 'from main import fetch_and_process_flights; import asyncio; asyncio.run(fetch_and_process_flights())'")

            if bot_process.poll() is not None:
                logger.warning("Telegram bot has stopped. Restarting...")
                bot_process = start_process("python bot/handlers.py")

            time.sleep(10)  # Check every 10 seconds

    except KeyboardInterrupt:
        logger.info("Shutting down processes...")
        stop_process(main_process)
        stop_process(bot_process)
        logger.info("Processes stopped.")

if __name__ == "__main__":
    main()
