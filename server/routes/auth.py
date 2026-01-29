# server/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from schemas.auth import LoginRequest, LoginResponse, UserResponse
from schemas.common import APIResponse
from services.auth_service import AuthService
from utils.database import get_db
from dependencies import get_current_user_id
from models.user import User
from utils.errors import NotFoundError
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/login")
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
) -> APIResponse[LoginResponse]:
    """Login endpoint - returns JWT tokens."""
    
    user = AuthService.authenticate_user(db, request.email, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    
    # Create tokens
    access_token = AuthService.create_access_token(
        user_id=user.id,
        company_id=user.company_id,
        role=user.role.value,
    )
    refresh_token = AuthService.create_refresh_token(user.id)
    
    response_data = LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role.value,
            company_id=user.company_id,
            created_at=user.created_at,
        ),
    )
    
    return APIResponse(
        success=True,
        data=response_data,
        meta={"timestamp": datetime.utcnow().isoformat()}
    )

@router.post("/refresh")
async def refresh_token(
    refresh_token: str,
    db: Session = Depends(get_db)
) -> APIResponse[LoginResponse]:
    """Refresh access token."""
    
    try:
        payload = AuthService.verify_token(refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = payload["sub"]
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise NotFoundError("User")
        
        # Create new access token
        access_token = AuthService.create_access_token(
            user_id=user.id,
            company_id=user.company_id,
            role=user.role.value,
        )
        
        response_data = LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse(
                id=user.id,
                email=user.email,
                name=user.name,
                role=user.role.value,
                company_id=user.company_id,
                created_at=user.created_at,
            ),
        )
        
        return APIResponse(
            success=True,
            data=response_data,
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

@router.get("/me")
async def get_me(
    current_user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> APIResponse[UserResponse]:
    """Get current authenticated user info."""
    
    user = db.query(User).filter(User.id == current_user_id).first()
    if not user:
        raise NotFoundError("User", str(current_user_id))
    
    return APIResponse(
        success=True,
        data=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role.value,
            company_id=user.company_id,
            created_at=user.created_at,
        ),
        meta={"timestamp": datetime.utcnow().isoformat()}
    )