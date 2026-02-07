# server/services/async_rca_service.py
"""
Async RCAService wrapper - handles root cause analysis operations asynchronously
Uses timeout protection to prevent blocking the event loop
"""

import asyncio
from typing import Dict, Any, Optional, List
from services.timeout_wrapper import run_with_timeout, OperationTimeout
from services.rca_service import RCAService
from core.logger import get_logger

logger = get_logger(__name__)


class AsyncRCAService:
    """Async wrapper for RCAService with timeout protection (NO asyncio.to_thread)"""
    
    @staticmethod
    async def create_or_update_rca(
        ticket_id: str,
        root_cause_description: str,
        contributing_factors: Optional[List[str]] = None,
        prevention_measures: Optional[str] = None,
        resolution_steps: Optional[List[str]] = None,
        rca_attachment_paths: Optional[List[str]] = None,
        created_by_user_id: Optional[str] = None,
        admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create or update RCA asynchronously with timeout protection.
        Timeout: 30 seconds (batch operation)
        """
        try:
            # Use run_in_executor + timeout wrapper instead of to_thread
            result = await run_with_timeout(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    RCAService.create_or_update_rca,
                    ticket_id,
                    root_cause_description,
                    contributing_factors,
                    prevention_measures,
                    resolution_steps,
                    rca_attachment_paths,
                    created_by_user_id,
                    admin_id
                ),
                timeout_seconds=30,
                operation_name="rca_create_or_update"
            )
            return result
        except OperationTimeout:
            logger.error(f"RCA operation timed out for ticket {ticket_id}")
            raise
    
    @staticmethod
    async def get_rca_with_details(ticket_id: str) -> Optional[Dict[str, Any]]:
        """
        Get RCA with details asynchronously with timeout protection.
        Timeout: 15 seconds (read operation)
        """
        try:
            result = await run_with_timeout(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    RCAService.get_rca_with_details,
                    ticket_id
                ),
                timeout_seconds=15,
                operation_name="rca_get_details"
            )
            return result
        except OperationTimeout:
            logger.error(f"RCA get_details timed out for ticket {ticket_id}")
            raise
    
    @staticmethod
    async def search_rcas_by_keyword(
        company_id: str,
        keyword: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search RCAs by keyword asynchronously with timeout protection.
        Timeout: 20 seconds (search operation)
        """
        try:
            result = await run_with_timeout(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    RCAService.search_rcas_by_keyword,
                    company_id,
                    keyword,
                    limit
                ),
                timeout_seconds=20,
                operation_name="rca_search"
            )
            return result
        except OperationTimeout:
            logger.error(f"RCA search timed out for keyword: {keyword}")
            raise