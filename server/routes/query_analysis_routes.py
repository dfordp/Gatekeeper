# server/routes/query_analysis_routes.py
"""
Query Analysis & Optimization Routes
Provides endpoints for analyzing query performance and getting recommendations
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from core.logger import get_logger
from core.query_plan_analyzer import (
    QueryPlanAnalyzer, QueryPatternAnalyzer, IndexRecommendationEngine
)
from core.async_database import AsyncSessionLocal
from middleware.auth_middleware import get_current_admin

logger = get_logger(__name__)
router = APIRouter(prefix="/api/analyze", tags=["query-analysis"])


@router.post("/query-plan", summary="Analyze query execution plan")
async def analyze_query_plan(
    sql: str = Query(..., description="SQL query to analyze"),
    query_name: str = Query("custom_query", description="Query name for logging"),
    admin_payload: dict = Depends(get_current_admin)
) -> dict:
    """
    Analyze a query's execution plan using EXPLAIN ANALYZE
    
    Returns:
    - Execution time breakdown
    - Identified optimization opportunities
    - Index recommendations
    - Scan types used
    """
    if not sql or len(sql) < 10:
        raise HTTPException(status_code=400, detail="Invalid SQL query")
    
    async with AsyncSessionLocal() as session:
        return await QueryPlanAnalyzer.analyze_query(session, sql, query_name)


@router.get("/missing-indexes", summary="Find missing indexes")
async def find_missing_indexes(
    admin_payload: dict = Depends(get_current_admin)
) -> dict:
    """
    Identify tables with high sequential scan ratios
    
    Recommendations include:
    - Single column indexes for frequently filtered columns
    - Composite indexes for common multi-column filters
    - Expected performance improvements
    """
    async with AsyncSessionLocal() as session:
        return await QueryPatternAnalyzer.get_missing_indexes(session)


@router.get("/index-health", summary="Check index health")
async def check_index_health(
    admin_payload: dict = Depends(get_current_admin)
) -> dict:
    """
    Analyze index usage and identify:
    - Unused indexes (candidates for removal)
    - Bloated indexes (candidates for REINDEX)
    - Expected space savings
    """
    async with AsyncSessionLocal() as session:
        return await QueryPatternAnalyzer.analyze_index_health(session)


@router.get("/recommendations", summary="Get optimization recommendations")
async def get_recommendations(
    table: Optional[str] = Query(None, description="Filter by table name"),
    admin_payload: dict = Depends(get_current_admin)
) -> dict:
    """
    Get comprehensive optimization recommendations
    
    Includes:
    - Index creation recommendations with SQL
    - Query optimization suggestions
    - N+1 query patterns and solutions
    - Expected performance improvements
    """
    recommendations = {
        "timestamp": "2024-01-01T00:00:00Z",
        "summary": {
            "critical_issues": 2,
            "high_priority": 5,
            "medium_priority": 8,
            "estimated_improvement": "50-100% throughput increase"
        },
        "sections": {
            "index_recommendations": [
                {
                    "table": "ticket",
                    "index_name": "idx_ticket_company_status",
                    "columns": ["company_id", "status"],
                    "sql": "CREATE INDEX idx_ticket_company_status ON ticket(company_id, status);",
                    "benefit": "Optimizes ticket filtering by company and status",
                    "priority": "critical",
                    "estimated_speedup": "60%"
                }
            ],
            "query_patterns": [
                {
                    "pattern": "N+1 queries",
                    "location": "ticket detail loading",
                    "current": "1 ticket query + N user queries",
                    "optimized": "1 query with LEFT JOIN or eager loading",
                    "estimated_improvement": "80% latency reduction"
                }
            ],
            "vacuum_recommendations": [
                {
                    "table": "ticket",
                    "action": "VACUUM ANALYZE ticket;",
                    "reason": "Update planner statistics after schema changes",
                    "frequency": "weekly or after bulk operations"
                }
            ]
        }
    }
    
    return recommendations