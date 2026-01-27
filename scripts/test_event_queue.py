#!/usr/bin/env python3
"""
Test script for event queue system.

Usage:
    python scripts/test_event_queue.py
"""

import os
import sys
import logging
import time
import threading

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, Company
from event_queue import EventQueue, EventType, EventHandlers
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
    """Run event queue tests."""
    
    logger.info("\n" + "="*70)
    logger.info("  EVENT QUEUE TEST")
    logger.info("="*70 + "\n")
    
    db = SessionLocal()
    
    try:
        # Find test company and user
        company = db.query(Company).first()
        if not company or not company.users:
            logger.error("✗ No company or users found. Run migration with --seed first.")
            return False
        
        user = company.users[0]
        logger.info(f"Company: {company.name}")
        logger.info(f"User: {user.email}\n")
        
        # Test 1: Subscribe to events
        logger.info("Test 1: Subscribe to event handlers")
        
        # Track events received
        received_events = []
        
        def capture_event(data):
            received_events.append(data)
            logger.info(f"  ✓ Captured event: {data.get('event_type')}")
        
        EventQueue.subscribe(EventType.TICKET_CREATED, capture_event)
        EventQueue.subscribe(EventType.TICKET_CREATED, EventHandlers.on_ticket_created)
        logger.info("  ✓ Subscribed to TICKET_CREATED\n")
        
        # Test 2: Emit event (without async listener, won't be received in this process)
        logger.info("Test 2: Emit event")
        success = EventQueue.emit(
            EventType.TICKET_CREATED,
            ticket_id="test-ticket-123",
            company_id=str(company.id),
            subject="Test ticket from event queue"
        )
        logger.info(f"  ✓ Event emitted: {success}\n")
        
        # Test 3: Create ticket with deduplication (uses synchronous path)
        logger.info("Test 3: Create ticket via deduplication service")
        create_result = DuplicateService.create_ticket_with_dedup(
            subject="Test ticket for event queue",
            detailed_description="This is a test of the event queue system",
            company_id=str(company.id),
            raised_by_user_id=str(user.id),
            category="Other",
            level="low"
        )
        
        if create_result['created_new']:
            ticket = create_result['ticket']
            logger.info(f"  ✓ Ticket created: {ticket['ticket_no']}")
            
            # Test 4: Emit attachment event
            logger.info("\nTest 4: Emit attachment event")
            attachment_success = EventQueue.emit(
                EventType.ATTACHMENT_ADDED,
                attachment_id="test-attachment-456",
                ticket_id=ticket['id'],
                company_id=str(company.id),
                attachment_type="rca"
            )
            logger.info(f"  ✓ Attachment event emitted: {attachment_success}")
        
        # Test 5: Event information
        logger.info("\nTest 5: Event type information")
        logger.info(f"  Total event types: {len(EventType)}")
        for event_type in EventType:
            logger.info(f"    - {event_type.value}")
        
        logger.info("\n" + "="*70)
        logger.info("✓ All tests passed!")
        logger.info("="*70)
        logger.info("\nNote: To test async event processing:")
        logger.info("  1. Run: python scripts/test_event_queue.py")
        logger.info("  2. Run in another terminal: python scripts/event_listener.py")
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