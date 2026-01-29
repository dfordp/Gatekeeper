# server/services/search_service.py
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_
from models.embedding import Embedding
from models.ticket import Ticket
import logging

logger = logging.getLogger(__name__)

class SearchService:
    """Semantic and full-text search."""
    
    @staticmethod
    def search_tickets(
        db: Session,
        company_id: UUID,
        query: str,
        semantic: bool = False,
        limit: int = 20
    ) -> list[dict]:
        """Search tickets by query."""
        
        results = []
        
        if semantic:
            # TODO: Use Qdrant for semantic search
            # For now, use simple text search on embeddings
            query_lower = query.lower()
            
            embeddings = db.query(Embedding).filter(
                and_(
                    Embedding.company_id == company_id,
                    Embedding.is_active == True
                )
            ).all()
            
            scored_tickets = {}
            
            for embedding in embeddings:
                if query_lower in embedding.text_content.lower():
                    ticket_id = embedding.ticket_id
                    if ticket_id not in scored_tickets:
                        scored_tickets[ticket_id] = 0
                    scored_tickets[ticket_id] += 1
            
            # Fetch ticket details
            for ticket_id, score in sorted(
                scored_tickets.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:limit]:
                ticket = db.query(Ticket).filter(
                    Ticket.id == ticket_id
                ).first()
                
                if ticket:
                    results.append({
                        "ticket_id": str(ticket.id),
                        "ticket_no": ticket.ticket_no,
                        "subject": ticket.subject,
                        "status": ticket.status,
                        "relevance_score": min(score / 10.0, 1.0),
                    })
        else:
            # Full-text search on ticket fields
            query_lower = f"%{query.lower()}%"
            
            tickets = db.query(Ticket).filter(
                and_(
                    Ticket.company_id == company_id,
                    (
                        Ticket.subject.ilike(query_lower) |
                        Ticket.detailed_description.ilike(query_lower) |
                        Ticket.ticket_no.ilike(query_lower)
                    )
                )
            ).limit(limit).all()
            
            for ticket in tickets:
                results.append({
                    "ticket_id": str(ticket.id),
                    "ticket_no": ticket.ticket_no,
                    "subject": ticket.subject,
                    "status": ticket.status,
                })
        
        return results