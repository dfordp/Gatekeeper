from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional

class CreateRCARequest(BaseModel):
    """Create RCA."""
    root_cause: str = Field(..., min_length=50, max_length=2000)
    resolution: str = Field(..., min_length=50, max_length=2000)
    prevention: str = Field(..., min_length=50, max_length=2000)

class SubmitRCARequest(BaseModel):
    """Submit RCA for approval."""
    notes: Optional[str] = Field(None, max_length=500)

class ApproveRCARequest(BaseModel):
    """Approve RCA."""
    approver_notes: Optional[str] = Field(None, max_length=500)

class RCAResponse(BaseModel):
    """RCA response."""
    id: UUID
    ticket_id: UUID
    status: str
    root_cause: Optional[str]
    resolution: Optional[str]
    prevention: Optional[str]
    created_by_user_id: UUID
    approved_by_user_id: Optional[UUID]
    created_at: datetime
    submitted_at: Optional[datetime]
    approved_at: Optional[datetime]
    
    class Config:
        from_attributes = True