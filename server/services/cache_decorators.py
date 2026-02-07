# server/services/cache_decorators.py
"""
Cache decorators for automatic query caching in route handlers
Simplifies cache integration without boilerplate

Usage:
    @cached_route("ticket:list", ttl=30, tags=["ticket:list"])
    async def list_tickets(request: Request):
        # Your handler code
        return tickets
"""

import functools
import inspect
import json
from typing import Callable, Any, Optional, List
from uuid import UUID

from core.logger import get_logger
from services.redis_cache_service import get_cache

logger = get_logger(__name__)


def cached_route(
    cache_key_base: str,
    ttl: int = 300,
    tags: Optional[List[str]] = None,
    cache_params: Optional[List[str]] = None
):
    """
    Decorator for caching route handler results
    
    Args:
        cache_key_base: Base cache key (e.g., "ticket:list")
        ttl: Time to live in seconds
        tags: Cache tags for invalidation
        cache_params: Parameter names to include in cache key (None = use all)
    
    Example:
        @app.get("/api/tickets")
        @cached_route("ticket:list", ttl=30, tags=["ticket:list"])
        async def list_tickets(company_id: str, status: Optional[str] = None):
            return await TicketService.list(company_id, status)
    """
    tags = tags or []
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cache = await get_cache()
            
            if not cache.enabled:
                return await func(*args, **kwargs)
            
            # Build cache key from function parameters
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            # Generate key params
            key_params = {}
            for param_name, param_value in bound_args.arguments.items():
                if cache_params and param_name not in cache_params:
                    continue
                if param_name in ['self', 'client', 'request', 'db']:
                    continue
                
                # Convert UUID to string
                if isinstance(param_value, UUID):
                    param_value = str(param_value)
                
                if param_value is not None:
                    key_params[param_name] = str(param_value)
            
            # Build full cache key
            cache_key = cache_key_base
            for k, v in sorted(key_params.items()):
                cache_key = cache_key.replace(f"{{{k}}}", v)
            
            # Try cache
            cached = await cache.get(cache_key)
            if cached:
                logger.debug(f"Route cache HIT: {cache_key}")
                return cached
            
            # Execute handler
            logger.debug(f"Route cache MISS: {cache_key}")
            result = await func(*args, **kwargs)
            
            # Cache result
            await cache.set(cache_key, result, ttl=ttl, tags=tags)
            
            return result
        
        return wrapper
    
    return decorator


def cache_invalidate(*invalidate_tags: str):
    """
    Decorator for route handlers that invalidate cache
    
    Example:
        @app.post("/api/tickets")
        @cache_invalidate("ticket:list", "analytics")
        async def create_ticket(ticket: TicketCreate):
            return await TicketService.create(ticket)
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Execute handler first
            result = await func(*args, **kwargs)
            
            # Then invalidate cache
            cache = await get_cache()
            if cache.enabled:
                for tag in invalidate_tags:
                    await cache.invalidate_by_tag(tag)
                    logger.info(f"Cache invalidated: {tag}")
            
            return result
        
        return wrapper
    
    return decorator