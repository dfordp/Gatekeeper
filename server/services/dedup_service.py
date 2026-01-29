# server/services/dedup_service.py
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_
from models.ticket import Ticket
from models.embedding import Embedding
import logging

logger = logging.getLogger(__name__)

class DeduplicationService:
    """Duplicate ticket detection via semantic similarity."""
    
    @staticmethod
    def find_similar_tickets(
        db: Session,
        company_id: UUID,
        ticket_id: UUID,
        threshold: float = 0.8,
        limit: int = 10
    ) -> list[dict]:
        """Find similar tickets using embeddings."""
        
        # Get source ticket embeddings
        source_embeddings = db.query(Embedding).filter(
            and_(
                Embedding.ticket_id == ticket_id,
                Embedding.is_active == True
            )
        ).all()
        
        if not source_embeddings:
            logger.warning(f"No embeddings found for ticket {ticket_id}")
            return []
        
        # Get all active embeddings for company
        all_embeddings = db.query(Embedding).filter(
            and_(
                Embedding.company_id == company_id,
                Embedding.is_active == True,
                Embedding.ticket_id != ticket_id
            )
        ).all()
        
        similar = []
        
        # TODO: Calculate cosine similarity between embeddings
        # For now, use simple text similarity
        source_texts = " ".join([e.text_content for e in source_embeddings])
        
        for embedding in all_embeddings:
            # Simple word overlap similarity
            source_words = set(source_texts.lower().split())
            target_words = set(embedding.text_content.lower().split())
            
            if not source_words or not target_words:
                continue
            
            overlap = len(source_words & target_words)
            total = len(source_words | target_words)
            similarity = overlap / total if total > 0 else 0
            
            if similarity >= threshold:
                ticket = db.query(Ticket).filter(
                    Ticket.id == embedding.ticket_id
                ).first()
                
                if ticket:
                    similar.append({
                        "ticket_id": str(ticket.id),
                        "ticket_no": ticket.ticket_no,
                        "subject": ticket.subject,
                        "status": ticket.status,
                        "similarity_score": round(similarity, 2),
                    })
        
        # Sort by similarity score
        similar.sort(key=lambda x: x["similarity_score"], reverse=True)
        return similar[:limit]
    
    @staticmethod
    def get_duplicate_groups(
        db: Session,
        company_id: UUID
    ) -> list[dict]:
        """Find all duplicate ticket groups."""
        
        tickets = db.query(Ticket).filter(
            Ticket.company_id == company_id
        ).all()
        
        duplicates = []
        processed = set()
        
        for i, ticket in enumerate(tickets):
            if ticket.id in processed:
                continue
            
            similar = DeduplicationService.find_similar_tickets(
                db, company_id, ticket.id, threshold=0.7, limit=100
            )
            
            if similar:
                group = {
                    "primary_ticket_id": str(ticket.id),
                    "primary_ticket_no": ticket.ticket_no,
                    "duplicates": similar,
                    "count": len(similar) + 1,
                }
                duplicates.append(group)
                processed.add(ticket.id)
                for dup in similar:
                    processed.add(UUID(dup["ticket_id"]))
        
        return duplicates