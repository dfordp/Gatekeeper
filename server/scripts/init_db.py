# server/scripts/init_db.py
"""
Database initialization script - Create tables, company, and super admin

Usage:
    python scripts/init_db.py

This script will:
1. Create all database tables
2. Create the default company "Future Tech Design"
3. Create a super admin user with email support@ftdsplm.com
4. Display the generated password for the super admin
"""

import os
import sys
import secrets
import string
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import init_db, test_connection, SessionLocal, Company, AdminUser
from core.config import DATABASE_URL
from services.auth_service import AuthService
from core.logger import get_logger
from datetime import datetime

logger = get_logger(__name__)

# Constants
DEFAULT_COMPANY_NAME = "Future Tech Design"
SUPER_ADMIN_EMAIL = "support@ftdsplm.com"
SUPER_ADMIN_NAME = "Support Admin"


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
    # Ensure we have at least one of each required character type
    uppercase = secrets.choice(string.ascii_uppercase)
    lowercase = secrets.choice(string.ascii_lowercase)
    digit = secrets.choice(string.digits)
    special = secrets.choice('!@#$%^&*()')  # Safe special chars only
    
    # Fill the rest with a mix of all character types
    all_chars = string.ascii_letters + string.digits + '!@#$%^&*()'
    remaining = ''.join(secrets.choice(all_chars) for _ in range(length - 4))
    
    # Combine and shuffle
    password_chars = list(uppercase + lowercase + digit + special + remaining)
    secrets.SystemRandom().shuffle(password_chars)
    
    password = ''.join(password_chars)
    return password


def create_default_company() -> str | None:
    """
    Create the default company if it doesn't exist.
    
    Returns:
        Company ID if successful, None otherwise
    """
    db = SessionLocal()
    try:
        # Check if company already exists
        existing = db.query(Company).filter(
            Company.name == DEFAULT_COMPANY_NAME
        ).first()
        
        if existing:
            logger.info(f"✓ Company '{DEFAULT_COMPANY_NAME}' already exists")
            return str(existing.id)
        
        # Create company
        company = Company(name=DEFAULT_COMPANY_NAME)
        db.add(company)
        db.commit()
        
        logger.info(f"✓ Created company: {DEFAULT_COMPANY_NAME} (ID: {company.id})")
        return str(company.id)
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create company: {e}")
        return None
    finally:
        db.close()


def create_super_admin(company_id: str, password: str) -> bool:
    """
    Create the super admin user.
    
    Args:
        company_id: Company UUID
        password: Admin password
        
    Returns:
        True if successful, False otherwise
    """
    db = SessionLocal()
    try:
        # Check if admin already exists
        existing = db.query(AdminUser).filter(
            AdminUser.email == SUPER_ADMIN_EMAIL
        ).first()
        
        if existing:
            logger.info(f"✓ Super admin '{SUPER_ADMIN_EMAIL}' already exists")
            return True
        
        # Hash password
        password_hash = AuthService.hash_password(password)
        
        # Create admin user
        admin = AdminUser(
            email=SUPER_ADMIN_EMAIL,
            password_hash=password_hash,
            full_name=SUPER_ADMIN_NAME,
            role="admin",
            is_active=True,
            company_id=company_id
        )
        
        db.add(admin)
        db.commit()
        
        logger.info(f"✓ Created super admin: {SUPER_ADMIN_EMAIL}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create super admin: {e}")
        return False
    finally:
        db.close()


def initialize_database() -> bool:
    """
    Initialize database with tables, company, and super admin.
    
    Returns:
        True if successful, False otherwise
    """
    logger.info("=" * 70)
    logger.info("🚀 Gatekeeper Database Initialization")
    logger.info("=" * 70)
    
    # Test connection
    logger.info("\n1️⃣ Testing database connection...")
    if not test_connection():
        logger.error("❌ Cannot connect to database")
        logger.error(f"Database URL: {DATABASE_URL}")
        return False
    logger.info("✓ Database connection successful")
    
    # Initialize tables
    logger.info("\n2️⃣ Creating database tables...")
    if not init_db():
        logger.error("❌ Failed to initialize database tables")
        return False
    logger.info("✓ All database tables created")
    
    # Create default company
    logger.info("\n3️⃣ Setting up default company...")
    company_id = create_default_company()
    if not company_id:
        logger.error("❌ Failed to create default company")
        return False
    
    # Generate super admin password
    logger.info("\n4️⃣ Creating super admin user...")
    generated_password = generate_password(16)
    
    if not create_super_admin(company_id, generated_password):
        logger.error("❌ Failed to create super admin")
        return False
    
    # Display credentials
    print("\n" + "=" * 70)
    print("✅ DATABASE INITIALIZATION COMPLETE")
    print("=" * 70)
    print("\n📋 SUPER ADMIN CREDENTIALS:\n")
    print(f"   Email:    {SUPER_ADMIN_EMAIL}")
    print(f"   Password: {generated_password}")
    print("\n" + "=" * 70)
    print("\n⚠️  IMPORTANT:\n")
    print("   • Save the password above securely")
    print("   • Password will NOT be shown again")
    print("   • Use these credentials to log into the dashboard")
    print("   • Additional admins can be created via the UI")
    print("\n" + "=" * 70 + "\n")
    
    # Also log to file
    logger.info("\n" + "=" * 70)
    logger.info("✅ DATABASE INITIALIZATION COMPLETE")
    logger.info(f"📋 SUPER ADMIN EMAIL: {SUPER_ADMIN_EMAIL}")
    logger.info(f"📋 SUPER ADMIN PASSWORD: {generated_password}")
    logger.info("=" * 70)
    
    return True


if __name__ == "__main__":
    try:
        success = initialize_database()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Initialization cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)