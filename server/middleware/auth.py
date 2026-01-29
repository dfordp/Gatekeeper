from fastapi import Request, HTTPException, status
from services.auth_service import AuthService
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

async def verify_jwt_middleware(request: Request, call_next):
    """Verify JWT on protected routes."""
    
    # Skip auth for public routes
    if request.url.path.startswith("/api/auth"):
        return await call_next(request)
    
    # Extract token from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    
    token = auth_header.split(" ")[1]
    
    try:
        payload = AuthService.verify_token(token)
        request.state.user_id = UUID(payload["sub"])
        request.state.company_id = UUID(payload["company_id"])
        request.state.role = payload["role"]
    except Exception as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    
    response = await call_next(request)
    return response