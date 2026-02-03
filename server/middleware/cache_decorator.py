# server/middleware/cache_decorator.py
"""
Cache decorators for FastAPI endpoints

Provides convenient decorators for caching read endpoints and invalidating on mutations.

Usage:
    @router.get("/api/tickets")
    @cache_endpoint(ttl=30, tag="ticket:list", key_params=["company_id"])
    async def get_tickets(company_id: str):
        return TicketService.get_tickets(company_id)
    
    @router.post("/api/tickets")
    @invalidate_on_mutation(tags=["ticket:list"])
    async def create_ticket(request: CreateTicketRequest):
        return TicketCreationService.create_ticket(request)
"""

import hashlib
import functools
import json
import inspect
from typing import Optional, List, Callable, Any
from datetime import datetime

from core.logger import get_logger
from core.cache_config import get_ttl
from services.redis_cache_service import get_cache
from services.cache_key_generator import CacheKeyGenerator
from pydantic import BaseModel

logger = get_logger(__name__)


def generate_cache_key(
    endpoint: str,
    key_params: Optional[List[str]] = None,
    request_body: Optional[BaseModel] = None,
    request_body_fields: Optional[List[str]] = None,
    **kwargs
) -> str:
    """
    Generate cache key from endpoint and parameters
    
    Supports:
    - Simple path/query parameters
    - Pydantic request body objects
    - Hash-based queries (for semantic search, etc.)
    
    Args:
        endpoint: Endpoint identifier (e.g., "search:similar")
        key_params: List of parameter names to include in key
        request_body: Optional Pydantic model instance
        request_body_fields: Fields to include from request body
        **kwargs: Parameter values
        
    Returns:
        Cache key string
        
    Examples:
        # Simple parameters
        key = generate_cache_key(
            "ticket:list",
            key_params=["company_id", "status"],
            company_id="abc123",
            status="open"
        )
        # Result: "endpoint:ticket:list:company_id-abc123:status-open"
        
        # With request body
        class SearchRequest(BaseModel):
            query: str
            limit: int
        
        req = SearchRequest(query="error", limit=5)
        key = generate_cache_key(
            "search:similar",
            key_params=["company_id"],
            request_body=req,
            request_body_fields=["query", "limit"],
            company_id="abc123"
        )
        # Result: "endpoint:search:similar:company_id-abc123:query_hash-a1b2c3d4"
    """
    base_key = endpoint
    key_parts = []
    
    # Add simple parameter parts
    if key_params:
        for param in key_params:
            value = kwargs.get(param)
            if value is not None:
                key_parts.append(f"{param}-{value}")
    
    # Add request body hash
    if request_body:
        body_hash = CacheKeyGenerator.generate_from_request_body(
            request_body,
            include_fields=request_body_fields
        )
        key_parts.append(f"body-{body_hash}")
    
    # Build final key
    if key_parts:
        base_key += ":" + ":".join(key_parts)
    
    return base_key

def cache_endpoint(
    ttl: Optional[int] = None,
    tag: Optional[str] = None,
    tags: Optional[List[str]] = None,
    key_params: Optional[List[str]] = None,
    endpoint_name: Optional[str] = None
):
    """
    Decorator to cache endpoint responses
    
    Args:
        ttl: Time to live in seconds (or CacheTTL enum value name)
        tag: Single tag for invalidation
        tags: List of tags for invalidation
        key_params: List of parameter names to include in cache key
        endpoint_name: Custom endpoint name for cache key (defaults to function name)
        
    Usage:
        @cache_endpoint(ttl=30, tag="ticket:list", key_params=["company_id"])
        async def get_tickets(company_id: str):
            pass
    """
    
    # Normalize TTL
    if isinstance(ttl, str):
        ttl = get_ttl(ttl)
    elif ttl is None:
        ttl = 60
    
    # Normalize tags
    all_tags = []
    if tag:
        all_tags.append(tag)
    if tags:
        all_tags.extend(tags)
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            # Determine cache key
            endpoint_id = endpoint_name or func.__name__
            cache_key = generate_cache_key(
                f"endpoint:{endpoint_id}",
                key_params,
                **kwargs
            )
            
            # Try to get from cache
            cache = await get_cache()
            cached_value = await cache.get(cache_key)
            
            if cached_value is not None:
                logger.debug(f"Cache HIT: {cache_key}")
                return cached_value
            
            # Not in cache, execute function
            logger.debug(f"Cache MISS: {cache_key}")
            result = await func(*args, **kwargs)
            
            # Store in cache with tags
            await cache.set(
                key=cache_key,
                value=result,
                ttl=ttl,
                tags=all_tags
            )
            
            return result
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            # For sync functions, return without caching
            logger.warning(f"Cache decorator applied to sync function {func.__name__}, caching disabled")
            return func(*args, **kwargs)
        
        # Return appropriate wrapper based on function type
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

def cache_endpoint_with_body(
    ttl: Optional[int] = None,
    tag: Optional[str] = None,
    tags: Optional[List[str]] = None,
    key_params: Optional[List[str]] = None,
    request_body_fields: Optional[List[str]] = None,
    endpoint_name: Optional[str] = None
):
    """
    Enhanced cache decorator for endpoints with request body
    
    Args:
        ttl: Time to live in seconds
        tag: Single tag for invalidation
        tags: List of tags for invalidation
        key_params: Path/query parameter names to include
        request_body_fields: Request body fields to hash
        endpoint_name: Custom endpoint name
        
    Usage:
        class SearchRequest(BaseModel):
            query: str
            limit: int
            threshold: float
        
        @router.post("/search")
        @cache_endpoint_with_body(
            ttl=120,
            tag="search:similar",
            key_params=["company_id"],
            request_body_fields=["query", "limit", "threshold"]
        )
        async def search(request: SearchRequest, company_id: str):
            # Cache key will include hashed request body
            pass
    """
    
    # Normalize TTL
    if isinstance(ttl, str):
        ttl = get_ttl(ttl)
    elif ttl is None:
        ttl = 60
    
    # Normalize tags
    all_tags = []
    if tag:
        all_tags.append(tag)
    if tags:
        all_tags.extend(tags)
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            # Extract request body from kwargs
            request_body = None
            for arg in args:
                if isinstance(arg, BaseModel):
                    request_body = arg
                    break
            
            # If not found in args, check kwargs
            if not request_body:
                for value in kwargs.values():
                    if isinstance(value, BaseModel):
                        request_body = value
                        break
            
            # Generate cache key with request body
            endpoint_id = endpoint_name or func.__name__
            cache_key = generate_cache_key(
                f"endpoint:{endpoint_id}",
                key_params,
                request_body=request_body,
                request_body_fields=request_body_fields,
                **kwargs
            )
            
            # Try to get from cache
            cache = await get_cache()
            cached_value = await cache.get(cache_key)
            
            if cached_value is not None:
                logger.debug(f"Cache HIT: {cache_key}")
                return cached_value
            
            # Not in cache, execute function
            logger.debug(f"Cache MISS: {cache_key}")
            result = await func(*args, **kwargs)
            
            # Store in cache with tags
            await cache.set(
                key=cache_key,
                value=result,
                ttl=ttl,
                tags=all_tags
            )
            
            return result
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            logger.warning(f"Cache decorator applied to sync function {func.__name__}, caching disabled")
            return func(*args, **kwargs)
        
        # Return appropriate wrapper based on function type
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def invalidate_on_mutation(
    tags: Optional[List[str]] = None,
    tag: Optional[str] = None,
    cascade: bool = True
):
    """
    Decorator to invalidate cache on mutation endpoints
    
    Args:
        tags: List of tags to invalidate
        tag: Single tag to invalidate
        cascade: Whether to invalidate pattern-based tags (e.g., "search:*")
        
    Usage:
        @invalidate_on_mutation(tags=["ticket:list", "analytics"])
        async def create_ticket(request: CreateTicketRequest):
            pass
    """
    
    # Normalize tags
    all_tags = []
    if tag:
        all_tags.append(tag)
    if tags:
        all_tags.extend(tags)
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            # Execute the mutation first
            result = await func(*args, **kwargs)
            
            # Invalidate cache after successful execution
            cache = await get_cache()
            
            for tag_to_invalidate in all_tags:
                if "*" in tag_to_invalidate:
                    # Pattern-based invalidation
                    pattern = tag_to_invalidate.replace("*", "*")
                    count = await cache.invalidate_by_pattern(pattern)
                    logger.info(f"Cache invalidated pattern '{pattern}': {count} keys removed")
                else:
                    # Tag-based invalidation
                    count = await cache.invalidate_by_tag(tag_to_invalidate)
                    if count > 0:
                        logger.info(f"Cache invalidated tag '{tag_to_invalidate}': {count} keys removed")
            
            return result
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            return func(*args, **kwargs)
        
        # Return appropriate wrapper
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def cache_key_from_params(
    *param_names: str
):
    """
    Decorator to customize cache key generation
    
    Usage:
        @cache_key_from_params("company_id", "status")
        @cache_endpoint(ttl=30)
        async def get_tickets(company_id: str, status: str, page: int):
            pass
    """
    
    def decorator(func: Callable) -> Callable:
        func._cache_key_params = list(param_names)
        return func
    
    return decorator

