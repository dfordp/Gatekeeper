# scripts/__init__.py
"""
Support Platform Backend Services

Modules:
  - database: Database connection, models, and session management
"""

from .database import (
    init_db,
    test_connection,
    get_db,
    get_db_context,
    Company,
    User,
    Ticket,
    TicketEvent,
    Attachment,
    AttachmentEvent,
    Embedding,
    Base,
    SessionLocal,
    engine,
)

__all__ = [
    "init_db",
    "test_connection",
    "get_db",
    "get_db_context",
    "Company",
    "User",
    "Ticket",
    "TicketEvent",
    "Attachment",
    "AttachmentEvent",
    "Embedding",
    "Base",
    "SessionLocal",
    "engine",
]