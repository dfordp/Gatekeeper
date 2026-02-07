# server/core/read_replica_manager.py
"""
Read Replica Management & Load Balancing
Manages multiple read replicas with intelligent query routing

Features:
- Primary/replica database configuration
- Query routing (writes to primary, reads to replicas)
- Health checking for replicas
- Replica lag monitoring
- Failover handling
- Load balancing across healthy replicas
"""

import asyncio
from typing import Optional, List, Dict
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
import random

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from core.logger import get_logger
from core.config import DATABASE_URL

logger = get_logger(__name__)


class ReplicaStatus(str, Enum):
    """Replica health status"""
    HEALTHY = "healthy"
    LAGGING = "lagging"
    UNHEALTHY = "unhealthy"
    UNREACHABLE = "unreachable"


@dataclass
class ReplicaHealthStatus:
    """Health status of a replica"""
    host: str
    port: int
    status: ReplicaStatus
    lag_bytes: Optional[int] = None  # Write-Ahead Log bytes behind
    lag_seconds: Optional[float] = None
    response_time_ms: Optional[float] = None
    last_check: Optional[datetime] = None
    error_message: Optional[str] = None


class ReadReplicaManager:
    """
    Manages connections to primary and read replicas
    
    Configuration:
        PRIMARY_HOST: "localhost"           # Primary database
        REPLICA_HOSTS: ["replica1", "replica2", "replica3"]  # Read replicas
    """
    
    def __init__(
        self,
        primary_url: str,
        replica_urls: Optional[List[str]] = None,
        max_replica_lag_bytes: int = 1_000_000_000,  # 1GB
        health_check_interval: int = 30  # seconds
    ):
        """
        Initialize replica manager
        
        Args:
            primary_url: Primary database connection URL
            replica_urls: List of read replica connection URLs
            max_replica_lag_bytes: Maximum acceptable WAL lag (bytes)
            health_check_interval: Health check frequency (seconds)
        """
        self.primary_url = primary_url
        self.replica_urls = replica_urls or []
        self.max_replica_lag_bytes = max_replica_lag_bytes
        self.health_check_interval = health_check_interval
        
        self.primary_engine: Optional[AsyncEngine] = None
        self.primary_session_maker = None
        
        self.replica_engines: Dict[str, AsyncEngine] = {}
        self.replica_session_makers = {}
        self.replica_health: Dict[str, ReplicaHealthStatus] = {}
        
        self._health_check_task = None
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize primary and replica connections"""
        try:
            # Create primary engine
            self.primary_engine = create_async_engine(
                self.primary_url,
                echo=False,
                pool_pre_ping=True,
                pool_size=20,
                max_overflow=10,
            )
            self.primary_session_maker = sessionmaker(
                self.primary_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Test primary connection
            async with self.primary_session_maker() as session:
                await session.execute(text("SELECT 1"))
            
            logger.info("✓ Primary database connection established")
            
            # Create replica engines
            for i, replica_url in enumerate(self.replica_urls):
                try:
                    engine = create_async_engine(
                        replica_url,
                        echo=False,
                        pool_pre_ping=True,
                        pool_size=15,
                        max_overflow=5,
                    )
                    
                    session_maker = sessionmaker(
                        engine,
                        class_=AsyncSession,
                        expire_on_commit=False
                    )
                    
                    # Test connection
                    async with session_maker() as session:
                        await session.execute(text("SELECT 1"))
                    
                    self.replica_engines[replica_url] = engine
                    self.replica_session_makers[replica_url] = session_maker
                    
                    # Initialize health status
                    self.replica_health[replica_url] = ReplicaHealthStatus(
                        host=replica_url.split("@")[1].split(":")[0] if "@" in replica_url else "unknown",
                        port=5432,
                        status=ReplicaStatus.HEALTHY
                    )
                    
                    logger.info(f"✓ Replica {i+1}/{len(self.replica_urls)} connected: {replica_url}")
                    
                except Exception as e:
                    logger.error(f"✗ Failed to connect to replica {i+1}: {e}")
                    self.replica_health[replica_url] = ReplicaHealthStatus(
                        host=replica_url.split("@")[1].split(":")[0] if "@" in replica_url else "unknown",
                        port=5432,
                        status=ReplicaStatus.UNREACHABLE,
                        error_message=str(e)
                    )
            
            # Start health check background task
            self._health_check_task = asyncio.create_task(self._run_health_checks())
            
            self._initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize replica manager: {e}")
            return False
    
    async def close(self):
        """Close all connections"""
        if self._health_check_task:
            self._health_check_task.cancel()
        
        # Close replica engines
        for engine in self.replica_engines.values():
            await engine.dispose()
        
        # Close primary engine
        if self.primary_engine:
            await self.primary_engine.dispose()
        
        logger.info("✓ All database connections closed")
    
    async def get_primary_session(self) -> AsyncSession:
        """Get session to primary database"""
        if not self._initialized:
            raise RuntimeError("ReplicaManager not initialized")
        return self.primary_session_maker()
    
    async def get_read_session(self) -> AsyncSession:
        """
        Get session to a healthy read replica
        Falls back to primary if no healthy replicas
        """
        if not self._initialized:
            raise RuntimeError("ReplicaManager not initialized")
        
        # Find healthy replicas
        healthy = [
            url for url, status in self.replica_health.items()
            if status.status == ReplicaStatus.HEALTHY
        ]
        
        # Use replica if available, otherwise primary
        if healthy:
            selected_url = random.choice(healthy)
            logger.debug(f"Routing read to replica: {selected_url}")
            return self.replica_session_makers[selected_url]()
        else:
            logger.warning("No healthy replicas available, routing to primary")
            return self.get_primary_session()
    
    async def _run_health_checks(self):
        """Background task for continuous health checking"""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                
                # Check each replica
                for replica_url, session_maker in self.replica_session_makers.items():
                    await self._check_replica_health(replica_url, session_maker)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
    
    async def _check_replica_health(self, replica_url: str, session_maker):
        """Check individual replica health and lag"""
        try:
            start = asyncio.get_event_loop().time()
            
            async with session_maker() as session:
                # Test connection
                await session.execute(text("SELECT 1"))
                
                # Check replication lag
                lag_result = await session.execute(text(
                    "SELECT EXTRACT(EPOCH FROM (NOW() - pg_last_xact_replay_timestamp()))::int as lag_seconds"
                ))
                lag_seconds = lag_result.scalar()
                
            response_time = (asyncio.get_event_loop().time() - start) * 1000
            
            # Update health status
            if lag_seconds is not None and lag_seconds < 5:
                status = ReplicaStatus.HEALTHY
            elif lag_seconds is not None and lag_seconds < 30:
                status = ReplicaStatus.LAGGING
            else:
                status = ReplicaStatus.LAGGING
            
            self.replica_health[replica_url] = ReplicaHealthStatus(
                host=replica_url.split("@")[1].split(":")[0] if "@" in replica_url else "unknown",
                port=5432,
                status=status,
                lag_seconds=lag_seconds,
                response_time_ms=response_time,
                last_check=datetime.now()
            )
            
            logger.debug(f"Replica health: {replica_url} - {status.value} (lag: {lag_seconds}s)")
            
        except Exception as e:
            logger.error(f"Health check failed for {replica_url}: {e}")
            self.replica_health[replica_url] = ReplicaHealthStatus(
                host=replica_url.split("@")[1].split(":")[0] if "@" in replica_url else "unknown",
                port=5432,
                status=ReplicaStatus.UNREACHABLE,
                error_message=str(e),
                last_check=datetime.now()
            )
    
    def get_health_status(self) -> Dict[str, Dict]:
        """Get current health status of all replicas"""
        return {
            "initialized": self._initialized,
            "replicas": {
                url: {
                    "status": status.status.value,
                    "lag_seconds": status.lag_seconds,
                    "response_time_ms": status.response_time_ms,
                    "last_check": status.last_check.isoformat() if status.last_check else None
                }
                for url, status in self.replica_health.items()
            },
            "healthy_count": sum(
                1 for status in self.replica_health.values()
                if status.status == ReplicaStatus.HEALTHY
            ),
            "total_replicas": len(self.replica_urls)
        }


# Global instance
_replica_manager: Optional[ReadReplicaManager] = None


async def get_replica_manager() -> ReadReplicaManager:
    """Get or create global replica manager"""
    global _replica_manager
    
    if _replica_manager is None:
        # Read from environment or config
        primary_url = DATABASE_URL
        replica_urls = [
            # os.getenv("READ_REPLICA_1"),
            # os.getenv("READ_REPLICA_2"),
            # os.getenv("READ_REPLICA_3"),
        ]
        
        _replica_manager = ReadReplicaManager(
            primary_url=primary_url,
            replica_urls=[url for url in replica_urls if url]
        )
    
    return _replica_manager


async def get_primary_session() -> AsyncSession:
    """Get primary database session"""
    manager = await get_replica_manager()
    return await manager.get_primary_session()


async def get_read_session() -> AsyncSession:
    """Get read replica session (or primary if unavailable)"""
    manager = await get_replica_manager()
    return await manager.get_read_session()