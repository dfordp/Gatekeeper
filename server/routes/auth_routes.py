# server/routes/auth_routes.py
"""Authentication routes - fully async, no thread pool blocking"""

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.auth_models import (
    RegisterRequest, LoginRequest, ChangePasswordRequest, 
    LoginResponse, AdminUserResponse
)
from services.async_auth_service import AsyncAuthService
from middleware.auth_middleware import get_current_admin
from core.async_database import get_async_db
from core.database import AdminUser
from core.config import ADMIN_SECRET_KEY
from utils.exceptions import ValidationError, UnauthorizedError, ConflictError
from core.logger import get_logger
from uuid import UUID

logger = get_logger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Authentication"])

@router.post("/register", response_model=LoginResponse)
async def register(req: RegisterRequest, request: Request, db: AsyncSession = Depends(get_async_db)):
    """Register a new admin user (fully async)"""
    if req.secret_key != ADMIN_SECRET_KEY:
        logger.warning(f"Invalid secret key attempt from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(status_code=403, detail="Invalid secret key")
    
    try:
        # ✓ CORRECT: Use async service directly
        from uuid import uuid4
        import hashlib
        
        # Create admin user record (async)
        admin_id = uuid4()
        hashed_password = hashlib.sha256(req.password.encode()).hexdigest()
        
        admin_user = AdminUser(
            id=admin_id,
            email=req.email,
            password_hash=hashed_password,
            full_name=req.full_name,
            role="admin",
            company_id=UUID(req.company_id) if req.company_id else None,
            is_active=True
        )
        
        db.add(admin_user)
        await db.flush()
        
        # ✓ ASYNC JWT creation (non-blocking)
        token = AuthService.create_jwt_token(
            str(admin_id),
            req.email,
            "admin"
        )
        
        # ✓ ASYNC audit logging
        audit_log = AdminAuditLog(
            admin_user_id=admin_id,
            action="admin_registered",
            ip_address=request.client.host if request.client else None,
            timestamp=datetime.utcnow()
        )
        db.add(audit_log)
        
        await db.commit()
        
        logger.info(f"✓ Admin registered: {req.email}")
        
        return LoginResponse(
            token=token,
            admin={
                "id": str(admin_id),
                "email": req.email,
                "full_name": req.full_name,
                "role": "admin"
            }
        )
    
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email already exists")
    except Exception as e:
        await db.rollback()
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request):
    """
    Authenticate admin and return JWT token (fully async).
    """
    try:
        # ✓ FULLY ASYNC: No asyncio.to_thread()
        result = await AsyncAuthService.authenticate(
            req.email,
            req.password,
            request.client.host if request.client else None
        )
        
        return LoginResponse(
            token=result["token"],
            admin=result["admin"]
        )
    
    except UnauthorizedError as e:
        logger.warning(f"Login failed: {e.message if hasattr(e, 'message') else str(e)}")
        raise HTTPException(status_code=401, detail=str(e))
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
    Change admin password (fully async).
    Requires authentication.
    """
    try:
        admin_id = admin_payload.get("sub")
        
        # ✓ FULLY ASYNC: No asyncio.to_thread()
        await AsyncAuthService.change_password(
            admin_id,
            req.old_password,
            req.new_password
        )
        
        return {"message": "Password changed successfully"}
    
    except (ValidationError, UnauthorizedError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Password change error: {e}")
        raise HTTPException(status_code=500, detail="Password change failed")


@router.get("/me", response_model=AdminUserResponse)
async def get_current_admin_info(
    admin_payload: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current admin user info (fully async).
    Requires authentication.
    """
    try:
        result = await db.execute(
            select(AdminUser).where(AdminUser.id == UUID(admin_payload.get("sub")))
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