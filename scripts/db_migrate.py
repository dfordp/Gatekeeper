#!/usr/bin/env python3
"""
Database Migration Script for Gatekeeper Support Platform
...
"""

import os
import sys
import logging
import argparse
import uuid

# Add current directory to path so we can import database module
sys.path.insert(0, os.path.dirname(__file__))

# Add parent directory for dotenv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database import (
    engine, Base, init_db, drop_all_tables, test_connection,
    Company, User, Ticket, TicketEvent, Attachment, AttachmentEvent, Embedding
)
from database import SessionLocal
from sqlalchemy import text

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_header(text):
    """Print formatted header."""
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70 + "\n")


def verify_schema():
    """Verify all tables exist and have correct structure."""
    logger.info("Verifying schema...")
    
    with engine.connect() as conn:
        # Get list of tables
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """))
        
        tables = [row[0] for row in result.fetchall()]
        logger.info(f"Found {len(tables)} tables: {', '.join(tables)}")
        
        expected_tables = [
            'company', 'user', 'ticket', 'ticket_event',
            'attachment', 'attachment_event', 'embedding'
        ]
        
        missing = set(expected_tables) - set(tables)
        if missing:
            logger.error(f"✗ Missing tables: {missing}")
            return False
        
        logger.info("✓ All required tables exist")
        
        # Verify some column structure
        for table_name in expected_tables:
            result = conn.execute(text(f"""
                SELECT column_name, data_type FROM information_schema.columns
                WHERE table_name = '{table_name}'
                ORDER BY ordinal_position;
            """))
            
            columns = [row[0] for row in result.fetchall()]
            logger.debug(f"  {table_name}: {len(columns)} columns")
        
        return True


def seed_test_data():
    """Seed initial test data."""
    logger.info("Seeding test data...")
    
    db = SessionLocal()
    
    try:
        # Check if data already exists
        existing_companies = db.query(Company).count()
        if existing_companies > 0:
            logger.info("✓ Test data already exists, skipping seed")
            return
        
        # Create test company
        company = Company(
            id=uuid.uuid4(),
            name="Acme Corporation"
        )
        db.add(company)
        db.flush()
        logger.info(f"  Created company: {company.name}")
        
        # Create test users
        admin = User(
            id=uuid.uuid4(),
            name="Admin User",
            email="admin@acme.com",
            phone_number="+1-555-0100",
            role="admin",
            company_id=company.id
        )
        db.add(admin)
        db.flush()
        logger.info(f"  Created admin user: {admin.email}")
        
        engineer = User(
            id=uuid.uuid4(),
            name="Support Engineer",
            email="engineer@acme.com",
            phone_number="+1-555-0101",
            role="engineer",
            company_id=company.id
        )
        db.add(engineer)
        db.flush()
        logger.info(f"  Created engineer user: {engineer.email}")
        
        customer = User(
            id=uuid.uuid4(),
            name="John Customer",
            email="john@acme.com",
            phone_number="+1-555-0102",
            role="customer",
            company_id=company.id
        )
        db.add(customer)
        db.flush()
        logger.info(f"  Created customer user: {customer.email}")
        
        # Create test ticket
        ticket = Ticket(
            id=uuid.uuid4(),
            ticket_no="TKT-00001",
            subject="Cannot save files in Creo",
            summary="User unable to save designs after system update",
            detailed_description="""
            After upgrading to Creo 11.0, users are unable to save their design files.
            Error message: "Disk I/O error - cache path invalid"
            
            Environment: Production
            Impact: Completely blocked - users cannot work
            
            Steps to reproduce:
            1. Open existing part file
            2. Make any modification
            3. Press Ctrl+S to save
            4. Error appears
            """,
            category="Upload or Save",
            level="critical",
            company_id=company.id,
            raised_by_user_id=customer.id,
            assigned_engineer_id=engineer.id,
            status="open"
        )
        db.add(ticket)
        db.flush()
        logger.info(f"  Created ticket: {ticket.ticket_no}")
        
        # Create ticket creation event
        event = TicketEvent(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            event_type="created",
            actor_user_id=customer.id,
            payload={
                "subject": ticket.subject,
                "summary": ticket.summary,
                "category": ticket.category
            }
        )
        db.add(event)
        db.flush()
        logger.info(f"  Created ticket event: created")
        
        # Create test attachment
        attachment = Attachment(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            type="rca",
            file_path="uploads/TKT-00001/creo_cache_fix_rca.pdf",
            mime_type="application/pdf"
        )
        db.add(attachment)
        db.flush()
        logger.info(f"  Created attachment: rca")
        
        # Create attachment event
        att_event = AttachmentEvent(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            attachment_id=attachment.id,
            event_type="attachment_added",
            actor_user_id=engineer.id,
            payload={"file_name": "creo_cache_fix_rca.pdf"}
        )
        db.add(att_event)
        
        db.commit()
        logger.info("✓ Test data seeded successfully")
        
    except Exception as e:
        db.rollback()
        logger.error(f"✗ Failed to seed test data: {e}")
        raise
    finally:
        db.close()


def show_schema_summary():
    """Show summary of created schema."""
    print_header("SCHEMA SUMMARY")
    
    summary = """
    Tables Created:
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    1. company
       - Stores company/organization data
       - Columns: id, name, created_at
       - Relationships: users, tickets, embeddings
    
    2. user
       - Stores user information (customers, engineers, admins)
       - Columns: id, name, email, phone_number, role, company_id, created_at
       - Indexes: company_id
    
    3. ticket
       - Main support ticket data (immutable facts)
       - Columns: id, ticket_no, status, level, category, subject, summary,
                  detailed_description, company_id, raised_by_user_id,
                  assigned_engineer_id, created_at, closed_at, reopened_at
       - Indexes: company_id, status, created_at
    
    4. ticket_event
       - Event log for ticket changes (immutable)
       - Columns: id, ticket_id, event_type, actor_user_id, payload, created_at
       - Types: created, status_changed, assignment_changed, comment_added,
                resolution_added, reopened, auto_resolved
       - Indexes: ticket_id, event_type, created_at
    
    5. attachment
       - File attachments (RCA, logs, images, documents)
       - Columns: id, ticket_id, type, file_path, mime_type, created_at
       - Types: image, document, log, rca
       - Indexes: ticket_id, type
    
    6. attachment_event
       - Event log for attachment changes
       - Columns: id, ticket_id, attachment_id, event_type, actor_user_id,
                  payload, created_at
       - Types: attachment_added, attachment_replaced, attachment_removed,
                attachment_promoted, attachment_deprecated
       - Indexes: ticket_id, attachment_id, event_type
    
    7. embedding
       - Vector embeddings for semantic search
       - Columns: id, company_id, ticket_id, attachment_id, source_type,
                  chunk_index, text_content, vector_id, is_active, created_at,
                  deprecated_at, deprecation_reason
       - Types: ticket_summary, ticket_description, resolution, rca, log_snippet
       - Indexes: (company_id, is_active), ticket_id, attachment_id, created_at
    
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    Key Design Decisions:
    ✓ Tickets and attachments are immutable (only events track changes)
    ✓ Embeddings use soft-delete (is_active flag, not hard delete)
    ✓ All timestamps use UTC
    ✓ Company isolation via company_id field
    ✓ JSONB payloads for flexible event data
    
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """
    print(summary)


def main():
    """Main migration entry point."""
    parser = argparse.ArgumentParser(
        description="Database migration script for Gatekeeper Support Platform"
    )
    parser.add_argument(
        '--seed',
        action='store_true',
        help='Seed database with test data'
    )
    parser.add_argument(
        '--drop',
        action='store_true',
        help='Drop all tables (DANGEROUS!)'
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='Check schema only, do not create'
    )
    
    args = parser.parse_args()
    
    print_header("GATEKEEPER DATABASE MIGRATION")
    
    # Test connection
    if not test_connection():
        logger.error("✗ Failed to connect to database. Exiting.")
        sys.exit(1)
    
    # Check if we should drop tables
    if args.drop:
        confirm = input("\n⚠ WARNING: This will DELETE all tables and data!\n")
        confirm += input("Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            logger.info("Migration cancelled.")
            sys.exit(0)
        drop_all_tables()
    
    # Check mode only
    if args.check:
        if verify_schema():
            logger.info("✓ Schema is valid")
        else:
            logger.warning("⚠ Schema is incomplete")
        sys.exit(0)
    
    # Run migrations
    try:
        init_db()
        
        # Verify schema
        if verify_schema():
            logger.info("✓ Migration completed successfully")
        else:
            logger.warning("⚠ Migration completed but schema verification failed")
            sys.exit(1)
        
        # Seed data if requested
        if args.seed:
            seed_test_data()
        
        # Show summary
        show_schema_summary()
        
        logger.info("\n✓ All done! Database is ready.\n")
        
    except Exception as e:
        logger.error(f"✗ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()