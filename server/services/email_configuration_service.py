# server/services/email_configuration_service.py
"""Email configuration service - manages templates and company-level email settings"""
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime
from functools import lru_cache

from core.database import SessionLocal, EmailTemplate, EmailConfiguration, Company, User
from utils.exceptions import NotFoundError, ValidationError
from core.logger import get_logger

logger = get_logger(__name__)


class EmailConfigurationService:
    """Service for managing email templates and configurations"""
    
    @staticmethod
    def get_template(event_type: str) -> Dict[str, Any]:
        """
        Get email template by event type.
        
        Args:
            event_type: Type of event (ticket_created, ticket_assigned, etc.)
            
        Returns:
            Dict with template details
            
        Raises:
            NotFoundError: If template not found
        """
        db = SessionLocal()
        try:
            template = db.query(EmailTemplate).filter(
                EmailTemplate.event_type == event_type,
                EmailTemplate.is_active == True
            ).first()
            
            if not template:
                raise NotFoundError(f"Email template not found for event: {event_type}")
            
            return {
                "id": str(template.id),
                "event_type": template.event_type,
                "subject_template": template.subject_template,
                "body_template": template.body_template,
                "description": template.description,
                "is_active": template.is_active
            }
            
        finally:
            db.close()
    
    @staticmethod
    def get_or_create_default_configuration(company_id: str) -> Dict[str, Any]:
        """
        Get or create default email configuration for company.
        
        Args:
            company_id: Company UUID
            
        Returns:
            Dict with configuration
        """
        db = SessionLocal()
        try:
            config = db.query(EmailConfiguration).filter(
                EmailConfiguration.company_id == UUID(company_id)
            ).first()
            
            if not config:
                # Create default configuration with all events enabled
                config = EmailConfiguration(
                    company_id=UUID(company_id),
                    enabled_events=[
                        "ticket_created",
                        "ticket_assigned",
                        "ticket_status_updated",
                        "ticket_resolved",
                        "ticket_closed",
                        "user_created",
                        "user_updated",
                        "user_deleted"
                    ],
                    is_enabled=True
                )
                db.add(config)
                db.commit()
                logger.info(f"Created default email configuration for company {company_id}")
            
            return EmailConfigurationService._format_config(config)
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to get/create configuration: {e}")
            raise ValidationError(f"Failed to get email configuration: {str(e)}")
        finally:
            db.close()
    
    @staticmethod
    def get_configuration(company_id: str) -> Dict[str, Any]:
        """Get email configuration for company"""
        db = SessionLocal()
        try:
            config = db.query(EmailConfiguration).filter(
                EmailConfiguration.company_id == UUID(company_id)
            ).first()
            
            if not config:
                db.close()
                return EmailConfigurationService.get_or_create_default_configuration(company_id)
            
            return EmailConfigurationService._format_config(config)
            
        finally:
            db.close()
    
    @staticmethod
    def is_event_enabled(event_type: str, company_id: str) -> bool:
        """
        Check if event type is enabled for company.
        
        Args:
            event_type: Type of event
            company_id: Company UUID
            
        Returns:
            True if enabled, False otherwise
        """
        db = SessionLocal()
        try:
            config = db.query(EmailConfiguration).filter(
                EmailConfiguration.company_id == UUID(company_id),
                EmailConfiguration.is_enabled == True
            ).first()
            
            if not config:
                return False
            
            enabled_events = config.enabled_events or []
            return event_type in enabled_events
            
        except Exception as e:
            logger.warning(f"Error checking if event enabled: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_recipients_for_event(
        event_type: str,
        company_id: str,
        ticket_id: Optional[str] = None,
        user_id: Optional[str] = None,
        assigned_engineer_id: Optional[str] = None,
        raised_by_user_id: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Determine recipients for an event based on event type, role, and company config.
        
        Args:
            event_type: Type of event
            company_id: Company UUID
            ticket_id: Ticket UUID (if applicable)
            user_id: User UUID (if applicable)
            assigned_engineer_id: Engineer UUID (if applicable)
            raised_by_user_id: Ticket raiser UUID (if applicable)
            
        Returns:
            List of dicts with {email, role, user_id} for each recipient
        """
        db = SessionLocal()
        try:
            recipients = []
            config_dict = EmailConfigurationService.get_configuration(company_id)
            recipient_overrides = config_dict.get("recipient_overrides", {})
            
            # Check for custom recipients in config
            if event_type in recipient_overrides:
                custom_recipients = recipient_overrides[event_type]
                for role, emails in custom_recipients.items():
                    for email in emails:
                        recipients.append({
                            "email": email,
                            "role": role,
                            "user_id": None
                        })
                return recipients
            
            # Default recipient logic based on event type
            if event_type == "ticket_created":
                # Email the ticket raiser
                if raised_by_user_id:
                    user = db.query(User).filter(User.id == UUID(raised_by_user_id)).first()
                    if user:
                        recipients.append({
                            "email": user.email,
                            "role": user.role,
                            "user_id": str(user.id)
                        })
            
            elif event_type == "ticket_assigned":
                # Email the assigned engineer
                if assigned_engineer_id:
                    user = db.query(User).filter(User.id == UUID(assigned_engineer_id)).first()
                    if user:
                        recipients.append({
                            "email": user.email,
                            "role": "engineer",
                            "user_id": str(user.id)
                        })
            
            elif event_type in ["ticket_status_updated", "ticket_resolved", "ticket_closed"]:
                # Email the ticket raiser on status changes
                if raised_by_user_id:
                    user = db.query(User).filter(User.id == UUID(raised_by_user_id)).first()
                    if user:
                        recipients.append({
                            "email": user.email,
                            "role": user.role,
                            "user_id": str(user.id)
                        })
            
            elif event_type == "user_created":
                # Email admins or supervisors
                company = db.query(Company).filter(Company.id == UUID(company_id)).first()
                if company:
                    admin_users = db.query(User).filter(
                        User.company_id == UUID(company_id),
                        User.role.in_(["supervisor", "manager"])
                    ).all()
                    for user in admin_users:
                        recipients.append({
                            "email": user.email,
                            "role": user.role,
                            "user_id": str(user.id)
                        })
            
            elif event_type in ["user_updated", "user_deleted"]:
                # Email the affected user (for updates) or admins (for deletions)
                if event_type == "user_updated" and user_id:
                    user = db.query(User).filter(User.id == UUID(user_id)).first()
                    if user:
                        recipients.append({
                            "email": user.email,
                            "role": user.role,
                            "user_id": str(user.id)
                        })
                else:
                    # For deleted users, notify admins
                    admin_users = db.query(User).filter(
                        User.company_id == UUID(company_id),
                        User.role.in_(["supervisor", "manager"])
                    ).all()
                    for user in admin_users:
                        recipients.append({
                            "email": user.email,
                            "role": user.role,
                            "user_id": str(user.id)
                        })
            
            return recipients
            
        except Exception as e:
            logger.error(f"Error getting recipients for event: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def update_configuration(
        company_id: str,
        enabled_events: Optional[List[str]] = None,
        recipient_overrides: Optional[Dict[str, Any]] = None,
        default_cc_list: Optional[List[str]] = None,
        default_bcc_list: Optional[List[str]] = None,
        email_from_name: Optional[str] = None,
        is_enabled: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Update email configuration for company"""
        db = SessionLocal()
        try:
            config = db.query(EmailConfiguration).filter(
                EmailConfiguration.company_id == UUID(company_id)
            ).first()
            
            if not config:
                config = EmailConfigurationService.get_or_create_default_configuration(company_id)
                config = db.query(EmailConfiguration).filter(
                    EmailConfiguration.company_id == UUID(company_id)
                ).first()
            
            if enabled_events is not None:
                config.enabled_events = enabled_events
            
            if recipient_overrides is not None:
                config.recipient_overrides = recipient_overrides
            
            if default_cc_list is not None:
                config.default_cc_list = default_cc_list
            
            if default_bcc_list is not None:
                config.default_bcc_list = default_bcc_list
            
            if email_from_name is not None:
                config.email_from_name = email_from_name
            
            if is_enabled is not None:
                config.is_enabled = is_enabled
            
            config.updated_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"✓ Email configuration updated for company {company_id}")
            
            return EmailConfigurationService._format_config(config)
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update configuration: {e}")
            raise ValidationError(f"Failed to update configuration: {str(e)}")
        finally:
            db.close()
    
    @staticmethod
    def _format_config(config) -> Dict[str, Any]:
        """Format configuration object as dictionary"""
        return {
            "id": str(config.id),
            "company_id": str(config.company_id),
            "enabled_events": config.enabled_events or [],
            "recipient_overrides": config.recipient_overrides or {},
            "default_cc_list": config.default_cc_list or [],
            "default_bcc_list": config.default_bcc_list or [],
            "email_from_name": config.email_from_name,
            "rate_limit_per_hour": config.rate_limit_per_hour,
            "is_enabled": config.is_enabled,
            "created_at": config.created_at,
            "updated_at": config.updated_at
        }
    
    @staticmethod
    def create_default_templates() -> bool:
        """
        Create default email templates.
        Should be called on application startup.
        
        Returns:
            True if successful
        """
        db = SessionLocal()
        try:
            default_templates = [
                {
                    "event_type": "ticket_created",
                    "subject_template": "New Support Ticket Created: {{ticket_no}} - {{ticket_subject}}",
                    "body_template": "ticket_created.html",
                    "description": "Sent to ticket raiser when a new ticket is created"
                },
                {
                    "event_type": "ticket_assigned",
                    "subject_template": "Support Ticket Assigned: {{ticket_no}}",
                    "body_template": "ticket_assigned.html",
                    "description": "Sent to assigned engineer when ticket is assigned"
                },
                {
                    "event_type": "ticket_status_updated",
                    "subject_template": "Support Ticket Status Updated: {{ticket_no}} → {{new_status}}",
                    "body_template": "ticket_status_changed.html",
                    "description": "Sent to ticket raiser when ticket status changes"
                },
                {
                    "event_type": "ticket_resolved",
                    "subject_template": "Your Support Ticket Has Been Resolved: {{ticket_no}}",
                    "body_template": "ticket_resolved.html",
                    "description": "Sent to ticket raiser when ticket is resolved"
                },
                {
                    "event_type": "ticket_closed",
                    "subject_template": "Support Ticket Closed: {{ticket_no}}",
                    "body_template": "ticket_closed.html",
                    "description": "Sent to ticket raiser when ticket is closed"
                },
                {
                    "event_type": "user_created",
                    "subject_template": "New Team Member Added: {{user_name}}",
                    "body_template": "user_welcome.html",
                    "description": "Sent to new users and admins when user is created"
                },
                {
                    "event_type": "user_updated",
                    "subject_template": "Your Profile Has Been Updated",
                    "body_template": "user_role_changed.html",
                    "description": "Sent to user when their profile is updated"
                },
                {
                    "event_type": "user_deleted",
                    "subject_template": "Team Member Removed: {{user_name}}",
                    "body_template": "admin_notification.html",
                    "description": "Sent to admins when user is deleted"
                }
            ]
            
            for template_data in default_templates:
                existing = db.query(EmailTemplate).filter(
                    EmailTemplate.event_type == template_data["event_type"]
                ).first()
                
                if not existing:
                    template = EmailTemplate(
                        event_type=template_data["event_type"],
                        subject_template=template_data["subject_template"],
                        body_template=template_data["body_template"],
                        description=template_data["description"],
                        is_active=True
                    )
                    db.add(template)
            
            db.commit()
            logger.info("✓ Default email templates created/verified")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create default templates: {e}")
            return False
        finally:
            db.close()
