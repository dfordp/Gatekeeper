# server/scripts/reset_db.py
"""
Database reset script - Drop all tables and reinitialize

Usage:
    python scripts/reset_db.py

This script will:
1. Drop all existing tables
2. Recreate all tables
3. Create the default company "Future Tech Design"
4. Create a super admin user
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import drop_all_tables, test_connection
from core.logger import get_logger

# Import from init_db
from init_db import initialize_database

logger = get_logger(__name__)


def reset_database() -> bool:
    """
    Reset database by dropping all tables and reinitializing.
    
    Returns:
        True if successful, False otherwise
    """
    # Confirm with user
    print("\n" + "=" * 60)
    print("⚠️  WARNING: This will DELETE all data in the database!")
    print("=" * 60)
    
    response = input("\nType 'yes' to confirm database reset: ").strip().lower()
    
    if response != "yes":
        logger.info("Reset cancelled")
        return False
    
    logger.info("Resetting database...")
    
    # Test connection
    if not test_connection():
        logger.error("Cannot connect to database")
        return False
    
    # Drop all tables
    logger.info("Dropping all tables...")
    if not drop_all_tables():
        logger.error("Failed to drop tables")
        return False
    logger.info("✓ All tables dropped")
    
    # Reinitialize
    logger.info("\nReinitializing database...")
    if not initialize_database():
        logger.error("Failed to reinitialize database")
        return False
    
    return True


if __name__ == "__main__":
    try:
        success = reset_database()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Reset cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)