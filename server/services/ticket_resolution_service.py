"""
Ticket Resolution Service - Fetch and format similar tickets for Telegram display
"""
import logging
import json
from typing import Optional, List, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session as DBSession

from core.database import (
    SessionLocal, Ticket, SimilarIssues, ResolutionNote, 
    RootCauseAnalysis, Attachment, RCAAttachment, User
)
from utils.datetime_utils import to_iso_date

logger = logging.getLogger(__name__)

# Simple in-memory cache for similar tickets (session-scoped)
# In production, use Redis, but this works for MVP
_ticket_cache: Dict[str, List[Dict[str, Any]]] = {}


class TicketResolutionService:
    """Service to fetch and format similar tickets for user resolution"""
        
    @staticmethod
    def get_similar_tickets_with_metadata(
        ticket_id: Optional[str] = None,
        company_id: str = None,
        limit: int = 3,
        min_score: int = 70,
        db: Optional[DBSession] = None,
        category_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch similar tickets with full metadata.
        
        Can search by:
        1. ticket_id (if ticket already created)
        2. category_filter (during chat, before ticket exists)
        """
        should_close = db is None
        db = db or SessionLocal()
        
        try:
            try:
                company_uuid = UUID(company_id)
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid company_id: {company_id}")
                return []
            
            # CASE 1: Search by similar_issues table
            if ticket_id:
                try:
                    ticket_uuid = UUID(ticket_id)
                    
                    similar_records = db.query(SimilarIssues, Ticket).join(
                        Ticket, Ticket.id == SimilarIssues.older_ticket_id
                    ).filter(
                        SimilarIssues.newer_ticket_id == ticket_uuid,
                        SimilarIssues.similarity_score >= min_score,
                        Ticket.company_id == company_uuid
                    ).order_by(
                        SimilarIssues.similarity_score.desc()
                    ).limit(limit).all()
                    
                    logger.info(f"Found {len(similar_records)} similar tickets by ticket_id")
                    results = []
                    for similarity, ticket in similar_records:
                        results.append(_build_ticket_dict(ticket, similarity.similarity_score, db))
                    
                    return results
                
                except ValueError:
                    logger.warning(f"Invalid ticket_id: {ticket_id}")
            
            # CASE 2: Search by category (during chat)
            if category_filter:
                logger.info(f"Searching tickets by category: {category_filter}")
                
                # Eagerly load the raised_by_user relationship
                from sqlalchemy.orm import joinedload
                resolved_tickets = db.query(Ticket).options(
                    joinedload(Ticket.raised_by_user)
                ).filter(
                    Ticket.company_id == company_uuid,
                    Ticket.category == category_filter,
                    Ticket.status.in_(["closed", "resolved"])
                ).order_by(
                    Ticket.created_at.desc()
                ).limit(limit).all()
                
                logger.info(f"Found {len(resolved_tickets)} resolved tickets in category '{category_filter}'")
                
                results = []
                for ticket in resolved_tickets:
                    ticket_dict = _build_ticket_dict(ticket, similarity_score=80, db=db)
                    # Only add non-empty dicts
                    if ticket_dict.get("ticket_no") and ticket_dict["ticket_no"] != "N/A":
                        results.append(ticket_dict)
                
                logger.info(f"Successfully built {len(results)} ticket dicts")
                return results
            
            logger.warning("No search criteria provided")
            return []
        
        except Exception as e:
            logger.error(f"Error fetching similar tickets: {e}", exc_info=True)
            return []
        
        finally:
            if should_close and db:
                db.close()
    
    @staticmethod
    def cache_similar_tickets_for_session(
        session_id: str,
        similar_tickets: List[Dict[str, Any]]
    ) -> bool:
        """
        Cache similar tickets in memory (simple approach).
        For production, use Redis.
        """
        try:
            _ticket_cache[session_id] = similar_tickets
            logger.info(f"Cached {len(similar_tickets)} similar tickets for session {session_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error caching similar tickets: {e}")
            return False
    
    @staticmethod
    def get_cached_similar_tickets(session_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve cached similar tickets from memory.
        Returns empty list if not found.
        """
        try:
            tickets = _ticket_cache.get(session_id, [])
            
            if tickets:
                logger.info(f"Retrieved {len(tickets)} similar tickets from cache")
                return tickets
            
            logger.warning(f"No cached tickets for session {session_id}")
            return []
        
        except Exception as e:
            logger.error(f"Error retrieving cached tickets: {e}")
            return []
    
    @staticmethod
    def clear_cached_similar_tickets(session_id: str) -> bool:
        """Clear cached similar tickets for a session"""
        try:
            if session_id in _ticket_cache:
                del _ticket_cache[session_id]
            logger.info(f"Cleared cache for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False
    
    @staticmethod
    def format_similar_tickets_for_telegram(
        similar_tickets: List[Dict[str, Any]]
    ) -> str:
        """
        Format similar tickets list for Telegram display.
        Shows ticket list with match percentage and quick preview.
        """
        if not similar_tickets:
            return "🔍 No similar tickets found.\n\nLet's create a new ticket for your issue."
        
        message = f"🔍 Found {len(similar_tickets)} similar issue(s):\n\n"
        
        for idx, ticket in enumerate(similar_tickets, 1):
            match_pct = ticket.get('similarity_score', 0)
            
            # Match quality indicator
            if match_pct >= 85:
                emoji = "🟢"
                quality = "Excellent Match"
            elif match_pct >= 75:
                emoji = "🟡"
                quality = "Good Match"
            else:
                emoji = "🔴"
                quality = "Fair Match"
            
            message += (
                f"{emoji} **{idx}. {ticket.get('ticket_no', 'N/A')}** - {match_pct}% ({quality})\n"
                f"   📌 {ticket.get('subject', 'No subject')}\n"
                f"   👤 {ticket.get('created_by', 'Unknown')} • {ticket.get('created_date', 'Unknown')}\n"
                f"   ✅ Status: {ticket.get('status', 'unknown').upper()}\n"
            )
            
            # Show resolution preview if available
            if ticket.get('resolution'):
                preview = ticket['resolution'][:60].rstrip() + ("..." if len(ticket['resolution']) > 60 else "")
                message += f"   💡 {preview}\n"
            
            message += "\n"
        
        message += (
            "📋 **Options:**\n"
            "• Reply with **number** (1-3) to see full details\n"
            "• Reply **'yes'** if one of these solves your issue\n"
            "• Reply **'no'** to create a new ticket\n"
            "• Reply **'create new'** to skip and create anyway"
        )
        
        return message
            
    @staticmethod
    def format_ticket_details_for_telegram(ticket: Dict[str, Any]) -> str:
        """
        Format ticket details for Telegram display with attachments
        """
        try:
            ticket_no = ticket.get("ticket_no", "N/A")
            subject = ticket.get("subject", "No subject")
            created_by = ticket.get("created_by", "Unknown")
            created_date = ticket.get("created_date", "Unknown")
            updated_date = ticket.get("updated_date", "Unknown")
            status = ticket.get("status", "unknown").upper()
            category = ticket.get("category", "unknown")
            priority = ticket.get("priority", "normal").upper()
            similarity_score = ticket.get("similarity_score", 0)
            
            # Resolution info
            resolution = ticket.get("resolution")
            resolution_steps = ticket.get("resolution_steps")
            
            # RCA info
            root_cause = ticket.get("root_cause")
            prevention = ticket.get("prevention")
            
            # Attachments
            attachments = ticket.get("attachments", [])
            rca_attachments = ticket.get("rca_attachments", [])
            
            # Build message
            message = f"""{ticket_no} - {subject}
    
    Created by: {created_by}
    Created: {created_date}
    Updated: {updated_date}
    Status: {status}
    Category: {category}
    Priority: {priority}
    Match: {similarity_score}%
    """
            
            # Add main attachments if available
            if attachments:
                message += f"\nATTACHMENTS: {len(attachments)} file(s)\n"
                for att in attachments[:5]:  # Show first 5
                    message += f"  {att.get('name', 'file')}\n"
            
            # Add resolution if available
            if resolution:
                message += f"\nSOLUTION:\n{resolution}\n"
            
            # Add resolution steps if available
            if resolution_steps:
                message += f"\nSTEPS:\n{resolution_steps}\n"
            
            # Add root cause if available
            if root_cause:
                message += f"\nROOT CAUSE:\n{root_cause}\n"
            
            # Add RCA attachments if available
            if rca_attachments:
                message += f"\nREFERENCES: {len(rca_attachments)} file(s)\n"
                for att in rca_attachments[:5]:  # Show first 5
                    message += f"  {att.get('name', 'file')}\n"
            
            # Add prevention measures if available
            if prevention and prevention != "Not Applicable":
                message += f"\nPREVENTION:\n{prevention}\n"
            
            # Add feedback prompt
            message += "\nDid this help? Reply: yes / no / need more help"
            
            logger.info(f"Formatted ticket details: {ticket_no}, attachments={len(attachments)}, rca_attachments={len(rca_attachments)}")
            
            return message.strip()
        
        except Exception as e:
            logger.error(f"Error formatting ticket details: {e}", exc_info=True)
            return f"Error loading ticket details: {str(e)}"



def _build_ticket_dict(ticket: Ticket, similarity_score: int, db: DBSession) -> Dict[str, Any]:
    """Helper to build ticket dictionary from Ticket model"""
    try:
        logger.info(f"\n{'='*60}")
        logger.info(f"Building ticket dict for: {ticket.ticket_no}")
        logger.info(f"== Ticket Object Debug Info ==")
        logger.info(f"ticket.id: {ticket.id}")
        logger.info(f"ticket.ticket_no: {ticket.ticket_no}")
        logger.info(f"ticket.subject: {ticket.subject}")
        logger.info(f"ticket.category: {ticket.category}")
        logger.info(f"ticket.status: {ticket.status}")
        logger.info(f"ticket.level: {ticket.level}")
        logger.info(f"ticket.created_at: {ticket.created_at} (type: {type(ticket.created_at).__name__})")
        logger.info(f"ticket.updated_at: {ticket.updated_at} (type: {type(ticket.updated_at).__name__})")
        logger.info(f"ticket.raised_by_user_id: {ticket.raised_by_user_id}")
        logger.info(f"ticket.raised_by_user: {ticket.raised_by_user}")
        if ticket.raised_by_user:
            logger.info(f"  - user.email: {ticket.raised_by_user.email}")
            logger.info(f"  - user.name: {ticket.raised_by_user.name}")
        logger.info(f"{'='*60}")
        
        # Get related records
        resolution = db.query(ResolutionNote).filter(
            ResolutionNote.ticket_id == ticket.id
        ).first()
        
        rca = db.query(RootCauseAnalysis).filter(
            RootCauseAnalysis.ticket_id == ticket.id
        ).first()
        
        # Get main attachments (images, documents)
        attachments = db.query(Attachment).filter(
            Attachment.ticket_id == ticket.id
        ).all()
        
        # Get RCA attachments if RCA exists
        rca_attachments = []
        if rca:
            rca_attachments = db.query(RCAAttachment).filter(
                RCAAttachment.rca_id == rca.id
            ).all()
        
        logger.info(f"Main attachments found: {len(attachments)}")
        logger.info(f"RCA attachments found: {len(rca_attachments)}")
        
        logger.info(f"ResolutionNote found: {bool(resolution)}")
        if resolution:
            logger.info(f"  - solution_description: {bool(resolution.solution_description)}")
            logger.info(f"  - steps_taken: {bool(resolution.steps_taken)}")
        
        logger.info(f"RootCauseAnalysis found: {bool(rca)}")
        if rca:
            logger.info(f"  - root_cause_description: {bool(rca.root_cause_description)}")
            logger.info(f"  - resolution_steps: {bool(rca.resolution_steps)}")
            logger.info(f"  - prevention_measures: {bool(rca.prevention_measures)}")
        
        # Get creator name from the eager-loaded relationship
        created_by = "Unknown"
        
        logger.info(f"\n--- Creator Resolution for {ticket.ticket_no} ---")
        
        # Use the relationship if it's loaded
        if ticket.raised_by_user:
            created_by = ticket.raised_by_user.email or ticket.raised_by_user.name or "Unknown"
            logger.info(f"✓ Creator from raised_by_user relationship: {created_by}")
        else:
            logger.warning(f"⚠ raised_by_user relationship not loaded")
            logger.info(f"  raised_by_user_id: {ticket.raised_by_user_id}")
            
            # Fallback: query the user
            if ticket.raised_by_user_id:
                try:
                    from core.database import User
                    user = db.query(User).filter(User.id == ticket.raised_by_user_id).first()
                    if user:
                        created_by = user.email or user.name or "Unknown"
                        logger.info(f"✓ Creator from fallback User query: {created_by}")
                    else:
                        logger.info(f"✗ User not found for ID: {ticket.raised_by_user_id}")
                except Exception as e:
                    logger.warning(f"✗ Could not resolve user: {e}")
        
        logger.info(f"--- Final creator: {created_by} ---\n")
        
        # Extract resolution fields from ResolutionNote
        resolution_text = None
        resolution_steps_text = None
        if resolution:
            resolution_text = resolution.solution_description
            
            # steps_taken is JSONB array from ResolutionNote, convert to readable text
            if resolution.steps_taken:
                if isinstance(resolution.steps_taken, list):
                    resolution_steps_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(resolution.steps_taken) if step])
                else:
                    resolution_steps_text = str(resolution.steps_taken)
        
        # Extract RCA fields from RootCauseAnalysis
        root_cause_text = None
        rca_resolution_steps_text = None
        prevention_text = None
        if rca:
            root_cause_text = rca.root_cause_description
            prevention_text = rca.prevention_measures
            
            # resolution_steps is JSONB array from RootCauseAnalysis
            if rca.resolution_steps:
                if isinstance(rca.resolution_steps, list):
                    rca_resolution_steps_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(rca.resolution_steps) if step])
                else:
                    rca_resolution_steps_text = str(rca.resolution_steps)
        
        # Use resolution steps from RCA if ResolutionNote doesn't have them
        final_resolution_steps = resolution_steps_text or rca_resolution_steps_text
        
        # Format main attachments - Attachment model has: type, file_path, mime_type
        formatted_attachments = [
            {
                "url": att.file_path,
                "name": att.file_path.split('/')[-1] if att.file_path else att.type,  # Extract filename from path
                "type": att.type,
                "mime_type": att.mime_type,
                "source": "main"
            }
            for att in attachments if att.file_path
        ]
        
        # Format RCA attachments - RCAAttachment model has: type, file_path, mime_type
        formatted_rca_attachments = [
            {
                "url": att.file_path,
                "name": att.file_path.split('/')[-1] if att.file_path else att.type,  # Extract filename from path
                "type": att.type,
                "mime_type": att.mime_type,
                "source": "rca"
            }
            for att in rca_attachments if att.file_path
        ]
        
        # Format dates - Ticket.created_at and updated_at are Date objects, not DateTime
        created_date = "Unknown"
        updated_date = None
        
        if ticket.created_at:
            try:
                # Handle both datetime and date objects
                if hasattr(ticket.created_at, 'strftime'):
                    created_date = ticket.created_at.strftime("%Y-%m-%d")
                else:
                    created_date = str(ticket.created_at)
                logger.info(f"✓ Formatted created_date: {created_date}")
            except Exception as e:
                logger.error(f"Error formatting created_at: {e}")
                created_date = str(ticket.created_at) if ticket.created_at else "Unknown"
        
        if ticket.updated_at:
            try:
                # Handle both datetime and date objects
                if hasattr(ticket.updated_at, 'strftime'):
                    updated_date = ticket.updated_at.strftime("%Y-%m-%d")
                else:
                    updated_date = str(ticket.updated_at)
                logger.info(f"✓ Formatted updated_date: {updated_date}")
            except Exception as e:
                logger.error(f"Error formatting updated_at: {e}")
                updated_date = str(ticket.updated_at) if ticket.updated_at else None
        
        logger.info(f"\nFinal data for {ticket.ticket_no}:")
        logger.info(f"  ticket_id: {ticket.id}")
        logger.info(f"  ticket_no: {ticket.ticket_no}")
        logger.info(f"  subject: {ticket.subject}")
        logger.info(f"  category: {ticket.category}")
        logger.info(f"  status: {ticket.status}")
        logger.info(f"  priority (level): {ticket.level}")
        logger.info(f"  created_by: {created_by}")
        logger.info(f"  created_date: {created_date}")
        logger.info(f"  updated_date: {updated_date}")
        logger.info(f"  resolution: {bool(resolution_text)}")
        logger.info(f"  steps: {bool(final_resolution_steps)}")
        logger.info(f"  root_cause: {bool(root_cause_text)}")
        logger.info(f"  prevention: {bool(prevention_text)}")
        logger.info(f"  main_attachments: {len(formatted_attachments)}")
        logger.info(f"  rca_attachments: {len(formatted_rca_attachments)}")
        logger.info(f"{'='*60}\n")
        
        return {
            "ticket_id": str(ticket.id),
            "ticket_no": ticket.ticket_no or "N/A",
            "subject": ticket.subject or "No subject",
            "category": ticket.category or "unknown",
            "similarity_score": similarity_score,
            "status": ticket.status or "open",
            "created_by": created_by,
            "created_date": created_date,
            "updated_date": updated_date,
            "priority": ticket.level or "normal",
            "resolution": resolution_text,
            "resolution_steps": final_resolution_steps,
            "root_cause": root_cause_text,
            "prevention": prevention_text,
            "attachments": formatted_attachments,
            "rca_attachments": formatted_rca_attachments
        }
    except Exception as e:
        logger.error(f"Error building ticket dict: {e}", exc_info=True)
        return {
            "ticket_id": str(ticket.id) if ticket else "unknown",
            "ticket_no": getattr(ticket, 'ticket_no', 'N/A'),
            "subject": getattr(ticket, 'subject', 'Error loading ticket'),
            "category": getattr(ticket, 'category', 'unknown'),
            "similarity_score": similarity_score,
            "status": getattr(ticket, 'status', 'unknown'),
            "created_by": "Unknown",
            "created_date": "Unknown",
            "updated_date": None,
            "priority": getattr(ticket, 'level', 'normal'),
            "resolution": None,
            "resolution_steps": None,
            "root_cause": None,
            "prevention": None,
            "attachments": [],
            "rca_attachments": []
        }