# server/services/ticket_service.py
"""Ticket service - handles ticket retrieval, updates, and analytics"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from core.database import SessionLocal, Ticket, TicketEvent, AdminAuditLog, Company, User
from utils.exceptions import ValidationError, NotFoundError
from core.logger import get_logger

logger = get_logger(__name__)


class TicketService:
    """Service for ticket management and analytics"""
    
    @staticmethod
    def get_tickets(
        company_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get paginated list of tickets with optional filters.
        
        Args:
            company_id: Filter by company
            status: Filter by status (open, in_progress, resolved, closed)
            limit: Number of tickets per page
            offset: Pagination offset
            search: Search in subject/summary
            
        Returns:
            Dict with tickets list and total count
        """
        db = SessionLocal()
        try:
            query = db.query(Ticket)
            
            # Apply filters
            if company_id:
                query = query.filter(Ticket.company_id == UUID(company_id))
            if status:
                query = query.filter(Ticket.status == status)
            if search:
                search_pattern = f"%{search}%"
                query = query.filter(
                    or_(
                        Ticket.subject.ilike(search_pattern),
                        Ticket.summary.ilike(search_pattern),
                        Ticket.ticket_no.ilike(search_pattern)
                    )
                )
            
            # Get total count
            total = query.count()
            
            # Get paginated results
            tickets = query.order_by(Ticket.created_at.desc()).limit(limit).offset(offset).all()
            
            # Convert to dicts
            tickets_data = []
            for ticket in tickets:
                tickets_data.append({
                    "id": str(ticket.id),
                    "ticket_no": ticket.ticket_no,
                    "subject": ticket.subject,
                    "status": ticket.status,
                    "category": ticket.category,
                    "level": ticket.level,
                    "company_id": str(ticket.company_id),
                    "company_name": ticket.company.name if ticket.company else None,
                    "created_by": ticket.raised_by_user.name if ticket.raised_by_user else None,
                    "assigned_to": ticket.assigned_engineer.name if ticket.assigned_engineer else None,
                    "created_at": ticket.created_at.isoformat(),
                    "updated_at": ticket.updated_at.isoformat(),
                    "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
                })
            
            return {
                "tickets": tickets_data,
                "total": total,
                "limit": limit,
                "offset": offset
            }
            
        except Exception as e:
            logger.error(f"Failed to get tickets: {e}")
            raise ValidationError("Failed to retrieve tickets")
        finally:
            db.close()
    
    @staticmethod
    def get_ticket_by_id(ticket_id: str) -> Dict[str, Any]:
        """Get ticket details by ID"""
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            # Get events
            events = db.query(TicketEvent).filter(
                TicketEvent.ticket_id == ticket.id
            ).order_by(TicketEvent.created_at).all()
            
            events_data = [
                {
                    "id": str(e.id),
                    "type": e.event_type,
                    "actor": e.actor_user.name if e.actor_user else None,
                    "payload": e.payload,
                    "created_at": e.created_at.isoformat()
                }
                for e in events
            ]
            
            return {
                "id": str(ticket.id),
                "ticket_no": ticket.ticket_no,
                "subject": ticket.subject,
                "summary": ticket.summary,
                "detailed_description": ticket.detailed_description,
                "status": ticket.status,
                "category": ticket.category,
                "level": ticket.level,
                "company_id": str(ticket.company_id),
                "company_name": ticket.company.name if ticket.company else None,
                "created_by": ticket.raised_by_user.name if ticket.raised_by_user else None,
                "created_by_id": str(ticket.raised_by_user_id) if ticket.raised_by_user_id else None,
                "assigned_to": ticket.assigned_engineer.name if ticket.assigned_engineer else None,
                "assigned_to_id": str(ticket.assigned_engineer_id) if ticket.assigned_engineer_id else None,
                "created_at": ticket.created_at.isoformat(),
                "updated_at": ticket.updated_at.isoformat(),
                "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
                "reopened_at": ticket.reopened_at.isoformat() if ticket.reopened_at else None,
                "attachment_ids": ticket.attachment_ids or [],
                "events": events_data
            }
            
        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to get ticket: {e}")
            raise ValidationError("Failed to retrieve ticket")
        finally:
            db.close()
    
    @staticmethod
    def update_ticket_status(ticket_id: str, new_status: str, admin_id: str) -> Dict[str, Any]:
        """Update ticket status"""
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            valid_statuses = ["open", "in_progress", "resolved", "closed", "reopened"]
            if new_status not in valid_statuses:
                raise ValidationError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
            
            old_status = ticket.status
            ticket.status = new_status
            ticket.updated_at = datetime.utcnow()
            
            # Set closed_at if closing
            if new_status == "closed" and not ticket.closed_at:
                ticket.closed_at = datetime.utcnow()
            
            # Set reopened_at if reopening
            if new_status == "reopened":
                ticket.reopened_at = datetime.utcnow()
            
            db.commit()
            
            # Log audit event
            AdminAuditLog.create(
                admin_user_id=UUID(admin_id),
                action="ticket_status_updated",
                resource="ticket",
                resource_id=ticket_id,
                changes={"from": old_status, "to": new_status}
            )
            
            logger.info(f"✓ Ticket {ticket.ticket_no} status updated: {old_status} → {new_status}")
            
            return {
                "id": str(ticket.id),
                "ticket_no": ticket.ticket_no,
                "status": ticket.status,
                "updated_at": ticket.updated_at.isoformat()
            }
            
        except (NotFoundError, ValidationError):
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update ticket status: {e}")
            raise ValidationError("Failed to update ticket")
        finally:
            db.close()
    
    @staticmethod
    def assign_ticket(ticket_id: str, engineer_id: str, admin_id: str) -> Dict[str, Any]:
        """Assign ticket to an engineer"""
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            engineer = db.query(User).filter(User.id == UUID(engineer_id)).first()
            if not engineer:
                raise NotFoundError("Engineer not found")
            
            ticket.assigned_engineer_id = UUID(engineer_id)
            ticket.updated_at = datetime.utcnow()
            db.commit()
            
            # Log audit event
            AdminAuditLog.create(
                admin_user_id=UUID(admin_id),
                action="ticket_assigned",
                resource="ticket",
                resource_id=ticket_id,
                changes={"assigned_to": engineer.name}
            )
            
            logger.info(f"✓ Ticket {ticket.ticket_no} assigned to {engineer.name}")
            
            return {
                "id": str(ticket.id),
                "ticket_no": ticket.ticket_no,
                "assigned_to": engineer.name,
                "assigned_to_id": str(engineer.id)
            }
            
        except (NotFoundError, ValidationError):
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to assign ticket: {e}")
            raise ValidationError("Failed to assign ticket")
        finally:
            db.close()
    
    @staticmethod
    def get_analytics(company_id: Optional[str] = None, days: int = 30) -> Dict[str, Any]:
        """Get ticket analytics"""
        db = SessionLocal()
        try:
            query = db.query(Ticket)
            if company_id:
                query = query.filter(Ticket.company_id == UUID(company_id))
            
            # Calculate metrics
            total_tickets = query.count()
            
            open_tickets = query.filter(Ticket.status == "open").count()
            in_progress = query.filter(Ticket.status == "in_progress").count()
            resolved = query.filter(Ticket.status == "resolved").count()
            closed = query.filter(Ticket.status == "closed").count()
            
            # Recent tickets (last N days)
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            recent_tickets = query.filter(Ticket.created_at >= cutoff_date).count()
            
            # Tickets by category
            categories = {}
            for ticket in query.all():
                cat = ticket.category or "Uncategorized"
                categories[cat] = categories.get(cat, 0) + 1
            
            # Tickets by level
            levels = {}
            for ticket in query.all():
                lvl = ticket.level or "Normal"
                levels[lvl] = levels.get(lvl, 0) + 1
            
            # Average resolution time (closed tickets only)
            closed_tickets = query.filter(Ticket.status == "closed").all()
            avg_resolution_time = 0
            if closed_tickets:
                total_time = 0
                for ticket in closed_tickets:
                    if ticket.created_at and ticket.closed_at:
                        delta = (ticket.closed_at - ticket.created_at).total_seconds()
                        total_time += delta
                avg_resolution_time = int(total_time / len(closed_tickets) / 3600)  # in hours
            
            return {
                "total_tickets": total_tickets,
                "open_tickets": open_tickets,
                "in_progress": in_progress,
                "resolved": resolved,
                "closed": closed,
                "recent_tickets": recent_tickets,
                "categories": categories,
                "levels": levels,
                "avg_resolution_time_hours": avg_resolution_time
            }
            
        except Exception as e:
            logger.error(f"Failed to get analytics: {e}")
            raise ValidationError("Failed to retrieve analytics")
        finally:
            db.close()