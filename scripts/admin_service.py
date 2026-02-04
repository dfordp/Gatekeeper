#!/usr/bin/env python3
"""
Admin Service for Gatekeeper Support Platform

Provides admin operations for quality control and maintenance:
1. Deprecate embeddings (mark as incorrect)
2. Find duplicate tickets
3. View embedding audit trails
4. Manage ticket relationships

Usage:
    from admin_service import AdminService
    
    # Deprecate an embedding
    AdminService.deprecate_embedding(
        embedding_id=embedding_id,
        reason="incorrect_analysis",
        actor_user_id=admin_id
    )
    
    # Find related tickets
    related = AdminService.find_related_tickets(
        primary_ticket_id=ticket_id,
        company_id=company_id
    )
"""

import os
import sys
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import uuid

from server.utils.datetime_utils import to_iso_string

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, Ticket, TicketEvent, Embedding, Company
from qdrant_wrapper import qdrant
from event_queue import EventQueue, EventType
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)


class AdminService:
    """Service for administrative operations and quality control."""
    
    @staticmethod
    def deprecate_embedding(
        embedding_id: str,
        reason: str,
        actor_user_id: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Mark an embedding as deprecated (incorrect/low quality).
        
        Updates both PostgreSQL and Qdrant to exclude from search results.
        
        Args:
            embedding_id: UUID of the embedding to deprecate
            reason: Reason for deprecation (e.g., "incorrect_analysis", "low_quality")
            actor_user_id: UUID of admin performing action
            notes: Optional detailed notes
            
        Returns:
            Dict with deprecation result
        """
        logger.info(f"Deprecating embedding {embedding_id}")
        db = SessionLocal()
        
        try:
            # Find embedding
            embedding = db.query(Embedding).filter(
                Embedding.id == embedding_id
            ).first()
            
            if not embedding:
                return {
                    "success": False,
                    "error": "Embedding not found"
                }
            
            if not embedding.is_active:
                return {
                    "success": False,
                    "error": "Embedding is already deprecated"
                }
            
            # Deprecate in PostgreSQL
            embedding.is_active = False
            embedding.deprecated_at = datetime.utcnow()
            embedding.deprecation_reason = reason
            
            # Create audit event
            event = TicketEvent(
                ticket_id=embedding.ticket_id,
                event_type="embedding_deprecated",
                actor_user_id=actor_user_id,
                payload={
                    "embedding_id": str(embedding.id),
                    "reason": reason,
                    "notes": notes,
                    "source_type": embedding.source_type
                }
            )
            db.add(event)
            db.commit()
            
            # Deprecate in Qdrant
            if qdrant:
                qdrant.mark_inactive(embedding_id, reason)
            
            # Emit event for listeners
            EventQueue.emit(
                EventType.EMBEDDING_DEPRECATED,
                embedding_id=embedding_id,
                ticket_id=str(embedding.ticket_id),
                reason=reason
            )
            
            logger.info(f"✓ Deprecated embedding {embedding_id}")
            
            return {
                "success": True,
                "embedding_id": str(embedding.id),
                "ticket_id": str(embedding.ticket_id),
                "reason": reason,
                "deprecated_at": to_iso_string(embedding.deprecated_at)
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to deprecate embedding: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            db.close()
    
    @staticmethod
    def find_related_tickets(
        primary_ticket_id: str,
        company_id: str,
        include_resolved: bool = False
    ) -> Dict[str, Any]:
        """
        Find tickets that are related to a primary ticket.
        
        Uses event trails and manual linking to identify duplicates
        and related issues.
        
        Args:
            primary_ticket_id: UUID of the primary ticket
            company_id: UUID of the company
            include_resolved: Include resolved tickets in results
            
        Returns:
            Dict with related tickets and relationships
        """
        logger.info(f"Finding related tickets for {primary_ticket_id}")
        db = SessionLocal()
        
        try:
            # Get primary ticket
            primary_ticket = db.query(Ticket).filter(
                Ticket.id == primary_ticket_id,
                Ticket.company_id == company_id
            ).first()
            
            if not primary_ticket:
                return {
                    "success": False,
                    "error": "Ticket not found"
                }
            
            related = {
                "primary_ticket": {
                    "id": str(primary_ticket.id),
                    "ticket_no": primary_ticket.ticket_no,
                    "subject": primary_ticket.subject,
                    "status": primary_ticket.status
                },
                "duplicates": [],
                "related_issues": [],
                "linking_events": []
            }
            
            # Find linking events
            link_events = db.query(TicketEvent).filter(
                TicketEvent.ticket_id == primary_ticket_id,
                TicketEvent.event_type.in_(['linked_to_ticket', 'has_duplicates'])
            ).all()
            
            for event in link_events:
                related["linking_events"].append({
                    "event_type": event.event_type,
                    "created_at": to_iso_string(event.created_at),
                    "payload": event.payload
                })
                
                if event.event_type == 'has_duplicates':
                    # This ticket has duplicates
                    duplicate_ids = event.payload.get('related_tickets', [])
                    for dup_id in duplicate_ids:
                        dup_ticket = db.query(Ticket).filter(
                            Ticket.id == dup_id
                        ).first()
                        
                        if dup_ticket:
                            related["duplicates"].append({
                                "id": str(dup_ticket.id),
                                "ticket_no": dup_ticket.ticket_no,
                                "subject": dup_ticket.subject,
                                "status": dup_ticket.status,
                                "created_at": to_iso_string(dup_ticket.created_at)
                            })
            
            # Find tickets with similar embeddings
            primary_embeddings = db.query(Embedding).filter(
                Embedding.ticket_id == primary_ticket_id,
                Embedding.is_active == True
            ).all()
            
            if primary_embeddings:
                # Find other tickets with same source type
                for emb in primary_embeddings:
                    similar_embeddings = db.query(Embedding).filter(
                        Embedding.ticket_id != primary_ticket_id,
                        Embedding.company_id == company_id,
                        Embedding.source_type == emb.source_type,
                        Embedding.is_active == True
                    ).all()
                    
                    for sim_emb in similar_embeddings:
                        ticket = sim_emb.ticket
                        if include_resolved or ticket.status != 'resolved':
                            related["related_issues"].append({
                                "id": str(ticket.id),
                                "ticket_no": ticket.ticket_no,
                                "subject": ticket.subject,
                                "status": ticket.status,
                                "similarity_source": emb.source_type
                            })
            
            # Remove duplicates
            related["related_issues"] = list({
                r["id"]: r for r in related["related_issues"]
            }.values())
            
            logger.info(f"✓ Found {len(related['duplicates'])} duplicates, {len(related['related_issues'])} related")
            
            return {
                "success": True,
                **related
            }
            
        except Exception as e:
            logger.error(f"Failed to find related tickets: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            db.close()
    
    @staticmethod
    def get_embedding_audit_trail(embedding_id: str) -> Dict[str, Any]:
        """
        Get the complete audit trail for an embedding.
        
        Shows creation, usage, and deprecation history.
        
        Args:
            embedding_id: UUID of the embedding
            
        Returns:
            Dict with audit trail
        """
        logger.info(f"Getting audit trail for embedding {embedding_id}")
        db = SessionLocal()
        
        try:
            # Get embedding
            embedding = db.query(Embedding).filter(
                Embedding.id == embedding_id
            ).first()
            
            if not embedding:
                return {
                    "success": False,
                    "error": "Embedding not found"
                }
            
            # Get associated ticket events
            events = db.query(TicketEvent).filter(
                TicketEvent.ticket_id == embedding.ticket_id
            ).order_by(TicketEvent.created_at).all()
            
            return {
                "success": True,
                "embedding": {
                    "id": str(embedding.id),
                    "ticket_id": str(embedding.ticket_id),
                    "source_type": embedding.source_type,
                    "chunk_index": embedding.chunk_index,
                    "is_active": embedding.is_active,
                    "created_at": to_iso_string(embedding.created_at),
                    "deprecated_at": to_iso_string(embedding.deprecated_at) if embedding.deprecated_at else None,
                    "deprecation_reason": embedding.deprecation_reason,
                    "content_preview": embedding.text_content[:200]
                },
                "ticket_events": [
                    {
                        "event_type": e.event_type,
                        "created_at": to_iso_string(e.created_at),
                        "actor_id": str(e.actor_user_id),
                        "payload": e.payload
                    }
                    for e in events
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to get audit trail: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            db.close()
    
    @staticmethod
    def get_company_audit_stats(company_id: str) -> Dict[str, Any]:
        """
        Get audit statistics for a company.
        
        Shows deprecation rates, linking activity, etc.
        
        Args:
            company_id: UUID of the company
            
        Returns:
            Dict with statistics
        """
        logger.info(f"Getting audit stats for company {company_id}")
        db = SessionLocal()
        
        try:
            # Count tickets
            total_tickets = db.query(Ticket).filter(
                Ticket.company_id == company_id
            ).count()
            
            # Count embeddings
            total_embeddings = db.query(Embedding).filter(
                Embedding.company_id == company_id
            ).count()
            
            active_embeddings = db.query(Embedding).filter(
                Embedding.company_id == company_id,
                Embedding.is_active == True
            ).count()
            
            deprecated_embeddings = total_embeddings - active_embeddings
            
            # Count deprecation events
            deprecation_events = db.query(TicketEvent).filter(
                TicketEvent.event_type == 'embedding_deprecated'
            ).all()
            
            # Count linking events
            linking_events = db.query(TicketEvent).filter(
                TicketEvent.event_type.in_(['linked_to_ticket', 'has_duplicates'])
            ).all()
            
            # Calculate deprecation rate
            deprecation_rate = (deprecated_embeddings / total_embeddings * 100) if total_embeddings > 0 else 0
            
            return {
                "success": True,
                "company_id": company_id,
                "tickets": {
                    "total": total_tickets
                },
                "embeddings": {
                    "total": total_embeddings,
                    "active": active_embeddings,
                    "deprecated": deprecated_embeddings,
                    "deprecation_rate_percent": round(deprecation_rate, 2)
                },
                "audit_events": {
                    "deprecation_events": len(deprecation_events),
                    "linking_events": len(linking_events),
                    "total_audit_events": len(deprecation_events) + len(linking_events)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get audit stats: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            db.close()