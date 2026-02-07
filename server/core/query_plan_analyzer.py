# server/core/query_plan_analyzer.py
"""
Query Plan Analysis & Optimization
Analyzes PostgreSQL EXPLAIN ANALYZE output to identify optimization opportunities

Features:
- EXPLAIN ANALYZE query execution plans
- N+1 query detection
- Missing index identification
- Sequential scan warnings
- Index recommendation suggestions
- Query pattern analysis with statistics
"""

import json
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from core.logger import get_logger

logger = get_logger(__name__)


class QueryIssueLevel(str, Enum):
    """Issue severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class QueryIssue:
    """Represents a query optimization issue"""
    level: QueryIssueLevel
    issue_type: str
    description: str
    sql_snippet: str
    recommendation: str
    estimated_improvement: str  # e.g., "50% faster"
    affected_tables: List[str]


@dataclass
class QueryPlanNode:
    """Represents a node in the execution plan"""
    node_type: str
    relation_name: Optional[str]
    startup_cost: float
    total_cost: float
    actual_time: Optional[Tuple[float, float]]  # (startup, total)
    rows: int
    actual_rows: Optional[int]
    width: int
    
    @property
    def is_sequential_scan(self) -> bool:
        return "Seq Scan" in self.node_type
    
    @property
    def is_index_scan(self) -> bool:
        return "Index" in self.node_type
    
    @property
    def is_slow(self, threshold_ms: float = 100) -> bool:
        """Check if node took longer than threshold"""
        if self.actual_time is None:
            return False
        actual_total_ms = self.actual_time[1]
        return actual_total_ms > threshold_ms


class QueryPlanAnalyzer:
    """Analyzes query execution plans"""
    
    # Slow node thresholds (milliseconds)
    SLOW_NODE_THRESHOLD = 50
    VERY_SLOW_NODE_THRESHOLD = 100
    
    @staticmethod
    async def analyze_query(
        db: AsyncSession,
        sql: str,
        query_name: str = "unknown"
    ) -> Dict[str, Any]:
        """
        Analyze a query using EXPLAIN ANALYZE
        
        Args:
            db: Async database session
            sql: SQL query to analyze
            query_name: Name/description of query
            
        Returns:
            Dictionary with plan analysis
        """
        try:
            # Execute EXPLAIN ANALYZE
            result = await db.execute(
                text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}")
            )
            plan_json = result.scalar()
            
            if not plan_json:
                return {
                    "status": "error",
                    "message": "Failed to get query plan"
                }
            
            # Parse plan
            plan_data = json.loads(plan_json)
            plan = plan_data[0]["Plan"]
            
            # Extract issues
            issues = []
            
            # Check for sequential scans
            seq_scans = QueryPlanAnalyzer._find_sequential_scans(plan)
            for table_name, node in seq_scans:
                issues.append(QueryIssue(
                    level=QueryIssueLevel.WARNING,
                    issue_type="SEQUENTIAL_SCAN",
                    description=f"Sequential scan on {table_name} (could benefit from index)",
                    sql_snippet=sql[:100],
                    recommendation=f"Create index on {table_name} for WHERE clause columns",
                    estimated_improvement="50-80% faster",
                    affected_tables=[table_name]
                ))
            
            # Check for high row count filtering
            high_filters = QueryPlanAnalyzer._find_high_filter_rates(plan)
            for table_name, ratio in high_filters:
                if ratio > 0.9:
                    issues.append(QueryIssue(
                        level=QueryIssueLevel.WARNING,
                        issue_type="HIGH_FILTER_RATE",
                        description=f"High filter rate on {table_name} ({ratio*100:.1f}%)",
                        sql_snippet=sql[:100],
                        recommendation="Consider adding composite index on filtered columns",
                        estimated_improvement="30-50% faster",
                        affected_tables=[table_name]
                    ))
            
            # Check for missing index joins
            bad_joins = QueryPlanAnalyzer._find_bad_joins(plan)
            for join_type, description in bad_joins:
                issues.append(QueryIssue(
                    level=QueryIssueLevel.WARNING,
                    issue_type="SUBOPTIMAL_JOIN",
                    description=description,
                    sql_snippet=sql[:100],
                    recommendation="Add foreign key index or consider join order",
                    estimated_improvement="40-70% faster",
                    affected_tables=[]
                ))
            
            return {
                "status": "success",
                "query_name": query_name,
                "total_cost": plan_data[0]["Total Runtime"],
                "planning_time": plan_data[0]["Planning Time"],
                "execution_time": plan_data[0]["Execution Time"],
                "issues": [
                    {
                        "level": issue.level.value,
                        "type": issue.issue_type,
                        "description": issue.description,
                        "recommendation": issue.recommendation,
                        "estimated_improvement": issue.estimated_improvement,
                        "tables": issue.affected_tables
                    }
                    for issue in issues
                ],
                "plan_summary": {
                    "node_count": QueryPlanAnalyzer._count_nodes(plan),
                    "max_depth": QueryPlanAnalyzer._get_max_depth(plan),
                    "scan_types": QueryPlanAnalyzer._get_scan_types(plan)
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing query '{query_name}': {e}")
            return {
                "status": "error",
                "message": str(e),
                "query_name": query_name
            }
    
    @staticmethod
    def _find_sequential_scans(plan: Dict, results: List = None) -> List[Tuple[str, Dict]]:
        """Find all sequential scans in plan tree"""
        if results is None:
            results = []
        
        if "Seq Scan" in plan.get("Node Type", ""):
            table = plan.get("Relation Name", "unknown")
            results.append((table, plan))
        
        for subplan in plan.get("Plans", []):
            QueryPlanAnalyzer._find_sequential_scans(subplan, results)
        
        return results
    
    @staticmethod
    def _find_high_filter_rates(plan: Dict, results: List = None) -> List[Tuple[str, float]]:
        """Find nodes with high filter rates (estimate rows != actual rows)"""
        if results is None:
            results = []
        
        plan_rows = plan.get("Plan Rows", 1)
        actual_rows = plan.get("Actual Rows", 1)
        
        if plan_rows > 0:
            filter_ratio = actual_rows / plan_rows
            if filter_ratio > 0.5:  # More than 50% filtered
                table = plan.get("Relation Name", "unknown")
                results.append((table, 1 - filter_ratio))
        
        for subplan in plan.get("Plans", []):
            QueryPlanAnalyzer._find_high_filter_rates(subplan, results)
        
        return results
    
    @staticmethod
    def _find_bad_joins(plan: Dict, results: List = None) -> List[Tuple[str, str]]:
        """Find suboptimal joins (nested loop without index)"""
        if results is None:
            results = []
        
        node_type = plan.get("Node Type", "")
        
        if "Nested Loop" in node_type:
            # Check if expensive
            cost = plan.get("Total Cost", 0)
            if cost > 1000:
                results.append((
                    "Nested Loop",
                    f"Expensive nested loop join (cost: {cost})"
                ))
        elif "Hash" in node_type and cost > 5000:
            results.append((
                "Hash Join",
                f"Large hash join (cost: {cost})"
            ))
        
        for subplan in plan.get("Plans", []):
            QueryPlanAnalyzer._find_bad_joins(subplan, results)
        
        return results
    
    @staticmethod
    def _count_nodes(plan: Dict) -> int:
        """Count total nodes in plan tree"""
        count = 1
        for subplan in plan.get("Plans", []):
            count += QueryPlanAnalyzer._count_nodes(subplan)
        return count
    
    @staticmethod
    def _get_max_depth(plan: Dict) -> int:
        """Get maximum depth of plan tree"""
        if not plan.get("Plans"):
            return 1
        return 1 + max(QueryPlanAnalyzer._get_max_depth(p) for p in plan["Plans"])
    
    @staticmethod
    def _get_scan_types(plan: Dict, types: Dict = None) -> Dict[str, int]:
        """Get counts of each scan type"""
        if types is None:
            types = {}
        
        node_type = plan.get("Node Type", "Unknown")
        types[node_type] = types.get(node_type, 0) + 1
        
        for subplan in plan.get("Plans", []):
            QueryPlanAnalyzer._get_scan_types(subplan, types)
        
        return types


class QueryPatternAnalyzer:
    """Analyzes query patterns to identify optimization opportunities"""
    
    @staticmethod
    async def analyze_slow_queries(
        db: AsyncSession,
        minimum_duration_ms: float = 100,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Query PostgreSQL log for slow queries
        
        Note: Requires log_statement='all' or log_min_duration_statement=100
        """
        try:
            # This would require log shipping or pg_stat_statements
            # For now, return structured recommendation
            return {
                "status": "info",
                "message": "Enable log_statement in PostgreSQL config to track slow queries",
                "setup_steps": [
                    "SET log_statement = 'all';",
                    "SET log_min_duration_statement = 100;  -- Log queries >100ms",
                    "ANALYZE; -- to update query planner statistics"
                ],
                "query": "SELECT query, calls, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 20;"
            }
        except Exception as e:
            logger.error(f"Error analyzing slow queries: {e}")
            return {"status": "error", "message": str(e)}
    
    @staticmethod
    async def get_missing_indexes(
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Identify potentially missing indexes based on sequential scans
        Uses pg_stat_user_tables and pg_stat_user_indexes
        """
        try:
            result = await db.execute(text("""
                SELECT 
                    schemaname,
                    tablename,
                    seq_scan,
                    idx_scan,
                    seq_tup_read,
                    idx_tup_fetch,
                    ROUND(100 * seq_scan / NULLIF(seq_scan + idx_scan, 0)) as seq_pct
                FROM pg_stat_user_tables
                WHERE seq_scan > 100
                ORDER BY seq_scan DESC
                LIMIT 20
            """))
            
            rows = result.fetchall()
            
            recommendations = []
            for row in rows:
                schema, table, seq_scans, idx_scans, seq_tuples, idx_tuples, seq_pct = row
                
                if seq_pct > 50:
                    recommendations.append({
                        "table": f"{schema}.{table}",
                        "issue": "High sequential scan ratio",
                        "sequential_scans": seq_scans,
                        "index_scans": idx_scans,
                        "seq_percentage": seq_pct,
                        "recommendation": f"Table {table} is mostly scanned sequentially. Consider adding indexes on frequently filtered columns."
                    })
            
            return {
                "status": "success",
                "table_recommendations": recommendations,
                "total_tables_analyzed": len(rows)
            }
            
        except Exception as e:
            logger.error(f"Error identifying missing indexes: {e}")
            return {"status": "error", "message": str(e)}
    
    @staticmethod
    async def analyze_index_health(
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Analyze index usage and identify unused or bloated indexes
        """
        try:
            # Unused indexes
            unused = await db.execute(text("""
                SELECT 
                    schemaname,
                    tablename,
                    indexname,
                    idx_scan as scans
                FROM pg_stat_user_indexes
                WHERE idx_scan = 0
                ORDER BY pg_relation_size(indexrelid) DESC
            """))
            
            unused_indexes = [
                {
                    "schema": row[0],
                    "table": row[1],
                    "index": row[2],
                    "size_mb": None,
                    "recommendation": f"Consider dropping index {row[2]} (never used)"
                }
                for row in unused.fetchall()
            ]
            
            # Bloated indexes
            bloated = await db.execute(text("""
                SELECT 
                    indexrelname,
                    ROUND(100 * (pg_relation_size(indexrelid) - pg_relation_size(relfilenode))::numeric / 
                          pg_relation_size(indexrelid)) as bloat_ratio
                FROM pg_stat_user_indexes i
                JOIN pg_index idx ON i.indexrelid = idx.indexrelid
                JOIN pg_class c ON idx.indrelid = c.oid
                WHERE (pg_relation_size(indexrelid) - pg_relation_size(relfilenode)) > 1000000
                ORDER BY pg_relation_size(indexrelid) DESC
            """))
            
            bloated_indexes = [
                {
                    "index": row[0],
                    "bloat_percentage": row[1],
                    "recommendation": f"REINDEX {row[0]} to reclaim space ({row[1]}% bloated)"
                }
                for row in bloated.fetchall()
            ]
            
            return {
                "status": "success",
                "unused_indexes": unused_indexes,
                "bloated_indexes": bloated_indexes
            }
            
        except Exception as e:
            logger.error(f"Error analyzing index health: {e}")
            return {"status": "error", "message": str(e)}


class IndexRecommendationEngine:
    """Generates specific index recommendations"""
    
    COMMON_FILTER_COLUMNS = {
        "ticket": ["status", "company_id", "priority", "created_at"],
        "user": ["company_id", "role", "email"],
        "company": ["name"],
        "incident_report": ["ticket_id", "status", "created_at"],
        "rca": ["ticket_id", "status"]
    }
    
    @staticmethod
    def recommend_indexes(
        table_name: str,
        query_patterns: List[str],
        sequential_scan_ratio: float = 0.8
    ) -> List[Dict[str, str]]:
        """
        Generate index recommendations for a table
        
        Args:
            table_name: Table to optimize
            query_patterns: List of WHERE clause patterns
            sequential_scan_ratio: Ratio of sequential scans (0-1)
            
        Returns:
            List of recommended indexes
        """
        recommendations = []
        
        # Recommend single column indexes for common filters
        if table_name in IndexRecommendationEngine.COMMON_FILTER_COLUMNS:
            for col in IndexRecommendationEngine.COMMON_FILTER_COLUMNS[table_name]:
                recommendations.append({
                    "index_name": f"idx_{table_name}_{col}",
                    "sql": f"CREATE INDEX idx_{table_name}_{col} ON {table_name}({col});",
                    "benefit": f"Speeds up queries filtering by {col}",
                    "priority": "high" if sequential_scan_ratio > 0.8 else "medium"
                })
        
        # Recommend composite indexes based on patterns
        if "company_id" in query_patterns and "status" in query_patterns:
            recommendations.append({
                "index_name": f"idx_{table_name}_company_status",
                "sql": f"CREATE INDEX idx_{table_name}_company_status ON {table_name}(company_id, status);",
                "benefit": "Optimizes queries filtering by company AND status",
                "priority": "high"
            })
        
        return recommendations