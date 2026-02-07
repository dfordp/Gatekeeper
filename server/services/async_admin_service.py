# server/services/async_admin_service.py
"""
Async AdminManagementService wrapper - handles admin management operations asynchronously
Uses timeout protection to prevent blocking the event loop
"""

import asyncio
from typing import Dict, Any, Optional
from services.timeout_wrapper import run_with_timeout, OperationTimeout
from services.admin_service import AdminManagementService
from core.logger import get_logger

logger = get_logger(__name__)


class AsyncAdminService:
    """Async wrapper for AdminManagementService with timeout protection (NO asyncio.to_thread)"""
    
    @staticmethod
    async def create_admin(
        email: str,
        full_name: str,
        role: str = "manager",
        created_by_admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new admin user asynchronously with timeout protection.
        Timeout: 15 seconds
        
        Args:
            email: Admin email
            full_name: Admin full name
            role: Admin role (admin, manager, analyst)
            created_by_admin_id: ID of admin creating this admin
            
        Returns:
            Dict with admin details and temporary password
        """
        try:
            result = await run_with_timeout(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    AdminManagementService.create_admin,
                    email,
                    full_name,
                    role,
                    created_by_admin_id
                ),
                timeout_seconds=15,
                operation_name="admin_create"
            )
            return result
        except OperationTimeout:
            logger.error(f"Admin creation timed out for email: {email}")
            raise
    
    @staticmethod
    async def get_admins(limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        Get paginated list of admins asynchronously with timeout protection.
        Timeout: 15 seconds
        """
        try:
            result = await run_with_timeout(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    AdminManagementService.get_admins,
                    limit,
                    offset
                ),
                timeout_seconds=15,
                operation_name="admin_get_list"
            )
            return result
        except OperationTimeout:
            logger.error(f"Admin list retrieval timed out")
            raise
    
    @staticmethod
    async def update_admin(
        admin_id: str,
        full_name: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        updated_by_admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update admin details asynchronously with timeout protection.
        Timeout: 15 seconds
        """
        try:
            result = await run_with_timeout(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    AdminManagementService.update_admin,
                    admin_id,
                    full_name,
                    role,
                    is_active,
                    updated_by_admin_id
                ),
                timeout_seconds=15,
                operation_name="admin_update"
            )
            return result
        except OperationTimeout:
            logger.error(f"Admin update timed out for admin_id: {admin_id}")
            raise
    
    @staticmethod
    async def delete_admin(
        admin_id: str,
        deleted_by_admin_id: Optional[str] = None
    ) -> bool:
        """
        Delete an admin asynchronously with timeout protection.
        Timeout: 15 seconds
        """
        try:
            result = await run_with_timeout(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    AdminManagementService.delete_admin,
                    admin_id,
                    deleted_by_admin_id
                ),
                timeout_seconds=15,
                operation_name="admin_delete"
            )
            return result
        except OperationTimeout:
            logger.error(f"Admin deletion timed out for admin_id: {admin_id}")
            raise