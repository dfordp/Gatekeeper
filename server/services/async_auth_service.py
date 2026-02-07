# server/services/async_auth_service.py
"""
Async Authentication Service - NO asyncio.to_thread() calls
Handles admin registration, login, password management using AsyncSessionLocal
"""

import hashlib
import uuid
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional

import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.async_database import AsyncSessionLocal
from core.database import AdminUser, AdminAuditLog, Company
from core.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS
from core.logger import get_logger
from utils.exceptions import ValidationError, UnauthorizedError, ConflictError

logger = get_logger(__name__)


class AsyncAuthService:
    """Fully async authentication service"""
    
    @staticmethod
    async def register_admin(
        email: str,
        password: str,
        full_name: str,
        role: str = "admin",
        company_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register a new admin user asynchronously.
        
        Args:
            email: Admin email address
            password: Plain text password (will be hashed)
            full_name: Full name of admin
            role: Admin role (admin, manager, analyst)
            company_id: Optional company UUID
            
        Returns:
            Dict with admin details
            
        Raises:
            ValidationError: If validation fails
            ConflictError: If email already exists
        """
        # Validate inputs
        if not email or "@" not in email:
            raise ValidationError("Invalid email format")
        if not password or len(password) < 12:
            raise ValidationError("Password must be at least 12 characters")
        if not full_name or len(full_name.strip()) < 2:
            raise ValidationError("Full name must be at least 2 characters")
        if role not in ["admin", "manager", "analyst"]:
            raise ValidationError("Invalid role. Must be: admin, manager, analyst")
        
        async with AsyncSessionLocal() as session:
            try:
                # Check if email already exists
                result = await session.execute(
                    select(AdminUser).where(AdminUser.email == email.lower())
                )
                if result.scalar_one_or_none():
                    raise ConflictError(f"Email '{email}' already registered")
                
                # Verify company exists if provided
                if company_id:
                    try:
                        company_result = await session.execute(
                            select(Company).where(Company.id == uuid.UUID(company_id))
                        )
                        if not company_result.scalar_one_or_none():
                            raise ValidationError(f"Company '{company_id}' not found")
                    except (ValueError, Exception) as e:
                        raise ValidationError(f"Invalid company ID: {str(e)}")
                
                # Hash password using SHA256
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                
                # Create admin user
                admin = AdminUser(
                    id=uuid.uuid4(),
                    email=email.lower(),
                    password_hash=password_hash,
                    full_name=full_name.strip(),
                    role=role,
                    is_active=True,
                    company_id=uuid.UUID(company_id) if company_id else None,
                    created_at=date.today(),
                    updated_at=date.today()
                )
                
                session.add(admin)
                await session.commit()
                
                logger.info(f"✓ Admin registered: {email} (role: {role})")
                
                return {
                    "id": str(admin.id),
                    "email": admin.email,
                    "full_name": admin.full_name,
                    "role": admin.role,
                    "is_active": admin.is_active,
                    "company_id": str(admin.company_id) if admin.company_id else None,
                    "created_at": str(admin.created_at)
                }
            
            except (ValidationError, ConflictError):
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Error registering admin: {e}")
                raise ValidationError(f"Registration failed: {str(e)}")
    
    @staticmethod
    async def authenticate(
        email: str,
        password: str,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Authenticate admin user and return JWT token.
        
        Args:
            email: Admin email
            password: Plain text password
            ip_address: Client IP address (optional, for audit logging)
            
        Returns:
            Dict with JWT token and admin details
            
        Raises:
            UnauthorizedError: If credentials are invalid
        """
        if not email or not password:
            raise UnauthorizedError("Email and password required")
        
        async with AsyncSessionLocal() as session:
            try:
                # Find admin by email
                result = await session.execute(
                    select(AdminUser).where(AdminUser.email == email.lower())
                )
                admin = result.scalar_one_or_none()
                
                if not admin:
                    logger.warning(f"Login attempt with non-existent email: {email}")
                    raise UnauthorizedError("Invalid email or password")
                
                # Verify password
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                if admin.password_hash != password_hash:
                    logger.warning(f"Failed login attempt for: {email}")
                    raise UnauthorizedError("Invalid email or password")
                
                if not admin.is_active:
                    logger.warning(f"Login attempt for inactive admin: {email}")
                    raise UnauthorizedError("Admin account is inactive")
                
                # Update last_login
                admin.last_login = date.today()
                session.add(admin)
                await session.commit()
                
                # Create JWT token
                token = AsyncAuthService._create_jwt_token(
                    str(admin.id),
                    admin.email,
                    admin.role
                )
                
                # Create audit log
                try:
                    audit = AdminAuditLog(
                        admin_user_id=admin.id,
                        action="login",
                        ip_address=ip_address,
                        created_at=datetime.utcnow()
                    )
                    session.add(audit)
                    await session.commit()
                except Exception as audit_error:
                    logger.warning(f"Failed to create audit log: {audit_error}")
                    # Don't fail the login if audit fails
                
                logger.info(f"✓ Admin authenticated: {email}")
                
                return {
                    "token": token,
                    "admin": {
                        "id": str(admin.id),
                        "email": admin.email,
                        "full_name": admin.full_name,
                        "role": admin.role,
                        "is_active": admin.is_active,
                        "company_id": str(admin.company_id) if admin.company_id else None,
                        "last_login": str(admin.last_login) if admin.last_login else None,
                        "created_at": str(admin.created_at)
                    }
                }
            
            except UnauthorizedError:
                raise
            except Exception as e:
                logger.error(f"Authentication error: {e}")
                raise UnauthorizedError("Authentication failed")
    
    @staticmethod
    async def change_password(
        admin_id: str,
        old_password: str,
        new_password: str
    ) -> Dict[str, Any]:
        """
        Change admin password.
        
        Args:
            admin_id: Admin UUID
            old_password: Current password
            new_password: New password
            
        Returns:
            Dict with success message
            
        Raises:
            ValidationError: If validation fails
            UnauthorizedError: If old password is incorrect
        """
        if not new_password or len(new_password) < 12:
            raise ValidationError("New password must be at least 12 characters")
        
        if old_password == new_password:
            raise ValidationError("New password must be different from old password")
        
        async with AsyncSessionLocal() as session:
            try:
                # Get admin
                admin = await session.get(AdminUser, uuid.UUID(admin_id))
                if not admin:
                    raise UnauthorizedError("Admin not found")
                
                # Verify old password
                old_password_hash = hashlib.sha256(old_password.encode()).hexdigest()
                if admin.password_hash != old_password_hash:
                    logger.warning(f"Failed password change attempt for: {admin.email}")
                    raise UnauthorizedError("Current password is incorrect")
                
                # Hash new password
                new_password_hash = hashlib.sha256(new_password.encode()).hexdigest()
                
                # Update password
                admin.password_hash = new_password_hash
                admin.updated_at = date.today()
                session.add(admin)
                
                # Create audit log
                audit = AdminAuditLog(
                    admin_user_id=admin.id,
                    action="password_changed",
                    created_at=datetime.utcnow()
                )
                session.add(audit)
                
                await session.commit()
                
                logger.info(f"✓ Password changed for: {admin.email}")
                
                return {"message": "Password changed successfully"}
            
            except (ValidationError, UnauthorizedError):
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Error changing password: {e}")
                raise ValidationError(f"Password change failed: {str(e)}")
    
    @staticmethod
    def _create_jwt_token(admin_id: str, email: str, role: str) -> str:
        """
        Create a JWT token (non-async helper).
        
        Args:
            admin_id: Admin UUID
            email: Admin email
            role: Admin role
            
        Returns:
            JWT token string
        """
        payload = {
            "sub": admin_id,
            "email": email,
            "role": role,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
        }
        
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        logger.debug(f"JWT token created for: {email}")
        return token