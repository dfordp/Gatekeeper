# server/routes/cache_levels_routes.py
"""
Multi-Level Cache Routes - Phase 14

REST API endpoints for managing multi-level cache:
- View cache statistics per level
- Monitor hit rates and efficiency
- Warm cache on demand
- Invalidate by tag or pattern
- Performance analysis
"""

import logging
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from datetime import datetime


from core.async_database import get_async_db
from services.multi_level_cache import (
    MultiLevelCache,
    CacheWarmingService,
    CacheLevel
)
from middleware.auth_middleware import get_current_admin
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cache-levels", tags=["cache-levels"])

# Global cache instance (would be injected in production)
_cache_instance: Optional[MultiLevelCache] = None


def get_cache() -> MultiLevelCache:
    """Get global cache instance"""
    if not _cache_instance:
        raise HTTPException(
            status_code=503,
            detail="Multi-level cache not initialized"
        )
    return _cache_instance


@router.get("/metrics")
async def get_cache_metrics(
    _=Depends(get_current_admin),
    cache: MultiLevelCache = Depends(get_cache)
):
    """Get metrics for all cache levels"""
    try:
        metrics = cache.get_all_metrics()
        
        # Calculate overall efficiency
        l1_hits = metrics["l1"]["hits"]
        l1_misses = metrics["l1"]["misses"]
        l2_hits = metrics["l2"]["hits"]
        l2_misses = metrics["l2"]["misses"]
        
        total_requests = l1_hits + l1_misses + l2_hits + l2_misses
        total_hits = l1_hits + l2_hits
        overall_hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "overall_hit_rate": f"{overall_hit_rate:.2f}%",
            "total_requests": total_requests,
            "by_level": metrics
        }
    except Exception as e:
        logger.error(f"Error getting cache metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/l1/stats")
async def get_l1_stats(
    _=Depends(get_current_admin),
    cache: MultiLevelCache = Depends(get_cache)
):
    """Get L1 (in-process) cache statistics"""
    try:
        stats = cache.get_l1_stats()
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "level": "L1 (In-Process LRU)",
            "stats": stats,
            "health": {
                "capacity_used_percent": stats["capacity_used_percent"],
                "health_status": "healthy" if stats["capacity_used_percent"] < 80 else "warning" if stats["capacity_used_percent"] < 95 else "critical"
            }
        }
    except Exception as e:
        logger.error(f"Error getting L1 stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hierarchy")
async def get_cache_hierarchy(
    _=Depends(get_current_admin),
    cache: MultiLevelCache = Depends(get_cache)
):
    """Get cache hierarchy information"""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "hierarchy": [
            {
                "level": "L1",
                "name": "In-Process LRU Cache",
                "ttl_seconds": cache.L1_TTL,
                "scope": "Single Process",
                "max_size_mb": cache.l1.MAX_SIZE_MB,
                "eviction_policy": "LRU",
                "characteristics": ["Fastest", "Non-persistent", "Process-local"]
            },
            {
                "level": "L2",
                "name": "Redis Distributed Cache",
                "ttl_seconds": cache.L2_TTL,
                "scope": "Cluster-Wide",
                "max_size_gb": "Configurable",
                "eviction_policy": "Redis policy",
                "characteristics": ["Fast", "Distributed", "Shared"]
            },
            {
                "level": "L3",
                "name": "Database (Source of Truth)",
                "ttl_seconds": "N/A",
                "scope": "Cluster-Wide",
                "max_size_gb": "Full DB size",
                "eviction_policy": "N/A",
                "characteristics": ["Slowest", "Persistent", "Authoritative"]
            }
        ]
    }


@router.post("/warm")
async def warm_cache(
    db: AsyncSession = Depends(get_async_db),
    background_tasks: BackgroundTasks = None,
    _=Depends(get_current_admin),
    cache: MultiLevelCache = Depends(get_cache)
):
    """Warm cache with startup data"""
    try:
        warming_service = CacheWarmingService(cache, db)
        
        # Run warming in background
        if background_tasks:
            background_tasks.add_task(warming_service.warm_all)
        else:
            results = await warming_service.warm_all()
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "message": "Cache warming started in background"
        }
    except Exception as e:
        logger.error(f"Error warming cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/invalidate-tag/{tag}")
async def invalidate_by_tag(
    tag: str,
    _=Depends(get_current_admin),
    cache: MultiLevelCache = Depends(get_cache)
):
    """Invalidate all cache entries with specific tag"""
    try:
        await cache.invalidate_by_tag(tag)
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "action": "invalidate_by_tag",
            "tag": tag,
            "message": f"All entries with tag '{tag}' invalidated"
        }
    except Exception as e:
        logger.error(f"Error invalidating tag: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/efficiency-analysis")
async def get_efficiency_analysis(
    _=Depends(get_current_admin),
    cache: MultiLevelCache = Depends(get_cache)
):
    """Analyze cache efficiency and provide recommendations"""
    try:
        metrics = cache.get_all_metrics()
        
        l1_stats = metrics["l1"]
        l1_hit_rate = l1_stats["hit_rate"]
        l1_capacity = l1_stats["capacity_used_percent"]
        
        recommendations = []
        
        # L1 analysis
        if l1_hit_rate < 50:
            recommendations.append({
                "level": "L1",
                "severity": "warning",
                "issue": f"Low L1 hit rate ({l1_hit_rate:.1f}%)",
                "recommendation": "Increase L1 cache size or adjust TTL"
            })
        
        if l1_capacity > 90:
            recommendations.append({
                "level": "L1",
                "severity": "critical",
                "issue": f"L1 capacity near limit ({l1_capacity:.1f}%)",
                "recommendation": "Size is OK with LRU eviction, but monitor eviction rate"
            })
        
        # Overall health score
        overall_hit_rate = (
            l1_stats["hits"] / (l1_stats["hits"] + l1_stats["misses"]) * 100
            if (l1_stats["hits"] + l1_stats["misses"]) > 0
            else 0
        )
        
        health_score = min(100, overall_hit_rate * 1.2)  # Weighted toward hit rate
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "health_score": f"{health_score:.1f}/100",
            "overall_hit_rate": f"{overall_hit_rate:.1f}%",
            "issues_count": len(recommendations),
            "recommendations": recommendations
        }
    except Exception as e:
        logger.error(f"Error analyzing cache efficiency: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bloom-filter-stats")
async def get_bloom_filter_stats(
    _=Depends(get_current_admin),
    cache: MultiLevelCache = Depends(get_cache)
):
    """Get Bloom filter statistics for negative caching"""
    try:
        bloom = cache.l1.bloom
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "bloom_filter": {
                "size_bits": bloom.size,
                "hash_functions": bloom.hash_count,
                "bits_set": len(bloom.bits),
                "false_positive_rate": f"{bloom.false_positive_rate():.4f}%",
                "true_positives": bloom.true_positives,
                "false_positives": bloom.false_positives
            }
        }
    except Exception as e:
        logger.error(f"Error getting Bloom filter stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))