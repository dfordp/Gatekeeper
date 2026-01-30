# server/models/auth_models.py
"""Authentication request/response models"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class RegisterRequest(BaseModel):
    """Admin registration request"""
    email: EmailStr
    password: str = Field(..., min_length=12, description="Password must be at least 12 characters")
    full_name: str = Field(..., min_length=2, max_length=255)
    company_id: Optional[str] = None
    secret_key: str = Field(..., description="Admin secret key")


class LoginRequest(BaseModel):
    """Admin login request"""
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Login response"""
    token: str
    admin: dict


class ChangePasswordRequest(BaseModel):
    """Change password request"""
    old_password: str
    new_password: str = Field(..., min_length=12)


class AdminUserResponse(BaseModel):
    """Admin user response"""
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    company_id: Optional[str] = None
    last_login: Optional[datetime] = None
    created_at: datetime


class AdminAuditLogResponse(BaseModel):
    """Admin audit log response"""
    id: str
    admin_email: str
    action: str
    resource: Optional[str] = None
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime