#!/bin/bash
# chatMine — cron wrapper with lock file to prevent Ollama contention
# Usage: run_chatmine.sh [prod|dev|claude] [extra args...]
#
# Cron schedule (staggered to avoid Ollama collision):
#   0 1,5,9,13,17,21  * * * /bin/bash .../run_chatmine.sh prod
#   0 3,7,11,15,19,23  * * * /bin/bash .../run_chatmine.sh dev
#   30 0,6,12,18       * * * /bin/bash .../run_chatmine.sh claude
#   30 2,8,14,20       * * * /bin/bash .../run_chatmine.sh codex

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="/Users/dana/.openclaw/workspace"
PYTHON="/opt/homebrew/bin/python3"
LOCK_DIR="/tmp/chatmine_locks"
LOG_DIR="$WORKSPACE/logs"

mkdir -p "$LOCK_DIR" "$LOG_DIR"

MODE="${1:-prod}"
shift 2>/dev/null || true
EXTRA_ARGS="$*"

# ── DB snapshot resolution ──────────────────────────────────────────
# Only mine from snapshots — never touch the live DB
SNAPSHOT_DIR="$WORKSPACE/.subconscious/db_snapshots"

case "$MODE" in
    prod)
        LOCK_FILE="$LOCK_DIR/chatmine_prod.lock"
        LOG_FILE="$LOG_DIR/chatmine.log"
        SCRIPT="$SCRIPT_DIR/chatmine.py"
        if [ -f "$SNAPSHOT_DIR/latest_prod.db" ]; then
            export APEX_DB="$SNAPSHOT_DIR/latest_prod.db"
        else
            echo "$(date): chatmine-prod skipped — no snapshot available" >> "$LOG_FILE"
            exit 0
        fi
        CMD="$PYTHON $SCRIPT --all --model gemma4:26b $EXTRA_ARGS"
        LABEL="chatmine-prod"
        ;;
    dev)
        LOCK_FILE="$LOCK_DIR/chatmine_dev.lock"
        LOG_FILE="$LOG_DIR/chatmine_dev.log"
        SCRIPT="$SCRIPT_DIR/chatmine.py"
        if [ -f "$SNAPSHOT_DIR/latest_dev.db" ]; then
            export APEX_DB="$SNAPSHOT_DIR/latest_dev.db"
        else
            echo "$(date): chatmine-dev skipped — no snapshot available" >> "$LOG_FILE"
            exit 0
        fi
        CMD="$PYTHON $SCRIPT --all --model gemma4:26b $EXTRA_ARGS"
        LABEL="chatmine-dev"
        ;;
    claude)
        LOCK_FILE="$LOCK_DIR/chatmine_claude.lock"
        LOG_FILE="$LOG_DIR/chatmine_claude.log"
        SCRIPT="$SCRIPT_DIR/chatmine_claude.py"
        CMD="$PYTHON $SCRIPT --all --model gemma4:26b $EXTRA_ARGS"
        LABEL="chatmine-claude"
        ;;
    codex)
        LOCK_FILE="$LOCK_DIR/chatmine_codex.lock"
        LOG_FILE="$LOG_DIR/chatmine_codex.log"
        SCRIPT="$SCRIPT_DIR/chatmine_codex.py"
        CMD="$PYTHON $SCRIPT --all --model gemma4:26b $EXTRA_ARGS"
        LABEL="chatmine-codex"
        ;;
    *)
        echo "Usage: run_chatmine.sh [prod|dev|claude|codex] [extra args...]"
        exit 1
        ;;
esac

# ── Lock file guard ──────────────────────────────────────────────────
# Also check if ANY chatmine lock exists — only one Ollama job at a time
GLOBAL_LOCK="$LOCK_DIR/chatmine_global.lock"

if [ -f "$GLOBAL_LOCK" ]; then
    OTHER_PID=$(cat "$GLOBAL_LOCK" 2>/dev/null)
    if kill -0 "$OTHER_PID" 2>/dev/null; then
        echo "$(date): $LABEL skipped — another chatmine is running (PID $OTHER_PID)" >> "$LOG_FILE"
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

# Acquire locks
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
        "chatmine" "warning" "chatMine Error"
fi

exit $EXIT_CODE
