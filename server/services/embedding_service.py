from uuid import UUID
from sqlalchemy.orm import Session
from models.embedding import Embedding, EmbeddingSourceType
from models.rca import RCA
from models.ticket import Ticket
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class EmbeddingService:
    """Vector embedding management."""
    
    @staticmethod
    def generate_rca_embeddings(
        db: Session,
        company_id: UUID,
        rca: RCA
    ) -> list[Embedding]:
        """Generate embeddings for approved RCA."""
        
        embeddings = []
        
        # Create embedding for RCA content
        if rca.root_cause:
            embedding = Embedding(
                company_id=company_id,
                ticket_id=rca.ticket_id,
                source_type=EmbeddingSourceType.RCA,
                chunk_index=0,
                text_content=f"Root Cause: {rca.root_cause}\n\nResolution: {rca.resolution}\n\nPrevention: {rca.prevention}",
                is_active=True,
            )
            db.add(embedding)
            embeddings.append(embedding)
        
        db.flush()
        logger.info(f"Generated {len(embeddings)} embeddings for RCA {rca.id}")
        return embeddings
    
    @staticmethod
    def generate_ticket_embeddings(
        db: Session,
        company_id: UUID,
        ticket: Ticket
    ) -> list[Embedding]:
        """Generate embeddings for ticket."""
        
        embeddings = []
        
        # Create embedding for ticket summary
        if ticket.summary:
            embedding = Embedding(
                company_id=company_id,
                ticket_id=ticket.id,
                source_type=EmbeddingSourceType.TICKET_SUMMARY,
                chunk_index=0,
                text_content=ticket.summary,
                is_active=True,
            )
            db.add(embedding)
            embeddings.append(embedding)
        
        # Create embedding for ticket description
        if ticket.detailed_description:
            embedding = Embedding(
                company_id=company_id,
                ticket_id=ticket.id,
                source_type=EmbeddingSourceType.TICKET_DESCRIPTION,
                chunk_index=0,
                text_content=ticket.detailed_description,
                is_active=True,
            )
            db.add(embedding)
            embeddings.append(embedding)
        
        db.flush()
        logger.info(f"Generated {len(embeddings)} embeddings for ticket {ticket.ticket_no}")
        return embeddings
    
    @staticmethod
    def deprecate_embeddings(
        db: Session,
        source_type: EmbeddingSourceType,
        reference_id: UUID,
        reason: str
    ):
        """Deprecate embeddings (soft-delete)."""
        
        embeddings = db.query(Embedding).filter(
            Embedding.source_type == source_type,
            Embedding.is_active == True,
        ).filter(
            (Embedding.ticket_id == reference_id) |
            (Embedding.attachment_id == reference_id)
        ).all()
        
        for embedding in embeddings:
            embedding.is_active = False
            embedding.deprecated_at = datetime.utcnow()
            embedding.deprecation_reason = reason
        
        db.flush()
        logger.info(f"Deprecated {len(embeddings)} embeddings for {source_type}")
    
    @staticmethod
    def get_active_embeddings(
        db: Session,
        company_id: UUID,
        ticket_id: UUID = None,
        source_type: EmbeddingSourceType = None
    ) -> list[Embedding]:
        """Get active embeddings (for search)."""
        
        query = db.query(Embedding).filter(
            Embedding.company_id == company_id,
            Embedding.is_active == True
        )
        
        if ticket_id:
            query = query.filter(Embedding.ticket_id == ticket_id)
        
        if source_type:
            query = query.filter(Embedding.source_type == source_type)
        
        return query.all()