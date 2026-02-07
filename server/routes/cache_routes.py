# server/routes/cache_routes.py
"""
Cache monitoring and management endpoints
Provides visibility into cache performance and allows manual invalidation
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from uuid import UUID

from core.logger import get_logger
from services.redis_cache_service import get_cache
from middleware.auth_middleware import get_current_admin

logger = get_logger(__name__)
router = APIRouter(prefix="/api/cache", tags=["cache"])


@router.get("/metrics", summary="Get cache metrics")
async def get_cache_metrics(
    auth_header: str = Depends(get_current_admin)
) -> dict:
    """
    Get cache performance metrics
    
    Returns:
        - hits: Total cache hits
        - misses: Total cache misses
        - hit_rate_percent: Cache hit rate percentage
        - sets: Total cache sets
        - deletes: Total cache deletes
        - tag_invalidations: Total tag invalidations
        - errors: Total cache errors
    """
    cache = await get_cache()
    metrics = await cache.get_metrics()
    
    return {
        "status": "success",
        "cache_enabled": cache.enabled,
        "metrics": metrics
    }


@router.get("/info", summary="Get cache server info")
async def get_cache_info(
    auth_header: str = Depends(get_current_admin)
) -> dict:
    """
    Get Redis server information
    
    Returns:
        - connected: Connection status
        - memory_used: Current memory usage
        - memory_peak: Peak memory usage
        - clients: Connected clients
        - commands_processed: Total commands processed
        - uptime_seconds: Redis uptime
    """
    cache = await get_cache()
    info = await cache.get_info()
    
    return {
        "status": "success",
        "info": info
    }


@router.post("/invalidate-tag", summary="Invalidate cache by tag")
async def invalidate_by_tag(
    tag: str = Query(..., description="Tag to invalidate (e.g., 'ticket:list')"),
    auth_header: str = Depends(get_current_admin)
) -> dict:
    """
    Manually invalidate all keys with a given tag
    
    Parameters:
        - tag: Tag name (supports pattern matching with *)
    """
    cache = await get_cache()
    
    if not cache.enabled:
        raise HTTPException(status_code=400, detail="Cache is disabled")
    
    # Check for auth (admin only)
    # In production, verify this is an admin user
    
    keys_invalidated = await cache.invalidate_by_tag(tag)
    
    return {
        "status": "success",
        "tag": tag,
        "keys_invalidated": keys_invalidated
    }


@router.post("/invalidate-pattern", summary="Invalidate cache by pattern")
async def invalidate_by_pattern(
    pattern: str = Query(..., description="Pattern to match (e.g., 'ticket:*')"),
    auth_header: str = Depends(get_current_admin)
) -> dict:
    """
    Manually invalidate all keys matching a pattern
    
    Parameters:
        - pattern: Pattern to match (supports * wildcard)
    """
    cache = await get_cache()
    
    if not cache.enabled:
        raise HTTPException(status_code=400, detail="Cache is disabled")
    
    keys_invalidated = await cache.invalidate_by_pattern(pattern)
    
    return {
        "status": "success",
        "pattern": pattern,
        "keys_invalidated": keys_invalidated
    }


@router.post("/clear", summary="Clear entire cache")
async def clear_cache(
    confirm: str = Query(..., description="Must be 'yes' to confirm"),
    auth_header: str = Depends(get_current_admin)
) -> dict:
    """
    Clear entire cache (use with caution)
    
    Parameters:
        - confirm: Must be 'yes' to confirm
    """
    if confirm != "yes":
        raise HTTPException(
            status_code=400,
            detail="Must pass confirm=yes to clear cache"
        )
    
    cache = await get_cache()
    
    if not cache.enabled:
        raise HTTPException(status_code=400, detail="Cache is disabled")
    
    success = await cache.clear_all()
    
    return {
        "status": "success" if success else "failed",
        "action": "cache_clear"
    }


@router.get("/hit-rate", summary="Get cache hit rate")
async def get_hit_rate(
    auth_header: str = Depends(get_current_admin)
) -> dict:
    """Get current cache hit rate percentage"""
    cache = await get_cache()
    hit_rate = cache.get_hit_rate()
    
    return {
        "status": "success",
        "hit_rate_percent": round(hit_rate, 2),
        "interpretation": (
            "Excellent (>80%)" if hit_rate > 80
            else "Good (60-80%)" if hit_rate > 60
            else "Fair (40-60%)" if hit_rate > 40
            else "Poor (<40%)"
        )
    }