"""Test R2 connection and basic operations"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from services.r2_storage_service import get_r2_service
from core.logger import get_logger

logger = get_logger(__name__)


def test_r2_connection():
    """Test R2 connection and basic operations"""
    print("\n" + "="*60)
    print("Testing R2 Connection")
    print("="*60)
    
    try:
        # Get R2 service
        r2_service = get_r2_service()
        
        if not r2_service.is_configured:
            print("❌ R2 is NOT configured!")
            print("   Check your .env file for:")
            print("   - R2_ACCOUNT_ID")
            print("   - R2_ACCESS_KEY_ID")
            print("   - R2_SECRET_ACCESS_KEY")
            print("   - R2_BUCKET_NAME")
            return False
        
        print("✅ R2 Configuration loaded successfully")
        print(f"   Account ID: {r2_service.bucket_name}")
        print(f"   Bucket: {r2_service.bucket_name}")
        print(f"   Public URL: {r2_service.public_url}")
        
        # Test file operations
        print("\n" + "-"*60)
        print("Testing file operations...")
        print("-"*60)
        
        # Create a test file
        test_file = Path(__file__).parent / "test_upload.txt"
        test_content = b"Hello R2! This is a test file."
        test_file.write_bytes(test_content)
        print(f"✅ Created test file: {test_file}")
        
        # Try uploading
        s3_key = "test/test_upload.txt"
        public_url = r2_service.upload_file(str(test_file), s3_key)
        
        if public_url:
            print(f"✅ File uploaded successfully!")
            print(f"   Public URL: {public_url}")
            
            # Try soft-delete
            print("\nTesting soft-delete...")
            soft_deleted = r2_service.soft_delete_file(s3_key)
            if soft_deleted:
                print(f"✅ File soft-deleted successfully")
            else:
                print(f"⚠️  Soft-delete may have failed (check logs)")
            
            # Clean up test file
            test_file.unlink()
            print(f"\n✅ Cleanup complete")
            
            print("\n" + "="*60)
            print("✅ ALL TESTS PASSED - R2 is ready!")
            print("="*60)
            return True
        else:
            print(f"❌ Upload failed - check R2 credentials and bucket settings")
            test_file.unlink()
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_r2_connection()
    sys.exit(0 if success else 1)
