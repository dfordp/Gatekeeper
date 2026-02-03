# server/scripts/migrate_add_ir_support.py
"""
Migration script to add Incident Report (IR) support to the database.

This script:
1. Adds IR-related columns to the ticket table
2. Creates the incident_report table
3. Creates the ir_event table
4. Adds necessary indexes

Usage:
    python server/scripts/migrate_add_ir_support.py
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text, inspect
from core.database import engine, SessionLocal, Base, IncidentReport, IREvent
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
    print("MIGRATION: Add Incident Report (IR) Support")
    print("=" * 80 + "\n")
    
    db = SessionLocal()
    
    try:
        # Step 1: Add IR columns to ticket table
        print("📌 Adding IR columns to 'ticket' table...")
        
        ir_columns = [
            ("has_ir", "BOOLEAN NOT NULL DEFAULT false"),
            ("ir_number", "VARCHAR(100) UNIQUE"),
            ("ir_raised_at", "TIMESTAMP"),
            ("ir_expected_resolution_date", "TIMESTAMP"),
            ("ir_notes", "TEXT"),
            ("ir_closed_at", "TIMESTAMP"),
        ]
        
        for col_name, col_def in ir_columns:
            if not column_exists("ticket", col_name):
                print(f"  ✓ Adding column: {col_name}")
                db.execute(text(f"ALTER TABLE ticket ADD COLUMN {col_name} {col_def}"))
            else:
                print(f"  ⊘ Column '{col_name}' already exists, skipping")
        
        db.commit()
        
        # Step 2: Create incident_report table
        if not table_exists("incident_report"):
            print("📌 Creating 'incident_report' table...")
            IncidentReport.__table__.create(engine, checkfirst=True)
            print("  ✓ Table created")
        else:
            print("  ⊘ Table 'incident_report' already exists, skipping")
        
        # Step 3: Create ir_event table
        if not table_exists("ir_event"):
            print("📌 Creating 'ir_event' table...")
            IREvent.__table__.create(engine, checkfirst=True)
            print("  ✓ Table created")
        else:
            print("  ⊘ Table 'ir_event' already exists, skipping")
        
        # Step 4: Add indexes to ticket table for IR columns
        print("📌 Adding indexes to 'ticket' table for IR columns...")
        
        indexes_to_add = [
            ("idx_ticket_has_ir", "has_ir"),
            ("idx_ticket_ir_raised_at", "ir_raised_at"),
        ]
        
        inspector = inspect(engine)
        existing_indexes = [idx['name'] for idx in inspector.get_indexes("ticket")]
        
        for idx_name, col_name in indexes_to_add:
            if idx_name not in existing_indexes:
                print(f"  ✓ Creating index: {idx_name}")
                db.execute(text(f"CREATE INDEX {idx_name} ON ticket ({col_name})"))
            else:
                print(f"  ⊘ Index '{idx_name}' already exists, skipping")
        
        db.commit()
        
        print("\n" + "=" * 80)
        print("✅ Migration completed successfully!")
        print("=" * 80 + "\n")
        
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed: {e}")
        print(f"\n❌ Migration failed: {e}\n")
        return False
    
    finally:
        db.close()

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)