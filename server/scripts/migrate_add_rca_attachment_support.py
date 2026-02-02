# server/scripts/migrate_add_rca_attachment_support.py
"""
Migration script to add RCA attachment support.

This script:
1. Adds rca_attachment table (if not exists)
2. Adds rca_attachment_id column to embedding table (if not exists)
3. Adds index for rca_attachment_id foreign key

Usage:
    python server/scripts/migrate_add_rca_attachment_support.py
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text, inspect
from core.database import engine, SessionLocal, Base, RCAAttachment
from core.logger import get_logger

logger = get_logger(__name__)

def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def table_exists(table_name: str) -> bool:
    """Check if a table exists"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def migrate():
    """Run the migration"""
    print("\n" + "=" * 80)
    print("MIGRATION: Add RCA Attachment Support")
    print("=" * 80 + "\n")
    
    db = SessionLocal()
    
    try:
        # Step 1: Create rca_attachment table if it doesn't exist
        if not table_exists("rca_attachment"):
            print("📌 Creating 'rca_attachment' table...")
            RCAAttachment.__table__.create(engine, checkfirst=True)
            print("✓ Created 'rca_attachment' table\n")
        else:
            print("✓ Table 'rca_attachment' already exists\n")
        
        # Step 2: Add rca_attachment_id column to embedding table
        if not column_exists("embedding", "rca_attachment_id"):
            print("📌 Adding 'rca_attachment_id' column to 'embedding' table...")
            with engine.connect() as conn:
                # Add column without foreign key first
                conn.execute(
                    text("""
                    ALTER TABLE embedding 
                    ADD COLUMN rca_attachment_id UUID
                    """)
                )
                conn.commit()
                print("✓ Added 'rca_attachment_id' column")
                
                # Add foreign key constraint
                print("📌 Adding foreign key constraint...")
                conn.execute(
                    text("""
                    ALTER TABLE embedding 
                    ADD CONSTRAINT fk_embedding_rca_attachment 
                    FOREIGN KEY (rca_attachment_id) 
                    REFERENCES rca_attachment(id) ON DELETE CASCADE
                    """)
                )
                conn.commit()
                print("✓ Added foreign key constraint\n")
        else:
            print("✓ Column 'rca_attachment_id' already exists\n")
        
        # Step 3: Create indexes if they don't exist
        print("📌 Creating indexes...")
        with engine.connect() as conn:
            # Check and create index on rca_attachment_id
            result = conn.execute(
                text("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename='embedding' AND indexname='idx_embedding_rca_attachment'
                """)
            ).fetchone()
            
            if not result:
                conn.execute(
                    text("""
                    CREATE INDEX idx_embedding_rca_attachment 
                    ON embedding(rca_attachment_id)
                    """)
                )
                conn.commit()
                print("✓ Created index 'idx_embedding_rca_attachment'")
            else:
                print("✓ Index 'idx_embedding_rca_attachment' already exists")
        
        print("\n" + "=" * 80)
        print("✓ Migration completed successfully!")
        print("=" * 80 + "\n")
        return True
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        print("=" * 80 + "\n")
        logger.error(f"Migration error: {e}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)