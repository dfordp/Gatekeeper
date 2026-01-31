# server/scripts/reset_admin_password.py
"""
Admin password reset script - Change password for support@ftdsplm.com

Usage:
    python scripts/reset_admin_password.py [new_password]

If no password is provided, a secure random one will be generated.

Examples:
    python scripts/reset_admin_password.py MyNewPassword123!
    python scripts/reset_admin_password.py
"""

import os
import sys
import secrets
import string
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import SessionLocal, AdminUser
from core.config import DATABASE_URL
from services.auth_service import AuthService
from core.logger import get_logger

logger = get_logger(__name__)

# Constants
ADMIN_EMAIL = "support@ftdsplm.com"


def generate_password(length: int = 16) -> str:
    """
    Generate a secure random password that meets all requirements:
    - At least 12 characters
    - Uppercase letters
    - Lowercase letters
    - Digits
    - Special characters
    
    Args:
        length: Password length (default 16)
        
    Returns:
        Random password string
    """
    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    digits = string.digits
    special_chars = "!@#$%^&*"
    
    # Ensure at least one of each required character type
    password_chars = [
        secrets.choice(uppercase),
        secrets.choice(lowercase),
        secrets.choice(digits),
        secrets.choice(special_chars),
    ]
    
    # Fill the rest with random characters from all pools
    all_chars = uppercase + lowercase + digits + special_chars
    for _ in range(length - len(password_chars)):
        password_chars.append(secrets.choice(all_chars))
    
    # Shuffle to avoid predictable patterns
    password_list = list(password_chars)
    for i in range(len(password_list) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        password_list[i], password_list[j] = password_list[j], password_list[i]
    
    return ''.join(password_list)


def reset_admin_password(new_password: str = None) -> bool:
    """
    Reset admin password for support@ftdsplm.com
    
    Args:
        new_password: New password string. If None, generates random password.
        
    Returns:
        True if successful, False otherwise
    """
    db = SessionLocal()
    try:
        # Find admin user
        admin = db.query(AdminUser).filter(
            AdminUser.email == ADMIN_EMAIL
        ).first()
        
        if not admin:
            print(f"ERROR: Admin user with email '{ADMIN_EMAIL}' not found")
            return False
        
        # Generate password if not provided
        if new_password is None:
            new_password = generate_password()
        
        # Hash the new password
        try:
            hashed_password = AuthService.hash_password(new_password)
        except Exception as e:
            print(f"ERROR: Password validation failed: {e}")
            return False
        
        # Update password
        admin.password_hash = hashed_password
        db.commit()
        
        print(f"✓ Password reset successful for {ADMIN_EMAIL}")
        print(f"\nNew password: {new_password}")
        print("\nIMPORTANT: Save this password in a secure location.")
        print("This password will not be displayed again.")
        
        return True
        
    except Exception as e:
        db.rollback()
        print(f"ERROR: Failed to reset password: {e}")
        logger.error(f"Failed to reset admin password: {e}")
        return False
    finally:
        db.close()


def main():
    """Main entry point"""
    new_password = None
    
    # Check if password provided as argument
    if len(sys.argv) > 1:
        new_password = sys.argv[1]
        print(f"Using provided password")
    else:
        print(f"Generating secure random password...")
    
    print(f"Resetting password for: {ADMIN_EMAIL}")
    print("-" * 50)
    
    success = reset_admin_password(new_password)
    
    if not success:
        sys.exit(1)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())