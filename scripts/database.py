# scripts/database.py
import os
import sys
import logging
from sqlalchemy import create_engine, text, Column, String, Text, DateTime, Boolean, Integer, ForeignKey, UUID, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from contextlib import contextmanager
from dotenv import load_dotenv
from datetime import datetime
import uuid

load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://gatekeeper_user:gatekeeper_secure_password_123@localhost:5432/gatekeeper_db"
)

# Create engine
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# ==================== ORM Models ====================

class Company(Base):
    __tablename__ = "company"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    users = relationship("User", back_populates="company", cascade="all, delete-orphan")
    tickets = relationship("Ticket", back_populates="company", cascade="all, delete-orphan")
    embeddings = relationship("Embedding", back_populates="company", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Company {self.name}>"


class User(Base):
    __tablename__ = "user"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=True)
    role = Column(String(50), nullable=False)
    company_id = Column(UUID(as_uuid=True), ForeignKey("company.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    company = relationship("Company", back_populates="users")
    tickets_raised = relationship("Ticket", foreign_keys="Ticket.raised_by_user_id", back_populates="raised_by_user")
    tickets_assigned = relationship("Ticket", foreign_keys="Ticket.assigned_engineer_id", back_populates="assigned_engineer")
    ticket_events = relationship("TicketEvent", back_populates="actor_user")
    attachment_events = relationship("AttachmentEvent", back_populates="actor_user")
    
    __table_args__ = (
        Index("idx_user_company", "company_id"),
    )
    
    def __repr__(self):
        return f"<User {self.email}>"


class Ticket(Base):
    __tablename__ = "ticket"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_no = Column(String(50), nullable=False, unique=True)
    status = Column(String(50), nullable=False, default="open")
    level = Column(String(50), nullable=True)
    category = Column(String(100), nullable=True)
    subject = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)
    detailed_description = Column(Text, nullable=False)
    company_id = Column(UUID(as_uuid=True), ForeignKey("company.id"), nullable=False)
    raised_by_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    assigned_engineer_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    reopened_at = Column(DateTime, nullable=True)
    
    company = relationship("Company", back_populates="tickets")
    raised_by_user = relationship("User", foreign_keys=[raised_by_user_id], back_populates="tickets_raised")
    assigned_engineer = relationship("User", foreign_keys=[assigned_engineer_id], back_populates="tickets_assigned")
    events = relationship("TicketEvent", back_populates="ticket", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="ticket", cascade="all, delete-orphan")
    embeddings = relationship("Embedding", back_populates="ticket", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_ticket_company", "company_id"),
        Index("idx_ticket_status", "status"),
        Index("idx_ticket_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<Ticket {self.ticket_no}>"


class TicketEvent(Base):
    __tablename__ = "ticket_event"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False)
    event_type = Column(String(50), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    ticket = relationship("Ticket", back_populates="events")
    actor_user = relationship("User", back_populates="ticket_events")
    
    __table_args__ = (
        Index("idx_ticket_event_ticket", "ticket_id"),
        Index("idx_ticket_event_type", "event_type"),
        Index("idx_ticket_event_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<TicketEvent {self.id} {self.event_type}>"


class Attachment(Base):
    __tablename__ = "attachment"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False)
    type = Column(String(50), nullable=False)
    file_path = Column(String(1000), nullable=False)
    mime_type = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    ticket = relationship("Ticket", back_populates="attachments")
    events = relationship("AttachmentEvent", back_populates="attachment", cascade="all, delete-orphan")
    embeddings = relationship("Embedding", back_populates="attachment", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_attachment_ticket", "ticket_id"),
        Index("idx_attachment_type", "type"),
    )
    
    def __repr__(self):
        return f"<Attachment {self.id} {self.type}>"


class AttachmentEvent(Base):
    __tablename__ = "attachment_event"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False)
    attachment_id = Column(UUID(as_uuid=True), ForeignKey("attachment.id"), nullable=True)
    event_type = Column(String(50), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    ticket = relationship("Ticket")
    attachment = relationship("Attachment", back_populates="events")
    actor_user = relationship("User", back_populates="attachment_events")
    
    __table_args__ = (
        Index("idx_attachment_event_ticket", "ticket_id"),
        Index("idx_attachment_event_attachment", "attachment_id"),
        Index("idx_attachment_event_type", "event_type"),
    )
    
    def __repr__(self):
        return f"<AttachmentEvent {self.id} {self.event_type}>"


class Embedding(Base):
    __tablename__ = "embedding"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("company.id"), nullable=False)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False)
    attachment_id = Column(UUID(as_uuid=True), ForeignKey("attachment.id"), nullable=True)
    source_type = Column(String(50), nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    text_content = Column(Text, nullable=False)
    vector_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    deprecated_at = Column(DateTime, nullable=True)
    deprecation_reason = Column(String(100), nullable=True)
    
    company = relationship("Company", back_populates="embeddings")
    ticket = relationship("Ticket", back_populates="embeddings")
    attachment = relationship("Attachment", back_populates="embeddings")
    
    __table_args__ = (
        CheckConstraint("source_type IN ('ticket_summary', 'ticket_description', 'resolution', 'rca', 'log_snippet')"),
        Index("idx_embedding_company_active", "company_id", "is_active"),
        Index("idx_embedding_ticket", "ticket_id"),
        Index("idx_embedding_attachment", "attachment_id"),
        Index("idx_embedding_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<Embedding {self.id} {self.source_type}>"


# ==================== Session Management ====================

def get_db() -> Session:
    """Dependency injection for FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """Context manager for synchronous code."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Database tables initialized")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to initialize database: {e}")
        return False


def test_connection():
    """Test database connectivity."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            logger.info("✓ Database connection successful")
            return True
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        return False


def drop_all_tables():
    """Drop all tables (testing only)."""
    try:
        Base.metadata.drop_all(bind=engine)
        logger.info("✓ All tables dropped")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to drop tables: {e}")
        return False