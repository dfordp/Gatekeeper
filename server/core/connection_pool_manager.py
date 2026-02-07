# server/core/connection_pool_manager.py
"""Connection pool management and monitoring"""
import logging
import threading
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class PoolStats:
    """Connection pool statistics"""
    
    def __init__(self):
        self.total_connections = 0
        self.active_connections = 0
        self.idle_connections = 0
        self.overflow_connections = 0
        self.last_updated = datetime.now()
    
    def to_dict(self) -> Dict:
        return {
            "total": self.total_connections,
            "active": self.active_connections,
            "idle": self.idle_connections,
            "overflow": self.overflow_connections,
            "utilization_percent": round(
                (self.active_connections / max(self.total_connections, 1)) * 100, 2
            ),
            "last_updated": self.last_updated.isoformat()
        }


class PoolMonitor:
    """Monitor SQLAlchemy connection pool health"""
    
    def __init__(self):
        self.lock = threading.Lock()
        self.stats = PoolStats()
        self.alerts = []
        self.warning_threshold = 0.80  # Alert if > 80% utilization
        self.critical_threshold = 0.95  # Critical if > 95% utilization
    
    def update_stats(self, pool) -> None:
        """
        Update pool statistics from SQLAlchemy pool.
        
        Args:
            pool: SQLAlchemy connection pool object
        """
        with self.lock:
            try:
                self.stats.total_connections = pool.size()
                self.stats.active_connections = pool.checkedout()
                self.stats.idle_connections = pool.size() - pool.checkedout()
                self.stats.overflow_connections = max(0, pool.overflow() - pool.size())
                self.stats.last_updated = datetime.now()
                
                # Check for issues
                self._check_thresholds()
                
            except Exception as e:
                logger.error(f"Failed to update pool stats: {e}")
    
    def _check_thresholds(self) -> None:
        """Check pool utilization thresholds"""
        if self.stats.total_connections == 0:
            return
        
        utilization = self.stats.active_connections / self.stats.total_connections
        
        if utilization > self.critical_threshold:
            alert = f"CRITICAL: Connection pool at {utilization*100:.1f}% utilization"
            logger.critical(alert)
            self.alerts.append(alert)
        elif utilization > self.warning_threshold:
            alert = f"WARNING: Connection pool at {utilization*100:.1f}% utilization"
            logger.warning(alert)
            self.alerts.append(alert)
    
    def get_stats(self) -> Dict:
        """Get current pool statistics"""
        with self.lock:
            return self.stats.to_dict()
    
    def get_recent_alerts(self, limit: int = 10) -> list:
        """Get recent alerts"""
        with self.lock:
            return self.alerts[-limit:]
    
    def clear_alerts(self) -> None:
        """Clear alert history"""
        with self.lock:
            self.alerts.clear()


class OptimizedPoolConfig:
    """Recommended connection pool configuration based on load profile"""
    
    # Configuration for different load profiles
    PROFILES = {
        "low_load": {
            "pool_size": 5,
            "max_overflow": 5,
            "pool_recycle": 3600,
            "pool_pre_ping": True,
            "description": "5 core + 5 overflow (< 50 RPS)"
        },
        "medium_load": {
            "pool_size": 10,
            "max_overflow": 5,
            "pool_recycle": 3600,
            "pool_pre_ping": True,
            "description": "10 core + 5 overflow (50-100 RPS)"
        },
        "high_load": {
            "pool_size": 20,
            "max_overflow": 10,
            "pool_recycle": 3600,
            "pool_pre_ping": True,
            "description": "20 core + 10 overflow (100-200+ RPS)"
        },
        "very_high_load": {
            "pool_size": 30,
            "max_overflow": 20,
            "pool_recycle": 3600,
            "pool_pre_ping": True,
            "description": "30 core + 20 overflow (200+ RPS)"
        }
    }
    
    @staticmethod
    def get_profile(name: str) -> Dict:
        """
        Get connection pool configuration for a load profile.
        
        Args:
            name: Profile name (low_load, medium_load, high_load, very_high_load)
            
        Returns:
            Dictionary of pool configuration parameters
        """
        profile = OptimizedPoolConfig.PROFILES.get(name)
        if not profile:
            logger.warning(f"Unknown profile: {name}, using high_load")
            return OptimizedPoolConfig.PROFILES["high_load"]
        return profile
    
    @staticmethod
    def get_recommended_profile(estimated_rps: int) -> str:
        """
        Recommend a profile based on estimated requests per second.
        
        Args:
            estimated_rps: Estimated requests per second
            
        Returns:
            Profile name
        """
        if estimated_rps < 50:
            return "low_load"
        elif estimated_rps < 100:
            return "medium_load"
        elif estimated_rps < 200:
            return "high_load"
        else:
            return "very_high_load"


# Global pool monitor
pool_monitor = PoolMonitor()


def get_pool_monitor() -> PoolMonitor:
    """Get global pool monitor instance"""
    return pool_monitor