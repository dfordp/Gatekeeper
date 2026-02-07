# server/services/timeout_wrapper.py
"""
Timeout wrapper for long-running async operations
Prevents request hangs and cascading timeouts
"""

import asyncio
from typing import Callable, Any, Optional
from functools import wraps
from core.logger import get_logger

logger = get_logger(__name__)


class OperationTimeout(Exception):
    """Raised when operation exceeds timeout"""
    pass


def with_timeout(timeout_seconds: float, operation_name: str = "operation"):
    """
    Decorator to wrap async functions with timeout protection.
    
    Args:
        timeout_seconds: Timeout in seconds
        operation_name: Name for logging
        
    Usage:
        @with_timeout(60, "ticket_creation")
        async def create_ticket(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout_seconds
                )
                return result
            
            except asyncio.TimeoutError:
                logger.error(
                    f"⏱️ {operation_name} timeout after {timeout_seconds}s"
                )
                raise OperationTimeout(
                    f"{operation_name} exceeded {timeout_seconds}s timeout"
                )
            
            except Exception:
                raise
        
        return wrapper
    
    return decorator


async def run_with_timeout(
    coro,
    timeout_seconds: float,
    operation_name: str = "operation"
) -> Any:
    """
    Run a coroutine with timeout protection (inline usage).
    
    Args:
        coro: Coroutine to execute
        timeout_seconds: Timeout in seconds
        operation_name: Name for logging
        
    Returns:
        Result from coroutine
        
    Raises:
        asyncio.TimeoutError: If timeout exceeded
        
    Usage:
        result = await run_with_timeout(
            create_ticket_impl(...),
            timeout_seconds=60,
            operation_name="ticket_creation"
        )
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    
    except asyncio.TimeoutError:
        logger.error(
            f"⏱️ {operation_name} timeout after {timeout_seconds}s"
        )
        raise OperationTimeout(
            f"{operation_name} exceeded {timeout_seconds}s timeout"
        )