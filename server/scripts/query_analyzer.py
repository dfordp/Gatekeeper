# server/scripts/query_analyzer.py
"""
Query Analysis & Optimization Script

Analyzes slow queries, generates execution plans, and recommends optimizations
"""

import asyncio
import json
import sys
from typing import List
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from core.config import DATABASE_URL
from core.query_plan_analyzer import (
    QueryPlanAnalyzer, QueryPatternAnalyzer, IndexRecommendationEngine
)
from core.logger import get_logger

logger = get_logger(__name__)


class QueryAnalysisRunner:
    """Run comprehensive query analysis"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        self.session_maker = None
    
    async def initialize(self):
        """Initialize async database connection"""
        self.engine = create_async_engine(self.database_url, echo=False)
        self.session_maker = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
    
    async def close(self):
        """Close database connection"""
        if self.engine:
            await self.engine.dispose()
    
    async def analyze_common_queries(self) -> dict:
        """Analyze execution plans for common queries"""
        async with self.session_maker() as session:
            results = {}
            
            # Query 1: List tickets for company
            query_1 = """
                SELECT t.id, t.title, t.status, t.priority
                FROM ticket t
                WHERE t.company_id = 'some-uuid'
                ORDER BY t.created_at DESC
                LIMIT 20
            """
            results["list_tickets"] = await QueryPlanAnalyzer.analyze_query(
                session, query_1, "list_tickets"
            )
            
            # Query 2: Get ticket with details
            query_2 = """
                SELECT t.*, u.name, c.name as company_name
                FROM ticket t
                LEFT JOIN user u ON t.raised_by_id = u.id
                LEFT JOIN company c ON t.company_id = c.id
                WHERE t.id = 'some-uuid'
            """
            results["get_ticket_detail"] = await QueryPlanAnalyzer.analyze_query(
                session, query_2, "get_ticket_detail"
            )
            
            # Query 3: Search tickets
            query_3 = """
                SELECT t.id, t.title, t.description
                FROM ticket t
                WHERE t.company_id = 'some-uuid'
                AND (t.title ILIKE '%search%' OR t.description ILIKE '%search%')
                LIMIT 50
            """
            results["search_tickets"] = await QueryPlanAnalyzer.analyze_query(
                session, query_3, "search_tickets"
            )
            
            # Query 4: Get RCA for ticket
            query_4 = """
                SELECT r.*, a.attachment_count
                FROM root_cause_analysis r
                LEFT JOIN (
                    SELECT rca_id, COUNT(*) as attachment_count
                    FROM attachment
                    GROUP BY rca_id
                ) a ON r.id = a.rca_id
                WHERE r.ticket_id = 'some-uuid'
            """
            results["get_rca"] = await QueryPlanAnalyzer.analyze_query(
                session, query_4, "get_rca"
            )
            
            return results
    
    async def find_slow_queries(self) -> dict:
        """Find slow queries using pg_stat_statements"""
        async with self.session_maker() as session:
            return await QueryPatternAnalyzer.analyze_slow_queries(
                session, minimum_duration_ms=100
            )
    
    async def find_missing_indexes(self) -> dict:
        """Identify missing indexes"""
        async with self.session_maker() as session:
            return await QueryPatternAnalyzer.get_missing_indexes(session)
    
    async def check_index_health(self) -> dict:
        """Check index usage and bloat"""
        async with self.session_maker() as session:
            return await QueryPatternAnalyzer.analyze_index_health(session)
    
    async def generate_recommendations(self) -> dict:
        """Generate comprehensive optimization recommendations"""
        recommendations = {
            "timestamp": datetime.now().isoformat(),
            "sections": {}
        }
        
        # Index recommendations
        recommendations["sections"]["indexes"] = {
            "ticket_table": IndexRecommendationEngine.recommend_indexes(
                "ticket",
                ["company_id", "status", "priority"],
                sequential_scan_ratio=0.7
            ),
            "user_table": IndexRecommendationEngine.recommend_indexes(
                "user",
                ["company_id", "email"],
                sequential_scan_ratio=0.6
            ),
            "incident_report_table": IndexRecommendationEngine.recommend_indexes(
                "incident_report",
                ["ticket_id", "status"],
                sequential_scan_ratio=0.8
            )
        }
        
        # Query optimizations
        recommendations["sections"]["query_optimizations"] = [
            {
                "issue": "N+1 query pattern",
                "affected_areas": ["ticket details", "user lookups"],
                "solution": "Use eager loading with joinedload() or selectinload()",
                "estimated_improvement": "50-80% latency reduction"
            },
            {
                "issue": "Missing composite indexes",
                "affected_areas": ["company_id + status filters"],
                "solution": "Create composite indexes for common multi-column filters",
                "estimated_improvement": "40-60% speed improvement"
            }
        ]
        
        return recommendations
    
    async def run_full_analysis(self):
        """Run complete analysis and generate report"""
        await self.initialize()
        
        try:
            print("\n" + "="*70)
            print("QUERY PLAN ANALYSIS & OPTIMIZATION RECOMMENDATIONS")
            print("="*70)
            
            # Analyze common queries
            print("\n[1/4] Analyzing common query execution plans...")
            query_plans = await self.analyze_common_queries()
            
            # Find slow queries
            print("[2/4] Identifying slow queries...")
            slow_queries = await self.find_slow_queries()
            
            # Find missing indexes
            print("[3/4] Identifying missing indexes...")
            missing_indexes = await self.find_missing_indexes()
            
            # Check index health
            print("[4/4] Analyzing index health...")
            index_health = await self.check_index_health()
            
            # Generate recommendations
            recommendations = await self.generate_recommendations()
            
            # Print summary
            self._print_summary(
                query_plans, slow_queries, missing_indexes,
                index_health, recommendations
            )
            
            # Save report
            report = {
                "timestamp": datetime.now().isoformat(),
                "query_plans": query_plans,
                "slow_queries": slow_queries,
                "missing_indexes": missing_indexes,
                "index_health": index_health,
                "recommendations": recommendations
            }
            
            output_file = Path("load_test_results/query_analysis_report.json")
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            
            print(f"\n✓ Report saved to {output_file}")
            
        finally:
            await self.close()
    
    def _print_summary(self, query_plans, slow_queries, missing_indexes,
                       index_health, recommendations):
        """Print analysis summary to console"""
        print("\n" + "-"*70)
        print("QUERY EXECUTION PLANS")
        print("-"*70)
        
        for query_name, analysis in query_plans.items():
            if analysis.get("status") == "success":
                issues = analysis.get("issues", [])
                print(f"\n{query_name}:")
                print(f"  Execution time: {analysis['execution_time']:.2f}ms")
                print(f"  Planning time: {analysis['planning_time']:.2f}ms")
                print(f"  Issues found: {len(issues)}")
                
                for issue in issues[:3]:  # Top 3 issues
                    print(f"    - [{issue['level'].upper()}] {issue['type']}")
                    print(f"      {issue['description']}")
                    print(f"      Fix: {issue['recommendation']}")
        
        print("\n" + "-"*70)
        print("INDEX RECOMMENDATIONS")
        print("-"*70)
        
        for table, indexes in recommendations["sections"]["indexes"].items():
            print(f"\n{table}:")
            for idx in indexes:
                print(f"  CREATE: {idx['index_name']}")
                print(f"  SQL: {idx['sql']}")
                print(f"  Benefit: {idx['benefit']}")
                print(f"  Priority: {idx['priority'].upper()}")
        
        print("\n" + "-"*70)
        print("QUERY OPTIMIZATION OPPORTUNITIES")
        print("-"*70)
        
        for optimization in recommendations["sections"]["query_optimizations"]:
            print(f"\n{optimization['issue']}:")
            print(f"  Affected: {', '.join(optimization['affected_areas'])}")
            print(f"  Solution: {optimization['solution']}")
            print(f"  Expected: {optimization['estimated_improvement']}")


async def main():
    """Main entry point"""
    runner = QueryAnalysisRunner(DATABASE_URL)
    await runner.run_full_analysis()


if __name__ == "__main__":
    asyncio.run(main())