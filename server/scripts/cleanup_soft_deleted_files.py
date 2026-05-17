"""Script to clean up soft-deleted files from R2 storage"""
import sys
import logging
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logger import get_logger
from services.r2_storage_service import get_r2_service
from core.database import SessionLocal, Attachment, RCAAttachment
from datetime import date, timedelta
from core.config import R2_SOFT_DELETE_RETENTION_DAYS

logger = get_logger(__name__)


def cleanup_r2_storage():
    """
    Clean up soft-deleted files from R2 storage that have expired.
    Permanently deletes files that have been soft-deleted for longer than retention period.
    """
    try:
        r2_service = get_r2_service()
        
        if not r2_service.is_configured:
            logger.error("R2 storage not configured, cannot perform cleanup")
            return 0
        
        logger.info("Starting R2 storage cleanup...")
        
        # Use R2 service's cleanup method
        deleted_count = r2_service.cleanup_expired_files()
        
        logger.info(f"✓ R2 cleanup complete: {deleted_count} files permanently deleted")
        return deleted_count
    except Exception as e:
        logger.error(f"R2 cleanup failed: {e}")
        return 0


def cleanup_database_records():
    """
    Clean up database records for soft-deleted attachments that have expired.
    Removes attachment records from database after they've been soft-deleted for retention period.
    """
    db = SessionLocal()
    deleted_count = 0
    
    try:
        logger.info("Cleaning up expired attachment records from database...")
        
        cutoff_date = date.today() - timedelta(days=R2_SOFT_DELETE_RETENTION_DAYS)
        
        # Find soft-deleted Attachment records that have expired
        expired_attachments = db.query(Attachment).filter(
            Attachment.deleted_at.isnot(None),
            Attachment.deleted_at <= cutoff_date
        ).all()
        
        if expired_attachments:
            logger.info(f"Found {len(expired_attachments)} expired attachment records")
            for attachment in expired_attachments:
                try:
                    logger.info(f"Deleting attachment record: {attachment.id}")
                    db.delete(attachment)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete attachment {attachment.id}: {e}")
            
            db.commit()
            logger.info(f"✓ Deleted {deleted_count} attachment records from database")
        else:
            logger.info("No expired attachment records found")
        
        # Find soft-deleted RCAAttachment records that have expired
        expired_rca_attachments = db.query(RCAAttachment).filter(
            RCAAttachment.deleted_at.isnot(None),
            RCAAttachment.deleted_at <= cutoff_date
        ).all()
        
        if expired_rca_attachments:
            logger.info(f"Found {len(expired_rca_attachments)} expired RCA attachment records")
            for rca_attachment in expired_rca_attachments:
                try:
                    logger.info(f"Deleting RCA attachment record: {rca_attachment.id}")
                    db.delete(rca_attachment)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete RCA attachment {rca_attachment.id}: {e}")
            
            db.commit()
            logger.info(f"✓ Deleted {len(expired_rca_attachments)} RCA attachment records from database")
        else:
            logger.info("No expired RCA attachment records found")
        
        return deleted_count
    except Exception as e:
        logger.error(f"Database cleanup failed: {e}")
        db.rollback()
        return 0
    finally:
        db.close()


def main():
    """Main cleanup routine"""
    logger.info("="*60)
    logger.info("Starting soft-delete cleanup process")
    logger.info(f"Retention period: {R2_SOFT_DELETE_RETENTION_DAYS} days")
    logger.info("="*60)
    
    # Cleanup R2 storage
    r2_deleted = cleanup_r2_storage()
    
    # Cleanup database records
    db_deleted = cleanup_database_records()
    
    total_deleted = r2_deleted + db_deleted
    logger.info("="*60)
    logger.info(f"✓ Cleanup complete: {total_deleted} total items cleaned up")
    logger.info(f"  - R2 files: {r2_deleted}")
    logger.info(f"  - Database records: {db_deleted}")
    logger.info("="*60)
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
