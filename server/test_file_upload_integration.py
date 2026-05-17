"""Test file upload service integration"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from services.file_upload_service import FileUploadService
from core.logger import get_logger

logger = get_logger(__name__)


def test_file_upload_service():
    """Test the FileUploadService integration with R2"""
    print("\n" + "="*60)
    print("Testing FileUploadService Integration")
    print("="*60)
    
    try:
        # Create a test file
        test_content = b"Test document for ticket attachment"
        test_filename = "test_ticket_attachment.txt"
        
        print(f"\nProcessing file upload: {test_filename}")
        print(f"File size: {len(test_content)} bytes")
        
        # Process file upload (same flow as real ticket attachments)
        result = FileUploadService.process_file_upload(test_content, test_filename)
        
        print("\n" + "-"*60)
        print("Upload Result:")
        print("-"*60)
        print(f"Success: {result.get('success')}")
        print(f"File Name: {result.get('file_name')}")
        print(f"File Size: {result.get('file_size')} bytes")
        
        # Check for R2 URL
        r2_url = result.get('r2_url')
        cloudinary_url = result.get('cloudinary_url')
        
        if r2_url:
            print(f"✅ R2 URL: {r2_url}")
        elif cloudinary_url:
            print(f"⚠️  Using Cloudinary URL (fallback): {cloudinary_url}")
        else:
            print(f"❌ No URL returned!")
            return False
        
        if result.get('success'):
            print("\n" + "="*60)
            print("✅ FILE UPLOAD SERVICE TEST PASSED!")
            print("Ready to handle ticket attachments")
            print("="*60)
            return True
        else:
            print(f"\n❌ Upload failed: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_file_upload_service()
    sys.exit(0 if success else 1)
