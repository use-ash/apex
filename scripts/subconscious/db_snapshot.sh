#!/bin/bash
# db_snapshot.sh — nightly safe backup of live Apex DB for offline mining
#
# Uses sqlite3 .backup (handles WAL safely) to create a point-in-time
# snapshot that chatmine/autodream can read without touching the live DB.
#
# Cron: runs before chatmine (e.g., 22:50 nightly)
# Output: .subconscious/db_snapshots/apex_YYYY-MM-DD.db
# Rotation: keeps 7 days, deletes older snapshots
#
# Usage: db_snapshot.sh [prod|dev]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-prod}"

# ── Resolve paths ────────────────────────────────────────────────────
# Source DB (live — never modified, only read via sqlite3 .backup)
case "$MODE" in
    prod)
        LIVE_DB="$HOME/.openclaw/apex/state/apex.db"
        ;;
    dev)
        LIVE_DB="$HOME/.openclaw/apex/state/apex_dev.db"
        ;;
    *)
        echo "Usage: db_snapshot.sh [prod|dev]"
        exit 1
        ;;
esac

# Snapshot destination
WORKSPACE="${APEX_WORKSPACE:-}"
if [ -z "$WORKSPACE" ]; then
    # Resolve from config.py's logic: read apex config.json
    CONFIG_JSON="$HOME/.openclaw/apex/state/config.json"
    if [ -f "$CONFIG_JSON" ]; then
        WORKSPACE=$(python3 -c "
import json
with open('$CONFIG_JSON') as f:
    c = json.load(f)
print(c.get('workspace',{}).get('path','').split(':')[0])
" 2>/dev/null)
    fi
    WORKSPACE="${WORKSPACE:-$HOME/.openclaw/workspace}"
fi

SNAPSHOT_DIR="$WORKSPACE/.subconscious/db_snapshots"
LOG_FILE="$WORKSPACE/logs/db_snapshot.log"
RETAIN_DAYS=7

mkdir -p "$SNAPSHOT_DIR" "$(dirname "$LOG_FILE")"

# ── Snapshot ─────────────────────────────────────────────────────────
TODAY=$(date +%Y-%m-%d)
SNAPSHOT="$SNAPSHOT_DIR/apex_${MODE}_${TODAY}.db"
LATEST_LINK="$SNAPSHOT_DIR/latest_${MODE}.db"

if [ ! -f "$LIVE_DB" ]; then
    echo "$(date): ERROR — live DB not found: $LIVE_DB" >> "$LOG_FILE"
    exit 1
fi

# sqlite3 .backup is atomic and WAL-safe
echo "$(date): Snapshotting $LIVE_DB → $SNAPSHOT" >> "$LOG_FILE"
sqlite3 "$LIVE_DB" ".backup '$SNAPSHOT'"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "$(date): ERROR — sqlite3 backup failed (exit=$EXIT_CODE)" >> "$LOG_FILE"
    exit $EXIT_CODE
fi

# Compact snapshot: VACUUM merges WAL into main file, removes SHM/WAL artifacts
sqlite3 "$SNAPSHOT" "VACUUM;"
rm -f "${SNAPSHOT}-shm" "${SNAPSHOT}-wal"

SNAP_SIZE=$(stat -f%z "$SNAPSHOT" 2>/dev/null || stat --printf="%s" "$SNAPSHOT" 2>/dev/null)
echo "$(date): Snapshot complete — ${SNAP_SIZE} bytes" >> "$LOG_FILE"

# Symlink latest for easy reference by chatmine
ln -sf "$SNAPSHOT" "$LATEST_LINK"

# ── Rotation ─────────────────────────────────────────────────────────
DELETED=0
find "$SNAPSHOT_DIR" -name "apex_${MODE}_*.db" -mtime +${RETAIN_DAYS} -type f | while read -r old; do
    rm -f "$old"
    DELETED=$((DELETED + 1))
    echo "$(date): Rotated old snapshot: $(basename "$old")" >> "$LOG_FILE"
done

echo "$(date): Done ($MODE). Latest: $LATEST_LINK" >> "$LOG_FILE"
echo "---" >> "$LOG_FILE"
