# server/services/ticket_service.py
"""Ticket retrieval and update service with embedding management"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, date, timedelta
from uuid import UUID

from core.database import (
    SessionLocal, Ticket, TicketEvent, AdminAuditLog, User,
    IncidentReport, RootCauseAnalysis, ResolutionNote
)
from utils.exceptions import ValidationError, NotFoundError, ConflictError
from core.logger import get_logger
from utils.datetime_utils import serialize_date_fields, to_iso_date
logger = get_logger(__name__)


class TicketService:
    """Service for ticket retrieval and updates"""
    @staticmethod
    def get_tickets(
        company_id: Optional[str] = None,
        status: Optional[str] = None,
        level: Optional[str] = None,
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
                valid_statuses = ["open", "in_progress", "resolved", "closed", "reopened", "user_input_required", "on_hold"]
                if status in valid_statuses:
                    query = query.filter(Ticket.status == status)
                else:
                    logger.warning(f"Invalid status filter: {status}")

            if level:
                valid_levels = ["level-1", "level-2", "level-3"]
                if level in valid_levels:
                    query = query.filter(Ticket.level == level)
                else:
                    logger.warning(f"Invalid level filter: {level}")
            
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
        response = {
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
            "created_at": to_iso_date(ticket.created_at),
            "updated_at": to_iso_date(ticket.updated_at),
            "closed_at": to_iso_date(ticket.closed_at)if ticket.closed_at else None,
            "reopened_at": to_iso_date(ticket.reopened_at) if ticket.reopened_at else None,
            "attachments": [
                {
                    "id": str(att.id),
                    "type": att.type,
                    "file_path": att.file_path,
                    "mime_type": att.mime_type,
                    "created_at": to_iso_date(att.created_at)
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
                        "created_at": to_iso_date(att.created_at)
                    }
                    for att in ticket.root_cause_analysis.attachments
                ] if ticket.root_cause_analysis.attachments else [],
                "created_at": to_iso_date(ticket.root_cause_analysis.created_at),
                "updated_at": to_iso_date(ticket.root_cause_analysis.updated_at)
            } if ticket.root_cause_analysis else None,
            "resolution_note": {
                "id": str(ticket.resolution_note.id),
                "solution_description": ticket.resolution_note.solution_description,
                "steps_taken": ticket.resolution_note.steps_taken or [],
                "resources_used": ticket.resolution_note.resources_used or [],
                "follow_up_notes": ticket.resolution_note.follow_up_notes,
                "created_at": to_iso_date(ticket.resolution_note.created_at),
                "updated_at": to_iso_date(ticket.resolution_note.updated_at)
            } if ticket.resolution_note else None,
            "events": [
                {
                    "id": str(event.id),
                    "event_type": event.event_type,
                    "actor_user_id": str(event.actor_user_id),
                    "actor": event.actor_user.name if event.actor_user else None,
                    "payload": event.payload,
                    "created_at": to_iso_date(event.created_at)
                }
                for event in ticket.events
            ] if ticket.events else [],
            "has_ir": ticket.has_ir or False,
            "ir_number": ticket.ir_number,
            "ir_raised_at": to_iso_date(ticket.ir_raised_at) if ticket.ir_raised_at else None,
            "ir_expected_resolution_date": to_iso_date(ticket.ir_expected_resolution_date) if ticket.ir_expected_resolution_date else None,
            "ir_notes": ticket.ir_notes,
            "ir_closed_at": to_iso_date(ticket.ir_closed_at) if ticket.ir_closed_at else None,
        }
        return serialize_date_fields(response)
    
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
            
            valid_statuses = ["open", "in_progress", "resolved", "closed", "reopened", "user_input_required", "on_hold"]
            if new_status not in valid_statuses:
                raise ValidationError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
            
            old_status = ticket.status
            logger.info(f"Updating ticket {ticket.ticket_no} status: {old_status} → {new_status}")
            
            # Update status
            ticket.status = new_status
            ticket.updated_at = date.today()
            
            if new_status == "closed":
                ticket.closed_at = date.today()
            elif new_status == "reopened":
                ticket.reopened_at = date.today()
            
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
                    "changed_at": to_iso_date(date.today())
                }
            )
            db.add(status_event)
            db.commit()
            
            logger.info(f"✓ Ticket status updated: {ticket.ticket_no} now {new_status}")
            
            # Trigger email notification
            try:
                from .email_listener_service import EmailListenerService
                EmailListenerService.on_ticket_status_updated(
                    ticket_id=ticket_id,
                    ticket_no=ticket.ticket_no,
                    company_id=str(ticket.company_id),
                    old_status=old_status,
                    new_status=new_status,
                    raised_by_user_id=str(ticket.raised_by_user_id),
                    raised_by_user_name=ticket.raised_by_user.name if ticket.raised_by_user else "User",
                    raised_by_user_email=ticket.raised_by_user.email if ticket.raised_by_user else ""
                )
            except Exception as e:
                logger.warning(f"Failed to trigger email notification: {e}")
            
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
            ticket.updated_at = date.today()
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
                    "assigned_at": to_iso_date(date.today())
                }
            )
            db.add(assignment_event)
            db.commit()
            
            logger.info(f"✓ Ticket assigned: {ticket.ticket_no} → {engineer.name}")
            
            # Trigger email notification
            try:
                from .email_listener_service import EmailListenerService
                EmailListenerService.on_ticket_assigned(
                    ticket_id=ticket_id,
                    ticket_no=ticket.ticket_no,
                    ticket_subject=ticket.subject,
                    company_id=str(ticket.company_id),
                    assigned_engineer_id=engineer_id,
                    assigned_engineer_name=engineer.name,
                    assigned_engineer_email=engineer.email
                )
            except Exception as e:
                logger.warning(f"Failed to trigger email notification: {e}")
            
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
            # Calculate date range
            now = date.today()
            start_date = now - timedelta(days=days)
            
            logger.info(f"Getting analytics for last {days} days (from {start_date} to {now})")
            
            # Base query for tickets
            query = db.query(Ticket)
            
            # Total tickets (all time)
            total_tickets = query.count()
            
            # Tickets by status
            tickets_by_status = {}
            for status in ["open", "in_progress", "resolved", "closed", "reopened", "user_input_required", "on_hold"]:
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
            
            avg_resolution_time = 0
            # Calculate average resolution time across ALL closed tickets (not limited by period)
            all_closed_tickets = query.filter(
                Ticket.status.in_(["closed", "resolved"]),
                Ticket.closed_at.isnot(None)
            ).all()
            
            logger.info(f"Found {len(all_closed_tickets)} closed tickets in database")
            
            if all_closed_tickets:
                closed_ticket_times = []
                for ticket in all_closed_tickets:
                    if ticket.closed_at and ticket.created_at:
                        resolution_time = (ticket.closed_at - ticket.created_at).total_seconds()
                        logger.debug(f"Ticket {ticket.ticket_no}: resolution_time={resolution_time}s")
                        # Only count valid resolutions (positive time)
                        if resolution_time >= 0:
                            closed_ticket_times.append(resolution_time)
                        else:
                            logger.warning(f"Ticket {ticket.ticket_no} has negative resolution time: {resolution_time}s (created_at={ticket.created_at}, closed_at={ticket.closed_at})")
                
                logger.info(f"Valid closed ticket times: {len(closed_ticket_times)} out of {len(all_closed_tickets)}")
                
                if closed_ticket_times:
                    avg_resolution_time = sum(closed_ticket_times) / len(closed_ticket_times)
                    # Convert to hours
                    avg_resolution_time = round(avg_resolution_time / 3600, 2)
                    logger.info(f"Average resolution time: {avg_resolution_time} hours")
                        
                        # Resolution rate
            resolution_rate = 0
            if total_tickets > 0:
                resolution_rate = round((closed_tickets / total_tickets) * 100, 2)
            
            # Ticket trends (daily count for last N days)
            trends = []
            current_date = start_date  # Already a date object from timedelta operation
            end_date = now  # Already a date object from date.today()

            while current_date <= end_date:
                daily_created = query.filter(
                    Ticket.created_at == current_date
                ).count()
                daily_closed = query.filter(
                    Ticket.closed_at == current_date,
                    Ticket.closed_at.isnot(None)
                ).count()
                
                trends.append({
                    "date": to_iso_date(current_date),
                    "created": daily_created,
                    "closed": daily_closed,
                    "net": daily_created - daily_closed
                })
                
                current_date += timedelta(days=1)

            open_statuses = ["open", "in_progress", "reopened", "user_input_required", "on_hold"]
            active_tickets = query.filter(Ticket.status.in_(open_statuses)).all()

            def ticket_age_days(ticket: Ticket) -> int:
                if not ticket.created_at:
                    return 0
                return max((now - ticket.created_at).days, 0)

            aging_buckets = {
                "0-1 days": 0,
                "2-3 days": 0,
                "4-7 days": 0,
                "8-14 days": 0,
                "15+ days": 0,
            }
            for ticket in active_tickets:
                age = ticket_age_days(ticket)
                if age <= 1:
                    aging_buckets["0-1 days"] += 1
                elif age <= 3:
                    aging_buckets["2-3 days"] += 1
                elif age <= 7:
                    aging_buckets["4-7 days"] += 1
                elif age <= 14:
                    aging_buckets["8-14 days"] += 1
                else:
                    aging_buckets["15+ days"] += 1

            needs_attention = sorted(active_tickets, key=ticket_age_days, reverse=True)[:5]
            needs_attention_list = [
                {
                    "id": str(ticket.id),
                    "ticket_no": ticket.ticket_no,
                    "subject": ticket.subject,
                    "status": ticket.status,
                    "level": ticket.level,
                    "company_name": ticket.company.name if ticket.company else None,
                    "age_days": ticket_age_days(ticket),
                    "created_at": to_iso_date(ticket.created_at),
                }
                for ticket in needs_attention
            ]

            stale_cutoff = now - timedelta(days=7)
            stale_tickets = []
            for ticket in active_tickets:
                last_event_at = max(
                    [event.created_at.date() for event in ticket.events if event.created_at] or [ticket.updated_at or ticket.created_at]
                )
                if last_event_at <= stale_cutoff:
                    stale_tickets.append({
                        "id": str(ticket.id),
                        "ticket_no": ticket.ticket_no,
                        "subject": ticket.subject,
                        "status": ticket.status,
                        "company_name": ticket.company.name if ticket.company else None,
                        "last_activity_at": to_iso_date(last_event_at),
                        "inactive_days": (now - last_event_at).days,
                    })

            open_ir_query = db.query(IncidentReport).filter(
                IncidentReport.status.in_(["open", "in_progress"])
            )
            open_irs = open_ir_query.count()
            overdue_irs = open_ir_query.filter(
                IncidentReport.expected_resolution_date.isnot(None),
                IncidentReport.expected_resolution_date < now
            ).count()

            closed_ticket_objs = query.filter(Ticket.status.in_(["closed", "resolved"])).all()
            closed_missing_rca = sum(1 for ticket in closed_ticket_objs if not ticket.root_cause_analysis)
            closed_missing_resolution = sum(1 for ticket in closed_ticket_objs if not ticket.resolution_note)
            rca_count = db.query(RootCauseAnalysis).count()
            resolution_note_count = db.query(ResolutionNote).count()

            rca_completion_rate = round(((len(closed_ticket_objs) - closed_missing_rca) / len(closed_ticket_objs)) * 100, 2) if closed_ticket_objs else 0
            resolution_note_completion_rate = round(((len(closed_ticket_objs) - closed_missing_resolution) / len(closed_ticket_objs)) * 100, 2) if closed_ticket_objs else 0

            company_health = []
            companies_seen = {}
            for ticket in query.all():
                company_name = ticket.company.name if ticket.company else "Unknown"
                if company_name not in companies_seen:
                    companies_seen[company_name] = {
                        "company_name": company_name,
                        "total": 0,
                        "open": 0,
                        "closed": 0,
                        "with_ir": 0,
                        "resolution_hours": [],
                    }
                item = companies_seen[company_name]
                item["total"] += 1
                if ticket.status in open_statuses:
                    item["open"] += 1
                if ticket.status in ["closed", "resolved"]:
                    item["closed"] += 1
                if ticket.has_ir:
                    item["with_ir"] += 1
                if ticket.closed_at and ticket.created_at and ticket.closed_at >= ticket.created_at:
                    item["resolution_hours"].append((ticket.closed_at - ticket.created_at).total_seconds() / 3600)

            for item in companies_seen.values():
                hours = item.pop("resolution_hours")
                item["closure_rate_percent"] = round((item["closed"] / item["total"]) * 100, 2) if item["total"] else 0
                item["avg_resolution_hours"] = round(sum(hours) / len(hours), 2) if hours else 0
                company_health.append(item)

            company_health = sorted(
                company_health,
                key=lambda item: (item["open"], item["total"]),
                reverse=True
            )[:8]

            category_performance = []
            for category, count in sorted(tickets_by_category.items(), key=lambda item: item[1], reverse=True):
                category_tickets = query.filter(Ticket.category == category).all()
                category_closed = [t for t in category_tickets if t.status in ["closed", "resolved"]]
                category_open = [t for t in category_tickets if t.status in open_statuses]
                resolution_hours = [
                    (t.closed_at - t.created_at).total_seconds() / 3600
                    for t in category_closed
                    if t.closed_at and t.created_at and t.closed_at >= t.created_at
                ]
                category_performance.append({
                    "category": category,
                    "total": count,
                    "open": len(category_open),
                    "closed": len(category_closed),
                    "closure_rate_percent": round((len(category_closed) / count) * 100, 2) if count else 0,
                    "avg_resolution_hours": round(sum(resolution_hours) / len(resolution_hours), 2) if resolution_hours else 0,
                })

            median_resolution_time_hours = 0
            if all_closed_tickets:
                median_values = sorted([
                    (ticket.closed_at - ticket.created_at).total_seconds() / 3600
                    for ticket in all_closed_tickets
                    if ticket.closed_at and ticket.created_at and ticket.closed_at >= ticket.created_at
                ])
                if median_values:
                    mid = len(median_values) // 2
                    if len(median_values) % 2 == 0:
                        median_resolution_time_hours = round((median_values[mid - 1] + median_values[mid]) / 2, 2)
                    else:
                        median_resolution_time_hours = round(median_values[mid], 2)
            
            logger.info(f"Analytics retrieved: {total_tickets} total, {open_tickets} open, {closed_tickets} closed")
            
            return {
                "total_tickets": total_tickets,
                "open_tickets": open_tickets,
                "in_progress": tickets_by_status.get("in_progress", 0),
                "resolved": tickets_by_status.get("resolved", 0),
                "closed": closed_tickets,
                "reopened": tickets_by_status.get("reopened", 0),
                "avg_resolution_time_hours": avg_resolution_time,
                "median_resolution_time_hours": median_resolution_time_hours,
                "resolution_rate_percent": resolution_rate,
                "categories": tickets_by_category,
                "levels": tickets_by_level,
                "tickets_created_last_n_days": tickets_created_last_n_days,
                "closed_last_n_days": closed_last_n_days,
                "aging_buckets": aging_buckets,
                "needs_attention": needs_attention_list,
                "stale_tickets": sorted(stale_tickets, key=lambda item: item["inactive_days"], reverse=True)[:5],
                "stale_tickets_count": len(stale_tickets),
                "open_irs": open_irs,
                "overdue_irs": overdue_irs,
                "quality": {
                    "rca_count": rca_count,
                    "resolution_note_count": resolution_note_count,
                    "closed_missing_rca": closed_missing_rca,
                    "closed_missing_resolution": closed_missing_resolution,
                    "rca_completion_rate_percent": rca_completion_rate,
                    "resolution_note_completion_rate_percent": resolution_note_completion_rate,
                },
                "company_health": company_health,
                "category_performance": category_performance[:8],
                "analysis_period_days": days,
                "trends": trends
            }
            
        except Exception as e:
            logger.error(f"Failed to retrieve analytics: {e}")
            raise ValidationError(f"Failed to retrieve analytics: {str(e)}")
        finally:
            db.close()
