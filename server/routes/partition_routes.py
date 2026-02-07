# server/routes/partition_routes.py
"""
Partition Management Routes - Phase 13

REST API for managing database partitions:
- View partition information and health
- Get optimization recommendations
- Execute partition operations (archive, split, readonly)
- Monitor partition statistics
"""

import logging
from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime

from core.async_database import get_async_db
from core.partitioning_manager import (
    PartitioningManager,
    OptimizationRecommendation,
    PartitionInfo
)
from middleware.auth_middleware import get_current_admin
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/partitions", tags=["partitions"])


@router.get("/health")
async def get_partition_health(
    db: AsyncSession = Depends(get_async_db),
    _=Depends(get_current_admin)
):
    """Get overall partition health and statistics"""
    manager = PartitioningManager(db)
    health = await manager.analyze_partition_health()
    
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "data": health
    }


@router.get("/list")
async def list_partitions(
    db: AsyncSession = Depends(get_async_db),
    _=Depends(get_current_admin)
):
    """List all partitions with detailed information"""
    manager = PartitioningManager(db)
    partitions = await manager.get_all_partitions()
    
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "total_count": len(partitions),
        "data": [
            {
                "partition_name": p.partition_name,
                "table_name": p.table_name,
                "strategy": p.strategy.value,
                "status": p.status.value,
                "size_mb": p.size_bytes / 1024 / 1024,
                "row_count": p.row_count,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "last_accessed": p.last_accessed.isoformat() if p.last_accessed else None
            }
            for p in partitions
        ]
    }


@router.get("/recommendations")
async def get_partition_recommendations(
    db: AsyncSession = Depends(get_async_db),
    _=Depends(get_current_admin)
):
    """Get partition optimization recommendations"""
    manager = PartitioningManager(db)
    recommendations = await manager.get_optimization_recommendations()
    
    # Group by type
    by_type = {}
    for rec in recommendations:
        if rec.recommendation_type not in by_type:
            by_type[rec.recommendation_type] = []
        by_type[rec.recommendation_type].append({
            "partition_name": rec.partition_name,
            "reason": rec.reason,
            "estimated_space_saved_mb": rec.estimated_space_saved / 1024 / 1024,
            "risk_level": rec.risk_level
        })
    
    total_space_saved = sum(r.estimated_space_saved for r in recommendations)
    
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "total_recommendations": len(recommendations),
        "estimated_total_space_saved_gb": total_space_saved / 1024 / 1024 / 1024,
        "by_type": by_type
    }


@router.get("/statistics")
async def get_partition_statistics(
    db: AsyncSession = Depends(get_async_db),
    _=Depends(get_current_admin)
):
    """Get comprehensive partition statistics"""
    manager = PartitioningManager(db)
    stats = await manager.get_partition_statistics()
    
    total_size_gb = sum(s["total_size_gb"] for s in stats.values())
    total_rows = sum(s["total_rows"] for s in stats.values())
    
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_tables": len(stats),
            "total_partitions": sum(s["partition_count"] for s in stats.values()),
            "total_size_gb": total_size_gb,
            "total_rows": total_rows
        },
        "by_table": stats
    }


@router.post("/mark-readonly/{partition_name}")
async def mark_partition_readonly(
    partition_name: str,
    db: AsyncSession = Depends(get_async_db),
    _=Depends(get_current_admin)
):
    """Mark a partition as readonly (disable write operations)"""
    manager = PartitioningManager(db)
    
    try:
        success = await manager.mark_partition_readonly(partition_name)
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to mark partition {partition_name} as readonly"
            )
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "partition_name": partition_name,
            "action": "marked_readonly",
            "message": f"Partition {partition_name} is now readonly"
        }
    except Exception as e:
        logger.error(f"Error marking partition readonly: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/archive/{partition_name}")
async def archive_partition(
    partition_name: str,
    db: AsyncSession = Depends(get_async_db),
    _=Depends(get_current_admin)
):
    """Archive a partition (compress and prepare for cold storage)"""
    manager = PartitioningManager(db)
    
    try:
        success = await manager.archive_partition(partition_name)
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to archive partition {partition_name}"
            )
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "partition_name": partition_name,
            "action": "archived",
            "message": f"Partition {partition_name} has been archived"
        }
    except Exception as e:
        logger.error(f"Error archiving partition: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/routing-info")
async def get_partition_routing_info(
    company_id: str = None,
    created_after: str = None,
    db: AsyncSession = Depends(get_async_db),
    _=Depends(get_current_admin)
):
    """Get which partitions would be used for a query with given predicates"""
    manager = PartitioningManager(db)
    
    try:
        from uuid import UUID
        from datetime import datetime as dt
        
        # Validate and convert company_id to UUID
        company_uuid = None
        if company_id:
            try:
                company_uuid = UUID(company_id)
            except (ValueError, AttributeError):
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid UUID format for company_id: {company_id}"
                )
        
        # Validate and convert created_after to date
        created_date = None
        if created_after:
            try:
                created_date = dt.fromisoformat(created_after).date()
            except (ValueError, AttributeError):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid date format for created_after: {created_after}. Use ISO format (YYYY-MM-DD)"
                )
        
        partitions = await manager.get_partition_for_query(company_uuid, created_date)
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "predicates": {
                "company_id": company_id,
                "created_after": created_after
            },
            "matching_partitions": partitions,
            "partition_count": len(partitions)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")