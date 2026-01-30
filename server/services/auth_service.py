# server/services/auth_service.py
"""Authentication service - handles user authentication and password management"""
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import jwt
import bcrypt
from uuid import UUID

from core.database import SessionLocal, AdminUser, AdminAuditLog
from core.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS
from utils.exceptions import ValidationError, UnauthorizedError, ConflictError
from utils.validators import validate_password_strength, validate_email, validate_full_name
from core.logger import get_logger

logger = get_logger(__name__)


class AuthService:
    """Service for authentication and password management"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash password using bcrypt.
        
        Args:
            password: Plain text password
            
        Returns:
            Bcrypt hash string
        """
        # Validate password strength
        validate_password_strength(password)
        
        # Hash password with rounds=12
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify password against hash.
        
        Args:
            plain_password: Plain text password
            hashed_password: Bcrypt hash
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            return bcrypt.checkpw(
                plain_password.encode('utf-8'),
                hashed_password.encode('utf-8')
            )
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    @staticmethod
    def create_jwt_token(admin_id: str, email: str, role: str) -> str:
        """
        Create JWT token for authenticated admin.
        
        Args:
            admin_id: Admin user UUID
            email: Admin email
            role: Admin role (admin, manager, analyst)
            
        Returns:
            JWT token string
        """
        payload = {
            "sub": str(admin_id),
            "email": email,
            "role": role,
            "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
            "iat": datetime.utcnow()
        }
        
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return token
    
    @staticmethod
    def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            Token payload dict if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
    
    @staticmethod
    def register_admin(email: str, password: str, full_name: str, 
                      role: str = "admin", company_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Register a new admin user.
        
        Args:
            email: Admin email address
            password: Plain text password (validated for strength)
            full_name: Admin full name
            role: Admin role (admin, manager, analyst) - defaults to admin
            company_id: Optional company UUID
            
        Returns:
            Dict with admin id, email, full_name, role, is_active, company_id, created_at
            
        Raises:
            ValidationError: If email/password/name invalid or registration fails
            ConflictError: If email already exists
        """
        db = SessionLocal()
        try:
            # Validate inputs
            validate_email(email)
            validate_password_strength(password)
            validate_full_name(full_name)
            
            # Check email doesn't exist
            existing = db.query(AdminUser).filter(AdminUser.email == email).first()
            if existing:
                raise ConflictError(f"Admin user with email {email} already exists")
            
            # Validate role
            valid_roles = ["admin", "manager", "analyst"]
            if role not in valid_roles:
                raise ValidationError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")
            
            # Hash password
            password_hash = AuthService.hash_password(password)
            
            # Create admin user
            admin = AdminUser(
                email=email,
                password_hash=password_hash,
                full_name=full_name,
                role=role,
                is_active=True,
                company_id=UUID(company_id) if company_id else None
            )
            
            db.add(admin)
            db.commit()
            
            # Convert to dict BEFORE closing session - this is critical!
            # We need to access all ORM attributes while session is still active
            admin_dict = {
                "id": str(admin.id),
                "email": admin.email,
                "full_name": admin.full_name,
                "role": admin.role,
                "is_active": admin.is_active,
                "company_id": str(admin.company_id) if admin.company_id else None,
                "created_at": admin.created_at.isoformat()
            }
            
            logger.info(f"✓ Admin user created: {email}")
            return admin_dict
            
        except (ValidationError, ConflictError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to register admin: {e}")
            raise ValidationError(f"Failed to register admin: {str(e)}")
        finally:
            db.close()
    
    @staticmethod
    def authenticate(email: str, password: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Authenticate admin user.
        
        Args:
            email: Admin email
            password: Plain text password
            ip_address: IP address for audit logging
            
        Returns:
            Dict with token and admin info
            
        Raises:
            UnauthorizedError: If credentials invalid or account disabled
        """
        db = SessionLocal()
        try:
            # Find admin user
            admin = db.query(AdminUser).filter(AdminUser.email == email).first()
            
            if not admin:
                logger.warning(f"Login attempt with non-existent email: {email}")
                raise UnauthorizedError("Invalid email or password")
            
            # Check password
            if not AuthService.verify_password(password, admin.password_hash):
                logger.warning(f"Failed login attempt for: {email}")
                
                # Log failed attempt
                AdminAuditLog.create(
                    admin_user_id=admin.id,
                    action="login_failed",
                    ip_address=ip_address
                )
                
                raise UnauthorizedError("Invalid email or password")
            
            # Check if account is active
            if not admin.is_active:
                logger.warning(f"Login attempt for disabled account: {email}")
                raise UnauthorizedError("Account is disabled. Contact administrator.")
            
            # Update last login
            admin.last_login = datetime.utcnow()
            
            # Create token
            token = AuthService.create_jwt_token(str(admin.id), admin.email, admin.role)
            
            # Log successful login
            AdminAuditLog.create(
                admin_user_id=admin.id,
                action="login_successful",
                ip_address=ip_address
            )
            
            db.commit()
            
            logger.info(f"✓ Admin logged in: {email}")
            
            return {
                "token": token,
                "admin": {
                    "id": str(admin.id),
                    "email": admin.email,
                    "full_name": admin.full_name,
                    "role": admin.role,
                    "company_id": str(admin.company_id) if admin.company_id else None
                }
            }
            
        except UnauthorizedError:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise UnauthorizedError("Authentication failed")
        finally:
            db.close()
    
    @staticmethod
    def change_password(admin_id: str, old_password: str, new_password: str) -> bool:
        """
        Change admin password.
        
        Args:
            admin_id: Admin UUID
            old_password: Current password
            new_password: New password
            
        Returns:
            True if successful
            
        Raises:
            ValidationError: If validation fails
            UnauthorizedError: If old password is incorrect
        """
        db = SessionLocal()
        try:
            admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
            if not admin:
                raise ValidationError("Admin not found")
            
            # Verify old password
            if not AuthService.verify_password(old_password, admin.password_hash):
                raise UnauthorizedError("Current password is incorrect")
            
            # Validate new password
            validate_password_strength(new_password)
            
            # Update password
            admin.password_hash = AuthService.hash_password(new_password)
            db.commit()
            
            logger.info(f"✓ Password changed for admin: {admin.email}")
            return True
            
        except (ValidationError, UnauthorizedError):
            raise
        except Exception as e:
            logger.error(f"Password change error: {e}")
            raise ValidationError("Failed to change password")
        finally:
            db.close()