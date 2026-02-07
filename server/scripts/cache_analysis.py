# server/scripts/cache_analysis.py
"""
Cache Analysis CLI Tool - Phase 14

Command-line utility for analyzing multi-level cache performance:
- Generate cache efficiency reports
- Analyze hit rates and patterns
- Identify optimization opportunities
- Provide recommendations
"""

import asyncio
import sys
import json
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from core.config import DATABASE_URL
from services.multi_level_cache import (
    MultiLevelCache,
    CacheWarmingService,
    CacheLevel
)


class CacheAnalysisTool:
    """Tool for analyzing cache performance"""
    
    def __init__(self):
        """Initialize analysis tool"""
        self.engine = None
        self.session_maker = None
        self.cache = None
    
    async def init_db(self):
        """Initialize database connection"""
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
    
    async def init_cache(self):
        """Initialize multi-level cache"""
        async with self.session_maker() as session:
            # Initialize cache (Redis would be configured in production)
            self.cache = MultiLevelCache(db=session, redis_client=None)
    
    async def analyze_performance(self, output_file: Optional[str] = None):
        """Analyze cache performance metrics"""
        print("\n" + "="*80)
        print("MULTI-LEVEL CACHE PERFORMANCE ANALYSIS")
        print("="*80)
        print(f"Timestamp: {datetime.now().isoformat()}\n")
        
        metrics = self.cache.get_all_metrics()
        
        # L1 Analysis
        print("📊 L1 CACHE (In-Process LRU)")
        print("-" * 80)
        l1 = metrics["l1"]
        print(f"  Total Size:     {l1['size_bytes'] / 1024 / 1024:>8.2f} MB")
        print(f"  Entries:        {l1['total_entries']:>8}")
        print(f"  Hits:           {l1['hits']:>8}")
        print(f"  Misses:         {l1['misses']:>8}")
        print(f"  Hit Rate:       {l1['hit_rate']:>8.2f}%")
        print(f"  Evictions:      {l1['evictions']:>8}")
        print(f"  Capacity Used:  {l1['capacity_used_percent']:>8.2f}%")
        
        # L2 Analysis
        print("\n📊 L2 CACHE (Redis Distributed)")
        print("-" * 80)
        l2 = metrics["l2"]
        print(f"  Hits:           {l2['hits']:>8}")
        print(f"  Misses:         {l2['misses']:>8}")
        print(f"  Hit Rate:       {l2['hit_rate']:>8.2f}%")
        
        # L3 Analysis
        print("\n📊 L3 CACHE (Database)")
        print("-" * 80)
        l3 = metrics["l3"]
        print(f"  Hits:           {l3['hits']:>8}")
        print(f"  Misses:         {l3['misses']:>8}")
        print(f"  Hit Rate:       {l3['hit_rate']:>8.2f}%")
        
        # Overall Metrics
        total_requests = (
            l1["hits"] + l1["misses"] +
            l2["hits"] + l2["misses"]
        )
        total_hits = l1["hits"] + l2["hits"]
        overall_hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
        
        print("\n📈 OVERALL METRICS")
        print("-" * 80)
        print(f"  Total Requests: {total_requests:>8}")
        print(f"  Total Hits:     {total_hits:>8}")
        print(f"  Overall Hit Rate: {overall_hit_rate:>7.2f}%")
        
        # Bloom filter stats
        bloom = self.cache.l1.bloom
        print("\n🔍 BLOOM FILTER (Negative Caching)")
        print("-" * 80)
        print(f"  Size:           {bloom.size:>8} bits")
        print(f"  Hash Functions: {bloom.hash_count:>8}")
        print(f"  Bits Set:       {len(bloom.bits):>8}")
        print(f"  FP Rate:        {bloom.false_positive_rate():>8.4f}%")
        
        # Recommendations
        print("\n💡 OPTIMIZATIONS & RECOMMENDATIONS")
        print("-" * 80)
        
        if l1["hit_rate"] < 60:
            print(f"  ⚠️  L1 hit rate below 60% ({l1['hit_rate']:.1f}%)")
            print(f"      → Consider increasing L1_TTL or cache warming")
        
        if l1["capacity_used_percent"] < 50:
            print(f"  ✓ L1 cache has headroom ({l1['capacity_used_percent']:.1f}%)")
        elif l1["capacity_used_percent"] > 90:
            print(f"  ⚠️  L1 cache near capacity ({l1['capacity_used_percent']:.1f}%)")
            print(f"      → LRU eviction active, monitor performance")
        
        if overall_hit_rate > 85:
            print(f"  ✓ Excellent overall hit rate ({overall_hit_rate:.1f}%)")
        elif overall_hit_rate > 70:
            print(f"  ⚠️  Good hit rate, could be improved ({overall_hit_rate:.1f}%)")
            print(f"      → Warm cache more aggressively on startup")
        else:
            print(f"  ✗ Low hit rate ({overall_hit_rate:.1f}%)")
            print(f"      → Implement cache warming and increase TTLs")
        
        # Export if requested
        if output_file:
            export_data = {
                "timestamp": datetime.now().isoformat(),
                "l1": l1,
                "l2": l2,
                "l3": l3,
                "overall": {
                    "total_requests": total_requests,
                    "total_hits": total_hits,
                    "hit_rate_percent": overall_hit_rate
                },
                "bloom_filter": {
                    "size": bloom.size,
                    "hash_functions": bloom.hash_count,
                    "bits_set": len(bloom.bits),
                    "false_positive_rate": bloom.false_positive_rate()
                }
            }
            
            with open(output_file, 'w') as f:
                json.dump(export_data, f, indent=2)
            
            print(f"\n✓ Report exported to {output_file}")
    
    async def warm_cache(self):
        """Warm cache with startup data"""
        print("\n" + "="*80)
        print("CACHE WARMING")
        print("="*80)
        
        async with self.session_maker() as session:
            warming = CacheWarmingService(self.cache, session)
            results = await warming.warm_all()
            
            print(f"\nCache warming completed:")
            print(f"  Companies:      {results.get('companies', 0):>4} entries")
            print(f"  Tickets:        {results.get('tickets', 0):>4} entries")
            print(f"  Users:          {results.get('users', 0):>4} entries")
            print(f"  Metadata:       {results.get('metadata', 0):>4} entries")
            
            total = sum(results.values())
            print(f"  Total:          {total:>4} entries")
            print(f"\n  L1 Capacity Used: {self.cache.get_l1_stats()['capacity_used_percent']:.2f}%")
    
    async def simulate_workload(self, duration_seconds: int = 10):
        """Simulate cache workload for testing"""
        print(f"\n" + "="*80)
        print(f"WORKLOAD SIMULATION ({duration_seconds} seconds)")
        print("="*80 + "\n")
        
        import random
        
        test_keys = [f"test:{i}" for i in range(100)]
        test_values = [f"value_{i}" for i in range(100)]
        
        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=duration_seconds)
        
        operations = 0
        
        while datetime.now() < end_time:
            # Random read/write operations
            if random.random() < 0.7:  # 70% reads
                key = random.choice(test_keys)
                value = await self.cache.get(key)
            else:  # 30% writes
                key = random.choice(test_keys)
                value = random.choice(test_values)
                await self.cache.set(key, value, ttl=60)
            
            operations += 1
            
            # Progress indicator
            if operations % 100 == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = operations / elapsed if elapsed > 0 else 0
                print(f"  {operations:>5} ops | {rate:>6.1f} ops/sec")
        
        print(f"\nTotal operations: {operations}")
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"Operations/sec: {operations / elapsed:.1f}")
        
        # Show final stats
        stats = self.cache.get_l1_stats()
        print(f"\nFinal L1 Stats:")
        print(f"  Hit Rate: {stats['hit_rate']:.2f}%")
        print(f"  Entries: {stats['total_entries']}")
        print(f"  Size: {stats['size_bytes'] / 1024 / 1024:.2f} MB")
    
    async def run(self, command: str, *args):
        """Execute command"""
        await self.init_db()
        await self.init_cache()
        
        try:
            if command == "analyze":
                await self.analyze_performance(args[0] if args else None)
            elif command == "warm":
                await self.warm_cache()
            elif command == "simulate":
                duration = int(args[0]) if args else 10
                await self.simulate_workload(duration)
            else:
                print(f"Unknown command: {command}")
                self.print_usage()
        finally:
            await self.close_db()
    
    @staticmethod
    def print_usage():
        """Print usage information"""
        print("""
Cache Analysis Tool - Phase 14

Usage: python cache_analysis.py <command> [options]

Commands:
  analyze [output_file]           Analyze cache performance
  warm                            Warm cache with startup data
  simulate [duration_seconds]     Simulate cache workload
  help                            Show this help message

Examples:
  python cache_analysis.py analyze
  python cache_analysis.py analyze report.json
  python cache_analysis.py warm
  python cache_analysis.py simulate 30
        """)


async def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        CacheAnalysisTool.print_usage()
        return
    
    command = sys.argv[1]
    args = sys.argv[2:] if len(sys.argv) > 2 else []
    
    if command == "help":
        CacheAnalysisTool.print_usage()
        return
    
    tool = CacheAnalysisTool()
    await tool.run(command, *args)


if __name__ == "__main__":
    asyncio.run(main())