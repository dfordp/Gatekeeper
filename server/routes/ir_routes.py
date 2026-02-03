from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from middleware.auth_middleware import get_current_admin
from services.ir_service import IRService
from services.embedding_manager import EmbeddingManager
from utils.exceptions import ValidationError, NotFoundError
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["Incident Reports"])

# ==================== REQUEST MODELS ====================

class OpenIRRequest(BaseModel):
    """Request model for opening an Incident Report"""
    ir_number: str
    vendor: Optional[str] = "siemens"
    expected_resolution_date: Optional[datetime] = None
    notes: Optional[str] = None
    created_by_user_id: Optional[str] = None

class UpdateIRStatusRequest(BaseModel):
    """Request model for updating IR status"""
    status: str
    vendor_status: Optional[str] = None
    vendor_notes: Optional[str] = None
    notes: Optional[str] = None
    updated_by_user_id: Optional[str] = None

class CloseIRRequest(BaseModel):
    """Request model for closing an IR"""
    resolution_notes: Optional[str] = None
    closed_by_user_id: Optional[str] = None

# ==================== ROUTES ====================

@router.post("/tickets/{ticket_id}/ir/open")
async def open_ir(
    ticket_id: str,
    request_data: OpenIRRequest,
    request: Request
):
    try:
        # Extract company_id and user_id from the ticket first
        from core.database import SessionLocal, Ticket
        from uuid import UUID
        db = SessionLocal()
        ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
        if not ticket:
            db.close()
            raise NotFoundError("Ticket not found")
        
        # Get user_id from request or use ticket's raised_by_user_id
        user_id = request_data.created_by_user_id
        if not user_id:
            user_id = str(ticket.raised_by_user_id)
        
        db.close()
        
        result = IRService.open_ir(
            ticket_id=ticket_id,
            ir_number=request_data.ir_number,
            vendor=request_data.vendor or "siemens",
            expected_resolution_date=request_data.expected_resolution_date,
            notes=request_data.notes,
            created_by_user_id=user_id
        )
        
        # Create embedding for the IR
        try:
            EmbeddingManager.add_ir_embedding(
                ticket_id=ticket_id,
                ir_id=result.get("id"),
                company_id=str(ticket.company_id),
                ir_number=result.get("ir_number"),
                vendor=result.get("vendor"),
                notes=request_data.notes
            )
        except Exception as e:
            logger.warning(f"Failed to create IR embedding: {e}")
        
        return result
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error opening IR: {e}")
        raise HTTPException(status_code=500, detail="Failed to open IR")

@router.put("/ir/{ir_id}/status")
async def update_ir_status(
    ir_id: str,
    request_data: UpdateIRStatusRequest,
    request: Request
):
    try:
        # Get user_id from header or use the provided one
        user_id = request_data.updated_by_user_id
        
        result = IRService.update_ir_status(
            ir_id=ir_id,
            status=request_data.status,
            vendor_status=request_data.vendor_status,
            vendor_notes=request_data.vendor_notes,
            notes=request_data.notes,
            updated_by_user_id=user_id
        )
        
        # Update embedding when IR status changes
        try:
            from core.database import SessionLocal, IncidentReport
            from uuid import UUID
            db = SessionLocal()
            ir = db.query(IncidentReport).filter(IncidentReport.id == UUID(ir_id)).first()
            if ir:
                EmbeddingManager.update_ir_embedding(
                    ticket_id=str(ir.ticket_id),
                    company_id=str(ir.ticket.company_id) if ir.ticket else None,
                    ir_number=ir.ir_number,
                    vendor=ir.vendor,
                    status=request_data.status,
                    notes=ir.notes,
                    vendor_notes=request_data.vendor_notes,
                    resolution_notes=request_data.notes if request_data.status in ["resolved", "closed"] else None
                )
            db.close()
        except Exception as e:
            logger.warning(f"Failed to update IR embedding: {e}")
        
        return result
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating IR: {e}")
        raise HTTPException(status_code=500, detail="Failed to update IR")

@router.post("/ir/{ir_id}/close")
async def close_ir(
    ir_id: str,
    request_data: CloseIRRequest,
    request: Request
):
    try:
        result = IRService.close_ir(
            ir_id=ir_id,
            resolution_notes=request_data.resolution_notes,
            closed_by_user_id=request_data.closed_by_user_id
        )
        
        # Update embedding when IR is closed
        try:
            from core.database import SessionLocal, IncidentReport
            from uuid import UUID
            db = SessionLocal()
            ir = db.query(IncidentReport).filter(IncidentReport.id == UUID(ir_id)).first()
            if ir:
                EmbeddingManager.update_ir_embedding(
                    ticket_id=str(ir.ticket_id),
                    company_id=str(ir.ticket.company_id) if ir.ticket else None,
                    ir_number=ir.ir_number,
                    vendor=ir.vendor,
                    status="closed",
                    resolution_notes=request_data.resolution_notes
                )
            db.close()
        except Exception as e:
            logger.warning(f"Failed to update IR embedding on close: {e}")
        
        return result
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error closing IR: {e}")
        raise HTTPException(status_code=500, detail="Failed to close IR")

@router.get("/ir/{ir_id}")
async def get_ir(ir_id: str):
    try:
        return IRService.get_ir(ir_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting IR: {e}")
        raise HTTPException(status_code=500, detail="Failed to get IR")

@router.get("/tickets/{ticket_id}/ir")
async def get_ticket_irs(ticket_id: str):
    try:
        return IRService.get_ticket_irs(ticket_id)
    except Exception as e:
        logger.error(f"Error getting ticket IRs: {e}")
        raise HTTPException(status_code=500, detail="Failed to get IRs")

@router.get("/ir/open")
async def get_open_irs():
    try:
        return IRService.get_open_irs()
    except Exception as e:
        logger.error(f"Error getting open IRs: {e}")
        raise HTTPException(status_code=500, detail="Failed to get open IRs")