"""Cloudflare R2 storage service for file uploads and management"""
import os
from typing import Optional
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
import logging

from core.config import (
    R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_BUCKET_NAME,
    R2_PUBLIC_URL,
    R2_SOFT_DELETE_RETENTION_DAYS
)

logger = logging.getLogger(__name__)


class R2StorageService:
    """Service for managing file uploads/downloads with Cloudflare R2"""
    
    def __init__(self):
        """Initialize R2 client with configured credentials"""
        self.bucket_name = R2_BUCKET_NAME
        self.public_url = R2_PUBLIC_URL
        self.soft_delete_retention_days = R2_SOFT_DELETE_RETENTION_DAYS
        
        # Initialize S3 client for R2 (S3-compatible API)
        if all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY]):
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
                aws_access_key_id=R2_ACCESS_KEY_ID,
                aws_secret_access_key=R2_SECRET_ACCESS_KEY,
                region_name="auto"
            )
            self.is_configured = True
            logger.info(f"✓ R2 configured: bucket={self.bucket_name}")
        else:
            self.s3_client = None
            self.is_configured = False
            logger.warning("R2 not fully configured - some environment variables missing")
    
    def upload_file(self, local_file_path: str, s3_key: str) -> Optional[str]:
        """
        Upload file to R2 and return public URL
        
        Args:
            local_file_path: Path to local file to upload
            s3_key: S3 key/path in R2 (e.g., "tickets/file-uuid_filename.pdf")
        
        Returns:
            Public URL to access file, or None if upload fails
        """
        if not self.is_configured:
            logger.warning("R2 not configured, upload skipped")
            return None
        
        if not os.path.exists(local_file_path):
            logger.error(f"Local file not found: {local_file_path}")
            return None
        
        try:
            file_size = os.path.getsize(local_file_path)
            logger.info(f"Uploading to R2: {s3_key} ({file_size} bytes)")
            
            # Upload file with metadata
            self.s3_client.upload_file(
                local_file_path,
                self.bucket_name,
                s3_key,
                ExtraArgs={
                    "Metadata": {
                        "upload_date": datetime.utcnow().isoformat(),
                        "local_filename": os.path.basename(local_file_path)
                    }
                }
            )
            
            # Generate public URL
            public_url = self.get_public_url(s3_key)
            logger.info(f"✓ File uploaded to R2: {public_url}")
            return public_url
            
        except ClientError as e:
            logger.error(f"R2 upload failed for {s3_key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error uploading to R2: {e}")
            return None
    
    def delete_file(self, s3_key: str) -> bool:
        """
        Permanently delete file from R2 (hard delete)
        
        Args:
            s3_key: S3 key/path in R2
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_configured:
            logger.warning("R2 not configured, deletion skipped")
            return False
        
        try:
            logger.info(f"Hard-deleting from R2: {s3_key}")
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"✓ File deleted from R2: {s3_key}")
            return True
        except ClientError as e:
            logger.error(f"R2 deletion failed for {s3_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting from R2: {e}")
            return False
    
    def soft_delete_file(self, s3_key: str, retention_days: Optional[int] = None) -> bool:
        """
        Soft-delete file by adding deletion metadata (keeps file for retention period)
        
        Args:
            s3_key: S3 key/path in R2
            retention_days: Days to keep file before permanent deletion (uses config default if None)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_configured:
            logger.warning("R2 not configured, soft deletion skipped")
            return False
        
        retention = retention_days or self.soft_delete_retention_days
        expiry_date = datetime.utcnow() + timedelta(days=retention)
        
        try:
            logger.info(f"Soft-deleting from R2: {s3_key} (retention: {retention} days)")
            
            # Copy object with new metadata marking it as deleted
            copy_source = {"Bucket": self.bucket_name, "Key": s3_key}
            self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=self.bucket_name,
                Key=s3_key,
                Metadata={
                    "deleted": "true",
                    "deleted_at": datetime.utcnow().isoformat(),
                    "expiry_date": expiry_date.isoformat(),
                    "retention_days": str(retention)
                },
                MetadataDirective="REPLACE"
            )
            
            logger.info(f"✓ File soft-deleted from R2: {s3_key} (expires: {expiry_date.date()})")
            return True
        except ClientError as e:
            logger.error(f"R2 soft deletion failed for {s3_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error soft-deleting from R2: {e}")
            return False
    
    def get_public_url(self, s3_key: str) -> str:
        """
        Generate public URL for file in R2 bucket
        
        Args:
            s3_key: S3 key/path in R2 (e.g., "tickets/file-uuid_filename.pdf")
        
        Returns:
            Full public URL to access file
        """
        # Remove trailing slash from public_url if present
        base_url = self.public_url.rstrip("/")
        return f"{base_url}/{s3_key}"
    
    def list_soft_deleted_files(self) -> list:
        """
        List all soft-deleted files in bucket
        
        Returns:
            List of dicts with 's3_key', 'deleted_at', and 'expiry_date'
        """
        if not self.is_configured:
            logger.warning("R2 not configured")
            return []
        
        try:
            soft_deleted = []
            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket_name)
            
            for page in pages:
                if "Contents" not in page:
                    continue
                
                for obj in page["Contents"]:
                    s3_key = obj["Key"]
                    try:
                        # Get object metadata
                        response = self.s3_client.head_object(
                            Bucket=self.bucket_name,
                            Key=s3_key
                        )
                        
                        metadata = response.get("Metadata", {})
                        if metadata.get("deleted") == "true":
                            soft_deleted.append({
                                "s3_key": s3_key,
                                "deleted_at": metadata.get("deleted_at"),
                                "expiry_date": metadata.get("expiry_date")
                            })
                    except ClientError as e:
                        logger.warning(f"Failed to get metadata for {s3_key}: {e}")
                        continue
            
            return soft_deleted
        except Exception as e:
            logger.error(f"Failed to list soft-deleted files: {e}")
            return []
    
    def cleanup_expired_files(self) -> int:
        """
        Permanently delete soft-deleted files that have expired
        
        Returns:
            Number of files deleted
        """
        if not self.is_configured:
            logger.warning("R2 not configured")
            return 0
        
        deleted_count = 0
        now = datetime.utcnow()
        
        try:
            soft_deleted = self.list_soft_deleted_files()
            logger.info(f"Found {len(soft_deleted)} soft-deleted files, checking expiry...")
            
            for item in soft_deleted:
                try:
                    expiry_str = item.get("expiry_date")
                    if not expiry_str:
                        logger.warning(f"No expiry date for {item['s3_key']}, skipping")
                        continue
                    
                    expiry_date = datetime.fromisoformat(expiry_str)
                    
                    # If expired, delete permanently
                    if now >= expiry_date:
                        logger.info(f"Deleting expired file: {item['s3_key']}")
                        self.delete_file(item["s3_key"])
                        deleted_count += 1
                except ValueError as e:
                    logger.warning(f"Failed to parse expiry date for {item['s3_key']}: {e}")
                    continue
            
            logger.info(f"✓ Cleanup complete: {deleted_count} files permanently deleted")
            return deleted_count
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return 0
    
    def file_exists(self, s3_key: str) -> bool:
        """
        Check if file exists in R2
        
        Args:
            s3_key: S3 key/path in R2
        
        Returns:
            True if file exists, False otherwise
        """
        if not self.is_configured:
            return False
        
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            logger.warning(f"Error checking if file exists {s3_key}: {e}")
            return False
        except Exception as e:
            logger.warning(f"Unexpected error checking file: {e}")
            return False


# Global instance for use across services
_r2_service = None


def get_r2_service() -> R2StorageService:
    """Get or create singleton R2 storage service"""
    global _r2_service
    if _r2_service is None:
        _r2_service = R2StorageService()
    return _r2_service
