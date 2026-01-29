from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, Any

class TicketEventResponse(BaseModel):
    """Ticket event."""
    id: UUID
    ticket_id: UUID
    event_type: str
    actor_user_id: UUID
    actor_user_name: str
    payload: Optional[dict[str, Any]]
    created_at: datetime
    
    class Config:
        from_attributes = True

class RCAEventResponse(BaseModel):
    """RCA event."""
    id: UUID
    rca_id: UUID
    event_type: str
    actor_user_id: UUID
    actor_user_name: str
    payload: Optional[dict[str, Any]]
    created_at: datetime
    
    class Config:
        from_attributes = True