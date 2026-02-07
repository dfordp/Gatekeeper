# server/core/circuit_breaker.py
"""
Circuit Breaker Pattern Implementation

Monitors service health and prevents cascade failures by stopping requests
when a service is degraded or unavailable.

States:
- CLOSED: Normal operation, all requests pass through
- OPEN: Service failed, requests fail fast without attempting
- HALF_OPEN: Testing if service recovered, limited requests allowed

Usage:
    breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
    try:
        result = await breaker.call(async_function, *args, **kwargs)
    except CircuitBreakerOpen:
        # Handle gracefully - use fallback, cache, etc
        pass
"""

import asyncio
import time
from typing import Callable, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
from core.logger import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Service failed, fail fast
    HALF_OPEN = "half_open"    # Testing recovery


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is OPEN"""
    pass


class CircuitBreaker:
    """
    Circuit breaker implementation for async operations
    
    Monitors failures and prevents cascading failures by failing fast
    when a service becomes unavailable.
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        recovery_timeout: int = 60
    ):
        """
        Initialize circuit breaker
        
        Args:
            name: Name of the service being protected
            failure_threshold: Number of failures before opening circuit (default 5)
            success_threshold: Number of successes in HALF_OPEN before closing (default 2)
            recovery_timeout: Seconds to wait before attempting recovery (default 60)
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.recovery_timeout = recovery_timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.opened_at: Optional[datetime] = None
        
    async def call(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function through circuit breaker
        
        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result from function
            
        Raises:
            CircuitBreakerOpen: If circuit is open (fail fast)
        """
        # Check if we should attempt recovery
        if self.state == CircuitState.OPEN:
            if self._should_attempt_recovery():
                logger.info(f"🔵 Circuit breaker '{self.name}': transitioning to HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                logger.warning(f"🔴 Circuit breaker '{self.name}': OPEN (fail fast)")
                raise CircuitBreakerOpen(f"Circuit breaker '{self.name}' is OPEN")
        
        # Execute the function
        try:
            result = await func(*args, **kwargs)
            await self._record_success()
            return result
        except Exception as e:
            await self._record_failure()
            raise
    
    async def _record_success(self):
        """Record successful execution"""
        self.failure_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            logger.debug(f"Circuit breaker '{self.name}': HALF_OPEN success ({self.success_count}/{self.success_threshold})")
            
            if self.success_count >= self.success_threshold:
                logger.info(f"✅ Circuit breaker '{self.name}': CLOSED (recovered)")
                self.state = CircuitState.CLOSED
                self.success_count = 0
        
        elif self.state == CircuitState.CLOSED:
            logger.debug(f"Circuit breaker '{self.name}': CLOSED (healthy)")
    
    async def _record_failure(self):
        """Record failed execution"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        logger.warning(f"Circuit breaker '{self.name}': failure {self.failure_count}/{self.failure_threshold}")
        
        if self.state == CircuitState.HALF_OPEN:
            logger.error(f"🔴 Circuit breaker '{self.name}': OPEN (recovery failed)")
            self.state = CircuitState.OPEN
            self.opened_at = datetime.utcnow()
            self.success_count = 0
        
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                logger.error(f"🔴 Circuit breaker '{self.name}': OPEN (threshold exceeded)")
                self.state = CircuitState.OPEN
                self.opened_at = datetime.utcnow()
    
    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery"""
        if self.opened_at is None:
            return False
        
        time_since_open = datetime.utcnow() - self.opened_at
        return time_since_open.total_seconds() >= self.recovery_timeout
    
    def get_status(self) -> dict:
        """Get current circuit breaker status"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout
        }


class CircuitBreakerRegistry:
    """
    Registry to manage multiple circuit breakers
    
    Centralized management of all circuit breakers in the system.
    """
    
    _breakers: dict[str, CircuitBreaker] = {}
    _lock = asyncio.Lock()
    
    @classmethod
    async def get_breaker(
        cls,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        recovery_timeout: int = 60
    ) -> CircuitBreaker:
        """
        Get or create a circuit breaker by name
        
        Args:
            name: Unique name for the circuit breaker
            failure_threshold: Number of failures before opening
            success_threshold: Number of successes to close
            recovery_timeout: Timeout before recovery attempt
            
        Returns:
            CircuitBreaker instance
        """
        async with cls._lock:
            if name not in cls._breakers:
                cls._breakers[name] = CircuitBreaker(
                    name=name,
                    failure_threshold=failure_threshold,
                    success_threshold=success_threshold,
                    recovery_timeout=recovery_timeout
                )
                logger.info(f"Created circuit breaker: {name}")
            
            return cls._breakers[name]
    
    @classmethod
    async def get_all_breakers(cls) -> dict[str, CircuitBreaker]:
        """Get all registered circuit breakers"""
        return cls._breakers.copy()
    
    @classmethod
    async def get_all_status(cls) -> dict[str, dict]:
        """Get status of all circuit breakers"""
        return {
            name: breaker.get_status()
            for name, breaker in cls._breakers.items()
        }
    
    @classmethod
    async def reset_breaker(cls, name: str):
        """Reset a circuit breaker"""
        async with cls._lock:
            if name in cls._breakers:
                breaker = cls._breakers[name]
                breaker.state = CircuitState.CLOSED
                breaker.failure_count = 0
                breaker.success_count = 0
                breaker.last_failure_time = None
                breaker.opened_at = None
                logger.info(f"Reset circuit breaker: {name}")