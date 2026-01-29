# server/routes/rca.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from schemas.rca import (
    RCAResponse, CreateRCARequest, SubmitRCARequest, ApproveRCARequest
)
from schemas.common import APIResponse
from services.rca_service import RCAService
from services.rbac_service import RBACService, Permission
from utils.database import get_db
from dependencies import get_current_user_id, get_current_company_id, get_current_role
from utils.errors import CompanyIsolationError, NotFoundError, RCANotInDraftError, DuplicateRCAError
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/{company_id}/tickets/{ticket_id}/rca")
async def get_rca(
    company_id: UUID,
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse:
    """Get RCA for ticket."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.RCA_CREATE)
    
    try:
        rca = RCAService.get_rca(db, company_id, ticket_id)
        if not rca:
            raise NotFoundError("RCA")
        
        return APIResponse(
            success=True,
            data=RCAResponse.from_orm(rca),
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting RCA: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{company_id}/tickets/{ticket_id}/rca")
async def create_rca(
    company_id: UUID,
    ticket_id: UUID,
    request: CreateRCARequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse[RCAResponse]:
    """Create RCA for ticket."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.RCA_CREATE)
    
    try:
        rca = RCAService.create_rca(
            db,
            company_id=company_id,
            ticket_id=ticket_id,
            user_id=current_user_id,
            request=request,
        )
        db.commit()
        
        return APIResponse(
            success=True,
            data=RCAResponse.from_orm(rca),
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except DuplicateRCAError:
        raise HTTPException(status_code=400, detail="RCA already exists for this ticket")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating RCA: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{company_id}/rca/{rca_id}")
async def update_rca(
    company_id: UUID,
    rca_id: UUID,
    request: CreateRCARequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse[RCAResponse]:
    """Update RCA (draft only)."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.RCA_EDIT)
    
    try:
        rca = RCAService.update_rca(
            db,
            company_id=company_id,
            rca_id=rca_id,
            user_id=current_user_id,
            request=request,
        )
        db.commit()
        
        return APIResponse(
            success=True,
            data=RCAResponse.from_orm(rca),
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except RCANotInDraftError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating RCA: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{company_id}/rca/{rca_id}/submit")
async def submit_rca(
    company_id: UUID,
    rca_id: UUID,
    request: SubmitRCARequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse[RCAResponse]:
    """Submit RCA for approval."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.RCA_SUBMIT)
    
    try:
        rca = RCAService.submit_rca(
            db,
            company_id=company_id,
            rca_id=rca_id,
            user_id=current_user_id,
            request=request,
        )
        db.commit()
        
        return APIResponse(
            success=True,
            data=RCAResponse.from_orm(rca),
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error submitting RCA: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{company_id}/rca/{rca_id}/approve")
async def approve_rca(
    company_id: UUID,
    rca_id: UUID,
    request: ApproveRCARequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse[RCAResponse]:
    """Approve RCA."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.RCA_APPROVE)
    
    try:
        rca = RCAService.approve_rca(
            db,
            company_id=company_id,
            rca_id=rca_id,
            approver_user_id=current_user_id,
            request=request,
        )
        db.commit()
        
        return APIResponse(
            success=True,
            data=RCAResponse.from_orm(rca),
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error approving RCA: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{company_id}/rca/{rca_id}/reject")
async def reject_rca(
    company_id: UUID,
    rca_id: UUID,
    reason: str,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse[RCAResponse]:
    """Reject RCA (back to draft)."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.RCA_APPROVE)
    
    try:
        rca = RCAService.reject_rca(
            db,
            company_id=company_id,
            rca_id=rca_id,
            approver_user_id=current_user_id,
            reason=reason,
        )
        db.commit()
        
        return APIResponse(
            success=True,
            data=RCAResponse.from_orm(rca),
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error rejecting RCA: {e}")
        raise HTTPException(status_code=400, detail=str(e))