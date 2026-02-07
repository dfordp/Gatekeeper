# server/scripts/benchmark_queries.py
"""
Benchmark database queries to identify performance issues
Usage: python scripts/benchmark_queries.py
"""
import time
import statistics
from datetime import datetime
from uuid import UUID
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import SessionLocal, Ticket, Company, User, IncidentReport
from services.query_optimizer import QueryOptimizer
from services.database_helpers import TicketQueries, CompanyQueries, UserQueries
from core.logger import get_logger

logger = get_logger(__name__)


class QueryBenchmark:
    """Benchmark database queries"""
    
    def __init__(self, num_iterations: int = 100):
        self.num_iterations = num_iterations
        self.db = SessionLocal()
        self.results = {}
    
    def measure(self, name: str, query_func, *args, **kwargs):
        """
        Measure execution time of a query function.
        
        Args:
            name: Query name for reporting
            query_func: Callable that executes the query
            *args, **kwargs: Arguments to pass to query_func
        """
        print(f"\nBenchmarking: {name}")
        print(f"Iterations: {self.num_iterations}")
        
        times = []
        errors = 0
        
        for i in range(self.num_iterations):
            try:
                start = time.perf_counter()
                result = query_func(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                times.append(elapsed_ms)
                
                if (i + 1) % max(1, self.num_iterations // 10) == 0:
                    print(f"  Progress: {i + 1}/{self.num_iterations}")
            
            except Exception as e:
                logger.error(f"Error in iteration {i}: {e}")
                errors += 1
        
        if times:
            stats = {
                "min": min(times),
                "max": max(times),
                "avg": statistics.mean(times),
                "median": statistics.median(times),
                "stdev": statistics.stdev(times) if len(times) > 1 else 0,
                "p95": sorted(times)[int(len(times) * 0.95)],
                "p99": sorted(times)[int(len(times) * 0.99)],
                "errors": errors
            }
            
            self.results[name] = stats
            self._print_results(name, stats)
            return stats
        
        return None
    
    def _print_results(self, name: str, stats: dict):
        """Print benchmark results in formatted table"""
        print(f"\n  Results for {name}:")
        print(f"    Min:    {stats['min']:.2f}ms")
        print(f"    Max:    {stats['max']:.2f}ms")
        print(f"    Avg:    {stats['avg']:.2f}ms")
        print(f"    Median: {stats['median']:.2f}ms")
        print(f"    StDev:  {stats['stdev']:.2f}ms")
        print(f"    P95:    {stats['p95']:.2f}ms")
        print(f"    P99:    {stats['p99']:.2f}ms")
        print(f"    Errors: {stats['errors']}")
    
    def run_all_benchmarks(self):
        """Run all benchmark tests"""
        print(f"\n{'='*70}")
        print(f"Database Query Benchmarking - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        
        # Get sample IDs
        try:
            company = self.db.query(Company).first()
            company_id = company.id if company else UUID("550e8400-e29b-41d4-a716-446655440000")
            
            ticket = self.db.query(Ticket).filter(Ticket.company_id == company_id).first()
            ticket_id = ticket.id if ticket else None
            
            user = self.db.query(User).filter(User.company_id == company_id).first()
            user_id = user.id if user else None
        except Exception as e:
            logger.error(f"Error getting sample data: {e}")
            return
        
        # Benchmark Ticket queries
        print(f"\n\n--- TICKET QUERIES ---")
        
        if ticket_id:
            self.measure(
                "Get Ticket with Relations",
                TicketQueries.get_ticket_with_relations,
                self.db,
                ticket_id
            )
        
        self.measure(
            "Get Company Tickets (all)",
            TicketQueries.get_company_tickets,
            self.db,
            company_id,
            None,
            limit=20,
            offset=0
        )
        
        self.measure(
            "Count Company Tickets",
            TicketQueries.count_company_tickets,
            self.db,
            company_id
        )
        
        # Benchmark Company queries
        print(f"\n\n--- COMPANY QUERIES ---")
        
        self.measure(
            "Get Company with Users",
            CompanyQueries.get_company_with_users,
            self.db,
            company_id
        )
        
        # Benchmark User queries
        print(f"\n\n--- USER QUERIES ---")
        
        self.measure(
            "Get Users by Company",
            UserQueries.get_users_by_company,
            self.db,
            company_id
        )
        
        # Direct query benchmarks
        print(f"\n\n--- DIRECT QUERIES ---")
        
        self.measure(
            "Query: All Tickets (no eager load)",
            lambda: self.db.query(Ticket).filter(
                Ticket.company_id == company_id
            ).limit(20).all()
        )
        
        self.measure(
            "Query: Ticket by ID",
            lambda: self.db.query(Ticket).filter(Ticket.id == ticket_id).first() if ticket_id else None
        )
        
        # Print summary
        self._print_summary()
    
    def _print_summary(self):
        """Print summary table of all benchmarks"""
        print(f"\n\n{'='*70}")
        print(f"BENCHMARK SUMMARY")
        print(f"{'='*70}")
        print(f"{'Query Name':<40} {'Avg (ms)':<12} {'P95 (ms)':<12} {'Errors':<8}")
        print(f"{'-'*70}")
        
        for name, stats in sorted(self.results.items()):
            print(f"{name:<40} {stats['avg']:<12.2f} {stats['p95']:<12.2f} {stats['errors']:<8}")
        
        print(f"{'='*70}\n")
    
    def close(self):
        """Close database connection"""
        self.db.close()


def main():
    """Run benchmarks"""
    benchmark = QueryBenchmark(num_iterations=100)
    try:
        benchmark.run_all_benchmarks()
    finally:
        benchmark.close()


if __name__ == "__main__":
    main()