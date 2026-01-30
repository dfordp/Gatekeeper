# server/scripts/drop_db.py
"""
Database drop script - WARNING: This will delete all data!

Usage:
    python scripts/drop_db.py
    
    Or with confirmation:
    python scripts/drop_db.py --force
"""

import os
import sys
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import drop_all_tables, test_connection
from core.logger import get_logger

logger = get_logger(__name__)


def drop_database(force: bool = False) -> bool:
    """
    Drop all database tables.
    
    Args:
        force: If True, skip confirmation prompt
        
    Returns:
        True if successful, False otherwise
    """
    # Test connection first
    logger.info("Testing database connection...")
    if not test_connection():
        logger.error("❌ Cannot connect to database")
        return False
    
    # Confirm before dropping
    if not force:
        print("\n" + "="*60)
        print("⚠️  WARNING: This will DELETE ALL DATA in the database!")
        print("="*60)
        print("\nThis action cannot be undone.")
        print("Database: " + os.getenv("DATABASE_URL", "").split("@")[-1])
        print("\nAre you sure you want to drop all tables?")
        
        response = input("\nType 'yes' to confirm, or press Enter to cancel: ").strip().lower()
        
        if response != "yes":
            print("❌ Operation cancelled.")
            return False
    
    # Drop tables
    logger.info("🗑️  Dropping all database tables...")
    if drop_all_tables():
        logger.info("✅ All database tables dropped successfully")
        return True
    else:
        logger.error("❌ Failed to drop database tables")
        return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Drop all database tables")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt (dangerous!)"
    )
    parser.add_argument(
        "--db-url",
        help="Override DATABASE_URL from .env (for manual connection)"
    )
    
    args = parser.parse_args()
    
    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url
    
    success = drop_database(force=args.force)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()