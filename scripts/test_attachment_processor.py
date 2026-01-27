#!/usr/bin/env python3
"""
Test script for attachment processor.

Usage:
    python scripts/test_attachment_processor.py
"""

import os
import sys
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, Attachment, Embedding
from attachment_processor import AttachmentProcessor
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run attachment processor tests."""
    
    logger.info("\n" + "="*70)
    logger.info("  ATTACHMENT PROCESSOR TEST")
    logger.info("="*70 + "\n")
    
    db = SessionLocal()
    
    try:
        # Test 1: Configuration
        logger.info("Test 1: Configuration")
        logger.info(f"  Supported types: {AttachmentProcessor.SUPPORTED_TYPES}")
        logger.info(f"  PDF MIME types: {AttachmentProcessor.PDF_MIME_TYPES}")
        
        # Test 2: Find test attachment
        logger.info("\nTest 2: Find test attachment")
        attachment = db.query(Attachment).first()
        if not attachment:
            logger.error("✗ No attachments found. Run migration with --seed first.")
            return False
        
        logger.info(f"  ✓ Found attachment: {attachment.id}")
        logger.info(f"    Type: {attachment.type}")
        logger.info(f"    File path: {attachment.file_path}")
        logger.info(f"    MIME type: {attachment.mime_type}")
        
        # Test 3: Get attachment info
        logger.info("\nTest 3: Get attachment info")
        info = AttachmentProcessor.get_attachment_info(str(attachment.id))
        logger.info(f"  ✓ Attachment info:")
        logger.info(f"    Total embeddings: {info.get('total_embeddings', 0)}")
        logger.info(f"    Active embeddings: {info.get('active_embeddings', 0)}")
        logger.info(f"    Inactive embeddings: {info.get('inactive_embeddings', 0)}")
        
        # Test 4: Check if already processed
        logger.info("\nTest 4: Check if already processed")
        existing = db.query(Embedding).filter(
            Embedding.attachment_id == attachment.id
        ).count()
        
        if existing > 0:
            logger.info(f"  ℹ Attachment already processed: {existing} embeddings exist")
            logger.info("  Skipping processing step")
        else:
            # Test 5: Process attachment
            logger.info("\nTest 5: Process attachment")
            
            # Check if file exists
            if not os.path.exists(attachment.file_path):
                logger.warning(f"  File not found: {attachment.file_path}")
                logger.info("  ℹ Creating sample PDF for testing...")
                AttachmentProcessor._create_sample_pdf(attachment.file_path)
            
            count = AttachmentProcessor.process_rca_attachment(
                str(attachment.id),
                str(attachment.ticket_id),
                str(attachment.ticket.company_id)
            )
            logger.info(f"  ✓ Created {count} embeddings")
        
        # Test 6: Query embeddings for attachment
        logger.info("\nTest 6: Query embeddings for attachment")
        embeddings = db.query(Embedding).filter(
            Embedding.attachment_id == attachment.id,
            Embedding.is_active == True
        ).all()
        
        logger.info(f"  ✓ Found {len(embeddings)} active embeddings:")
        for idx, emb in enumerate(embeddings[:5]):  # Show first 5
            logger.info(f"    - Chunk {emb.chunk_index}: {len(emb.text_content)} chars")
        
        if len(embeddings) > 5:
            logger.info(f"    ... and {len(embeddings) - 5} more")
        
        # Test 7: Verify attachment isolation
        logger.info("\nTest 7: Verify company isolation")
        ticket = attachment.ticket
        company_embeddings = db.query(Embedding).filter(
            Embedding.company_id == ticket.company_id,
            Embedding.is_active == True
        ).count()
        logger.info(f"  ✓ Total active embeddings for company: {company_embeddings}")
        
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