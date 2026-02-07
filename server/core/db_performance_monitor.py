# server/core/db_performance_monitor.py
"""Database performance monitoring and metrics"""
import logging
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)


class QueryMetrics:
    """Single query execution metrics"""
    
    def __init__(self, query_name: str, duration_ms: float):
        self.query_name = query_name
        self.duration_ms = duration_ms
        self.timestamp = datetime.now()
    
    def __repr__(self):
        return f"QueryMetrics({self.query_name}, {self.duration_ms:.2f}ms)"


class PerformanceMonitor:
    """Monitor database query performance"""
    
    def __init__(self, history_size: int = 1000):
        self.history_size = history_size
        self.metrics: List[QueryMetrics] = []
        self.lock = threading.Lock()
        self.slow_queries_threshold = 100  # milliseconds
    
    def record_query(self, query_name: str, duration_ms: float) -> None:
        """
        Record a query execution.
        
        Args:
            query_name: Name/description of the query
            duration_ms: Execution time in milliseconds
        """
        metric = QueryMetrics(query_name, duration_ms)
        
        with self.lock:
            self.metrics.append(metric)
            
            # Keep only recent history
            if len(self.metrics) > self.history_size:
                self.metrics = self.metrics[-self.history_size:]
            
            # Log if slow
            if duration_ms > self.slow_queries_threshold:
                logger.warning(f"Slow query: {query_name} ({duration_ms:.2f}ms)")
    
    def get_stats(self, window_minutes: int = 5) -> Dict:
        """
        Get performance statistics for recent queries.
        
        Args:
            window_minutes: Time window to analyze (last N minutes)
            
        Returns:
            Dictionary with statistics
        """
        cutoff = datetime.now() - timedelta(minutes=window_minutes)
        
        with self.lock:
            recent = [m for m in self.metrics if m.timestamp > cutoff]
        
        if not recent:
            return {
                "total_queries": 0,
                "avg_duration_ms": 0,
                "slow_queries": [],
                "window_minutes": window_minutes
            }
        
        # Calculate statistics by query name
        stats_by_query = defaultdict(list)
        for metric in recent:
            stats_by_query[metric.query_name].append(metric.duration_ms)
        
        # Find slow queries
        slow = [m for m in recent if m.duration_ms > self.slow_queries_threshold]
        
        avg_all = sum(m.duration_ms for m in recent) / len(recent)
        
        return {
            "total_queries": len(recent),
            "avg_duration_ms": round(avg_all, 2),
            "slow_queries": [
                {
                    "query": m.query_name,
                    "duration_ms": round(m.duration_ms, 2),
                    "timestamp": m.timestamp.isoformat()
                }
                for m in sorted(slow, key=lambda x: x.duration_ms, reverse=True)[:10]
            ],
            "queries_by_type": {
                query_name: {
                    "count": len(durations),
                    "avg_ms": round(sum(durations) / len(durations), 2),
                    "max_ms": round(max(durations), 2),
                    "min_ms": round(min(durations), 2)
                }
                for query_name, durations in stats_by_query.items()
            },
            "window_minutes": window_minutes
        }
    
    def get_slow_queries(self, limit: int = 20) -> List[Dict]:
        """Get slowest queries from history"""
        with self.lock:
            sorted_metrics = sorted(
                self.metrics,
                key=lambda x: x.duration_ms,
                reverse=True
            )[:limit]
        
        return [
            {
                "query": m.query_name,
                "duration_ms": round(m.duration_ms, 2),
                "timestamp": m.timestamp.isoformat()
            }
            for m in sorted_metrics
        ]
    
    def reset(self) -> None:
        """Clear all metrics"""
        with self.lock:
            self.metrics.clear()


# Global monitor instance
query_monitor = PerformanceMonitor()


def get_query_monitor() -> PerformanceMonitor:
    """Get global query monitor instance"""
    return query_monitor