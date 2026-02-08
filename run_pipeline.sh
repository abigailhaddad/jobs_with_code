#!/bin/bash
# Full pipeline: scrape -> prepare batch -> submit -> poll -> download -> build web data
# Usage: caffeinate -i bash run_pipeline.sh [--limit N]
# Resumable — detects in-flight batches and skips straight to polling.

set -e
cd "$(dirname "$0")"
source .venv/bin/activate

# Parse --limit flag
LIMIT_ARG=""
LIMIT_VAL=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --limit) LIMIT_VAL="$2"; LIMIT_ARG="--limit $2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Check if there's already an active batch we should resume
SKIP_TO_POLL=false
if [ -f data/batch_state.json ]; then
    OUTPUT=$(python 04_submit_batch.py status 2>&1) || true
    if echo "$OUTPUT" | grep -qE "Status: (validating|in_progress|finalizing)"; then
        echo "=== Active batch detected, resuming poll ==="
        echo "  $OUTPUT" | head -3
        SKIP_TO_POLL=true
    fi
fi

if [ "$SKIP_TO_POLL" = false ]; then
    echo "=== Step 1: Scrape jobs ==="
    SCRAPED_COUNT=$(ls data/scraped_jobs/*.txt 2>/dev/null | wc -l | tr -d ' ')
    if [ -n "$LIMIT_ARG" ] && [ "$SCRAPED_COUNT" -ge "$LIMIT_VAL" ]; then
        echo "Already have $SCRAPED_COUNT scraped (>= $LIMIT_VAL), skipping scrape."
        python 02_scrape_job_pages.py --status
    else
        python 02_scrape_job_pages.py $LIMIT_ARG
    fi
    echo ""

    echo "=== Step 2: Prepare batch input ==="
    python 03_prepare_batch.py $LIMIT_ARG
    echo ""

    # Check if there's anything to submit
    LINE_COUNT=$(wc -l < data/batch_input.jsonl | tr -d ' ')
    if [ "$LINE_COUNT" -eq 0 ]; then
        echo "No new jobs to process, skipping batch."
    else
        echo "=== Step 3: Submit batch ($LINE_COUNT requests) ==="
        python 04_submit_batch.py submit
        echo ""
        SKIP_TO_POLL=true
    fi
fi

if [ "$SKIP_TO_POLL" = true ]; then
    echo "=== Step 4: Polling for completion ==="
    while true; do
        OUTPUT=$(python 04_submit_batch.py status 2>&1)
        echo "  $OUTPUT" | head -3

        if echo "$OUTPUT" | grep -q "Status: completed"; then
            break
        elif echo "$OUTPUT" | grep -qE "Status: (failed|expired|cancelled)"; then
            echo "Batch ended with non-success status."
            exit 1
        fi

        sleep 30
    done
    echo ""

    echo "=== Step 5: Download results ==="
    python 04_submit_batch.py download
    echo ""
fi

echo "=== Step 6: Build web data ==="
python 05_build_web_data.py
echo ""

echo "=== Done! ==="
echo "Open web/index.html or deploy web/ to Netlify."
