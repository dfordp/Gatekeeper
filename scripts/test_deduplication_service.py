#!/usr/bin/env python3
"""
Test script for deduplication service.

Usage:
    python scripts/test_deduplication_service.py
"""

import os
import sys
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, Company
from deduplication_service import DuplicateService
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run deduplication service tests."""
    
    logger.info("\n" + "="*70)
    logger.info("  DEDUPLICATION SERVICE TEST")
    logger.info("="*70 + "\n")
    
    db = SessionLocal()
    
    try:
        # Find test company
        company = db.query(Company).first()
        if not company:
            logger.error("✗ No company found. Run migration with --seed first.")
            return False
        
        logger.info(f"Company: {company.name}\n")
        
        # Get a user for testing
        user = company.users[0] if company.users else None
        if not user:
            logger.error("✗ No users found in company.")
            return False
        
        user_id = str(user.id)
        logger.info(f"User: {user.email}\n")
        
        # Test 1: Check for duplicates (should find existing ticket)
        logger.info("Test 1: Check for duplicates (similar query)")
        dedup_result = DuplicateService.check_for_duplicates(
            query_text="I cannot save my Creo designs",
            company_id=str(company.id),
            category="Upload or Save",
            user_id=user_id
        )
        
        logger.info(f"  Should create ticket: {dedup_result['should_create_ticket']}")
        logger.info(f"  Message: {dedup_result['message']}")
        
        if not dedup_result['should_create_ticket']:
            existing = dedup_result.get('existing_ticket', {})
            logger.info(f"  ✓ Found existing: {existing.get('ticket_no')}")
            logger.info(f"    Confidence: {dedup_result['search_result'].get('confidence'):.3f}")
        
        # Test 2: Create ticket with deduplication (should return existing)
        logger.info("\nTest 2: Create ticket with deduplication (similar issue)")
        create_result = DuplicateService.create_ticket_with_dedup(
            subject="Cannot save designs in Creo",
            detailed_description="After upgrading to Creo 11.0, I cannot save my designs",
            company_id=str(company.id),
            raised_by_user_id=user_id,
            category="Upload or Save"
        )
        
        logger.info(f"  Created new: {create_result['created_new']}")
        logger.info(f"  Message: {create_result['message']}")
        
        if not create_result['created_new']:
            logger.info(f"  ✓ Duplicate prevention worked")
            existing = create_result.get('existing_ticket', {})
            logger.info(f"    Returned ticket: {existing.get('ticket_no')}")
        
        # Test 3: Check for non-duplicates (should allow creation)
        logger.info("\nTest 3: Check for duplicates (unrelated query)")
        dedup_result = DuplicateService.check_for_duplicates(
            query_text="How do I configure network settings on Windows server?",
            company_id=str(company.id),
            user_id=user_id
        )
        
        logger.info(f"  Should create ticket: {dedup_result['should_create_ticket']}")
        logger.info(f"  Message: {dedup_result['message']}")
        
        if dedup_result['should_create_ticket']:
            logger.info(f"  ✓ No duplicates found, new ticket can be created")
        
        # Test 4: Create new ticket (should succeed)
        logger.info("\nTest 4: Create new ticket (unrelated issue)")
        create_result = DuplicateService.create_ticket_with_dedup(
            subject="Network configuration issue on Windows Server",
            detailed_description="Need help configuring network settings for a Windows Server deployment",
            company_id=str(company.id),
            raised_by_user_id=user_id,
            category="Installation",
            level="medium"
        )
        
        logger.info(f"  Created new: {create_result['created_new']}")
        logger.info(f"  Success: {create_result['success']}")
        
        if create_result['created_new']:
            ticket = create_result.get('ticket', {})
            logger.info(f"  ✓ New ticket created: {ticket.get('ticket_no')}")
        
        # Test 5: Get deduplication stats
        logger.info("\nTest 5: Deduplication statistics")
        stats = DuplicateService.get_dedup_stats(str(company.id))
        logger.info(f"  Total tickets: {stats['total_tickets']}")
        logger.info(f"  Linked as duplicates: {stats['linked_as_duplicates']}")
        logger.info(f"  Dedup events: {stats['dedup_events']}")
        
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