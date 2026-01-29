# server/utils/logger.py
import logging
from config import settings

def setup_logger():
    """Configure logging."""
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return logging.getLogger(__name__)