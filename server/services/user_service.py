# server/services/user_service.py
"""User service - handles user management and team operations"""
from typing import Dict, Any, Optional
from uuid import UUID

from core.database import SessionLocal, User, Company, AdminAuditLog
from utils.datetime_utils import to_iso_string
from utils.exceptions import ValidationError, NotFoundError, ConflictError
from core.logger import get_logger

logger = get_logger(__name__)


class UserService:
    """Service for user management"""
    
    @staticmethod
    def create_user(
        name: str,
        email: str,
        company_id: str,
        role: str = "support_engineer",
        phone_number: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new user/team member.
        
        Args:
            name: User full name
            email: User email
            company_id: Company UUID
            role: User role (support_engineer, manager, supervisor)
            phone_number: Optional phone number
            admin_id: Admin user ID for audit logging
            
        Returns:
            Dict with user details
            
        Raises:
            ValidationError: If validation fails
            ConflictError: If email already exists
        """
        db = SessionLocal()
        try:
            # Validate inputs
            if not name or len(name.strip()) < 2:
                raise ValidationError("Name must be at least 2 characters")
            
            if not email or "@" not in email:
                raise ValidationError("Invalid email format")
            
            # Check email doesn't exist
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                raise ConflictError(f"User with email {email} already exists")
            
            # Check company exists
            company = db.query(Company).filter(Company.id == UUID(company_id)).first()
            if not company:
                raise NotFoundError("Company not found")
            
            # Validate role
            valid_roles = ["support_engineer", "manager", "supervisor","external"]
            if role not in valid_roles:
                raise ValidationError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")
            
            # Create user
            user = User(
                name=name,
                email=email,
                company_id=UUID(company_id),
                role=role,
                phone_number=phone_number
            )
            
            db.add(user)
            db.commit()
            
            # Log audit event
            if admin_id:
                AdminAuditLog.create(
                    admin_user_id=UUID(admin_id),
                    action="user_created",
                    resource="user",
                    resource_id=str(user.id),
                    changes={"name": name, "email": email, "role": role}
                )
            
            logger.info(f"✓ User created: {email}")
            
            return {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "phone_number": user.phone_number,
                "role": user.role,
                "company_id": str(user.company_id),
                "created_at": to_iso_string(user.created_at)
            }
            
        except (ValidationError, ConflictError, NotFoundError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create user: {e}")
            raise ValidationError(f"Failed to create user: {str(e)}")
        finally:
            db.close()
    
    @staticmethod
    def get_users(
        company_id: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get paginated list of users"""
        db = SessionLocal()
        try:
            query = db.query(User)
            
            # Apply filters
            if company_id:
                query = query.filter(User.company_id == UUID(company_id))
            if role:
                query = query.filter(User.role == role)
            
            # Get total count
            total = query.count()
            
            # Get paginated results
            users = query.order_by(User.name).limit(limit).offset(offset).all()
            
            # Convert to dicts
            users_data = []
            for user in users:
                users_data.append({
                    "id": str(user.id),
                    "name": user.name,
                    "email": user.email,
                    "phone_number": user.phone_number,
                    "role": user.role,
                    "company_id": str(user.company_id),
                    "company_name": user.company.name if user.company else None,
                    "created_at": to_iso_string(user.created_at)
                })
            
            return {
                "users": users_data,
                "total": total,
                "limit": limit,
                "offset": offset
            }
            
        except Exception as e:
            logger.error(f"Failed to get users: {e}")
            raise ValidationError("Failed to retrieve users")
        finally:
            db.close()
    
    @staticmethod
    def get_user_by_id(user_id: str) -> Dict[str, Any]:
        """Get user by ID"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == UUID(user_id)).first()
            if not user:
                raise NotFoundError("User not found")
            
            return {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "phone_number": user.phone_number,
                "role": user.role,
                "company_id": str(user.company_id),
                "company_name": user.company.name if user.company else None,
                "created_at": to_iso_string(user.created_at)
            }
            
        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to get user: {e}")
            raise ValidationError("Failed to retrieve user")
        finally:
            db.close()
    
    @staticmethod
    def update_user(
        user_id: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[str] = None,
        phone_number: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update user details"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == UUID(user_id)).first()
            if not user:
                raise NotFoundError("User not found")
            
            changes = {}
            
            # Update fields
            if name is not None:
                if len(name.strip()) < 2:
                    raise ValidationError("Name must be at least 2 characters")
                changes["name"] = {"from": user.name, "to": name}
                user.name = name
            
            if email is not None:
                if "@" not in email:
                    raise ValidationError("Invalid email format")
                existing = db.query(User).filter(
                    User.email == email,
                    User.id != UUID(user_id)
                ).first()
                if existing:
                    raise ConflictError(f"Email {email} is already in use")
                changes["email"] = {"from": user.email, "to": email}
                user.email = email
            
            if role is not None:
                valid_roles = ["support_engineer", "manager", "supervisor"]
                if role not in valid_roles:
                    raise ValidationError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")
                changes["role"] = {"from": user.role, "to": role}
                user.role = role
            
            if phone_number is not None:
                changes["phone_number"] = {"from": user.phone_number, "to": phone_number}
                user.phone_number = phone_number
            
            if changes:
                db.commit()
                
                # Log audit event
                if admin_id:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="user_updated",
                        resource="user",
                        resource_id=user_id,
                        changes=changes
                    )
                
                logger.info(f"✓ User updated: {user.email}")
            
            return {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "phone_number": user.phone_number,
                "role": user.role,
                "company_id": str(user.company_id),
                "created_at": to_iso_string(user.created_at)
            }
            
        except (ValidationError, NotFoundError, ConflictError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update user: {e}")
            raise ValidationError("Failed to update user")
        finally:
            db.close()
    
    @staticmethod
    def delete_user(user_id: str, admin_id: Optional[str] = None) -> bool:
        """Delete a user"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == UUID(user_id)).first()
            if not user:
                raise NotFoundError("User not found")
            
            email = user.email
            db.delete(user)
            db.commit()
            
            # Log audit event
            if admin_id:
                AdminAuditLog.create(
                    admin_user_id=UUID(admin_id),
                    action="user_deleted",
                    resource="user",
                    resource_id=user_id,
                    changes={"email": email}
                )
            
            logger.info(f"✓ User deleted: {email}")
            return True
            
        except NotFoundError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete user: {e}")
            raise ValidationError("Failed to delete user")
        finally:
            db.close()