#!/bin/bash
# Apex dev launcher — port 8301, apex_dev.db
# Used by ~/restart_apex_dev.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APEX_ROOT="$(dirname "$SCRIPT_DIR")"
SSL_DIR="$APEX_ROOT/state/ssl"

export APEX_PORT=8301
export APEX_HOST=0.0.0.0
export APEX_DB_NAME=apex_dev.db
export APEX_ROOT="$APEX_ROOT"

# Always self-signed for dev
export APEX_SSL_CERT="$SSL_DIR/apex.crt"
export APEX_SSL_KEY="$SSL_DIR/apex.key"
export APEX_SSL_CA="$SSL_DIR/ca.crt"

# Load credentials (source all found .env files — later ones override earlier)
for candidate in "$HOME/.apex/.env" "$HOME/.config/apex/.env" "$HOME/.openclaw/.env"; do
    if [ -f "$candidate" ]; then
        set -a; source "$candidate"; set +a
    fi
done

# Reassert dev runtime after sourcing shared env files so prod defaults cannot override it.
export APEX_PORT=8301
export APEX_HOST=0.0.0.0
export APEX_DB_NAME=apex_dev.db
export APEX_ROOT="$APEX_ROOT"
export APEX_SSL_CERT="$SSL_DIR/apex.crt"
export APEX_SSL_KEY="$SSL_DIR/apex.key"
export APEX_SSL_CA="$SSL_DIR/ca.crt"

# Keep dev-side alert senders scoped to dev even if shared env files target prod.
export APEX_SERVER="https://localhost:${APEX_PORT}"

PYTHON="$APEX_ROOT/.venv/bin/python3"
[ -x "$PYTHON" ] || PYTHON="python3"

echo "Starting Apex dev (port $APEX_PORT, db=$APEX_DB_NAME)..."
exec "$PYTHON" "$SCRIPT_DIR/apex.py"
