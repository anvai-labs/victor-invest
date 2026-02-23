#!/bin/bash
# Quick start script for web UI cache sweep
# This script runs the sweep to populate artifacts/ui_cache/ for the web UI

set -e

echo "=================================="
echo "Web UI Cache Sweep - Quick Start"
echo "=================================="
echo ""

# Default values
PARALLEL=${PARALLEL:-8}
MODE=${MODE:-standard}

# Display configuration
echo "Configuration:"
echo "  Parallel Workers: $PARALLEL"
echo "  Mode: $MODE"
echo "  Output: artifacts/ui_cache/"
echo ""

# Check if user wants to do a dry run first
read -p "Run dry run first to see what will be processed? (y/n): " dry_run

if [ "$dry_run" = "y" ]; then
    echo ""
    python scripts/sweep_ui_cache.py --dry-run --parallel "$PARALLEL" --mode "$MODE"
    echo ""
    read -p "Proceed with actual sweep? (y/n): " proceed
    if [ "$proceed" != "y" ]; then
        echo "Cancelled."
        exit 0
    fi
fi

echo ""
echo "Starting sweep..."
python scripts/sweep_ui_cache.py --parallel "$PARALLEL" --mode "$MODE"

echo ""
echo "=================================="
echo "Sweep Complete!"
echo "=================================="
echo ""
echo "Check cache files:"
echo "  ls -la artifacts/ui_cache/*.json | wc -l"
echo ""
echo "View a symbol:"
echo "  python3 -c \"import json; print(json.load(open('artifacts/ui_cache/AAPL.json'))['payload']['schema_version'])\""
