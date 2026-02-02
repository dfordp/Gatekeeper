# server/core/migrations.py
"""
Database migration helpers for adding new tables

This module provides utilities for creating new tables without resetting the database.
"""

import logging
from sqlalchemy import text
from core.database import engine, SessionLocal, Base
from core.logger import get_logger

logger = get_logger(__name__)


def create_queued_task_table():
    """Create queued_task table if it doesn't exist"""
    db = SessionLocal()
    try:
        # Check if table exists
        inspector_query = """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'queued_task'
        )
        """
        result = db.execute(text(inspector_query)).scalar()
        
        if result:
            logger.info("✓ queued_task table already exists")
            return True
        
        # Create table
        create_query = """
        CREATE TABLE queued_task (
            id UUID PRIMARY KEY,
            ticket_id UUID NOT NULL REFERENCES ticket(id) ON DELETE CASCADE,
            task_type VARCHAR(50) NOT NULL,
            status VARCHAR(50) NOT NULL,
            payload JSONB,
            error_message TEXT,
            retry_count INT DEFAULT 0,
            max_retries INT DEFAULT 3,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            INDEX idx_queued_task_ticket (ticket_id),
            INDEX idx_queued_task_status (status),
            INDEX idx_queued_task_type (task_type),
            INDEX idx_queued_task_created (created_at)
        )
        """
        
        db.execute(text(create_query))
        db.commit()
        logger.info("✓ Created queued_task table")
        return True
    
    except Exception as e:
        logger.error(f"Failed to create queued_task table: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def create_attachment_summary_table():
    """Create attachment_summary table if it doesn't exist"""
    db = SessionLocal()
    try:
        # Check if table exists
        inspector_query = """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'attachment_summary'
        )
        """
        result = db.execute(text(inspector_query)).scalar()
        
        if result:
            logger.info("✓ attachment_summary table already exists")
            return True
        
        # Create table
        create_query = """
        CREATE TABLE attachment_summary (
            id UUID PRIMARY KEY,
            attachment_id UUID NOT NULL REFERENCES attachment(id) ON DELETE CASCADE,
            summary_text TEXT NOT NULL,
            key_points TEXT[],
            confidence_score FLOAT,
            processing_method VARCHAR(50),
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_attachment_summary_attachment (attachment_id)
        )
        """
        
        db.execute(text(create_query))
        db.commit()
        logger.info("✓ Created attachment_summary table")
        return True
    
    except Exception as e:
        logger.error(f"Failed to create attachment_summary table: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def run_all_migrations():
    """Run all database migrations"""
    logger.info("\n" + "="*70)
    logger.info("  DATABASE MIGRATIONS")
    logger.info("="*70 + "\n")
    
    success = True
    success = create_queued_task_table() and success
    success = create_attachment_summary_table() and success
    
    if success:
        logger.info("\n✓ All migrations completed successfully\n")
    else:
        logger.error("\n✗ Some migrations failed\n")
    
    return success