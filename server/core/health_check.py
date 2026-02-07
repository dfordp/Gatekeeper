# server/core/health_check.py
"""
Health Check System

Monitors the health of core system components:
- Database connection pool
- Embedding API (OpenAI)
- Qdrant vector database
- Redis cache

Provides detailed status for monitoring and alerting.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum
import asyncio

from core.logger import get_logger
from core.async_database import test_async_connection

logger = get_logger(__name__)


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth:
    """Health status for a single component"""
    
    def __init__(self, name: str):
        self.name = name
        self.status = HealthStatus.HEALTHY
        self.message = "No checks performed yet"
        self.last_check: Optional[datetime] = None
        self.response_time_ms: float = 0
        self.details: Dict[str, Any] = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "response_time_ms": round(self.response_time_ms, 2),
            "details": self.details
        }


class HealthCheckSystem:
    """System-wide health check manager"""
    
    def __init__(self):
        self.components: Dict[str, ComponentHealth] = {
            "database": ComponentHealth("database"),
            "embedding_api": ComponentHealth("embedding_api"),
            "qdrant": ComponentHealth("qdrant"),
            "redis": ComponentHealth("redis")
        }
    
    async def check_database(self) -> ComponentHealth:
        """Check database connection health"""
        component = self.components["database"]
        start_time = datetime.utcnow()
        
        try:
            result = await test_async_connection()
            component.response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if result:
                component.status = HealthStatus.HEALTHY
                component.message = "Database connection successful"
            else:
                component.status = HealthStatus.UNHEALTHY
                component.message = "Database connection test failed"
            
            component.last_check = datetime.utcnow()
            return component
            
        except Exception as e:
            component.response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            component.status = HealthStatus.UNHEALTHY
            component.message = f"Database connection error: {str(e)}"
            component.last_check = datetime.utcnow()
            logger.error(f"Database health check failed: {e}")
            return component
    
    async def check_embedding_api(self) -> ComponentHealth:
        """Check OpenAI embedding API health"""
        component = self.components["embedding_api"]
        start_time = datetime.utcnow()
        
        try:
            from services.async_embedding_api_client import AsyncEmbeddingAPIClient
            
            client = AsyncEmbeddingAPIClient()
            # Simple test: embed one word
            vector = await client.get_embedding_vector("test")
            component.response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if vector and len(vector) == 1536:  # text-embedding-3-small dimension
                component.status = HealthStatus.HEALTHY
                component.message = "Embedding API responsive"
            else:
                component.status = HealthStatus.DEGRADED
                component.message = "Embedding API returned invalid vector"
            
            component.last_check = datetime.utcnow()
            return component
            
        except Exception as e:
            component.response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            component.status = HealthStatus.UNHEALTHY
            component.message = f"Embedding API error: {str(e)}"
            component.last_check = datetime.utcnow()
            logger.error(f"Embedding API health check failed: {e}")
            return component
    
    async def check_qdrant(self) -> ComponentHealth:
        """Check Qdrant vector database health"""
        component = self.components["qdrant"]
        start_time = datetime.utcnow()
        
        try:
            from qdrant_client import AsyncQdrantClient
            from core.config import QDRANT_HOST, QDRANT_PORT, QDRANT_API_KEY
            
            # Build URL from host and port
            qdrant_url = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
            client = AsyncQdrantClient(url=qdrant_url, api_key=QDRANT_API_KEY)
            
            # Test: check if collection exists
            collections = await client.get_collections()
            component.response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if collections:
                component.status = HealthStatus.HEALTHY
                component.message = f"Qdrant responsive ({len(collections.collections)} collections)"
                component.details = {
                    "collections": len(collections.collections)
                }
            else:
                component.status = HealthStatus.DEGRADED
                component.message = "Qdrant active but no collections"
            
            component.last_check = datetime.utcnow()
            return component
            
        except Exception as e:
            component.response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            component.status = HealthStatus.UNHEALTHY
            component.message = f"Qdrant error: {str(e)}"
            component.last_check = datetime.utcnow()
            logger.error(f"Qdrant health check failed: {e}")
            return component
    
    async def check_redis(self) -> ComponentHealth:
        """Check Redis cache health"""
        component = self.components["redis"]
        start_time = datetime.utcnow()
        
        try:
            from services.redis_cache_service import RedisCacheService
            
            cache = RedisCacheService()
            await cache.initialize()
            # Test: set and get a key
            test_key = "health_check_test"
            await cache.set(test_key, "ok", ttl=10)
            result = await cache.get(test_key)
            component.response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if result == "ok":
                component.status = HealthStatus.HEALTHY
                component.message = "Redis responsive"
            else:
                component.status = HealthStatus.DEGRADED
                component.message = "Redis set/get test failed"
            
            component.last_check = datetime.utcnow()
            return component
            
        except Exception as e:
            component.response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            component.status = HealthStatus.UNHEALTHY
            component.message = f"Redis error: {str(e)}"
            component.last_check = datetime.utcnow()
            logger.error(f"Redis health check failed: {e}")
            return component
    
    async def check_all(self) -> Dict[str, ComponentHealth]:
        """Check all components health in parallel"""
        logger.info("Starting system health check...")
        
        # Run all checks in parallel
        results = await asyncio.gather(
            self.check_database(),
            self.check_embedding_api(),
            self.check_qdrant(),
            self.check_redis(),
            return_exceptions=True
        )
        
        # Update components from results
        for component in results:
            if isinstance(component, ComponentHealth):
                self.components[component.name] = component
        
        logger.info("System health check complete")
        return self.components
    
    def get_overall_status(self) -> str:
        """Get overall system status"""
        statuses = [c.status for c in self.components.values()]
        
        if all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY.value
        elif all(s != HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.DEGRADED.value
        else:
            return HealthStatus.UNHEALTHY.value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "overall_status": self.get_overall_status(),
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                name: component.to_dict()
                for name, component in self.components.items()
            }
        }


# Global instance
_health_check_system: Optional[HealthCheckSystem] = None


def get_health_check_system() -> HealthCheckSystem:
    """Get or create global health check system"""
    global _health_check_system
    if _health_check_system is None:
        _health_check_system = HealthCheckSystem()
    return _health_check_system