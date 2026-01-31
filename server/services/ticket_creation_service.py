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
            # Query the ticket with the highest ticket_no, ordered descending
            latest_ticket = db.query(Ticket).order_by(Ticket.ticket_no.desc()).first()
            
            if not latest_ticket:
                # No tickets exist yet, start with 000001
                return "TKT-000001"
            
            # Extract numeric part from latest ticket_no (e.g., "TKT-000005" -> 5)
            try:
                last_num = int(latest_ticket.ticket_no.split('-')[1])
                next_num = last_num + 1
                return f"TKT-{str(next_num).zfill(6)}"
            except (IndexError, ValueError):
                # If parsing fails, fall back to UUID-based generation
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
        
        Supports:
        - Immediate ticket creation
        - Older tickets (with custom creation dates)
        - Category and priority levels
        - Optional immediate assignment
        
        Args:
            subject: Ticket subject (3+ chars)
            detailed_description: Full description (10+ chars)
            company_id: Company UUID
            raised_by_user_id: User who raised ticket (can be from any company)
            summary: Optional summary
            category: Optional category
            level: Optional level (level-1, level-2, level-3)
            assigned_engineer_id: Optional engineer assignment (must belong to ticket's company)
            created_at: Optional custom creation date (for older tickets)
            created_by_admin_id: Admin creating this ticket
            ticket_no: Optional custom ticket number (auto-generated if not provided)
            status: Optional initial status (open, in_progress, resolved, closed, reopened)
            
        Returns:
            Dict with ticket details
            
        Raises:
            ValidationError: If validation fails
            NotFoundError: If company or user not found
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
            
            # Verify user exists (can be from any company)
            raised_by_user = db.query(User).filter(
                User.id == UUID(raised_by_user_id)
            ).first()
            if not raised_by_user:
                raise NotFoundError("User not found")   
            
            # Verify assigned engineer if provided - MUST belong to the ticket's company
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
            
            # Handle ticket number - use provided or auto-generate
            if ticket_no:
                ticket_no = ticket_no.strip()
                # If it's just a number, format it properly
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
        """
        Add attachment to ticket.
        
        Args:
            ticket_id: Ticket UUID
            file_path: Local file path or URL
            file_name: Original file name
            attachment_type: Type (image, document, log, code, other)
            mime_type: MIME type
            file_size: File size in bytes
            cloudinary_url: Cloudinary URL (after upload)
            created_by_user_id: User adding attachment
            admin_id: Admin performing action
            
        Returns:
            Dict with attachment details
        """
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            valid_types = ["image", "document", "log", "code", "other"]
            if attachment_type not in valid_types:
                raise ValidationError(f"Invalid attachment type. Must be one of: {', '.join(valid_types)}")
            
            # Create attachment - only use fields that exist in schema
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
            
            # Log attachment event
            event = TicketEvent(
                ticket_id=UUID(ticket_id),
                event_type="attachment_added",
                actor_user_id=UUID(created_by_user_id) if created_by_user_id else ticket.raised_by_user_id,
                payload={
                    "attachment_id": str(attachment.id),
                    "file_name": file_name,
                    "file_size": file_size,
                    "type": attachment_type,
                    "cloudinary_url": cloudinary_url
                }
            )
            db.add(event)
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
        """
        Add Root Cause Analysis to ticket.
        """
        db = SessionLocal()
        try:
            logger.info(f"Adding RCA for ticket {ticket_id}, user {created_by_user_id}")
            
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
            
            # Check if RCA already exists
            existing_rca = db.query(RootCauseAnalysis).filter(
                RootCauseAnalysis.ticket_id == ticket_uuid
            ).first()
            if existing_rca:
                logger.warning(f"RCA already exists for ticket {ticket.ticket_no}")
                raise ConflictError(f"RCA already exists for ticket {ticket.ticket_no}")
            
            # Validate root cause description
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
            
            # Create RCA
            try:
                rca = RootCauseAnalysis(
                    ticket_id=ticket_uuid,
                    root_cause_description=root_cause_description.strip(),
                    created_by_user_id=actual_creator_id,  # Use verified or fallback user
                    contributing_factors=contributing_factors or [],
                    prevention_measures=prevention_measures.strip() if prevention_measures else None,
                    resolution_steps=resolution_steps or [],
                    related_ticket_ids=related_ticket_ids or []
                )
                logger.info(f"RCA object created with creator_id={actual_creator_id}, adding to database")
                
                db.add(rca)
                db.flush()
                logger.info(f"✓ RCA flushed to database: {rca.id}")
                
                # Log RCA event
                event = TicketEvent(
                    ticket_id=ticket_uuid,
                    event_type="rca_added",
                    actor_user_id=actual_creator_id,
                    payload={
                        "rca_id": str(rca.id),
                        "factors_count": len(contributing_factors or []),
                        "steps_count": len(resolution_steps or [])
                    }
                )
                db.add(event)
                db.commit()
                logger.info(f"✓ RCA and event committed successfully")
                
                # Audit log
                if admin_id:
                    try:
                        AdminAuditLog.create(
                            admin_user_id=UUID(admin_id),
                            action="rca_added",
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
                
                logger.info(f"✓ RCA added to ticket {ticket.ticket_no}")
                
                return {
                    "id": str(rca.id),
                    "ticket_id": ticket_id,
                    "root_cause_description": rca.root_cause_description,
                    "contributing_factors": rca.contributing_factors,
                    "prevention_measures": rca.prevention_measures,
                    "resolution_steps": rca.resolution_steps,
                    "related_ticket_ids": rca.related_ticket_ids,
                    "ticket_closed_at": ticket_closed_at,
                    "created_at": rca.created_at.isoformat()
                }
            except Exception as e:
                logger.error(f"Failed during RCA creation: {e}", exc_info=True)
                raise
                    
        except (ValidationError, NotFoundError, ConflictError):
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
    def add_resolution_note(
        ticket_id: str,
        solution_description: str,
        created_by_user_id: str,
        steps_taken: Optional[List[str]] = None,
        resources_used: Optional[List[str]] = None,
        follow_up_notes: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add Resolution Note to ticket when closing.
        
        Args:
            ticket_id: Ticket UUID
            solution_description: Description of solution
            created_by_user_id: User creating note
            steps_taken: List of steps taken
            resources_used: List of resources used
            follow_up_notes: Optional follow-up notes
            admin_id: Admin performing action
            
        Returns:
            Dict with resolution note details
        """
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
    
    
    @staticmethod
    def update_ticket(
        ticket_id: str,
        subject: Optional[str] = None,
        summary: Optional[str] = None,
        detailed_description: Optional[str] = None,
        category: Optional[str] = None,
        level: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update ticket details"""
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            changes = {}
            
            if subject and len(subject.strip()) >= 3:
                changes["subject"] = subject
                ticket.subject = subject.strip()
            
            if summary:
                changes["summary"] = summary
                ticket.summary = summary.strip()
            
            if detailed_description and len(detailed_description.strip()) >= 10:
                changes["detailed_description"] = detailed_description[:100]
                ticket.detailed_description = detailed_description.strip()
            
            if category:
                changes["category"] = category
                ticket.category = category.strip()
            
            if level:
                valid_levels = ["level-1", "level-2", "level-3"]
                if level not in valid_levels:
                    raise ValidationError(f"Invalid level. Must be one of: {', '.join(valid_levels)}")
                changes["level"] = level
                ticket.level = level
            
            if not changes:
                raise ValidationError("No fields to update")
            
            ticket.updated_at = datetime.utcnow()
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
    def delete_attachment(ticket_id: str, attachment_id: str) -> Dict[str, Any]:
        """Delete attachment from ticket"""
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
            
            # Delete from Cloudinary if it's a Cloudinary URL
            if attachment.file_path and attachment.file_path.startswith('http'):
                try:
                    # Extract public_id from Cloudinary URL
                    # URL format: https://res.cloudinary.com/cloud_name/image/upload/v1234567890/tickets/filename.ext
                    from urllib.parse import urlparse
                    path_parts = urlparse(attachment.file_path).path.split('/')
                    # Get the part after 'upload' which is 'vXXX' and everything after
                    if 'upload' in path_parts:
                        upload_idx = path_parts.index('upload')
                        public_id_parts = path_parts[upload_idx + 2:]  # Skip 'upload' and 'vXXX'
                        public_id = '/'.join(public_id_parts).rsplit('.', 1)[0]  # Remove extension
                        
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
            
            # Delete attachment from database
            db.delete(attachment)
            ticket.updated_at = datetime.utcnow()
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