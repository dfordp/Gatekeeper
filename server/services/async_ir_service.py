# server/services/async_ir_service.py
"""
REPLACEMENT VERSION - No asyncio.to_thread() calls
Fully async IR service using AsyncSessionLocal
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, date
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.async_database import AsyncSessionLocal
from core.database import IncidentReport, Ticket
from core.logger import get_logger
from utils.exceptions import NotFoundError, ValidationError

logger = get_logger(__name__)


class AsyncIRService:
    """Async Incident Report service - NO thread pool wrapping"""
    
    @staticmethod
    async def delete_ir(ir_id: str) -> Dict[str, Any]:
        """Delete an Incident Report asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                ir = await session.get(IncidentReport, UUID(ir_id))
                if not ir:
                    raise NotFoundError(f"IR {ir_id} not found")
                
                await session.delete(ir)
                await session.commit()
                
                logger.info(f"✓ IR deleted: {ir_id}")
                return {
                    "success": True,
                    "ir_id": ir_id,
                    "message": "IR deleted successfully"
                }
            
            except NotFoundError:
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Error deleting IR: {e}")
                raise ValidationError(f"Failed to delete IR: {str(e)}")
    
    @staticmethod
    async def update_ir_status(
        ir_id: str,
        status: str,
        vendor_status: Optional[str] = None,
        vendor_notes: Optional[str] = None,
        notes: Optional[str] = None,
        updated_by_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update IR status and vendor information asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                ir = await session.get(IncidentReport, UUID(ir_id))
                if not ir:
                    raise NotFoundError(f"IR {ir_id} not found")
                
                # Validate status
                valid_statuses = ["open", "in_progress", "resolved", "closed"]
                if status not in valid_statuses:
                    raise ValidationError(f"Invalid status: {status}")
                
                # Update fields
                ir.status = status
                if vendor_status:
                    ir.vendor_status = vendor_status
                if vendor_notes:
                    ir.vendor_notes = vendor_notes
                if notes:
                    ir.notes = notes
                
                ir.last_vendor_update = date.today()
                session.add(ir)
                await session.commit()
                
                logger.info(f"✓ IR {ir_id} status updated to {status}")
                
                return {
                    "success": True,
                    "ir_id": ir_id,
                    "status": ir.status,
                    "vendor_status": ir.vendor_status,
                    "message": "IR status updated"
                }
            
            except (NotFoundError, ValidationError):
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Error updating IR status: {e}")
                raise ValidationError(f"Failed to update IR: {str(e)}")
    
    @staticmethod
    async def close_ir(
        ir_id: str,
        resolution_notes: Optional[str] = None,
        closed_at: Optional[str] = None,
        closed_by_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Close an Incident Report asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                ir = await session.get(IncidentReport, UUID(ir_id))
                if not ir:
                    raise NotFoundError(f"IR {ir_id} not found")
                
                ir.status = "closed"
                ir.resolved_at = date.today()
                if resolution_notes:
                    ir.notes = resolution_notes
                
                session.add(ir)
                await session.commit()
                
                logger.info(f"✓ IR {ir_id} closed")
                
                return {
                    "success": True,
                    "ir_id": ir_id,
                    "status": "closed",
                    "resolved_at": str(ir.resolved_at),
                    "message": "IR closed successfully"
                }
            
            except NotFoundError:
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Error closing IR: {e}")
                raise ValidationError(f"Failed to close IR: {str(e)}")
    
    @staticmethod
    async def get_ticket_irs(ticket_id: str) -> List[Dict[str, Any]]:
        """Get all IRs for a ticket asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                result = await session.execute(
                    select(IncidentReport).where(
                        IncidentReport.ticket_id == UUID(ticket_id)
                    )
                )
                irs = result.scalars().all()
                
                return [
                    {
                        "id": str(ir.id),
                        "ir_number": ir.ir_number,
                        "status": ir.status,
                        "vendor": ir.vendor,
                        "raised_at": str(ir.raised_at),
                        "resolved_at": str(ir.resolved_at) if ir.resolved_at else None
                    }
                    for ir in irs
                ]
            
            except Exception as e:
                logger.error(f"Error fetching IRs for ticket {ticket_id}: {e}")
                raise ValidationError(f"Failed to fetch IRs: {str(e)}")
    
    @staticmethod
    async def open_ir(
        ticket_id: str,
        ir_number: str,
        vendor: str = "siemens",
        expected_resolution_date: Optional[str] = None,
        ir_raised_at: Optional[str] = None,
        created_by_user_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Open an Incident Report asynchronously"""
        async with AsyncSessionLocal() as session:
            try:
                # Verify ticket exists
                ticket = await session.get(Ticket, UUID(ticket_id))
                if not ticket:
                    raise NotFoundError(f"Ticket {ticket_id} not found")
                
                # Create IR
                ir = IncidentReport(
                    id=UUID(''),  # Will be auto-generated
                    ticket_id=UUID(ticket_id),
                    ir_number=ir_number,
                    vendor=vendor or "siemens",
                    status="open",
                    raised_at=date.today(),
                    notes=notes
                )
                
                session.add(ir)
                await session.flush()
                
                # Update ticket's IR tracking
                ticket.has_ir = True
                ticket.ir_number = ir_number
                ticket.ir_raised_at = date.today()
                session.add(ticket)
                
                await session.commit()
                
                logger.info(f"✓ IR {ir_number} opened for ticket {ticket_id}")
                
                return {
                    "success": True,
                    "ir_id": str(ir.id),
                    "ir_number": ir.ir_number,
                    "status": "open",
                    "message": "IR opened successfully"
                }
            
            except NotFoundError:
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Error opening IR: {e}")
                raise ValidationError(f"Failed to open IR: {str(e)}")