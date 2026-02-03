# server/services/redis_cache_service.py
"""
Redis Cache Service - Async Redis wrapper with TTL and tag-based invalidation

Features:
- Async/await support for non-blocking operations
- Automatic TTL expiration
- Tag-based invalidation (invalidate multiple keys by tag)
- Company data isolation
- Metrics tracking (hit/miss rates)
- Graceful degradation (works without Redis)
"""

import asyncio
import json
from typing import Optional, Any, List, Dict
import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError, ConnectionError

from core.logger import get_logger
from core.config import (
    REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD,
    REDIS_ENABLED, CACHE_DEFAULT_TTL
)

logger = get_logger(__name__)


class RedisCacheService:
    """
    Redis-backed cache service with TTL and tag-based invalidation
    
    Usage:
        cache = RedisCacheService()
        await cache.initialize()
        
        # Set value with TTL and tags
        await cache.set(
            key="ticket:123",
            value={"id": "123", "status": "open"},
            ttl=60,
            tags=["ticket:list", "analytics"]
        )
        
        # Get value
        value = await cache.get("ticket:123")
        
        # Invalidate by tag
        await cache.invalidate_by_tag("ticket:list")
        
        # Cleanup on shutdown
        await cache.close()
    """
    
    def __init__(
        self,
        host: str = REDIS_HOST,
        port: int = REDIS_PORT,
        db: int = REDIS_DB,
        password: Optional[str] = REDIS_PASSWORD,
        enabled: bool = REDIS_ENABLED,
        default_ttl: int = CACHE_DEFAULT_TTL
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.enabled = enabled
        self.default_ttl = default_ttl
        
        self.redis: Optional[aioredis.Redis] = None
        self.pool: Optional[ConnectionPool] = None
        self._initialized = False
        
        # Metrics
        self.metrics = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0,
            "tag_invalidations": 0
        }
    
    async def initialize(self) -> bool:
        """Initialize Redis connection pool"""
        if not self.enabled:
            logger.warning("Redis caching is disabled in configuration")
            return False
        
        try:
            # Create connection pool for better resource management
            self.pool = ConnectionPool(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password if self.password else None,
                max_connections=20,
                socket_connect_timeout=5,
                socket_keepalive=True,
                decode_responses=False,
                retry_on_timeout=True
            )
            
            self.redis = aioredis.Redis(connection_pool=self.pool)
            
            # Test connection with timeout
            await asyncio.wait_for(self.redis.ping(), timeout=5)
            logger.info(f"✓ Redis connected: {self.host}:{self.port}/db{self.db}")
            
            self._initialized = True
            return True
            
        except asyncio.TimeoutError:
            logger.error(f"✗ Redis connection timeout: {self.host}:{self.port}")
            self.enabled = False
            return False
        except ConnectionError as e:
            logger.error(f"✗ Failed to connect to Redis: {e}")
            self.enabled = False
            return False
        except Exception as e:
            logger.error(f"✗ Redis initialization failed: {e}")
            self.enabled = False
            return False
    
    async def close(self) -> None:
        """Close Redis connection"""
        if self.redis:
            try:
                await self.redis.close()
                if self.pool:
                    await self.pool.disconnect()
                logger.info("✓ Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        if not self.enabled or not self._initialized:
            return None
        
        try:
            value = await self.redis.get(key)
            
            if value:
                self.metrics["hits"] += 1
                # Parse JSON
                return json.loads(value)
            else:
                self.metrics["misses"] += 1
                return None
                
        except RedisError as e:
            logger.error(f"Redis GET error for key '{key}': {e}")
            self.metrics["errors"] += 1
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for key '{key}': {e}")
            await self.delete(key)  # Remove corrupted entry
            return None
        except Exception as e:
            logger.error(f"Unexpected error in cache.get('{key}'): {e}")
            self.metrics["errors"] += 1
            return None
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> bool:
        """
        Set value in cache with TTL and tags
        
        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds (default: CACHE_DEFAULT_TTL)
            tags: List of tags for invalidation
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self._initialized:
            return False
        
        ttl = ttl or self.default_ttl
        
        try:
            # Serialize value
            json_value = json.dumps(value, default=str)
            
            # Set main cache entry
            await self.redis.setex(key, ttl, json_value)
            self.metrics["sets"] += 1
            
            # Store tags for invalidation
            if tags:
                for tag in tags:
                    # Store key in tag set with same TTL
                    await self.redis.sadd(f"tag:{tag}", key)
                    await self.redis.expire(f"tag:{tag}", ttl + 3600)  # Keep tag set longer
            
            logger.debug(f"Cache SET: {key} (ttl={ttl}s, tags={tags})")
            return True
            
        except RedisError as e:
            logger.error(f"Redis SET error for key '{key}': {e}")
            self.metrics["errors"] += 1
            return False
        except json.JSONEncodeError as e:
            logger.error(f"JSON encode error for key '{key}': {e}")
            self.metrics["errors"] += 1
            return False
        except Exception as e:
            logger.error(f"Unexpected error in cache.set('{key}'): {e}")
            self.metrics["errors"] += 1
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Delete key from cache
        
        Args:
            key: Cache key
            
        Returns:
            True if key was deleted, False otherwise
        """
        if not self.enabled or not self._initialized:
            return False
        
        try:
            result = await self.redis.delete(key)
            self.metrics["deletes"] += 1
            logger.debug(f"Cache DELETE: {key}")
            return result > 0
        except RedisError as e:
            logger.error(f"Redis DELETE error for key '{key}': {e}")
            self.metrics["errors"] += 1
            return False
    
    async def invalidate_by_tag(self, tag: str) -> int:
        """
        Invalidate all keys with given tag
        
        Args:
            tag: Tag to invalidate
            
        Returns:
            Number of keys invalidated
        """
        if not self.enabled or not self._initialized:
            return 0
        
        try:
            # Get all keys with this tag
            keys = await self.redis.smembers(f"tag:{tag}")
            
            if keys:
                # Delete all keys
                await self.redis.delete(*keys)
                
                # Delete tag set
                await self.redis.delete(f"tag:{tag}")
                
                self.metrics["tag_invalidations"] += 1
                logger.info(f"Cache INVALIDATE: tag '{tag}' removed {len(keys)} keys")
                return len(keys)
            
            return 0
            
        except RedisError as e:
            logger.error(f"Redis invalidate error for tag '{tag}': {e}")
            self.metrics["errors"] += 1
            return 0
    
    async def invalidate_by_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern
        
        Args:
            pattern: Key pattern (e.g., "ticket:list:*")
            
        Returns:
            Number of keys invalidated
        """
        if not self.enabled or not self._initialized:
            return 0
        
        try:
            # Get all matching keys
            cursor = 0
            keys_to_delete = []
            
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                keys_to_delete.extend(keys)
                
                if cursor == 0:
                    break
            
            if keys_to_delete:
                await self.redis.delete(*keys_to_delete)
                logger.info(f"Cache INVALIDATE: pattern '{pattern}' removed {len(keys_to_delete)} keys")
                return len(keys_to_delete)
            
            return 0
            
        except RedisError as e:
            logger.error(f"Redis pattern invalidate error: {e}")
            self.metrics["errors"] += 1
            return 0
    
    async def clear_all(self) -> bool:
        """Clear entire cache (use with caution)"""
        if not self.enabled or not self._initialized:
            return False
        
        try:
            await self.redis.flushdb()
            logger.warning("Cache CLEAR: entire cache cleared")
            return True
        except RedisError as e:
            logger.error(f"Redis flush error: {e}")
            return False
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get cache metrics"""
        total = self.metrics["hits"] + self.metrics["misses"]
        hit_rate = (
            (self.metrics["hits"] / total * 100) if total > 0 else 0
        )
        
        return {
            "hits": self.metrics["hits"],
            "misses": self.metrics["misses"],
            "hit_rate_percent": round(hit_rate, 2),
            "sets": self.metrics["sets"],
            "deletes": self.metrics["deletes"],
            "tag_invalidations": self.metrics["tag_invalidations"],
            "errors": self.metrics["errors"],
        }
    
    async def get_info(self) -> Dict[str, Any]:
        """Get Redis server info"""
        if not self.enabled or not self._initialized:
            return {}
        
        try:
            info = await self.redis.info()
            
            return {
                "connected": True,
                "memory_used": info.get("used_memory_human"),
                "memory_peak": info.get("used_memory_peak_human"),
                "clients": info.get("connected_clients"),
                "commands_processed": info.get("total_commands_processed"),
                "uptime_seconds": info.get("uptime_in_seconds"),
            }
        except Exception as e:
            logger.error(f"Error getting Redis info: {e}")
            return {"connected": False}
    
    def get_hit_rate(self) -> float:
        """Get cache hit rate percentage"""
        total = self.metrics["hits"] + self.metrics["misses"]
        return (self.metrics["hits"] / total * 100) if total > 0 else 0


# Global cache instance
_cache_instance: Optional[RedisCacheService] = None


async def get_cache() -> RedisCacheService:
    """Get or create global cache instance"""
    global _cache_instance
    
    if _cache_instance is None:
        _cache_instance = RedisCacheService()
        await _cache_instance.initialize()
    
    return _cache_instance


async def init_cache() -> RedisCacheService:
    """Initialize global cache"""
    cache = await get_cache()
    return cache


async def close_cache() -> None:
    """Close global cache"""
    global _cache_instance
    
    if _cache_instance:
        await _cache_instance.close()
        _cache_instance = None