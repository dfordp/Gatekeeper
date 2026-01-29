# server/dependencies.py
from fastapi import Request, HTTPException, status
from uuid import UUID

async def get_current_user_id(request: Request) -> UUID:
    """Extract current user ID from JWT (set by middleware)."""
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated",
        )
    return user_id

async def get_current_company_id(request: Request) -> UUID:
    """Extract current company ID from JWT (set by middleware)."""
    company_id = getattr(request.state, 'company_id', None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Company not found in token",
        )
    return company_id

async def get_current_role(request: Request) -> str:
    """Extract current user role from JWT (set by middleware)."""
    role = getattr(request.state, 'role', None)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Role not found in token",
        )
    return role

def get_current_user_full(request: Request) -> dict:
    """Get all current user info from JWT."""
    return {
        'user_id': getattr(request.state, 'user_id', None),
        'company_id': getattr(request.state, 'company_id', None),
        'role': getattr(request.state, 'role', None),
    }