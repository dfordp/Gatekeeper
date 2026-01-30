# server/middleware/auth_middleware.py
"""Authentication middleware for JWT verification"""
from fastapi import Request, HTTPException, Depends
from typing import Optional
from services.auth_service import AuthService
from core.logger import get_logger

logger = get_logger(__name__)


def get_token_from_header(request: Request) -> Optional[str]:
    """
    Extract JWT token from Authorization header.
    
    Expected format: "Bearer <token>"
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    
    # Format: "Bearer <token>"
    parts = auth_header.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    return parts[1]


def verify_token(request: Request) -> dict:
    """
    Verify JWT token from request and return payload.
    
    Raises HTTPException if token is invalid or missing.
    """
    token = get_token_from_header(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    
    payload = AuthService.verify_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload


async def get_current_admin(request: Request) -> dict:
    """
    FastAPI dependency to get current authenticated admin.
    
    Extracts and verifies JWT token from Authorization header.
    
    Returns:
        Token payload with admin info
        
    Raises:
        HTTPException: If token is missing, invalid, or expired
    """
    return verify_token(request)