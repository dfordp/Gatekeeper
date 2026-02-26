"""
Ticket Creation Service - Atomic ticket operations with sequential numbering

Handles ticket creation, attachments, RCA, resolution notes, and deletion.
All operations are atomic with proper transaction isolation.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID
from sqlalchemy import text

from core.database import (
    SessionLocal, Ticket, TicketEvent, RootCauseAnalysis, ResolutionNote,
    Attachment, AdminAuditLog, Company, User, SimilarIssues
)
from utils.datetime_utils import to_iso_date
from .embedding_manager import EmbeddingManager
from .attachment_processor import AttachmentProcessor
from .ticket_request_queue import TicketRequestQueue, TaskType
from utils.exceptions import ValidationError, NotFoundError, ConflictError
from core.logger import get_logger

logger = get_logger(__name__)


class TicketCreationService:
    """Service for ticket creation and management with atomic operations."""

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
        created_at: Optional[date] = None,
        closed_at: Optional[date] = None,
        created_by_admin_id: Optional[str] = None,
        ticket_no: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new ticket with atomic sequential ticket number generation.
        Ticket number is generated inside this transaction to prevent race conditions.
        """
        db = SessionLocal()
        task_id = None

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
            raised_by_user = db.query(User).filter(User.id == UUID(raised_by_user_id)).first()
            if not raised_by_user:
                raise NotFoundError("User not found")

            # Verify assigned engineer if provided
            engineer = None
            if assigned_engineer_id:
                engineer = db.query(User).filter(User.id == UUID(assigned_engineer_id)).first()
                if not engineer:
                    raise NotFoundError("Engineer not found")

            # Validate level if provided
            valid_levels = ["level-1", "level-2", "level-3"]
            if level and level not in valid_levels:
                raise ValidationError(f"Invalid level. Must be one of: {', '.join(valid_levels)}")

            # Generate ticket number atomically INSIDE this transaction
            # SELECT FOR UPDATE locks the row and prevents concurrent duplicate generations
            if not ticket_no:
                result = db.execute(
                    text(
                        "SELECT ticket_no FROM ticket "
                        "ORDER BY CAST(SPLIT_PART(ticket_no, '-', 2) AS INTEGER) DESC "
                        "LIMIT 1 FOR UPDATE"
                    )
                ).fetchone()

                if not result:
                    ticket_no = "TKT-000001"
                else:
                    try:
                        num = int(result[0].split('-')[-1])
                        ticket_no = f"TKT-{str(num + 1).zfill(6)}"
                    except (ValueError, IndexError):
                        logger.error(f"Invalid ticket_no format in DB: {result[0]}")
                        raise ValidationError("Invalid ticket number format in database")

                logger.info(f"Generated sequential ticket_no: {ticket_no}")
            else:
                # Validate provided ticket_no format
                if ticket_no.isdigit():
                    ticket_no = f"TKT-{ticket_no.zfill(6)}"
                ticket_no = ticket_no.strip()

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

            db.add(ticket)
            db.flush()

            # Log creation event
            event = TicketEvent(
                ticket_id=ticket.id,
                event_type="ticket_created",
                actor_user_id=UUID(raised_by_user_id),
                payload={
                    "ticket_no": ticket_no,
                    "subject": subject.strip(),
                    "category": category,
                    "level": level,
                    "assigned_to": engineer.name if engineer else None
                }
            )
            db.add(event)
            db.commit()

            logger.info(f"✓ Ticket created: {ticket_no}")

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
                            "subject": subject.strip(),
                            "company_id": company_id,
                            "status": initial_status
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")

            # Queue embedding task
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

            # Create embeddings synchronously
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
                if task_id:
                    TicketRequestQueue.mark_completed(task_id)
            except Exception as e:
                logger.warning(f"Failed to create embeddings: {e}")
                if task_id:
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
            db.rollback()
            if task_id:
                TicketRequestQueue.mark_failed(task_id, str(type(e).__name__))
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Unexpected error creating ticket: {e}")
            if task_id:
                TicketRequestQueue.mark_failed(task_id, str(e))
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
        """Add attachment to ticket with embedding processing."""
        db = SessionLocal()
        task_id = None

        try:
            ticket_uuid = UUID(ticket_id)
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

            # Log event
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
                    "mime_type": mime_type
                }
            )
            db.add(attachment_event)
            db.commit()

            logger.info(f"✓ Attachment added: {file_name}")

            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="attachment_added",
                        resource="attachment",
                        resource_id=str(attachment.id),
                        changes={"ticket_id": ticket_id, "file_name": file_name, "size": file_size}
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")

            # Queue embedding task
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
                logger.info(f"✓ Task queued: {task_id}")
                TicketRequestQueue.mark_processing(task_id)
            except Exception as e:
                logger.warning(f"Failed to queue task: {e}")

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
                logger.info(f"✓ Processed with {embedding_count} embeddings")
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
                "mime_type": mime_type,
                "embeddings_created": embedding_count,
                "task_id": task_id,
                "created_at": to_iso_date(attachment.created_at)
            }

        except (NotFoundError, ValidationError):
            db.rollback()
            if task_id:
                TicketRequestQueue.mark_failed(task_id, str(type(e).__name__))
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add attachment: {e}")
            if task_id:
                TicketRequestQueue.mark_failed(task_id, str(e))
            raise ValidationError(f"Failed to add attachment: {str(e)}")
        finally:
            db.close()

    @staticmethod
    def delete_attachment(
        ticket_id: str,
        attachment_id: str,
        admin_id: Optional[str] = None
    ) -> bool:
        """Delete attachment from ticket."""
        db = SessionLocal()

        try:
            ticket_uuid = UUID(ticket_id)
            attachment_uuid = UUID(attachment_id)

            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise NotFoundError(f"Ticket {ticket_id} not found")

            attachment = db.query(Attachment).filter(
                Attachment.id == attachment_uuid,
                Attachment.ticket_id == ticket_uuid
            ).first()
            if not attachment:
                raise NotFoundError(f"Attachment {attachment_id} not found")

            logger.info(f"Deleting attachment {attachment_id}")

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
                        logger.info(f"✓ Deleted from Cloudinary")
                except Exception as e:
                    logger.warning(f"Failed to delete from Cloudinary: {e}")

            # Deprecate embeddings
            try:
                AttachmentProcessor.deprecate_attachment(
                    attachment_id=attachment_id,
                    reason="attachment_deleted"
                )
                logger.info(f"✓ Deprecated embeddings")
            except Exception as e:
                logger.warning(f"Failed to deprecate embeddings: {e}")

            # Log deletion event
            deletion_event = TicketEvent(
                ticket_id=ticket_uuid,
                event_type="attachment_deleted",
                actor_user_id=ticket.raised_by_user_id,
                payload={"attachment_id": str(attachment.id), "file_name": attachment.file_path.split('/')[-1]}
            )

            db.delete(attachment)
            db.add(deletion_event)
            db.commit()

            logger.info(f"✓ Attachment deleted")

            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="attachment_deleted",
                        resource="attachment",
                        resource_id=attachment_id,
                        changes={"ticket_id": ticket_id}
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")

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
        related_ticket_ids: Optional[List[str]] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add or update Root Cause Analysis."""
        db = SessionLocal()
        task_id = None

        try:
            ticket_uuid = UUID(ticket_id)
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise NotFoundError("Ticket not found")

            if not root_cause_description or len(root_cause_description.strip()) < 10:
                raise ValidationError("Root cause description must be at least 10 characters")

            logger.info(f"Adding/updating RCA for ticket {ticket.ticket_no}")

            # Get or create user reference
            actual_creator_id = ticket.raised_by_user_id
            try:
                user = db.query(User).filter(User.id == UUID(created_by_user_id)).first()
                if user:
                    actual_creator_id = UUID(created_by_user_id)
            except (ValueError, Exception):
                pass

            # Check if RCA exists
            existing_rca = db.query(RootCauseAnalysis).filter(
                RootCauseAnalysis.ticket_id == ticket_uuid
            ).first()

            is_update = False
            if existing_rca:
                existing_rca.root_cause_description = root_cause_description.strip()
                existing_rca.contributing_factors = contributing_factors or []
                existing_rca.prevention_measures = prevention_measures.strip() if prevention_measures else None
                existing_rca.resolution_steps = resolution_steps or []
                existing_rca.related_ticket_ids = related_ticket_ids or []
                rca = existing_rca
                is_update = True
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

            # Log event
            rca_event = TicketEvent(
                ticket_id=ticket_uuid,
                event_type="rca_updated" if is_update else "rca_added",
                actor_user_id=actual_creator_id,
                payload={
                    "rca_id": str(rca.id),
                    "root_cause": root_cause_description.strip()[:100],
                    "factors_count": len(contributing_factors or [])
                }
            )
            db.add(rca_event)
            db.commit()

            logger.info(f"✓ RCA {'updated' if is_update else 'added'}")

            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="rca_added" if not is_update else "rca_updated",
                        resource="rca",
                        resource_id=str(rca.id),
                        changes={"ticket_id": ticket_id, "root_cause": root_cause_description[:100]}
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")

            # Queue embedding task
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
                logger.info(f"✓ Task queued: {task_id}")
                TicketRequestQueue.mark_processing(task_id)
            except Exception as e:
                logger.warning(f"Failed to queue task: {e}")

            # Create embeddings
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
                logger.warning(f"Failed to create RCA embeddings: {e}")
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
                "task_id": task_id,
                "created_at": to_iso_date(rca.created_at),
                "is_update": is_update
            }

        except (ValidationError, NotFoundError):
            db.rollback()
            if task_id:
                TicketRequestQueue.mark_failed(task_id, str(type(e).__name__))
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Unexpected error in add_root_cause_analysis: {e}")
            if task_id:
                TicketRequestQueue.mark_failed(task_id, str(e))
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
        """Add or update resolution note."""
        db = SessionLocal()

        try:
            ticket_uuid = UUID(ticket_id)
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise NotFoundError("Ticket not found")

            if not solution_description or len(solution_description.strip()) < 10:
                raise ValidationError("Solution description must be at least 10 characters")

            logger.info(f"Adding/updating resolution note for {ticket.ticket_no}")

            # Get or create user reference
            actual_creator_id = ticket.raised_by_user_id
            try:
                user = db.query(User).filter(User.id == UUID(created_by_user_id)).first()
                if user:
                    actual_creator_id = UUID(created_by_user_id)
            except (ValueError, Exception):
                pass

            # Check if note exists
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

            # Log event
            note_event = TicketEvent(
                ticket_id=ticket_uuid,
                event_type="resolution_updated" if is_update else "resolution_added",
                actor_user_id=actual_creator_id,
                payload={"solution": solution_description.strip()[:100]}
            )
            db.add(note_event)
            db.commit()

            logger.info(f"✓ Resolution note {'updated' if is_update else 'added'}")

            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="resolution_added" if not is_update else "resolution_updated",
                        resource="resolution_note",
                        resource_id=str(note.id),
                        changes={"ticket_id": ticket_id, "solution": solution_description[:100]}
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")

            # Create embeddings
            try:
                EmbeddingManager.add_resolution_embedding(
                    ticket_id=ticket_id,
                    company_id=str(ticket.company_id),
                    solution_description=solution_description.strip(),
                    steps_taken=steps_taken,
                    resources_used=resources_used,
                    follow_up_notes=follow_up_notes
                )
                logger.info(f"✓ Resolution embeddings created/updated")
            except Exception as e:
                logger.warning(f"Failed to create resolution embeddings: {e}")

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
        """Delete a ticket and all related data."""
        db = SessionLocal()

        try:
            ticket_uuid = UUID(ticket_id)
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise NotFoundError(f"Ticket {ticket_id} not found")

            logger.info(f"Deleting ticket {ticket.ticket_no}...")

            # Deprecate embeddings
            try:
                EmbeddingManager.deprecate_resolution_embeddings(ticket_id=ticket_id, reason="ticket_deleted")
                EmbeddingManager.deprecate_ticket_embeddings(ticket_id=ticket_id, reason="ticket_deleted")
                logger.info(f"✓ Deprecated embeddings")
            except Exception as e:
                logger.warning(f"Failed to deprecate embeddings: {e}")

            # Deprecate attachment embeddings
            attachments = db.query(Attachment).filter(Attachment.ticket_id == ticket_uuid).all()
            for attachment in attachments:
                try:
                    AttachmentProcessor.deprecate_attachment(
                        attachment_id=str(attachment.id),
                        reason="ticket_deleted"
                    )
                except Exception as e:
                    logger.warning(f"Failed to deprecate attachment {attachment.id}: {e}")

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
            db.add(deletion_event)
            db.flush()

            # Delete all related records
            if ticket.resolution_note:
                db.delete(ticket.resolution_note)
            if ticket.root_cause_analysis:
                db.delete(ticket.root_cause_analysis)
            for attachment in attachments:
                db.delete(attachment)

            # Delete similar issues
            similar_issues = db.query(SimilarIssues).filter(
                (SimilarIssues.newer_ticket_id == ticket_uuid) | (SimilarIssues.older_ticket_id == ticket_uuid)
            ).all()
            for similar in similar_issues:
                db.delete(similar)
            if similar_issues:
                logger.info(f"✓ Deleted {len(similar_issues)} similar issue records")

            # Delete all events
            events = db.query(TicketEvent).filter(TicketEvent.ticket_id == ticket_uuid).all()
            for event in events:
                db.delete(event)

            # Delete ticket
            db.delete(ticket)
            db.commit()

            logger.info(f"✓ Ticket deleted: {ticket.ticket_no}")

            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="ticket_deleted",
                        resource="ticket",
                        resource_id=ticket_id,
                        changes={"ticket_no": ticket.ticket_no, "subject": ticket.subject}
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")

            return {
                "id": ticket_id,
                "ticket_no": ticket.ticket_no,
                "deleted": True,
                "deleted_at": to_iso_date(date.today())
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
        status: Optional[str] = None,
        assigned_engineer_id: Optional[str] = None,
        created_at: Optional[date] = None,
        closed_at: Optional[date] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update ticket details."""
        db = SessionLocal()

        try:
            ticket_uuid = UUID(ticket_id)
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise NotFoundError("Ticket not found")

            changes = {}

            if subject is not None:
                if len(subject.strip()) < 3:
                    raise ValidationError("Subject must be at least 3 characters")
                ticket.subject = subject.strip()
                changes["subject"] = subject.strip()

            if summary is not None:
                ticket.summary = summary.strip() if summary.strip() else None
                changes["summary"] = ticket.summary

            if detailed_description is not None:
                if len(detailed_description.strip()) < 10:
                    raise ValidationError("Description must be at least 10 characters")
                ticket.detailed_description = detailed_description.strip()
                changes["detailed_description"] = detailed_description.strip()

            if category is not None:
                ticket.category = category.strip() if category.strip() else None
                changes["category"] = ticket.category

            if level is not None:
                valid_levels = ["level-1", "level-2", "level-3"]
                if level not in valid_levels:
                    raise ValidationError(f"Invalid level. Must be one of: {', '.join(valid_levels)}")
                ticket.level = level
                changes["level"] = level

            if status is not None:
                valid_statuses = ["open", "in_progress", "resolved", "closed", "reopened"]
                if status not in valid_statuses:
                    raise ValidationError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
                ticket.status = status
                changes["status"] = status

            if assigned_engineer_id is not None:
                engineer = db.query(User).filter(User.id == UUID(assigned_engineer_id)).first()
                if not engineer:
                    raise NotFoundError("Engineer not found")
                ticket.assigned_engineer_id = UUID(assigned_engineer_id)
                changes["assigned_engineer_id"] = assigned_engineer_id

            if created_at is not None:
                ticket.created_at = created_at
                changes["created_at"] = to_iso_date(created_at)

            if closed_at is not None:
                ticket.closed_at = closed_at
                changes["closed_at"] = to_iso_date(closed_at) if closed_at else None

            ticket.updated_at = date.today()
            db.flush()

            # Log update event
            update_event = TicketEvent(
                ticket_id=ticket_uuid,
                event_type="ticket_updated",
                actor_user_id=ticket.raised_by_user_id,
                payload={
                    "changes": changes,
                    "updated_at": to_iso_date(date.today())
                }
            )
            db.add(update_event)
            db.commit()

            logger.info(f"✓ Ticket updated: {ticket.ticket_no}")

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
                "created_at": to_iso_date(ticket.created_at),
                "updated_at": to_iso_date(ticket.updated_at),
                "closed_at": to_iso_date(ticket.closed_at) if ticket.closed_at else None
            }

        except (ValidationError, NotFoundError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update ticket: {e}")
            raise ValidationError(f"Failed to update ticket: {str(e)}")
        finally:
            db.close()