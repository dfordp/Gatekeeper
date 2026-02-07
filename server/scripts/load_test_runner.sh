#!/bin/bash
# Run load tests with different profiles

echo "======================================"
echo "Gatekeeper Load Testing Suite"
echo "======================================"
echo ""

# Configuration
HOST="${1:-http://localhost:8000}"
RESULTS_DIR="./load_test_results"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Create results directory
mkdir -p "$RESULTS_DIR"

echo "Host: $HOST"
echo "Results Directory: $RESULTS_DIR"
echo ""

# Test 1: Baseline test - gradual ramp-up to 200 RPS
echo "Test 1: Baseline (Gradual Ramp-up to 200 RPS)"
echo "Duration: 5 minutes"
locust -f scripts/load_test.py \
  --host=$HOST \
  --users 200 \
  --spawn-rate 10 \
  --run-time 5m \
  --csv=$RESULTS_DIR/baseline_$TIMESTAMP \
  --headless

# Test 2: Sustained load at 200 RPS
echo ""
echo "Test 2: Sustained Load (200 RPS for 10 minutes)"
locust -f scripts/load_test.py \
  --host=$HOST \
  --users 200 \
  --spawn-rate 200 \
  --run-time 10m \
  --csv=$RESULTS_DIR/sustained_$TIMESTAMP \
  --headless

# Test 3: Spike test - sudden jump to 300 RPS
echo ""
echo "Test 3: Spike Test (Ramp to 300 RPS)"
locust -f scripts/load_test.py \
  --host=$HOST \
  --users 300 \
  --spawn-rate 100 \
  --run-time 3m \
  --csv=$RESULTS_DIR/spike_$TIMESTAMP \
  --headless

echo ""
echo "======================================"
echo "Load tests complete!"
echo "Results saved to: $RESULTS_DIR"
echo "======================================"