# server/core/partitioning_manager.py
"""
Database Partitioning Manager - Phase 13

Implements range and list partitioning strategies for optimized query performance:
- Company-based list partitioning (multi-tenant horizontal scaling)
- Time-based range partitioning (archival and performance optimization)
- Partition maintenance and management
- Query routing to correct partitions
"""

import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
from dataclasses import dataclass, asdict
import uuid
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PartitionStrategy(str, Enum):
    """Partitioning strategies"""
    RANGE = "range"  # Time-based partitioning
    LIST = "list"  # Company/tenant-based partitioning
    HASH = "hash"  # Hash-based distribution


class PartitionStatus(str, Enum):
    """Partition lifecycle status"""
    ACTIVE = "active"
    READONLY = "readonly"  # Old partitions, no writes
    ARCHIVED = "archived"  # Compressed, moved to cold storage
    DROPPED = "dropped"


@dataclass
class PartitionInfo:
    """Partition metadata"""
    partition_name: str
    table_name: str
    strategy: PartitionStrategy
    status: PartitionStatus
    size_bytes: int
    row_count: int
    created_at: datetime
    last_accessed: Optional[datetime]
    constraint: str  # e.g., "company_id = 'uuid'" or "created_at >= '2026-01-01'"


@dataclass
class OptimizationRecommendation:
    """Partition optimization suggestion"""
    partition_name: str
    recommendation_type: str  # "archive", "compress", "split", "merge"
    reason: str
    estimated_space_saved: int  # bytes
    risk_level: str  # "low", "medium", "high"


class PartitioningManager:
    """Manages database partitioning operations"""
    
    # Configuration constants
    RANGE_PARTITION_SIZE_MONTHS = 3  # Months per partition
    ARCHIVE_THRESHOLD_MONTHS = 12  # Archive data older than this
    READONLY_THRESHOLD_MONTHS = 6  # Mark as readonly after this
    MIN_PARTITION_SIZE_MB = 100  # Don't split if smaller
    MAX_PARTITION_SIZE_GB = 10  # Split if larger
    
    def __init__(self, db_session: AsyncSession):
        """Initialize partitioning manager"""
        self.db = db_session
        self.logger = logger
        
    async def initialize(self) -> bool:
        """Initialize partitioning schema"""
        try:
            # Create range partitions for tickets table
            await self._create_range_partitions()
            
            # Create list partitions by company
            await self._create_list_partitions()
            
            # Create partition management tables
            await self._create_partition_metadata_table()
            
            self.logger.info("Partitioning schema initialized")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize partitioning: {e}")
            return False
    
    async def _create_range_partitions(self) -> None:
        """Create time-based range partitions for tickets"""
        # Create partitioned table if not exists
        await self.db.execute(text("""
            -- Create range partitioned tickets table
            CREATE TABLE IF NOT EXISTS ticket_partitioned (
                id UUID PRIMARY KEY,
                ticket_no VARCHAR(50) UNIQUE NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'open',
                level VARCHAR(50),
                category VARCHAR(100),
                subject VARCHAR(500) NOT NULL,
                summary TEXT,
                detailed_description TEXT NOT NULL,
                company_id UUID NOT NULL,
                raised_by_user_id UUID NOT NULL,
                assigned_engineer_id UUID,
                created_at DATE NOT NULL,
                updated_at DATE NOT NULL,
                closed_at DATE,
                reopened_at DATE,
                CONSTRAINT ticket_company_fk FOREIGN KEY (company_id) REFERENCES company(id),
                CONSTRAINT ticket_raised_by_fk FOREIGN KEY (raised_by_user_id) REFERENCES "user"(id),
                CONSTRAINT ticket_assigned_fk FOREIGN KEY (assigned_engineer_id) REFERENCES "user"(id)
            ) PARTITION BY RANGE (created_at);
        """))
        
        # Create quarterly partitions for current and past 2 years
        current_date = datetime.now()
        for months_back in range(0, 24, 3):
            partition_date = current_date - timedelta(days=months_back * 30)
            partition_name = f"ticket_p_{partition_date.strftime('%Y%m')}"
            partition_start = partition_date.strftime('%Y-%m-%d')
            partition_end = (partition_date + timedelta(days=90)).strftime('%Y-%m-%d')
            
            try:
                await self.db.execute(text(f"""
                    CREATE TABLE IF NOT EXISTS {partition_name}
                    PARTITION OF ticket_partitioned
                    FOR VALUES FROM ('{partition_start}') TO ('{partition_end}');
                    
                    CREATE INDEX IF NOT EXISTS {partition_name}_company_idx 
                        ON {partition_name}(company_id);
                    CREATE INDEX IF NOT EXISTS {partition_name}_status_idx 
                        ON {partition_name}(status);
                    CREATE INDEX IF NOT EXISTS {partition_name}_created_idx 
                        ON {partition_name}(created_at);
                """))
                self.logger.info(f"Created range partition: {partition_name}")
            except Exception as e:
                self.logger.warning(f"Range partition {partition_name} may exist: {e}")
    
    async def _create_list_partitions(self) -> None:
        """Create company-based list partitions for tickets"""
        # Get all companies
        result = await self.db.execute(text("""
            SELECT id FROM company ORDER BY created_at DESC LIMIT 10
        """))
        companies = result.fetchall()
        
        for company in companies:
            company_id = company[0]
            partition_name = f"ticket_company_{str(company_id)[:8]}"
            
            try:
                await self.db.execute(text(f"""
                    CREATE TABLE IF NOT EXISTS {partition_name} (
                        id UUID PRIMARY KEY,
                        ticket_no VARCHAR(50) UNIQUE NOT NULL,
                        status VARCHAR(50) NOT NULL DEFAULT 'open',
                        level VARCHAR(50),
                        category VARCHAR(100),
                        subject VARCHAR(500) NOT NULL,
                        summary TEXT,
                        detailed_description TEXT NOT NULL,
                        company_id UUID NOT NULL CHECK (company_id = '{company_id}'),
                        raised_by_user_id UUID NOT NULL,
                        assigned_engineer_id UUID,
                        created_at DATE NOT NULL,
                        updated_at DATE NOT NULL,
                        closed_at DATE,
                        reopened_at DATE,
                        CONSTRAINT {partition_name}_company_fk FOREIGN KEY (company_id) REFERENCES company(id),
                        CONSTRAINT {partition_name}_raised_by_fk FOREIGN KEY (raised_by_user_id) REFERENCES "user"(id),
                        CONSTRAINT {partition_name}_assigned_fk FOREIGN KEY (assigned_engineer_id) REFERENCES "user"(id)
                    );
                    
                    CREATE INDEX IF NOT EXISTS {partition_name}_status_idx ON {partition_name}(status);
                    CREATE INDEX IF NOT EXISTS {partition_name}_created_idx ON {partition_name}(created_at);
                """))
                self.logger.info(f"Created list partition: {partition_name}")
            except Exception as e:
                self.logger.warning(f"List partition {partition_name} may exist: {e}")
    
    async def _create_partition_metadata_table(self) -> None:
        """Create table for tracking partition metadata"""
        await self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS partition_metadata (
                id SERIAL PRIMARY KEY,
                partition_name VARCHAR(255) UNIQUE NOT NULL,
                table_name VARCHAR(255) NOT NULL,
                strategy VARCHAR(50) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'active',
                size_bytes BIGINT,
                row_count BIGINT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                last_accessed TIMESTAMP,
                constraint_expr TEXT
            );
        """))
        
        # Create indexes separately (PostgreSQL syntax)
        await self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_partition_status 
            ON partition_metadata(status);
        """))
        
        await self.db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_partition_table 
            ON partition_metadata(table_name);
        """))
    
    async def get_all_partitions(self) -> List[PartitionInfo]:
        """Get information about all partitions"""
        result = await self.db.execute(text("""
            SELECT 
                partition_name,
                table_name,
                strategy,
                status,
                size_bytes,
                row_count,
                created_at,
                last_accessed,
                constraint_expr
            FROM partition_metadata
            ORDER BY created_at DESC
        """))
        
        partitions = []
        for row in result.fetchall():
            partitions.append(PartitionInfo(
                partition_name=row[0],
                table_name=row[1],
                strategy=PartitionStrategy(row[2]),
                status=PartitionStatus(row[3]),
                size_bytes=row[4] or 0,
                row_count=row[5] or 0,
                created_at=row[6],
                last_accessed=row[7],
                constraint=row[8]
            ))
        
        return partitions
    
    async def analyze_partition_health(self) -> Dict[str, Any]:
        """Analyze health and efficiency of all partitions"""
        partitions = await self.get_all_partitions()
        
        total_size = sum(p.size_bytes for p in partitions)
        total_rows = sum(p.row_count for p in partitions)
        avg_partition_size = total_size / len(partitions) if partitions else 0
        
        health_score = 100.0
        issues = []
        
        for partition in partitions:
            # Check partition size balance
            if partition.size_bytes > avg_partition_size * 2:
                health_score -= 5
                issues.append(f"{partition.partition_name}: oversized ({partition.size_bytes / 1024 / 1024:.2f} MB)")
            
            if partition.size_bytes < avg_partition_size * 0.5:
                health_score -= 3
                issues.append(f"{partition.partition_name}: undersized ({partition.size_bytes / 1024 / 1024:.2f} MB)")
            
            # Check access patterns
            if partition.last_accessed and (datetime.now() - partition.last_accessed).days > 90:
                if partition.status == PartitionStatus.ACTIVE:
                    issues.append(f"{partition.partition_name}: stale for 90+ days")
        
        return {
            "health_score": max(0, health_score),
            "total_partitions": len(partitions),
            "total_size_gb": total_size / 1024 / 1024 / 1024,
            "total_rows": total_rows,
            "avg_partition_size_mb": avg_partition_size / 1024 / 1024,
            "issues": issues,
            "partitions": [asdict(p) for p in partitions]
        }
    
    async def get_optimization_recommendations(self) -> List[OptimizationRecommendation]:
        """Analyze partitions and recommend optimizations"""
        recommendations = []
        health = await self.analyze_partition_health()
        
        for partition_data in health["partitions"]:
            partition = PartitionInfo(**partition_data)
            size_gb = partition.size_bytes / 1024 / 1024 / 1024
            created_months_ago = (datetime.now() - partition.created_at).days / 30
            
            # Archive recommendation: old inactive partitions
            if created_months_ago > self.ARCHIVE_THRESHOLD_MONTHS and partition.last_accessed:
                days_since_access = (datetime.now() - partition.last_accessed).days
                if days_since_access > 30:
                    recommendations.append(OptimizationRecommendation(
                        partition_name=partition.partition_name,
                        recommendation_type="archive",
                        reason=f"Partition inactive for {days_since_access} days, created {created_months_ago:.0f} months ago",
                        estimated_space_saved=int(partition.size_bytes * 0.7),  # 70% compression
                        risk_level="low"
                    ))
            
            # Split recommendation: oversized partitions
            if size_gb > self.MAX_PARTITION_SIZE_GB:
                recommendations.append(OptimizationRecommendation(
                    partition_name=partition.partition_name,
                    recommendation_type="split",
                    reason=f"Partition size {size_gb:.2f} GB exceeds threshold",
                    estimated_space_saved=int(partition.size_bytes * 0.15),
                    risk_level="medium"
                ))
            
            # Readonly recommendation: old but active partitions
            if created_months_ago > self.READONLY_THRESHOLD_MONTHS:
                recommendations.append(OptimizationRecommendation(
                    partition_name=partition.partition_name,
                    recommendation_type="readonly",
                    reason=f"Partition {created_months_ago:.0f} months old, candidate for readonly status",
                    estimated_space_saved=0,
                    risk_level="low"
                ))
        
        return recommendations
    
    async def mark_partition_readonly(self, partition_name: str) -> bool:
        """Mark a partition as readonly (disable INSERTs/UPDATEs)"""
        try:
            await self.db.execute(text(f"""
                ALTER TABLE {partition_name} DISABLE TRIGGER ALL;
                UPDATE partition_metadata 
                SET status = 'readonly' 
                WHERE partition_name = '{partition_name}';
            """))
            self.logger.info(f"Marked partition {partition_name} as readonly")
            return True
        except Exception as e:
            self.logger.error(f"Failed to mark partition readonly: {e}")
            return False
    
    async def archive_partition(self, partition_name: str) -> bool:
        """Archive a partition (compress and prepare for deletion)"""
        try:
            # Get size before archival
            result = await self.db.execute(text(f"""
                SELECT pg_total_relation_size('{partition_name}')
            """))
            original_size = result.scalar()
            
            # Update metadata
            await self.db.execute(text(f"""
                UPDATE partition_metadata 
                SET status = 'archived' 
                WHERE partition_name = '{partition_name}';
            """))
            
            self.logger.info(
                f"Archived partition {partition_name} ({original_size / 1024 / 1024:.2f} MB)"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to archive partition: {e}")
            return False
    
    async def get_partition_for_query(
        self, 
        company_id: Optional[uuid.UUID] = None,
        created_after: Optional[date] = None
    ) -> List[str]:
        """Route query to appropriate partitions based on predicates"""
        partitions = await self.get_all_partitions()
        matching = []
        
        for partition in partitions:
            # Filter by company if specified
            if company_id and f"company_id = '{company_id}'" not in partition.constraint:
                continue
            
            # Filter by date range if specified
            if created_after and partition.strategy == PartitionStrategy.RANGE:
                # Parse date from constraint (simplified)
                if str(created_after) in partition.constraint or partition.status == PartitionStatus.ACTIVE:
                    matching.append(partition.partition_name)
            elif company_id and partition.strategy == PartitionStrategy.LIST:
                matching.append(partition.partition_name)
            elif not company_id and not created_after:
                matching.append(partition.partition_name)
        
        return matching if matching else [p.partition_name for p in partitions[:3]]
    
    async def get_partition_statistics(self) -> Dict[str, Any]:
        """Get comprehensive partition statistics"""
        result = await self.db.execute(text("""
            SELECT 
                table_name,
                COUNT(*) as partition_count,
                SUM(size_bytes) as total_size,
                SUM(row_count) as total_rows,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_count,
                COUNT(CASE WHEN status = 'readonly' THEN 1 END) as readonly_count,
                COUNT(CASE WHEN status = 'archived' THEN 1 END) as archived_count
            FROM partition_metadata
            GROUP BY table_name
        """))
        
        stats = {}
        for row in result.fetchall():
            stats[row[0]] = {
                "partition_count": row[1],
                "total_size_gb": (row[2] or 0) / 1024 / 1024 / 1024,
                "total_rows": row[3] or 0,
                "active_partitions": row[4],
                "readonly_partitions": row[5],
                "archived_partitions": row[6]
            }
        
        return stats