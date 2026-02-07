# server/services/multi_level_cache.py
"""
Multi-Level Cache Service - Phase 14

Implements a three-level caching hierarchy for optimal performance:
- L1: In-process LRU cache (fast, bounded memory)
- L2: Redis distributed cache (shared across processes, larger capacity)
- L3: Database lazy loading (fallback, source of truth)

Features:
- Automatic promotion up cache levels
- Bloom filters for negative caching
- Cache warming on startup
- Hit rate tracking per level
- Configurable TTLs per level
- Graceful degradation when levels unavailable
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Any, Dict, List, Set, Tuple
from enum import Enum
from dataclasses import dataclass, field
from collections import OrderedDict
import json
import hashlib

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


class CacheLevel(str, Enum):
    """Cache level identifiers"""
    L1 = "l1"  # In-process
    L2 = "l2"  # Redis
    L3 = "l3"  # Database


@dataclass
class CacheMetrics:
    """Cache hit/miss metrics"""
    level: CacheLevel
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size_bytes: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate hit rate percentage"""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0
    
    @property
    def efficiency_score(self) -> float:
        """Score cache efficiency (0-100)"""
        hit_rate_score = self.hit_rate
        return hit_rate_score


@dataclass
class CacheEntry:
    """Single cache entry with metadata"""
    key: str
    value: Any
    ttl: int
    created_at: datetime
    accessed_at: datetime
    level: CacheLevel
    size_bytes: int
    tags: Set[str] = field(default_factory=set)
    
    @property
    def age_seconds(self) -> int:
        """Age of entry in seconds"""
        return int((datetime.now() - self.created_at).total_seconds())
    
    @property
    def is_expired(self) -> bool:
        """Check if entry has expired"""
        return self.age_seconds > self.ttl
    
    @property
    def is_stale(self) -> bool:
        """Check if entry is stale (accessed > 80% of TTL ago)"""
        time_since_access = (datetime.now() - self.accessed_at).total_seconds()
        return time_since_access > (self.ttl * 0.8)


class BloomFilter:
    """
    Bloom filter for negative caching
    
    Prevents cache lookups for definitely non-existent keys
    Trades small false positives for reduced database pressure
    """
    
    def __init__(self, size: int = 1000000, hash_count: int = 3):
        """Initialize Bloom filter"""
        self.size = size
        self.hash_count = hash_count
        self.bits = set()
        self.false_positives = 0
        self.true_positives = 0
    
    def _hash(self, item: str, seed: int) -> int:
        """Generate hash for item"""
        hash_obj = hashlib.md5(f"{item}:{seed}".encode())
        return int(hash_obj.hexdigest(), 16) % self.size
    
    def add(self, item: str) -> None:
        """Add item to filter"""
        for i in range(self.hash_count):
            bit = self._hash(item, i)
            self.bits.add(bit)
    
    def maybe_contains(self, item: str) -> bool:
        """Check if item might be in set (no false negatives)"""
        for i in range(self.hash_count):
            bit = self._hash(item, i)
            if bit not in self.bits:
                return False
        return True
    
    def record_lookup(self, item: str, found: bool) -> None:
        """Record lookup result for metrics"""
        if found:
            self.true_positives += 1
        else:
            if self.maybe_contains(item):
                self.false_positives += 1
    
    def false_positive_rate(self) -> float:
        """Calculate false positive rate"""
        total = self.false_positives + self.true_positives
        return (self.false_positives / total * 100) if total > 0 else 0.0


class L1Cache:
    """
    L1: In-Process LRU Cache
    
    - Fast (memory access)
    - Bounded size (100MB default)
    - Per-process (not shared)
    - Auto-eviction on size limit
    """
    
    # Configuration
    MAX_SIZE_MB = 100
    MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
    EVICTION_RATIO = 0.25  # Evict 25% when full
    
    def __init__(self):
        """Initialize L1 cache"""
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.metrics = CacheMetrics(level=CacheLevel.L1)
        self.bloom = BloomFilter()
    
    def set(self, entry: CacheEntry) -> bool:
        """Set cache entry, evicting if necessary"""
        # Check if we need to evict
        current_size = sum(e.size_bytes for e in self.cache.values())
        if current_size + entry.size_bytes > self.MAX_SIZE_BYTES:
            self._evict(entry.size_bytes)
        
        self.cache[entry.key] = entry
        entry.accessed_at = datetime.now()
        self.bloom.add(entry.key)
        
        # Update metrics
        self.metrics.size_bytes = sum(e.size_bytes for e in self.cache.values())
        return True
    
    def get(self, key: str) -> Optional[CacheEntry]:
        """Get cache entry, updating LRU order"""
        if key not in self.cache:
            self.metrics.misses += 1
            return None
        
        entry = self.cache[key]
        if entry.is_expired:
            del self.cache[key]
            self.metrics.misses += 1
            return None
        
        # Update LRU order (move to end)
        self.cache.move_to_end(key)
        entry.accessed_at = datetime.now()
        self.metrics.hits += 1
        
        return entry
    
    def delete(self, key: str) -> bool:
        """Delete cache entry"""
        if key in self.cache:
            del self.cache[key]
            self.metrics.size_bytes = sum(e.size_bytes for e in self.cache.values())
            return True
        return False
    
    def clear(self) -> None:
        """Clear all entries"""
        count = len(self.cache)
        self.cache.clear()
        self.bloom.bits.clear()
        self.metrics.size_bytes = 0
        logger.info(f"L1 cache cleared ({count} entries)")
    
    def _evict(self, required_bytes: int) -> None:
        """Evict oldest entries until enough space"""
        bytes_to_free = int(self.MAX_SIZE_BYTES * self.EVICTION_RATIO)
        freed = 0
        evicted = 0
        
        while freed < bytes_to_free and self.cache:
            key, entry = self.cache.popitem(last=False)  # Remove oldest
            freed += entry.size_bytes
            evicted += 1
        
        self.metrics.evictions += evicted
        self.metrics.size_bytes = sum(e.size_bytes for e in self.cache.values())
        logger.debug(f"L1 evicted {evicted} entries ({freed / 1024 / 1024:.2f} MB)")
    
    def get_stats(self) -> Dict[str, any]:
        """Get L1 cache statistics"""
        return {
            "level": CacheLevel.L1.value,
            "size_bytes": self.metrics.size_bytes,
            "total_entries": len(self.cache),
            "hits": self.metrics.hits,
            "misses": self.metrics.misses,
            "hit_rate": self.metrics.hit_rate,
            "evictions": self.metrics.evictions,
            "capacity_used_percent": (self.metrics.size_bytes / self.MAX_SIZE_BYTES * 100) if self.MAX_SIZE_BYTES > 0 else 0
        }


class MultiLevelCache:
    """
    Multi-Level Cache Orchestrator
    
    Manages caching across L1 (in-process), L2 (Redis), and L3 (database)
    with automatic promotion and demotion between levels.
    """
    
    # TTL configuration (seconds)
    L1_TTL = 60  # Short - hot data
    L2_TTL = 300  # Medium - distributed cache
    L3_TTL = 3600  # Long - database
    
    def __init__(self, db: AsyncSession = None, redis_client = None):
        """Initialize multi-level cache"""
        self.db = db
        self.redis_client = redis_client
        self.l1 = L1Cache()
        self.l2_enabled = redis_client is not None
        self.metrics: Dict[CacheLevel, CacheMetrics] = {
            CacheLevel.L1: self.l1.metrics,
            CacheLevel.L2: CacheMetrics(level=CacheLevel.L2),
            CacheLevel.L3: CacheMetrics(level=CacheLevel.L3)
        }
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache with multi-level fallback
        
        Tries L1 → L2 → L3, promoting on each miss
        """
        # Try L1 (in-process)
        entry = self.l1.get(key)
        if entry:
            return entry.value
        
        # Try L2 (Redis)
        if self.l2_enabled and self.redis_client:
            try:
                value = await self.redis_client.get(key)
                if value is not None:
                    # Promote to L1
                    entry = CacheEntry(
                        key=key,
                        value=value,
                        ttl=self.L1_TTL,
                        created_at=datetime.now(),
                        accessed_at=datetime.now(),
                        level=CacheLevel.L1,
                        size_bytes=len(str(value).encode())
                    )
                    self.l1.set(entry)
                    self.metrics[CacheLevel.L2].hits += 1
                    return value
                self.metrics[CacheLevel.L2].misses += 1
            except Exception as e:
                logger.warning(f"L2 cache error: {e}")
        
        # Try L3 (Database) - not implemented here, handled by caller
        self.metrics[CacheLevel.L3].misses += 1
        return None
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[Set[str]] = None,
        promote_to_l2: bool = True
    ) -> None:
        """
        Set value across cache levels
        
        Always set L1 (in-process)
        Optionally set L2 (Redis) if enabled
        """
        ttl = ttl or self.L1_TTL
        tags = tags or set()
        size_bytes = len(str(value).encode())
        
        # Set L1
        entry = CacheEntry(
            key=key,
            value=value,
            ttl=ttl,
            created_at=datetime.now(),
            accessed_at=datetime.now(),
            level=CacheLevel.L1,
            size_bytes=size_bytes,
            tags=tags
        )
        self.l1.set(entry)
        
        # Set L2 (Redis)
        if promote_to_l2 and self.l2_enabled and self.redis_client:
            try:
                await self.redis_client.set(
                    key,
                    value,
                    ex=ttl
                )
            except Exception as e:
                logger.warning(f"L2 set failed: {e}")
    
    async def delete(self, key: str) -> None:
        """Delete from all cache levels"""
        # Delete L1
        self.l1.delete(key)
        
        # Delete L2
        if self.l2_enabled and self.redis_client:
            try:
                await self.redis_client.delete(key)
            except Exception as e:
                logger.warning(f"L2 delete failed: {e}")
    
    async def invalidate_by_tag(self, tag: str) -> None:
        """Invalidate all entries with tag"""
        # L1: iterate and delete matching
        keys_to_delete = [
            key for key, entry in self.l1.cache.items()
            if tag in entry.tags
        ]
        for key in keys_to_delete:
            self.l1.delete(key)
        
        # L2: call Redis if available
        if self.l2_enabled and self.redis_client:
            try:
                await self.redis_client.delete_by_pattern(f"{tag}:*")
            except Exception as e:
                logger.warning(f"L2 tag invalidation failed: {e}")
    
    async def warm_cache(self, data: Dict[str, Tuple[Any, int, Set[str]]]) -> int:
        """
        Warm cache with initial data on startup
        
        Args:
            data: Dict[key] = (value, ttl, tags)
        
        Returns:
            Number of entries loaded
        """
        count = 0
        for key, (value, ttl, tags) in data.items():
            try:
                await self.set(key, value, ttl=ttl, tags=tags, promote_to_l2=True)
                count += 1
            except Exception as e:
                logger.warning(f"Cache warming failed for {key}: {e}")
        
        logger.info(f"Cache warmed with {count} entries")
        return count
    
    def get_l1_stats(self) -> Dict[str, any]:
        """Get L1 cache statistics"""
        return self.l1.get_stats()
    
    def get_all_metrics(self) -> Dict[str, Dict[str, any]]:
        """Get metrics for all cache levels"""
        return {
            "l1": self.get_l1_stats(),
            "l2": {
                "level": "l2",
                "hits": self.metrics[CacheLevel.L2].hits,
                "misses": self.metrics[CacheLevel.L2].misses,
                "hit_rate": self.metrics[CacheLevel.L2].hit_rate
            },
            "l3": {
                "level": "l3",
                "hits": self.metrics[CacheLevel.L3].hits,
                "misses": self.metrics[CacheLevel.L3].misses,
                "hit_rate": self.metrics[CacheLevel.L3].hit_rate
            }
        }


class CacheWarmingService:
    """
    Service for warming caches on startup
    
    Loads frequently accessed data into L1/L2 caches
    """
    
    def __init__(self, cache: MultiLevelCache, db: AsyncSession):
        """Initialize cache warming service"""
        self.cache = cache
        self.db = db
    
    async def warm_all(self) -> Dict[str, int]:
        """Warm all caches with startup data"""
        results = {
            "companies": await self._warm_companies(),
            "tickets": await self._warm_recent_tickets(),
            "users": await self._warm_users(),
            "metadata": await self._warm_metadata()
        }
        logger.info(f"Cache warming complete: {results}")
        return results
    
    async def _warm_companies(self) -> int:
        """Warm company data (~10 entries)"""
        result = await self.db.execute(text("""
            SELECT id, name FROM company 
            LIMIT 10
        """))
        rows = result.fetchall()
        count = 0
        
        for company_id, name in rows:
            key = f"company:{company_id}"
            value = {"id": str(company_id), "name": name}
            await self.cache.set(
                key,
                json.dumps(value),
                ttl=3600,
                tags={"company", "metadata"}
            )
            count += 1
        
        return count
    
    async def _warm_recent_tickets(self) -> int:
        """Warm recent tickets (~100 entries)"""
        result = await self.db.execute(text("""
            SELECT id, ticket_no, status 
            FROM ticket 
            ORDER BY created_at DESC 
            LIMIT 100
        """))
        rows = result.fetchall()
        count = 0
        
        for ticket_id, ticket_no, status in rows:
            key = f"ticket:{ticket_id}"
            value = {
                "id": str(ticket_id),
                "ticket_no": ticket_no,
                "status": status
            }
            await self.cache.set(
                key,
                json.dumps(value),
                ttl=300,
                tags={"ticket", "active"}
            )
            count += 1
        
        return count
    
    async def _warm_users(self) -> int:
        """Warm user data (~20 entries)"""
        result = await self.db.execute(text("""
            SELECT id, name, email 
            FROM "user" 
            LIMIT 20
        """))
        rows = result.fetchall()
        count = 0
        
        for user_id, name, email in rows:
            key = f"user:{user_id}"
            value = {
                "id": str(user_id),
                "name": name,
                "email": email
            }
            await self.cache.set(
                key,
                json.dumps(value),
                ttl=600,
                tags={"user", "metadata"}
            )
            count += 1
        
        return count
    
    async def _warm_metadata(self) -> int:
        """Warm metadata (~5 entries)"""
        metadata = {
            "cache:config": {"version": "1.0", "levels": 3},
            "cache:initialized": {"timestamp": datetime.now().isoformat()},
            "cache:stats": {"warm": True}
        }
        
        for key, value in metadata.items():
            await self.cache.set(
                key,
                json.dumps(value),
                ttl=86400,  # 24 hours
                tags={"metadata"}
            )
        
        return len(metadata)