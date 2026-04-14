#!/bin/bash
# autoDream — cron wrapper with lock file to prevent Ollama contention
# Usage: run_autodream.sh [extra args...]
#
# Cron schedule: 0 3 * * * (3 AM, after chatmine finishes)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="/Users/dana/.openclaw/workspace"
PYTHON="/opt/homebrew/bin/python3"
LOCK_DIR="/tmp/chatmine_locks"
LOG_DIR="$WORKSPACE/logs"

mkdir -p "$LOCK_DIR" "$LOG_DIR"

EXTRA_ARGS="${*:-}"

LOCK_FILE="$LOCK_DIR/autodream.lock"
LOG_FILE="$LOG_DIR/autodream.log"
SCRIPT="$SCRIPT_DIR/autodream.py"
CMD="$PYTHON $SCRIPT $EXTRA_ARGS"
LABEL="autodream"

# ── Lock file guard ──────────────────────────────────────────────────
# Check if any chatmine is running — wait for Ollama to be free
GLOBAL_LOCK="$LOCK_DIR/chatmine_global.lock"

if [ -f "$GLOBAL_LOCK" ]; then
    OTHER_PID=$(cat "$GLOBAL_LOCK" 2>/dev/null)
    if kill -0 "$OTHER_PID" 2>/dev/null; then
        echo "$(date): $LABEL skipped — chatmine is running (PID $OTHER_PID)" >> "$LOG_FILE"
        exit 0
    else
        # Stale lock
        rm -f "$GLOBAL_LOCK"
    fi
fi

if [ -f "$LOCK_FILE" ]; then
    LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null)
    if kill -0 "$LOCK_PID" 2>/dev/null; then
        echo "$(date): $LABEL already running (PID $LOCK_PID), skipping" >> "$LOG_FILE"
        exit 0
    else
        rm -f "$LOCK_FILE"
    fi
fi

# Acquire locks — use global lock to prevent chatmine overlap
echo $$ > "$LOCK_FILE"
echo $$ > "$GLOBAL_LOCK"

cleanup() {
    rm -f "$LOCK_FILE" "$GLOBAL_LOCK"
}
trap cleanup EXIT

# ── Run ──────────────────────────────────────────────────────────────
echo "$(date): $LABEL starting" >> "$LOG_FILE"

OUTPUT=$($CMD 2>&1)
EXIT_CODE=$?

echo "$OUTPUT" >> "$LOG_FILE"
echo "$(date): $LABEL finished (exit=$EXIT_CODE)" >> "$LOG_FILE"
echo "---" >> "$LOG_FILE"

if [ $EXIT_CODE -ne 0 ]; then
    /bin/bash "$WORKSPACE/scripts/send_alert.sh" \
        "$LABEL failed (exit=$EXIT_CODE). Check $LOG_FILE" \
        "autodream" "warning" "autoDream Error"
fi

exit $EXIT_CODE
