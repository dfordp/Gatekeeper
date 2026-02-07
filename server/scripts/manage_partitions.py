# server/scripts/manage_partitions.py
"""
Partition Management CLI Tool - Phase 13

Command-line utility for database partition administration:
- Analyze partition health
- Generate optimization recommendations
- Execute partition operations (archive, split, readonly)
- Generate reports
"""

import asyncio
import sys
import json
from datetime import datetime
from typing import Optional
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from core.config import DATABASE_URL
from core.partitioning_manager import PartitioningManager


class PartitionManagementCLI:
    """CLI for partition management operations"""
    
    def __init__(self):
        """Initialize CLI with database connection"""
        self.engine = None
        self.session_maker = None
    
    async def init_db(self):
        """Initialize async database connection"""
        self.engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            pool_size=10,
            max_overflow=5
        )
        self.session_maker = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False
        )
    
    async def close_db(self):
        """Close database connection"""
        if self.engine:
            await self.engine.dispose()
    
    async def analyze_health(self, output_file: Optional[str] = None):
        """Analyze partition health and print results"""
        async with self.session_maker() as session:
            manager = PartitioningManager(session)
            health = await manager.analyze_partition_health()
            
            print("\n" + "="*80)
            print("PARTITION HEALTH ANALYSIS")
            print("="*80)
            print(f"Health Score: {health['health_score']:.1f}/100")
            print(f"Total Partitions: {health['total_partitions']}")
            print(f"Total Size: {health['total_size_gb']:.2f} GB")
            print(f"Total Rows: {health['total_rows']:,}")
            print(f"Avg Partition Size: {health['avg_partition_size_mb']:.2f} MB")
            
            if health['issues']:
                print(f"\nIssues Found ({len(health['issues'])}):")
                for issue in health['issues']:
                    print(f"  ⚠️  {issue}")
            else:
                print("\n✓ No issues detected")
            
            print("\nPartition Details:")
            print("-" * 80)
            for partition in health['partitions']:
                status_icon = "🟢" if partition['status'] == 'active' else "🔵" if partition['status'] == 'readonly' else "⚫"
                print(
                    f"{status_icon} {partition['partition_name']:<30} "
                    f"{partition['size_bytes']/1024/1024:>8.1f} MB | "
                    f"{partition['row_count']:>10,} rows"
                )
            
            if output_file:
                with open(output_file, 'w') as f:
                    json.dump(health, f, indent=2, default=str)
                print(f"\n✓ Report saved to {output_file}")
    
    async def get_recommendations(self, output_file: Optional[str] = None):
        """Get optimization recommendations"""
        async with self.session_maker() as session:
            manager = PartitioningManager(session)
            recommendations = await manager.get_optimization_recommendations()
            
            print("\n" + "="*80)
            print("PARTITION OPTIMIZATION RECOMMENDATIONS")
            print("="*80)
            print(f"Total Recommendations: {len(recommendations)}\n")
            
            # Group by type
            by_type = {}
            for rec in recommendations:
                if rec.recommendation_type not in by_type:
                    by_type[rec.recommendation_type] = []
                by_type[rec.recommendation_type].append(rec)
            
            for rec_type, recs in by_type.items():
                print(f"\n{rec_type.upper()} ({len(recs)} partitions)")
                print("-" * 80)
                for rec in recs:
                    # Use emoji if terminal supports it, otherwise use text
                    risk_symbols = {"high": "🔴 HIGH", "medium": "🟡 MED ", "low": "� LOW "}
                    risk_display = risk_symbols.get(rec.risk_level, rec.risk_level)
                    
                    print(
                        f"  {risk_display} {rec.partition_name:<25} "
                        f"saves {rec.estimated_space_saved/1024/1024:>6.1f} MB\n"
                        f"      {rec.reason}\n"
                    )
            
            total_space = sum(r.estimated_space_saved for r in recommendations)
            print(f"\nTotal Estimated Space Savings: {total_space/1024/1024/1024:.2f} GB")
            
            if output_file:
                with open(output_file, 'w') as f:
                    data = [
                        {
                            "partition_name": r.partition_name,
                            "type": r.recommendation_type,
                            "reason": r.reason,
                            "space_saved_mb": r.estimated_space_saved / 1024 / 1024,
                            "risk_level": r.risk_level
                        }
                        for r in recommendations
                    ]
                    json.dump(data, f, indent=2)
                print(f"✓ Recommendations saved to {output_file}")
    
    async def get_statistics(self, output_file: Optional[str] = None):
        """Get partition statistics"""
        async with self.session_maker() as session:
            manager = PartitioningManager(session)
            stats = await manager.get_partition_statistics()
            
            print("\n" + "="*80)
            print("PARTITION STATISTICS")
            print("="*80)
            
            total_size = sum(s['total_size_gb'] for s in stats.values())
            total_rows = sum(s['total_rows'] for s in stats.values())
            total_partitions = sum(s['partition_count'] for s in stats.values())
            
            print(f"Total Tables: {len(stats)}")
            print(f"Total Partitions: {total_partitions}")
            print(f"Total Size: {total_size:.2f} GB")
            print(f"Total Rows: {total_rows:,}\n")
            
            print("By Table:")
            print("-" * 80)
            for table_name, table_stats in stats.items():
                print(f"\n{table_name}:")
                print(f"  Partitions: {table_stats['partition_count']}")
                print(f"  Size: {table_stats['total_size_gb']:.2f} GB")
                print(f"  Rows: {table_stats['total_rows']:,}")
                print(f"  Active: {table_stats['active_partitions']} | "
                      f"Readonly: {table_stats['readonly_partitions']} | "
                      f"Archived: {table_stats['archived_partitions']}")
            
            if output_file:
                with open(output_file, 'w') as f:
                    json.dump(stats, f, indent=2)
                print(f"\n✓ Statistics saved to {output_file}")
    
    async def mark_readonly(self, partition_name: str):
        """Mark a partition as readonly"""
        async with self.session_maker() as session:
            manager = PartitioningManager(session)
            success = await manager.mark_partition_readonly(partition_name)
            
            if success:
                print(f"✓ Marked {partition_name} as readonly")
            else:
                print(f"✗ Failed to mark {partition_name} as readonly")
    
    async def archive_partition(self, partition_name: str):
        """Archive a partition"""
        async with self.session_maker() as session:
            manager = PartitioningManager(session)
            success = await manager.archive_partition(partition_name)
            
            if success:
                print(f"✓ Archived {partition_name}")
            else:
                print(f"✗ Failed to archive {partition_name}")
    
    async def run(self, command: str, *args):
        """Execute CLI command"""
        await self.init_db()
        
        try:
            if command == "health":
                await self.analyze_health(args[0] if args else None)
            elif command == "recommendations":
                await self.get_recommendations(args[0] if args else None)
            elif command == "stats":
                await self.get_statistics(args[0] if args else None)
            elif command == "readonly":
                if not args:
                    print("Error: partition name required")
                    return
                await self.mark_readonly(args[0])
            elif command == "archive":
                if not args:
                    print("Error: partition name required")
                    return
                await self.archive_partition(args[0])
            else:
                print(f"Unknown command: {command}")
                self.print_usage()
        finally:
            await self.close_db()
    
    @staticmethod
    def print_usage():
        """Print CLI usage information"""
        print("""
Partition Management CLI

Usage: python manage_partitions.py <command> [options]

Commands:
  health [output_file]              Analyze partition health
  recommendations [output_file]     Get optimization recommendations
  stats [output_file]               Get partition statistics
  readonly <partition_name>         Mark partition as readonly
  archive <partition_name>          Archive a partition
  help                              Show this help message

Examples:
  python manage_partitions.py health
  python manage_partitions.py health health_report.json
  python manage_partitions.py recommendations
  python manage_partitions.py readonly ticket_p_202601
  python manage_partitions.py archive ticket_p_202501
        """)


async def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        PartitionManagementCLI.print_usage()
        return
    
    command = sys.argv[1]
    args = sys.argv[2:] if len(sys.argv) > 2 else []
    
    if command == "help":
        PartitionManagementCLI.print_usage()
        return
    
    cli = PartitionManagementCLI()
    await cli.run(command, *args)


if __name__ == "__main__":
    asyncio.run(main())