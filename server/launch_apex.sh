#!/bin/bash
# Launch Apex with mTLS (client certificate auth)
# Usage: cd apex && bash server/launch_apex.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APEX_ROOT="$(dirname "$SCRIPT_DIR")"
SSL_DIR="$APEX_ROOT/state/ssl"

# Client cert generation removed — use setup.py or dashboard UI instead.
# The CA key is now encrypted at rest; inline openssl cannot read it.

# Prefer Let's Encrypt certs if available, fall back to self-signed
LE_CERT="$SSL_DIR/le_fullchain.pem"
LE_KEY="$SSL_DIR/le_privkey.pem"
if [ -f "$LE_CERT" ] && [ -f "$LE_KEY" ]; then
    export APEX_SSL_CERT="$LE_CERT"
    export APEX_SSL_KEY="$LE_KEY"
else
    export APEX_SSL_CERT="$SSL_DIR/apex.crt"
    export APEX_SSL_KEY="$SSL_DIR/apex.key"
fi
# CA always self-signed (for mTLS client cert verification)
export APEX_SSL_CA="$SSL_DIR/ca.crt"

export APEX_ROOT="$APEX_ROOT"

# Source credentials (all found .env files — later ones override earlier)
# APEX_ENV_FILE overrides automatic discovery
if [ -n "${APEX_ENV_FILE:-}" ] && [ -f "$APEX_ENV_FILE" ]; then
    set -a; source "$APEX_ENV_FILE"; set +a
else
    for candidate in "$HOME/.apex/.env" "$HOME/.config/apex/.env" "$HOME/.openclaw/.env"; do
        if [ -f "$candidate" ]; then
            set -a; source "$candidate"; set +a
        fi
    done
fi

# Reassert prod runtime after sourcing shared env files so local defaults
# cannot override the external prod listener or DB selection.
export APEX_PORT="8300"
export APEX_HOST="0.0.0.0"
export APEX_DB_NAME="apex.db"
export APEX_ROOT="$APEX_ROOT"
if [ -f "$LE_CERT" ] && [ -f "$LE_KEY" ]; then
    export APEX_SSL_CERT="$LE_CERT"
    export APEX_SSL_KEY="$LE_KEY"
else
    export APEX_SSL_CERT="$SSL_DIR/apex.crt"
    export APEX_SSL_KEY="$SSL_DIR/apex.key"
fi
export APEX_SSL_CA="$SSL_DIR/ca.crt"

# First-run detection — run setup wizard if no CA cert exists
if [ ! -f "$SSL_DIR/ca.crt" ]; then
    echo ""
    echo "  First run detected. Starting setup wizard..."
    echo ""
    python3 "$(dirname "$APEX_ROOT")/setup.py" || {
        echo "Setup failed. You can also run: python3 setup.py"
        exit 1
    }
fi

# Use venv Python if available (created by setup.py)
PYTHON="$APEX_ROOT/.venv/bin/python3"
if [ ! -x "$PYTHON" ]; then
    PYTHON="python3"
fi

if [ -n "${APEX_PIDFILE:-}" ]; then
    mkdir -p "$(dirname "$APEX_PIDFILE")"
    echo "$$" > "$APEX_PIDFILE"
fi

echo "Starting Apex with mTLS..."
exec "$PYTHON" "$SCRIPT_DIR/apex.py"
