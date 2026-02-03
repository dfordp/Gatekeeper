# server/services/ir_service.py
"""Incident Report (IR) Management Service"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID

from core.database import SessionLocal, Ticket, IncidentReport, IREvent, User
from utils.exceptions import ValidationError, NotFoundError
from core.logger import get_logger

logger = get_logger(__name__)


class IRService:
    """Service for managing Incident Reports"""
    
    @staticmethod
    def open_ir(
        ticket_id: str,
        ir_number: str,
        vendor: str = "siemens",
        expected_resolution_date: Optional[datetime] = None,
        notes: Optional[str] = None,
        created_by_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Open an Incident Report for a ticket"""
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            
            # Verify ticket exists
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            # Check if IR already exists
            existing_ir = db.query(IncidentReport).filter(
                IncidentReport.ir_number == ir_number
            ).first()
            if existing_ir:
                raise ValidationError(f"IR {ir_number} already exists")
            
            # Create IR
            ir = IncidentReport(
                ticket_id=ticket_uuid,
                ir_number=ir_number.strip(),
                vendor=vendor.lower(),
                expected_resolution_date=expected_resolution_date,
                notes=notes,
                created_by_user_id=UUID(created_by_user_id) if created_by_user_id else ticket.raised_by_user_id
            )
            db.add(ir)
            db.flush()
            
            # Update ticket to mark it has IR
            ticket.has_ir = True
            ticket.ir_number = ir_number.strip()
            ticket.ir_raised_at = datetime.utcnow()
            ticket.ir_expected_resolution_date = expected_resolution_date
            ticket.ir_notes = notes
            db.flush()
            
            # Log IR event
            ir_event = IREvent(
                incident_report_id=ir.id,
                event_type="ir_opened",
                actor_user_id=UUID(created_by_user_id) if created_by_user_id else ticket.raised_by_user_id,
                new_status="open",
                notes=f"IR opened for ticket {ticket.ticket_no}",
                payload={
                    "ir_number": ir_number,
                    "vendor": vendor,
                    "expected_resolution_date": expected_resolution_date.isoformat() if expected_resolution_date else None
                }
            )
            db.add(ir_event)
            db.commit()
            
            logger.info(f"✓ IR opened: {ir_number} for ticket {ticket.ticket_no}")
            
            return {
                "id": str(ir.id),
                "ir_number": ir.ir_number,
                "ticket_id": ticket_id,
                "ticket_no": ticket.ticket_no,
                "company_id": str(ticket.company_id),
                "vendor": ir.vendor,
                "status": ir.status,
                "expected_resolution_date": ir.expected_resolution_date.isoformat() if ir.expected_resolution_date else None,
                "created_at": ir.created_at.isoformat()
            }
            
        except (ValidationError, NotFoundError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to open IR: {e}")
            raise ValidationError(f"Failed to open IR: {str(e)}")
        finally:
            db.close()
    
    
    @staticmethod
    def update_ir_status(
        ir_id: str,
        status: str,
        vendor_status: Optional[str] = None,
        vendor_notes: Optional[str] = None,
        notes: Optional[str] = None,
        updated_by_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update IR status and vendor information"""
        db = SessionLocal()
        try:
            ir_uuid = UUID(ir_id)
            
            # Verify IR exists
            ir = db.query(IncidentReport).filter(IncidentReport.id == ir_uuid).first()
            if not ir:
                raise NotFoundError("Incident Report not found")
            
            # Get ticket for company_id
            ticket = db.query(Ticket).filter(Ticket.id == ir.ticket_id).first()
            if not ticket:
                raise NotFoundError("Associated ticket not found")
            
            valid_statuses = ["open", "in_progress", "resolved", "closed"]
            if status not in valid_statuses:
                raise ValidationError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
            
            old_status = ir.status
            ir.status = status
            ir.vendor_status = vendor_status
            ir.vendor_notes = vendor_notes
            ir.notes = notes or ir.notes
            ir.last_vendor_update = datetime.utcnow()
            ir.updated_by_user_id = UUID(updated_by_user_id) if updated_by_user_id else ir.created_by_user_id
            
            # If status is resolved/closed, mark IR as closed
            if status in ["resolved", "closed"]:
                ir.resolved_at = datetime.utcnow()
                ticket.ir_closed_at = datetime.utcnow()
                ticket.has_ir = False
            
            db.flush()
            
            # Log IR event
            ir_event = IREvent(
                incident_report_id=ir.id,
                event_type="status_updated",
                actor_user_id=UUID(updated_by_user_id) if updated_by_user_id else ir.created_by_user_id,
                old_status=old_status,
                new_status=status,
                notes=notes,
                payload={
                    "vendor_status": vendor_status,
                    "vendor_notes": vendor_notes
                }
            )
            db.add(ir_event)
            db.commit()
            
            logger.info(f"✓ IR {ir.ir_number} status updated: {old_status} → {status}")
            
            return {
                "id": str(ir.id),
                "ir_number": ir.ir_number,
                "ticket_id": str(ir.ticket_id),
                "company_id": str(ticket.company_id),
                "status": ir.status,
                "vendor": ir.vendor,
                "vendor_status": ir.vendor_status,
                "notes": ir.notes,
                "last_vendor_update": ir.last_vendor_update.isoformat() if ir.last_vendor_update else None,
                "updated_at": ir.updated_at.isoformat()
            }
            
        except (ValidationError, NotFoundError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update IR: {e}")
            raise ValidationError(f"Failed to update IR: {str(e)}")
        finally:
            db.close()
    
    
    @staticmethod
    def close_ir(
        ir_id: str,
        resolution_notes: Optional[str] = None,
        closed_by_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Close an Incident Report"""
        return IRService.update_ir_status(
            ir_id=ir_id,
            status="closed",
            notes=resolution_notes,
            updated_by_user_id=closed_by_user_id
        )
    
    
    @staticmethod
    def get_ir(ir_id: str) -> Dict[str, Any]:
        """Get IR details"""
        db = SessionLocal()
        try:
            ir = db.query(IncidentReport).filter(
                IncidentReport.id == UUID(ir_id)
            ).first()
            
            if not ir:
                raise NotFoundError("Incident Report not found")
            
            # Get ticket for company_id
            ticket = db.query(Ticket).filter(Ticket.id == ir.ticket_id).first()
            company_id = str(ticket.company_id) if ticket else None
            
            return {
                "id": str(ir.id),
                "ir_number": ir.ir_number,
                "ticket_id": str(ir.ticket_id),
                "company_id": company_id,
                "vendor": ir.vendor,
                "status": ir.status,
                "expected_resolution_date": ir.expected_resolution_date.isoformat() if ir.expected_resolution_date else None,
                "resolved_at": ir.resolved_at.isoformat() if ir.resolved_at else None,
                "notes": ir.notes,
                "vendor_status": ir.vendor_status,
                "vendor_notes": ir.vendor_notes,
                "last_vendor_update": ir.last_vendor_update.isoformat() if ir.last_vendor_update else None,
                "created_at": ir.created_at.isoformat(),
                "updated_at": ir.updated_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get IR: {e}")
            raise
        finally:
            db.close()
    
    
    @staticmethod
    def get_ticket_irs(ticket_id: str) -> List[Dict[str, Any]]:
        """Get all IRs for a ticket"""
        db = SessionLocal()
        try:
            # Get ticket for company_id
            ticket = db.query(Ticket).filter(Ticket.id == UUID(ticket_id)).first()
            company_id = str(ticket.company_id) if ticket else None
            
            irs = db.query(IncidentReport).filter(
                IncidentReport.ticket_id == UUID(ticket_id)
            ).order_by(IncidentReport.raised_at.desc()).all()
            
            return [
                {
                    "id": str(ir.id),
                    "ir_number": ir.ir_number,
                    "vendor": ir.vendor,
                    "status": ir.status,
                    "company_id": company_id,
                    "raised_at": ir.raised_at.isoformat(),
                    "expected_resolution_date": ir.expected_resolution_date.isoformat() if ir.expected_resolution_date else None,
                    "resolved_at": ir.resolved_at.isoformat() if ir.resolved_at else None,
                }
                for ir in irs
            ]
            
        except Exception as e:
            logger.error(f"Failed to get ticket IRs: {e}")
            return []
        finally:
            db.close()
    
    
    @staticmethod
    def get_open_irs() -> List[Dict[str, Any]]:
        """Get all open IRs across system"""
        db = SessionLocal()
        try:
            irs = db.query(IncidentReport).filter(
                IncidentReport.status == "open"
            ).order_by(IncidentReport.raised_at.asc()).all()
            
            results = []
            for ir in irs:
                # Get ticket for company_id
                ticket = db.query(Ticket).filter(Ticket.id == ir.ticket_id).first()
                company_id = str(ticket.company_id) if ticket else None
                
                results.append({
                    "id": str(ir.id),
                    "ir_number": ir.ir_number,
                    "ticket_id": str(ir.ticket_id),
                    "vendor": ir.vendor,
                    "status": ir.status,
                    "company_id": company_id,
                    "raised_at": ir.raised_at.isoformat(),
                    "expected_resolution_date": ir.expected_resolution_date.isoformat() if ir.expected_resolution_date else None,
                    "days_open": (datetime.utcnow() - ir.raised_at).days
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get open IRs: {e}")
            return []
        finally:
            db.close()