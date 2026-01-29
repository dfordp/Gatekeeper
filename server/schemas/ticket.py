# server/schemas/ticket.py
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional

class CreateTicketRequest(BaseModel):
    """Create ticket request."""
    subject: str = Field(..., min_length=10, max_length=500)
    detailed_description: str = Field(..., min_length=20)
    level: Optional[str] = None
    category: Optional[str] = None

class UpdateTicketStatusRequest(BaseModel):
    """Update ticket status."""
    new_status: str = Field(..., pattern="^(draft|open|resolved|closed|reopened|ir)$")
    reason: str = Field(..., min_length=5, max_length=500)

class AssignTicketRequest(BaseModel):
    """Assign ticket to engineer."""
    engineer_id: UUID
    reason: str = Field(..., min_length=5, max_length=500)

class ChangeTicketLevelRequest(BaseModel):
    """Change ticket level."""
    new_level: str = Field(..., pattern="^(critical|high|medium|low)$")
    reason: str = Field(..., min_length=5, max_length=500)

class CommentRequest(BaseModel):
    """Add comment to ticket."""
    text: str = Field(..., min_length=1, max_length=2000)

class TicketResponse(BaseModel):
    """Ticket response."""
    id: UUID
    ticket_no: str
    status: str
    level: Optional[str]
    category: Optional[str]
    subject: str
    summary: Optional[str]
    detailed_description: str
    raised_by_user_id: UUID
    assigned_engineer_id: Optional[UUID]
    created_at: datetime
    closed_at: Optional[datetime]
    reopened_at: Optional[datetime]
    
    class Config:
        from_attributes = True