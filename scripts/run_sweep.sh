#!/bin/bash
# Example script to run compact cache sweep
# Usage: ./scripts/run_sweep.sh [options]

set -e

# Default values
PARALLEL=4
LIMIT=1000
OUTPUT_DIR="/tmp/sweep_compact"
MODE="standard"
DRY_RUN=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --parallel)
            PARALLEL="$2"
            shift 2
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --mode)
            MODE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --all)
            LIMIT=""
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Display configuration
echo "=================================="
echo "Compact Cache Sweep Configuration"
echo "=================================="
echo "Parallel Workers: $PARALLEL"
echo "Limit: ${LIMIT:-all (3,719 total)}"
echo "Output Directory: $OUTPUT_DIR"
echo "Mode: $MODE"
echo "Dry Run: ${DRY_RUN:-false}"
echo "=================================="
echo ""

# Run the sweep
cd "$(dirname "$0")/.."

python scripts/sweep_compact_cache.py \
    --parallel "$PARALLEL" \
    ${LIMIT:+--limit "$LIMIT"} \
    --output-dir "$OUTPUT_DIR" \
    --mode "$MODE" \
    $DRY_RUN

# Show results
if [ -z "$DRY_RUN" ]; then
    echo ""
    echo "=================================="
    echo "Sweep Results"
    echo "=================================="
    echo "Output Directory: $OUTPUT_DIR"

    # Count processed files
    if [ -d "$OUTPUT_DIR" ]; then
        PROCESSED=$(find "$OUTPUT_DIR" -name "*.json" ! -name "batch_summary_*" ! -name "sweep_summary_*" ! -name "sweep_log_*" | wc -l)
        echo "Symbols Processed: $PROCESSED"

        # Show total size
        TOTAL_SIZE=$(du -sh "$OUTPUT_DIR" | cut -f1)
        echo "Total Size: $TOTAL_SIZE"

        # Show last 5 files
        echo ""
        echo "Last 5 Files:"
        ls -lt "$OUTPUT_DIR"/*.json 2>/dev/null | grep -v "batch_summary\|sweep_summary\|sweep_log" | head -5 | awk '{print "  " $9 " (" $5 ")"}'
    fi

    echo "=================================="
fi
