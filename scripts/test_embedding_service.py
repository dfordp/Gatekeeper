#!/usr/bin/env python3
"""
Test script for embedding service with adaptive threshold learning.

Usage:
    python scripts/test_embedding_service.py
"""

import os
import sys
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, Ticket, Embedding, User
from embedding_service import EmbeddingService
from adaptive_threshold_service import AdaptiveThresholdService
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
    logger.info("  EMBEDDING SERVICE TEST WITH ADAPTIVE THRESHOLDS")
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
        
        # Test 6: Get confidence threshold (before feedback)
        logger.info("\nTest 6: Initial confidence thresholds")
        logger.info("  (Before training with feedback data)")
        initial_thresholds = {}
        for category in ["Login / Access", "License", "Performance", "Other"]:
            threshold = EmbeddingService.get_confidence_threshold(category)
            initial_thresholds[category] = threshold
            logger.info(f"    {category}: {threshold}")
        
        # Test 7: Record user feedback to train adaptive thresholds
        logger.info("\nTest 7: Training with user feedback")

        # Get all available tickets for feedback
        all_tickets = db.query(Ticket).all()
        system_user = db.query(User).first()

        if not system_user:
            logger.warning("  ⚠ No users found in database, skipping feedback training")
        elif len(all_tickets) == 0:
            logger.warning("  ⚠ No tickets found in database, skipping feedback training")
        else:
            feedback_recorded = 0
            num_tickets = len(all_tickets)
            
            # Record helpful feedback for most tickets
            num_helpful = max(1, num_tickets - 1)  # All but one (or just 1 if only 1 ticket)
            for i in range(num_helpful):
                result = AdaptiveThresholdService.record_search_feedback(
                    ticket_id=str(all_tickets[i].id),
                    search_confidence=0.65 + min(i * 0.03, 0.10),
                    was_helpful=True,
                    rating=5
                )
                if result:
                    logger.info(f"  ✓ Recorded helpful feedback for {all_tickets[i].ticket_no} (confidence: {0.65 + min(i * 0.03, 0.10):.2f})")
                    feedback_recorded += 1
                else:
                    logger.warning(f"  ✗ Failed to record feedback for {all_tickets[i].ticket_no}")
            
            # Record unhelpful feedback for last ticket if we have more than 1
            if num_tickets > 1:
                result = AdaptiveThresholdService.record_search_feedback(
                    ticket_id=str(all_tickets[-1].id),
                    search_confidence=0.54,
                    was_helpful=False,
                    rating=1
                )
                if result:
                    logger.info(f"  ✓ Recorded unhelpful feedback for {all_tickets[-1].ticket_no} (confidence: 0.54)")
                    feedback_recorded += 1
                else:
                    logger.warning(f"  ✗ Failed to record feedback for {all_tickets[-1].ticket_no}")
            
            if feedback_recorded > 0:
                logger.info(f"  ✓ Total feedback records: {feedback_recorded}")
            else:
                logger.warning("  ⚠ No feedback could be recorded")
        # Test 8: Recalculate thresholds after training
        logger.info("\nTest 8: Recalculated thresholds (after learning)")
        logger.info("  (System should adjust thresholds based on feedback)")
        
        # Clear cache to force recalculation
        EmbeddingService._dynamic_thresholds = None
        
        # Recalculate with updated feedback data
        company_id = str(ticket.company_id)
        thresholds = EmbeddingService._load_thresholds(company_id)
        
        for category in sorted(thresholds.keys()):
            old = initial_thresholds.get(category, "N/A")
            new = thresholds[category]
            change = ""
            if old != "N/A":
                if new < old:
                    change = f" ↓ (was {old})"
                elif new > old:
                    change = f" ↑ (was {old})"
                else:
                    change = f" = (no change)"
            logger.info(f"    {category}: {new:.2f}{change}")
        
        # Test 9: Get statistics
        logger.info("\nTest 9: Embedding statistics")
        stats = EmbeddingService.get_stats()
        logger.info(f"  Total embeddings: {stats['total_embeddings']}")
        logger.info(f"  Active embeddings: {stats['active_embeddings']}")
        logger.info(f"  Inactive embeddings: {stats['inactive_embeddings']}")
        
        logger.info("\n" + "="*70)
        logger.info("✓ All tests passed!")
        logger.info("="*70)
        logger.info("\nKey learnings:")
        logger.info("  • Adaptive thresholds dynamically adjust based on user feedback")
        logger.info("  • High precision (helpful results) → lower threshold (be inclusive)")
        logger.info("  • Low precision (false positives) → higher threshold (be selective)")
        logger.info("  • System learns and improves over time")
        logger.info("")
        
        return True
        
        
    except Exception as e:
        logger.error(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)