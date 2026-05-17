# server/services/email_listener_service.py
"""Email listener service - listens for ticket and user events and triggers email sending"""
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

from services.email_configuration_service import EmailConfigurationService
from services.email_queue_service import EmailQueueService
from utils.datetime_utils import to_iso_date
from core.logger import get_logger

logger = get_logger(__name__)


class EmailListenerService:
    """Service that listens to events and triggers email sending"""
    
    # ==================== TICKET EVENT LISTENERS ====================
    
    @staticmethod
    def on_ticket_created(
        ticket_id: str,
        ticket_no: str,
        ticket_subject: str,
        company_id: str,
        raised_by_user_id: str,
        raised_by_user_name: str,
        raised_by_user_email: str,
        category: Optional[str] = None,
        level: Optional[str] = None
    ) -> None:
        """
        Called when a ticket is created.
        Sends email to ticket raiser confirming ticket creation.
        """
        try:
            # Check if event is enabled
            if not EmailConfigurationService.is_event_enabled("ticket_created", company_id):
                logger.debug(f"ticket_created email event disabled for company {company_id}")
                return
            
            # Get recipients
            recipients = EmailConfigurationService.get_recipients_for_event(
                event_type="ticket_created",
                company_id=company_id,
                raised_by_user_id=raised_by_user_id
            )
            
            if not recipients:
                logger.warning(f"No recipients for ticket_created email")
                return
            
            # Prepare template variables
            template_variables = {
                "ticket_id": ticket_id,
                "ticket_no": ticket_no,
                "ticket_subject": ticket_subject,
                "category": category or "General",
                "level": level or "Level 3",
                "user_name": raised_by_user_name,
                "company_name": company_id,  # Can be enhanced to fetch company name
                "ticket_url": f"https://gatekeeper.example.com/tickets/{ticket_no}",
                "portal_url": f"https://gatekeeper.example.com"
            }
            
            # Queue email task
            task_id = EmailQueueService.queue_email_task(
                email_type="ticket_created",
                event_type="ticket_created",
                company_id=company_id,
                recipient_list=recipients,
                template_variables=template_variables,
                ticket_id=ticket_id
            )
            
            logger.info(f"✓ Queued ticket_created email for ticket {ticket_no}")
            
        except Exception as e:
            logger.error(f"Error in on_ticket_created listener: {e}")
    
    @staticmethod
    def on_ticket_assigned(
        ticket_id: str,
        ticket_no: str,
        ticket_subject: str,
        company_id: str,
        assigned_engineer_id: str,
        assigned_engineer_name: str,
        assigned_engineer_email: str,
        assigned_by_admin_id: Optional[str] = None
    ) -> None:
        """
        Called when a ticket is assigned to an engineer.
        Sends email to assigned engineer notifying them of the assignment.
        """
        try:
            # Check if event is enabled
            if not EmailConfigurationService.is_event_enabled("ticket_assigned", company_id):
                logger.debug(f"ticket_assigned email event disabled for company {company_id}")
                return
            
            # Get recipients
            recipients = EmailConfigurationService.get_recipients_for_event(
                event_type="ticket_assigned",
                company_id=company_id,
                assigned_engineer_id=assigned_engineer_id
            )
            
            if not recipients:
                logger.warning(f"No recipients for ticket_assigned email")
                return
            
            # Prepare template variables
            template_variables = {
                "ticket_id": ticket_id,
                "ticket_no": ticket_no,
                "ticket_subject": ticket_subject,
                "engineer_name": assigned_engineer_name,
                "company_name": company_id,
                "ticket_url": f"https://gatekeeper.example.com/tickets/{ticket_no}",
                "portal_url": f"https://gatekeeper.example.com"
            }
            
            # Queue email task
            task_id = EmailQueueService.queue_email_task(
                email_type="ticket_assigned",
                event_type="ticket_assigned",
                company_id=company_id,
                recipient_list=recipients,
                template_variables=template_variables,
                ticket_id=ticket_id,
                user_id=assigned_engineer_id
            )
            
            logger.info(f"✓ Queued ticket_assigned email for ticket {ticket_no}")
            
        except Exception as e:
            logger.error(f"Error in on_ticket_assigned listener: {e}")
    
    @staticmethod
    def on_ticket_status_updated(
        ticket_id: str,
        ticket_no: str,
        ticket_subject: str,
        company_id: str,
        old_status: str,
        new_status: str,
        raised_by_user_id: str,
        raised_by_user_name: str
    ) -> None:
        """
        Called when ticket status is updated.
        Sends email to ticket raiser about status change (conditional based on status).
        """
        try:
            # Check if event is enabled
            if not EmailConfigurationService.is_event_enabled("ticket_status_updated", company_id):
                logger.debug(f"ticket_status_updated email event disabled for company {company_id}")
                return
            
            # Get recipients
            recipients = EmailConfigurationService.get_recipients_for_event(
                event_type="ticket_status_updated",
                company_id=company_id,
                raised_by_user_id=raised_by_user_id
            )
            
            if not recipients:
                logger.warning(f"No recipients for ticket_status_updated email")
                return
            
            # Prepare template variables
            template_variables = {
                "ticket_id": ticket_id,
                "ticket_no": ticket_no,
                "ticket_subject": ticket_subject,
                "old_status": old_status,
                "new_status": new_status,
                "user_name": raised_by_user_name,
                "company_name": company_id,
                "ticket_url": f"https://gatekeeper.example.com/tickets/{ticket_no}",
                "portal_url": f"https://gatekeeper.example.com"
            }
            
            # Queue email task
            task_id = EmailQueueService.queue_email_task(
                email_type="ticket_status_updated",
                event_type="ticket_status_updated",
                company_id=company_id,
                recipient_list=recipients,
                template_variables=template_variables,
                ticket_id=ticket_id
            )
            
            logger.info(f"✓ Queued ticket_status_updated email for ticket {ticket_no}")
            
        except Exception as e:
            logger.error(f"Error in on_ticket_status_updated listener: {e}")
    
    @staticmethod
    def on_ticket_resolved(
        ticket_id: str,
        ticket_no: str,
        ticket_subject: str,
        company_id: str,
        raised_by_user_id: str,
        raised_by_user_name: str
    ) -> None:
        """
        Called when a ticket is resolved.
        Sends email to ticket raiser notifying resolution.
        """
        try:
            # Check if event is enabled
            if not EmailConfigurationService.is_event_enabled("ticket_resolved", company_id):
                logger.debug(f"ticket_resolved email event disabled for company {company_id}")
                return
            
            # Get recipients
            recipients = EmailConfigurationService.get_recipients_for_event(
                event_type="ticket_resolved",
                company_id=company_id,
                raised_by_user_id=raised_by_user_id
            )
            
            if not recipients:
                logger.warning(f"No recipients for ticket_resolved email")
                return
            
            # Prepare template variables
            template_variables = {
                "ticket_id": ticket_id,
                "ticket_no": ticket_no,
                "ticket_subject": ticket_subject,
                "user_name": raised_by_user_name,
                "company_name": company_id,
                "ticket_url": f"https://gatekeeper.example.com/tickets/{ticket_no}",
                "portal_url": f"https://gatekeeper.example.com"
            }
            
            # Queue email task
            task_id = EmailQueueService.queue_email_task(
                email_type="ticket_resolved",
                event_type="ticket_resolved",
                company_id=company_id,
                recipient_list=recipients,
                template_variables=template_variables,
                ticket_id=ticket_id
            )
            
            logger.info(f"✓ Queued ticket_resolved email for ticket {ticket_no}")
            
        except Exception as e:
            logger.error(f"Error in on_ticket_resolved listener: {e}")
    
    @staticmethod
    def on_ticket_closed(
        ticket_id: str,
        ticket_no: str,
        ticket_subject: str,
        company_id: str,
        raised_by_user_id: str,
        raised_by_user_name: str
    ) -> None:
        """
        Called when a ticket is closed.
        Sends email to ticket raiser confirming ticket closure.
        """
        try:
            # Check if event is enabled
            if not EmailConfigurationService.is_event_enabled("ticket_closed", company_id):
                logger.debug(f"ticket_closed email event disabled for company {company_id}")
                return
            
            # Get recipients
            recipients = EmailConfigurationService.get_recipients_for_event(
                event_type="ticket_closed",
                company_id=company_id,
                raised_by_user_id=raised_by_user_id
            )
            
            if not recipients:
                logger.warning(f"No recipients for ticket_closed email")
                return
            
            # Prepare template variables
            template_variables = {
                "ticket_id": ticket_id,
                "ticket_no": ticket_no,
                "ticket_subject": ticket_subject,
                "user_name": raised_by_user_name,
                "company_name": company_id,
                "ticket_url": f"https://gatekeeper.example.com/tickets/{ticket_no}",
                "portal_url": f"https://gatekeeper.example.com",
                "survey_url": f"https://gatekeeper.example.com/survey/{ticket_no}"
            }
            
            # Queue email task
            task_id = EmailQueueService.queue_email_task(
                email_type="ticket_closed",
                event_type="ticket_closed",
                company_id=company_id,
                recipient_list=recipients,
                template_variables=template_variables,
                ticket_id=ticket_id
            )
            
            logger.info(f"✓ Queued ticket_closed email for ticket {ticket_no}")
            
        except Exception as e:
            logger.error(f"Error in on_ticket_closed listener: {e}")
    
    # ==================== USER EVENT LISTENERS ====================
    
    @staticmethod
    def on_user_created(
        user_id: str,
        user_name: str,
        user_email: str,
        company_id: str,
        role: str
    ) -> None:
        """
        Called when a new user is created.
        Sends welcome email to new user.
        """
        try:
            # Check if event is enabled
            if not EmailConfigurationService.is_event_enabled("user_created", company_id):
                logger.debug(f"user_created email event disabled for company {company_id}")
                return
            
            # Get recipients
            recipients = EmailConfigurationService.get_recipients_for_event(
                event_type="user_created",
                company_id=company_id,
                user_id=user_id
            )
            
            if not recipients:
                logger.warning(f"No recipients for user_created email")
                return
            
            # Prepare template variables
            template_variables = {
                "user_id": user_id,
                "user_name": user_name,
                "user_email": user_email,
                "role": role,
                "company_name": company_id,
                "portal_url": f"https://gatekeeper.example.com",
                "login_url": f"https://gatekeeper.example.com/login"
            }
            
            # Queue email task
            task_id = EmailQueueService.queue_email_task(
                email_type="user_created",
                event_type="user_created",
                company_id=company_id,
                recipient_list=recipients,
                template_variables=template_variables,
                user_id=user_id
            )
            
            logger.info(f"✓ Queued user_created email for user {user_email}")
            
        except Exception as e:
            logger.error(f"Error in on_user_created listener: {e}")
    
    @staticmethod
    def on_user_updated(
        user_id: str,
        user_name: str,
        user_email: str,
        company_id: str,
        changes: Dict[str, Any]
    ) -> None:
        """
        Called when a user is updated.
        Sends email to user about their profile updates.
        """
        try:
            # Check if event is enabled
            if not EmailConfigurationService.is_event_enabled("user_updated", company_id):
                logger.debug(f"user_updated email event disabled for company {company_id}")
                return
            
            # Get recipients
            recipients = EmailConfigurationService.get_recipients_for_event(
                event_type="user_updated",
                company_id=company_id,
                user_id=user_id
            )
            
            if not recipients:
                logger.warning(f"No recipients for user_updated email")
                return
            
            # Format changes for template
            changes_text = "\n".join([f"- {k}: {v['from']} → {v['to']}" for k, v in changes.items()])
            
            # Prepare template variables
            template_variables = {
                "user_id": user_id,
                "user_name": user_name,
                "user_email": user_email,
                "changes": changes_text,
                "company_name": company_id,
                "portal_url": f"https://gatekeeper.example.com"
            }
            
            # Queue email task
            task_id = EmailQueueService.queue_email_task(
                email_type="user_updated",
                event_type="user_updated",
                company_id=company_id,
                recipient_list=recipients,
                template_variables=template_variables,
                user_id=user_id
            )
            
            logger.info(f"✓ Queued user_updated email for user {user_email}")
            
        except Exception as e:
            logger.error(f"Error in on_user_updated listener: {e}")
    
    @staticmethod
    def on_user_deleted(
        user_id: str,
        user_name: str,
        user_email: str,
        company_id: str
    ) -> None:
        """
        Called when a user is deleted.
        Sends notification email to admins about user deletion.
        """
        try:
            # Check if event is enabled
            if not EmailConfigurationService.is_event_enabled("user_deleted", company_id):
                logger.debug(f"user_deleted email event disabled for company {company_id}")
                return
            
            # Get recipients (typically admins)
            recipients = EmailConfigurationService.get_recipients_for_event(
                event_type="user_deleted",
                company_id=company_id
            )
            
            if not recipients:
                logger.warning(f"No recipients for user_deleted email")
                return
            
            # Prepare template variables
            template_variables = {
                "user_id": user_id,
                "user_name": user_name,
                "user_email": user_email,
                "company_name": company_id,
                "deletion_time": to_iso_date(datetime.utcnow()),
                "portal_url": f"https://gatekeeper.example.com"
            }
            
            # Queue email task
            task_id = EmailQueueService.queue_email_task(
                email_type="user_deleted",
                event_type="user_deleted",
                company_id=company_id,
                recipient_list=recipients,
                template_variables=template_variables,
                user_id=user_id
            )
            
            logger.info(f"✓ Queued user_deleted email for user {user_email}")
            
        except Exception as e:
            logger.error(f"Error in on_user_deleted listener: {e}")
