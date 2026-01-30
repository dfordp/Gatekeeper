# server/routes/ticket_routes.py
"""Ticket creation, management, and RCA routes"""
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

from middleware.auth_middleware import get_current_admin
from services.ticket_creation_service import TicketCreationService
from services.file_upload_service import FileUploadService
from utils.exceptions import ValidationError, NotFoundError, ConflictError
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/tickets", tags=["Tickets"])


# ==================== REQUEST MODELS ====================

class CreateTicketRequest(BaseModel):
    """Request model for creating a new ticket"""
    subject: str = Field(..., min_length=3, description="Ticket subject")
    detailed_description: str = Field(..., min_length=10, description="Full description")
    company_id: str = Field(..., description="Company UUID")
    raised_by_user_id: str = Field(..., description="User UUID who raised ticket")
    summary: Optional[str] = Field(None, description="Optional summary")
    category: Optional[str] = Field(None, description="Ticket category")
    level: Optional[str] = Field(None, description="Priority level (level-1, level-2, level-3)")
    assigned_engineer_id: Optional[str] = Field(None, description="Engineer UUID to assign")
    created_at: Optional[str] = Field(None, description="ISO format date for older tickets")
    ticket_no: Optional[str] = Field(None, description="Custom ticket number (auto-generated if not provided)")
    status: Optional[str] = Field(None, description="Initial status (open, in_progress, resolved, closed, reopened)")


class AddAttachmentRequest(BaseModel):
    """Request model for adding attachment"""
    file_path: str = Field(..., description="File path or URL")
    file_name: str = Field(..., description="Original file name")
    attachment_type: str = Field(..., description="Type: image, document, log, code, other")
    mime_type: Optional[str] = Field(None, description="MIME type")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    cloudinary_url: Optional[str] = Field(None, description="Cloudinary URL")
    created_by_user_id: Optional[str] = Field(None, description="User adding attachment")


class AddRCARequest(BaseModel):
    """Request model for adding Root Cause Analysis"""
    root_cause_description: str = Field(..., min_length=10, description="Root cause description")
    created_by_user_id: str = Field(..., description="User UUID creating RCA")
    contributing_factors: Optional[List[str]] = Field(None, description="List of factors")
    prevention_measures: Optional[str] = Field(None, description="Prevention measures")
    resolution_steps: Optional[List[str]] = Field(None, description="Steps taken")
    related_ticket_ids: Optional[List[str]] = Field(None, description="Related ticket UUIDs")


class AddResolutionNoteRequest(BaseModel):
    """Request model for adding resolution note"""
    solution_description: str = Field(..., min_length=10, description="Solution description")
    created_by_user_id: str = Field(..., description="User UUID creating note")
    steps_taken: Optional[List[str]] = Field(None, description="Steps taken")
    resources_used: Optional[List[str]] = Field(None, description="Resources used")
    follow_up_notes: Optional[str] = Field(None, description="Follow-up notes")


# ==================== ENDPOINTS ====================

@router.post("/create")
async def create_ticket(
    request: CreateTicketRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """
    Create a new ticket with optional older ticket support.
    
    Supports:
    - New tickets (automatic timestamp)
    - Older tickets (custom created_at date)
    - Category and priority levels
    - Optional engineer assignment
    """
    try:
        created_at = None
        if request.created_at:
            created_at = datetime.fromisoformat(request.created_at.replace("Z", "+00:00"))
        
        result = TicketCreationService.create_ticket(
            subject=request.subject,
            detailed_description=request.detailed_description,
            company_id=request.company_id,
            raised_by_user_id=request.raised_by_user_id,
            summary=request.summary,
            category=request.category,
            level=request.level,
            assigned_engineer_id=request.assigned_engineer_id,
            created_at=created_at,
            created_by_admin_id=admin_payload.get("id"),
            ticket_no=request.ticket_no,
            status=request.status
        )
        return result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating ticket: {e}")
        raise HTTPException(status_code=500, detail="Failed to create ticket")


@router.post("/{ticket_id}/upload-attachment")
async def upload_attachment(
    ticket_id: str,
    file: UploadFile = File(...),
    admin_payload: dict = Depends(get_current_admin)
):
    """
    Upload attachment file to ticket.
    File is saved locally, uploaded to Cloudinary, then deleted from local storage.
    """
    try:
        # Read file content
        content = await file.read()
        
        # Process file (save → upload to Cloudinary → delete local)
        result = FileUploadService.process_file_upload(content, file.filename)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=f"Upload failed: {result.get('error')}")
        
        # Now create attachment record with Cloudinary URL
        attachment_result = TicketCreationService.add_attachment(
            ticket_id=ticket_id,
            file_path=result.get("file_path"),
            file_name=result.get("file_name"),
            attachment_type="document",  # Can be determined by MIME type
            mime_type=file.content_type,
            file_size=result.get("file_size"),
            cloudinary_url=result.get("cloudinary_url"),
            created_by_user_id=admin_payload.get("id"),
            admin_id=admin_payload.get("id")
        )
        
        return attachment_result
        
    except Exception as e:
        logger.error(f"Error uploading attachment: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload attachment")


@router.post("/{ticket_id}/attachments")
async def add_attachment(
    ticket_id: str,
    request: AddAttachmentRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """Add attachment to ticket"""
    try:
        result = TicketCreationService.add_attachment(
            ticket_id=ticket_id,
            file_path=request.file_path,
            file_name=request.file_name,
            attachment_type=request.attachment_type,
            mime_type=request.mime_type,
            file_size=request.file_size,
            cloudinary_url=request.cloudinary_url,
            created_by_user_id=request.created_by_user_id,
            admin_id=admin_payload.get("sub")
        )
        return result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding attachment: {e}")
        raise HTTPException(status_code=500, detail="Failed to add attachment")


@router.post("/{ticket_id}/rca")
async def add_rca(
    ticket_id: str,
    request: AddRCARequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """Add Root Cause Analysis to ticket"""
    try:
        result = TicketCreationService.add_root_cause_analysis(
            ticket_id=ticket_id,
            root_cause_description=request.root_cause_description,
            created_by_user_id=request.created_by_user_id,
            contributing_factors=request.contributing_factors,
            prevention_measures=request.prevention_measures,
            resolution_steps=request.resolution_steps,
            related_ticket_ids=request.related_ticket_ids,
            admin_id=admin_payload.get("sub")
        )
        return result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding RCA: {e}")
        raise HTTPException(status_code=500, detail="Failed to add RCA")


@router.post("/{ticket_id}/resolution")
async def add_resolution_note(
    ticket_id: str,
    request: AddResolutionNoteRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """Add resolution note to ticket"""
    try:
        result = TicketCreationService.add_resolution_note(
            ticket_id=ticket_id,
            solution_description=request.solution_description,
            created_by_user_id=request.created_by_user_id,
            steps_taken=request.steps_taken,
            resources_used=request.resources_used,
            follow_up_notes=request.follow_up_notes,
            admin_id=admin_payload.get("sub")
        )
        return result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding resolution note: {e}")
        raise HTTPException(status_code=500, detail="Failed to add resolution note")