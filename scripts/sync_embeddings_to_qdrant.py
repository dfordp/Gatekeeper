#!/usr/bin/env python3
"""
Sync embeddings from PostgreSQL to Qdrant.

This script populates the Qdrant vector database with embeddings
that were previously created in PostgreSQL.

Usage:
    python scripts/sync_embeddings_to_qdrant.py
    python scripts/sync_embeddings_to_qdrant.py --company-id <uuid>
    python scripts/sync_embeddings_to_qdrant.py --clear  # Clear and resync everything
"""

import os
import sys
import logging
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, Embedding
from qdrant_wrapper import qdrant
from embedding_service import EmbeddingService
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def sync_embeddings(company_id=None, clear_first=False):
    """
    Sync embeddings from PostgreSQL to Qdrant.
    
    Args:
        company_id: Optional UUID to sync only one company
        clear_first: If True, clear Qdrant before syncing
        
    Returns:
        Number of embeddings synced
    """
    if qdrant is None:
        logger.error("✗ Qdrant wrapper not available")
        return 0
    
    db = SessionLocal()
    
    try:
        logger.info("\n" + "="*70)
        logger.info("  EMBEDDING SYNC TO QDRANT")
        logger.info("="*70 + "\n")
        
        # Query embeddings
        query = db.query(Embedding).filter(Embedding.is_active == True)
        
        if company_id:
            logger.info(f"Syncing embeddings for company: {company_id}")
            query = query.filter(Embedding.company_id == company_id)
        else:
            logger.info("Syncing all active embeddings...")
        
        embeddings = query.all()
        
        if not embeddings:
            logger.info("✓ No active embeddings to sync")
            return 0
        
        logger.info(f"Found {len(embeddings)} active embeddings to sync\n")
        
        synced_count = 0
        error_count = 0
        
        for i, embedding in enumerate(embeddings, 1):
            try:
                # Get the vector from text
                vector = EmbeddingService.get_embedding_vector(embedding.text_content)
                
                if not vector:
                    logger.warning(f"✗ [{i}/{len(embeddings)}] Failed to get vector for {embedding.id}")
                    error_count += 1
                    continue
                
                # Insert into Qdrant
                success = qdrant.insert_embedding(
                    embedding_id=str(embedding.id),
                    vector=vector,
                    ticket_id=str(embedding.ticket_id),
                    company_id=str(embedding.company_id),
                    source_type=embedding.source_type,
                    chunk_index=embedding.chunk_index,
                    attachment_id=str(embedding.attachment_id) if embedding.attachment_id else None,
                    text_content=embedding.text_content
                )
                
                if success:
                    logger.info(f"✓ [{i}/{len(embeddings)}] Synced {embedding.source_type} for ticket {embedding.ticket_id}")
                    synced_count += 1
                else:
                    logger.warning(f"✗ [{i}/{len(embeddings)}] Failed to insert embedding {embedding.id}")
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"✗ [{i}/{len(embeddings)}] Error syncing {embedding.id}: {e}")
                error_count += 1
                continue
        
        logger.info("\n" + "="*70)
        logger.info(f"✓ Sync complete: {synced_count} synced, {error_count} errors")
        logger.info("="*70 + "\n")
        
        return synced_count
        
    except Exception as e:
        logger.error(f"✗ Sync failed: {e}")
        import traceback
        traceback.print_exc()
        return 0
    finally:
        db.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync embeddings from PostgreSQL to Qdrant"
    )
    parser.add_argument(
        "--company-id",
        help="Sync only this company (UUID)"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear Qdrant before syncing (TODO: implement)"
    )
    
    args = parser.parse_args()
    
    # Sync embeddings
    count = sync_embeddings(company_id=args.company_id, clear_first=args.clear)
    
    return 0 if count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())