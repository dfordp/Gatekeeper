# server/services/async_ir_service.py
"""Async wrapper for IRService - handles incident report operations asynchronously"""
import asyncio
from typing import Dict, Any, Optional, List

from services.ir_service import IRService
from core.logger import get_logger

logger = get_logger(__name__)


class AsyncIRService:
    """Async wrapper for IRService using thread pool execution"""
    
    @staticmethod
    async def delete_ir(ir_id: str) -> Dict[str, Any]:
        """Delete an Incident Report asynchronously"""
        return await asyncio.to_thread(
            IRService.delete_ir,
            ir_id
        )
    
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
        return await asyncio.to_thread(
            IRService.update_ir_status,
            ir_id,
            status,
            vendor_status,
            vendor_notes,
            notes,
            updated_by_user_id
        )
    
    @staticmethod
    async def close_ir(
        ir_id: str,
        resolution_notes: Optional[str] = None,
        closed_at: Optional[str] = None,
        closed_by_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Close an Incident Report asynchronously"""
        return await asyncio.to_thread(
            IRService.close_ir,
            ir_id,
            resolution_notes,
            closed_at,
            closed_by_user_id
        )
    
    @staticmethod
    async def get_ticket_irs(ticket_id: str) -> List[Dict[str, Any]]:
        """Get all IRs for a ticket asynchronously"""
        return await asyncio.to_thread(
            IRService.get_ticket_irs,
            ticket_id
        )
    
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
        return await asyncio.to_thread(
            IRService.open_ir,
            ticket_id,
            ir_number,
            vendor,
            expected_resolution_date,
            ir_raised_at,
            created_by_user_id,
            notes
        )