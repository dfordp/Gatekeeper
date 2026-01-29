from uuid import UUID
from typing import Optional, Any
from sqlalchemy.orm import Session
from models.ticket_event import TicketEvent, TicketEventType
from models.rca_event import RCAEvent, RCAEventType
from models.attachment_event import AttachmentEvent, AttachmentEventType
import logging

logger = logging.getLogger(__name__)

class EventService:
    """Service for emitting immutable events."""
    
    @staticmethod
    def emit_ticket_event(
        db: Session,
        ticket_id: UUID,
        event_type: TicketEventType,
        actor_user_id: UUID,
        payload: Optional[dict[str, Any]] = None
    ) -> TicketEvent:
        """Emit a ticket event (immutable)."""
        event = TicketEvent(
            ticket_id=ticket_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        db.add(event)
        db.flush()
        logger.info(f"Ticket event emitted: {event_type} for ticket {ticket_id}")
        return event
    
    @staticmethod
    def emit_rca_event(
        db: Session,
        rca_id: UUID,
        event_type: RCAEventType,
        actor_user_id: UUID,
        payload: Optional[dict[str, Any]] = None
    ) -> RCAEvent:
        """Emit an RCA event (immutable)."""
        event = RCAEvent(
            rca_id=rca_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        db.add(event)
        db.flush()
        logger.info(f"RCA event emitted: {event_type} for RCA {rca_id}")
        return event
    
    @staticmethod
    def emit_attachment_event(
        db: Session,
        ticket_id: UUID,
        event_type: AttachmentEventType,
        actor_user_id: UUID,
        attachment_id: Optional[UUID] = None,
        payload: Optional[dict[str, Any]] = None
    ) -> AttachmentEvent:
        """Emit an attachment event (immutable)."""
        event = AttachmentEvent(
            ticket_id=ticket_id,
            attachment_id=attachment_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        db.add(event)
        db.flush()
        logger.info(f"Attachment event emitted: {event_type}")
        return event