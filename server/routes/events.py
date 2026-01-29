from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID
from sqlalchemy import desc
from models.ticket_event import TicketEvent
from models.rca_event import RCAEvent
from models.ticket import Ticket
from models.rca import RCA
from schemas.event import TicketEventResponse, RCAEventResponse
from schemas.common import APIResponse, PaginatedResponse
from utils.database import get_db
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/{company_id}/tickets/{ticket_id}/events")
async def get_ticket_events(
    company_id: UUID,
    ticket_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_company_id: UUID = Depends(lambda: None),
) -> APIResponse[PaginatedResponse[TicketEventResponse]]:
    """Get ticket event timeline (immutable)."""
    
    if str(company_id) != str(current_company_id):
        raise HTTPException(status_code=403, detail="Company mismatch")
    
    try:
        # Verify ticket exists
        ticket = db.query(Ticket).filter(
            Ticket.id == ticket_id,
            Ticket.company_id == company_id
        ).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        # Get events
        total = db.query(TicketEvent).filter(
            TicketEvent.ticket_id == ticket_id
        ).count()
        
        events = db.query(TicketEvent).filter(
            TicketEvent.ticket_id == ticket_id
        ).order_by(desc(TicketEvent.created_at)).offset((page - 1) * limit).limit(limit).all()
        
        # Enrich with actor user name
        event_responses = []
        for event in events:
            event_dict = TicketEventResponse.from_orm(event).dict()
            event_dict['actor_user_name'] = event.actor_user.name
            event_responses.append(TicketEventResponse(**event_dict))
        
        paginated = PaginatedResponse(
            items=event_responses,
            total=total,
            page=page,
            limit=limit,
            pages=(total + limit - 1) // limit,
        )
        
        return APIResponse(
            success=True,
            data=paginated,
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ticket events: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{company_id}/rca/{rca_id}/events")
async def get_rca_events(
    company_id: UUID,
    rca_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_company_id: UUID = Depends(lambda: None),
) -> APIResponse[PaginatedResponse[RCAEventResponse]]:
    """Get RCA event timeline (approval workflow)."""
    
    if str(company_id) != str(current_company_id):
        raise HTTPException(status_code=403, detail="Company mismatch")
    
    try:
        # Verify RCA exists in company
        rca = db.query(RCA).filter(RCA.id == rca_id).first()
        if not rca:
            raise HTTPException(status_code=404, detail="RCA not found")
        
        ticket = db.query(Ticket).filter(
            Ticket.id == rca.ticket_id,
            Ticket.company_id == company_id
        ).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="RCA not found in company")
        
        # Get events
        total = db.query(RCAEvent).filter(
            RCAEvent.rca_id == rca_id
        ).count()
        
        events = db.query(RCAEvent).filter(
            RCAEvent.rca_id == rca_id
        ).order_by(desc(RCAEvent.created_at)).offset((page - 1) * limit).limit(limit).all()
        
        # Enrich with actor user name
        event_responses = []
        for event in events:
            event_dict = RCAEventResponse.from_orm(event).dict()
            event_dict['actor_user_name'] = event.actor_user.name
            event_responses.append(RCAEventResponse(**event_dict))
        
        paginated = PaginatedResponse(
            items=event_responses,
            total=total,
            page=page,
            limit=limit,
            pages=(total + limit - 1) // limit,
        )
        
        return APIResponse(
            success=True,
            data=paginated,
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting RCA events: {e}")
        raise HTTPException(status_code=400, detail=str(e))