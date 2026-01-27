#!/usr/bin/env python3
"""
Search Service for Gatekeeper Support Platform

Responsibilities:
1. Embed user queries
2. Search Qdrant for similar solutions
3. Filter by company_id and confidence threshold
4. Return matching tickets or recommend new ticket creation
5. Deduplicate before ticket creation

Usage:
    from search_service import SearchService
    
    # Search for similar solutions
    result = SearchService.search_similar_solutions(
        query_text="I can't save files in Creo",
        company_id=company_uuid,
        category="Upload or Save"
    )
    
    # Decide if new ticket needed
    should_create = SearchService.should_create_new_ticket(
        query_text="Cannot save files",
        company_id=company_uuid
    )
"""

import os
import sys
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, Ticket, TicketEvent, Embedding, Company, User
from embedding_service import EmbeddingService
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)


class SearchService:
    """Service for searching similar solutions and deduplicating support requests."""
    
    # Default confidence thresholds
    DEFAULT_THRESHOLD = 0.75
    
    @staticmethod
    def search_similar_solutions(
        query_text: str,
        company_id: str,
        category: Optional[str] = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Search for similar solutions using semantic search.
        Returns top matches ranked by confidence score.
        
        Args:
            query_text: User's query/problem description
            company_id: UUID of the company (for isolation)
            category: Optional ticket category filter
            limit: Max results to return (default 5)
            
        Returns:
            Dict with search results and metadata
        """
        logger.info(f"Searching for similar solutions: '{query_text[:60]}...'")
        
        # Embed the query
        query_vector = EmbeddingService.get_embedding_vector(query_text)
        if not query_vector:
            logger.error("Failed to embed query")
            return {
                "status": "error",
                "message": "Failed to embed query",
                "confidence": 0.0
            }
        
        # Determine confidence threshold for this category
        threshold = EmbeddingService.get_confidence_threshold(category or "Other")
        logger.debug(f"Using confidence threshold: {threshold}")
        
        # Import Qdrant wrapper
        try:
            from qdrant_wrapper import qdrant
        except ImportError:
            logger.error("Qdrant wrapper not available")
            return {
                "status": "error",
                "message": "Search service not available",
                "confidence": 0.0
            }
        
        # Search Qdrant
        logger.debug(f"Querying Qdrant (company: {company_id}, category: {category})")
        qdrant_results = qdrant.search(
            query_vector=query_vector,
            company_id=company_id,
            limit=limit,
            score_threshold=threshold,
            category=category
        )
        
        # No results found
        if not qdrant_results:
            logger.info("No solutions found above confidence threshold")
            return {
                "status": "no_solution_found",
                "confidence": 0.0,
                "threshold": threshold,
                "message": f"No relevant solutions found (threshold: {threshold})"
            }
        
        # Get best match
        best_match = qdrant_results[0]
        best_confidence = best_match["score"]
        
        logger.info(f"Found solution with confidence: {best_confidence:.3f}")
        
        # Fetch full ticket details from Postgres
        db = SessionLocal()
        try:
            payload = best_match.get("payload", {})
            ticket_id = payload.get("ticket_id")
            
            if not ticket_id:
                logger.error("No ticket_id in search result payload")
                return {
                    "status": "error",
                    "message": "Invalid search result",
                    "confidence": 0.0
                }
            
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            
            if not ticket:
                logger.error(f"Ticket not found: {ticket_id}")
                return {
                    "status": "error",
                    "message": "Ticket not found",
                    "confidence": 0.0
                }
            
            # Get resolution from latest TicketEvent
            resolution_event = db.query(TicketEvent).filter(
                TicketEvent.ticket_id == ticket_id,
                TicketEvent.event_type == "resolution_added"
            ).order_by(TicketEvent.created_at.desc()).first()
            
            resolution_text = None
            if resolution_event and resolution_event.payload:
                resolution_text = resolution_event.payload.get("resolution_text")
            
            # Build response
            response = {
                "status": "solution_found",
                "confidence": best_confidence,
                "threshold": threshold,
                "ticket": {
                    "id": str(ticket.id),
                    "ticket_no": ticket.ticket_no,
                    "subject": ticket.subject,
                    "summary": ticket.summary,
                    "category": ticket.category,
                    "level": ticket.level,
                    "status": ticket.status,
                    "created_at": ticket.created_at.isoformat(),
                    "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None
                },
                "resolution": resolution_text,
                "match_info": {
                    "source_type": payload.get("source_type"),
                    "chunk_index": payload.get("chunk_index", 0)
                },
                "similar_matches": []
            }
            
            # Add other matches
            for result in qdrant_results[1:]:
                result_payload = result.get("payload", {})
                similar_ticket_id = result_payload.get("ticket_id")
                
                if similar_ticket_id:
                    similar_ticket = db.query(Ticket).filter(
                        Ticket.id == similar_ticket_id
                    ).first()
                    
                    if similar_ticket:
                        response["similar_matches"].append({
                            "ticket_no": similar_ticket.ticket_no,
                            "confidence": result["score"],
                            "source_type": result_payload.get("source_type"),
                            "category": similar_ticket.category
                        })
            
            logger.info(f"Returning solution: {ticket.ticket_no}")
            return response
            
        finally:
            db.close()
    
    @staticmethod
    def should_create_new_ticket(
        query_text: str,
        company_id: str,
        category: Optional[str] = None
    ) -> bool:
        """
        Determine if a new ticket should be created.
        Returns True if no good solution found.
        Returns False if a solution exists (use existing ticket).
        
        Args:
            query_text: User's query/problem description
            company_id: UUID of the company
            category: Optional ticket category
            
        Returns:
            True if new ticket should be created, False if solution found
        """
        result = SearchService.search_similar_solutions(
            query_text=query_text,
            company_id=company_id,
            category=category,
            limit=1
        )
        
        if result.get("status") == "solution_found":
            confidence = result.get("confidence", 0)
            logger.info(f"Solution found (confidence {confidence:.3f}), skip new ticket")
            return False
        
        logger.info("No solution found, create new ticket")
        return True
    
    @staticmethod
    def get_ticket_with_embeddings(ticket_id: str) -> Dict[str, Any]:
        """
        Get ticket details with all related embeddings.
        Useful for support dashboard and audit trails.
        
        Args:
            ticket_id: UUID of the ticket
            
        Returns:
            Dict with ticket and embedding information
        """
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            
            if not ticket:
                return {"error": "Ticket not found"}
            
            # Get all embeddings for this ticket
            embeddings = db.query(Embedding).filter(
                Embedding.ticket_id == ticket_id
            ).order_by(
                Embedding.source_type,
                Embedding.chunk_index
            ).all()
            
            # Separate active and inactive
            active_embeddings = [e for e in embeddings if e.is_active]
            inactive_embeddings = [e for e in embeddings if not e.is_active]
            
            # Get all events
            events = db.query(TicketEvent).filter(
                TicketEvent.ticket_id == ticket_id
            ).order_by(TicketEvent.created_at).all()
            
            return {
                "ticket": {
                    "id": str(ticket.id),
                    "ticket_no": ticket.ticket_no,
                    "subject": ticket.subject,
                    "category": ticket.category,
                    "level": ticket.level,
                    "status": ticket.status,
                    "summary": ticket.summary,
                    "detailed_description": ticket.detailed_description,
                    "created_at": ticket.created_at.isoformat(),
                    "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
                    "reopened_at": ticket.reopened_at.isoformat() if ticket.reopened_at else None
                },
                "embeddings": {
                    "total": len(embeddings),
                    "active": len(active_embeddings),
                    "inactive": len(inactive_embeddings),
                    "details": [
                        {
                            "id": str(e.id),
                            "source_type": e.source_type,
                            "chunk_index": e.chunk_index,
                            "is_active": e.is_active,
                            "content_length": len(e.text_content),
                            "created_at": e.created_at.isoformat(),
                            "deprecated_at": e.deprecated_at.isoformat() if e.deprecated_at else None,
                            "deprecation_reason": e.deprecation_reason
                        }
                        for e in embeddings
                    ]
                },
                "events": [
                    {
                        "id": str(e.id),
                        "type": e.event_type,
                        "created_at": e.created_at.isoformat(),
                        "actor_id": str(e.actor_user_id),
                        "payload": e.payload
                    }
                    for e in events
                ]
            }
            
        finally:
            db.close()
    
    @staticmethod
    def get_company_search_stats(company_id: str) -> Dict[str, Any]:
        """
        Get search statistics for a company.
        Useful for monitoring and debugging.
        
        Args:
            company_id: UUID of the company
            
        Returns:
            Dict with statistics
        """
        db = SessionLocal()
        try:
            # Count tickets
            total_tickets = db.query(Ticket).filter(
                Ticket.company_id == company_id
            ).count()
            
            resolved_tickets = db.query(Ticket).filter(
                Ticket.company_id == company_id,
                Ticket.status == "resolved"
            ).count()
            
            # Count embeddings
            total_embeddings = db.query(Embedding).filter(
                Embedding.company_id == company_id
            ).count()
            
            active_embeddings = db.query(Embedding).filter(
                Embedding.company_id == company_id,
                Embedding.is_active == True
            ).count()
            
            inactive_embeddings = total_embeddings - active_embeddings
            
            # Breakdown by source type
            source_types = {}
            embeddings = db.query(Embedding).filter(
                Embedding.company_id == company_id
            ).all()
            
            for emb in embeddings:
                key = f"{emb.source_type}({'active' if emb.is_active else 'inactive'})"
                source_types[key] = source_types.get(key, 0) + 1
            
            return {
                "company_id": str(company_id),
                "tickets": {
                    "total": total_tickets,
                    "resolved": resolved_tickets,
                    "open": total_tickets - resolved_tickets
                },
                "embeddings": {
                    "total": total_embeddings,
                    "active": active_embeddings,
                    "inactive": inactive_embeddings,
                    "by_source": source_types
                },
                "search_potential": f"{active_embeddings}/{total_tickets}" if total_tickets > 0 else "0/0"
            }
            
        finally:
            db.close()