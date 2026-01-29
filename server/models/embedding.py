# server/models/embedding.py
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index, Enum, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from .base import Base

class EmbeddingSourceType(str, enum.Enum):
    """Source of embedding content."""
    TICKET_SUMMARY = "ticket_summary"
    TICKET_DESCRIPTION = "ticket_description"
    RESOLUTION = "resolution"
    RCA = "rca"
    LOG_SNIPPET = "log_snippet"

class Embedding(Base):
    """Vector embeddings for semantic search."""
    __tablename__ = "embedding"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("company.id"), nullable=False)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("ticket.id"), nullable=False)
    attachment_id = Column(UUID(as_uuid=True), ForeignKey("attachment.id"), nullable=True)
    
    source_type = Column(Enum(EmbeddingSourceType), nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    text_content = Column(Text, nullable=False)
    vector_id = Column(String(100), nullable=True)  # Qdrant vector ID
    
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    deprecated_at = Column(DateTime, nullable=True)
    deprecation_reason = Column(String(100), nullable=True)
    
    # Relationships
    company = relationship("Company", back_populates="embeddings")
    ticket = relationship("Ticket", back_populates="embeddings")
    attachment = relationship("Attachment", back_populates="embeddings")
    
    __table_args__ = (
        Index("idx_embedding_company_active", "company_id", "is_active"),
        Index("idx_embedding_ticket", "ticket_id"),
        Index("idx_embedding_attachment", "attachment_id"),
    )
    
    def __repr__(self):
        return f"<Embedding {self.source_type}>"