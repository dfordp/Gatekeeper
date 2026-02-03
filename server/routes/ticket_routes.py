# server/routes/ticket_routes.py
"""
Ticket creation, management, and RCA routes with Phase 1 integration

Integrates:
- EmbeddingAPIClient for OpenAI embeddings
- AttachmentSummarizer for attachment analysis
- TicketRequestQueue for async task management
- Event emission for Qdrant sync
"""
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
import sys
import os

from middleware.auth_middleware import get_current_admin
from services.ticket_creation_service import TicketCreationService
from services.file_upload_service import FileUploadService
from services.ticket_request_queue import TicketRequestQueue
from utils.exceptions import ValidationError, NotFoundError, ConflictError
from core.logger import get_logger
from middleware.cache_decorator import cache_endpoint, invalidate_on_mutation

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
    rca_attachments: Optional[List[str]] = Field(None, description="File paths for RCA attachments")
    ticket_closed_at: Optional[str] = Field(None, description="Ticket closed date (ISO format)")


class AddResolutionNoteRequest(BaseModel):
    """Request model for adding resolution note"""
    solution_description: str = Field(..., min_length=10, description="Solution description")
    created_by_user_id: str = Field(..., description="User UUID creating note")
    steps_taken: Optional[List[str]] = Field(None, description="Steps taken")
    resources_used: Optional[List[str]] = Field(None, description="Resources used")
    follow_up_notes: Optional[str] = Field(None, description="Follow-up notes")


class UpdateTicketRequest(BaseModel):
    """Request model for updating a ticket"""
    subject: Optional[str] = Field(None, min_length=3, description="Ticket subject")
    summary: Optional[str] = Field(None, description="Optional summary")
    detailed_description: Optional[str] = Field(None, min_length=10, description="Full description")
    category: Optional[str] = Field(None, description="Ticket category")
    level: Optional[str] = Field(None, description="Priority level (level-1, level-2, level-3)")
    created_at: Optional[str] = Field(None, description="ISO format creation date")  # ADD THIS


# ==================== ENDPOINTS ====================

@router.post("/create")
@invalidate_on_mutation(tags=["ticket:list", "analytics", "search:*"])
async def create_ticket(
    request: CreateTicketRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """
    Create a new ticket with optional older ticket support.
    
    Integrates Phase 1:
    - Queues embedding creation task
    - Returns async task tracking URLs
    
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
        
        # Create ticket (synchronous)
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
        
        # Get ticket async task status (Phase 1)
        try:
            ticket_status = TicketRequestQueue.get_ticket_status(result["id"])
            result["creation_status"] = "success"
            result["async_tasks"] = {
                "task_summary": ticket_status.get("task_breakdown", {}),
                "polling_url": f"/api/tickets/creation-status/{result['id']}",
                "in_progress": ticket_status.get("in_progress_tasks", 0) > 0
            }
        except Exception as e:
            logger.warning(f"Failed to get ticket status: {e}")
            result["async_tasks"] = {"error": "Failed to track async tasks"}
        
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


@router.get("/creation-status/{ticket_id}")
@cache_endpoint(ttl=10, tag="ticket:status", key_params=["ticket_id"])
async def get_ticket_creation_status(ticket_id: str):
    """
    Get the creation status of a ticket, including all async tasks (Phase 1)
    
    Returns comprehensive status of all async operations for the ticket.
    
    Response:
    {
        "ticket_id": "uuid",
        "overall_status": "pending|processing|completed|error",
        "task_breakdown": {
            "pending": 0,
            "processing": 1,
            "completed": 2,
            "failed": 0,
            "skipped": 0,
            "retrying": 0
        },
        "tasks": {
            "task_id_1": {
                "task_id": "...",
                "task_type": "attachment_processing|embedding_creation|rca_creation",
                "status": "completed|pending|processing|failed",
                "retry_count": 0,
                "error_message": null,
                "created_at": "...",
                "completed_at": "..."
            },
            ...
        },
        "total_tasks": 3,
        "completed_tasks": 2,
        "failed_tasks": 0,
        "in_progress_tasks": 1
    }
    """
    try:
        status = TicketRequestQueue.get_ticket_status(ticket_id)
        return status
    except Exception as e:
        logger.error(f"Error getting ticket creation status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get ticket status")


@router.get("/queue-status/{task_id}")
@cache_endpoint(ttl=10, tag="queue:status", key_params=["task_id"])
async def get_queue_task_status(task_id: str):
    """
    Get status of a specific queued task (Phase 1)
    
    Returns detailed status of an individual async task.
    
    Response:
    {
        "task_id": "uuid",
        "ticket_id": "uuid",
        "task_type": "attachment_processing|embedding_creation|rca_creation|qdrant_sync",
        "status": "pending|processing|completed|failed|skipped|retrying",
        "retry_count": 0,
        "max_retries": 3,
        "error_message": null,
        "created_at": "2026-02-02T...",
        "started_at": null,
        "completed_at": null
    }
    """
    try:
        task_status = TicketRequestQueue.get_task_status(task_id)
        if not task_status:
            raise HTTPException(status_code=404, detail="Task not found")
        return task_status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get task status")


@router.get("/queue/stats")
@cache_endpoint(ttl=30, tag="queue:stats", key_params=[])
async def get_queue_statistics():
    """
    Get overall queue statistics (Phase 1)
    
    Returns system-wide async queue statistics.
    
    Response:
    {
        "total_tasks": 42,
        "status_breakdown": {
            "pending": 5,
            "processing": 3,
            "completed": 30,
            "failed": 2,
            "skipped": 2,
            "retrying": 0
        },
        "type_breakdown": {
            "attachment_processing": 10,
            "embedding_creation": 15,
            "rca_creation": 8,
            "qdrant_sync": 9
        },
        "queue_capacity_used": "4.2%"
    }
    """
    try:
        stats = TicketRequestQueue.get_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting queue stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get queue statistics")


@router.post("/{ticket_id}/upload-attachment")
async def upload_attachment(
    ticket_id: str,
    file: UploadFile = File(...)
):
    """
    Upload attachment file to ticket with Phase 1 integration.
    
    Workflow:
    1. Save file locally
    2. Upload to Cloudinary
    3. Delete from local storage
    4. Queue attachment processing task (summarization + embedding)
    5. Store attachment metadata
    
    File is saved locally, uploaded to Cloudinary, then deleted from local storage.
    """
    try:
        from core.database import SessionLocal, Ticket
        from uuid import UUID
        
        # Verify ticket exists first
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
        finally:
            db.close()
        
        # Read file content
        content = await file.read()
        
        # Process file (save → upload to Cloudinary → delete local)
        result = FileUploadService.process_file_upload(content, file.filename)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=f"Upload failed: {result.get('error')}")
        
        # Extract URLs - prefer Cloudinary, fallback to local path
        cloudinary_url = result.get("cloudinary_url")
        local_path = result.get("file_path")
        
        # Use Cloudinary URL if available, otherwise use local path
        # If neither exists, something went wrong
        if not cloudinary_url and not local_path:
            raise HTTPException(status_code=500, detail="No file URL available after upload")
        
        storage_path = cloudinary_url if cloudinary_url else local_path
        
        logger.info(f"Attachment upload - cloudinary: {cloudinary_url}, local: {local_path}, using: {storage_path}")
        
        # Create attachment record with Phase 1 integration
        attachment_result = TicketCreationService.add_attachment(
            ticket_id=ticket_id,
            file_path=cloudinary_url,  # Store the URL we'll use for retrieval
            file_name=result.get("file_name"),
            attachment_type="document",
            mime_type=file.content_type,
            file_size=result.get("file_size"),
            cloudinary_url=cloudinary_url,  # Store separately for reference
            created_by_user_id=None,
            admin_id=None
        )
        
        return attachment_result
        
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error uploading attachment: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload attachment: {str(e)}")


@router.post("/{ticket_id}/attachments")
async def add_attachment(
    ticket_id: str,
    request: AddAttachmentRequest
):
    """
    Add attachment to ticket with Phase 1 integration.
    
    Queues:
    - Attachment summarization task (Grok Vision for images, PDF extraction, etc.)
    - Embedding creation task for attachment content
    
    Add attachment to ticket
    """
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
            admin_id=None
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
@invalidate_on_mutation(tags=["ticket:rca", "ticket:detail", "search:*"])
async def add_rca(
    ticket_id: str,
    request: AddRCARequest
):
    """
    Add Root Cause Analysis to ticket.
    
    Service handles:
    - RCA creation and persistence
    - Embedding generation
    - Task queue management
    """
    try:
        logger.info(f"RCA endpoint called: ticket_id={ticket_id}")
        logger.info(f"RCA request data: {request.dict()}")
        
        result = TicketCreationService.add_root_cause_analysis(
            ticket_id=ticket_id,
            root_cause_description=request.root_cause_description,
            created_by_user_id=request.created_by_user_id,
            contributing_factors=request.contributing_factors,
            prevention_measures=request.prevention_measures,
            resolution_steps=request.resolution_steps,
            rca_attachments=request.rca_attachments,
            related_ticket_ids=request.related_ticket_ids,
            ticket_closed_at=request.ticket_closed_at,
            admin_id=None
        )
        
        # Service already queued and completed RCA task - don't queue again!
        logger.info(f"✓ RCA endpoint success: {result}")
        return result
        
    except ValidationError as e:
        logger.error(f"ValidationError in RCA: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except NotFoundError as e:
        logger.error(f"NotFoundError in RCA: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in RCA: {e}")
        raise HTTPException(status_code=500, detail="Failed to add RCA")


@router.post("/{ticket_id}/resolution")
@invalidate_on_mutation(tags=["ticket:detail", "analytics"])
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


@router.delete("/{ticket_id}")
@invalidate_on_mutation(tags=["ticket:detail", "ticket:list", "search:*", "analytics"])
async def delete_ticket(
    ticket_id: str,
    admin_payload: dict = Depends(get_current_admin)
):
    """Delete a ticket"""
    try:
        result = TicketCreationService.delete_ticket(
            ticket_id=ticket_id,
            admin_id=admin_payload.get("id")
        )
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting ticket: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete ticket")


@router.put("/{ticket_id}")
@invalidate_on_mutation(tags=["ticket:detail", "ticket:list", "analytics"])  # Add analytics to invalidation
async def update_ticket(
    ticket_id: str,
    request: UpdateTicketRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """Update ticket details"""
    try:
        # Parse created_at if provided
        update_data = request.dict(exclude_unset=True)
        created_at = None
        if "created_at" in update_data and update_data["created_at"]:
            created_at = datetime.fromisoformat(
                update_data["created_at"].replace('Z', '+00:00')
            )
        
        result = TicketCreationService.update_ticket(
            ticket_id=ticket_id,
            subject=request.subject,
            summary=request.summary,
            detailed_description=request.detailed_description,
            category=request.category,
            level=request.level,
            created_at=created_at,  # ADD THIS LINE
            admin_id=admin_payload.get("id"),
        )
        return result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating ticket: {e}")
        raise HTTPException(status_code=500, detail="Failed to update ticket")


@router.get("/{ticket_id}/attachments/{attachment_id}/download")
@cache_endpoint(ttl=600, tag="attachment:download", key_params=["attachment_id"])
async def download_attachment(
    ticket_id: str,
    attachment_id: str
):
    """Download attachment file - supports local files and Cloudinary URLs"""
    try:
        from core.database import SessionLocal, Attachment, Ticket
        from uuid import UUID
        import os
        from fastapi.responses import FileResponse, RedirectResponse
        
        db = SessionLocal()
        
        try:
            # Verify ticket exists
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            # Get attachment
            attachment = db.query(Attachment).filter(
                Attachment.id == UUID(attachment_id),
                Attachment.ticket_id == UUID(ticket_id)
            ).first()
            
            if not attachment:
                raise NotFoundError("Attachment not found")
            
            file_path = attachment.file_path
            
            # If it's a Cloudinary URL or other remote URL, redirect to it
            if file_path.startswith('http'):
                return RedirectResponse(url=file_path, status_code=307)
            
            # If it's a local file
            if os.path.exists(file_path):
                return FileResponse(
                    path=file_path,
                    filename=file_path.split(os.sep)[-1] or file_path.split('/')[-1],
                    media_type=attachment.mime_type or 'application/octet-stream'
                )
            
            # If neither remote nor local exists
            raise NotFoundError("File not found")
            
        finally:
            db.close()
            
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error downloading attachment: {e}")
        raise HTTPException(status_code=500, detail="Failed to download attachment")


@router.delete("/{ticket_id}/attachments/{attachment_id}")
@invalidate_on_mutation(tags=["ticket:detail", "search:*"])
async def delete_attachment(
    ticket_id: str,
    attachment_id: str
):
    """Delete attachment from ticket"""
    try:
        logger.info(f"Delete request: ticket_id={ticket_id}, attachment_id={attachment_id}")
        result = TicketCreationService.delete_attachment(
            ticket_id=ticket_id,
            attachment_id=attachment_id
        )
        logger.info(f"✓ Delete successful: {result}")
        return result
    except NotFoundError as e:
        logger.warning(f"NotFound: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        logger.warning(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting attachment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete attachment: {str(e)}")

@router.post("/{ticket_id}/upload-rca-attachment")
async def upload_rca_attachment(
    ticket_id: str,
    file: UploadFile = File(...)
):
    """
    Upload RCA-specific attachment file.
    
    Workflow:
    1. Save file locally
    2. Upload to Cloudinary
    3. Delete from local storage
    4. Return file path for RCA creation
    
    Note: RCA attachments are processed when RCA is created/updated,
    not immediately upon upload.
    """
    try:
        from core.database import SessionLocal, Ticket
        from uuid import UUID
        
        # Verify ticket exists first
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
        finally:
            db.close()
        
        # Read file content
        content = await file.read()
        
        # Process file (save → upload to Cloudinary → delete local)
        result = FileUploadService.process_file_upload(content, file.filename)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=f"Upload failed: {result.get('error')}")
        
        # Extract URLs - prefer Cloudinary, fallback to local path
        cloudinary_url = result.get("cloudinary_url")
        local_path = result.get("file_path")
        
        # Use Cloudinary URL if available, otherwise use local path
        storage_path = cloudinary_url if cloudinary_url else local_path
        
        if not storage_path:
            raise HTTPException(status_code=500, detail="No file URL available after upload")
        
        logger.info(f"RCA attachment upload - using: {storage_path}")
        
        # Return the file path to be used when creating/updating RCA
        return {
            "success": True,
            "file_path": storage_path,
            "file_name": result.get("file_name"),
            "file_size": result.get("file_size"),
            "mime_type": file.content_type
        }
        
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error uploading RCA attachment: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload RCA attachment: {str(e)}")

@router.delete("/{ticket_id}/rca-attachments/{attachment_id}")
@invalidate_on_mutation(tags=["ticket:rca", "search:*"])
async def delete_rca_attachment(
    ticket_id: str,
    attachment_id: str,
    admin_payload: dict = Depends(get_current_admin)
):
    """Delete RCA attachment and its embeddings"""
    try:
        from core.database import SessionLocal, RCAAttachment, Ticket, Embedding
        from uuid import UUID
        
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            attachment_uuid = UUID(attachment_id)
            
            # Verify ticket exists
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise HTTPException(status_code=404, detail="Ticket not found")
            
            # Get RCA attachment
            rca_attachment = db.query(RCAAttachment).filter(
                RCAAttachment.id == attachment_uuid
            ).first()
            
            if not rca_attachment:
                raise HTTPException(status_code=404, detail="RCA attachment not found")
            
            logger.info(f"Deleting RCA attachment {attachment_id}")
            
            # Deprecate all embeddings linked to this RCA attachment
            try:
                embeddings = db.query(Embedding).filter(
                    Embedding.rca_attachment_id == attachment_uuid
                ).all()
                
                if embeddings:
                    logger.info(f"Deprecating {len(embeddings)} embeddings for RCA attachment {attachment_id}")
                    for embedding in embeddings:
                        embedding.is_deprecated = True
                    db.flush()
                    logger.info(f"✓ Deprecated {len(embeddings)} embeddings")
            except Exception as e:
                logger.warning(f"Failed to deprecate embeddings: {e}")
            
            # Delete from Cloudinary if applicable
            if rca_attachment.file_path and rca_attachment.file_path.startswith("http"):
                try:
                    import cloudinary
                    import cloudinary.uploader
                    from core.config import CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
                    
                    if all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
                        cloudinary.config(
                            cloud_name=CLOUDINARY_CLOUD_NAME,
                            api_key=CLOUDINARY_API_KEY,
                            api_secret=CLOUDINARY_API_SECRET
                        )
                        public_id = rca_attachment.file_path.split('/')[-1].split('.')[0]
                        cloudinary.uploader.destroy(f"tickets/{public_id}")
                        logger.info(f"✓ Deleted from Cloudinary: {public_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete from Cloudinary: {e}")
            
            # Delete from database
            db.delete(rca_attachment)
            db.commit()
            
            logger.info(f"✓ RCA attachment deleted: {attachment_id}")
            
            return {
                "success": True,
                "message": "RCA attachment deleted successfully",
                "attachment_id": attachment_id
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting RCA attachment: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete RCA attachment: {str(e)}")