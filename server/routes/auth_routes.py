# server/routes/auth_routes.py
"""Authentication routes"""
from fastapi import APIRouter, Request, HTTPException, Depends
from models.auth_models import (
    RegisterRequest, LoginRequest, ChangePasswordRequest, 
    LoginResponse, AdminUserResponse
)
from services.auth_service import AuthService
from middleware.auth_middleware import get_current_admin
from core.database import AdminAuditLog, SessionLocal, AdminUser
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
        # Register new admin - now returns a dict
        admin = AuthService.register_admin(
            email=req.email,
            password=req.password,
            full_name=req.full_name,
            role="admin",  # First admin is always admin role
            company_id=req.company_id
        )
        
        # Create JWT token using dict values
        token = AuthService.create_jwt_token(admin["id"], admin["email"], admin["role"])
        
        # Log audit event
        AdminAuditLog.create(
            admin_user_id=admin["id"],
            action="admin_registered",
            ip_address=request.client.host if request.client else None
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
        result = AuthService.authenticate(
            email=req.email,
            password=req.password,
            ip_address=request.client.host if request.client else None
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
        
        AuthService.change_password(
            admin_id=admin_id,
            old_password=req.old_password,
            new_password=req.new_password
        )
        
        # Log audit event
        AdminAuditLog.create(
            admin_user_id=UUID(admin_id),
            action="password_changed",
            ip_address=request.client.host if request.client else None
        )
        
        return {"message": "Password changed successfully"}
    
    except (ValidationError, UnauthorizedError) as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Password change error: {e}")
        raise HTTPException(status_code=500, detail="Password change failed")


@router.get("/me", response_model=AdminUserResponse)
async def get_current_admin_info(admin_payload: dict = Depends(get_current_admin)):
    """
    Get current admin user info.
    Requires authentication.
    """
    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter(AdminUser.id == admin_payload.get("sub")).first()
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
    finally:
        db.close()