from sqlalchemy import Column, String, UUID, ForeignKey, Index, Enum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
import uuid
import enum
from .base import Base, TimestampMixin

class UserRole(str, enum.Enum):
    """User roles for RBAC."""
    PLATFORM_ADMIN = "platform_admin"
    COMPANY_ADMIN = "company_admin"
    ENGINEER = "engineer"
    REQUESTER = "requester"

class User(Base, TimestampMixin):
    """User entity - belongs to exactly one company."""
    __tablename__ = "user"
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=True)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.REQUESTER)
    company_id = Column(PG_UUID(as_uuid=True), ForeignKey("company.id"), nullable=False)
    
    # Relationships
    company = relationship("Company", back_populates="users")
    tickets_raised = relationship(
        "Ticket",
        foreign_keys="Ticket.raised_by_user_id",
        back_populates="raised_by_user"
    )
    tickets_assigned = relationship(
        "Ticket",
        foreign_keys="Ticket.assigned_engineer_id",
        back_populates="assigned_engineer"
    )
    ticket_events = relationship("TicketEvent", back_populates="actor_user")
    attachment_events = relationship("AttachmentEvent", back_populates="actor_user")
    rca_events = relationship("RCAEvent", back_populates="actor_user")
    
    __table_args__ = (
        Index("idx_user_email", "email"),
        Index("idx_user_company", "company_id"),
    )
    
    def __repr__(self):
        return f"<User {self.email}>"