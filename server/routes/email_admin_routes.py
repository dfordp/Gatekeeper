# server/routes/email_admin_routes.py
"""Email administration routes - for managing templates and configuration"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from uuid import UUID

from middleware.auth_middleware import get_current_admin
from services.email_configuration_service import EmailConfigurationService
from services.email_queue_service import EmailQueueService
from services.email_listener_service import EmailListenerService
from utils.exceptions import ValidationError, NotFoundError
from core.logger import get_logger
from middleware.cache_decorator import invalidate_on_mutation, cache_endpoint

logger = get_logger(__name__)

router = APIRouter(prefix="/api/admin/email", tags=["Email Administration"])


# ==================== REQUEST/RESPONSE MODELS ====================

class EmailTemplateResponse(BaseModel):
    id: str
    event_type: str
    subject_template: str
    body_template: str
    description: Optional[str] = None
    is_active: bool


class EmailConfigurationResponse(BaseModel):
    id: str
    company_id: str
    enabled_events: List[str]
    recipient_overrides: Dict[str, Any]
    default_cc_list: List[str]
    default_bcc_list: List[str]
    email_from_name: Optional[str] = None
    rate_limit_per_hour: Optional[int] = None
    is_enabled: bool


class UpdateEmailConfigurationRequest(BaseModel):
    enabled_events: Optional[List[str]] = None
    recipient_overrides: Optional[Dict[str, Any]] = None
    default_cc_list: Optional[List[str]] = None
    default_bcc_list: Optional[List[str]] = None
    email_from_name: Optional[str] = None
    is_enabled: Optional[bool] = None


class TestEmailRequest(BaseModel):
    recipient_email: EmailStr
    event_type: str


class EmailLogResponse(BaseModel):
    id: str
    event_type: str
    recipient_email: str
    recipient_role: Optional[str] = None
    subject: str
    status: str
    error_message: Optional[str] = None
    retry_count: int
    sent_at: Optional[str] = None
    created_at: str


# ==================== ENDPOINTS ====================

@router.get("/templates")
@cache_endpoint(ttl=600, tag="email:templates", key_params=[])
async def get_all_templates(admin_payload: dict = Depends(get_current_admin)):
    """Get all email templates"""
    try:
        from core.database import SessionLocal, EmailTemplate
        
        db = SessionLocal()
        templates = db.query(EmailTemplate).filter(EmailTemplate.is_active == True).all()
        db.close()
        
        return {
            "templates": [
                {
                    "id": str(t.id),
                    "event_type": t.event_type,
                    "subject_template": t.subject_template,
                    "body_template": t.body_template,
                    "description": t.description,
                    "is_active": t.is_active
                }
                for t in templates
            ]
        }
    except Exception as e:
        logger.error(f"Error getting templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to get templates")


@router.get("/configuration/{company_id}")
@cache_endpoint(ttl=600, tag="email:config", key_params=["company_id"])
async def get_company_email_config(
    company_id: str,
    admin_payload: dict = Depends(get_current_admin)
):
    """Get email configuration for a company"""
    try:
        config = EmailConfigurationService.get_or_create_default_configuration(company_id)
        return config
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error getting configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to get configuration")


@router.put("/configuration/{company_id}")
@invalidate_on_mutation(tags=["email:config"])
async def update_company_email_config(
    company_id: str,
    request: UpdateEmailConfigurationRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """Update email configuration for a company"""
    try:
        config = EmailConfigurationService.update_configuration(
            company_id=company_id,
            enabled_events=request.enabled_events,
            recipient_overrides=request.recipient_overrides,
            default_cc_list=request.default_cc_list,
            default_bcc_list=request.default_bcc_list,
            email_from_name=request.email_from_name,
            is_enabled=request.is_enabled
        )
        return config
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error updating configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to update configuration")


@router.post("/test/{company_id}")
async def send_test_email(
    company_id: str,
    request: TestEmailRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """Send a test email to verify configuration"""
    try:
        # Check if event/template exists
        EmailConfigurationService.get_template(request.event_type)
        
        # Queue test email
        recipients = [{
            "email": request.recipient_email,
            "role": "admin",
            "user_id": admin_payload.get("sub")
        }]
        
        template_variables = {
            "user_name": admin_payload.get("email", "Admin"),
            "ticket_no": "TEST-000001",
            "ticket_subject": "This is a test email",
            "category": "Test",
            "level": "Level 3",
            "company_name": company_id,
            "ticket_url": "https://gatekeeper.example.com/tickets/TEST-000001",
            "portal_url": "https://gatekeeper.example.com",
            "new_status": "in_progress",
            "old_status": "open",
            "engineer_name": "Test Engineer",
            "user_email": request.recipient_email,
            "changes": "- Status: Open -> In Progress"
        }
        
        task_id = EmailQueueService.queue_email_task(
            email_type=f"test_{request.event_type}",
            event_type=request.event_type,
            company_id=company_id,
            recipient_list=recipients,
            template_variables=template_variables
        )
        
        if not task_id:
            raise HTTPException(status_code=500, detail="Failed to queue test email")
        
        return {
            "status": "success",
            "message": f"Test email queued to {request.recipient_email}",
            "task_id": task_id,
            "note": "Email should arrive in a few seconds"
        }
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error sending test email: {e}")
        raise HTTPException(status_code=500, detail="Failed to send test email")


@router.get("/logs/{company_id}")
@cache_endpoint(ttl=60, tag="email:logs", key_params=["company_id", "event_type", "status"])
async def get_email_logs(
    company_id: str,
    event_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ticket_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    admin_payload: dict = Depends(get_current_admin)
):
    """Get email logs with filtering"""
    try:
        logs = EmailQueueService.get_email_logs(
            company_id=company_id,
            event_type=event_type,
            status=status,
            ticket_id=ticket_id,
            limit=limit,
            offset=offset
        )
        return logs
    except Exception as e:
        logger.error(f"Error getting email logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to get email logs")


@router.get("/logs/{company_id}/stats")
@cache_endpoint(ttl=300, tag="email:logs", key_params=["company_id"])
async def get_email_statistics(
    company_id: str,
    admin_payload: dict = Depends(get_current_admin)
):
    """Get email statistics for company"""
    try:
        from core.database import SessionLocal, EmailLog
        from sqlalchemy import func
        
        db = SessionLocal()
        
        total_sent = db.query(func.count(EmailLog.id)).filter(
            EmailLog.company_id == UUID(company_id),
            EmailLog.status == "sent"
        ).scalar()
        
        total_failed = db.query(func.count(EmailLog.id)).filter(
            EmailLog.company_id == UUID(company_id),
            EmailLog.status == "failed"
        ).scalar()
        
        pending = db.query(func.count(EmailLog.id)).filter(
            EmailLog.company_id == UUID(company_id),
            EmailLog.status == "pending"
        ).scalar()
        
        by_event = db.query(
            EmailLog.event_type,
            func.count(EmailLog.id).label("count")
        ).filter(
            EmailLog.company_id == UUID(company_id)
        ).group_by(EmailLog.event_type).all()
        
        db.close()
        
        return {
            "total_sent": total_sent,
            "total_failed": total_failed,
            "pending": pending,
            "by_event_type": [
                {"event_type": row[0], "count": row[1]}
                for row in by_event
            ]
        }
    except Exception as e:
        logger.error(f"Error getting email statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")


@router.post("/retry-failed")
async def retry_failed_emails(
    company_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    admin_payload: dict = Depends(get_current_admin)
):
    """Retry failed emails"""
    try:
        stats = EmailQueueService.retry_failed_emails(limit=limit)
        return {
            "status": "success",
            "message": "Failed emails retry job completed",
            "statistics": stats
        }
    except Exception as e:
        logger.error(f"Error retrying failed emails: {e}")
        raise HTTPException(status_code=500, detail="Failed to retry emails")


@router.post("/initialize-templates")
async def initialize_default_templates(
    admin_payload: dict = Depends(get_current_admin)
):
    """Initialize default email templates (admin only)"""
    try:
        success = EmailConfigurationService.create_default_templates()
        if not success:
            raise HTTPException(status_code=500, detail="Failed to initialize templates")
        
        return {
            "status": "success",
            "message": "Default email templates initialized"
        }
    except Exception as e:
        logger.error(f"Error initializing templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize templates")
