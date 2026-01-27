#!/usr/bin/env python3
"""
Test script for search service.

Usage:
    python scripts/test_search_service.py
"""

import os
import sys
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, Ticket, Company
from search_service import SearchService
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run search service tests."""
    
    logger.info("\n" + "="*70)
    logger.info("  SEARCH SERVICE TEST")
    logger.info("="*70 + "\n")
    
    db = SessionLocal()
    
    try:
        # Test 1: Find test company and ticket
        logger.info("Test 1: Find test data")
        company = db.query(Company).first()
        if not company:
            logger.error("✗ No company found. Run migration with --seed first.")
            return False
        
        logger.info(f"  ✓ Found company: {company.name}")
        
        ticket = db.query(Ticket).filter(Ticket.company_id == company.id).first()
        if not ticket:
            logger.error("✗ No tickets found in company.")
            return False
        
        logger.info(f"  ✓ Found ticket: {ticket.ticket_no} - {ticket.subject}")
        
        # Test 2: Get company stats
        logger.info("\nTest 2: Company search statistics")
        stats = SearchService.get_company_search_stats(str(company.id))
        logger.info(f"  Company: {stats['company_id']}")
        logger.info(f"  Tickets: {stats['tickets']['total']} total, {stats['tickets']['resolved']} resolved")
        logger.info(f"  Embeddings: {stats['embeddings']['total']} total, {stats['embeddings']['active']} active")
        logger.info(f"  Search potential: {stats['search_potential']}")
        
        # Test 3: Test similarity search with similar query
        logger.info("\nTest 3: Search with similar query")
        similar_query = "I cannot save files in Creo design software"
        result = SearchService.search_similar_solutions(
            query_text=similar_query,
            company_id=str(company.id),
            category="Upload or Save"
        )
        
        logger.info(f"  Query: '{similar_query}'")
        logger.info(f"  Status: {result.get('status')}")
        logger.info(f"  Confidence: {result.get('confidence', 0):.3f}")
        logger.info(f"  Threshold: {result.get('threshold', 0):.2f}")
        
        if result.get("status") == "solution_found":
            ticket_info = result.get("ticket", {})
            logger.info(f"  ✓ Found solution: {ticket_info.get('ticket_no')}")
            logger.info(f"    Subject: {ticket_info.get('subject')}")
            logger.info(f"    Status: {ticket_info.get('status')}")
            
            if result.get("resolution"):
                resolution = result.get("resolution", "")
                logger.info(f"    Resolution: {resolution[:100]}...")
            
            similar = result.get("similar_matches", [])
            if similar:
                logger.info(f"    Similar matches: {len(similar)}")
        else:
            logger.info(f"  Message: {result.get('message', 'Unknown')}")
        
        # Test 4: Should create new ticket?
        logger.info("\nTest 4: Deduplication decision")
        should_create = SearchService.should_create_new_ticket(
            query_text=similar_query,
            company_id=str(company.id)
        )
        logger.info(f"  Query: '{similar_query}'")
        logger.info(f"  Should create new ticket: {should_create}")
        
        # Test 5: Test dissimilar query
        logger.info("\nTest 5: Search with dissimilar query")
        dissimilar_query = "How do I configure QWERTY keyboard settings in Windows?"
        result = SearchService.search_similar_solutions(
            query_text=dissimilar_query,
            company_id=str(company.id)
        )
        
        logger.info(f"  Query: '{dissimilar_query}'")
        logger.info(f"  Status: {result.get('status')}")
        logger.info(f"  Confidence: {result.get('confidence', 0):.3f}")
        
        should_create = SearchService.should_create_new_ticket(
            query_text=dissimilar_query,
            company_id=str(company.id)
        )
        logger.info(f"  Should create new ticket: {should_create}")
        
        # Test 6: Get ticket with embeddings
        logger.info("\nTest 6: Get ticket details with embeddings")
        ticket_details = SearchService.get_ticket_with_embeddings(str(ticket.id))
        
        if "error" not in ticket_details:
            logger.info(f"  Ticket: {ticket_details['ticket']['ticket_no']}")
            embeddings = ticket_details.get('embeddings', {})
            logger.info(f"  Embeddings: {embeddings.get('total', 0)} total, {embeddings.get('active', 0)} active")
            events = ticket_details.get('events', [])
            logger.info(f"  Events: {len(events)} total")
        
        logger.info("\n" + "="*70)
        logger.info("✓ All tests passed!")
        logger.info("="*70 + "\n")
        
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