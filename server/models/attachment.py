from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index, Enum, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from .base import Base

class AttachmentType(str, enum.Enum):
    """Type of attachment."""
    IMAGE = "image"
    DOCUMENT = "document"
    LOG = "log"
    SCREENSHOT = "screenshot"
    VIDEO = "video"

class Attachment(Base):
    """File attachment to ticket - versioned via events."""
    __tablename__ = "attachment"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False)
    type = Column(Enum(AttachmentType), nullable=False)
    file_name = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)  # bytes
    mime_type = Column(String(100), nullable=True)
    file_path = Column(String(1000), nullable=False)  # S3 path or local path
    is_active = Column(Boolean, nullable=False, default=True)
    deprecated_at = Column(DateTime, nullable=True)
    deprecation_reason = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    ticket = relationship("Ticket", back_populates="attachments")
    events = relationship("AttachmentEvent", back_populates="attachment", cascade="all, delete-orphan")
    embeddings = relationship("Embedding", back_populates="attachment", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_attachment_ticket", "ticket_id"),
        Index("idx_attachment_is_active", "is_active"),
    )
    
    def __repr__(self):
        return f"<Attachment {self.file_name}>"