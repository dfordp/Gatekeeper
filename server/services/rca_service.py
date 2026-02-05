# server/services/rca_service.py
"""
RCA Service - Root Cause Analysis with attachments and visual guides

Manages RCA creation, updating, attachment handling, and semantic search integration.
"""

import logging
import os
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, date

from core.database import (
    SessionLocal, Ticket, RootCauseAnalysis, User, RCAAttachment,
    TicketEvent, AdminAuditLog
)
from utils.datetime_utils import to_iso_date
from .embedding_manager import EmbeddingManager
from .attachment_processor import AttachmentProcessor
from utils.exceptions import ValidationError, NotFoundError
from core.logger import get_logger

logger = get_logger(__name__)


class RCAService:
    """Service for Root Cause Analysis with attachments"""
    @staticmethod
    def create_or_update_rca(
        ticket_id: str,
        root_cause_description: str,
        contributing_factors: Optional[List[str]] = None,
        prevention_measures: Optional[str] = None,
        resolution_steps: Optional[List[str]] = None,
        rca_attachment_paths: Optional[List[str]] = None,
        created_by_user_id: str = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create or update RCA with attachments.
        Processes RCA attachments and creates embeddings for semantic search.
        
        Now uses RCAAttachment table instead of JSONB column.
        """
        db = SessionLocal()
        
        try:
            # Validate ticket exists
            try:
                ticket_uuid = UUID(ticket_id)
                ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
                if not ticket:
                    raise NotFoundError(f"Ticket {ticket_id} not found")
            except ValueError:
                raise ValidationError(f"Invalid ticket ID format: {ticket_id}")
            
            # Validate description
            if not root_cause_description or len(root_cause_description.strip()) < 10:
                raise ValidationError("Root cause description must be at least 10 characters")
            
            # Get or determine creator
            actual_creator_id = ticket.raised_by_user_id
            if created_by_user_id:
                try:
                    user_uuid = UUID(created_by_user_id)
                    user = db.query(User).filter(User.id == user_uuid).first()
                    if user:
                        actual_creator_id = user_uuid
                except (ValueError, Exception):
                    pass
            
            # Check existing RCA
            existing_rca = db.query(RootCauseAnalysis).filter(
                RootCauseAnalysis.ticket_id == ticket_uuid
            ).first()
            
            is_update = False
            if existing_rca:
                logger.info(f"Updating existing RCA for ticket {ticket_id}")
                existing_rca.root_cause_description = root_cause_description.strip()
                existing_rca.contributing_factors = contributing_factors or []
                existing_rca.prevention_measures = prevention_measures.strip() if prevention_measures else None
                existing_rca.resolution_steps = resolution_steps or []
                existing_rca.updated_at = date.today()

                AttachmentProcessor.deprecate_rca_attachments(
                    rca_id=str(existing_rca.id),
                    reason="rca_updated"
                )
                
                # Clear old attachments and add new ones
                db.query(RCAAttachment).filter(RCAAttachment.rca_id == existing_rca.id).delete()
                rca = existing_rca
                is_update = True
            else:
                logger.info(f"Creating new RCA for ticket {ticket_id}")
                rca = RootCauseAnalysis(
                    ticket_id=ticket_uuid,
                    root_cause_description=root_cause_description.strip(),
                    created_by_user_id=actual_creator_id,
                    contributing_factors=contributing_factors or [],
                    prevention_measures=prevention_measures.strip() if prevention_measures else None,
                    resolution_steps=resolution_steps or []
                )
                db.add(rca)
            
            db.flush()
            
            # Add RCA attachments to RCAAttachment table
            if rca_attachment_paths:
                logger.info(f"Adding {len(rca_attachment_paths)} attachments to RCA")
                for path in rca_attachment_paths:
                    rca_att = RCAAttachment(
                        rca_id=rca.id,
                        type="document",  # Could be enhanced to detect type
                        file_path=path,
                        mime_type=None  # Could be enhanced to detect mime type
                    )
                    db.add(rca_att)
            
            db.flush()
            
            # Create RCA embedding for semantic search (text content)
            logger.info(f"Creating RCA text embedding for semantic search")
            rca_text = f"{root_cause_description}\n\n{prevention_measures or ''}\n\n{' '.join(resolution_steps or [])}"
            
            try:
                AttachmentProcessor._create_rca_embeddings(
                    db=db,
                    ticket_id=ticket_uuid,
                    company_id=ticket.company_id,
                    root_cause_text=rca_text,
                    is_update=is_update
                )
            except Exception as e:
                logger.warning(f"Failed to create RCA text embedding: {e}")
            
            # Process RCA attachments if provided
            if rca_attachment_paths and len(rca_attachment_paths) > 0:
                logger.info(f"Processing {len(rca_attachment_paths)} RCA attachments")
                try:
                    attachment_count = AttachmentProcessor.process_rca_attachments(
                        rca_id=str(rca.id),
                        ticket_id=str(ticket_uuid),
                        company_id=str(ticket.company_id),
                        attachment_paths=rca_attachment_paths
                    )
                    logger.info(f"✓ RCA attachment processing complete: {attachment_count} embeddings")
                except Exception as e:
                    logger.warning(f"Failed to process RCA attachments: {e}")
            
            # Log event
            event_type = "rca_updated" if is_update else "rca_added"
            rca_event = TicketEvent(
                ticket_id=ticket_uuid,
                event_type=event_type,
                actor_user_id=actual_creator_id,
                payload={
                    "rca_id": str(rca.id),
                    "root_cause": root_cause_description.strip()[:100],
                    "has_attachments": bool(rca_attachment_paths),
                    "attachment_count": len(rca_attachment_paths or []),
                    "is_update": is_update
                }
            )
            db.add(rca_event)
            db.commit()
            
            logger.info(f"✓ RCA {'updated' if is_update else 'created'} successfully")
            
            return {
                "ok": True,
                "rca_id": str(rca.id),
                "ticket_id": ticket_id,
                "is_update": is_update,
                "has_attachments": bool(rca_attachment_paths),
                "attachment_count": len(rca_attachment_paths or [])
            }
        
        except (ValidationError, NotFoundError) as e:
            logger.error(f"RCA validation error: {e}")
            return {
                "ok": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"RCA creation failed: {e}")
            db.rollback()
            return {
                "ok": False,
                "error": "Failed to create/update RCA"
            }
        finally:
            db.close()
    
    @staticmethod
    def get_rca_with_details(ticket_id: str) -> Optional[Dict[str, Any]]:
        """
        Get RCA with all details and attachments.
        
        Args:
            ticket_id: Ticket UUID
            
        Returns:
            RCA details or None
        """
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            rca = db.query(RootCauseAnalysis).filter(
                RootCauseAnalysis.ticket_id == ticket_uuid
            ).first()
            
            if not rca:
                return None
            
            # Fetch RCA attachments
            attachments = db.query(RCAAttachment).filter(
                RCAAttachment.rca_id == rca.id
            ).all()
            
            attachment_list = [
                {
                    "id": str(att.id),
                    "file_path": att.file_path,
                    "type": att.type,
                    "created_at": to_iso_date(att.created_at) if att.created_at else None
                }
                for att in attachments
            ]
            
            return {
                "id": str(rca.id),
                "ticket_id": str(rca.ticket_id),
                "root_cause": rca.root_cause_description,
                "contributing_factors": rca.contributing_factors,
                "prevention_measures": rca.prevention_measures,
                "resolution_steps": rca.resolution_steps,
                "attachments": attachment_list,
                "created_by": rca.created_by_user.name if rca.created_by_user else None,
                "created_at": to_iso_date(rca.created_at) if rca.created_at else None,
                "updated_at": to_iso_date(rca.updated_at) if rca.updated_at else None
            }
        except ValueError:
            return None
        except Exception as e:
            logger.error(f"Error fetching RCA: {e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def format_rca_for_telegram(rca_details: Dict[str, Any]) -> str:
        """
        Format RCA details for Telegram chatbot display.
        
        Args:
            rca_details: RCA data from get_rca_with_details()
            
        Returns:
            Formatted message for Telegram
        """
        if not rca_details:
            return "❌ No RCA found for this ticket"
        
        message = "📋 **ROOT CAUSE ANALYSIS**\n\n"
        
        # Root cause
        message += f"🔍 **Root Cause:**\n{rca_details['root_cause']}\n\n"
        
        # Contributing factors
        if rca_details.get('contributing_factors'):
            message += "⚠️ **Contributing Factors:**\n"
            for i, factor in enumerate(rca_details['contributing_factors'], 1):
                message += f"  {i}. {factor}\n"
            message += "\n"
        
        # Prevention measures
        if rca_details.get('prevention_measures'):
            message += f"🛡️ **Prevention Measures:**\n{rca_details['prevention_measures']}\n\n"
        
        # Resolution steps
        if rca_details.get('resolution_steps'):
            message += "✅ **Resolution Steps:**\n"
            for i, step in enumerate(rca_details['resolution_steps'], 1):
                message += f"  {i}. {step}\n"
            message += "\n"
        
        # Attachments
        if rca_details.get('attachments'):
            message += f"📎 **Attachments:** {len(rca_details['attachments'])} file(s)\n"
        
        return message
    
    @staticmethod
    def search_rcas_by_keyword(
        keyword: str,
        company_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search RCAs by keyword in root cause or prevention measures.
        
        Args:
            keyword: Search keyword
            company_id: Optional company filter
            limit: Max results
            
        Returns:
            List of matching RCAs
        """
        db = SessionLocal()
        try:
            from core.database import Ticket
            query = db.query(RootCauseAnalysis)
            
            # Search in text fields
            search_text = f"%{keyword.lower()}%"
            query = query.filter(
                (RootCauseAnalysis.root_cause_description.ilike(search_text)) |
                (RootCauseAnalysis.prevention_measures.ilike(search_text))
            )
            
            # Filter by company if provided
            if company_id:
                company_uuid = UUID(company_id)
                query = query.join(Ticket).filter(Ticket.company_id == company_uuid)
            
            rcas = query.order_by(RootCauseAnalysis.created_at.desc()).limit(limit).all()
            
            return [
                {
                    "id": str(rca.id),
                    "ticket_id": str(rca.ticket_id),
                    "ticket_no": rca.ticket.ticket_no if rca.ticket else None,
                    "root_cause": rca.root_cause_description[:150],
                    "attachment_count": len(rca.attachments or []),
                    "created_at": to_iso_date(rca.created_at) if rca.created_at else None
                }
                for rca in rcas
            ]
        except Exception as e:
            logger.error(f"RCA search failed: {e}")
            return []
        finally:
            db.close()