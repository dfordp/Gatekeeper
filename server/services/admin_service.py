# server/services/admin_service.py
"""Admin user management service"""
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from core.database import SessionLocal, AdminUser, AdminAuditLog
from utils.datetime_utils import to_iso_date
from utils.exceptions import ValidationError, NotFoundError, ConflictError, UnauthorizedError
from utils.validators import validate_email, validate_full_name
from core.logger import get_logger
from services.auth_service import AuthService
import secrets
import string

logger = get_logger(__name__)


class AdminManagementService:
    """Service for admin user management"""
    
    @staticmethod
    def can_create_admin(admin_id: str) -> bool:
        """
        Check if an admin can create other admins.
        Only super admins (role='admin') can create admins.
        
        Args:
            admin_id: Admin user ID
            
        Returns:
            True if admin can create other admins
        """
        db = SessionLocal()
        try:
            try:
                admin_uuid = UUID(admin_id)
            except (ValueError, AttributeError):
                return False
                
            admin = db.query(AdminUser).filter(AdminUser.id == admin_uuid).first()
            return admin and admin.role == "admin"
        except Exception:
            return False
        finally:
            db.close()
    @staticmethod
    def _generate_temp_password(length: int = 12) -> str:
        """
        Generate a temporary password for new admins.
        
        Args:
            length: Password length (default 12)
            
        Returns:
            Random alphanumeric password with special characters
        """
        characters = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(characters) for _ in range(length))
        return password
    @staticmethod
    def create_admin(
        email: str,
        full_name: str,
        role: str = "manager",
        created_by_admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new admin user.
        
        Args:
            email: Admin email
            full_name: Admin full name
            role: Admin role (admin, manager, analyst)
            created_by_admin_id: ID of admin creating this admin
            
        Returns:
            Dict with admin details and temporary password
            
        Raises:
            UnauthorizedError: If creator doesn't have permission
            ValidationError: If validation fails
            ConflictError: If email already exists
        """
        # Check permission
        if created_by_admin_id:
            if not AdminManagementService.can_create_admin(created_by_admin_id):
                raise UnauthorizedError("You don't have permission to create admins")
        
        db = SessionLocal()
        try:
            # Validate inputs
            validate_email(email)
            validate_full_name(full_name)
            
            # Check email doesn't exist
            existing = db.query(AdminUser).filter(AdminUser.email == email).first()
            if existing:
                raise ConflictError(f"Admin with email {email} already exists")
            
            # Validate role
            valid_roles = ["admin", "manager", "analyst"]
            if role not in valid_roles:
                raise ValidationError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")
            
            # Generate temporary password
            temp_password = AdminManagementService._generate_temp_password()
            password_hash = AuthService.hash_password(temp_password)
            
            # Create admin
            admin = AdminUser(
                email=email,
                password_hash=password_hash,
                full_name=full_name,
                role=role,
                is_active=True,
                company_id=None  # Admins don't belong to a company
            )
            
            db.add(admin)
            db.commit()
            
            # Log audit event
            if created_by_admin_id:
                AdminAuditLog.create(
                    admin_user_id=UUID(created_by_admin_id),
                    action="admin_created",
                    resource="admin_user",
                    resource_id=str(admin.id),
                    changes={"email": email, "full_name": full_name, "role": role}
                )
            
            logger.info(f"✓ Admin created: {email} (role: {role})")
            
            return {
                "id": str(admin.id),
                "email": admin.email,
                "full_name": admin.full_name,
                "role": admin.role,
                "is_active": admin.is_active,
                "created_at": to_iso_date(admin.created_at),
                "temporary_password": temp_password
            }
            
        except (ValidationError, ConflictError, UnauthorizedError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create admin: {e}")
            raise ValidationError(f"Failed to create admin: {str(e)}")
        finally:
            db.close()
    
    @staticmethod
    def get_admins(limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get paginated list of admins"""
        db = SessionLocal()
        try:
            query = db.query(AdminUser)
            
            total = query.count()
            admins = query.order_by(AdminUser.created_at.desc()).limit(limit).offset(offset).all()
            
            admins_data = []
            for admin in admins:
                admins_data.append({
                    "id": str(admin.id),
                    "email": admin.email,
                    "full_name": admin.full_name,
                    "role": admin.role,
                    "is_active": admin.is_active,
                    "created_at": to_iso_date(admin.created_at),
                    "last_login": to_iso_date(admin.last_login) if admin.last_login else None
                })
            
            return {
                "admins": admins_data,
                "total": total,
                "limit": limit,
                "offset": offset
            }
            
        except Exception as e:
            logger.error(f"Failed to get admins: {e}")
            raise ValidationError("Failed to retrieve admins")
        finally:
            db.close()
    
    @staticmethod
    def update_admin(
        admin_id: str,
        full_name: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        updated_by_admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update admin details"""
        # Check permission
        if updated_by_admin_id:
            if not AdminManagementService.can_create_admin(updated_by_admin_id):
                raise UnauthorizedError("You don't have permission to update admins")
        
        db = SessionLocal()
        try:
            admin = db.query(AdminUser).filter(AdminUser.id == UUID(admin_id)).first()
            if not admin:
                raise NotFoundError("Admin not found")
            
            changes = {}
            
            if full_name is not None:
                if len(full_name.strip()) < 2:
                    raise ValidationError("Name must be at least 2 characters")
                changes["full_name"] = {"from": admin.full_name, "to": full_name}
                admin.full_name = full_name
            
            if role is not None:
                valid_roles = ["admin", "manager", "analyst"]
                if role not in valid_roles:
                    raise ValidationError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")
                changes["role"] = {"from": admin.role, "to": role}
                admin.role = role
            
            if is_active is not None:
                changes["is_active"] = {"from": admin.is_active, "to": is_active}
                admin.is_active = is_active
            
            if changes:
                db.commit()
                
                if updated_by_admin_id:
                    AdminAuditLog.create(
                        admin_user_id=UUID(updated_by_admin_id),
                        action="admin_updated",
                        resource="admin_user",
                        resource_id=admin_id,
                        changes=changes
                    )
                
                logger.info(f"✓ Admin updated: {admin.email}")
            
            return {
                "id": str(admin.id),
                "email": admin.email,
                "full_name": admin.full_name,
                "role": admin.role,
                "is_active": admin.is_active,
                "created_at": to_iso_date(admin.created_at),
                "last_login": to_iso_date(admin.last_login) if admin.last_login else None
            }
            
        except (ValidationError, NotFoundError, UnauthorizedError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update admin: {e}")
            raise ValidationError("Failed to update admin")
        finally:
            db.close()
    
    @staticmethod
    def delete_admin(admin_id: str, deleted_by_admin_id: Optional[str] = None) -> bool:
        """Delete an admin"""
        # Check permission
        if deleted_by_admin_id:
            try:
                if not AdminManagementService.can_create_admin(deleted_by_admin_id):
                    raise UnauthorizedError("You don't have permission to delete admins")
            except UnauthorizedError:
                raise
            except Exception as e:
                logger.error(f"Permission check failed: {e}")
                raise UnauthorizedError("You don't have permission to delete admins")
        
        db = SessionLocal()
        try:
            try:
                admin_uuid = UUID(admin_id)
            except (ValueError, AttributeError):
                raise NotFoundError("Invalid admin ID")
                
            admin = db.query(AdminUser).filter(AdminUser.id == admin_uuid).first()
            if not admin:
                raise NotFoundError("Admin not found")
            
            # Prevent deleting self
            if deleted_by_admin_id and str(admin_id) == deleted_by_admin_id:
                raise ValidationError("Cannot delete your own account")
            
            email = admin.email
            db.delete(admin)
            db.commit()
            
            if deleted_by_admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(deleted_by_admin_id),
                        action="admin_deleted",
                        resource="admin_user",
                        resource_id=admin_id,
                        changes={"email": email}
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log for admin deletion: {e}")
            
            logger.info(f"✓ Admin deleted: {email}")
            return True
            
        except (NotFoundError, ValidationError, UnauthorizedError):
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete admin: {e}")
            raise ValidationError("Failed to delete admin")
        finally:
            db.close()