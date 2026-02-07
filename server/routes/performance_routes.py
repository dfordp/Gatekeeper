# server/routes/performance_routes.py
"""Performance monitoring and metrics endpoints"""
from fastapi import APIRouter, HTTPException, Depends
from middleware.auth_middleware import get_current_admin
from core.db_performance_monitor import get_query_monitor
from core.connection_pool_manager import get_pool_monitor, OptimizedPoolConfig
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/performance", tags=["Performance"])


@router.get("/query-stats")
async def get_query_stats(
    window_minutes: int = 5,
    admin_payload: dict = Depends(get_current_admin)
):
    """
    Get database query performance statistics.
    
    Args:
        window_minutes: Time window for analysis (default 5 minutes)
        
    Returns:
        Query statistics including slow queries
    """
    try:
        monitor = get_query_monitor()
        stats = monitor.get_stats(window_minutes=window_minutes)
        
        return {
            "status": "success",
            "data": stats,
            "window_minutes": window_minutes
        }
    except Exception as e:
        logger.error(f"Error getting query stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get query statistics")


@router.get("/slow-queries")
async def get_slow_queries(
    limit: int = 20,
    admin_payload: dict = Depends(get_current_admin)
):
    """
    Get slowest queries from history.
    
    Args:
        limit: Number of queries to return
        
    Returns:
        List of slowest queries
    """
    try:
        monitor = get_query_monitor()
        slow = monitor.get_slow_queries(limit=limit)
        
        return {
            "status": "success",
            "queries": slow,
            "total": len(slow)
        }
    except Exception as e:
        logger.error(f"Error getting slow queries: {e}")
        raise HTTPException(status_code=500, detail="Failed to get slow queries")


@router.get("/connection-pool")
async def get_connection_pool_stats(
    admin_payload: dict = Depends(get_current_admin)
):
    """
    Get connection pool statistics.
    
    Returns:
        Current pool utilization and health status
    """
    try:
        pool_monitor = get_pool_monitor()
        stats = pool_monitor.get_stats()
        alerts = pool_monitor.get_recent_alerts(limit=5)
        
        return {
            "status": "success",
            "pool": stats,
            "recent_alerts": alerts,
            "health": "critical" if stats["utilization_percent"] > 95 else (
                "warning" if stats["utilization_percent"] > 80 else "healthy"
            )
        }
    except Exception as e:
        logger.error(f"Error getting pool stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get pool statistics")


@router.get("/pool-profiles")
async def get_pool_profiles(
    admin_payload: dict = Depends(get_current_admin)
):
    """
    Get available connection pool configuration profiles.
    
    Returns:
        Configuration recommendations for different load profiles
    """
    try:
        profiles = {
            name: {
                **config,
                "name": name
            }
            for name, config in OptimizedPoolConfig.PROFILES.items()
        }
        
        return {
            "status": "success",
            "profiles": profiles,
            "current": "high_load",  # Can detect from actual config
            "recommended": OptimizedPoolConfig.get_recommended_profile(200)  # 200 RPS target
        }
    except Exception as e:
        logger.error(f"Error getting pool profiles: {e}")
        raise HTTPException(status_code=500, detail="Failed to get pool profiles")


@router.post("/reset-metrics")
async def reset_metrics(
    admin_payload: dict = Depends(get_current_admin)
):
    """
    Reset performance metrics (admin only).
    
    Returns:
        Confirmation message
    """
    try:
        monitor = get_query_monitor()
        monitor.reset()
        
        pool_monitor = get_pool_monitor()
        pool_monitor.clear_alerts()
        
        return {
            "status": "success",
            "message": "Metrics reset successfully"
        }
    except Exception as e:
        logger.error(f"Error resetting metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset metrics")