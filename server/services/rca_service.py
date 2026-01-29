from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from models.rca import RCA, RCAStatus
from models.ticket import Ticket
from schemas.rca import CreateRCARequest, SubmitRCARequest, ApproveRCARequest
from .event_service import EventService
from models.rca_event import RCAEventType
import logging

logger = logging.getLogger(__name__)

class RCAService:
    """RCA (Root Cause Analysis) management with approval workflow."""
    
    @staticmethod
    def create_rca(
        db: Session,
        company_id: UUID,
        ticket_id: UUID,
        user_id: UUID,
        request: CreateRCARequest
    ) -> RCA:
        """Create RCA in draft status."""
        # Verify ticket exists in company
        ticket = db.query(Ticket).filter(
            Ticket.id == ticket_id,
            Ticket.company_id == company_id
        ).first()
        if not ticket:
            raise Exception("Ticket not found")
        
        # Check if RCA already exists
        existing_rca = db.query(RCA).filter(RCA.ticket_id == ticket_id).first()
        if existing_rca and existing_rca.status != RCAStatus.DEPRECATED:
            raise Exception("RCA already exists for this ticket")
        
        rca = RCA(
            ticket_id=ticket_id,
            status=RCAStatus.DRAFT,
            root_cause=request.root_cause,
            resolution=request.resolution,
            prevention=request.prevention,
            created_by_user_id=user_id,
        )
        db.add(rca)
        db.flush()
        
        # Emit event
        EventService.emit_rca_event(
            db,
            rca.id,
            RCAEventType.CREATED,
            user_id,
            {}
        )
        
        logger.info(f"RCA created for ticket {ticket.ticket_no}")
        return rca
    
    @staticmethod
    def get_rca(db: Session, company_id: UUID, ticket_id: UUID) -> RCA:
        """Get RCA for ticket."""
        ticket = db.query(Ticket).filter(
            Ticket.id == ticket_id,
            Ticket.company_id == company_id
        ).first()
        if not ticket:
            raise Exception("Ticket not found")
        
        return db.query(RCA).filter(
            RCA.ticket_id == ticket_id,
            RCA.status != RCAStatus.DEPRECATED
        ).first()
    
    @staticmethod
    def update_rca(
        db: Session,
        company_id: UUID,
        rca_id: UUID,
        user_id: UUID,
        request: CreateRCARequest
    ) -> RCA:
        """Update RCA (draft only)."""
        rca = db.query(RCA).filter(RCA.id == rca_id).first()
        if not rca:
            raise Exception("RCA not found")
        
        # Verify company access
        ticket = db.query(Ticket).filter(
            Ticket.id == rca.ticket_id,
            Ticket.company_id == company_id
        ).first()
        if not ticket:
            raise Exception("RCA not found in company")
        
        if rca.status != RCAStatus.DRAFT:
            raise Exception("Can only edit RCA in draft status")
        
        rca.root_cause = request.root_cause
        rca.resolution = request.resolution
        rca.prevention = request.prevention
        db.flush()
        
        logger.info(f"RCA updated: {rca.id}")
        return rca
    
    @staticmethod
    def submit_rca(
        db: Session,
        company_id: UUID,
        rca_id: UUID,
        user_id: UUID,
        request: SubmitRCARequest
    ) -> RCA:
        """Submit RCA for approval."""
        rca = db.query(RCA).filter(RCA.id == rca_id).first()
        if not rca:
            raise Exception("RCA not found")
        
        # Verify company access
        ticket = db.query(Ticket).filter(
            Ticket.id == rca.ticket_id,
            Ticket.company_id == company_id
        ).first()
        if not ticket:
            raise Exception("RCA not found in company")
        
        if rca.status != RCAStatus.DRAFT:
            raise Exception("Can only submit RCA in draft status")
        
        rca.status = RCAStatus.PENDING_APPROVAL
        rca.submitted_at = datetime.utcnow()
        db.flush()
        
        # Emit event
        EventService.emit_rca_event(
            db,
            rca.id,
            RCAEventType.SUBMITTED,
            user_id,
            {"notes": request.notes}
        )
        
        logger.info(f"RCA submitted for approval: {rca.id}")
        return rca
    
    @staticmethod
    def approve_rca(
        db: Session,
        company_id: UUID,
        rca_id: UUID,
        approver_user_id: UUID,
        request: ApproveRCARequest
    ) -> RCA:
        """Approve RCA and generate embeddings."""
        rca = db.query(RCA).filter(RCA.id == rca_id).first()
        if not rca:
            raise Exception("RCA not found")
        
        # Verify company access
        ticket = db.query(Ticket).filter(
            Ticket.id == rca.ticket_id,
            Ticket.company_id == company_id
        ).first()
        if not ticket:
            raise Exception("RCA not found in company")
        
        if rca.status != RCAStatus.PENDING_APPROVAL:
            raise Exception("Can only approve RCA in pending approval status")
        
        rca.status = RCAStatus.APPROVED
        rca.approved_by_user_id = approver_user_id
        rca.approved_at = datetime.utcnow()
        db.flush()
        
        # Emit event
        EventService.emit_rca_event(
            db,
            rca.id,
            RCAEventType.APPROVED,
            approver_user_id,
            {"approver_notes": request.approver_notes}
        )
        
        logger.info(f"RCA approved: {rca.id}")
        
        # TODO: Generate embeddings in Qdrant
        # EmbeddingService.generate_rca_embeddings(db, company_id, rca)
        
        return rca
    
    @staticmethod
    def reject_rca(
        db: Session,
        company_id: UUID,
        rca_id: UUID,
        approver_user_id: UUID,
        reason: str
    ) -> RCA:
        """Reject RCA (back to draft)."""
        rca = db.query(RCA).filter(RCA.id == rca_id).first()
        if not rca:
            raise Exception("RCA not found")
        
        # Verify company access
        ticket = db.query(Ticket).filter(
            Ticket.id == rca.ticket_id,
            Ticket.company_id == company_id
        ).first()
        if not ticket:
            raise Exception("RCA not found in company")
        
        if rca.status != RCAStatus.PENDING_APPROVAL:
            raise Exception("Can only reject RCA in pending approval status")
        
        rca.status = RCAStatus.DRAFT
        db.flush()
        
        # Emit event
        EventService.emit_rca_event(
            db,
            rca.id,
            RCAEventType.REJECTED,
            approver_user_id,
            {"reason": reason}
        )
        
        logger.info(f"RCA rejected: {rca.id}")
        return rca