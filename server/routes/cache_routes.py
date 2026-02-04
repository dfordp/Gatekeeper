# server/routes/cache_routes.py
"""
Cache management endpoints for admin dashboard

Provides endpoints to monitor, manage, and control the caching layer.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional

from middleware.auth_middleware import get_current_admin
from utils.datetime_utils import to_iso_string
from services.redis_cache_service import get_cache
from core.cache_config import get_invalidation_tags
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/cache", tags=["Cache Management"])


@router.get("/metrics")
async def get_cache_metrics(admin_payload: dict = Depends(get_current_admin)) -> Dict[str, Any]:
    """
    Get cache metrics (hit rate, memory, etc.)
    
    Only accessible by admin users.
    """
    try:
        cache = await get_cache()
        
        metrics = await cache.get_metrics()
        info = await cache.get_info()
        
        return {
            "metrics": metrics,
            "server": info,
            "timestamp": to_iso_string(datetime.utcnow())
        }
    except Exception as e:
        logger.error(f"Failed to get cache metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear")
async def clear_cache(admin_payload: dict = Depends(get_current_admin)) -> Dict[str, Any]:
    """
    Clear entire cache (use with caution!)
    
    Only accessible by admin users.
    """
    try:
        cache = await get_cache()
        success = await cache.clear_all()
        
        if success:
            logger.warning(f"Admin {admin_payload.get('email')} cleared entire cache")
            return {
                "status": "success",
                "message": "Cache cleared successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to clear cache")
            
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/invalidate-tag")
async def invalidate_cache_tag(
    tag: str,
    admin_payload: dict = Depends(get_current_admin)
) -> Dict[str, Any]:
    """
    Invalidate cache by tag
    
    Args:
        tag: Cache tag to invalidate (e.g., "ticket:list")
        
    Only accessible by admin users.
    """
    try:
        cache = await get_cache()
        count = await cache.invalidate_by_tag(tag)
        
        logger.info(f"Admin {admin_payload.get('email')} invalidated tag '{tag}': {count} keys removed")
        
        return {
            "status": "success",
            "tag": tag,
            "keys_removed": count
        }
        
    except Exception as e:
        logger.error(f"Failed to invalidate tag '{tag}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/invalidate-pattern")
async def invalidate_cache_pattern(
    pattern: str,
    admin_payload: dict = Depends(get_current_admin)
) -> Dict[str, Any]:
    """
    Invalidate cache by key pattern
    
    Args:
        pattern: Key pattern to invalidate (e.g., "ticket:list:*")
        
    Only accessible by admin users.
    """
    try:
        cache = await get_cache()
        count = await cache.invalidate_by_pattern(pattern)
        
        logger.info(f"Admin {admin_payload.get('email')} invalidated pattern '{pattern}': {count} keys removed")
        
        return {
            "status": "success",
            "pattern": pattern,
            "keys_removed": count
        }
        
    except Exception as e:
        logger.error(f"Failed to invalidate pattern '{pattern}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/invalidate-event")
async def invalidate_on_event(
    event_type: str,
    admin_payload: dict = Depends(get_current_admin),
    **kwargs
) -> Dict[str, Any]:
    """
    Manually trigger invalidation for an event
    
    Args:
        event_type: Event type (e.g., "ticket:create", "rca:update")
        **kwargs: Event context variables
        
    Only accessible by admin users.
    """
    try:
        from core.cache_config import INVALIDATION_RULES
        
        if event_type not in INVALIDATION_RULES:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown event type: {event_type}"
            )
        
        cache = await get_cache()
        tags = get_invalidation_tags(event_type, **kwargs)
        
        total_removed = 0
        for tag in tags:
            if "*" in tag:
                count = await cache.invalidate_by_pattern(tag)
            else:
                count = await cache.invalidate_by_tag(tag)
            total_removed += count
        
        logger.info(f"Admin {admin_payload.get('email')} triggered invalidation for event '{event_type}': {total_removed} keys removed")
        
        return {
            "status": "success",
            "event_type": event_type,
            "tags": tags,
            "total_keys_removed": total_removed
        }
        
    except Exception as e:
        logger.error(f"Failed to process event invalidation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


from datetime import datetime