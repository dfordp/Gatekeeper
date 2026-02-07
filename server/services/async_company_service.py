# server/services/async_company_service.py
"""Async wrapper for CompanyService - handles company management operations asynchronously"""
import asyncio
from typing import Dict, Any, Optional

from services.company_service import CompanyService
from core.logger import get_logger

logger = get_logger(__name__)


class AsyncCompanyService:
    """Async wrapper for CompanyService using thread pool execution"""
    
    @staticmethod
    async def create_company(
        name: str,
        created_by_admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new company asynchronously.
        
        Args:
            name: Company name (must be unique)
            created_by_admin_id: Admin creating the company
            
        Returns:
            Dict with company details
        """
        return await asyncio.to_thread(
            CompanyService.create_company,
            name,
            created_by_admin_id
        )
    
    @staticmethod
    async def get_companies(limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get paginated list of companies asynchronously"""
        return await asyncio.to_thread(
            CompanyService.get_companies,
            limit,
            offset
        )
    
    @staticmethod
    async def get_company_by_id(company_id: str) -> Dict[str, Any]:
        """Get company by ID asynchronously"""
        return await asyncio.to_thread(
            CompanyService.get_company_by_id,
            company_id
        )