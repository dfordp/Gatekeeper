from sqlalchemy import Column, Text, DateTime, ForeignKey, Index, Enum, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from .base import Base

class RCAStatus(str, enum.Enum):
    """RCA approval workflow status."""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    DEPRECATED = "deprecated"

class RCA(Base):
    """Root Cause Analysis - structured form with approval workflow."""
    __tablename__ = "rca"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False)
    status = Column(Enum(RCAStatus), nullable=False, default=RCAStatus.DRAFT)
    
    # RCA fields (structured form)
    root_cause = Column(Text, nullable=True)
    resolution = Column(Text, nullable=True)
    prevention = Column(Text, nullable=True)
    
    # Workflow
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    approved_by_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    deprecated_at = Column(DateTime, nullable=True)
    
    # Relationships
    ticket = relationship("Ticket", back_populates="rca")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
    approved_by_user = relationship("User", foreign_keys=[approved_by_user_id])
    events = relationship("RCAEvent", back_populates="rca", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_rca_ticket", "ticket_id"),
        Index("idx_rca_status", "status"),
    )
    
    def __repr__(self):
        return f"<RCA {self.id}>"