# server/middleware/audit_middleware.py
"""Audit logging middleware"""
from fastapi import Request
from uuid import UUID as PyUUID
from core.database import AdminAuditLog
from middleware.auth_middleware import get_token_from_header
from services.auth_service import AuthService
from core.logger import get_logger

logger = get_logger(__name__)


async def audit_middleware(request: Request, call_next):
    """
    Middleware to log admin actions to audit trail.
    Logs all POST, PATCH, DELETE requests from authenticated admins.
    """
    # Process request
    response = await call_next(request)
    
    # Only log mutation operations
    if request.method not in ["POST", "PATCH", "DELETE"]:
        return response
    
    # Skip non-API routes
    if not request.url.path.startswith("/api/"):
        return response
    
    # Try to get current admin
    try:
        token = get_token_from_header(request)
        if not token:
            return response
        
        payload = AuthService.verify_jwt_token(token)
        if not payload:
            return response
        
        admin_id = payload.get("sub")
        
        # Log to audit trail
        try:
            AdminAuditLog.create(
                admin_user_id=PyUUID(admin_id),
                action=f"{request.method} {request.url.path}",
                resource=request.url.path.split("/")[-1],
                ip_address=request.client.host if request.client else None
            )
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
    
    except Exception as e:
        logger.warning(f"Audit middleware error: {e}")
    
    return response