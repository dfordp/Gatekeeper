# server/services/ticket_service.py
"""Ticket retrieval and update service with embedding management"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

from core.database import SessionLocal, Ticket, TicketEvent, AdminAuditLog, User
from utils.exceptions import ValidationError, NotFoundError, ConflictError
from core.logger import get_logger

logger = get_logger(__name__)


class TicketService:
    """Service for ticket retrieval and updates"""
    @staticmethod
    def get_tickets(
        company_id: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get paginated list of tickets with optional filtering and search.
        
        Args:
            company_id: Filter by company ID (optional)
            status: Filter by ticket status (optional)
            search: Search in ticket number, subject, and description (optional)
            limit: Number of tickets per page (default 50)
            offset: Pagination offset (default 0)
            
        Returns:
            Dict containing:
            - tickets: List of formatted ticket objects
            - total: Total count of matching tickets
            - limit: Limit parameter used
            - offset: Offset parameter used
        """
        db = SessionLocal()
        try:
            # Start with base query
            query = db.query(Ticket)
            
            # Apply filters if provided
            if company_id:
                try:
                    company_uuid = UUID(company_id)
                    query = query.filter(Ticket.company_id == company_uuid)
                except ValueError:
                    logger.warning(f"Invalid company_id format: {company_id}")
            
            if status:
                valid_statuses = ["open", "in_progress", "resolved", "closed", "reopened"]
                if status in valid_statuses:
                    query = query.filter(Ticket.status == status)
                else:
                    logger.warning(f"Invalid status filter: {status}")
            
            # Apply search filter if provided
            if search and search.strip():
                search_term = f"%{search.strip()}%"
                # Search in ticket number, subject, and description
                from sqlalchemy import or_
                query = query.filter(
                    or_(
                        Ticket.ticket_no.ilike(search_term),
                        Ticket.subject.ilike(search_term),
                        Ticket.detailed_description.ilike(search_term)
                    )
                )
                logger.debug(f"Applied search filter: {search}")
            
            # Get total count before pagination
            total = query.count()
            
            # Apply pagination and ordering (latest first)
            tickets = query.order_by(Ticket.created_at.desc()).limit(limit).offset(offset).all()
            
            logger.info(f"Retrieved {len(tickets)} tickets (total: {total}, limit: {limit}, offset: {offset}, search: {search})")
            
            return {
                "tickets": [TicketService._format_ticket(t) for t in tickets],
                "total": total,
                "limit": limit,
                "offset": offset
            }
            
        except Exception as e:
            logger.error(f"Failed to retrieve tickets: {e}")
            raise ValidationError(f"Failed to retrieve tickets: {str(e)}")
        finally:
            db.close()
    
    @staticmethod
    def get_ticket_by_id(ticket_id: str) -> Dict[str, Any]:
        """Get ticket by ID with all related data"""
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            return TicketService._format_ticket(ticket)
        finally:
            db.close()
    
    
    @staticmethod
    def get_ticket_by_number(ticket_no: str) -> Dict[str, Any]:
        """Get ticket by ticket number"""
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
            if not ticket:
                raise NotFoundError(f"Ticket {ticket_no} not found")
            
            return TicketService._format_ticket(ticket)
        finally:
            db.close()
    
    
    @staticmethod
    def _format_ticket(ticket) -> Dict[str, Any]:
        """Format ticket object as dictionary"""
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
            "raised_by_user_id": str(ticket.raised_by_user_id),
            "raised_by_user": {
                "id": str(ticket.raised_by_user.id),
                "name": ticket.raised_by_user.name,
                "email": ticket.raised_by_user.email
            } if ticket.raised_by_user else None,
            "created_by": ticket.raised_by_user.name if ticket.raised_by_user else None,
            "assigned_engineer_id": str(ticket.assigned_engineer_id) if ticket.assigned_engineer_id else None,
            "assigned_engineer": {
                "id": str(ticket.assigned_engineer.id),
                "name": ticket.assigned_engineer.name,
                "email": ticket.assigned_engineer.email
            } if ticket.assigned_engineer else None,
            "assigned_to": ticket.assigned_engineer.name if ticket.assigned_engineer else None,
            "assigned_to_id": str(ticket.assigned_engineer_id) if ticket.assigned_engineer_id else None,
            "created_at": ticket.created_at.isoformat(),
            "updated_at": ticket.updated_at.isoformat(),
            "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
            "reopened_at": ticket.reopened_at.isoformat() if ticket.reopened_at else None,
            "attachments": [
                {
                    "id": str(att.id),
                    "type": att.type,
                    "file_path": att.file_path,
                    "mime_type": att.mime_type,
                    "created_at": att.created_at.isoformat()
                }
                for att in ticket.attachments
            ] if ticket.attachments else [],
            "rca": {
                "id": str(ticket.root_cause_analysis.id),
                "root_cause_description": ticket.root_cause_analysis.root_cause_description,
                "contributing_factors": ticket.root_cause_analysis.contributing_factors or [],
                "prevention_measures": ticket.root_cause_analysis.prevention_measures,
                "resolution_steps": ticket.root_cause_analysis.resolution_steps or [],
                "related_ticket_ids": ticket.root_cause_analysis.related_ticket_ids or [],
                "attachments": [
                    {
                        "id": str(att.id),
                        "type": att.type,
                        "file_path": att.file_path,
                        "mime_type": att.mime_type,
                        "created_at": att.created_at.isoformat()
                    }
                    for att in ticket.root_cause_analysis.attachments
                ] if ticket.root_cause_analysis.attachments else [],
                "created_at": ticket.root_cause_analysis.created_at.isoformat(),
                "updated_at": ticket.root_cause_analysis.updated_at.isoformat()
            } if ticket.root_cause_analysis else None,
            "resolution_note": {
                "id": str(ticket.resolution_note.id),
                "solution_description": ticket.resolution_note.solution_description,
                "steps_taken": ticket.resolution_note.steps_taken or [],
                "resources_used": ticket.resolution_note.resources_used or [],
                "follow_up_notes": ticket.resolution_note.follow_up_notes,
                "created_at": ticket.resolution_note.created_at.isoformat(),
                "updated_at": ticket.resolution_note.updated_at.isoformat()
            } if ticket.resolution_note else None,
            "events": [
                {
                    "id": str(event.id),
                    "event_type": event.event_type,
                    "actor_user_id": str(event.actor_user_id),
                    "actor": event.actor_user.name if event.actor_user else None,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat()
                }
                for event in ticket.events
            ] if ticket.events else []
        }
    
    @staticmethod
    def update_ticket_status(
        ticket_id: str,
        new_status: str,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update ticket status"""
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            
            # Verify ticket exists
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            valid_statuses = ["open", "in_progress", "resolved", "closed", "reopened"]
            if new_status not in valid_statuses:
                raise ValidationError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
            
            old_status = ticket.status
            logger.info(f"Updating ticket {ticket.ticket_no} status: {old_status} → {new_status}")
            
            # Update status
            ticket.status = new_status
            ticket.updated_at = datetime.utcnow()
            
            if new_status == "closed":
                ticket.closed_at = datetime.utcnow()
            elif new_status == "reopened":
                ticket.reopened_at = datetime.utcnow()
            
            db.flush()
            
            # Verify user for event logging
            actual_user_id = ticket.raised_by_user_id
            if admin_id:
                try:
                    user = db.query(User).filter(User.id == UUID(admin_id)).first()
                    if user:
                        actual_user_id = UUID(admin_id)
                except Exception as e:
                    logger.warning(f"Could not verify admin user: {e}, using ticket raiser")
            
            # Create status update event
            status_event = TicketEvent(
                ticket_id=ticket_uuid,
                event_type="status_updated",
                actor_user_id=actual_user_id,
                payload={
                    "old_status": old_status,
                    "new_status": new_status,
                    "changed_at": datetime.utcnow().isoformat()
                }
            )
            db.add(status_event)
            db.commit()
            
            logger.info(f"✓ Ticket status updated: {ticket.ticket_no} now {new_status}")
            
            # Deprecate embeddings when ticket is closed or reopened
            if new_status in ["closed", "reopened"]:
                try:
                    from .embedding_manager import EmbeddingManager
                    EmbeddingManager.deprecate_ticket_embeddings(
                        ticket_id=ticket_id,
                        reason=f"ticket_{new_status}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to deprecate embeddings: {e}")
            
            # Audit log
            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="status_updated",
                        resource="ticket",
                        resource_id=ticket_id,
                        changes={
                            "ticket_no": ticket.ticket_no,
                            "old_status": old_status,
                            "new_status": new_status
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")
            
            return TicketService._format_ticket(ticket)
            
        except (ValidationError, NotFoundError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update ticket status: {e}")
            raise ValidationError(f"Failed to update status: {str(e)}")
        finally:
            db.close()
    
    
    @staticmethod
    def assign_ticket(
        ticket_id: str,
        engineer_id: str,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Assign ticket to engineer"""
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            engineer_uuid = UUID(engineer_id)
            
            # Verify ticket exists
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            # Verify engineer exists
            engineer = db.query(User).filter(User.id == engineer_uuid).first()
            if not engineer:
                raise NotFoundError("Engineer not found")
            
            old_engineer_id = ticket.assigned_engineer_id
            logger.info(f"Assigning ticket {ticket.ticket_no} to {engineer.name}")
            
            # Update assignment
            ticket.assigned_engineer_id = engineer_uuid
            ticket.updated_at = datetime.utcnow()
            db.flush()
            
            # Verify user for event logging
            actual_user_id = ticket.raised_by_user_id
            if admin_id:
                try:
                    user = db.query(User).filter(User.id == UUID(admin_id)).first()
                    if user:
                        actual_user_id = UUID(admin_id)
                except Exception as e:
                    logger.warning(f"Could not verify admin user: {e}, using ticket raiser")
            
            # Create assignment event
            if old_engineer_id:
                event_type = "ticket_assigned"
            else:
                event_type = "ticket_assigned"
            
            assignment_event = TicketEvent(
                ticket_id=ticket_uuid,
                event_type=event_type,
                actor_user_id=actual_user_id,
                payload={
                    "assigned_to": engineer.name,
                    "assigned_to_id": engineer_id,
                    "previous_assignment": None,
                    "assigned_at": datetime.utcnow().isoformat()
                }
            )
            db.add(assignment_event)
            db.commit()
            
            logger.info(f"✓ Ticket assigned: {ticket.ticket_no} → {engineer.name}")
            
            # Audit log
            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="ticket_assigned",
                        resource="ticket",
                        resource_id=ticket_id,
                        changes={
                            "ticket_no": ticket.ticket_no,
                            "assigned_to": engineer.name,
                            "assigned_to_id": engineer_id
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")
            
            return TicketService._format_ticket(ticket)
            
        except (ValidationError, NotFoundError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to assign ticket: {e}")
            raise ValidationError(f"Failed to assign ticket: {str(e)}")
        finally:
            db.close()
    
    @staticmethod
    def get_analytics(days: int = 30) -> Dict[str, Any]:
        """
        Get ticket analytics for the specified number of days.
        
        Args:
            days: Number of days to analyze (default 30, max 365)
            
        Returns:
            Dict containing analytics data:
            - total_tickets: Total number of tickets
            - tickets_by_status: Count of tickets by status
            - tickets_by_level: Count of tickets by level
            - tickets_by_category: Count of tickets by category
            - tickets_created_last_n_days: Tickets created in the period
            - avg_resolution_time: Average time to close tickets
            - open_tickets_count: Number of open tickets
            - closed_tickets_count: Number of closed tickets
            - resolution_rate: Percentage of resolved tickets
        """
        db = SessionLocal()
        try:
            from datetime import timedelta
            
            # Calculate date range
            now = datetime.utcnow()
            start_date = now - timedelta(days=days)
            
            logger.info(f"Getting analytics for last {days} days (from {start_date} to {now})")
            
            # Base query for tickets
            query = db.query(Ticket)
            
            # Total tickets (all time)
            total_tickets = query.count()
            
            # Tickets by status
            tickets_by_status = {}
            for status in ["open", "in_progress", "resolved", "closed", "reopened"]:
                count = query.filter(Ticket.status == status).count()
                if count > 0:
                    tickets_by_status[status] = count
            
            # Tickets by level
            tickets_by_level = {}
            for level in ["level-1", "level-2", "level-3"]:
                count = query.filter(Ticket.level == level).count()
                if count > 0:
                    tickets_by_level[level] = count
            
            # Tickets by category
            tickets_by_category = {}
            categories = db.query(Ticket.category).distinct().filter(
                Ticket.category.isnot(None)
            ).all()
            for (category,) in categories:
                if category:
                    count = query.filter(Ticket.category == category).count()
                    tickets_by_category[category] = count
            
            # Tickets created in the last N days
            tickets_created_last_n_days = query.filter(
                Ticket.created_at >= start_date
            ).count()
            
            # Closed tickets in the last N days
            closed_last_n_days = query.filter(
                Ticket.closed_at >= start_date,
                Ticket.closed_at.isnot(None)
            ).count()
            
            # Open tickets count
            open_tickets = query.filter(
                Ticket.status.in_(["open", "in_progress"])
            ).count()
            
            # Closed tickets count (all time)
            closed_tickets = query.filter(
                Ticket.status.in_(["closed", "resolved"])
            ).count()
            
            # Average resolution time
            avg_resolution_time = 0
            if closed_tickets > 0:
                closed_ticket_times = []
                closed_tickets_query = query.filter(
                    Ticket.closed_at.isnot(None)
                ).all()
                
                for ticket in closed_tickets_query:
                    if ticket.closed_at and ticket.created_at:
                        resolution_time = (ticket.closed_at - ticket.created_at).total_seconds()
                        closed_ticket_times.append(resolution_time)
                
                if closed_ticket_times:
                    avg_resolution_time = sum(closed_ticket_times) / len(closed_ticket_times)
                    # Convert to hours
                    avg_resolution_time = round(avg_resolution_time / 3600, 2)
            
            # Resolution rate
            resolution_rate = 0
            if total_tickets > 0:
                resolution_rate = round((closed_tickets / total_tickets) * 100, 2)
            
            # Ticket trends (daily count for last N days)
            trends = []
            current_date = start_date.date()
            end_date = now.date()
            
            while current_date <= end_date:
                day_start = datetime.combine(current_date, datetime.min.time())
                day_end = datetime.combine(current_date, datetime.max.time())
                
                daily_count = query.filter(
                    Ticket.created_at >= day_start,
                    Ticket.created_at <= day_end
                ).count()
                
                if daily_count > 0:
                    trends.append({
                        "date": current_date.isoformat(),
                        "count": daily_count
                    })
                
                current_date += timedelta(days=1)
            
            logger.info(f"Analytics retrieved: {total_tickets} total, {open_tickets} open, {closed_tickets} closed")
            
            return {
                "total_tickets": total_tickets,
                "open_tickets": open_tickets,
                "closed_tickets": closed_tickets,
                "tickets_by_status": tickets_by_status,
                "tickets_by_level": tickets_by_level,
                "tickets_by_category": tickets_by_category,
                "tickets_created_last_n_days": tickets_created_last_n_days,
                "closed_last_n_days": closed_last_n_days,
                "avg_resolution_time_hours": avg_resolution_time,
                "resolution_rate_percent": resolution_rate,
                "analysis_period_days": days,
                "trends": trends
            }
            
        except Exception as e:
            logger.error(f"Failed to retrieve analytics: {e}")
            raise ValidationError(f"Failed to retrieve analytics: {str(e)}")
        finally:
            db.close()