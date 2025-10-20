#!/bin/bash

# Convenience script to regenerate benchmark plots from the latest CSV data

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$PROJECT_DIR/benchmark-results/comparison"
OUTPUT_DIR="$PROJECT_DIR/docs/plots"

# Find the most recent CSV file
LATEST_CSV=$(find "$RESULTS_DIR" -name "comparison_data_*.csv" -type f | sort -r | head -1)

if [ -z "$LATEST_CSV" ]; then
    echo "Error: No benchmark CSV files found in $RESULTS_DIR"
    exit 1
fi

echo "Found benchmark data: $(basename "$LATEST_CSV")"
echo "Generating plots..."

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Generate plots
python3 "$SCRIPT_DIR/generate-plots.py" "$LATEST_CSV" --output-dir "$OUTPUT_DIR"

echo ""
echo "Plots updated successfully in: $OUTPUT_DIR"
echo ""
echo "Generated files:"
ls -lh "$OUTPUT_DIR"/*.png
