# 1. Establish baselines
python scripts/performance_baseline.py
# Output: load_test_results/performance_baselines.json

# 2. Benchmark database queries
python scripts/benchmark_queries.py
# Output: Console output with p95/p99 for each query

# 3. Run automated load test suite
bash scripts/load_test_runner.sh http://localhost:8000
# Output: 3 test runs with CSV results

# 4. Analyze specific test
python scripts/analyze_results.py load_test_results/baseline_<timestamp>_stats.csv
# Output: SLA assessment with recommendations

# 5. Interactive load testing
locust -f scripts/load_test.py --host=http://localhost:8000
# Opens UI at http://localhost:8089

# Query Analysis
python server/scripts/query_analyzer.py health
python server/scripts/query_analyzer.py recommendations
python server/scripts/query_analyzer.py stats

# Partition Management
python server/scripts/manage_partitions.py health
python server/scripts/manage_partitions.py recommendations
python server/scripts/manage_partitions.py readonly <partition>

# Cache Analysis
python server/scripts/cache_analysis.py analyze
python server/scripts/cache_analysis.py warm
python server/scripts/cache_analysis.py simulate 30

# Telemetry Analysis
python server/scripts/telemetry_analyzer.py metrics
python server/scripts/telemetry_analyzer.py alerts
python server/scripts/telemetry_analyzer.py health
python server/scripts/telemetry_analyzer.py report

# Load Testing
python server/scripts/load_test.py smoke
python server/scripts/load_test.py normal
python server/scripts/load_test.py stress