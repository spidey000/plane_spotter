from loguru import logger
import sys

# ... existing code ...
# Remove default handler that outputs to terminal
logger.remove()


logger.add("test/debug.log", level="DEBUG", rotation="1 day", retention="7 days", format="{time} {level} {message}")
logger.add(sys.stdout, level="INFO")#, filter=lambda record: record["level"].no >= logger.level("INFO").no)
logger.debug("debug test level")
logger.info("infor logger level")