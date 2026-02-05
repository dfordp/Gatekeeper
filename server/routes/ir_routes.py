from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from utils.datetime_utils import parse_iso_date
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
    expected_resolution_date: Optional[str] = None
    ir_raised_at: Optional[str] = None  # NEW: ISO string format
    closed_at: Optional[str] = None  # NEW: ISO string format
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
    closed_at: Optional[str] = None  # NEW: ISO string format for closure date
    closed_by_user_id: Optional[str] = None

# ==================== ROUTES ====================

@router.post("/tickets/{ticket_id}/ir/open")
async def open_ir(
    ticket_id: str,
    request_data: OpenIRRequest,
    request: Request
):
    try:
        # Parse dates if provided
        ir_raised_at = None
        if request_data.ir_raised_at:
            try:
                ir_raised_at = parse_iso_date(request_data.ir_raised_at)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid ir_raised_at date: {str(e)}")
        
        # Parse expected_resolution_date
        expected_resolution_date = None
        if request_data.expected_resolution_date:
            try:
                expected_resolution_date = parse_iso_date(request_data.expected_resolution_date)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid expected_resolution_date: {str(e)}")
        
        closed_at = None
        if request_data.closed_at:
            try:
                closed_at = parse_iso_date(request_data.closed_at)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid closed_at date: {str(e)}")
        
        # Remove the duplicate closed_at parsing block here
        
        result = IRService.open_ir(
            ticket_id=ticket_id,
            ir_number=request_data.ir_number,
            vendor=request_data.vendor,
            expected_resolution_date=expected_resolution_date,  # Use parsed date
            ir_raised_at=ir_raised_at,
            notes=request_data.notes,
            closed_at=closed_at,
            created_by_user_id=request_data.created_by_user_id
        )
        
        # Create embedding for IR
        try:
            EmbeddingManager.add_ir_embedding(
                ticket_id=ticket_id,
                ir_id=result["id"],
                company_id=result["company_id"],
                ir_number=result["ir_number"],
                vendor=result["vendor"],
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

@router.post("/ir/{ir_id}/close")
async def close_ir(
    ir_id: str,
    request_data: CloseIRRequest,
    request: Request
):
    try:
        # Parse closure date if provided
        resolved_at = None
        if hasattr(request_data, 'closed_at') and request_data.closed_at:
            try:
                resolved_at = parse_iso_date(request_data.closed_at)
            except ValueError as e:
                logger.warning(f"Failed to parse closed_at date: {e}")
        
        result = IRService.close_ir(
            ir_id=ir_id,
            resolution_notes=request_data.resolution_notes,
            closed_by_user_id=request_data.closed_by_user_id,
            resolved_at=resolved_at  # NEW: Pass the closure date
        )
        
        # Delete embeddings when IR is closed
        try:
            from core.database import SessionLocal, IncidentReport
            from uuid import UUID
            db = SessionLocal()
            ir = db.query(IncidentReport).filter(IncidentReport.id == UUID(ir_id)).first()
            if ir:
                EmbeddingManager.deprecate_ir_embeddings(
                    ticket_id=str(ir.ticket_id),
                    reason="ir_closed"
                )
            db.close()
        except Exception as e:
            logger.warning(f"Failed to deprecate IR embeddings on close: {e}")
        
        return result
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error closing IR: {e}")
        raise HTTPException(status_code=500, detail="Failed to close IR")
    
@router.put("/ir/{ir_id}/status")
async def update_ir_status(
    ir_id: str,
    request_data: UpdateIRStatusRequest,
    request: Request
):
    try:
        result = IRService.update_ir_status(
            ir_id=ir_id,
            status=request_data.status,
            vendor_status=request_data.vendor_status,
            vendor_notes=request_data.vendor_notes,
            notes=request_data.notes,
            updated_by_user_id=request_data.updated_by_user_id
        )
        return result
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating IR status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update IR status")

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
    
@router.delete("/ir/{ir_id}")
async def delete_ir(
    ir_id: str,
    request: Request
):
    """Delete an Incident Report and its embeddings"""
    try:
        from core.database import SessionLocal, IncidentReport
        from uuid import UUID
        
        # Get IR details before deletion
        db = SessionLocal()
        ir = db.query(IncidentReport).filter(IncidentReport.id == UUID(ir_id)).first()
        if not ir:
            raise NotFoundError("Incident Report not found")
        
        ticket_id = str(ir.ticket_id)
        ir_number = ir.ir_number
        db.close()
        
        # Deprecate IR embeddings (delete from Qdrant, mark inactive in PostgreSQL)
        try:
            EmbeddingManager.deprecate_ir_embeddings(
                ticket_id=ticket_id,
                reason="ir_deleted"
            )
        except Exception as e:
            logger.warning(f"Failed to deprecate IR embeddings: {e}")
        
        # Delete the IR via service
        result = IRService.delete_ir(ir_id)
        
        return {
            "success": True,
            "message": f"Incident Report {ir_number} deleted successfully",
            "ir_id": ir_id,
            "ticket_id": ticket_id
        }
        
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting IR: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete IR")