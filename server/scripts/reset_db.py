# server/scripts/reset_db.py
"""
Database reset script - Drop all tables and recreate them

WARNING: This will delete all data!

Usage:
    python scripts/reset_db.py
    
    Or skip confirmation:
    python scripts/reset_db.py --force
"""

import os
import sys
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import drop_all_tables, init_db, test_connection
from core.logger import get_logger

logger = get_logger(__name__)


def reset_database(force: bool = False) -> bool:
    """
    Reset database - drop all tables and recreate them.
    
    Args:
        force: If True, skip confirmation prompt
        
    Returns:
        True if successful, False otherwise
    """
    # Test connection
    logger.info("Testing database connection...")
    if not test_connection():
        logger.error("❌ Cannot connect to database")
        return False
    
    # Confirm before resetting
    if not force:
        print("\n" + "="*60)
        print("⚠️  WARNING: This will DELETE ALL DATA!")
        print("="*60)
        print("\nThis will:")
        print("  1. Drop all existing tables")
        print("  2. Create fresh tables")
        print("\nAll data will be PERMANENTLY DELETED.")
        print("Database: " + os.getenv("DATABASE_URL", "").split("@")[-1])
        print("\nAre you sure?")
        
        response = input("\nType 'yes' to confirm, or press Enter to cancel: ").strip().lower()
        
        if response != "yes":
            print("❌ Operation cancelled.")
            return False
    
    # Drop tables
    logger.info("🗑️  Dropping all tables...")
    if not drop_all_tables():
        logger.error("❌ Failed to drop tables")
        return False
    
    # Initialize tables
    logger.info("📦 Creating fresh tables...")
    if not init_db():
        logger.error("❌ Failed to create tables")
        return False
    
    logger.info("✅ Database reset successfully")
    return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Reset database (drop and recreate)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt"
    )
    
    args = parser.parse_args()
    
    success = reset_database(force=args.force)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()