from sqlalchemy import Column, DateTime, ForeignKey, Index, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from .base import Base

class RCAEventType(str, enum.Enum):
    """Types of RCA workflow events."""
    CREATED = "created"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"

class RCAEvent(Base):
    """Immutable event log for RCA approval workflow."""
    __tablename__ = "rca_event"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rca_id = Column(UUID(as_uuid=True), ForeignKey("rca.id"), nullable=False)
    event_type = Column(Enum(RCAEventType), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    payload = Column(JSON, nullable=True)  # approver_notes, rejection_reason
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    rca = relationship("RCA", back_populates="events")
    actor_user = relationship("User", back_populates="rca_events")
    
    __table_args__ = (
        Index("idx_rca_event_rca", "rca_id"),
        Index("idx_rca_event_type", "event_type"),
    )
    
    def __repr__(self):
        return f"<RCAEvent {self.event_type}>"