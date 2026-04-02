#!/bin/bash
# Backup apex.db before server restart — prevents data loss from schema migrations
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APEX_ROOT="$(dirname "$SCRIPT_DIR")"
DB="${APEX_ROOT}/state/${APEX_DB_NAME:-apex.db}"
BACKUP_DIR="${APEX_ROOT}/state/backups"
mkdir -p "$BACKUP_DIR"

if [ -f "$DB" ]; then
    TS=$(date +%Y%m%d_%H%M%S)
    SIZE=$(stat -f%z "$DB" 2>/dev/null || echo 0)
    if [ "$SIZE" -gt 4096 ]; then
        cp "$DB" "$BACKUP_DIR/apex_${TS}.db"
        # Keep last 10 backups
        ls -t "$BACKUP_DIR"/apex_*.db 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null
        echo "[backup] apex.db → backups/apex_${TS}.db (${SIZE} bytes)"
    fi
fi
