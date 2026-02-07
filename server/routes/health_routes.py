# server/routes/health_routes.py
"""
Health Check Endpoints

Provides detailed health status of all system components for monitoring,
alerting, and orchestration (Kubernetes liveness/readiness probes).

Endpoints:
- GET /health - Overall system health
- GET /health/db - Database status
- GET /health/embedding-api - OpenAI API status  
- GET /health/qdrant - Qdrant vector DB status
- GET /health/redis - Redis cache status
- GET /health/circuit-breakers - Circuit breaker status
"""

from fastapi import APIRouter, HTTPException
from core.health_check import get_health_check_system
from core.circuit_breaker import CircuitBreakerRegistry
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def get_overall_health():
    """
    Get overall system health status
    
    Returns:
    {
        "overall_status": "healthy|degraded|unhealthy",
        "timestamp": "2026-02-06T...",
        "components": {
            "database": {...},
            "embedding_api": {...},
            "qdrant": {...},
            "redis": {...}
        }
    }
    """
    try:
        health_system = get_health_check_system()
        await health_system.check_all()
        
        status = health_system.to_dict()
        overall = status["overall_status"]
        
        # Return 200 for healthy/degraded, 503 for unhealthy
        if overall == "unhealthy":
            raise HTTPException(
                status_code=503,
                detail="System unhealthy",
                headers={"X-Health-Status": overall}
            )
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Health check error"
        )


@router.get("/db")
async def check_database_health():
    """Check database connection health"""
    try:
        health_system = get_health_check_system()
        component = await health_system.check_database()
        
        if component.status.value == "unhealthy":
            raise HTTPException(status_code=503, detail=component.message)
        
        return component.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(status_code=500, detail="Database check error")


@router.get("/embedding-api")
async def check_embedding_api_health():
    """Check OpenAI embedding API health"""
    try:
        health_system = get_health_check_system()
        component = await health_system.check_embedding_api()
        
        if component.status.value == "unhealthy":
            raise HTTPException(status_code=503, detail=component.message)
        
        return component.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Embedding API health check failed: {e}")
        raise HTTPException(status_code=500, detail="Embedding API check error")


@router.get("/qdrant")
async def check_qdrant_health():
    """Check Qdrant vector database health"""
    try:
        health_system = get_health_check_system()
        component = await health_system.check_qdrant()
        
        if component.status.value == "unhealthy":
            raise HTTPException(status_code=503, detail=component.message)
        
        return component.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        raise HTTPException(status_code=500, detail="Qdrant check error")


@router.get("/redis")
async def check_redis_health():
    """Check Redis cache health"""
    try:
        health_system = get_health_check_system()
        component = await health_system.check_redis()
        
        if component.status.value == "unhealthy":
            raise HTTPException(status_code=503, detail=component.message)
        
        return component.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        raise HTTPException(status_code=500, detail="Redis check error")


@router.get("/circuit-breakers")
async def get_circuit_breakers_status():
    """Get status of all circuit breakers"""
    try:
        status = await CircuitBreakerRegistry.get_all_status()
        
        if not status:
            return {
                "circuit_breakers": [],
                "count": 0,
                "message": "No circuit breakers registered"
            }
        
        # Count open circuit breakers
        open_breakers = sum(
            1 for breaker in status.values()
            if breaker["state"] == "open"
        )
        
        return {
            "circuit_breakers": status,
            "count": len(status),
            "open_count": open_breakers,
            "status": "warning" if open_breakers > 0 else "ok"
        }
        
    except Exception as e:
        logger.error(f"Circuit breaker status check failed: {e}")
        raise HTTPException(status_code=500, detail="Circuit breaker check error")