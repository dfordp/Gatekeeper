from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class AttachmentResponse(BaseModel):
    """Attachment response."""
    id: UUID
    ticket_id: UUID
    type: str
    file_name: str
    file_size: int
    mime_type: Optional[str]
    is_active: bool
    created_at: datetime
    deprecated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class AttachmentEventResponse(BaseModel):
    """Attachment event."""
    id: UUID
    attachment_id: Optional[UUID]
    ticket_id: UUID
    event_type: str
    actor_user_id: UUID
    actor_user_name: str
    created_at: datetime
    
    class Config:
        from_attributes = True