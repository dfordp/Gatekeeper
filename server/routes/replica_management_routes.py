# server/routes/replica_management_routes.py
"""
Read Replica Management Routes
APIs for managing and monitoring read replicas
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from core.logger import get_logger
from core.read_replica_manager import get_replica_manager
from middleware.auth_middleware import get_current_admin

logger = get_logger(__name__)
router = APIRouter(prefix="/api/replicas", tags=["replica-management"])


@router.get("/health", summary="Get replica health status")
async def get_replica_health(
    admin_payload: dict = Depends(get_current_admin)
) -> dict:
    """
    Get health status of all read replicas
    
    Returns:
    - Replica connectivity status
    - Replication lag in seconds
    - Response time for each replica
    - Overall healthy replica count
    """
    manager = await get_replica_manager()
    return manager.get_health_status()


@router.get("/status", summary="Get detailed replica status")
async def get_replica_status(
    admin_payload: dict = Depends(get_current_admin)
) -> dict:
    """
    Get detailed status of each replica including:
    - Lag from primary (bytes and time)
    - Last successful health check
    - Error messages if unhealthy
    - Recommendation for action
    """
    manager = await get_replica_manager()
    health = manager.get_health_status()
    
    return {
        "status": "success",
        "summary": {
            "total_replicas": health["total_replicas"],
            "healthy_replicas": health["healthy_count"],
            "failure_rate": round(
                (1 - health["healthy_count"] / max(health["total_replicas"], 1)) * 100, 2
            )
        },
        "replicas": health["replicas"],
        "recommendations": _generate_recommendations(health)
    }


@router.post("/promote", summary="Promote replica to primary")
async def promote_replica(
    replica_url: str,
    admin_payload: dict = Depends(get_current_admin)
) -> dict:
    """
    Promote a read replica to primary (failover)
    
    Note: This is a destructive operation. Ensure proper backup exists.
    """
    # This would require external orchestration (e.g., Patroni, pg_failover)
    # For now, return a message with instructions
    
    return {
        "status": "info",
        "message": "Replica promotion requires external orchestration",
        "steps": [
            "1. Verify replica lag is near zero",
            "2. Stop writes to current primary",
            "3. Promote replica using: SELECT pg_promote()",
            "4. Update connection strings to new primary",
            "5. Failback old primary as replica when ready"
        ],
        "tools": [
            "Patroni - High availability for PostgreSQL",
            "pg_failover - Automated failover tool",
            "pgBackRest - Backup and recovery"
        ]
    }


def _generate_recommendations(health: dict) -> list:
    """Generate recommendations based on health status"""
    recommendations = []
    
    if health["healthy_count"] == 0:
        recommendations.append({
            "severity": "critical",
            "issue": "No healthy replicas",
            "action": "Investigate replica connectivity issues immediately"
        })
    elif health["healthy_count"] < health["total_replicas"] // 2:
        recommendations.append({
            "severity": "warning",
            "issue": "More than 50% of replicas unhealthy",
            "action": "Review replica logs and network connectivity"
        })
    
    # Check for high lag
    for replica_url, status in health["replicas"].items():
        if status.get("lag_seconds", 0) > 30:
            recommendations.append({
                "severity": "warning",
                "issue": f"High replication lag on {replica_url}",
                "action": f"Lag is {status['lag_seconds']}s. Check primary write load."
            })
    
    if not recommendations:
        recommendations.append({
            "severity": "info",
            "issue": "All systems healthy",
            "action": "Continue monitoring"
        })
    
    return recommendations