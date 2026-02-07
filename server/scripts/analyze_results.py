# server/scripts/analyze_results.py
"""
Analyze load test results and generate reports
Usage: python scripts/analyze_results.py <results_csv_path>
"""
import csv
import sys
import statistics
from pathlib import Path
from datetime import datetime
from collections import defaultdict


class LoadTestAnalyzer:
    """Analyze load test results"""
    
    def __init__(self, csv_file: str):
        self.csv_file = csv_file
        self.data = []
        self.endpoints = defaultdict(list)
        self.load_data()
    
    def load_data(self):
        """Load CSV data from Locust results"""
        print(f"Loading data from: {self.csv_file}")
        
        try:
            with open(self.csv_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.data.append(row)
        except FileNotFoundError:
            print(f"Error: File not found: {self.csv_file}")
            sys.exit(1)
    
    def analyze(self):
        """Analyze the test results"""
        print(f"\n{'='*80}")
        print(f"LOAD TEST ANALYSIS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")
        
        if not self.data:
            print("No data to analyze")
            return
        
        # Parse Locust response times (convert to ms)
        response_times = []
        status_codes = defaultdict(int)
        methods = defaultdict(int)
        names = defaultdict(int)
        
        for row in self.data:
            try:
                # Locust CSV format
                if 'Response Time' in row:
                    rt = float(row['Response Time'])
                    response_times.append(rt / 1000)  # Convert to ms
                
                if 'status_code' in row:
                    status_codes[row['status_code']] += 1
                
                if 'method' in row:
                    methods[row['method']] += 1
                
                if 'name' in row:
                    names[row['name']] += 1
            except (ValueError, KeyError):
                continue
        
        # Calculate statistics
        if response_times:
            stats = {
                "total": len(response_times),
                "min": min(response_times),
                "max": max(response_times),
                "avg": statistics.mean(response_times),
                "median": statistics.median(response_times),
                "stdev": statistics.stdev(response_times) if len(response_times) > 1 else 0,
                "p95": sorted(response_times)[int(len(response_times) * 0.95)],
                "p99": sorted(response_times)[int(len(response_times) * 0.99)]
            }
            
            self._print_summary(stats)
            self._print_status_codes(status_codes)
            self._print_endpoint_stats(names)
            self._print_recommendations(stats)
    
    def _print_summary(self, stats: dict):
        """Print summary statistics"""
        print("\n=== RESPONSE TIME STATISTICS ===")
        print(f"Total Requests: {stats['total']}")
        print(f"Min:    {stats['min']:.2f}ms")
        print(f"Max:    {stats['max']:.2f}ms")
        print(f"Avg:    {stats['avg']:.2f}ms")
        print(f"Median: {stats['median']:.2f}ms")
        print(f"StDev:  {stats['stdev']:.2f}ms")
        print(f"P95:    {stats['p95']:.2f}ms (95% of requests faster than this)")
        print(f"P99:    {stats['p99']:.2f}ms (99% of requests faster than this)")
    
    def _print_status_codes(self, codes: dict):
        """Print status code distribution"""
        print("\n=== STATUS CODES ===")
        for code, count in sorted(codes.items()):
            pct = (count / sum(codes.values())) * 100
            print(f"{code}: {count} ({pct:.1f}%)")
    
    def _print_endpoint_stats(self, names: dict):
        """Print endpoint request counts"""
        print("\n=== ENDPOINTS (Request Count) ===")
        total = sum(names.values())
        for name, count in sorted(names.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total) * 100
            print(f"{name}: {count} ({pct:.1f}%)")
    
    def _print_recommendations(self, stats: dict):
        """Print performance recommendations"""
        print("\n=== PERFORMANCE RECOMMENDATIONS ===")
        
        # P95 latency targets
        if stats['p95'] < 50:
            print("✓ P95 latency < 50ms (EXCELLENT)")
        elif stats['p95'] < 100:
            print("✓ P95 latency < 100ms (GOOD)")
        elif stats['p95'] < 200:
            print("⚠ P95 latency < 200ms (ACCEPTABLE)")
        else:
            print("✗ P95 latency > 200ms (NEEDS OPTIMIZATION)")
        
        # P99 latency targets
        if stats['p99'] < 100:
            print("✓ P99 latency < 100ms (EXCELLENT)")
        elif stats['p99'] < 300:
            print("✓ P99 latency < 300ms (GOOD)")
        elif stats['p99'] < 500:
            print("⚠ P99 latency < 500ms (ACCEPTABLE)")
        else:
            print("✗ P99 latency > 500ms (NEEDS OPTIMIZATION)")
        
        # Standard deviation (consistency)
        if stats['stdev'] < stats['avg'] * 0.5:
            print("✓ Response times stable (low StDev)")
        elif stats['stdev'] < stats['avg']:
            print("⚠ Response times somewhat variable")
        else:
            print("✗ Response times highly variable (investigate outliers)")
    
    def export_summary(self, output_file: str = None):
        """Export analysis summary to file"""
        if output_file is None:
            output_file = Path(self.csv_file).stem + "_analysis.txt"
        
        print(f"\nExporting analysis to: {output_file}")
        # Could implement file export here


def main():
    """Run analysis"""
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze_results.py <results_csv_file>")
        print("Example: python scripts/analyze_results.py load_test_results/baseline_20260206_120000_stats.csv")
        sys.exit(1)
    
    analyzer = LoadTestAnalyzer(sys.argv[1])
    analyzer.analyze()


if __name__ == "__main__":
    main()