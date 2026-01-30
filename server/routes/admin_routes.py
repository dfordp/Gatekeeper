# server/routes/admin_routes.py
"""Admin management routes"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from pydantic import BaseModel, EmailStr

from middleware.auth_middleware import get_current_admin
from services.admin_service import AdminManagementService
from utils.exceptions import ValidationError, NotFoundError, ConflictError, UnauthorizedError
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/admin-management", tags=["Admin Management"])


# Pydantic models
class CreateAdminRequest(BaseModel):
    email: EmailStr
    full_name: str
    role: str = "manager"


class UpdateAdminRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


@router.post("/admins")
async def create_admin(
    req: CreateAdminRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """
    Create a new admin user.
    Only admins with role 'admin' can create other admins.
    """
    try:
        result = AdminManagementService.create_admin(
            email=req.email,
            full_name=req.full_name,
            role=req.role,
            created_by_admin_id=admin_payload.get("sub")
        )
        return result
    except UnauthorizedError as e:
        raise HTTPException(status_code=403, detail=e.message)
    except (ValidationError, ConflictError) as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error creating admin: {e}")
        raise HTTPException(status_code=500, detail="Failed to create admin")


@router.get("/admins")
async def get_admins(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    admin_payload: dict = Depends(get_current_admin)
):
    """Get list of admins (admin access only)"""
    try:
        # Check if user has admin role
        if admin_payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins can view other admins")
        
        result = AdminManagementService.get_admins(limit=limit, offset=offset)
        return result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error getting admins: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve admins")


@router.put("/admins/{admin_id}")
async def update_admin(
    admin_id: str,
    req: UpdateAdminRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """Update admin details (admin access only)"""
    try:
        result = AdminManagementService.update_admin(
            admin_id=admin_id,
            full_name=req.full_name,
            role=req.role,
            is_active=req.is_active,
            updated_by_admin_id=admin_payload.get("sub")
        )
        return result
    except UnauthorizedError as e:
        raise HTTPException(status_code=403, detail=e.message)
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error updating admin: {e}")
        raise HTTPException(status_code=500, detail="Failed to update admin")


@router.delete("/admins/{admin_id}")
async def delete_admin(
    admin_id: str,
    admin_payload: dict = Depends(get_current_admin)
):
    """Delete an admin (admin access only)"""
    # Get admin ID from token
    admin_user_id = admin_payload.get("sub")
    if not admin_user_id:
        raise HTTPException(status_code=401, detail="Invalid token - missing admin ID")
    
    try:
        AdminManagementService.delete_admin(
            admin_id=admin_id,
            deleted_by_admin_id=admin_user_id
        )
        return {"message": "Admin deleted successfully"}
    except UnauthorizedError as e:
        raise HTTPException(status_code=403, detail=e.message)
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error deleting admin: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete admin")