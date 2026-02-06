# server/scripts/index_qdrant.py
"""
Qdrant Payload Indexing Script - Add indexes to existing collection

Usage:
    python scripts/index_qdrant.py

This script will:
1. Connect to Qdrant at http://localhost:6333
2. Find the 'tickets' collection
3. Add keyword indexes for filtering fields (company_id, is_active, source_type, ticket_id)
4. Report success or any existing indexes

Perfect for existing Qdrant instances that don't have payload indexes yet.
No data is deleted or modified - only indexes are added.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logger import get_logger

logger = get_logger(__name__)

# Qdrant configuration
QDRANT_URL = "http://localhost:6333"
QDRANT_API_KEY = "qdrant_secure_key_123"
QDRANT_COLLECTION = "tickets"


def index_qdrant_collection() -> bool:
    """
    Add payload indexes to existing Qdrant collection.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        from qdrant_client import QdrantClient
        
        logger.info("=" * 70)
        logger.info("🔍 Qdrant Payload Indexing")
        logger.info("=" * 70)
        
        logger.info(f"\nConnecting to Qdrant at {QDRANT_URL}...")
        
        client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
            timeout=30.0
        )
        
        # Check if collection exists
        logger.info(f"Checking for collection '{QDRANT_COLLECTION}'...")
        collection_exists = False
        try:
            collection = client.get_collection(QDRANT_COLLECTION)
            logger.info(f"✓ Found collection with {collection.points_count} points")
            collection_exists = True
        except Exception as e:
            error_str = str(e).lower()
            # Handle Pydantic validation errors (schema mismatch between client and server)
            if "validation error" in error_str and "parsing" in error_str:
                logger.info("✓ Collection exists (validation warning ignored)")
                logger.info("   (This is a client-server version mismatch, but collection exists)")
                collection_exists = True
            elif "not found" in error_str or "doesn't exist" in error_str:
                logger.error(f"❌ Collection '{QDRANT_COLLECTION}' does not exist")
                logger.error("   Run 'python scripts/init_db.py' first to create it")
                return False
            else:
                logger.error(f"❌ Error checking collection: {e}")
                return False
        
        if not collection_exists:
            return False
        
        # Add payload indexes for filtering
        logger.info("\nAdding payload indexes for filtering...")
        fields_to_index = [
            "company_id",
            "is_active", 
            "source_type",
            "ticket_id"
        ]
        
        indexed_count = 0
        skipped_count = 0
        
        for field in fields_to_index:
            try:
                logger.info(f"  Creating index for '{field}'...")
                client.create_payload_index(
                    collection_name=QDRANT_COLLECTION,
                    field_name=field,
                    field_schema="keyword"
                )
                logger.info(f"    ✓ Index created for '{field}'")
                indexed_count += 1
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str:
                    logger.info(f"    ✓ Index already exists for '{field}'")
                    skipped_count += 1
                else:
                    logger.warning(f"    ❌ Failed to create index for '{field}': {str(e)[:100]}")
                    failed_count += 1
        
        logger.info("\n" + "=" * 70)
        logger.info("✅ INDEXING COMPLETE")
        logger.info("=" * 70)
        logger.info(f"\n📊 Summary:")
        logger.info(f"   • New indexes created: {indexed_count}")
        logger.info(f"   • Existing indexes: {skipped_count}")
        logger.info(f"   • Total indexed fields: {indexed_count + skipped_count}")
        logger.info("\n✓ Your Qdrant collection is now optimized for filtering by:")
        logger.info("   • company_id (company filtering)")
        logger.info("   • is_active (active embeddings only)")
        logger.info("   • source_type (embedding type filtering)")
        logger.info("   • ticket_id (ticket-specific searches)")
        logger.info("\n" + "=" * 70 + "\n")
        
        return True
        
    except ImportError:
        logger.error("❌ Qdrant client not installed")
        logger.error("   Install with: pip install qdrant-client")
        return False
        
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        success = index_qdrant_collection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Indexing cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)