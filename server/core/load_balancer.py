# server/core/load_balancer.py
"""
Intelligent Request Load Balancing
Routes requests to the most optimal backend based on multiple factors

Features:
- Multiple backend pool support
- Health-based routing
- Response time tracking
- Request queuing and distribution
- Circuit breaker integration
- Graceful degradation
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import asyncio
import time
from datetime import datetime, timedelta

from core.logger import get_logger

logger = get_logger(__name__)


class BackendStatus(str, Enum):
    """Backend health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class BackendMetrics:
    """Metrics for a backend server"""
    name: str
    status: BackendStatus
    response_time_ms: float
    error_rate: float
    request_count: int
    error_count: int
    last_check: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.request_count == 0:
            return 1.0
        return 1.0 - self.error_rate
    
    @property
    def load_score(self) -> float:
        """Calculate backend load score (lower is better)"""
        # Factor in: response time, error rate, request count
        base_score = self.response_time_ms
        error_penalty = self.error_rate * 100
        return base_score + error_penalty


class LoadBalancer:
    """
    Distributes requests across multiple backends
    
    Configuration:
        backends: Dict[str, str] = {
            "primary": "http://primary:8000",
            "replica1": "http://replica1:8000",
            "replica2": "http://replica2:8000"
        }
    """
    
    def __init__(
        self,
        name: str,
        backends: Dict[str, str],
        algo="least_response_time"
    ):
        """
        Initialize load balancer
        
        Args:
            name: Load balancer name
            backends: Dict of backend_name -> backend_url
            algo: Load balancing algorithm (round_robin, least_response_time, random)
        """
        self.name = name
        self.backends = backends
        self.algo = algo
        
        self.metrics: Dict[str, BackendMetrics] = {}
        self.request_queue = []
        self._current_index = 0
        
        # Initialize metrics
        for backend_name in backends.keys():
            self.metrics[backend_name] = BackendMetrics(
                name=backend_name,
                status=BackendStatus.HEALTHY,
                response_time_ms=0.0,
                error_rate=0.0,
                request_count=0,
                error_count=0
            )
    
    def select_backend(self) -> str:
        """
        Select optimal backend using configured algorithm
        
        Returns:
            Backend name
        """
        # Filter healthy backends
        healthy = [
            name for name, metrics in self.metrics.items()
            if metrics.status in [BackendStatus.HEALTHY, BackendStatus.DEGRADED]
        ]
        
        if not healthy:
            # Return primary even if unhealthy
            return list(self.backends.keys())[0]
        
        if self.algo == "round_robin":
            return self._select_round_robin(healthy)
        elif self.algo == "least_response_time":
            return self._select_least_response_time(healthy)
        elif self.algo == "random":
            return self._select_random(healthy)
        else:
            return self._select_least_response_time(healthy)
    
    def _select_round_robin(self, backends: List[str]) -> str:
        """Round robin selection"""
        selected = backends[self._current_index % len(backends)]
        self._current_index += 1
        return selected
    
    def _select_least_response_time(self, backends: List[str]) -> str:
        """Select backend with lowest response time"""
        return min(
            backends,
            key=lambda name: self.metrics[name].response_time_ms
        )
    
    def _select_random(self, backends: List[str]) -> str:
        """Random selection from healthy backends"""
        import random
        return random.choice(backends)
    
    def record_request(
        self,
        backend_name: str,
        response_time_ms: float,
        success: bool
    ):
        """Record request metrics for a backend"""
        metrics = self.metrics[backend_name]
        metrics.request_count += 1
        
        if not success:
            metrics.error_count += 1
        
        # Update response time (exponential moving average)
        alpha = 0.3  # Smoothing factor
        metrics.response_time_ms = (
            alpha * response_time_ms +
            (1 - alpha) * metrics.response_time_ms
        )
        
        # Update error rate
        metrics.error_rate = metrics.error_count / max(metrics.request_count, 1)
        
        # Update status based on metrics
        self._update_backend_status(backend_name)
        
        metrics.last_check = datetime.now()
    
    def _update_backend_status(self, backend_name: str):
        """Update backend status based on metrics"""
        metrics = self.metrics[backend_name]
        
        if metrics.error_rate > 0.5:
            metrics.status = BackendStatus.UNHEALTHY
        elif metrics.error_rate > 0.1 or metrics.response_time_ms > 1000:
            metrics.status = BackendStatus.DEGRADED
        else:
            metrics.status = BackendStatus.HEALTHY
    
    def get_stats(self) -> Dict[str, Any]:
        """Get load balancer statistics"""
        return {
            "name": self.name,
            "algorithm": self.algo,
            "backends": {
                name: {
                    "status": metrics.status.value,
                    "response_time_ms": round(metrics.response_time_ms, 2),
                    "error_rate": round(metrics.error_rate * 100, 2),
                    "request_count": metrics.request_count,
                    "error_count": metrics.error_count,
                    "success_rate": round(metrics.success_rate * 100, 2),
                    "load_score": round(metrics.load_score, 2)
                }
                for name, metrics in self.metrics.items()
            },
            "healthy_backends": sum(
                1 for m in self.metrics.values()
                if m.status in [BackendStatus.HEALTHY, BackendStatus.DEGRADED]
            )
        }