#!/usr/bin/env python3
"""Check for inactive embeddings in PostgreSQL"""
import sys
from pathlib import Path
from sqlalchemy.orm import Session

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import SessionLocal, Embedding
import logging

logger = logging.getLogger(__name__)

def check_inactive_embeddings():
    """Check and report inactive embeddings"""
    db = SessionLocal()
    try:
        # Get all inactive embeddings
        active = db.query(Embedding).filter(Embedding.is_active == True).all()
        
        if not active:
            print("✓ No active embeddings found")
            return
        
        print(f"\n✗ Found {len(active)} active embeddings:\n")
        
        # Group by source type
        by_source = {}
        for emb in active:
            if emb.source_type not in by_source:
                by_source[emb.source_type] = []
            by_source[emb.source_type].append(emb)
        
        # Print by source type
        for source_type, embeddings in sorted(by_source.items()):
            print(f"{source_type.upper()}: {len(embeddings)} inactive")
            for emb in embeddings[:3]:  # Show first 3
                print(f"  ID: {emb.id}")
                print(f"  Ticket: {emb.ticket_id}")
                print(f"  Deprecated: {emb.deprecated_at}")
                print(f"  Reason: {emb.deprecation_reason}")
                if emb.attachment_id:
                    print(f"  Attachment: {emb.attachment_id}")
                print()
            if len(embeddings) > 3:
                print(f"  ... and {len(embeddings) - 3} more\n")
        
        # Summary statistics
        print("\n=== SUMMARY ===")
        print(f"Total inactive: {len(active)}")
        for source_type, count in sorted([(s, len(e)) for s, e in by_source.items()]):
            print(f"  {source_type}: {count}")
            
    except Exception as e:
        logger.error(f"Error checking inactive embeddings: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_inactive_embeddings()