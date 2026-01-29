from sqlalchemy import Column, DateTime, ForeignKey, Index, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from .base import Base

class TicketEventType(str, enum.Enum):
    """Types of ticket events (immutable)."""
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    LEVEL_CHANGED = "level_changed"
    COMMENT_ADDED = "comment_added"
    ATTACHMENT_ADDED = "attachment_added"
    ATTACHMENT_REPLACED = "attachment_replaced"
    ATTACHMENT_DEPRECATED = "attachment_deprecated"

class TicketEvent(Base):
    """Immutable event log for tickets."""
    __tablename__ = "ticket_event"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False)
    event_type = Column(Enum(TicketEventType), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    payload = Column(JSON, nullable=True)  # Store event-specific data
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    ticket = relationship("Ticket", back_populates="events")
    actor_user = relationship("User", back_populates="ticket_events")
    
    __table_args__ = (
        Index("idx_ticket_event_ticket", "ticket_id"),
        Index("idx_ticket_event_type", "event_type"),
        Index("idx_ticket_event_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<TicketEvent {self.event_type}>"