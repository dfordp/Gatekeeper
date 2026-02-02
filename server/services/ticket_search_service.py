# server/services/ticket_search_service.py
"""
Ticket Search Service - Semantic search for similar tickets

Integrates with Qdrant to find similar support tickets based on user queries.
Used by Telegram chatbot and web interface to suggest existing solutions.
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.models import Distance
from core.database import SessionLocal, Ticket
from services.embedding_api_client import EmbeddingAPIClient
from core.logger import get_logger

logger = get_logger(__name__)


class TicketSearchService:
    """Service for semantic ticket search"""
    
    QDRANT_URL = "http://qdrant:6333"
    QDRANT_API_KEY = "qdrant_secure_key_123"
    QDRANT_COLLECTION = "tickets"
    
    @staticmethod
    def _get_qdrant_client() -> QdrantClient:
        """Get Qdrant client"""
        return QdrantClient(
            url=TicketSearchService.QDRANT_URL,
            api_key=TicketSearchService.QDRANT_API_KEY,
            timeout=30.0
        )
    
    @staticmethod
    def search_similar_tickets(
        query: str,
        limit: int = 5,
        threshold: float = 0.5,
        company_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar tickets using semantic similarity.
        
        Args:
            query: Search query text
            limit: Max results to return
            threshold: Minimum similarity score (0-1)
            company_id: Optional company filter
            
        Returns:
            List of similar tickets with metadata
        """
        db = SessionLocal()
        try:
            # Generate embedding for query
            embedding_client = EmbeddingAPIClient()
            query_vector = embedding_client.get_embedding_vector(query)
            
            if not query_vector:
                logger.warning(f"Failed to generate embedding for query: {query}")
                return []
            
            logger.info(f"Searching for tickets similar to: {query}")
            
            # Search in Qdrant
            qdrant_client = TicketSearchService._get_qdrant_client()
            qdrant_results = qdrant_client.search(
                collection_name=TicketSearchService.QDRANT_COLLECTION,
                query_vector=query_vector,
                limit=limit * 2,  # Get more to filter
                score_threshold=threshold
            )
            
            # Deduplicate and fetch ticket details
            ticket_ids = set()
            results = []
            
            for qdrant_point in qdrant_results:
                payload = qdrant_point.payload
                ticket_id = payload.get("ticket_id")
                
                # Skip duplicates
                if ticket_id in ticket_ids:
                    continue
                
                ticket_ids.add(ticket_id)
                
                # Fetch ticket details
                try:
                    ticket = db.query(Ticket).filter(
                        Ticket.id == UUID(ticket_id)
                    ).first()
                    
                    if not ticket:
                        continue
                    
                    # Filter by company if specified
                    if company_id and str(ticket.company_id) != company_id:
                        continue
                    
                    # Build result with ticket details + embedding metadata
                    result = {
                        "similarity_score": qdrant_point.score,
                        "ticket_id": ticket_id,
                        "ticket_no": ticket.ticket_no,
                        "subject": ticket.subject,
                        "status": ticket.status,
                        "category": ticket.category,
                        "assigned_to": ticket.assigned_engineer.name if ticket.assigned_engineer else None,
                        "embedding_source_type": payload.get("source_type"),
                        "embedding_text": payload.get("text", "")[:150],
                        "has_rca": ticket.rca is not None,
                        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                    }
                    
                    results.append(result)
                    
                    if len(results) >= limit:
                        break
                
                except Exception as e:
                    logger.warning(f"Error fetching ticket {ticket_id}: {e}")
                    continue
            
            logger.info(f"Found {len(results)} similar tickets")
            return results
        
        except Exception as e:
            logger.error(f"Ticket search failed: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def format_search_results_for_telegram(
        results: List[Dict[str, Any]],
        query: str
    ) -> str:
        """
        Format search results for Telegram message.
        
        Args:
            results: List of similar tickets
            query: Original search query
            
        Returns:
            Formatted message string
        """
        if not results:
            return (
                f"❌ No similar tickets found for: '{query}'\n\n"
                f"This might be a new issue. Feel free to create a new ticket!"
            )
        
        message = f"🔍 Found {len(results)} similar ticket(s) for: '{query}'\n\n"
        
        for i, ticket in enumerate(results, 1):
            score_percent = int(ticket["similarity_score"] * 100)
            status_emoji = "✅" if ticket["status"] == "closed" else "🟡"
            rca_emoji = "📋" if ticket["has_rca"] else ""
            
            message += (
                f"{i}. {status_emoji} {ticket['ticket_no']} - {ticket['subject']}\n"
                f"   Match: {score_percent}% | Category: {ticket['category']} {rca_emoji}\n"
                f"   Status: {ticket['status'].upper()}\n"
            )
            
            if ticket["assigned_to"]:
                message += f"   Assigned to: {ticket['assigned_to']}\n"
            
            message += "\n"
        
        message += "💡 Check these tickets for solutions, or create a new one if your issue is different."
        return message
    
    @staticmethod
    def get_ticket_details(ticket_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full ticket details for display.
        
        Args:
            ticket_id: Ticket UUID
            
        Returns:
            Ticket details or None
        """
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(
                Ticket.id == UUID(ticket_id)
            ).first()
            
            if not ticket:
                return None
            
            return {
                "id": str(ticket.id),
                "ticket_no": ticket.ticket_no,
                "subject": ticket.subject,
                "description": ticket.detailed_description,
                "status": ticket.status,
                "category": ticket.category,
                "level": ticket.level,
                "company": ticket.company.name if ticket.company else None,
                "assigned_to": ticket.assigned_engineer.name if ticket.assigned_engineer else None,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
                "rca": {
                    "description": ticket.rca.root_cause_description,
                    "factors": ticket.rca.contributing_factors,
                    "prevention": ticket.rca.prevention_measures,
                    "steps": ticket.rca.resolution_steps,
                    "attachments": [
                        {
                            "id": str(att.id),
                            "file_path": att.file_path,
                            "type": att.type,
                            "created_at": att.created_at.isoformat() if att.created_at else None
                        }
                        for att in ticket.rca.attachments
                    ] if ticket.rca.attachments else []
                } if ticket.rca else None,
                "attachments_count": len(ticket.attachments) if ticket.attachments else 0,
            }
        except Exception as e:
            logger.error(f"Error fetching ticket details: {e}")
            return None
        finally:
            db.close()

    @staticmethod
    def get_rca_with_attachments(ticket_id: str) -> Optional[Dict[str, Any]]:
        """
        Get RCA with visual guide and attachments for ticket display.
        
        Args:
            ticket_id: Ticket UUID
            
        Returns:
            RCA with attachments or None
        """
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(
                Ticket.id == UUID(ticket_id)
            ).first()
            
            if not ticket or not ticket.rca:
                return None
            
            rca = ticket.rca
            
            # Fetch RCA attachments from the relationship
            attachments = []
            if rca and rca.attachments:
                attachments = [
                    {
                        "id": str(att.id),
                        "file_path": att.file_path,
                        "type": att.type,
                        "created_at": att.created_at.isoformat() if att.created_at else None
                    }
                    for att in rca.attachments
                ]
            
            return {
                "id": str(rca.id),
                "root_cause": rca.root_cause_description,
                "contributing_factors": rca.contributing_factors,
                "prevention_measures": rca.prevention_measures,
                "resolution_steps": rca.resolution_steps,
                "attachments": attachments,
                "created_by": rca.created_by_user.name if rca.created_by_user else None,
            }
        except Exception as e:
            logger.error(f"Error fetching RCA: {e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def format_rca_solution_for_telegram(rca: Dict[str, Any], ticket_no: str) -> str:
        """
        Format RCA as a solution guide for Telegram display.
        Shows visual guide and step-by-step resolution.
        
        Args:
            rca: RCA data dict
            ticket_no: Ticket number for reference
            
        Returns:
            Formatted Telegram message
        """
        if not rca:
            return "📋 No solution guide available for this ticket yet"
        
        message = f"💡 **Solution for {ticket_no}**\n\n"
        
        message += f"🔍 **What was the problem?**\n{rca['root_cause']}\n\n"
        
        if rca.get('contributing_factors'):
            message += "⚠️ **Why did it happen?**\n"
            for factor in rca['contributing_factors'][:3]:  # Limit to 3 factors
                message += f"• {factor}\n"
            message += "\n"
        
        if rca.get('resolution_steps'):
            message += "✅ **How to fix it:**\n"
            for i, step in enumerate(rca['resolution_steps'][:5], 1):  # Limit to 5 steps
                message += f"{i}. {step}\n"
            message += "\n"
        
        if rca.get('prevention_measures'):
            message += f"🛡️ **How to prevent it:**\n{rca['prevention_measures']}\n\n"
        
        if rca.get('attachments'):
            message += f"📎 **Reference Materials:** {len(rca['attachments'])} file(s)\n"
        
        return message