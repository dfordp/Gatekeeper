# server/services/async_user_service.py
"""TRUE Async User Service - Uses AsyncSession for all DB operations"""

from typing import Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.async_database import AsyncSessionLocal
from core.database import User, Company, AdminAuditLog
from utils.datetime_utils import to_iso_date
from utils.exceptions import ValidationError, NotFoundError, ConflictError
from core.logger import get_logger

logger = get_logger(__name__)


class AsyncUserService:
    """TRUE async service for user management (uses AsyncSession directly)"""
    
    @staticmethod
    async def create_user(
        name: str,
        email: str,
        company_id: str,
        role: str = "support_engineer",
        phone_number: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new user/team member asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                # Validate inputs
                if not name or len(name.strip()) < 2:
                    raise ValidationError("Name must be at least 2 characters")
                
                if not email or "@" not in email:
                    raise ValidationError("Invalid email format")
                
                # Check email doesn't exist
                existing_stmt = select(User).where(User.email == email)
                existing_result = await session.execute(existing_stmt)
                existing = existing_result.scalar_one_or_none()
                if existing:
                    raise ConflictError(f"User with email {email} already exists")
                
                # Check company exists
                company_stmt = select(Company).where(Company.id == UUID(company_id))
                company_result = await session.execute(company_stmt)
                company = company_result.scalar_one_or_none()
                if not company:
                    raise NotFoundError("Company not found")
                
                # Validate role
                valid_roles = ["support_engineer", "manager", "supervisor", "external"]
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
                
                session.add(user)
                await session.commit()
                
                logger.info(f"✓ User created: {email}")
                
                return {
                    "id": str(user.id),
                    "name": user.name,
                    "email": user.email,
                    "phone_number": user.phone_number,
                    "role": user.role,
                    "company_id": str(user.company_id),
                    "created_at": to_iso_date(user.created_at)
                }
                
            except (ValidationError, ConflictError, NotFoundError):
                await session.rollback()
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to create user: {e}")
                raise ValidationError(f"Failed to create user: {str(e)}")
    
    @staticmethod
    async def get_users(
        company_id: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get paginated list of users asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                query = select(User)
                filters = []
                
                # Apply filters
                if company_id:
                    filters.append(User.company_id == UUID(company_id))
                if role:
                    filters.append(User.role == role)
                
                # Combine filters
                if filters:
                    from sqlalchemy import and_
                    query = query.where(and_(*filters))
                
                # Get total count
                count_query = select(User)
                if filters:
                    count_query = count_query.where(and_(*filters))
                count_result = await session.execute(count_query)
                total = len(count_result.scalars().all())
                
                # Get paginated results
                query = query.order_by(User.name).limit(limit).offset(offset)
                result = await session.execute(query)
                users = result.scalars().all()
                
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
                        "created_at": to_iso_date(user.created_at)
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
    
    @staticmethod
    async def get_user_by_id(user_id: str) -> Dict[str, Any]:
        """Get user by ID asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                stmt = select(User).where(User.id == UUID(user_id))
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
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
                    "created_at": to_iso_date(user.created_at)
                }
                
            except NotFoundError:
                raise
            except Exception as e:
                logger.error(f"Failed to get user: {e}")
                raise ValidationError("Failed to retrieve user")
    
    @staticmethod
    async def update_user(
        user_id: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[str] = None,
        phone_number: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update user details asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                user_uuid = UUID(user_id)
                
                # Get user
                stmt = select(User).where(User.id == user_uuid)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                if not user:
                    raise NotFoundError("User not found")
                
                # Validate and update
                if name is not None:
                    if len(name.strip()) < 2:
                        raise ValidationError("Name must be at least 2 characters")
                    user.name = name
                
                if email is not None:
                    if "@" not in email:
                        raise ValidationError("Invalid email format")
                    # Check email isn't already taken by someone else
                    existing_stmt = select(User).where(
                        User.email == email,
                        User.id != user_uuid
                    )
                    existing_result = await session.execute(existing_stmt)
                    existing = existing_result.scalar_one_or_none()
                    if existing:
                        raise ConflictError(f"Email {email} already in use")
                    user.email = email
                
                if role is not None:
                    valid_roles = ["support_engineer", "manager", "supervisor", "external"]
                    if role not in valid_roles:
                        raise ValidationError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")
                    user.role = role
                
                if phone_number is not None:
                    user.phone_number = phone_number
                
                await session.commit()
                
                logger.info(f"✓ User updated: {user.email}")
                
                return {
                    "id": str(user.id),
                    "name": user.name,
                    "email": user.email,
                    "phone_number": user.phone_number,
                    "role": user.role,
                    "company_id": str(user.company_id),
                    "created_at": to_iso_date(user.created_at)
                }
                
            except (ValidationError, ConflictError, NotFoundError):
                await session.rollback()
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to update user: {e}")
                raise ValidationError(f"Failed to update user: {str(e)}")
    
    @staticmethod
    async def delete_user(user_id: str, admin_id: Optional[str] = None) -> bool:
        """Delete a user asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                user_uuid = UUID(user_id)
                
                stmt = select(User).where(User.id == user_uuid)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                if not user:
                    raise NotFoundError("User not found")
                
                await session.delete(user)
                await session.commit()
                
                logger.info(f"✓ User deleted: {user.email}")
                
                return True
                
            except NotFoundError:
                await session.rollback()
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to delete user: {e}")
                raise ValidationError(f"Failed to delete user: {str(e)}")