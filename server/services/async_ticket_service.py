# server/services/async_ticket_service.py
"""TRUE Async Ticket Service - Uses AsyncSession for all DB operations"""

from typing import Optional, Dict, Any
from datetime import date
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_

from core.async_database import AsyncSessionLocal
from core.database import Ticket, TicketEvent, AdminAuditLog, User
from utils.exceptions import ValidationError, NotFoundError
from core.logger import get_logger
from utils.datetime_utils import serialize_date_fields, to_iso_date

logger = get_logger(__name__)


class AsyncTicketService:
    """TRUE async service for ticket retrieval and updates (uses AsyncSession directly)"""
    
    @staticmethod
    async def get_tickets(
        company_id: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get paginated list of tickets with optional filtering and search"""
        async with AsyncSessionLocal() as session:
            try:
                # Start with base query
                query = select(Ticket)
                
                filters = []
                
                # Apply filters if provided
                if company_id:
                    try:
                        company_uuid = UUID(company_id)
                        filters.append(Ticket.company_id == company_uuid)
                    except ValueError:
                        logger.warning(f"Invalid company_id format: {company_id}")
                
                if status:
                    valid_statuses = ["open", "in_progress", "resolved", "closed", "reopened"]
                    if status in valid_statuses:
                        filters.append(Ticket.status == status)
                    else:
                        logger.warning(f"Invalid status filter: {status}")
                
                # Apply search filter if provided
                if search and search.strip():
                    search_term = f"%{search.strip()}%"
                    filters.append(
                        or_(
                            Ticket.ticket_no.ilike(search_term),
                            Ticket.subject.ilike(search_term),
                            Ticket.detailed_description.ilike(search_term)
                        )
                    )
                    logger.debug(f"Applied search filter: {search}")
                
                # Combine filters
                if filters:
                    from sqlalchemy import and_
                    query = query.where(and_(*filters))
                
                # Get total count before pagination
                count_query = select(Ticket)
                if filters:
                    count_query = count_query.where(and_(*filters))
                count_result = await session.execute(count_query)
                total = len(count_result.scalars().all())
                
                # Apply pagination and ordering
                query = query.order_by(desc(Ticket.created_at)).limit(limit).offset(offset)
                result = await session.execute(query)
                tickets = result.scalars().all()
                
                logger.info(f"Retrieved {len(tickets)} tickets (total: {total}, limit: {limit}, offset: {offset})")
                
                return {
                    "tickets": [await AsyncTicketService._format_ticket(t) for t in tickets],
                    "total": total,
                    "limit": limit,
                    "offset": offset
                }
                
            except Exception as e:
                logger.error(f"Failed to retrieve tickets: {e}")
                raise ValidationError(f"Failed to retrieve tickets: {str(e)}")
    
    @staticmethod
    async def get_ticket_by_id(ticket_id: str) -> Dict[str, Any]:
        """Get ticket by ID with all related data"""
        async with AsyncSessionLocal() as session:
            try:
                stmt = select(Ticket).where(Ticket.id == UUID(ticket_id))
                result = await session.execute(stmt)
                ticket = result.scalar_one_or_none()
                if not ticket:
                    raise NotFoundError("Ticket not found")
                
                return await AsyncTicketService._format_ticket(ticket)
            except NotFoundError:
                raise
            except Exception as e:
                logger.error(f"Failed to get ticket: {e}")
                raise ValidationError(f"Failed to get ticket: {str(e)}")
    
    @staticmethod
    async def get_ticket_by_number(ticket_no: str) -> Dict[str, Any]:
        """Get ticket by ticket number"""
        async with AsyncSessionLocal() as session:
            try:
                stmt = select(Ticket).where(Ticket.ticket_no == ticket_no)
                result = await session.execute(stmt)
                ticket = result.scalar_one_or_none()
                if not ticket:
                    raise NotFoundError(f"Ticket {ticket_no} not found")
                
                return await AsyncTicketService._format_ticket(ticket)
            except NotFoundError:
                raise
            except Exception as e:
                logger.error(f"Failed to get ticket by number: {e}")
                raise ValidationError(f"Failed to get ticket: {str(e)}")
    
    @staticmethod
    async def _format_ticket(ticket) -> Dict[str, Any]:
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
            "closed_at": to_iso_date(ticket.closed_at) if ticket.closed_at else None,
            "reopened_at": to_iso_date(ticket.reopened_at) if ticket.reopened_at else None,
            "attachments": [
                {
                    "id": str(att.id),
                    "type": att.type,
                    "file_path": att.file_path,
                    "mime_type": att.mime_type,
                    "created_at": to_iso_date(att.created_at)
                }
                for att in (ticket.attachments or [])
            ],
            "rca": {
                "id": str(ticket.root_cause_analysis.id),
                "root_cause_description": ticket.root_cause_analysis.root_cause_description,
                "contributing_factors": ticket.root_cause_analysis.contributing_factors or [],
                "prevention_measures": ticket.root_cause_analysis.prevention_measures,
                "resolution_steps": ticket.root_cause_analysis.resolution_steps or [],
                "related_ticket_ids": ticket.root_cause_analysis.related_ticket_ids or [],
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
                for event in (ticket.events or [])
            ],
            "has_ir": ticket.has_ir or False,
            "ir_number": ticket.ir_number,
            "ir_raised_at": to_iso_date(ticket.ir_raised_at) if ticket.ir_raised_at else None,
            "ir_expected_resolution_date": to_iso_date(ticket.ir_expected_resolution_date) if ticket.ir_expected_resolution_date else None,
            "ir_notes": ticket.ir_notes,
            "ir_closed_at": to_iso_date(ticket.ir_closed_at) if ticket.ir_closed_at else None,
        }
        return serialize_date_fields(response)
    
    @staticmethod
    async def update_ticket_status(
        ticket_id: str,
        new_status: str,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update ticket status asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                ticket_uuid = UUID(ticket_id)
                
                # Verify ticket exists
                stmt = select(Ticket).where(Ticket.id == ticket_uuid)
                result = await session.execute(stmt)
                ticket = result.scalar_one_or_none()
                if not ticket:
                    raise NotFoundError("Ticket not found")
                
                valid_statuses = ["open", "in_progress", "resolved", "closed", "reopened"]
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
                
                await session.flush()
                
                # Verify user for event logging
                actual_user_id = ticket.raised_by_user_id
                if admin_id:
                    try:
                        user_stmt = select(User).where(User.id == UUID(admin_id))
                        user_result = await session.execute(user_stmt)
                        user = user_result.scalar_one_or_none()
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
                session.add(status_event)
                await session.commit()
                
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
                
                return await AsyncTicketService._format_ticket(ticket)
                
            except (ValidationError, NotFoundError):
                await session.rollback()
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to update ticket status: {e}")
                raise ValidationError(f"Failed to update ticket status: {str(e)}")
    
    @staticmethod
    async def assign_ticket(
        ticket_id: str,
        engineer_id: str,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Assign ticket to engineer asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                ticket_uuid = UUID(ticket_id)
                engineer_uuid = UUID(engineer_id)
                
                # Verify ticket exists
                ticket_stmt = select(Ticket).where(Ticket.id == ticket_uuid)
                ticket_result = await session.execute(ticket_stmt)
                ticket = ticket_result.scalar_one_or_none()
                if not ticket:
                    raise NotFoundError("Ticket not found")
                
                # Verify engineer exists
                engineer_stmt = select(User).where(User.id == engineer_uuid)
                engineer_result = await session.execute(engineer_stmt)
                engineer = engineer_result.scalar_one_or_none()
                if not engineer:
                    raise NotFoundError("Engineer not found")
                
                old_engineer_id = ticket.assigned_engineer_id
                ticket.assigned_engineer_id = engineer_uuid
                ticket.updated_at = date.today()
                
                await session.flush()
                
                # Create assignment event
                assignment_event = TicketEvent(
                    ticket_id=ticket_uuid,
                    event_type="assigned",
                    actor_user_id=UUID(admin_id) if admin_id else ticket.raised_by_user_id,
                    payload={
                        "old_engineer_id": str(old_engineer_id) if old_engineer_id else None,
                        "new_engineer_id": str(engineer_uuid),
                        "engineer_name": engineer.name,
                        "assigned_at": to_iso_date(date.today())
                    }
                )
                session.add(assignment_event)
                await session.commit()
                
                logger.info(f"✓ Ticket {ticket.ticket_no} assigned to {engineer.name}")
                
                return await AsyncTicketService._format_ticket(ticket)
                
            except (ValidationError, NotFoundError):
                await session.rollback()
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to assign ticket: {e}")
                raise ValidationError(f"Failed to assign ticket: {str(e)}")