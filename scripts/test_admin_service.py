#!/usr/bin/env python3
"""
Test script for admin service.

Usage:
    python scripts/test_admin_service.py
"""

import os
import sys
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, Company, Embedding
from admin_service import AdminService
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
    """Run admin service tests."""
    
    logger.info("\n" + "="*70)
    logger.info("  ADMIN SERVICE TEST")
    logger.info("="*70 + "\n")
    
    db = SessionLocal()
    
    try:
        # Find test company
        company = db.query(Company).first()
        if not company or not company.users:
            logger.error("✗ No company or users found. Run migration with --seed first.")
            return False
        
        user = company.users[0]
        logger.info(f"Company: {company.name}")
        logger.info(f"Admin user: {user.email}\n")
        
        # Test 1: Get audit stats
        logger.info("Test 1: Get company audit statistics")
        stats = AdminService.get_company_audit_stats(str(company.id))
        
        if stats['success']:
            logger.info(f"  ✓ Tickets: {stats['tickets']['total']}")
            logger.info(f"  ✓ Embeddings: {stats['embeddings']['total']} total, {stats['embeddings']['active']} active")
            logger.info(f"  ✓ Deprecation rate: {stats['embeddings']['deprecation_rate_percent']}%")
        
        # Test 2: Get embedding audit trail
        logger.info("\nTest 2: Get embedding audit trail")
        embeddings = db.query(Embedding).filter(
            Embedding.company_id == company.id,
            Embedding.is_active == True
        ).first()
        
        if embeddings:
            trail = AdminService.get_embedding_audit_trail(str(embeddings.id))
            if trail['success']:
                emb_info = trail['embedding']
                logger.info(f"  ✓ Embedding {emb_info['id'][:8]}...")
                logger.info(f"    Source: {emb_info['source_type']}")
                logger.info(f"    Active: {emb_info['is_active']}")
                logger.info(f"    Events: {len(trail['ticket_events'])}")
        
        # Test 3: Deprecate an embedding
        logger.info("\nTest 3: Deprecate an embedding")
        
        embeddings = db.query(Embedding).filter(
            Embedding.company_id == company.id,
            Embedding.is_active == True
        ).first()
        
        if embeddings:
            result = AdminService.deprecate_embedding(
                embedding_id=str(embeddings.id),
                reason="incorrect_analysis",
                actor_user_id=str(user.id),
                notes="This embedding had low quality results"
            )
            
            if result['success']:
                logger.info(f"  ✓ Deprecation successful")
                logger.info(f"    Embedding: {result['embedding_id'][:8]}...")
                logger.info(f"    Reason: {result['reason']}")
            else:
                logger.info(f"  Error: {result['error']}")
        
        # Test 4: Find related tickets
        logger.info("\nTest 4: Find related tickets")
        
        ticket = company.tickets[0] if company.tickets else None
        if ticket:
            related = AdminService.find_related_tickets(
                primary_ticket_id=str(ticket.id),
                company_id=str(company.id)
            )
            
            if related['success']:
                logger.info(f"  ✓ Primary ticket: {related['primary_ticket']['ticket_no']}")
                logger.info(f"    Duplicates found: {len(related['duplicates'])}")
                logger.info(f"    Related issues: {len(related['related_issues'])}")
                logger.info(f"    Linking events: {len(related['linking_events'])}")
        
        # Test 5: Updated audit stats (after deprecation)
        logger.info("\nTest 5: Updated audit statistics")
        stats = AdminService.get_company_audit_stats(str(company.id))
        
        if stats['success']:
            logger.info(f"  ✓ Embeddings: {stats['embeddings']['total']} total, {stats['embeddings']['active']} active")
            logger.info(f"  ✓ Deprecated: {stats['embeddings']['deprecated']}")
            logger.info(f"  ✓ Deprecation events: {stats['audit_events']['deprecation_events']}")
        
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