# server/routes/tickets.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from uuid import UUID
from schemas.ticket import (
    TicketResponse, CreateTicketRequest, UpdateTicketStatusRequest,
    AssignTicketRequest, ChangeTicketLevelRequest
)
from schemas.common import APIResponse, PaginatedResponse
from services.ticket_service import TicketService
from services.rbac_service import RBACService, Permission
from utils.database import get_db
from dependencies import get_current_user_id, get_current_company_id, get_current_role
from utils.errors import CompanyIsolationError, NotFoundError
from datetime import datetime
import logging
from schemas.ticket import (
    TicketResponse, CreateTicketRequest, UpdateTicketStatusRequest,
    AssignTicketRequest, ChangeTicketLevelRequest, CommentRequest
)

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/{company_id}/tickets")
async def create_ticket(
    company_id: UUID,
    request: CreateTicketRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
    db: Session = Depends(get_db),
) -> APIResponse[TicketResponse]:
    """Create a new ticket."""
    
    # Verify company match
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    # RBAC check
    RBACService.require_permission(current_role, Permission.TICKET_CREATE)
    
    try:
        ticket = TicketService.create_ticket(
            db,
            company_id=company_id,
            user_id=current_user_id,
            request=request
        )
        db.commit()
        
        return APIResponse(
            success=True,
            data=TicketResponse.from_orm(ticket),
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating ticket: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{company_id}/tickets")
async def list_tickets(
    company_id: UUID,
    status: str = Query(None),
    level: str = Query(None),
    category: str = Query(None),
    assignee: UUID = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    db: Session = Depends(get_db),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse[PaginatedResponse[TicketResponse]]:
    """List tickets (company-scoped)."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.TICKET_VIEW)
    
    try:
        tickets, total = TicketService.list_tickets(
            db,
            company_id=company_id,
            status=status,
            level=level,
            category=category,
            assignee_id=assignee,
            page=page,
            limit=limit,
            search=search,
        )
        
        paginated = PaginatedResponse(
            items=[TicketResponse.from_orm(t) for t in tickets],
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
    except Exception as e:
        logger.error(f"Error listing tickets: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{company_id}/tickets/{ticket_id}")
async def get_ticket(
    company_id: UUID,
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse[TicketResponse]:
    """Get ticket detail."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.TICKET_VIEW)
    
    ticket = TicketService.get_ticket(db, company_id, ticket_id)
    if not ticket:
        raise NotFoundError("Ticket", str(ticket_id))
    
    return APIResponse(
        success=True,
        data=TicketResponse.from_orm(ticket),
        meta={"timestamp": datetime.utcnow().isoformat()}
    )

@router.post("/{company_id}/tickets/{ticket_id}/status")
async def update_ticket_status(
    company_id: UUID,
    ticket_id: UUID,
    request: UpdateTicketStatusRequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse[TicketResponse]:
    """Update ticket status (emits event)."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.TICKET_CHANGE_STATUS)
    
    try:
        ticket = TicketService.update_ticket_status(
            db,
            company_id=company_id,
            ticket_id=ticket_id,
            new_status=request.new_status,
            actor_user_id=current_user_id,
            reason=request.reason,
        )
        db.commit()
        
        return APIResponse(
            success=True,
            data=TicketResponse.from_orm(ticket),
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating ticket status: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{company_id}/tickets/{ticket_id}/assign")
async def assign_ticket(
    company_id: UUID,
    ticket_id: UUID,
    request: AssignTicketRequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse[TicketResponse]:
    """Assign ticket to engineer."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.TICKET_ASSIGN)
    
    try:
        ticket = TicketService.assign_ticket(
            db,
            company_id=company_id,
            ticket_id=ticket_id,
            engineer_id=request.engineer_id,
            actor_user_id=current_user_id,
            reason=request.reason,
        )
        db.commit()
        
        return APIResponse(
            success=True,
            data=TicketResponse.from_orm(ticket),
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error assigning ticket: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{company_id}/tickets/{ticket_id}/level")
async def change_ticket_level(
    company_id: UUID,
    ticket_id: UUID,
    request: ChangeTicketLevelRequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse[TicketResponse]:
    """Change ticket severity level."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.TICKET_CHANGE_LEVEL)
    
    try:
        ticket = TicketService.change_level(
            db,
            company_id=company_id,
            ticket_id=ticket_id,
            new_level=request.new_level,
            actor_user_id=current_user_id,
            reason=request.reason,
        )
        db.commit()
        
        return APIResponse(
            success=True,
            data=TicketResponse.from_orm(ticket),
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error changing ticket level: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{company_id}/tickets/{ticket_id}/comment")
async def add_comment(
    company_id: UUID,
    ticket_id: UUID,
    request: CommentRequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse:
    """Add comment to ticket."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.TICKET_VIEW)
    
    try:
        event = TicketService.add_comment(
            db,
            company_id=company_id,
            ticket_id=ticket_id,
            user_id=current_user_id,
            text=request.text,
        )
        db.commit()
        
        return APIResponse(
            success=True,
            data={"event_id": str(event.id)},
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding comment: {e}")
        raise HTTPException(status_code=400, detail=str(e))

