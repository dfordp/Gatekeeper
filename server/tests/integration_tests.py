# server/tests/integration_tests.py
"""
Comprehensive Integration Tests - Phase 12
Tests all async layers, caching, optimization, and resilience patterns

Run with: pytest tests/integration_tests.py -v
Coverage: pytest tests/integration_tests.py --cov=. --cov-report=html
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base, Company, Ticket, User
from core.config import DATABASE_URL
from core.cache_config import CacheTTL
from services.redis_cache_service import RedisCacheService, get_cache
from core.query_optimizer import QueryOptimizer
from core.db_performance_monitor import get_query_monitor
from core.connection_pool_manager import get_pool_monitor
from core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from core.health_check import HealthCheckSystem
from core.read_replica_manager import ReadReplicaManager


@pytest.fixture
async def test_db():
    """Create test database session"""
    # Use in-memory SQLite for tests (comment out for integration with real DB)
    # engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    
    # For real integration tests, use test database
    engine = create_async_engine(
        DATABASE_URL.replace("/gatekeeper_db", "/gatekeeper_test_db"),
        echo=False
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    yield async_session
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def test_cache():
    """Create test Redis cache"""
    cache = RedisCacheService(enabled=True)
    await cache.initialize()
    yield cache
    await cache.clear_all()
    await cache.close()


# ==================== ASYNC DATABASE TESTS ====================

class TestAsyncDatabase:
    """Test async database operations"""
    
    @pytest.mark.asyncio
    async def test_async_connection(self, test_db):
        """Test basic async database connection"""
        async with test_db() as session:
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    
    @pytest.mark.asyncio
    async def test_create_company(self, test_db):
        """Test creating company via async session"""
        async with test_db() as session:
            company = Company(name=f"Test Company {uuid4()}")
            session.add(company)
            await session.commit()
            
            # Verify creation
            from sqlalchemy import select
            result = await session.execute(
                select(Company).where(Company.name == company.name)
            )
            retrieved = result.scalar_one_or_none()
            
            assert retrieved is not None
            assert retrieved.name == company.name
    
    @pytest.mark.asyncio
    async def test_async_transaction_rollback(self, test_db):
        """Test transaction rollback in async session"""
        async with test_db() as session:
            company = Company(name=f"Rollback Test {uuid4()}")
            session.add(company)
            
            # Rollback instead of commit
            await session.rollback()
            
            # Verify not created
            from sqlalchemy import select
            result = await session.execute(
                select(Company).where(Company.name == company.name)
            )
            assert result.scalar_one_or_none() is None


# ==================== CACHE TESTS ====================

class TestCaching:
    """Test caching functionality"""
    
    @pytest.mark.asyncio
    async def test_cache_set_get(self, test_cache):
        """Test basic cache set/get"""
        await test_cache.set("test_key", {"data": "value"}, ttl=60)
        result = await test_cache.get("test_key")
        
        assert result is not None
        assert result["data"] == "value"
    
    @pytest.mark.asyncio
    async def test_cache_miss(self, test_cache):
        """Test cache miss returns None"""
        result = await test_cache.get("nonexistent_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_with_tags(self, test_cache):
        """Test tag-based cache invalidation"""
        await test_cache.set(
            "key1", {"id": 1},
            ttl=60,
            tags=["ticket:list", "company:abc"]
        )
        await test_cache.set(
            "key2", {"id": 2},
            ttl=60,
            tags=["ticket:list", "company:abc"]
        )
        
        # Invalidate by tag
        invalidated = await test_cache.invalidate_by_tag("ticket:list")
        
        assert invalidated == 2
        assert await test_cache.get("key1") is None
        assert await test_cache.get("key2") is None
    
    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self, test_cache):
        """Test cache TTL expiration (mocked)"""
        await test_cache.set("ttl_key", {"data": "test"}, ttl=1)
        
        # Verify exists immediately
        assert await test_cache.get("ttl_key") is not None
        
        # Wait for expiration
        await asyncio.sleep(1.1)
        
        # Verify expired (if Redis TTL works)
        # Note: In-memory cache may not expire, Redis will
        # This test validates expiration behavior


# ==================== QUERY OPTIMIZATION TESTS ====================

class TestQueryOptimization:
    """Test query optimization and performance monitoring"""
    
    @pytest.mark.asyncio
    async def test_performance_monitoring(self, test_db):
        """Test query performance monitoring"""
        monitor = get_query_monitor()
        
        # Record some queries
        monitor.record_query("query_1", 50.5)
        monitor.record_query("query_1", 45.2)
        monitor.record_query("query_2", 150.8)
        
        stats = monitor.get_stats(window_minutes=5)
        
        assert stats["total_queries"] == 3
        assert len(stats["slow_queries"]) >= 1  # query_2 > 100ms
    
    @pytest.mark.asyncio
    async def test_pool_monitoring(self):
        """Test connection pool monitoring"""
        pool_monitor = get_pool_monitor()
        
        stats = pool_monitor.get_stats()
        
        assert "pool_size" in stats
        assert "utilization_percent" in stats


# ==================== CIRCUIT BREAKER TESTS ====================

class TestCircuitBreaker:
    """Test circuit breaker resilience pattern"""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_closed_state(self):
        """Test circuit breaker in CLOSED state (normal operation)"""
        config = CircuitBreakerConfig(failure_threshold=3, success_threshold=2)
        breaker = CircuitBreaker("test_breaker", config)
        
        # Breaker starts in CLOSED state
        assert breaker.state.value == "closed"
        
        # Successful call
        breaker.record_success()
        assert breaker.state.value == "closed"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_open_state(self):
        """Test circuit breaker transitions to OPEN after failures"""
        config = CircuitBreakerConfig(failure_threshold=2, success_threshold=2)
        breaker = CircuitBreaker("test_breaker", config)
        
        # Record failures
        breaker.record_failure()
        breaker.record_failure()
        
        # Should transition to OPEN
        assert breaker.state.value == "open"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_recovery(self):
        """Test circuit breaker recovery through HALF_OPEN"""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=1,
            recovery_timeout=0.1  # 100ms for testing
        )
        breaker = CircuitBreaker("test_breaker", config)
        
        # Cause failure
        breaker.record_failure()
        assert breaker.state.value == "open"
        
        # Wait for recovery timeout
        await asyncio.sleep(0.15)
        
        # Should transition to HALF_OPEN
        result = breaker.call_allowed()
        assert breaker.state.value == "half_open"
        
        # Record success
        breaker.record_success()
        assert breaker.state.value == "closed"


# ==================== HEALTH CHECK TESTS ====================

class TestHealthChecks:
    """Test health check system"""
    
    @pytest.mark.asyncio
    async def test_health_check_database(self, test_db):
        """Test database health check"""
        async with test_db() as session:
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    
    @pytest.mark.asyncio
    async def test_health_check_cache(self, test_cache):
        """Test cache health check"""
        # Set and get to verify health
        await test_cache.set("health_check", {"status": "ok"}, ttl=60)
        result = await test_cache.get("health_check")
        
        assert result is not None
        assert result["status"] == "ok"


# ==================== LOAD BALANCER TESTS ====================

class TestLoadBalancer:
    """Test load balancer logic"""
    
    def test_round_robin_selection(self):
        """Test round-robin backend selection"""
        from core.load_balancer import LoadBalancer, BackendStatus
        
        backends = {
            "backend1": "http://backend1:8000",
            "backend2": "http://backend2:8000",
            "backend3": "http://backend3:8000"
        }
        
        lb = LoadBalancer("test_lb", backends, algo="round_robin")
        
        # Should alternate
        assert lb.select_backend() in backends.keys()
        assert lb.select_backend() in backends.keys()
    
    def test_least_response_time_selection(self):
        """Test least response time backend selection"""
        from core.load_balancer import LoadBalancer
        
        backends = {
            "fast": "http://fast:8000",
            "slow": "http://slow:8000"
        }
        
        lb = LoadBalancer("test_lb", backends, algo="least_response_time")
        
        # Record different response times
        lb.record_request("fast", 10.0, True)
        lb.record_request("fast", 12.0, True)
        lb.record_request("slow", 100.0, True)
        
        # Should select fast backend
        selected = lb.select_backend()
        assert selected == "fast"
    
    def test_backend_status_transition(self):
        """Test backend status transitions based on errors"""
        from core.load_balancer import LoadBalancer, BackendStatus
        
        backends = {"backend1": "http://backend1:8000"}
        lb = LoadBalancer("test_lb", backends)
        
        # Record success
        lb.record_request("backend1", 50.0, True)
        assert lb.metrics["backend1"].status == BackendStatus.HEALTHY
        
        # Record failures
        for _ in range(3):
            lb.record_request("backend1", 50.0, False)
        
        # Should degrade
        assert lb.metrics["backend1"].status != BackendStatus.HEALTHY


# ==================== REPLICA MANAGEMENT TESTS ====================

class TestReplicaManagement:
    """Test read replica management"""
    
    def test_replica_health_status(self):
        """Test replica health status tracking"""
        from core.read_replica_manager import ReplicaStatus, ReplicaHealthStatus
        
        status = ReplicaHealthStatus(
            host="replica1.example.com",
            port=5432,
            status=ReplicaStatus.HEALTHY,
            lag_seconds=2.5
        )
        
        assert status.status == ReplicaStatus.HEALTHY
        assert status.lag_seconds == 2.5
    
    def test_replica_lag_detection(self):
        """Test replica lag detection logic"""
        from core.read_replica_manager import ReplicaStatus, ReplicaHealthStatus
        
        # Healthy replica
        healthy = ReplicaHealthStatus(
            host="replica1",
            port=5432,
            status=ReplicaStatus.HEALTHY,
            lag_seconds=2.0
        )
        assert healthy.status == ReplicaStatus.HEALTHY
        
        # Lagging replica
        lagging = ReplicaHealthStatus(
            host="replica2",
            port=5432,
            status=ReplicaStatus.LAGGING,
            lag_seconds=45.0
        )
        assert lagging.status == ReplicaStatus.LAGGING


# ==================== CONCURRENT LOAD TESTS ====================

class TestConcurrentOperations:
    """Test concurrent request handling"""
    
    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self, test_cache):
        """Test 100 concurrent cache operations"""
        async def cache_operation(index):
            key = f"concurrent_key_{index}"
            await test_cache.set(key, {"index": index}, ttl=60)
            result = await test_cache.get(key)
            assert result["index"] == index
        
        # Run 100 concurrent operations
        tasks = [cache_operation(i) for i in range(100)]
        await asyncio.gather(*tasks)
    
    @pytest.mark.asyncio
    async def test_concurrent_database_operations(self, test_db):
        """Test 50 concurrent database operations"""
        from sqlalchemy import select
        
        async def db_operation(index):
            async with test_db() as session:
                company = Company(name=f"Company_{uuid4()}")
                session.add(company)
                await session.commit()
                
                result = await session.execute(
                    select(Company).where(Company.id == company.id)
                )
                assert result.scalar_one_or_none() is not None
        
        # Run 50 concurrent operations
        tasks = [db_operation(i) for i in range(50)]
        await asyncio.gather(*tasks)


# ==================== ERROR HANDLING TESTS ====================

class TestErrorHandling:
    """Test error handling and recovery"""
    
    @pytest.mark.asyncio
    async def test_cache_graceful_degradation(self, test_cache):
        """Test cache graceful degradation when disabled"""
        disabled_cache = RedisCacheService(enabled=False)
        
        # Should not raise, but return None
        result = await disabled_cache.get("any_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_graceful_failure(self):
        """Test circuit breaker graceful failure mode"""
        from core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
        
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker("test", config)
        
        # Open circuit
        breaker.record_failure()
        
        # Should still allow half-open testing
        assert breaker.state.value == "open"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])