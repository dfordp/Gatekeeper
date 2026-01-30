# server/scripts/init_db.py
"""
Database initialization script - Create all tables

Usage:
    python scripts/init_db.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import init_db, test_connection
from core.logger import get_logger

logger = get_logger(__name__)


def initialize_database() -> bool:
    """
    Initialize database tables.
    
    Returns:
        True if successful, False otherwise
    """
    # Test connection first
    logger.info("Testing database connection...")
    if not test_connection():
        logger.error("❌ Cannot connect to database")
        return False
    
    # Initialize tables
    logger.info("📦 Initializing database tables...")
    if init_db():
        logger.info("✅ Database initialized successfully")
        return True
    else:
        logger.error("❌ Failed to initialize database")
        return False


if __name__ == "__main__":
    success = initialize_database()
    sys.exit(0 if success else 1)