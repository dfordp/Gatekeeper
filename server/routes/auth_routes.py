# server/routes/auth_routes.py
"""Authentication routes"""
import asyncio
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.auth_models import (
    RegisterRequest, LoginRequest, ChangePasswordRequest, 
    LoginResponse, AdminUserResponse
)
from services.auth_service import AuthService
from middleware.auth_middleware import get_current_admin
from core.database import AdminAuditLog, AdminUser
from core.async_database import get_async_db
from core.config import ADMIN_SECRET_KEY
from utils.exceptions import ValidationError, UnauthorizedError, ConflictError
from core.logger import get_logger
from uuid import UUID

logger = get_logger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Authentication"])


@router.post("/register", response_model=LoginResponse)
async def register(req: RegisterRequest, request: Request):
    """
    Register a new admin user.
    
    Requires ADMIN_SECRET_KEY for security.
    """
    # Verify secret key
    if req.secret_key != ADMIN_SECRET_KEY:
        logger.warning(f"Invalid secret key attempt from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(status_code=403, detail="Invalid secret key")
    
    try:
        # Run sync service method in thread pool to avoid blocking event loop
        admin = await asyncio.to_thread(
            AuthService.register_admin,
            req.email,
            req.password,
            req.full_name,
            "admin",
            req.company_id
        )
        
        # Create JWT token using dict values
        token = await asyncio.to_thread(
            AuthService.create_jwt_token,
            admin["id"],
            admin["email"],
            admin["role"]
        )
        
        # Log audit event in thread pool
        await asyncio.to_thread(
            AdminAuditLog.create,
            admin["id"],
            "admin_registered",
            request.client.host if request.client else None
        )
        
        return LoginResponse(
            token=token,
            admin={
                "id": admin["id"],
                "email": admin["email"],
                "full_name": admin["full_name"],
                "role": admin["role"]
            }
        )
    
    except (ValidationError, ConflictError) as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request):
    """
    Authenticate admin and return JWT token.
    """
    try:
        # Run sync service method in thread pool
        result = await asyncio.to_thread(
            AuthService.authenticate,
            req.email,
            req.password,
            request.client.host if request.client else None
        )
        
        return LoginResponse(
            token=result["token"],
            admin=result["admin"]
        )
    
    except UnauthorizedError as e:
        raise HTTPException(status_code=401, detail=e.message)
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    admin_payload: dict = Depends(get_current_admin),
    request: Request = None
):
    """
    Change admin password.
    Requires authentication.
    """
    try:
        admin_id = admin_payload.get("sub")
        
        # Run sync service method in thread pool
        await asyncio.to_thread(
            AuthService.change_password,
            admin_id,
            req.old_password,
            req.new_password
        )
        
        # Log audit event in thread pool
        await asyncio.to_thread(
            AdminAuditLog.create,
            UUID(admin_id),
            "password_changed",
            request.client.host if request.client else None
        )
        
        return {"message": "Password changed successfully"}
    
    except (ValidationError, UnauthorizedError) as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Password change error: {e}")
        raise HTTPException(status_code=500, detail="Password change failed")


@router.get("/me", response_model=AdminUserResponse)
async def get_current_admin_info(
    admin_payload: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current admin user info.
    Requires authentication.
    """
    try:
        result = await db.execute(
            select(AdminUser).where(AdminUser.id == admin_payload.get("sub"))
        )
        admin = result.scalars().first()
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        
        return AdminUserResponse(
            id=str(admin.id),
            email=admin.email,
            full_name=admin.full_name,
            role=admin.role,
            is_active=admin.is_active,
            company_id=str(admin.company_id) if admin.company_id else None,
            last_login=admin.last_login,
            created_at=admin.created_at
        )
    except Exception as e:
        logger.error(f"Error retrieving admin info: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve admin info")