#!/bin/bash
# Apex Let's Encrypt Renewal — called by LaunchAgent or cron
#
# Certbot only actually renews when the cert has <30 days remaining.
# Safe to run daily.
#
# Usage:
#   bash scripts/letsencrypt/renew_le.sh
#   bash scripts/letsencrypt/renew_le.sh --dry-run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APEX_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SSL_DIR="$APEX_ROOT/state/ssl"

# Credential directory
if [ "$(uname)" = "Darwin" ]; then
    CRED_DIR="${APEX_ENV_DIR:-$HOME/.apex}"
else
    CRED_DIR="$HOME/.config/apex"
fi

LE_DIR="$CRED_DIR/letsencrypt"
CF_INI="$CRED_DIR/cloudflare.ini"
LOG="$APEX_ROOT/state/le_renew.log"

DRY_RUN=""
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN="--dry-run"
fi

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG"
}

# --- Preflight ---
if [ ! -f "$CF_INI" ]; then
    log "ERROR: Cloudflare credentials not found: $CF_INI"
    log "Run setup_le.sh first."
    exit 1
fi

if ! command -v certbot &>/dev/null; then
    log "ERROR: certbot not found"
    exit 1
fi

# --- Renew ---
log "Starting certbot renewal check..."

certbot renew \
    --dns-cloudflare \
    --dns-cloudflare-credentials "$CF_INI" \
    --config-dir "$LE_DIR" \
    --work-dir "$LE_DIR/work" \
    --logs-dir "$LE_DIR/logs" \
    --non-interactive \
    $DRY_RUN \
    2>&1 | tee -a "$LOG"

RENEW_EXIT=${PIPESTATUS[0]}

if [ "$RENEW_EXIT" -ne 0 ]; then
    log "ERROR: certbot renew failed (exit $RENEW_EXIT)"
    exit "$RENEW_EXIT"
fi

if [ -n "$DRY_RUN" ]; then
    log "Dry run complete — no certs were changed."
    exit 0
fi

# --- Check if certs were actually renewed ---
# certbot renew outputs "No renewals were attempted" if nothing to do
if grep -q "No renewals were attempted" "$LOG" 2>/dev/null; then
    log "No renewal needed — cert still valid."
    exit 0
fi

# --- Copy renewed certs ---
# Find the domain from config
VENV_PYTHON="$APEX_ROOT/.venv/bin/python3"
PYTHON="${VENV_PYTHON:-python3}"
[ -x "$VENV_PYTHON" ] || PYTHON="python3"

DOMAIN=$("$PYTHON" -c "
import json
from pathlib import Path
config = json.loads(Path('$APEX_ROOT/state/config.json').read_text())
print(config.get('tls', {}).get('domain', ''))
" 2>/dev/null || echo "")

if [ -z "$DOMAIN" ]; then
    # Fall back to first live cert directory
    DOMAIN=$(ls "$LE_DIR/live/" 2>/dev/null | head -1)
fi

if [ -z "$DOMAIN" ]; then
    log "ERROR: Could not determine domain for cert copy."
    exit 1
fi

LE_LIVE="$LE_DIR/live/$DOMAIN"
if [ ! -d "$LE_LIVE" ]; then
    log "ERROR: Live cert directory not found: $LE_LIVE"
    exit 1
fi

log "Copying renewed certs for $DOMAIN..."
cp -L "$LE_LIVE/fullchain.pem" "$SSL_DIR/le_fullchain.pem"
cp -L "$LE_LIVE/privkey.pem"   "$SSL_DIR/le_privkey.pem"
chmod 644 "$SSL_DIR/le_fullchain.pem"
chmod 600 "$SSL_DIR/le_privkey.pem"

# --- Encrypt the renewed key ---
"$PYTHON" -c "
import sys
sys.path.insert(0, '$APEX_ROOT')
try:
    from setup.ssl_keystore import retrieve_passphrase, encrypt_key_file
    from pathlib import Path
    pw = retrieve_passphrase()
    if pw:
        encrypt_key_file(Path('$SSL_DIR/le_privkey.pem'), pw)
except Exception:
    pass
" 2>/dev/null || true

log "Certs copied. Restarting server..."

# --- Restart server ---
# Signal the running server to restart
APEX_PID=$(pgrep -f "apex.py" 2>/dev/null | head -1 || echo "")
if [ -n "$APEX_PID" ]; then
    kill -HUP "$APEX_PID" 2>/dev/null || true
    log "Sent HUP to server (PID $APEX_PID). It will pick up new certs on next restart."
    # If the server doesn't handle HUP, fall back to full restart
    sleep 2
    if kill -0 "$APEX_PID" 2>/dev/null; then
        log "Server still running — a manual restart may be needed to load new certs."
    fi
else
    log "Server not running — new certs will be used on next start."
fi

log "Renewal complete."
