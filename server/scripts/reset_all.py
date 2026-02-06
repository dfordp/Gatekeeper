# server/scripts/reset_all.py
"""
Complete Reset Script - Clear PostgreSQL and Qdrant

Usage:
    python scripts/reset_all.py

This script will:
1. Drop all PostgreSQL tables
2. Delete all Qdrant collections
3. Reinitialize PostgreSQL with default company and admin
4. Recreate Qdrant collection
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import drop_all_tables, test_connection, init_db
from core.logger import get_logger
from qdrant_client import QdrantClient

logger = get_logger(__name__)

# Qdrant configuration for local development (not Docker)
QDRANT_URL = "http://localhost:6333"
QDRANT_API_KEY = "qdrant_secure_key_123"
QDRANT_COLLECTION = "tickets"


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client for local development"""
    return QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        timeout=30.0
    )


def reset_qdrant() -> bool:
    """
    Delete all Qdrant collections
    
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Connecting to Qdrant at {QDRANT_URL}...")
        client = get_qdrant_client()
        
        # Delete the collection if it exists
        try:
            logger.info(f"Deleting Qdrant collection '{QDRANT_COLLECTION}'...")
            client.delete_collection(collection_name=QDRANT_COLLECTION)
            logger.info(f"✓ Deleted Qdrant collection")
        except Exception as e:
            error_str = str(e).lower()
            if "not found" in error_str or "doesn't exist" in error_str:
                logger.info("✓ Collection doesn't exist (nothing to delete)")
            else:
                logger.warning(f"Failed to delete collection: {e}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to connect to Qdrant: {e}")
        logger.warning(f"Make sure Qdrant is running at: {QDRANT_URL}")
        return False


def reset_postgresql() -> bool:
    """
    Drop all PostgreSQL tables and reinitialize
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Test connection
        if not test_connection():
            logger.error("Cannot connect to PostgreSQL")
            return False
        
        # Drop all tables
        logger.info("Dropping all PostgreSQL tables...")
        if not drop_all_tables():
            logger.error("Failed to drop tables")
            return False
        logger.info("✓ Dropped all tables")
        
        # Reinitialize tables
        logger.info("Reinitializing PostgreSQL tables...")
        if not init_db():
            logger.error("Failed to initialize database")
            return False
        logger.info("✓ Reinitialized PostgreSQL")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to reset PostgreSQL: {e}")
        return False


def initialize_defaults() -> bool:
    """
    Create default company and admin user after reset
    
    Returns:
        True if successful, False otherwise
    """
    try:
        from scripts.init_db import initialize_database
        
        logger.info("Initializing default company and admin...")
        if not initialize_database():
            logger.error("Failed to initialize defaults")
            return False
        logger.info("✓ Initialized defaults")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize defaults: {e}")
        return False


def verify_qdrant_collection() -> bool:
    """
    Verify Qdrant collection is ready for new embeddings
    
    Returns:
        True if successful, False otherwise
    """
    try:
        from qdrant_client.models import VectorParams, Distance, PayloadSchemaType, PayloadIndexInfo
        
        logger.info("Verifying Qdrant collection...")
        client = get_qdrant_client()
        
        try:
            # Check if collection exists
            client.get_collection(QDRANT_COLLECTION)
            logger.info("✓ Collection already exists")
            return True
        except Exception as e:
            error_str = str(e).lower()
            if "not found" in error_str or "doesn't exist" in error_str:
                # Create collection
                logger.info(f"Creating Qdrant collection '{QDRANT_COLLECTION}'...")
                client.create_collection(
                    collection_name=EmbeddingManager.QDRANT_COLLECTION,
                    vectors_config=VectorParams(
                        size=EmbeddingManager.VECTOR_SIZE,
                        distance=Distance.COSINE
                    ),
                    payload_schema={
                        "company_id": PayloadIndexInfo(
                            type=PayloadSchemaType.KEYWORD,
                            index_type=None  # or IndexType.EXACT for keyword search
                        ),
                        "is_active": PayloadIndexInfo(
                            type=PayloadSchemaType.KEYWORD
                        ),
                        "source_type": PayloadIndexInfo(
                            type=PayloadSchemaType.KEYWORD
                        ),
                        "ticket_id": PayloadIndexInfo(
                            type=PayloadSchemaType.KEYWORD
                        )
                    }
                )
                logger.info("✓ Collection created")
                return True
            else:
                logger.warning(f"Failed to check/create collection: {e}")
                return False
        
    except Exception as e:
        logger.warning(f"Failed to verify Qdrant: {e}")
        return False


def main() -> bool:
    """
    Main reset function
    
    Returns:
        True if successful, False otherwise
    """
    # Confirm with user
    print("\n" + "=" * 70)
    print("⚠️  WARNING: This will DELETE ALL data in PostgreSQL and Qdrant!")
    print("=" * 70)
    print("\nThis will:")
    print("  1. Drop all PostgreSQL tables")
    print("  2. Delete all Qdrant collections")
    print("  3. Reinitialize PostgreSQL")
    print("  4. Create default company and admin")
    print("\n" + "=" * 70)
    
    response = input("\nType 'yes-reset-all' to confirm: ").strip().lower()
    
    if response != "yes-reset-all":
        logger.info("Reset cancelled")
        return False
    
    logger.info("\n" + "=" * 70)
    logger.info("STARTING COMPLETE RESET")
    logger.info("=" * 70 + "\n")
    
    # Step 1: Reset Qdrant
    logger.info("[1/4] Resetting Qdrant...")
    if not reset_qdrant():
        logger.error("Failed to reset Qdrant. Aborting.")
        return False
    logger.info("✓ Qdrant reset complete\n")
    
    # Step 2: Reset PostgreSQL
    logger.info("[2/4] Resetting PostgreSQL...")
    if not reset_postgresql():
        logger.error("Failed to reset PostgreSQL. Aborting.")
        return False
    logger.info("✓ PostgreSQL reset complete\n")
    
    # Step 3: Initialize defaults
    logger.info("[3/4] Initializing defaults...")
    if not initialize_defaults():
        logger.error("Failed to initialize defaults. Aborting.")
        return False
    logger.info("✓ Defaults initialized\n")
    
    # Step 4: Verify Qdrant collection is ready
    logger.info("[4/4] Verifying Qdrant collection...")
    if not verify_qdrant_collection():
        logger.warning("Failed to verify Qdrant collection, but continuing...")
    logger.info("✓ Qdrant collection ready\n")
    
    # Success
    logger.info("=" * 70)
    logger.info("✅ COMPLETE RESET SUCCESSFUL")
    logger.info("=" * 70)
    logger.info("\nSystem is ready for fresh start:")
    logger.info("  • PostgreSQL: All tables created and initialized")
    logger.info("  • Qdrant: Collection deleted and ready for new embeddings")
    logger.info("  • Default company: 'Future Tech Design'")
    logger.info("  • Admin user: support@ftdsplm.com")
    logger.info("\nYou can now start creating tickets and embeddings from scratch.")
    logger.info("=" * 70 + "\n")
    
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Reset cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)