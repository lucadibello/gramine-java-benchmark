#!/bin/bash

# Helper script to calculate overhead percentages
# Usage: ./calc_overhead.sh <baseline_value> <test_value> <metric_type>
# metric_type: "throughput" (lower is worse) or "latency" (higher is worse)

baseline="$1"
test_value="$2"
metric_type="$3"

# Check if values are provided and numeric
if [ -z "$baseline" ] || [ -z "$test_value" ] || [ -z "$metric_type" ]; then
    echo "N/A"
    exit 0
fi

# Check if values are numeric
if ! echo "$baseline" | grep -qE '^[0-9]+(\.[0-9]+)?$' || ! echo "$test_value" | grep -qE '^[0-9]+(\.[0-9]+)?$'; then
    echo "N/A"
    exit 0
fi

# Check for zero baseline
if [ "$baseline" = "0" ] || [ "$baseline" = "0.0" ]; then
    echo "N/A"
    exit 0
fi

# Calculate overhead using shell arithmetic (avoiding bc dependency)
# For throughput: overhead = (baseline - test) / baseline * 100
# For latency/time: overhead = (test - baseline) / baseline * 100

if [ "$metric_type" = "throughput" ]; then
    # Throughput: lower is worse, so we calculate performance loss
    # If SGX throughput is lower, overhead is positive
    overhead=$(awk "BEGIN {printf \"%.2f\", (($baseline - $test_value) / $baseline) * 100}")
else
    # Latency/Time: higher is worse, so we calculate performance degradation
    # If SGX latency is higher, overhead is positive
    overhead=$(awk "BEGIN {printf \"%.2f\", (($test_value - $baseline) / $baseline) * 100}")
fi

echo "$overhead"
