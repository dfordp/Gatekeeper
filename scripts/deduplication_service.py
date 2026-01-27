#!/usr/bin/env python3
"""
Deduplication Service for Gatekeeper Support Platform

Integrates search service into ticket creation workflow.

Responsibilities:
1. Check for duplicate tickets before creation
2. Provide deduplication recommendations
3. Link similar existing tickets
4. Create new tickets only when necessary

Workflow:
    1. User submits problem description
    2. DuplicateService checks for similar solutions
    3. If found: Return existing ticket + resolution
    4. If not found: Allow creation of new ticket

Usage:
    from deduplication_service import DuplicateService
    
    # Check if new ticket is needed
    dedup_result = DuplicateService.check_for_duplicates(
        query_text="Cannot save files in Creo",
        company_id=company_uuid,
        category="Upload or Save"
    )
    
    if dedup_result["should_create_ticket"]:
        # Create new ticket
        pass
    else:
        # Show existing solution
        existing_ticket = dedup_result["existing_ticket"]
"""

import os
import sys
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, Ticket, TicketEvent, User
from search_service import SearchService
from embedding_service import EmbeddingService
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)


class DuplicateService:
    """Service for checking and handling duplicate support requests."""
    
    @staticmethod
    def check_for_duplicates(
        query_text: str,
        company_id: str,
        category: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check if a problem description matches existing solutions.
        
        This is the main entry point for deduplication.
        Call this BEFORE creating a new ticket.
        
        Args:
            query_text: User's problem description
            company_id: UUID of the company
            category: Optional ticket category
            user_id: UUID of the user submitting (for audit trail)
            
        Returns:
            Dict with deduplication result and recommendations
        """
        logger.info(f"Checking for duplicates: '{query_text[:60]}...'")
        
        # Search for similar solutions
        search_result = SearchService.search_similar_solutions(
            query_text=query_text,
            company_id=company_id,
            category=category,
            limit=3
        )
        
        # Determine if we should create a new ticket
        should_create = search_result.get("status") == "no_solution_found"
        
        response = {
            "should_create_ticket": should_create,
            "search_result": search_result,
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "category": category
        }
        
        if not should_create:
            # Found existing solution
            ticket_info = search_result.get("ticket", {})
            response["existing_ticket"] = {
                "id": ticket_info.get("id"),
                "ticket_no": ticket_info.get("ticket_no"),
                "subject": ticket_info.get("subject"),
                "status": ticket_info.get("status"),
                "category": ticket_info.get("category"),
                "confidence": search_result.get("confidence"),
                "resolution": search_result.get("resolution")
            }
            response["message"] = f"Found similar solution: {ticket_info.get('ticket_no')}"
            logger.info(f"Duplicate detected: {ticket_info.get('ticket_no')}")
        else:
            response["message"] = "No similar solution found, proceed with new ticket"
            logger.info("No duplicates found, new ticket can be created")
        
        return response
    
    @staticmethod
    def create_ticket_with_dedup(
        subject: str,
        detailed_description: str,
        company_id: str,
        raised_by_user_id: str,
        category: Optional[str] = None,
        summary: Optional[str] = None,
        level: Optional[str] = None,
        assigned_engineer_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new ticket with automatic deduplication.
        
        If a similar solution exists, returns that instead of creating new ticket.
        Otherwise, creates the ticket and triggers embedding creation.
        
        Args:
            subject: Ticket subject
            detailed_description: Full problem description
            company_id: UUID of the company
            raised_by_user_id: UUID of the user creating the ticket
            category: Optional category
            summary: Optional summary
            level: Optional severity level
            assigned_engineer_id: Optional engineer to assign
            
        Returns:
            Dict with ticket creation result and dedup info
        """
        logger.info(f"Creating ticket with deduplication: '{subject}'")
        
        # Check for duplicates using the detailed description
        dedup_result = DuplicateService.check_for_duplicates(
            query_text=detailed_description or subject,
            company_id=company_id,
            category=category,
            user_id=raised_by_user_id
        )
        
        # If duplicate found, return existing ticket instead
        if not dedup_result["should_create_ticket"]:
            logger.info(f"Returning existing ticket instead of creating new one")
            return {
                "success": False,
                "created_new": False,
                "reason": "duplicate_found",
                "dedup_result": dedup_result,
                "existing_ticket": dedup_result.get("existing_ticket"),
                "message": f"Similar solution already exists: {dedup_result.get('existing_ticket', {}).get('ticket_no')}"
            }
        
        # No duplicate found, create the ticket
        db = SessionLocal()
        
        try:
            # Generate ticket number
            ticket_no = DuplicateService._generate_ticket_no(company_id, db)
            
            # Create ticket
            ticket = Ticket(
                ticket_no=ticket_no,
                subject=subject,
                detailed_description=detailed_description,
                summary=summary,
                category=category,
                level=level,
                status="open",
                company_id=company_id,
                raised_by_user_id=raised_by_user_id,
                assigned_engineer_id=assigned_engineer_id
            )
            db.add(ticket)
            db.flush()
            
            # Create TicketEvent for creation
            creation_event = TicketEvent(
                ticket_id=ticket.id,
                event_type="created",
                actor_user_id=raised_by_user_id,
                payload={
                    "subject": subject,
                    "category": category,
                    "level": level,
                    "summary": summary
                }
            )
            db.add(creation_event)
            db.commit()
            
            logger.info(f"✓ Created ticket {ticket_no}")
            
            # Trigger embedding creation asynchronously (in real system)
            # For now, do it synchronously
            try:
                embedding_count = EmbeddingService.embed_ticket_created(
                    str(ticket.id),
                    company_id
                )
                logger.info(f"✓ Created {embedding_count} embeddings for {ticket_no}")
            except Exception as e:
                logger.error(f"Failed to create embeddings: {e}")
                # Don't fail ticket creation if embeddings fail
            
            return {
                "success": True,
                "created_new": True,
                "ticket": {
                    "id": str(ticket.id),
                    "ticket_no": ticket.ticket_no,
                    "subject": ticket.subject,
                    "status": ticket.status,
                    "created_at": ticket.created_at.isoformat()
                },
                "dedup_result": dedup_result,
                "message": f"New ticket created: {ticket_no}"
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create ticket: {e}")
            return {
                "success": False,
                "created_new": False,
                "reason": "creation_error",
                "error": str(e),
                "message": f"Failed to create ticket: {str(e)}"
            }
        finally:
            db.close()
    
    @staticmethod
    def _generate_ticket_no(company_id: str, db) -> str:
        """
        Generate next ticket number for a company.
        Format: TKT-XXXXX (5 digits)
        
        Args:
            company_id: UUID of the company
            db: SQLAlchemy session
            
        Returns:
            Next ticket number
        """
        # Get highest ticket number for this company
        last_ticket = db.query(Ticket).filter(
            Ticket.company_id == company_id,
            Ticket.ticket_no.like('TKT-%')
        ).order_by(Ticket.ticket_no.desc()).first()
        
        if last_ticket:
            # Extract number and increment
            number = int(last_ticket.ticket_no.split('-')[1])
            next_number = number + 1
        else:
            next_number = 1
        
        return f"TKT-{next_number:05d}"
    
    @staticmethod
    def link_similar_tickets(
        primary_ticket_id: str,
        related_ticket_ids: list,
        actor_user_id: str
    ) -> bool:
        """
        Link multiple tickets that represent the same issue.
        Useful when duplicates aren't caught initially.
        
        Creates a relationship between tickets for tracking.
        
        Args:
            primary_ticket_id: The canonical ticket ID
            related_ticket_ids: List of duplicate ticket IDs
            actor_user_id: User creating the link
            
        Returns:
            True if successful
        """
        logger.info(f"Linking {len(related_ticket_ids)} tickets to {primary_ticket_id}")
        
        db = SessionLocal()
        try:
            for ticket_id in related_ticket_ids:
                # Create event on each related ticket
                event = TicketEvent(
                    ticket_id=ticket_id,
                    event_type="linked_to_ticket",
                    actor_user_id=actor_user_id,
                    payload={
                        "primary_ticket_id": primary_ticket_id,
                        "note": f"Linked to {primary_ticket_id} as duplicate"
                    }
                )
                db.add(event)
            
            # Create event on primary ticket
            event = TicketEvent(
                ticket_id=primary_ticket_id,
                event_type="has_duplicates",
                actor_user_id=actor_user_id,
                payload={
                    "related_tickets": related_ticket_ids,
                    "count": len(related_ticket_ids)
                }
            )
            db.add(event)
            
            db.commit()
            logger.info(f"✓ Linked {len(related_ticket_ids)} tickets")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to link tickets: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_dedup_stats(company_id: str) -> Dict[str, Any]:
        """
        Get deduplication statistics for a company.
        
        Returns:
            Statistics about duplicate handling
        """
        db = SessionLocal()
        try:
            # Count tickets created (proxy for duplicates prevented)
            total_tickets = db.query(Ticket).filter(
                Ticket.company_id == company_id
            ).count()
            
            # Count linked/duplicate events
            duplicate_events = db.query(TicketEvent).filter(
                TicketEvent.event_type.in_(['linked_to_ticket', 'has_duplicates'])
            ).all()
            
            linked_count = sum(1 for e in duplicate_events if e.event_type == 'has_duplicates')
            
            return {
                "company_id": company_id,
                "total_tickets": total_tickets,
                "linked_as_duplicates": linked_count,
                "dedup_events": len(duplicate_events)
            }
            
        finally:
            db.close()