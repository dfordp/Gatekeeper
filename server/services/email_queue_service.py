# server/services/email_queue_service.py
"""Email queue service - handles async email sending with retry logic"""
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from uuid import UUID
from jinja2 import Template, TemplateError

from core.database import SessionLocal, EmailLog, EmailTemplate
from services.ticket_request_queue import TicketRequestQueue, TaskType, TaskStatus
from services.email_service import send_zoho_email
from utils.exceptions import ValidationError
from core.logger import get_logger
from utils.datetime_utils import to_iso_date

logger = get_logger(__name__)


class EmailQueueService:
    """Service for queuing and processing email tasks"""
    
    @staticmethod
    def queue_email_task(
        email_type: str,
        event_type: str,
        company_id: str,
        recipient_list: List[Dict[str, str]],
        template_variables: Dict[str, Any],
        ticket_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Queue an email task for async sending.
        
        Args:
            email_type: Type of email (ticket_created, user_welcome, etc.)
            event_type: Event that triggered this email
            company_id: Company UUID
            recipient_list: List of {email, role, user_id} dicts
            template_variables: Variables to inject into template
            ticket_id: Related ticket UUID (if applicable)
            user_id: Related user UUID (if applicable)
            
        Returns:
            Task ID of queued email task
        """
        try:
            if not recipient_list:
                logger.warning(f"No recipients for {email_type} email")
                return None
            
            payload = {
                "email_type": email_type,
                "event_type": event_type,
                "company_id": company_id,
                "recipient_list": recipient_list,
                "template_variables": template_variables,
                "ticket_id": ticket_id,
                "user_id": user_id,
                "queued_at": to_iso_date(datetime.utcnow())
            }
            
            # Queue task for each recipient separately for independent tracking
            task_ids = []
            for recipient in recipient_list:
                recipient_payload = payload.copy()
                recipient_payload["recipient"] = recipient
                recipient_payload["recipient_email"] = recipient["email"]
                recipient_payload["recipient_role"] = recipient.get("role")
                
                task_id = TicketRequestQueue.queue_task(
                    ticket_id=ticket_id or "global",
                    task_type=TaskType.EMAIL_SEND,
                    payload=recipient_payload
                )
                
                if task_id:
                    task_ids.append(task_id)
                    logger.info(f"✓ Email task queued ({task_id}) for {recipient['email']}")
            
            return task_ids[0] if task_ids else None
            
        except Exception as e:
            logger.error(f"Failed to queue email task: {e}")
            return None
    
    @staticmethod
    def process_email_task(task_id: str, payload: Dict[str, Any]) -> bool:
        """
        Process a queued email task.
        
        Args:
            task_id: Task ID from queue
            payload: Task payload with email details
            
        Returns:
            True if email sent successfully
        """
        db = SessionLocal()
        try:
            email_type = payload.get("email_type")
            event_type = payload.get("event_type")
            company_id = payload.get("company_id")
            recipient = payload.get("recipient", {})
            recipient_email = recipient.get("email") or payload.get("recipient_email")
            recipient_role = recipient.get("role") or payload.get("recipient_role")
            ticket_id = payload.get("ticket_id")
            user_id = payload.get("user_id")
            template_variables = payload.get("template_variables", {})
            
            if not recipient_email:
                raise ValidationError("No recipient email in payload")
            
            logger.info(f"Processing email task {task_id} for {recipient_email}")
            
            # Get email template
            template = db.query(EmailTemplate).filter(
                EmailTemplate.event_type == event_type,
                EmailTemplate.is_active == True
            ).first()
            
            if not template:
                raise ValidationError(f"Email template not found for event: {event_type}")
            
            # Render subject and body
            subject = EmailQueueService._render_template(
                template.subject_template,
                template_variables
            )
            body = EmailQueueService._render_template(
                template.body_template,
                template_variables,
                is_html=True
            )
            
            # Create email log entry
            email_log = EmailLog(
                company_id=UUID(company_id),
                event_type=event_type,
                ticket_id=UUID(ticket_id) if ticket_id and ticket_id != "global" else None,
                user_id=UUID(user_id) if user_id else None,
                recipient_email=recipient_email,
                recipient_role=recipient_role,
                subject=subject,
                status="pending"
            )
            db.add(email_log)
            db.flush()
            email_log_id = str(email_log.id)
            db.commit()
            
            # Send email via Zoho
            result = send_zoho_email(
                to_email=recipient_email,
                subject=subject,
                body=body
            )
            
            # Update log
            db.begin()
            email_log = db.query(EmailLog).filter(EmailLog.id == UUID(email_log_id)).first()
            
            if "error" in result:
                email_log.status = "failed"
                email_log.error_message = result.get("error", "Unknown error")
                logger.error(f"Failed to send email to {recipient_email}: {result['error']}")
            else:
                email_log.status = "sent"
                email_log.zoho_message_id = result.get("data", {}).get("message_id")
                email_log.sent_at = datetime.utcnow()
                logger.info(f"✓ Email sent successfully to {recipient_email}")
            
            email_log.updated_at = datetime.utcnow()
            db.commit()
            
            return email_log.status == "sent"
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error processing email task {task_id}: {e}")
            
            # Log the failure
            try:
                email_log = EmailLog(
                    company_id=UUID(payload.get("company_id")) if payload.get("company_id") else None,
                    event_type=payload.get("event_type"),
                    ticket_id=UUID(payload.get("ticket_id")) if payload.get("ticket_id") and payload.get("ticket_id") != "global" else None,
                    user_id=UUID(payload.get("user_id")) if payload.get("user_id") else None,
                    recipient_email=payload.get("recipient_email", "unknown"),
                    recipient_role=payload.get("recipient_role"),
                    subject="[ERROR]",
                    status="failed",
                    error_message=str(e)
                )
                db_log = SessionLocal()
                db_log.add(email_log)
                db_log.commit()
                db_log.close()
            except:
                pass
            
            return False
        finally:
            db.close()
    
    @staticmethod
    def retry_failed_emails(max_age_hours: int = 24, limit: int = 100) -> Dict[str, Any]:
        """
        Retry failed emails that haven't exceeded max retry attempts.
        
        Args:
            max_age_hours: Only retry emails created within last N hours
            limit: Maximum number of emails to retry
            
        Returns:
            Dict with retry statistics
        """
        db = SessionLocal()
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
            
            failed_logs = db.query(EmailLog).filter(
                EmailLog.status == "failed",
                EmailLog.retry_count < EmailLog.max_retries,
                EmailLog.created_at >= cutoff_time
            ).limit(limit).all()
            
            stats = {
                "total_retried": 0,
                "successful": 0,
                "still_failed": 0,
                "errors": []
            }
            
            for email_log in failed_logs:
                try:
                    # Reconstruct payload from email log
                    payload = {
                        "company_id": str(email_log.company_id),
                        "event_type": email_log.event_type,
                        "recipient_email": email_log.recipient_email,
                        "recipient_role": email_log.recipient_role,
                        "ticket_id": str(email_log.ticket_id) if email_log.ticket_id else None,
                        "user_id": str(email_log.user_id) if email_log.user_id else None,
                        "template_variables": {}  # Note: original variables are lost; this is limitation
                    }
                    
                    # Attempt to resend
                    result = send_zoho_email(
                        to_email=email_log.recipient_email,
                        subject=email_log.subject,
                        body="[Retry] " + "Email retry - original content not available"
                    )
                    
                    email_log.retry_count += 1
                    
                    if "error" not in result:
                        email_log.status = "sent"
                        email_log.zoho_message_id = result.get("data", {}).get("message_id")
                        email_log.sent_at = datetime.utcnow()
                        stats["successful"] += 1
                        logger.info(f"✓ Retry successful for email {email_log.id}")
                    else:
                        email_log.status = "failed"
                        email_log.error_message = result.get("error")
                        stats["still_failed"] += 1
                        logger.warning(f"Retry still failed for email {email_log.id}")
                    
                    email_log.updated_at = datetime.utcnow()
                    stats["total_retried"] += 1
                    
                except Exception as e:
                    logger.error(f"Error retrying email {email_log.id}: {e}")
                    stats["errors"].append(str(e))
            
            db.commit()
            logger.info(f"Email retry batch completed: {stats}")
            return stats
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to retry emails: {e}")
            return {"error": str(e)}
        finally:
            db.close()
    
    @staticmethod
    def _render_template(
        template_string: str,
        variables: Dict[str, Any],
        is_html: bool = False
    ) -> str:
        """
        Render Jinja2 template with variables.
        
        Args:
            template_string: Template string or file path (if starts with /)
            variables: Variables to inject
            is_html: Whether to treat as HTML file reference
            
        Returns:
            Rendered template string
        """
        try:
            # If it looks like a file path and is HTML, load from templates/email/
            if is_html and template_string.endswith(".html"):
                import os
                template_dir = os.path.join(os.path.dirname(__file__), "..", "templates", "email")
                template_path = os.path.join(template_dir, template_string)
                
                if os.path.exists(template_path):
                    with open(template_path, "r") as f:
                        template_string = f.read()
                else:
                    logger.warning(f"Template file not found: {template_path}, using as literal")
            
            template = Template(template_string)
            rendered = template.render(**variables)
            return rendered
            
        except TemplateError as e:
            logger.error(f"Template rendering error: {e}")
            raise ValidationError(f"Failed to render template: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error rendering template: {e}")
            raise ValidationError(f"Unexpected template error: {str(e)}")
    
    @staticmethod
    def get_email_logs(
        company_id: str,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
        ticket_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get email logs with optional filtering.
        
        Args:
            company_id: Company UUID
            event_type: Filter by event type
            status: Filter by status (sent, failed, pending)
            ticket_id: Filter by ticket
            limit: Pagination limit
            offset: Pagination offset
            
        Returns:
            Dict with logs and pagination info
        """
        db = SessionLocal()
        try:
            query = db.query(EmailLog).filter(EmailLog.company_id == UUID(company_id))
            
            if event_type:
                query = query.filter(EmailLog.event_type == event_type)
            
            if status:
                query = query.filter(EmailLog.status == status)
            
            if ticket_id:
                query = query.filter(EmailLog.ticket_id == UUID(ticket_id))
            
            total = query.count()
            logs = query.order_by(EmailLog.created_at.desc()).limit(limit).offset(offset).all()
            
            return {
                "logs": [
                    {
                        "id": str(log.id),
                        "event_type": log.event_type,
                        "recipient_email": log.recipient_email,
                        "recipient_role": log.recipient_role,
                        "subject": log.subject,
                        "status": log.status,
                        "error_message": log.error_message,
                        "retry_count": log.retry_count,
                        "sent_at": to_iso_date(log.sent_at) if log.sent_at else None,
                        "created_at": to_iso_date(log.created_at)
                    }
                    for log in logs
                ],
                "total": total,
                "limit": limit,
                "offset": offset
            }
            
        finally:
            db.close()
