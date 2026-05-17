# server/services/file_upload_service.py
"""File upload service with R2 and legacy Cloudinary support"""
import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

from core.logger import get_logger
from services.r2_storage_service import get_r2_service

logger = get_logger(__name__)

UPLOADS_DIR = Path(__file__).parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)


class FileUploadService:
    """Service for handling file uploads to local storage and R2"""

    @staticmethod
    def save_upload_file(file_path: str, content: bytes) -> str:
        """
        Save uploaded file to local uploads directory (temporary)
        
        Args:
            file_path: Original file name/path
            content: File content bytes
            
        Returns:
            Local file path
        """
        try:
            file_name = os.path.basename(file_path)
            local_path = UPLOADS_DIR / file_name
            
            with open(local_path, 'wb') as f:
                f.write(content)
            
            logger.info(f"✓ File saved locally: {local_path}")
            return str(local_path)
        except Exception as e:
            logger.error(f"Failed to save file locally: {e}")
            raise

    @staticmethod
    def upload_to_r2(local_file_path: str, file_name: str) -> Optional[str]:
        """
        Upload file from local storage to Cloudflare R2
        
        Args:
            local_file_path: Path to local file
            file_name: Original file name
            
        Returns:
            R2 public URL or None if upload fails
        """
        try:
            r2_service = get_r2_service()
            
            # Generate S3 key with uuid prefix to avoid collisions
            file_uuid = str(uuid.uuid4())[:8]
            file_ext = os.path.splitext(file_name)[1]
            s3_key = f"tickets/{file_uuid}_{os.path.splitext(file_name)[0]}{file_ext}"
            
            # Upload to R2
            r2_url = r2_service.upload_file(local_file_path, s3_key)
            
            if r2_url:
                logger.info(f"✓ File uploaded to R2: {r2_url}")
                return r2_url
            else:
                logger.warning("R2 upload returned None")
                return None
        except Exception as e:
            logger.error(f"Failed to upload to R2: {e}")
            return None

    @staticmethod
    def delete_local_file(local_file_path: str) -> bool:
        """
        Delete file from local uploads directory
        
        Args:
            local_file_path: Path to local file
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            if os.path.exists(local_file_path):
                os.remove(local_file_path)
                logger.info(f"✓ Local file deleted: {local_file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete local file: {e}")
            return False

    @staticmethod
    def process_file_upload(file_content: bytes, file_name: str) -> Dict[str, Any]:
        """
        Complete file upload process:
        1. Save to local uploads directory
        2. Upload to R2
        3. Delete from local directory
        
        Args:
            file_content: File content bytes
            file_name: Original file name
            
        Returns:
            Dict with file_path (local), r2_url, file_name, file_size
        """
        try:
            # Step 1: Save locally
            local_path = FileUploadService.save_upload_file(file_name, file_content)
            file_size = len(file_content)
            
            # Step 2: Upload to R2
            r2_url = FileUploadService.upload_to_r2(local_path, file_name)
            
            # Step 3: Delete local file
            FileUploadService.delete_local_file(local_path)
            
            return {
                "file_path": local_path,
                "r2_url": r2_url,
                "cloudinary_url": r2_url,  # For backwards compatibility with calling code
                "file_name": file_name,
                "file_size": file_size,
                "success": True
            }
        except Exception as e:
            logger.error(f"File upload process failed: {e}")
            return {
                "file_name": file_name,
                "success": False,
                "error": str(e)
            }