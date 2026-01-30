# server/services/file_upload_service.py
"""File upload service with Cloudinary integration"""
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import cloudinary
import cloudinary.uploader

from core.config import CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
from core.logger import get_logger

logger = get_logger(__name__)

# Configure Cloudinary
if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET
    )

UPLOADS_DIR = Path(__file__).parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)


class FileUploadService:
    """Service for handling file uploads to local storage and Cloudinary"""

    @staticmethod
    def save_upload_file(file_path: str, content: bytes) -> str:
        """
        Save uploaded file to local uploads directory
        
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
    def upload_to_cloudinary(local_file_path: str, file_name: str) -> Optional[str]:
        """
        Upload file from local storage to Cloudinary
        
        Args:
            local_file_path: Path to local file
            file_name: Original file name
            
        Returns:
            Cloudinary URL or None if upload fails
        """
        if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
            logger.warning("Cloudinary not configured, skipping upload")
            return None
        
        try:
            result = cloudinary.uploader.upload(
                local_file_path,
                public_id=f"tickets/{os.path.splitext(file_name)[0]}",
                overwrite=True,
                resource_type="auto"
            )
            
            cloudinary_url = result.get("secure_url")
            logger.info(f"✓ File uploaded to Cloudinary: {cloudinary_url}")
            return cloudinary_url
        except Exception as e:
            logger.error(f"Failed to upload to Cloudinary: {e}")
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
        2. Upload to Cloudinary
        3. Delete from local directory
        
        Args:
            file_content: File content bytes
            file_name: Original file name
            
        Returns:
            Dict with file_path (local), cloudinary_url, file_name, file_size
        """
        try:
            # Step 1: Save locally
            local_path = FileUploadService.save_upload_file(file_name, file_content)
            file_size = len(file_content)
            
            # Step 2: Upload to Cloudinary
            cloudinary_url = FileUploadService.upload_to_cloudinary(local_path, file_name)
            
            # Step 3: Delete local file
            FileUploadService.delete_local_file(local_path)
            
            return {
                "file_path": local_path,
                "cloudinary_url": cloudinary_url,
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