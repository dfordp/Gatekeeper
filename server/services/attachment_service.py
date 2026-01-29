from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from models.attachment import Attachment
from models.ticket import Ticket
from .event_service import EventService
from models.attachment_event import AttachmentEventType
import logging

logger = logging.getLogger(__name__)

class AttachmentService:
    """Attachment management with versioning."""
    
    @staticmethod
    def upload_attachment(
        db: Session,
        company_id: UUID,
        ticket_id: UUID,
        user_id: UUID,
        file_name: str,
        file_size: int,
        mime_type: str,
        file_path: str,
        attachment_type: str = "document"
    ) -> Attachment:
        """Upload attachment (new version)."""
        # Verify ticket exists
        ticket = db.query(Ticket).filter(
            Ticket.id == ticket_id,
            Ticket.company_id == company_id
        ).first()
        if not ticket:
            raise Exception("Ticket not found")
        
        attachment = Attachment(
            ticket_id=ticket_id,
            type=attachment_type,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            file_path=file_path,
            is_active=True,
        )
        db.add(attachment)
        db.flush()
        
        # Emit event
        EventService.emit_attachment_event(
            db,
            ticket_id,
            AttachmentEventType.UPLOADED,
            user_id,
            attachment_id=attachment.id,
            payload={
                "file_name": file_name,
                "file_size": file_size,
                "mime_type": mime_type,
            }
        )
        
        logger.info(f"Attachment uploaded: {file_name} to ticket {ticket.ticket_no}")
        return attachment
    
    @staticmethod
    def deprecate_attachment(
        db: Session,
        company_id: UUID,
        attachment_id: UUID,
        user_id: UUID,
        reason: str
    ) -> Attachment:
        """Deprecate attachment (soft-delete)."""
        attachment = db.query(Attachment).filter(
            Attachment.id == attachment_id
        ).first()
        if not attachment:
            raise Exception("Attachment not found")
        
        # Verify company access
        ticket = db.query(Ticket).filter(
            Ticket.id == attachment.ticket_id,
            Ticket.company_id == company_id
        ).first()
        if not ticket:
            raise Exception("Attachment not found in company")
        
        if not attachment.is_active:
            raise Exception("Attachment already deprecated")
        
        attachment.is_active = False
        attachment.deprecated_at = datetime.utcnow()
        attachment.deprecation_reason = reason
        db.flush()
        
        # Emit event
        EventService.emit_attachment_event(
            db,
            attachment.ticket_id,
            AttachmentEventType.DEPRECATED,
            user_id,
            attachment_id=attachment.id,
            payload={"reason": reason}
        )
        
        # TODO: Invalidate embeddings
        # EmbeddingService.deprecate_attachment_embeddings(db, attachment.id)
        
        logger.info(f"Attachment deprecated: {attachment.file_name}")
        return attachment
    
    @staticmethod
    def get_attachment(db: Session, company_id: UUID, attachment_id: UUID) -> Attachment:
        """Get attachment (with company isolation)."""
        attachment = db.query(Attachment).filter(
            Attachment.id == attachment_id
        ).first()
        if not attachment:
            return None
        
        # Verify company access
        ticket = db.query(Ticket).filter(
            Ticket.id == attachment.ticket_id,
            Ticket.company_id == company_id
        ).first()
        if not ticket:
            return None
        
        return attachment
    
    @staticmethod
    def list_attachments(db: Session, company_id: UUID, ticket_id: UUID):
        """List attachments for ticket."""
        ticket = db.query(Ticket).filter(
            Ticket.id == ticket_id,
            Ticket.company_id == company_id
        ).first()
        if not ticket:
            return []
        
        return db.query(Attachment).filter(
            Attachment.ticket_id == ticket_id
        ).order_by(Attachment.created_at.desc()).all()