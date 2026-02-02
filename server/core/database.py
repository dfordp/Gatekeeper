# server/core/database.py
"""Database configuration, models, and session management"""
import logging
from sqlalchemy import (
    create_engine, text, Column, String, Text, DateTime, Boolean, 
    Integer, ForeignKey, UUID, CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from contextlib import contextmanager
from datetime import datetime
import uuid

from .config import DATABASE_URL

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create engine
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


class Company(Base):
    """Company model"""
    __tablename__ = "company"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    users = relationship("User", back_populates="company", cascade="all, delete-orphan")
    tickets = relationship("Ticket", back_populates="company", cascade="all, delete-orphan")
    embeddings = relationship("Embedding", back_populates="company", cascade="all, delete-orphan")
    admin_users = relationship("AdminUser", back_populates="company", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Company {self.name}>"


class User(Base):
    """User/Support team member model"""
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
    root_cause_analyses = relationship("RootCauseAnalysis", back_populates="created_by_user")
    resolution_notes = relationship("ResolutionNote", back_populates="created_by_user")
    
    __table_args__ = (
        Index("idx_user_company", "company_id"),
        Index("idx_user_email", "email"),
    )
    
    def __repr__(self):
        return f"<User {self.email}>"


class Ticket(Base):
    """Support ticket model - complete with RCA and resolution notes"""
    __tablename__ = "ticket"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_no = Column(String(50), nullable=False, unique=True, index=True)
    status = Column(String(50), nullable=False, default="open", index=True)
    level = Column(String(50), nullable=True)
    category = Column(String(100), nullable=True)
    subject = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)
    detailed_description = Column(Text, nullable=False)
    company_id = Column(UUID(as_uuid=True), ForeignKey("company.id"), nullable=False, index=True)
    raised_by_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    assigned_engineer_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    reopened_at = Column(DateTime, nullable=True)
    attachment_ids = Column(JSONB, nullable=True, default=[])
    
    company = relationship("Company", back_populates="tickets")
    raised_by_user = relationship("User", foreign_keys=[raised_by_user_id], back_populates="tickets_raised")
    assigned_engineer = relationship("User", foreign_keys=[assigned_engineer_id], back_populates="tickets_assigned")
    events = relationship("TicketEvent", back_populates="ticket", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="ticket", cascade="all, delete-orphan")
    embeddings = relationship("Embedding", back_populates="ticket", cascade="all, delete-orphan")
    root_cause_analysis = relationship("RootCauseAnalysis", uselist=False, back_populates="ticket", cascade="all, delete-orphan")
    resolution_note = relationship("ResolutionNote", uselist=False, back_populates="ticket", cascade="all, delete-orphan")
    similar_issues_as_newer = relationship("SimilarIssues", foreign_keys="SimilarIssues.newer_ticket_id", back_populates="newer_ticket")
    similar_issues_as_older = relationship("SimilarIssues", foreign_keys="SimilarIssues.older_ticket_id", back_populates="older_ticket")
    
    __table_args__ = (
        Index("idx_ticket_company", "company_id"),
        Index("idx_ticket_status", "status"),
        Index("idx_ticket_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<Ticket {self.ticket_no}>"


class TicketEvent(Base):
    """Ticket event/action log - tracks all changes to a ticket"""
    __tablename__ = "ticket_event"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
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
    """Attachment model - files attached to tickets"""
    __tablename__ = "attachment"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False, index=True)
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
        Index("idx_attachment_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<Attachment {self.file_path}>"


class AttachmentEvent(Base):
    """Attachment event log - tracks attachment changes"""
    __tablename__ = "attachment_event"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False, index=True)
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
        return f"<AttachmentEvent {self.id}>"


class RootCauseAnalysis(Base):
    """Root Cause Analysis model - added when resolving tickets"""
    __tablename__ = "root_cause_analysis"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False, unique=True, index=True)
    root_cause_description = Column(Text, nullable=False)
    contributing_factors = Column(JSONB, nullable=True, default=[])
    prevention_measures = Column(Text, nullable=True)
    resolution_steps = Column(JSONB, nullable=True, default=[])
    related_ticket_ids = Column(JSONB, nullable=True, default=[])
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    ticket = relationship("Ticket", foreign_keys=[ticket_id], back_populates="root_cause_analysis")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id], back_populates="root_cause_analyses")
    
    __table_args__ = (
        Index("idx_rca_ticket", "ticket_id"),
        Index("idx_rca_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<RootCauseAnalysis {self.ticket_id}>"


class ResolutionNote(Base):
    """Resolution Note model - final summary when closing tickets"""
    __tablename__ = "resolution_note"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False, unique=True, index=True)
    solution_description = Column(Text, nullable=False)
    steps_taken = Column(JSONB, nullable=True, default=[])
    resources_used = Column(JSONB, nullable=True, default=[])
    follow_up_notes = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    ticket = relationship("Ticket", foreign_keys=[ticket_id], back_populates="resolution_note")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id], back_populates="resolution_notes")
    
    __table_args__ = (
        Index("idx_resolution_note_ticket", "ticket_id"),
        Index("idx_resolution_note_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<ResolutionNote {self.ticket_id}>"


class Embedding(Base):
    """Embedding/vector model for semantic search"""
    __tablename__ = "embedding"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("company.id"), nullable=False, index=True)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False, index=True)
    attachment_id = Column(UUID(as_uuid=True), ForeignKey("attachment.id"), nullable=True)
    source_type = Column(String(50), nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    text_content = Column(Text, nullable=False)
    vector_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
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
        return f"<Embedding {self.id}>"


class SimilarIssues(Base):
    """Similar Issues mapping - tracks semantic similarity between tickets"""
    __tablename__ = "similar_issues"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    newer_ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False, index=True)
    older_ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False, index=True)
    similarity_score = Column(Integer, nullable=False)  # 0-100 score
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    newer_ticket = relationship("Ticket", foreign_keys=[newer_ticket_id], back_populates="similar_issues_as_newer")
    older_ticket = relationship("Ticket", foreign_keys=[older_ticket_id], back_populates="similar_issues_as_older")
    
    __table_args__ = (
        Index("idx_similar_newer_ticket", "newer_ticket_id"),
        Index("idx_similar_older_ticket", "older_ticket_id"),
        Index("idx_similar_score", "similarity_score"),
    )
    
    def __repr__(self):
        return f"<SimilarIssues {self.newer_ticket_id} -> {self.older_ticket_id}>"


class AdminUser(Base):
    """Admin user model"""
    __tablename__ = "admin_user"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("company.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    company = relationship("Company", back_populates="admin_users")
    audit_logs = relationship("AdminAuditLog", back_populates="admin_user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<AdminUser {self.email}>"


class AdminAuditLog(Base):
    """Admin audit log model"""
    __tablename__ = "admin_audit_log"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_user_id = Column(UUID(as_uuid=True), ForeignKey("admin_user.id"), nullable=False)
    action = Column(String(100), nullable=False)
    resource = Column(String(100), nullable=True)
    resource_id = Column(String(100), nullable=True)
    changes = Column(JSONB, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    admin_user = relationship("AdminUser", back_populates="audit_logs")
    
    __table_args__ = (
        Index("idx_audit_admin_user", "admin_user_id"),
        Index("idx_audit_created_at", "created_at"),
        Index("idx_audit_action", "action"),
    )
    
    def __repr__(self):
        return f"<AdminAuditLog {self.action}>"
    
    @staticmethod
    def create(admin_user_id, action: str, resource: str = None, resource_id: str = None,
               changes: dict = None, ip_address: str = None, payload: dict = None):
        """Create an audit log entry"""
        if not admin_user_id:
            return None
        
        db = SessionLocal()
        try:
            log_entry = AdminAuditLog(
                admin_user_id=admin_user_id,
                action=action,
                resource=resource,
                resource_id=resource_id,
                changes=changes or payload,
                ip_address=ip_address
            )
            db.add(log_entry)
            db.commit()
            return log_entry
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create audit log: {e}")
            return None
        finally:
            db.close()


def get_db() -> Session:
    """Dependency injection for FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """Context manager for synchronous code"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables in database"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Database tables initialized")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to initialize database: {e}")
        return False


def test_connection():
    """Test database connectivity"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            logger.info("✓ Database connection successful")
            return True
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        return False


def drop_all_tables():
    """Drop all tables (testing only)"""
    try:
        Base.metadata.drop_all(bind=engine)
        logger.info("✓ All tables dropped")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to drop tables: {e}")
        return False