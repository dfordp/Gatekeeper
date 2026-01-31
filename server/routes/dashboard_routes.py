# server/routes/dashboard_routes.py
"""Dashboard routes for ticket management and analytics"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from middleware.auth_middleware import get_current_admin
from services.ticket_service import TicketService
from utils.exceptions import ValidationError, NotFoundError
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# Request models
class UpdateStatusRequest(BaseModel):
    status: str

class AssignTicketRequest(BaseModel):
    engineer_id: str

@router.get("/tickets")
async def get_tickets(
    status: str = Query(None),
    search: str = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin_payload: dict = Depends(get_current_admin)
):
    """Get paginated list of tickets"""
    try:
        result = TicketService.get_tickets(
            status=status,
            limit=limit,
            offset=offset,
            search=search
        )
        return result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error getting tickets: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve tickets")


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: str,
    admin_payload: dict = Depends(get_current_admin)
):
    """Get ticket details"""
    try:
        ticket = TicketService.get_ticket_by_id(ticket_id)
        return ticket
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error getting ticket: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve ticket")


@router.put("/tickets/{ticket_id}/status")
async def update_ticket_status(
    ticket_id: str,
    request: UpdateStatusRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """Update ticket status"""
    try:
        result = TicketService.update_ticket_status(
            ticket_id=ticket_id,
            new_status=request.status,
            admin_id=admin_payload.get("sub")
        )
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error updating ticket status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update ticket")


@router.put("/tickets/{ticket_id}/assign")
async def assign_ticket(
    ticket_id: str,
    request: AssignTicketRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """Assign ticket to engineer"""
    try:
        result = TicketService.assign_ticket(
            ticket_id=ticket_id,
            engineer_id=request.engineer_id,
            admin_id=admin_payload.get("sub")
        )
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error assigning ticket: {e}")
        raise HTTPException(status_code=500, detail="Failed to assign ticket")


@router.get("/analytics")
async def get_analytics(
    days: int = Query(30, ge=1, le=365),
    admin_payload: dict = Depends(get_current_admin)
):
    """Get ticket analytics"""
    try:
        analytics = TicketService.get_analytics(days=days)
        return analytics
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve analytics")