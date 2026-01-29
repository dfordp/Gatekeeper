from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc
from models.ticket import Ticket, TicketStatus, TicketLevel, TicketCategory
from models.user import User
from schemas.ticket import CreateTicketRequest
from .event_service import EventService
from models.ticket_event import TicketEventType
import logging

logger = logging.getLogger(__name__)

class TicketService:
    """Ticket management with event sourcing."""
    
    @staticmethod
    def _generate_ticket_number(db: Session) -> str:
        """Generate next ticket number (TKT-00001, TKT-00002, etc.)."""
        last_ticket = db.query(Ticket).order_by(desc(Ticket.created_at)).first()
        if last_ticket:
            # Extract number from ticket_no like "TKT-00001"
            try:
                num = int(last_ticket.ticket_no.split('-')[1])
                return f"TKT-{num + 1:05d}"
            except:
                return "TKT-00001"
        return "TKT-00001"
    
    @staticmethod
    def create_ticket(
        db: Session,
        company_id: UUID,
        user_id: UUID,
        request: CreateTicketRequest
    ) -> Ticket:
        """Create a new ticket (starts in draft status)."""
        ticket_no = TicketService._generate_ticket_number(db)
        
        ticket = Ticket(
            ticket_no=ticket_no,
            status=TicketStatus.DRAFT,
            subject=request.subject,
            detailed_description=request.detailed_description,
            level=TicketLevel[request.level.upper()] if request.level else None,
            category=TicketCategory[request.category.upper()] if request.category else None,
            company_id=company_id,
            raised_by_user_id=user_id,
        )
        db.add(ticket)
        db.flush()
        
        # Emit creation event
        EventService.emit_ticket_event(
            db,
            ticket.id,
            TicketEventType.CREATED,
            user_id,
            {
                "subject": request.subject,
                "category": request.category,
                "level": request.level,
            }
        )
        
        logger.info(f"Ticket created: {ticket.ticket_no}")
        return ticket
    
    @staticmethod
    def get_ticket(db: Session, company_id: UUID, ticket_id: UUID) -> Ticket:
        """Get ticket (with company isolation)."""
        return db.query(Ticket).filter(
            Ticket.id == ticket_id,
            Ticket.company_id == company_id
        ).first()
    
    @staticmethod
    def list_tickets(
        db: Session,
        company_id: UUID,
        status: str = None,
        level: str = None,
        category: str = None,
        assignee_id: UUID = None,
        page: int = 1,
        limit: int = 20,
        search: str = None
    ):
        """List tickets with filters (company-scoped)."""
        query = db.query(Ticket).filter(Ticket.company_id == company_id)
        
        if status:
            query = query.filter(Ticket.status == status)
        if level:
            query = query.filter(Ticket.level == level)
        if category:
            query = query.filter(Ticket.category == category)
        if assignee_id:
            query = query.filter(Ticket.assigned_engineer_id == assignee_id)
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (Ticket.subject.ilike(search_term)) |
                (Ticket.detailed_description.ilike(search_term)) |
                (Ticket.ticket_no.ilike(search_term))
            )
        
        total = query.count()
        tickets = query.order_by(desc(Ticket.created_at)).offset((page - 1) * limit).limit(limit).all()
        
        return tickets, total
    
    @staticmethod
    def update_ticket_status(
        db: Session,
        company_id: UUID,
        ticket_id: UUID,
        new_status: str,
        actor_user_id: UUID,
        reason: str
    ) -> Ticket:
        """Update ticket status (emits event)."""
        ticket = TicketService.get_ticket(db, company_id, ticket_id)
        if not ticket:
            raise Exception("Ticket not found")
        
        old_status = ticket.status
        ticket.status = TicketStatus[new_status.upper()]
        
        if new_status.lower() == "closed":
            ticket.closed_at = datetime.utcnow()
        elif new_status.lower() == "reopened":
            ticket.reopened_at = datetime.utcnow()
        
        db.flush()
        
        # Emit event
        EventService.emit_ticket_event(
            db,
            ticket.id,
            TicketEventType.STATUS_CHANGED,
            actor_user_id,
            {
                "old_status": old_status,
                "new_status": new_status,
                "reason": reason,
            }
        )
        
        logger.info(f"Ticket {ticket.ticket_no} status changed: {old_status} → {new_status}")
        return ticket
    
    @staticmethod
    def assign_ticket(
        db: Session,
        company_id: UUID,
        ticket_id: UUID,
        engineer_id: UUID,
        actor_user_id: UUID,
        reason: str
    ) -> Ticket:
        """Assign ticket to engineer (emits event)."""
        ticket = TicketService.get_ticket(db, company_id, ticket_id)
        if not ticket:
            raise Exception("Ticket not found")
        
        # Verify engineer exists in same company
        engineer = db.query(User).filter(
            User.id == engineer_id,
            User.company_id == company_id
        ).first()
        if not engineer:
            raise Exception("Engineer not found in company")
        
        old_assignee = ticket.assigned_engineer_id
        ticket.assigned_engineer_id = engineer_id
        db.flush()
        
        # Emit event
        EventService.emit_ticket_event(
            db,
            ticket.id,
            TicketEventType.ASSIGNED,
            actor_user_id,
            {
                "old_assignee_id": str(old_assignee) if old_assignee else None,
                "new_assignee_id": str(engineer_id),
                "engineer_name": engineer.name,
                "reason": reason,
            }
        )
        
        logger.info(f"Ticket {ticket.ticket_no} assigned to {engineer.name}")
        return ticket
    
    @staticmethod
    def change_level(
        db: Session,
        company_id: UUID,
        ticket_id: UUID,
        new_level: str,
        actor_user_id: UUID,
        reason: str
    ) -> Ticket:
        """Change ticket level (emits event)."""
        ticket = TicketService.get_ticket(db, company_id, ticket_id)
        if not ticket:
            raise Exception("Ticket not found")
        
        old_level = ticket.level
        ticket.level = TicketLevel[new_level.upper()]
        db.flush()
        
        # Emit event
        EventService.emit_ticket_event(
            db,
            ticket.id,
            TicketEventType.LEVEL_CHANGED,
            actor_user_id,
            {
                "old_level": str(old_level) if old_level else None,
                "new_level": new_level,
                "reason": reason,
            }
        )
        
        logger.info(f"Ticket {ticket.ticket_no} level changed to {new_level}")
        return ticket
    
    @staticmethod
    def add_comment(
        db: Session,
        company_id: UUID,
        ticket_id: UUID,
        user_id: UUID,
        text: str
    ) -> TicketEvent:
        """Add comment to ticket (emits event)."""
        ticket = TicketService.get_ticket(db, company_id, ticket_id)
        if not ticket:
            raise Exception("Ticket not found")
        
        # Emit event
        event = EventService.emit_ticket_event(
            db,
            ticket.id,
            TicketEventType.COMMENT_ADDED,
            user_id,
            {"text": text}
        )
        
        logger.info(f"Comment added to ticket {ticket.ticket_no}")
        return event