#!/bin/bash
# Dev instance launcher — runs on port 8301 with separate DB
# Usage: tmux new-session -d -s apex-dev "cd /Users/dana/.openclaw/apex && bash server/launch_dev.sh"
#
# This is a development/testing instance that runs alongside production.
# Production: port 8300 (launch_dana.sh) — stable, main branch
# Dev:        port 8301 (this script)     — feature work, dev branch

set -euo pipefail

export APEX_WORKSPACE="/Users/dana/.openclaw/workspace"
export APEX_MODEL="claude-opus-4-6"
export APEX_PERMISSION_MODE="bypassPermissions"
export APEX_DEBUG=1
export APEX_ENABLE_WHISPER=1
export APEX_PORT=8301

# Separate dev DB — no risk to production data
export APEX_DB_NAME="apex_dev.db"

# Load API keys from .env
if [ -f "$HOME/.openclaw/.env" ]; then
    set -a
    source "$HOME/.openclaw/.env"
    set +a
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APEX_ROOT="$(dirname "$SCRIPT_DIR")"
SSL_DIR="$APEX_ROOT/state/ssl"

# Reuse production SSL certs (same CA, same client cert)
export APEX_SSL_CERT="$SSL_DIR/apex.crt"
export APEX_SSL_KEY="$SSL_DIR/apex.key"
export APEX_SSL_CA="$SSL_DIR/ca.crt"
export APEX_ROOT="$APEX_ROOT"

echo "=== Apex DEV instance ==="
echo "  Port:  $APEX_PORT"
echo "  DB:    $APEX_ROOT/state/$APEX_DB_NAME"
echo "  Branch: $(git -C "$APEX_ROOT" branch --show-current 2>/dev/null || echo 'unknown')"
echo "========================="

cd "$APEX_ROOT"
exec python3 "$SCRIPT_DIR/apex.py"
