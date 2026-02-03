# server/services/ticket_creation_service.py
"""
Ticket Creation Service - Delegates to existing services with task queue tracking

Handles ticket creation, attachments, RCA, and resolution notes.
Uses existing services:
- EmbeddingManager: Embedding lifecycle management
- AttachmentProcessor: Attachment processing with Grok Vision
- TicketRequestQueue: Task status tracking for frontend polling
"""

import logging
import sys
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

from core.database import (
    SessionLocal, Ticket, TicketEvent, RootCauseAnalysis, ResolutionNote,
    Attachment, AdminAuditLog, Company, User
)
from .embedding_manager import EmbeddingManager
from .attachment_processor import AttachmentProcessor
from .ticket_request_queue import TicketRequestQueue, TaskType, TaskStatus

from utils.exceptions import ValidationError, NotFoundError, ConflictError
from core.logger import get_logger

logger = get_logger(__name__)


class TicketCreationService:
    """Service for ticket creation and management with task queue tracking"""
    
    @staticmethod
    def get_next_ticket_number() -> str:
        """Get the next ticket number"""
        db = SessionLocal()
        try:
            latest_ticket = db.query(Ticket).order_by(Ticket.created_at.desc()).first()
            
            if not latest_ticket:
                return "TKT-000001"
            
            ticket_no = latest_ticket.ticket_no
            number = int(ticket_no.split('-')[-1])
            next_number = number + 1
            
            return f"TKT-{str(next_number).zfill(6)}"
        finally:
            db.close()
    
    
    @staticmethod
    def create_ticket(
        subject: str,
        detailed_description: str,
        company_id: str,
        raised_by_user_id: str,
        summary: Optional[str] = None,
        category: Optional[str] = None,
        level: Optional[str] = None,
        assigned_engineer_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        created_by_admin_id: Optional[str] = None,
        ticket_no: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new ticket with full validation and task queue tracking.
        Immediately queues embedding creation task.
        """
        db = SessionLocal()
        try:
            # Validate inputs
            if not subject or len(subject.strip()) < 3:
                raise ValidationError("Subject must be at least 3 characters")
            
            if not detailed_description or len(detailed_description.strip()) < 10:
                raise ValidationError("Description must be at least 10 characters")
            
            # Verify company exists
            company = db.query(Company).filter(Company.id == UUID(company_id)).first()
            if not company:
                raise NotFoundError("Company not found")
            
            # Verify user exists
            raised_by_user = db.query(User).filter(
                User.id == UUID(raised_by_user_id)
            ).first()
            if not raised_by_user:
                raise NotFoundError("User not found")   
            
            # Verify assigned engineer if provided
            engineer = None
            if assigned_engineer_id:
                engineer = db.query(User).filter(
                    User.id == UUID(assigned_engineer_id),
                ).first()
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
                ticket_no = TicketCreationService.get_next_ticket_number()
            
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
                created_at=created_at or datetime.utcnow(),
                attachment_ids=[]
            )
            
            # Set closed_at if status is closed
            if initial_status == "closed" and created_at:
                try:
                    if isinstance(created_at, str):
                        ticket.closed_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    else:
                        ticket.closed_at = created_at
                except Exception as e:
                    logger.warning(f"Failed to parse closed_at date: {e}")
            
            db.add(ticket)
            db.flush()
            
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
            db.add(event)
            db.commit()
            
            # Audit log
            if created_by_admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(created_by_admin_id),
                        action="ticket_created",
                        resource="ticket",
                        resource_id=str(ticket.id),
                        changes={
                            "ticket_no": ticket_no,
                            "subject": subject,
                            "company_id": company_id,
                            "is_older_ticket": created_at is not None,
                            "status": initial_status
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")
            
            logger.info(f"✓ Ticket created: {ticket_no}")
            
            # Queue embedding creation task
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
            
            # Create embeddings synchronously using EmbeddingManager
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
                
                # Mark embedding task as completed
                if 'task_id' in locals():
                    TicketRequestQueue.mark_completed(task_id)
            except Exception as e:
                logger.warning(f"Failed to create embeddings for ticket: {e}")
                if 'task_id' in locals():
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
                "created_at": ticket.created_at.isoformat()
            }
            
        except (ValidationError, NotFoundError, ConflictError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Unexpected error creating ticket: {e}")
            raise ValidationError(f"Failed to create ticket: {str(e)}")
        finally:
            db.close()
    
    
    @staticmethod
    def add_attachment(
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
        """
        Add attachment to ticket with task queue tracking.
        Processes attachment synchronously and updates task status on completion.
        """
        db = SessionLocal()
        task_id = None
        
        try:
            ticket_uuid = UUID(ticket_id)
            
            # Verify ticket exists
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
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
            
            db.add(attachment)
            db.flush()
            
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
            db.add(attachment_event)
            db.commit()
            
            # Audit log
            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="attachment_added",
                        resource="attachment",
                        resource_id=str(attachment.id),
                        changes={
                            "ticket_id": ticket_id,
                            "file_name": file_name,
                            "type": attachment_type,
                            "file_size": file_size,
                            "cloudinary_url": cloudinary_url
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")
            
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
            
            # Process attachment using AttachmentProcessor
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
                
                # Mark task as completed
                if task_id:
                    TicketRequestQueue.mark_completed(task_id)
                    logger.info(f"✓ Task {task_id} marked as completed")
            except Exception as e:
                logger.warning(f"Failed to process attachment: {e}")
                if task_id:
                    TicketRequestQueue.mark_failed(task_id, str(e))
                    logger.error(f"✓ Task {task_id} marked as failed: {e}")
            
            return {
                "id": str(attachment.id),
                "ticket_id": ticket_id,
                "file_name": file_name,
                "type": attachment.type,
                "file_path": attachment.file_path,
                "mime_type": attachment.mime_type,
                "embeddings_created": embedding_count,
                "task_id": task_id,
                "created_at": attachment.created_at.isoformat()
            }
            
        except (NotFoundError, ValidationError):
            if task_id:
                TicketRequestQueue.mark_failed(task_id, str(e))
            db.rollback()
            raise
        except Exception as e:
            if task_id:
                TicketRequestQueue.mark_failed(task_id, str(e))
            db.rollback()
            logger.error(f"Failed to add attachment: {e}")
            raise ValidationError(f"Failed to add attachment: {str(e)}")
        finally:
            db.close()

    
    @staticmethod
    def delete_attachment(
        ticket_id: str,
        attachment_id: str,
        admin_id: Optional[str] = None
    ) -> bool:
        """Delete attachment from ticket - delegates to AttachmentProcessor"""
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            attachment_uuid = UUID(attachment_id)
            
            # Verify ticket exists
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise NotFoundError(f"Ticket {ticket_id} not found")
            
            # Get attachment
            attachment = db.query(Attachment).filter(
                Attachment.id == attachment_uuid,
                Attachment.ticket_id == ticket_uuid
            ).first()
            
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
            
            # Delete from database
            db.delete(attachment)
            db.add(deletion_event)
            db.commit()
            
            # Audit log
            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="attachment_deleted",
                        resource="attachment",
                        resource_id=str(attachment.id),
                        changes={"ticket_id": ticket_id}
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")
            
            logger.info(f"✓ Attachment deleted: {attachment_id}")
            
            # Deprecate embeddings using AttachmentProcessor
            try:
                AttachmentProcessor.deprecate_attachment(
                    attachment_id=attachment_id,
                    reason="attachment_deleted"
                )
                logger.info(f"✓ Deprecated embeddings for attachment {attachment_id}")
            except Exception as e:
                logger.warning(f"Failed to deprecate attachment embeddings: {e}")
            
            return True
            
        except (NotFoundError, ValidationError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete attachment: {e}")
            raise ValidationError(f"Failed to delete attachment: {str(e)}")
        finally:
            db.close()
    
    
    @staticmethod
    def add_root_cause_analysis(
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
        """
        Add or update Root Cause Analysis with task queue tracking.
        Processes RCA embeddings synchronously and updates task status.
        """
        db = SessionLocal()
        task_id = None
        
        try:
            logger.info(f"Adding/updating RCA for ticket {ticket_id}")
            
            # Verify ticket exists
            try:
                ticket_uuid = UUID(ticket_id)
                ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
                if not ticket:
                    logger.error(f"Ticket {ticket_id} not found")
                    raise NotFoundError("Ticket not found")
                logger.info(f"✓ Ticket found: {ticket.ticket_no}")
            except ValueError as e:
                logger.error(f"Invalid ticket UUID: {ticket_id}")
                raise ValidationError(f"Invalid ticket ID format: {str(e)}")
            
            # Validate root cause description
            if not root_cause_description or len(root_cause_description.strip()) < 10:
                raise ValidationError("Root cause description must be at least 10 characters")
            
            # Verify creator user exists, fallback to ticket raiser if not
            actual_creator_id = None
            try:
                user_uuid = UUID(created_by_user_id)
                user = db.query(User).filter(User.id == user_uuid).first()
                if user:
                    logger.info(f"✓ User found: {user.name}")
                    actual_creator_id = user_uuid
                else:
                    logger.warning(f"User {created_by_user_id} not found, using ticket raiser")
                    actual_creator_id = ticket.raised_by_user_id
            except (ValueError, Exception):
                logger.warning(f"Invalid user UUID, using ticket raiser")
                actual_creator_id = ticket.raised_by_user_id
            
            # Check if RCA already exists
            existing_rca = db.query(RootCauseAnalysis).filter(
                RootCauseAnalysis.ticket_id == ticket_uuid
            ).first()
            
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
                db.flush()
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
                db.add(rca)
                db.flush()
            
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
            db.add(rca_event)
            db.commit()
            logger.info(f"✓ RCA event committed")
            
            # Audit log
            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="rca_added" if not is_update else "rca_updated",
                        resource="rca",
                        resource_id=str(rca.id),
                        changes={
                            "ticket_id": ticket_id,
                            "root_cause": root_cause_description[:100],
                            "factors": len(contributing_factors or []),
                            "steps": len(resolution_steps or [])
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")
            
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
                
                # Mark task as completed
                if task_id:
                    TicketRequestQueue.mark_completed(task_id)
                    logger.info(f"✓ Task {task_id} marked as completed")
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
                "created_at": rca.created_at.isoformat(),
                "is_update": is_update
            }
                    
        except (ValidationError, NotFoundError):
            if task_id:
                TicketRequestQueue.mark_failed(task_id, str(e))
            db.rollback()
            raise
        except Exception as e:
            if task_id:
                TicketRequestQueue.mark_failed(task_id, str(e))
            db.rollback()
            logger.error(f"Unexpected error in add_root_cause_analysis: {e}")
            raise ValidationError(f"Failed to add RCA: {str(e)}")
        finally:
            db.close()
    
    
    @staticmethod
    def add_resolution_note(
        ticket_id: str,
        solution_description: str,
        created_by_user_id: str,
        steps_taken: Optional[List[str]] = None,
        resources_used: Optional[List[str]] = None,
        follow_up_notes: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add resolution note to ticket"""
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            
            # Verify ticket exists
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
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
                user = db.query(User).filter(User.id == user_uuid).first()
                if user:
                    actual_creator_id = user_uuid
                else:
                    actual_creator_id = ticket.raised_by_user_id
            except (ValueError, Exception):
                actual_creator_id = ticket.raised_by_user_id
            
            # Check if resolution note already exists
            existing_note = db.query(ResolutionNote).filter(
                ResolutionNote.ticket_id == ticket_uuid
            ).first()
            
            is_update = False
            if existing_note:
                existing_note.solution_description = solution_description.strip()
                existing_note.steps_taken = steps_taken or []
                existing_note.resources_used = resources_used or []
                existing_note.follow_up_notes = follow_up_notes
                note = existing_note
                is_update = True
                db.flush()
            else:
                note = ResolutionNote(
                    ticket_id=ticket_uuid,
                    solution_description=solution_description.strip(),
                    created_by_user_id=actual_creator_id,
                    steps_taken=steps_taken or [],
                    resources_used=resources_used or [],
                    follow_up_notes=follow_up_notes
                )
                db.add(note)
                db.flush()
            
            db.commit()
            logger.info(f"✓ Resolution note {'updated' if is_update else 'added'}")
            
            # Audit log
            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="resolution_added" if not is_update else "resolution_updated",
                        resource="resolution_note",
                        resource_id=str(note.id),
                        changes={
                            "ticket_id": ticket_id,
                            "solution": solution_description[:100]
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")
            
            return {
                "id": str(note.id),
                "ticket_id": ticket_id,
                "solution_description": note.solution_description,
                "steps_taken": note.steps_taken,
                "resources_used": note.resources_used,
                "follow_up_notes": note.follow_up_notes,
                "created_at": note.created_at.isoformat(),
                "is_update": is_update
            }
            
        except (ValidationError, NotFoundError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add resolution note: {e}")
            raise ValidationError(f"Failed to add resolution note: {str(e)}")
        finally:
            db.close()

    
    @staticmethod
    def delete_ticket(
        ticket_id: str,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Delete a ticket and all related data - delegates to services"""
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            
            # Verify ticket exists
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise NotFoundError(f"Ticket {ticket_id} not found")
            
            logger.info(f"Deleting ticket {ticket.ticket_no}...")
            
            # Deprecate all embeddings using EmbeddingManager
            try:
                EmbeddingManager.deprecate_ticket_embeddings(
                    ticket_id=ticket_id,
                    reason="ticket_deleted"
                )
                logger.info(f"✓ Deprecated ticket embeddings")
            except Exception as e:
                logger.warning(f"Failed to deprecate ticket embeddings: {e}")
            
            # Deprecate all attachment embeddings
            attachments = db.query(Attachment).filter(
                Attachment.ticket_id == ticket_uuid
            ).all()
            
            for attachment in attachments:
                try:
                    AttachmentProcessor.deprecate_attachment(
                        attachment_id=str(attachment.id),
                        reason="ticket_deleted"
                    )
                    logger.debug(f"✓ Deprecated embeddings for attachment {attachment.id}")
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
                    "deleted_at": datetime.utcnow().isoformat()
                }
            )
            db.add(deletion_event)
            db.flush()
            
            # Delete resolution note if exists
            if ticket.resolution_note:
                db.delete(ticket.resolution_note)
                logger.debug(f"✓ Deleted resolution note")
            
            # Delete RCA if exists
            if ticket.root_cause_analysis:
                db.delete(ticket.root_cause_analysis)
                logger.debug(f"✓ Deleted RCA")
            
            # Delete all attachments
            for attachment in attachments:
                db.delete(attachment)
            if attachments:
                logger.debug(f"✓ Deleted {len(attachments)} attachments")
            
            # Delete all events
            events = db.query(TicketEvent).filter(TicketEvent.ticket_id == ticket_uuid).all()
            for event in events:
                db.delete(event)
            
            # Delete the ticket
            db.delete(ticket)
            db.commit()
            
            logger.info(f"✓ Ticket deleted: {ticket.ticket_no}")
            
            # Audit log
            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="ticket_deleted",
                        resource="ticket",
                        resource_id=ticket_id,
                        changes={
                            "ticket_no": ticket.ticket_no,
                            "subject": ticket.subject
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")
            
            return {
                "id": ticket_id,
                "ticket_no": ticket.ticket_no,
                "deleted": True,
                "deleted_at": datetime.utcnow().isoformat()
            }
            
        except NotFoundError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete ticket: {e}")
            raise ValidationError(f"Failed to delete ticket: {str(e)}")
        finally:
            db.close()

    @staticmethod
    def update_ticket(
        ticket_id: str,
        subject: Optional[str] = None,
        summary: Optional[str] = None,
        detailed_description: Optional[str] = None,
        category: Optional[str] = None,
        level: Optional[str] = None,
        created_at: Optional[datetime] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update ticket details"""
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            
            # Verify ticket exists
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            # Validate inputs
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
            ticket.updated_at = datetime.utcnow()
            db.flush()
            
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
                changes["created_at"] = created_at.isoformat()
            
            ticket_event = TicketEvent(
                ticket_id=ticket_uuid,
                event_type="ticket_updated",
                actor_user_id=ticket.raised_by_user_id,
                payload={
                    "changes": changes,
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
            db.add(ticket_event)
            db.commit()
            
            logger.info(f"✓ Ticket updated: {ticket.ticket_no}")
            
            # Audit log
            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="ticket_updated",
                        resource="ticket",
                        resource_id=ticket_id,
                        changes=changes
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")
            
            from .ticket_service import TicketService
            return TicketService._format_ticket(ticket)
            
        except (ValidationError, NotFoundError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update ticket: {e}")
            raise ValidationError(f"Failed to update ticket: {str(e)}")
        finally:
            db.close()