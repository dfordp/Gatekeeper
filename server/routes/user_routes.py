# server/routes/user_routes.py
"""User management routes"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from pydantic import BaseModel, EmailStr

from middleware.auth_middleware import get_current_admin
from services.user_service import UserService
from utils.exceptions import ValidationError, NotFoundError, ConflictError
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/users", tags=["Users"])


# Pydantic models
class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    company_id: str
    role: str = "support_engineer"
    phone_number: Optional[str] = None


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    phone_number: Optional[str] = None


def check_admin_permission(admin_payload: dict) -> bool:
    """Check if user is an admin"""
    return admin_payload.get("role") == "admin"


@router.post("/")
async def create_user(
    req: CreateUserRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """Create a new user"""
    try:
        result = UserService.create_user(
            name=req.name,
            email=req.email,
            company_id=req.company_id,
            role=req.role,
            phone_number=req.phone_number,
            admin_id=admin_payload.get("sub")
        )
        return result
    except (ValidationError, ConflictError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to create user")


@router.get("/")
async def get_users(
    company_id: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    admin_payload: dict = Depends(get_current_admin)
):
    """Get list of users"""
    try:
        result = UserService.get_users(
            company_id=company_id,
            role=role,
            limit=limit,
            offset=offset
        )
        return result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve users")


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    admin_payload: dict = Depends(get_current_admin)
):
    """Get user by ID"""
    try:
        result = UserService.get_user_by_id(user_id)
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user")


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    req: UpdateUserRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """Update user details"""
    try:
        result = UserService.update_user(
            user_id=user_id,
            name=req.name,
            email=req.email,
            role=req.role,
            phone_number=req.phone_number,
            admin_id=admin_payload.get("sub")
        )
        return result
    except (ValidationError, ConflictError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user")

@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    admin_payload: dict = Depends(get_current_admin)
):
    """Delete a user (admin access only)"""
    # Check if user is admin
    if not check_admin_permission(admin_payload):
        raise HTTPException(status_code=403, detail="Only admins can delete users")
    
    # Get admin ID from token
    admin_user_id = admin_payload.get("sub")
    if not admin_user_id:
        raise HTTPException(status_code=401, detail="Invalid token - missing admin ID")
    
    try:
        UserService.delete_user(user_id, admin_id=admin_user_id)
        return {"message": "User deleted successfully"}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete user")