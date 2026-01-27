#!/usr/bin/env python3
"""
Test script for embedding service.

Usage:
    python scripts/test_embedding_service.py
"""

import os
import sys
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, Ticket, Embedding
from embedding_service import EmbeddingService
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run embedding service tests."""
    
    logger.info("\n" + "="*70)
    logger.info("  EMBEDDING SERVICE TEST")
    logger.info("="*70 + "\n")
    
    db = SessionLocal()
    
    try:
        # Test 1: Get embeddings config
        logger.info("Test 1: Configuration")
        logger.info(f"  Chunk size: {EmbeddingService.CHUNK_SIZE} chars")
        logger.info(f"  Chunk overlap: {EmbeddingService.CHUNK_OVERLAP} chars")
        logger.info(f"  Max text length: {EmbeddingService.MAX_TEXT_LENGTH} chars")
        
        # Test 2: Find test ticket
        logger.info("\nTest 2: Find test ticket")
        ticket = db.query(Ticket).first()
        if not ticket:
            logger.error("✗ No tickets found. Run migration with --seed first.")
            return False
        
        logger.info(f"  ✓ Found ticket: {ticket.ticket_no}")
        logger.info(f"    Subject: {ticket.subject}")
        logger.info(f"    Category: {ticket.category}")
        
        # Test 3: Check if already embedded
        logger.info("\nTest 3: Check existing embeddings")
        existing = db.query(Embedding).filter(Embedding.ticket_id == ticket.id).count()
        logger.info(f"  Existing embeddings for this ticket: {existing}")
        
        if existing > 0:
            logger.info("  ℹ Ticket already embedded, skipping embedding step")
        else:
            # Test 4: Embed ticket
            logger.info("\nTest 4: Embed ticket")
            count = EmbeddingService.embed_ticket_created(str(ticket.id), str(ticket.company_id))
            logger.info(f"  ✓ Created {count} embeddings")
        
        # Test 5: Get embeddings
        logger.info("\nTest 5: Query embeddings")
        embeddings = db.query(Embedding).filter(
            Embedding.ticket_id == ticket.id,
            Embedding.is_active == True
        ).all()
        
        logger.info(f"  ✓ Found {len(embeddings)} active embeddings:")
        for emb in embeddings:
            logger.info(f"    - {emb.source_type} (chunk {emb.chunk_index}): {len(emb.text_content)} chars")
        
        # Test 6: Get confidence threshold
        logger.info("\nTest 6: Confidence thresholds")
        for category in ["Login / Access", "License", "Performance", "Other"]:
            threshold = EmbeddingService.get_confidence_threshold(category)
            logger.info(f"  {category}: {threshold}")
        
        # Test 7: Get statistics
        logger.info("\nTest 7: Embedding statistics")
        stats = EmbeddingService.get_stats()
        logger.info(f"  Total embeddings: {stats['total_embeddings']}")
        logger.info(f"  Active embeddings: {stats['active_embeddings']}")
        logger.info(f"  Inactive embeddings: {stats['inactive_embeddings']}")
        
        logger.info("\n" + "="*70)
        logger.info("✓ All tests passed!")
        logger.info("="*70 + "\n")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Test failed: {e}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)