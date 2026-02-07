# server/scripts/performance_baseline.py
"""
Establish performance baselines for critical operations
Usage: python scripts/performance_baseline.py
"""
import time
import json
from datetime import datetime
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.async_database import AsyncSessionLocal, async_engine
from core.database import SessionLocal
from core.logger import get_logger

logger = get_logger(__name__)


PERFORMANCE_TARGETS = {
    "get_ticket": {
        "p95_ms": 50,
        "p99_ms": 100,
        "description": "Fetch single ticket with relationships"
    },
    "list_tickets": {
        "p95_ms": 200,
        "p99_ms": 500,
        "description": "List 20 tickets with pagination"
    },
    "search_tickets": {
        "p95_ms": 500,
        "p99_ms": 1000,
        "description": "Search tickets by query"
    },
    "create_ticket": {
        "p95_ms": 1000,
        "p99_ms": 2000,
        "description": "Create new ticket"
    },
    "get_rca": {
        "p95_ms": 100,
        "p99_ms": 200,
        "description": "Fetch RCA for ticket"
    },
    "update_ticket_status": {
        "p95_ms": 200,
        "p99_ms": 500,
        "description": "Update ticket status"
    },
    "database_connection": {
        "p95_ms": 5,
        "p99_ms": 10,
        "description": "Database connection latency"
    }
}


class PerformanceBaseline:
    """Establish and track performance baselines"""
    
    def __init__(self):
        self.baselines = {}
        self.timestamp = datetime.now()
    
    def test_database_connection(self):
        """Test raw database connection latency"""
        print("\nTesting database connection latency...")
        
        times = []
        for _ in range(10):
            db = SessionLocal()
            start = time.perf_counter()
            try:
                db.execute("SELECT 1")
                elapsed = (time.perf_counter() - start) * 1000
                times.append(elapsed)
            finally:
                db.close()
        
        avg = sum(times) / len(times)
        print(f"  Average: {avg:.2f}ms")
        print(f"  Min: {min(times):.2f}ms, Max: {max(times):.2f}ms")
        
        self.baselines["database_connection"] = {
            "avg_ms": avg,
            "min_ms": min(times),
            "max_ms": max(times)
        }
    
    def generate_report(self):
        """Generate baseline report"""
        print(f"\n{'='*80}")
        print(f"PERFORMANCE BASELINES - {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")
        
        print("PERFORMANCE TARGETS (SLA):")
        print(f"{'Operation':<30} {'P95 Target':<15} {'P99 Target':<15} {'Description':<30}")
        print(f"{'-'*80}")
        
        for op, targets in PERFORMANCE_TARGETS.items():
            print(f"{op:<30} {targets['p95_ms']:<15}ms {targets['p99_ms']:<15}ms {targets['description']:<30}")
        
        print(f"\n{'='*80}\n")
        
        # Test database
        self.test_database_connection()
        
        # Save baselines
        self._save_baselines()
    
    def _save_baselines(self):
        """Save baselines to JSON file"""
        output_file = Path("./load_test_results/performance_baselines.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "timestamp": self.timestamp.isoformat(),
            "targets": PERFORMANCE_TARGETS,
            "baselines": self.baselines
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\nBaselines saved to: {output_file}")


def main():
    """Run baseline generation"""
    baseline = PerformanceBaseline()
    try:
        baseline.generate_report()
    except Exception as e:
        logger.error(f"Error generating baseline: {e}")
        raise


if __name__ == "__main__":
    main()