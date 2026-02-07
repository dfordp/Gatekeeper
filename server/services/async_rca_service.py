# server/services/async_rca_service.py
"""Async wrapper for RCAService - handles root cause analysis operations asynchronously"""
import asyncio
from typing import Dict, Any, Optional, List

from services.rca_service import RCAService
from core.logger import get_logger

logger = get_logger(__name__)


class AsyncRCAService:
    """Async wrapper for RCAService using thread pool execution"""
    
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
        """Create or update RCA asynchronously"""
        return await asyncio.to_thread(
            RCAService.create_or_update_rca,
            ticket_id,
            root_cause_description,
            contributing_factors,
            prevention_measures,
            resolution_steps,
            rca_attachment_paths,
            created_by_user_id,
            admin_id
        )
    
    @staticmethod
    async def get_rca_with_details(ticket_id: str) -> Optional[Dict[str, Any]]:
        """Get RCA with details asynchronously"""
        return await asyncio.to_thread(
            RCAService.get_rca_with_details,
            ticket_id
        )
    
    @staticmethod
    async def search_rcas_by_keyword(
        company_id: str,
        keyword: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search RCAs by keyword asynchronously"""
        return await asyncio.to_thread(
            RCAService.search_rcas_by_keyword,
            company_id,
            keyword,
            limit
        )