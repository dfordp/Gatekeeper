# server/services/async_admin_service.py
"""Async wrapper for AdminManagementService - handles admin management operations asynchronously"""
import asyncio
from typing import Dict, Any, Optional

from services.admin_service import AdminManagementService
from core.logger import get_logger

logger = get_logger(__name__)


class AsyncAdminService:
    """Async wrapper for AdminManagementService using thread pool execution"""
    
    @staticmethod
    async def create_admin(
        email: str,
        full_name: str,
        role: str = "manager",
        created_by_admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new admin user asynchronously.
        
        Args:
            email: Admin email
            full_name: Admin full name
            role: Admin role (admin, manager, analyst)
            created_by_admin_id: ID of admin creating this admin
            
        Returns:
            Dict with admin details and temporary password
        """
        return await asyncio.to_thread(
            AdminManagementService.create_admin,
            email,
            full_name,
            role,
            created_by_admin_id
        )
    
    @staticmethod
    async def get_admins(limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get paginated list of admins asynchronously"""
        return await asyncio.to_thread(
            AdminManagementService.get_admins,
            limit,
            offset
        )
    
    @staticmethod
    async def update_admin(
        admin_id: str,
        full_name: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        updated_by_admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update admin details asynchronously"""
        return await asyncio.to_thread(
            AdminManagementService.update_admin,
            admin_id,
            full_name,
            role,
            is_active,
            updated_by_admin_id
        )
    
    @staticmethod
    async def delete_admin(admin_id: str, deleted_by_admin_id: Optional[str] = None) -> bool:
        """Delete an admin asynchronously"""
        return await asyncio.to_thread(
            AdminManagementService.delete_admin,
            admin_id,
            deleted_by_admin_id
        )