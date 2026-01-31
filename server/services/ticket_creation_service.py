# server/services/ticket_creation_service.py
"""Comprehensive ticket creation service with attachments and RCA support"""
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime
import uuid as uuid_lib

from core.database import (
    SessionLocal, Ticket, TicketEvent, Attachment, AdminAuditLog, 
    RootCauseAnalysis, ResolutionNote, User, Company
)
from utils.exceptions import ValidationError, NotFoundError, ConflictError
from core.logger import get_logger

logger = get_logger(__name__)


class TicketCreationService:
    """Service for creating and managing tickets"""

    @staticmethod
    def get_next_ticket_number() -> str:
        """Get next sequential ticket number based on largest in DB"""
        db = SessionLocal()
        try:
            latest_ticket = db.query(Ticket).order_by(Ticket.ticket_no.desc()).first()
            
            if not latest_ticket:
                return "TKT-000001"
            
            try:
                last_num = int(latest_ticket.ticket_no.split('-')[1])
                next_num = last_num + 1
                return f"TKT-{str(next_num).zfill(6)}"
            except (IndexError, ValueError):
                return f"TKT-{uuid_lib.uuid4().hex[:8].upper()}"
        finally:
            db.close()
        
    @staticmethod
    def generate_ticket_number() -> str:
        """Generate unique ticket number"""
        return f"TKT-{uuid_lib.uuid4().hex[:8].upper()}"
    
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
        Create a new ticket with full validation.
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
            
            # Use provided status or default to "open"
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
            logger.error(f"Failed to create ticket: {e}")
            raise ValidationError(f"Failed to create ticket: {str(e)}")
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
        actor_user_id: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update ticket details and log as event"""
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            changes = {}
            
            if subject and len(subject.strip()) >= 3:
                if subject.strip() != ticket.subject:
                    changes["subject"] = {"from": ticket.subject, "to": subject.strip()}
                    ticket.subject = subject.strip()
            
            if summary:
                if summary.strip() != (ticket.summary or ""):
                    changes["summary"] = {"from": ticket.summary, "to": summary.strip()}
                    ticket.summary = summary.strip()
            
            if detailed_description and len(detailed_description.strip()) >= 10:
                if detailed_description.strip() != ticket.detailed_description:
                    changes["detailed_description"] = {"from": ticket.detailed_description[:100], "to": detailed_description[:100]}
                    ticket.detailed_description = detailed_description.strip()
            
            if category:
                if category.strip() != (ticket.category or ""):
                    changes["category"] = {"from": ticket.category, "to": category.strip()}
                    ticket.category = category.strip()
            
            if level:
                valid_levels = ["level-1", "level-2", "level-3"]
                if level not in valid_levels:
                    raise ValidationError(f"Invalid level. Must be one of: {', '.join(valid_levels)}")
                if level != ticket.level:
                    changes["level"] = {"from": ticket.level, "to": level}
                    ticket.level = level
            
            if not changes:
                raise ValidationError("No fields to update")
            
            ticket.updated_at = datetime.utcnow()
            db.flush()
            
            # Log ticket update event
            actor_uuid = UUID(actor_user_id) if actor_user_id else ticket.raised_by_user_id
            event = TicketEvent(
                ticket_id=ticket.id,
                event_type="ticket_updated",
                actor_user_id=actor_uuid,
                payload={
                    "changes": changes,
                    "updated_at": ticket.updated_at.isoformat()
                }
            )
            db.add(event)
            db.commit()
            
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
            
            logger.info(f"✓ Ticket {ticket.ticket_no} updated")
            
            return {
                "id": str(ticket.id),
                "ticket_no": ticket.ticket_no,
                "subject": ticket.subject,
                "summary": ticket.summary,
                "detailed_description": ticket.detailed_description,
                "category": ticket.category,
                "level": ticket.level,
                "updated_at": ticket.updated_at.isoformat()
            }
            
        except (NotFoundError, ValidationError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update ticket: {e}")
            raise ValidationError(f"Failed to update ticket: {str(e)}")
        finally:
            db.close()
    
    @staticmethod
    def add_attachment(
        ticket_id: str,
        file_path: str,
        file_name: str,
        attachment_type: str,
        mime_type: Optional[str] = None,
        file_size: Optional[int] = None,
        cloudinary_url: Optional[str] = None,
        created_by_user_id: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add attachment to ticket and log as event"""
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            valid_types = ["image", "document", "log", "code", "other"]
            if attachment_type not in valid_types:
                raise ValidationError(f"Invalid attachment type. Must be one of: {', '.join(valid_types)}")
            
            # Create attachment
            attachment = Attachment(
                ticket_id=UUID(ticket_id),
                type=attachment_type,
                file_path=file_path,
                mime_type=mime_type
            )
            
            db.add(attachment)
            db.flush()
            
            # Update ticket's attachment_ids
            if not ticket.attachment_ids:
                ticket.attachment_ids = []
            ticket.attachment_ids.append(str(attachment.id))
            ticket.updated_at = datetime.utcnow()
            
            # Log attachment event (separate event)
            actor_uuid = UUID(created_by_user_id) if created_by_user_id else ticket.raised_by_user_id
            attachment_event = TicketEvent(
                ticket_id=UUID(ticket_id),
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
            
            return {
                "id": str(attachment.id),
                "ticket_id": ticket_id,
                "file_name": file_name,
                "type": attachment.type,
                "file_path": attachment.file_path,
                "mime_type": attachment.mime_type,
                "created_at": attachment.created_at.isoformat()
            }
            
        except (ValidationError, NotFoundError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add attachment: {e}")
            raise ValidationError(f"Failed to add attachment: {str(e)}")
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
        ticket_closed_at: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add or update Root Cause Analysis and log as separate event"""
        db = SessionLocal()
        try:
            logger.info(f"Adding/updating RCA for ticket {ticket_id}, user {created_by_user_id}")
            
            # Verify ticket exists
            try:
                ticket_uuid = UUID(ticket_id)
                ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
                if not ticket:
                    logger.error(f"Ticket {ticket_id} not found")
                    raise NotFoundError("Ticket not found")
                logger.info(f"✓ Ticket found: {ticket.ticket_no}")
            except ValueError as e:
                logger.error(f"Invalid ticket UUID: {ticket_id}, error: {e}")
                raise ValidationError(f"Invalid ticket ID format: {str(e)}")
            
            # Validate root cause description FIRST
            if not root_cause_description or len(root_cause_description.strip()) < 10:
                logger.warning(f"Root cause description too short: '{root_cause_description}'")
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
                    logger.warning(f"User {created_by_user_id} not found, using ticket raiser instead")
                    actual_creator_id = ticket.raised_by_user_id
            except ValueError as e:
                logger.warning(f"Invalid user UUID format: {created_by_user_id}, using ticket raiser")
                actual_creator_id = ticket.raised_by_user_id
            except Exception as e:
                logger.warning(f"Failed to verify user, using ticket raiser: {e}")
                actual_creator_id = ticket.raised_by_user_id
            
            # Check if RCA already exists
            existing_rca = db.query(RootCauseAnalysis).filter(
                RootCauseAnalysis.ticket_id == ticket_uuid
            ).first()
            
            is_update = False
            if existing_rca:
                # Update existing RCA
                logger.info(f"RCA already exists for {ticket.ticket_no}, updating it")
                existing_rca.root_cause_description = root_cause_description.strip()
                existing_rca.contributing_factors = contributing_factors or []
                existing_rca.prevention_measures = prevention_measures.strip() if prevention_measures else None
                existing_rca.resolution_steps = resolution_steps or []
                existing_rca.related_ticket_ids = related_ticket_ids or []
                rca = existing_rca
                is_update = True
                db.flush()
                logger.info(f"✓ RCA updated: {rca.id}")
            else:
                # Create new RCA
                rca = RootCauseAnalysis(
                    ticket_id=ticket_uuid,
                    root_cause_description=root_cause_description.strip(),
                    created_by_user_id=actual_creator_id,
                    contributing_factors=contributing_factors or [],
                    prevention_measures=prevention_measures.strip() if prevention_measures else None,
                    resolution_steps=resolution_steps or [],
                    related_ticket_ids=related_ticket_ids or []
                )
                logger.info(f"RCA object created with creator_id={actual_creator_id}")
                db.add(rca)
                db.flush()
                logger.info(f"✓ RCA created: {rca.id}")
            
            # Log RCA event (separate event)
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
            logger.info(f"✓ RCA event committed successfully")
            
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
            
            return {
                "id": str(rca.id),
                "ticket_id": ticket_id,
                "root_cause_description": rca.root_cause_description,
                "contributing_factors": rca.contributing_factors,
                "prevention_measures": rca.prevention_measures,
                "resolution_steps": rca.resolution_steps,
                "related_ticket_ids": rca.related_ticket_ids,
                "ticket_closed_at": ticket_closed_at,
                "created_at": rca.created_at.isoformat(),
                "is_update": is_update
            }
                    
        except (ValidationError, NotFoundError):
            db.rollback()
            logger.info(f"Caught expected exception, rolling back")
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Unexpected error adding RCA: {e}", exc_info=True)
            raise ValidationError(f"Failed to add RCA: {str(e)}")
        finally:
            db.close()
    
    @staticmethod
    def delete_attachment(ticket_id: str, attachment_id: str, actor_user_id: Optional[str] = None, admin_id: Optional[str] = None) -> Dict[str, Any]:
        """Delete attachment from ticket and log as event"""
        db = SessionLocal()
        try:
            # Validate UUIDs
            try:
                ticket_uuid = UUID(ticket_id)
                attachment_uuid = UUID(attachment_id)
            except ValueError:
                raise NotFoundError("Invalid ticket or attachment ID format")
            
            # Verify ticket exists
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            # Get attachment - ensure it belongs to the ticket
            attachment = db.query(Attachment).filter(
                Attachment.id == attachment_uuid,
                Attachment.ticket_id == ticket_uuid
            ).first()
            
            if not attachment:
                raise NotFoundError("Attachment not found or does not belong to this ticket")
            
            file_name = None
            
            # Delete from Cloudinary if it's a Cloudinary URL
            if attachment.file_path and attachment.file_path.startswith('http'):
                try:
                    from urllib.parse import urlparse
                    path_parts = urlparse(attachment.file_path).path.split('/')
                    if 'upload' in path_parts:
                        upload_idx = path_parts.index('upload')
                        public_id_parts = path_parts[upload_idx + 2:]
                        public_id = '/'.join(public_id_parts).rsplit('.', 1)[0]
                        
                        import cloudinary
                        cloudinary.uploader.destroy(public_id, resource_type="auto")
                        logger.info(f"✓ Cloudinary asset deleted: {public_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete from Cloudinary: {e}")
            
            # Delete from local storage if it's a local file
            elif attachment.file_path:
                import os
                try:
                    if os.path.exists(attachment.file_path):
                        os.remove(attachment.file_path)
                        logger.info(f"✓ Local file deleted: {attachment.file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete local file: {e}")
            
            # Remove from attachment_ids list if present
            if ticket.attachment_ids and str(attachment.id) in ticket.attachment_ids:
                ticket.attachment_ids.remove(str(attachment.id))
            
            ticket.updated_at = datetime.utcnow()
            
            # Log attachment deletion event
            actor_uuid = UUID(actor_user_id) if actor_user_id else ticket.raised_by_user_id
            deletion_event = TicketEvent(
                ticket_id=ticket_uuid,
                event_type="attachment_deleted",
                actor_user_id=actor_uuid,
                payload={
                    "attachment_id": str(attachment.id),
                    "file_name": attachment.file_path.split('/')[-1] if attachment.file_path else "unknown"
                }
            )
            db.add(deletion_event)
            
            # Delete attachment from database
            db.delete(attachment)
            db.commit()
            
            logger.info(f"✓ Attachment deleted: {attachment.id}")
            
            return {
                "id": str(attachment.id),
                "ticket_id": ticket_id,
                "message": "Attachment deleted successfully"
            }
            
        except NotFoundError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete attachment: {e}")
            raise ValidationError(f"Failed to delete attachment: {str(e)}")
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
        """Add Resolution Note to ticket when closing."""
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            # Check if resolution note already exists
            existing_note = db.query(ResolutionNote).filter(
                ResolutionNote.ticket_id == UUID(ticket_id)
            ).first()
            if existing_note:
                raise ConflictError(f"Resolution note already exists for ticket {ticket.ticket_no}")
            
            if not solution_description or len(solution_description.strip()) < 10:
                raise ValidationError("Solution description must be at least 10 characters")
            
            # Verify user exists
            user = db.query(User).filter(User.id == UUID(created_by_user_id)).first()
            if not user:
                raise NotFoundError("User not found")
            
            # Create resolution note
            note = ResolutionNote(
                ticket_id=UUID(ticket_id),
                solution_description=solution_description.strip(),
                created_by_user_id=UUID(created_by_user_id),
                steps_taken=steps_taken or [],
                resources_used=resources_used or [],
                follow_up_notes=follow_up_notes.strip() if follow_up_notes else None
            )
            
            db.add(note)
            db.flush()
            
            # Log resolution event
            event = TicketEvent(
                ticket_id=UUID(ticket_id),
                event_type="resolution_note_added",
                actor_user_id=UUID(created_by_user_id),
                payload={
                    "note_id": str(note.id),
                    "steps_count": len(steps_taken or []),
                    "resources_count": len(resources_used or [])
                }
            )
            db.add(event)
            db.commit()
            
            # Audit log
            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="resolution_note_added",
                        resource="resolution_note",
                        resource_id=str(note.id),
                        changes={
                            "ticket_id": ticket_id,
                            "solution": solution_description[:100],
                            "steps": len(steps_taken or [])
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")
            
            logger.info(f"✓ Resolution note added to ticket {ticket.ticket_no}")
            
            return {
                "id": str(note.id),
                "ticket_id": ticket_id,
                "solution_description": note.solution_description,
                "steps_taken": note.steps_taken,
                "resources_used": note.resources_used,
                "follow_up_notes": note.follow_up_notes,
                "created_at": note.created_at.isoformat()
            }
            
        except (ValidationError, NotFoundError, ConflictError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add resolution note: {e}")
            raise ValidationError(f"Failed to add resolution note: {str(e)}")
        finally:
            db.close()
    
    @staticmethod
    def delete_ticket(ticket_id: str, admin_id: str) -> Dict[str, Any]:
        """Delete a ticket"""
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            ticket_no = ticket.ticket_no
            
            # Delete associated events, attachments, RCA, resolution notes
            db.query(TicketEvent).filter(TicketEvent.ticket_id == UUID(ticket_id)).delete()
            db.query(Attachment).filter(Attachment.ticket_id == UUID(ticket_id)).delete()
            db.query(RootCauseAnalysis).filter(RootCauseAnalysis.ticket_id == UUID(ticket_id)).delete()
            db.query(ResolutionNote).filter(ResolutionNote.ticket_id == UUID(ticket_id)).delete()
            
            # Delete ticket
            db.delete(ticket)
            db.commit()
            
            # Audit log
            if admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(admin_id),
                        action="ticket_deleted",
                        resource="ticket",
                        resource_id=ticket_id,
                        changes={"ticket_no": ticket_no}
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")
            
            logger.info(f"✓ Ticket deleted: {ticket_no}")
            
            return {
                "id": ticket_id,
                "ticket_no": ticket_no,
                "message": "Ticket deleted successfully"
            }
            
        except (NotFoundError, ValidationError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete ticket: {e}")
            raise ValidationError(f"Failed to delete ticket: {str(e)}")
        finally:
            db.close()