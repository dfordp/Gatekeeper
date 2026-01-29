from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from .base import Base

class AttachmentEventType(str, enum.Enum):
    """Types of attachment events."""
    UPLOADED = "uploaded"
    REPLACED = "replaced"
    DEPRECATED = "deprecated"

class AttachmentEvent(Base):
    """Immutable event log for attachment versioning."""
    __tablename__ = "attachment_event"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False)
    attachment_id = Column(UUID(as_uuid=True), ForeignKey("attachment.id"), nullable=True)
    event_type = Column(Enum(AttachmentEventType), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    payload = Column(JSON, nullable=True)  # file_name, file_size, previous_version_id
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    ticket = relationship("Ticket")
    attachment = relationship("Attachment", back_populates="events")
    actor_user = relationship("User", back_populates="attachment_events")
    
    __table_args__ = (
        Index("idx_attachment_event_ticket", "ticket_id"),
        Index("idx_attachment_event_attachment", "attachment_id"),
        Index("idx_attachment_event_type", "event_type"),
    )
    
    def __repr__(self):
        return f"<AttachmentEvent {self.event_type}>"