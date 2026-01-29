from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime

class LoginRequest(BaseModel):
    """Login request."""
    email: EmailStr
    password: str = Field(..., min_length=8)

class UserResponse(BaseModel):
    """User data."""
    id: UUID
    email: str
    name: str
    role: str
    company_id: UUID
    created_at: datetime

class LoginResponse(BaseModel):
    """Login response with tokens."""
    access_token: str
    refresh_token: str
    user: UserResponse
    token_type: str = "bearer"