from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum
from .base import Base, TimestampMixin

class TicketStatus(str, enum.Enum):
    """Ticket status - strict lifecycle."""
    DRAFT = "draft"
    OPEN = "open"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"
    IR = "ir"  # Internal Request / Siemens issue

class TicketLevel(str, enum.Enum):
    """Ticket severity level."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class TicketCategory(str, enum.Enum):
    """Ticket category."""
    LOGIN_ACCESS = "login_access"
    LICENSE = "license"
    INSTALLATION = "installation"
    UPLOAD_SAVE = "upload_save"
    WORKFLOW = "workflow"
    PERFORMANCE = "performance"
    INTEGRATION = "integration"
    DATA_CONFIG = "data_config"
    OTHER = "other"

class Ticket(Base, TimestampMixin):
    """Ticket entity - immutable via events only."""
    __tablename__ = "ticket"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_no = Column(String(50), nullable=False, unique=True)
    status = Column(Enum(TicketStatus), nullable=False, default=TicketStatus.DRAFT)
    level = Column(Enum(TicketLevel), nullable=True)
    category = Column(Enum(TicketCategory), nullable=True)
    subject = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)
    detailed_description = Column(Text, nullable=False)
    
    company_id = Column(UUID(as_uuid=True), ForeignKey("company.id"), nullable=False)
    raised_by_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    assigned_engineer_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    
    closed_at = Column(DateTime, nullable=True)
    reopened_at = Column(DateTime, nullable=True)
    
    # Relationships
    company = relationship("Company", back_populates="tickets")
    raised_by_user = relationship(
        "User",
        foreign_keys=[raised_by_user_id],
        back_populates="tickets_raised"
    )
    assigned_engineer = relationship(
        "User",
        foreign_keys=[assigned_engineer_id],
        back_populates="tickets_assigned"
    )
    events = relationship("TicketEvent", back_populates="ticket", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="ticket", cascade="all, delete-orphan")
    embeddings = relationship("Embedding", back_populates="ticket", cascade="all, delete-orphan")
    rca = relationship("RCA", back_populates="ticket", uselist=False, cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_ticket_company", "company_id"),
        Index("idx_ticket_status", "status"),
        Index("idx_ticket_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<Ticket {self.ticket_no}>"