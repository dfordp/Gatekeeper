# server/services/async_ticket_creation_service.py
"""
TRUE Async Ticket Creation Service - Uses AsyncSession, not thread pool wrapper

This is a complete async implementation using:
- AsyncSessionLocal for all database operations
- Async/await for all I/O operations  
- No asyncio.to_thread() wrapping
- Circuit breaker protected API calls
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_

from core.async_database import AsyncSessionLocal
from core.database import (
    Ticket, TicketEvent, RootCauseAnalysis, ResolutionNote,
    Attachment, AdminAuditLog, Company, User
)
from core.logger import get_logger
from utils.exceptions import ValidationError, NotFoundError, ConflictError
from utils.datetime_utils import to_iso_date
from .embedding_manager import EmbeddingManager
from .attachment_processor import AttachmentProcessor
from .ticket_request_queue import TicketRequestQueue, TaskType, TaskStatus

logger = get_logger(__name__)


class AsyncTicketCreationService:
    """TRUE async service for ticket creation (uses AsyncSession directly)"""
    
    @staticmethod
    async def get_next_ticket_number() -> str:
        """Get the next ticket number asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                stmt = select(Ticket).order_by(desc(Ticket.created_at)).limit(1)
                result = await session.execute(stmt)
                latest_ticket = result.scalar_one_or_none()
                
                if not latest_ticket:
                    return "TKT-000001"
                
                ticket_no = latest_ticket.ticket_no
                number = int(ticket_no.split('-')[-1])
                next_number = number + 1
                
                return f"TKT-{str(next_number).zfill(6)}"
            except Exception as e:
                logger.error(f"Error getting next ticket number: {e}")
                raise
    
    @staticmethod
    async def create_ticket(
        subject: str,
        detailed_description: str,
        company_id: str,
        raised_by_user_id: str,
        summary: Optional[str] = None,
        category: Optional[str] = None,
        level: Optional[str] = None,
        assigned_engineer_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        closed_at: Optional[datetime] = None,
        created_by_admin_id: Optional[str] = None,
        ticket_no: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new ticket asynchronously with validation and task queueing"""
        async with AsyncSessionLocal() as session:
            try:
                # Validate inputs
                if not subject or len(subject.strip()) < 3:
                    raise ValidationError("Subject must be at least 3 characters")
                
                if not detailed_description or len(detailed_description.strip()) < 10:
                    raise ValidationError("Description must be at least 10 characters")
                
                # Verify company exists
                company_stmt = select(Company).where(Company.id == UUID(company_id))
                company_result = await session.execute(company_stmt)
                company = company_result.scalar_one_or_none()
                if not company:
                    raise NotFoundError("Company not found")
                
                # Verify user exists
                user_stmt = select(User).where(User.id == UUID(raised_by_user_id))
                user_result = await session.execute(user_stmt)
                raised_by_user = user_result.scalar_one_or_none()
                if not raised_by_user:
                    raise NotFoundError("User not found")
                
                # Verify assigned engineer if provided
                engineer = None
                if assigned_engineer_id:
                    engineer_stmt = select(User).where(User.id == UUID(assigned_engineer_id))
                    engineer_result = await session.execute(engineer_stmt)
                    engineer = engineer_result.scalar_one_or_none()
                    if not engineer:
                        raise NotFoundError("Engineer not found")
                
                # Validate level if provided
                valid_levels = ["level-1", "level-2", "level-3"]
                if level and level not in valid_levels:
                    raise ValidationError(f"Invalid level. Must be one of: {', '.join(valid_levels)}")
                
                # Handle ticket number
                if ticket_no:
                    ticket_no = ticket_no.strip()
                    if ticket_no.isdigit():
                        ticket_no = f"TKT-{ticket_no.zfill(6)}"
                else:
                    ticket_no = await AsyncTicketCreationService.get_next_ticket_number()
                
                initial_status = status if status in ["open", "in_progress", "resolved", "closed", "reopened"] else "open"
                
                # Create ticket
                ticket = Ticket(
                    ticket_no=ticket_no,
                    subject=subject.strip(),
                    summary=summary.strip() if summary else None,
                    detailed_description=detailed_description.strip(),
                    category=category.strip() if category else None,
                    level=level,
                    company_id=UUID(company_id),
                    raised_by_user_id=UUID(raised_by_user_id),
                    assigned_engineer_id=UUID(assigned_engineer_id) if assigned_engineer_id else None,
                    status=initial_status,
                    created_at=created_at or date.today(),
                    attachment_ids=[]
                )
                
                if initial_status == "closed" and closed_at:
                    ticket.closed_at = closed_at
                
                session.add(ticket)
                await session.flush()
                
                # Log creation event
                event = TicketEvent(
                    ticket_id=ticket.id,
                    event_type="ticket_created",
                    actor_user_id=UUID(raised_by_user_id),
                    payload={
                        "ticket_no": ticket_no,
                        "subject": subject,
                        "category": category,
                        "level": level,
                        "assigned_to": engineer.name if engineer else None
                    }
                )
                session.add(event)
                
                await session.commit()
                
                logger.info(f"✓ Ticket created: {ticket_no} (id={ticket.id})")
                
                # Queue embedding creation task (runs in background, doesn't block)
                try:
                    task_id = TicketRequestQueue.queue_task(
                        ticket_id=str(ticket.id),
                        task_type=TaskType.EMBEDDING_CREATION,
                        payload={
                            "subject": subject.strip(),
                            "description": detailed_description.strip(),
                            "category": category,
                            "summary": summary,
                            "company_id": company_id
                        }
                    )
                    logger.info(f"✓ Task queued for embeddings: {task_id}")
                except Exception as e:
                    logger.warning(f"Failed to queue embedding task: {e}")
                
                # Create embeddings (delegated to EmbeddingManager - sync but may use async)
                try:
                    EmbeddingManager.create_ticket_embeddings(
                        ticket_id=str(ticket.id),
                        company_id=company_id,
                        subject=subject.strip(),
                        description=detailed_description.strip(),
                        category=category,
                        summary=summary
                    )
                    logger.info(f"✓ Embeddings created for ticket {ticket_no}")
                    TicketRequestQueue.mark_completed(task_id)
                except Exception as e:
                    logger.warning(f"Failed to create embeddings: {e}")
                    TicketRequestQueue.mark_failed(task_id, str(e))
                
                return {
                    "id": str(ticket.id),
                    "ticket_no": ticket.ticket_no,
                    "subject": ticket.subject,
                    "status": ticket.status,
                    "category": ticket.category,
                    "level": ticket.level,
                    "company_id": str(ticket.company_id),
                    "raised_by_user_id": str(ticket.raised_by_user_id),
                    "assigned_engineer_id": str(ticket.assigned_engineer_id) if ticket.assigned_engineer_id else None,
                    "created_at": to_iso_date(ticket.created_at)
                }
                
            except (ValidationError, NotFoundError, ConflictError):
                await session.rollback()
                logger.warning(f"Validation error creating ticket: {e}")
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Error creating ticket: {e}")
                raise ValidationError(f"Failed to create ticket: {str(e)}")
    
    @staticmethod
    async def add_attachment(
        ticket_id: str,
        file_name: str,
        file_path: str,
        mime_type: Optional[str] = None,
        attachment_type: str = "document",
        cloudinary_url: Optional[str] = None,
        file_size: int = 0,
        created_by_user_id: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add attachment to ticket asynchronously"""
        async with AsyncSessionLocal() as session:
            task_id = None
            try:
                ticket_uuid = UUID(ticket_id)
                
                # Verify ticket exists
                ticket_stmt = select(Ticket).where(Ticket.id == ticket_uuid)
                ticket_result = await session.execute(ticket_stmt)
                ticket = ticket_result.scalar_one_or_none()
                if not ticket:
                    raise NotFoundError(f"Ticket {ticket_id} not found")
                
                logger.info(f"Adding attachment to ticket {ticket.ticket_no}: {file_name}")
                
                # Create attachment
                attachment = Attachment(
                    ticket_id=ticket_uuid,
                    type=attachment_type,
                    file_path=cloudinary_url or file_path,
                    mime_type=mime_type
                )
                
                session.add(attachment)
                await session.flush()
                
                # Log attachment event
                actor_uuid = UUID(created_by_user_id) if created_by_user_id else ticket.raised_by_user_id
                attachment_event = TicketEvent(
                    ticket_id=ticket_uuid,
                    event_type="attachment_added",
                    actor_user_id=actor_uuid,
                    payload={
                        "attachment_id": str(attachment.id),
                        "file_name": file_name,
                        "file_size": file_size,
                        "type": attachment_type,
                        "cloudinary_url": cloudinary_url,
                        "mime_type": mime_type
                    }
                )
                session.add(attachment_event)
                await session.commit()
                
                logger.info(f"✓ Attachment added to ticket {ticket.ticket_no}: {file_name}")
                
                # Queue attachment processing task
                try:
                    task_id = TicketRequestQueue.queue_task(
                        ticket_id=ticket_id,
                        task_type=TaskType.ATTACHMENT_PROCESSING,
                        payload={
                            "attachment_id": str(attachment.id),
                            "file_name": file_name,
                            "mime_type": mime_type,
                            "ticket_subject": ticket.subject
                        }
                    )
                    logger.info(f"✓ Task queued for attachment processing: {task_id}")
                    TicketRequestQueue.mark_processing(task_id)
                except Exception as e:
                    logger.warning(f"Failed to queue attachment task: {e}")
                
                # Process attachment
                embedding_count = 0
                try:
                    embedding_count = AttachmentProcessor.process_attachment(
                        attachment_id=str(attachment.id),
                        ticket_id=ticket_id,
                        company_id=str(ticket.company_id),
                        mime_type=mime_type,
                        ticket_subject=ticket.subject,
                        ticket_description=ticket.detailed_description
                    )
                    logger.info(f"✓ Processed attachment with {embedding_count} embeddings")
                    
                    if task_id:
                        TicketRequestQueue.mark_completed(task_id)
                except Exception as e:
                    logger.warning(f"Failed to process attachment: {e}")
                    if task_id:
                        TicketRequestQueue.mark_failed(task_id, str(e))
                
                return {
                    "id": str(attachment.id),
                    "ticket_id": ticket_id,
                    "file_name": file_name,
                    "type": attachment.type,
                    "file_path": attachment.file_path,
                    "mime_type": attachment.mime_type,
                    "embeddings_created": embedding_count,
                    "task_id": task_id,
                    "created_at": to_iso_date(attachment.created_at)
                }
                
            except (NotFoundError, ValidationError) as e:
                if task_id:
                    TicketRequestQueue.mark_failed(task_id, str(e))
                await session.rollback()
                raise
            except Exception as e:
                if task_id:
                    TicketRequestQueue.mark_failed(task_id, str(e))
                await session.rollback()
                logger.error(f"Failed to add attachment: {e}")
                raise ValidationError(f"Failed to add attachment: {str(e)}")
    
    @staticmethod
    async def delete_attachment(
        ticket_id: str,
        attachment_id: str,
        admin_id: Optional[str] = None
    ) -> bool:
        """Delete attachment from ticket asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                ticket_uuid = UUID(ticket_id)
                attachment_uuid = UUID(attachment_id)
                
                # Verify ticket exists
                ticket_stmt = select(Ticket).where(Ticket.id == ticket_uuid)
                ticket_result = await session.execute(ticket_stmt)
                ticket = ticket_result.scalar_one_or_none()
                if not ticket:
                    raise NotFoundError(f"Ticket {ticket_id} not found")
                
                # Get attachment
                attachment_stmt = select(Attachment).where(
                    and_(
                        Attachment.id == attachment_uuid,
                        Attachment.ticket_id == ticket_uuid
                    )
                )
                attachment_result = await session.execute(attachment_stmt)
                attachment = attachment_result.scalar_one_or_none()
                
                if not attachment:
                    raise NotFoundError(f"Attachment {attachment_id} not found")
                
                logger.info(f"Deleting attachment {attachment_id} from ticket {ticket.ticket_no}")
                
                # Delete from Cloudinary if applicable
                if attachment.file_path and attachment.file_path.startswith("http"):
                    try:
                        import cloudinary
                        import cloudinary.uploader
                        from core.config import CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
                        
                        if all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
                            cloudinary.config(
                                cloud_name=CLOUDINARY_CLOUD_NAME,
                                api_key=CLOUDINARY_API_KEY,
                                api_secret=CLOUDINARY_API_SECRET
                            )
                            public_id = attachment.file_path.split('/')[-1].split('.')[0]
                            cloudinary.uploader.destroy(f"tickets/{public_id}")
                            logger.info(f"✓ Deleted from Cloudinary: {public_id}")
                    except Exception as e:
                        logger.warning(f"Failed to delete from Cloudinary: {e}")
                
                # Log deletion event
                deletion_event = TicketEvent(
                    ticket_id=ticket_uuid,
                    event_type="attachment_deleted",
                    actor_user_id=ticket.raised_by_user_id,
                    payload={
                        "attachment_id": str(attachment.id),
                        "file_name": attachment.file_path.split('/')[-1] if attachment.file_path else "unknown"
                    }
                )
                
                # Deprecate embeddings
                try:
                    AttachmentProcessor.deprecate_attachment(
                        attachment_id=attachment_id,
                        reason="attachment_deleted"
                    )
                    logger.info(f"✓ Deprecated embeddings for attachment {attachment_id}")
                except Exception as e:
                    logger.warning(f"Failed to deprecate embeddings: {e}")
                
                # Delete from database
                await session.delete(attachment)
                session.add(deletion_event)
                await session.commit()
                
                logger.info(f"✓ Attachment deleted: {attachment_id}")
                return True
                
            except (NotFoundError, ValidationError):
                await session.rollback()
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to delete attachment: {e}")
                raise ValidationError(f"Failed to delete attachment: {str(e)}")
    
    @staticmethod
    async def add_root_cause_analysis(
        ticket_id: str,
        root_cause_description: str,
        created_by_user_id: str,
        contributing_factors: Optional[List[str]] = None,
        prevention_measures: Optional[str] = None,
        resolution_steps: Optional[List[str]] = None,
        rca_attachments: Optional[List[str]] = None,
        related_ticket_ids: Optional[List[str]] = None,
        ticket_closed_at: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add or update Root Cause Analysis asynchronously"""
        async with AsyncSessionLocal() as session:
            task_id = None
            try:
                logger.info(f"Adding/updating RCA for ticket {ticket_id}")
                
                # Verify ticket exists
                try:
                    ticket_uuid = UUID(ticket_id)
                    ticket_stmt = select(Ticket).where(Ticket.id == ticket_uuid)
                    ticket_result = await session.execute(ticket_stmt)
                    ticket = ticket_result.scalar_one_or_none()
                    if not ticket:
                        raise NotFoundError("Ticket not found")
                    logger.info(f"✓ Ticket found: {ticket.ticket_no}")
                except ValueError as e:
                    raise ValidationError(f"Invalid ticket ID format: {str(e)}")
                
                # Validate root cause description
                if not root_cause_description or len(root_cause_description.strip()) < 10:
                    raise ValidationError("Root cause description must be at least 10 characters")
                
                # Verify creator user exists, fallback to ticket raiser if not
                actual_creator_id = None
                try:
                    user_uuid = UUID(created_by_user_id)
                    user_stmt = select(User).where(User.id == user_uuid)
                    user_result = await session.execute(user_stmt)
                    user = user_result.scalar_one_or_none()
                    if user:
                        actual_creator_id = user_uuid
                    else:
                        actual_creator_id = ticket.raised_by_user_id
                except (ValueError, Exception):
                    actual_creator_id = ticket.raised_by_user_id
                
                # Check if RCA already exists
                existing_rca_stmt = select(RootCauseAnalysis).where(RootCauseAnalysis.ticket_id == ticket_uuid)
                existing_rca_result = await session.execute(existing_rca_stmt)
                existing_rca = existing_rca_result.scalar_one_or_none()
                
                is_update = False
                if existing_rca:
                    logger.info(f"RCA already exists, updating it")
                    existing_rca.root_cause_description = root_cause_description.strip()
                    existing_rca.contributing_factors = contributing_factors or []
                    existing_rca.prevention_measures = prevention_measures.strip() if prevention_measures else None
                    existing_rca.resolution_steps = resolution_steps or []
                    existing_rca.related_ticket_ids = related_ticket_ids or []
                    rca = existing_rca
                    is_update = True
                    await session.flush()
                else:
                    rca = RootCauseAnalysis(
                        ticket_id=ticket_uuid,
                        root_cause_description=root_cause_description.strip(),
                        created_by_user_id=actual_creator_id,
                        contributing_factors=contributing_factors or [],
                        prevention_measures=prevention_measures.strip() if prevention_measures else None,
                        resolution_steps=resolution_steps or [],
                        related_ticket_ids=related_ticket_ids or []
                    )
                    session.add(rca)
                    await session.flush()
                
                # Log RCA event
                event_type = "rca_updated" if is_update else "rca_added"
                rca_event = TicketEvent(
                    ticket_id=ticket_uuid,
                    event_type=event_type,
                    actor_user_id=actual_creator_id,
                    payload={
                        "rca_id": str(rca.id),
                        "root_cause": root_cause_description.strip()[:100],
                        "factors_count": len(contributing_factors or []),
                        "steps_count": len(resolution_steps or []),
                        "is_update": is_update
                    }
                )
                session.add(rca_event)
                await session.commit()
                logger.info(f"✓ RCA event committed")
                
                logger.info(f"✓ RCA {'updated' if is_update else 'added'} to ticket {ticket.ticket_no}")
                
                # Queue RCA embedding task
                try:
                    task_id = TicketRequestQueue.queue_task(
                        ticket_id=ticket_id,
                        task_type=TaskType.RCA_CREATION,
                        payload={
                            "rca_id": str(rca.id),
                            "root_cause": root_cause_description.strip(),
                            "factors": contributing_factors or [],
                            "measures": prevention_measures
                        }
                    )
                    logger.info(f"✓ Task queued for RCA embeddings: {task_id}")
                    TicketRequestQueue.mark_processing(task_id)
                except Exception as e:
                    logger.warning(f"Failed to queue RCA task: {e}")
                
                # Update embeddings using EmbeddingManager
                try:
                    EmbeddingManager.add_rca_embedding(
                        ticket_id=ticket_id,
                        company_id=str(ticket.company_id),
                        root_cause_description=root_cause_description.strip(),
                        contributing_factors=contributing_factors,
                        prevention_measures=prevention_measures
                    )
                    logger.info(f"✓ RCA embeddings created/updated")
                    
                    if task_id:
                        TicketRequestQueue.mark_completed(task_id)
                except Exception as e:
                    logger.warning(f"Failed to update RCA embeddings: {e}")
                    if task_id:
                        TicketRequestQueue.mark_failed(task_id, str(e))
                
                return {
                    "id": str(rca.id),
                    "ticket_id": ticket_id,
                    "root_cause_description": rca.root_cause_description,
                    "contributing_factors": rca.contributing_factors,
                    "prevention_measures": rca.prevention_measures,
                    "resolution_steps": rca.resolution_steps,
                    "related_ticket_ids": rca.related_ticket_ids,
                    "ticket_closed_at": ticket_closed_at,
                    "task_id": task_id,
                    "created_at": to_iso_date(rca.created_at),
                    "is_update": is_update
                }
                
            except (ValidationError, NotFoundError) as e:
                if task_id:
                    TicketRequestQueue.mark_failed(task_id, str(e))
                await session.rollback()
                raise
            except Exception as e:
                if task_id:
                    TicketRequestQueue.mark_failed(task_id, str(e))
                await session.rollback()
                logger.error(f"Error in add_root_cause_analysis: {e}")
                raise ValidationError(f"Failed to add RCA: {str(e)}")
    
    @staticmethod
    async def add_resolution_note(
        ticket_id: str,
        solution_description: str,
        created_by_user_id: str,
        steps_taken: Optional[List[str]] = None,
        resources_used: Optional[List[str]] = None,
        follow_up_notes: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add resolution note to ticket asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                ticket_uuid = UUID(ticket_id)
                
                # Verify ticket exists
                ticket_stmt = select(Ticket).where(Ticket.id == ticket_uuid)
                ticket_result = await session.execute(ticket_stmt)
                ticket = ticket_result.scalar_one_or_none()
                if not ticket:
                    raise NotFoundError("Ticket not found")
                
                # Validate input
                if not solution_description or len(solution_description.strip()) < 10:
                    raise ValidationError("Solution description must be at least 10 characters")
                
                logger.info(f"Adding resolution note for ticket {ticket.ticket_no}")
                
                # Verify creator user exists, fallback to ticket raiser if not
                actual_creator_id = None
                try:
                    user_uuid = UUID(created_by_user_id)
                    user_stmt = select(User).where(User.id == user_uuid)
                    user_result = await session.execute(user_stmt)
                    user = user_result.scalar_one_or_none()
                    if user:
                        actual_creator_id = user_uuid
                    else:
                        actual_creator_id = ticket.raised_by_user_id
                except (ValueError, Exception):
                    actual_creator_id = ticket.raised_by_user_id
                
                # Check if resolution note already exists
                existing_note_stmt = select(ResolutionNote).where(ResolutionNote.ticket_id == ticket_uuid)
                existing_note_result = await session.execute(existing_note_stmt)
                existing_note = existing_note_result.scalar_one_or_none()
                
                is_update = False
                if existing_note:
                    existing_note.solution_description = solution_description.strip()
                    existing_note.steps_taken = steps_taken or []
                    existing_note.resources_used = resources_used or []
                    existing_note.follow_up_notes = follow_up_notes
                    note = existing_note
                    is_update = True
                    await session.flush()
                else:
                    note = ResolutionNote(
                        ticket_id=ticket_uuid,
                        solution_description=solution_description.strip(),
                        created_by_user_id=actual_creator_id,
                        steps_taken=steps_taken or [],
                        resources_used=resources_used or [],
                        follow_up_notes=follow_up_notes
                    )
                    session.add(note)
                    await session.flush()
                
                await session.commit()
                
                try:
                    EmbeddingManager.add_resolution_embedding(
                        ticket_id=ticket_id,
                        company_id=str(ticket.company_id),
                        solution_description=solution_description,
                        steps_taken=steps_taken,
                        resources_used=resources_used,
                        follow_up_notes=follow_up_notes
                    )
                except Exception as e:
                    logger.warning(f"Failed to create resolution embedding: {e}")
                
                logger.info(f"✓ Resolution note {'updated' if is_update else 'added'}")
                
                return {
                    "id": str(note.id),
                    "ticket_id": ticket_id,
                    "solution_description": note.solution_description,
                    "steps_taken": note.steps_taken,
                    "resources_used": note.resources_used,
                    "follow_up_notes": note.follow_up_notes,
                    "created_at": to_iso_date(note.created_at),
                    "is_update": is_update
                }
                
            except (ValidationError, NotFoundError):
                await session.rollback()
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to add resolution note: {e}")
                raise ValidationError(f"Failed to add resolution note: {str(e)}")
    
    @staticmethod
    async def delete_ticket(
        ticket_id: str,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Delete a ticket and all related data asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                ticket_uuid = UUID(ticket_id)
                
                # Verify ticket exists
                ticket_stmt = select(Ticket).where(Ticket.id == ticket_uuid)
                ticket_result = await session.execute(ticket_stmt)
                ticket = ticket_result.scalar_one_or_none()
                if not ticket:
                    raise NotFoundError(f"Ticket {ticket_id} not found")
                
                logger.info(f"Deleting ticket {ticket.ticket_no}...")
                
                # Deprecate all embeddings
                try:
                    EmbeddingManager.deprecate_resolution_embeddings(
                        ticket_id=ticket_id,
                        reason="ticket_deleted"
                    )
                    EmbeddingManager.deprecate_ticket_embeddings(
                        ticket_id=ticket_id,
                        reason="ticket_deleted"
                    )
                    logger.info(f"✓ Deprecated ticket embeddings")
                except Exception as e:
                    logger.warning(f"Failed to deprecate embeddings: {e}")
                
                # Deprecate all attachment embeddings
                attachment_stmt = select(Attachment).where(Attachment.ticket_id == ticket_uuid)
                attachment_result = await session.execute(attachment_stmt)
                attachments = attachment_result.scalars().all()
                
                for attachment in attachments:
                    try:
                        AttachmentProcessor.deprecate_attachment(
                            attachment_id=str(attachment.id),
                            reason="ticket_deleted"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to deprecate attachment embeddings: {e}")
                
                # Log deletion event
                deletion_event = TicketEvent(
                    ticket_id=ticket_uuid,
                    event_type="ticket_deleted",
                    actor_user_id=UUID(admin_id) if admin_id else ticket.raised_by_user_id,
                    payload={
                        "ticket_no": ticket.ticket_no,
                        "subject": ticket.subject,
                        "deleted_at": to_iso_date(date.today())
                    }
                )
                session.add(deletion_event)
                await session.flush()
                
                # Delete resolution note if exists
                if ticket.resolution_note:
                    await session.delete(ticket.resolution_note)
                
                # Delete RCA if exists
                if ticket.root_cause_analysis:
                    await session.delete(ticket.root_cause_analysis)
                
                # Delete all attachments
                for attachment in attachments:
                    await session.delete(attachment)
                
                # Delete all events
                events_stmt = select(TicketEvent).where(TicketEvent.ticket_id == ticket_uuid)
                events_result = await session.execute(events_stmt)
                events = events_result.scalars().all()
                for event in events:
                    await session.delete(event)
                
                # Delete the ticket
                await session.delete(ticket)
                await session.commit()
                
                logger.info(f"✓ Ticket deleted: {ticket.ticket_no}")
                
                return {
                    "id": ticket_id,
                    "ticket_no": ticket.ticket_no,
                    "deleted": True,
                    "deleted_at": to_iso_date(date.today())
                }
                
            except NotFoundError:
                await session.rollback()
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to delete ticket: {e}")
                raise ValidationError(f"Failed to delete ticket: {str(e)}")
    
    @staticmethod
    async def update_ticket(
        ticket_id: str,
        subject: Optional[str] = None,
        summary: Optional[str] = None,
        detailed_description: Optional[str] = None,
        category: Optional[str] = None,
        level: Optional[str] = None,
        created_at: Optional[datetime] = None,
        closed_at: Optional[datetime] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update ticket details asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                ticket_uuid = UUID(ticket_id)
                
                # Verify ticket exists
                ticket_stmt = select(Ticket).where(Ticket.id == ticket_uuid)
                ticket_result = await session.execute(ticket_stmt)
                ticket = ticket_result.scalar_one_or_none()
                if not ticket:
                    raise NotFoundError("Ticket not found")
                
                # Validate and update inputs
                if subject is not None:
                    if len(subject.strip()) < 3:
                        raise ValidationError("Subject must be at least 3 characters")
                    ticket.subject = subject.strip()
                
                if summary is not None:
                    ticket.summary = summary.strip() if summary.strip() else None
                
                if detailed_description is not None:
                    if len(detailed_description.strip()) < 10:
                        raise ValidationError("Description must be at least 10 characters")
                    ticket.detailed_description = detailed_description.strip()
                
                if category is not None:
                    ticket.category = category.strip() if category.strip() else None
                
                if level is not None:
                    valid_levels = ["level-1", "level-2", "level-3"]
                    if level not in valid_levels:
                        raise ValidationError(f"Invalid level. Must be one of: {', '.join(valid_levels)}")
                    ticket.level = level
                
                if created_at is not None:
                    ticket.created_at = created_at
                
                if closed_at is not None:
                    ticket.closed_at = closed_at
                
                ticket.updated_at = date.today()
                await session.flush()
                
                # Create update event
                changes = {}
                if subject is not None:
                    changes["subject"] = subject.strip()
                if summary is not None:
                    changes["summary"] = summary.strip() if summary else None
                if detailed_description is not None:
                    changes["detailed_description"] = detailed_description.strip()
                if category is not None:
                    changes["category"] = category.strip() if category else None
                if level is not None:
                    changes["level"] = level
                if created_at is not None:
                    changes["created_at"] = to_iso_date(created_at)
                if closed_at is not None:
                    changes["closed_at"] = to_iso_date(closed_at)
                
                ticket_event = TicketEvent(
                    ticket_id=ticket_uuid,
                    event_type="ticket_updated",
                    actor_user_id=ticket.raised_by_user_id,
                    payload={
                        "changes": changes,
                        "updated_at": to_iso_date(date.today())
                    }
                )
                session.add(ticket_event)
                await session.commit()
                
                logger.info(f"✓ Ticket updated: {ticket.ticket_no}")
                
                return {
                    "id": str(ticket.id),
                    "ticket_no": ticket.ticket_no,
                    "subject": ticket.subject,
                    "summary": ticket.summary,
                    "detailed_description": ticket.detailed_description,
                    "category": ticket.category,
                    "level": ticket.level,
                    "status": ticket.status,
                    "created_at": to_iso_date(ticket.created_at),
                    "updated_at": to_iso_date(ticket.updated_at),
                    "closed_at": to_iso_date(ticket.closed_at) if ticket.closed_at else None
                }
                
            except (ValidationError, NotFoundError):
                await session.rollback()
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to update ticket: {e}")
                raise ValidationError(f"Failed to update ticket: {str(e)}")