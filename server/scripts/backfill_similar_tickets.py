#!/usr/bin/env python3
"""
Backfill Similar Tickets Mapping

Maps similarity relationships for all existing tickets in the database.
This script:
1. Gets all tickets ordered by creation date
2. Ensures embeddings exist for each ticket
3. Maps similar tickets using the embedding manager
"""

from pathlib import Path
import sys
import logging
from datetime import datetime

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import SessionLocal, Ticket, Embedding
from services.embedding_manager import EmbeddingManager
from core.logger import get_logger

logger = get_logger(__name__)


def backfill_similar_tickets(company_id: str = None, limit: int = None):
    """
    Backfill similarity mappings for existing tickets.
    
    Args:
        company_id: Optional company UUID to limit backfill to one company
        limit: Optional limit on number of tickets to process
    """
    db = SessionLocal()
    try:
        # Get all tickets ordered by creation date
        query = db.query(Ticket)
        
        if company_id:
            query = query.filter(Ticket.company_id == company_id)
            logger.info(f"Backfilling tickets for company: {company_id}")
        else:
            logger.info("Backfilling tickets for ALL companies")
        
        tickets = query.order_by(Ticket.created_at.asc()).all()
        
        if limit:
            tickets = tickets[:limit]
        
        total = len(tickets)
        logger.info(f"Found {total} tickets to process")
        
        processed = 0
        skipped = 0
        error_count = 0
        
        for idx, ticket in enumerate(tickets, 1):
            try:
                logger.info(f"[{idx}/{total}] Processing ticket {ticket.ticket_no}...")
                
                # Check if embeddings exist for this ticket
                embeddings = db.query(Embedding).filter(
                    Embedding.ticket_id == ticket.id,
                    Embedding.is_active == True
                ).count()
                
                if embeddings == 0:
                    logger.debug(f"  → No active embeddings found, skipping (embeddings must exist first)")
                    skipped += 1
                    continue
                
                # Map similar tickets
                success = EmbeddingManager._find_and_map_similar_tickets(
                    ticket_id=str(ticket.id),
                    company_id=str(ticket.company_id)
                )
                
                if success:
                    logger.info(f"  ✓ Mapped similar tickets for {ticket.ticket_no}")
                    processed += 1
                else:
                    logger.warning(f"  ✗ Failed to map similar tickets for {ticket.ticket_no}")
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"  ✗ Error processing ticket {ticket.ticket_no}: {e}")
                error_count += 1
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Backfill Complete!")
        logger.info(f"  Processed: {processed}")
        logger.info(f"  Skipped: {skipped}")
        logger.info(f"  Errors: {error_count}")
        logger.info(f"{'='*60}")
        
        return processed, skipped, error_count
        
    except Exception as e:
        logger.error(f"Fatal error during backfill: {e}")
        return 0, 0, 1
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Backfill similar tickets mapping")
    parser.add_argument(
        "--company-id",
        type=str,
        help="Optional company UUID to limit backfill to one company"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional limit on number of tickets to process"
    )
    
    args = parser.parse_args()
    
    processed, skipped, errors = backfill_similar_tickets(
        company_id=args.company_id,
        limit=args.limit
    )
    
    sys.exit(0 if errors == 0 else 1)
