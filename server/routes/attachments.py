# server/routes/attachments.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from uuid import UUID
from pathlib import Path
import os
from schemas.attachment import AttachmentResponse
from schemas.common import APIResponse
from services.attachment_service import AttachmentService
from services.rbac_service import RBACService, Permission
from utils.database import get_db
from dependencies import get_current_user_id, get_current_company_id, get_current_role
from utils.errors import CompanyIsolationError, NotFoundError
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# File storage configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

@router.post("/{company_id}/tickets/{ticket_id}/attachments")
async def upload_attachment(
    company_id: UUID,
    ticket_id: UUID,
    file: UploadFile = File(...),
    attachment_type: str = Form(default="document"),
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse[AttachmentResponse]:
    """Upload attachment."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.ATTACHMENT_UPLOAD)
    
    try:
        # Validate file size
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File too large (max {MAX_FILE_SIZE} bytes)")
        
        # Create directory for company/ticket
        ticket_dir = UPLOAD_DIR / str(company_id) / str(ticket_id)
        ticket_dir.mkdir(parents=True, exist_ok=True)
        
        # Save file
        file_path = ticket_dir / file.filename
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Create attachment record
        attachment = AttachmentService.upload_attachment(
            db,
            company_id=company_id,
            ticket_id=ticket_id,
            user_id=current_user_id,
            file_name=file.filename,
            file_size=len(contents),
            mime_type=file.content_type or "application/octet-stream",
            file_path=str(file_path),
            attachment_type=attachment_type,
        )
        db.commit()
        
        return APIResponse(
            success=True,
            data=AttachmentResponse.from_orm(attachment),
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error uploading attachment: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{company_id}/tickets/{ticket_id}/attachments")
async def list_attachments(
    company_id: UUID,
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse:
    """List attachments for ticket."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.ATTACHMENT_UPLOAD)
    
    try:
        attachments = AttachmentService.list_attachments(
            db,
            company_id=company_id,
            ticket_id=ticket_id,
        )
        
        return APIResponse(
            success=True,
            data=[AttachmentResponse.from_orm(a) for a in attachments],
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        logger.error(f"Error listing attachments: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{company_id}/attachments/{attachment_id}/deprecate")
async def deprecate_attachment(
    company_id: UUID,
    attachment_id: UUID,
    reason: str,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
    current_company_id: UUID = Depends(get_current_company_id),
    current_role: str = Depends(get_current_role),
) -> APIResponse[AttachmentResponse]:
    """Deprecate attachment."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    RBACService.require_permission(current_role, Permission.ATTACHMENT_DEPRECATE)
    
    try:
        attachment = AttachmentService.deprecate_attachment(
            db,
            company_id=company_id,
            attachment_id=attachment_id,
            user_id=current_user_id,
            reason=reason,
        )
        db.commit()
        
        return APIResponse(
            success=True,
            data=AttachmentResponse.from_orm(attachment),
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error deprecating attachment: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{company_id}/attachments/{attachment_id}/download")
async def download_attachment(
    company_id: UUID,
    attachment_id: UUID,
    db: Session = Depends(get_db),
    current_company_id: UUID = Depends(get_current_company_id),
) -> None:
    """Download attachment file."""
    
    if company_id != current_company_id:
        raise CompanyIsolationError()
    
    try:
        attachment = AttachmentService.get_attachment(db, company_id, attachment_id)
        if not attachment:
            raise NotFoundError("Attachment")
        
        file_path = Path(attachment.file_path)
        if not file_path.exists():
            raise NotFoundError("File")
        
        # Return file via FileResponse
        from fastapi.responses import FileResponse
        return FileResponse(
            path=file_path,
            filename=attachment.file_name,
            media_type=attachment.mime_type
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading attachment: {e}")
        raise HTTPException(status_code=400, detail=str(e))