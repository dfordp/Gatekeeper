from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from contextlib import contextmanager
import logging
from config import settings

logger = logging.getLogger(__name__)

# Create engine
engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    poolclass=NullPool if settings.debug else None,
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

def get_db() -> Session:
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_db_context():
    """Context manager for sync code."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database - create all tables."""
    from models import (
        Company, User, Ticket, TicketEvent,
        Attachment, AttachmentEvent,
        RCA, RCAEvent, Embedding
    )
    
    try:
        # Import base to ensure all models are registered
        from models.base import Base
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Database tables initialized")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to initialize database: {e}")
        return False

def drop_all():
    """Drop all tables (testing only)."""
    from models.base import Base
    Base.metadata.drop_all(bind=engine)
    logger.info("✓ All tables dropped")