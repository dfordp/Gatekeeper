# server/services/ir_service.py
"""Incident Report (IR) Management Service"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID

from core.database import SessionLocal, Ticket, IncidentReport, IREvent, User
from utils.datetime_utils import to_iso_string
from utils.exceptions import ValidationError, NotFoundError
from core.logger import get_logger

logger = get_logger(__name__)


class IRService:
    """Service for managing Incident Reports"""
    
    @staticmethod
    def delete_ir(ir_id: str) -> Dict[str, Any]:
        """Delete an Incident Report and its related records"""
        db = SessionLocal()
        try:
            ir_uuid = UUID(ir_id)
            
            # Verify IR exists
            ir = db.query(IncidentReport).filter(IncidentReport.id == ir_uuid).first()
            if not ir:
                raise NotFoundError("Incident Report not found")
            
            ir_number = ir.ir_number
            ticket_id = ir.ticket_id
            
            # Get ticket to update has_ir flag
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            
            # Delete related IR events first (due to FK constraint)
            db.query(IREvent).filter(IREvent.incident_report_id == ir_uuid).delete(synchronize_session=False)
            
            # Delete the IR
            db.delete(ir)
            
            # Update ticket: remove IR tracking if this was the only IR
            if ticket:
                # Check if there are other IRs for this ticket
                other_irs = db.query(IncidentReport).filter(
                    IncidentReport.ticket_id == ticket_id,
                    IncidentReport.id != ir_uuid
                ).count()
                
                if other_irs == 0:
                    # No other IRs, so mark ticket as having no open IR
                    ticket.has_ir = False
                    ticket.ir_number = None
                    ticket.ir_raised_at = None
                    ticket.ir_closed_at = None
            
            db.commit()
            
            logger.info(f"✓ IR deleted: {ir_number}")
            
            return {
                "id": ir_id,
                "ir_number": ir_number,
                "ticket_id": str(ticket_id),
                "message": f"IR {ir_number} deleted successfully"
            }
            
        except NotFoundError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete IR: {e}")
            raise ValidationError(f"Failed to delete IR: {str(e)}")
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
                "last_vendor_update": to_iso_string(ir.last_vendor_update) if ir.last_vendor_update else None,
                "updated_at": to_iso_string(ir.updated_at)
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
        closed_by_user_id: Optional[str] = None,
        resolved_at: Optional[datetime] = None  # NEW: Accept closure date
    ) -> Dict[str, Any]:
        """Close an Incident Report"""
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
            
            ir.status = "closed"
            ir.notes = resolution_notes or ir.notes
            ir.resolved_at = resolved_at if resolved_at else datetime.utcnow()  # Use provided date or current time
            ir.updated_by_user_id = UUID(closed_by_user_id) if closed_by_user_id else ir.created_by_user_id
            ticket.ir_closed_at = ir.resolved_at  # Set ticket closure date to match IR
            db.flush()
            
            # Log IR event
            ir_event = IREvent(
                incident_report_id=ir.id,
                event_type="closed",
                actor_user_id=UUID(closed_by_user_id) if closed_by_user_id else ir.created_by_user_id,
                old_status=ir.status,
                new_status="closed",
                notes=resolution_notes,
                payload={
                    "resolved_at": to_iso_string(ir.resolved_at)
                }
            )
            db.add(ir_event)
            db.commit()
            
            logger.info(f"✓ IR {ir.ir_number} closed")
            
            return {
                "id": str(ir.id),
                "ir_number": ir.ir_number,
                "status": ir.status,
                "resolved_at": to_iso_string(ir.resolved_at) if ir.resolved_at else None,
            }
            
        except (ValidationError, NotFoundError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to close IR: {e}")
            raise ValidationError(f"Failed to close IR: {str(e)}")
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
                    "raised_at": to_iso_string(ir.raised_at),
                    "expected_resolution_date": to_iso_string(ir.expected_resolution_date) if ir.expected_resolution_date else None,
                    "resolved_at": to_iso_string(ir.resolved_at) if ir.resolved_at else None,
                }
                for ir in irs
            ]
            
        except Exception as e:
            logger.error(f"Failed to get ticket IRs: {e}")
            return []
        finally:
            db.close()
    
    
    @staticmethod
    def open_ir(
        ticket_id: str,
        ir_number: str,
        vendor: str = "siemens",
        expected_resolution_date: Optional[datetime] = None,
        ir_raised_at: Optional[datetime] = None,  # NEW: Accept ir_raised_at parameter
        notes: Optional[str] = None,
        closed_at: Optional[datetime] = None,
        created_by_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Open an Incident Report for a ticket (may already be closed if importing legacy data)"""
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            
            # Verify ticket exists
            ticket = db.query(Ticket).filter(Ticket.id == ticket_uuid).first()
            if not ticket:
                raise NotFoundError("Ticket not found")
            
            # Check if IR already exists FOR THIS TICKET (not globally)
            existing_ir = db.query(IncidentReport).filter(
                IncidentReport.ticket_id == ticket_uuid,
                IncidentReport.ir_number == ir_number
            ).first()
            if existing_ir:
                raise ValidationError(f"IR {ir_number} already exists for this ticket")
            
            # Determine if IR will be open or closed
            ir_status = "closed" if closed_at else "open"
            
            # Create IR
            ir = IncidentReport(
                ticket_id=ticket_uuid,
                ir_number=ir_number.strip(),
                vendor=vendor.lower(),
                expected_resolution_date=expected_resolution_date,
                notes=notes,
                created_by_user_id=UUID(created_by_user_id) if created_by_user_id else ticket.raised_by_user_id,
                status=ir_status,
                resolved_at=closed_at  # Set closure date if provided
            )
            
            db.add(ir)
            db.flush()
            
            ticket.has_ir = True  # Mark ticket as having an IR (open or closed)
            ticket.ir_number = ir_number.strip()
            # Use the passed ir_raised_at if provided, otherwise use current time
            ticket.ir_raised_at = ir_raised_at if ir_raised_at else datetime.utcnow()
            ticket.ir_expected_resolution_date = expected_resolution_date
            ticket.ir_notes = notes
            ticket.ir_closed_at = closed_at  # Track when IR was closed on ticket
            db.flush()
            
            # Log IR event
            ir_event = IREvent(
                incident_report_id=ir.id,
                event_type="ir_opened",
                actor_user_id=UUID(created_by_user_id) if created_by_user_id else ticket.raised_by_user_id,
                new_status=ir_status,
                notes=f"IR opened for ticket {ticket.ticket_no}" + (f" (already closed at {to_iso_string(closed_at)})" if closed_at else ""),
                payload={
                    "ir_number": ir_number,
                    "vendor": vendor,
                    "expected_resolution_date": to_iso_string(expected_resolution_date) if expected_resolution_date else None,
                    "ir_raised_at": to_iso_string(ir_raised_at) if ir_raised_at else None,
                    "resolved_at": to_iso_string(closed_at) if closed_at else None
                }
            )
            db.add(ir_event)
            db.commit()
            
            status_note = f" (already closed at {to_iso_string(closed_at)})" if closed_at else ""
            logger.info(f"✓ IR opened: {ir_number} for ticket {ticket.ticket_no}{status_note}")
            
            return {
                "id": str(ir.id),
                "ir_number": ir.ir_number,
                "ticket_id": ticket_id,
                "ticket_no": ticket.ticket_no,
                "company_id": str(ticket.company_id),
                "vendor": ir.vendor,
                "status": ir.status,
                "expected_resolution_date": to_iso_string(ir.expected_resolution_date) if ir.expected_resolution_date else None,
                "resolved_at": to_iso_string(ir.resolved_at) if ir.resolved_at else None,
                "created_at": to_iso_string(ir.created_at)
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