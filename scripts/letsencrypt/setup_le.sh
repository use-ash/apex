#!/bin/bash
# Apex Let's Encrypt Setup — Cloudflare DNS-01 challenge
#
# Prerequisites (manual steps):
#   1. Add your domain to Cloudflare (free tier)
#   2. Point nameservers at Namecheap to Cloudflare
#   3. Create A record: apex.<domain> -> your server IP (DNS only, no proxy)
#   4. Create Cloudflare API token: Edit zone DNS, scoped to your domain
#
# Usage:
#   bash scripts/letsencrypt/setup_le.sh
#   bash scripts/letsencrypt/setup_le.sh --domain apex.use-ash.com --email you@example.com

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

# --- Parse arguments ---
DOMAIN=""
EMAIL=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain) DOMAIN="$2"; shift 2 ;;
        --email)  EMAIL="$2"; shift 2 ;;
        *)        echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo ""
echo "  Apex — Let's Encrypt Setup (Cloudflare DNS-01)"
echo "  ================================================"
echo ""

# --- Check certbot ---
if ! command -v certbot &>/dev/null; then
    echo "  certbot not found. Installing..."
    if command -v brew &>/dev/null; then
        brew install certbot
    else
        echo "  Error: Install certbot manually (brew install certbot or pip install certbot)"
        exit 1
    fi
fi

# --- Check Cloudflare plugin ---
if ! python3 -c "import certbot_dns_cloudflare" 2>/dev/null; then
    echo "  Installing certbot-dns-cloudflare..."
    VENV_PIP="$APEX_ROOT/.venv/bin/pip"
    if [ -x "$VENV_PIP" ]; then
        "$VENV_PIP" install -q certbot-dns-cloudflare
    else
        pip3 install -q certbot-dns-cloudflare
    fi
fi

# --- Prompt for domain ---
if [ -z "$DOMAIN" ]; then
    read -rp "  Domain (e.g., apex.use-ash.com): " DOMAIN
fi
if [ -z "$DOMAIN" ]; then
    echo "  Error: domain is required."
    exit 1
fi

# --- Prompt for email ---
if [ -z "$EMAIL" ]; then
    read -rp "  Email for Let's Encrypt notifications: " EMAIL
fi
if [ -z "$EMAIL" ]; then
    echo "  Error: email is required."
    exit 1
fi

# --- Cloudflare API token ---
mkdir -p "$CRED_DIR"

if [ -f "$CF_INI" ]; then
    echo "  Found existing Cloudflare credentials: $CF_INI"
    read -rp "  Overwrite? [y/N]: " OVERWRITE
    if [[ ! "$OVERWRITE" =~ ^[Yy] ]]; then
        echo "  Keeping existing credentials."
    else
        read -rsp "  Cloudflare API token (Edit zone DNS): " CF_TOKEN
        echo ""
        echo "dns_cloudflare_api_token = $CF_TOKEN" > "$CF_INI"
        chmod 600 "$CF_INI"
        echo "  Saved: $CF_INI (0600)"
    fi
else
    read -rsp "  Cloudflare API token (Edit zone DNS): " CF_TOKEN
    echo ""
    if [ -z "$CF_TOKEN" ]; then
        echo "  Error: Cloudflare API token is required."
        exit 1
    fi
    echo "dns_cloudflare_api_token = $CF_TOKEN" > "$CF_INI"
    chmod 600 "$CF_INI"
    echo "  Saved: $CF_INI (0600)"
fi

# --- Request certificate ---
echo ""
echo "  Requesting certificate for $DOMAIN..."
echo "  (This takes ~30-60 seconds for DNS propagation)"
echo ""

mkdir -p "$LE_DIR"

certbot certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials "$CF_INI" \
    --dns-cloudflare-propagation-seconds 30 \
    -d "$DOMAIN" \
    --config-dir "$LE_DIR" \
    --work-dir "$LE_DIR/work" \
    --logs-dir "$LE_DIR/logs" \
    --non-interactive \
    --agree-tos \
    -m "$EMAIL"

# --- Copy certs to state/ssl ---
LE_LIVE="$LE_DIR/live/$DOMAIN"
if [ ! -d "$LE_LIVE" ]; then
    echo "  Error: certbot did not create expected directory: $LE_LIVE"
    exit 1
fi

echo ""
echo "  Copying certificates to $SSL_DIR..."
mkdir -p "$SSL_DIR"
cp -L "$LE_LIVE/fullchain.pem" "$SSL_DIR/le_fullchain.pem"
cp -L "$LE_LIVE/privkey.pem"   "$SSL_DIR/le_privkey.pem"
chmod 644 "$SSL_DIR/le_fullchain.pem"
chmod 600 "$SSL_DIR/le_privkey.pem"

# --- Encrypt the LE private key at rest ---
VENV_PYTHON="$APEX_ROOT/.venv/bin/python3"
PYTHON="${VENV_PYTHON:-python3}"
[ -x "$VENV_PYTHON" ] || PYTHON="python3"

"$PYTHON" -c "
import sys
sys.path.insert(0, '$APEX_ROOT')
try:
    from setup.ssl_keystore import retrieve_passphrase, encrypt_key_file
    from pathlib import Path
    pw = retrieve_passphrase()
    if pw:
        encrypt_key_file(Path('$SSL_DIR/le_privkey.pem'), pw)
        print('  Encrypted LE private key at rest.')
    else:
        print('  Note: no keystore passphrase found; LE key stored unencrypted.')
except ImportError:
    print('  Note: ssl_keystore not available; LE key stored unencrypted.')
" 2>/dev/null || true

# --- Save config ---
"$PYTHON" -c "
import json
from pathlib import Path
config_path = Path('$APEX_ROOT/state/config.json')
config = {}
if config_path.exists():
    try:
        config = json.loads(config_path.read_text())
    except Exception:
        pass
config.setdefault('tls', {})
config['tls']['mode'] = 'letsencrypt'
config['tls']['domain'] = '$DOMAIN'
config['tls']['le_cert'] = '$SSL_DIR/le_fullchain.pem'
config['tls']['le_key'] = '$SSL_DIR/le_privkey.pem'
config_path.write_text(json.dumps(config, indent=2) + '\n')
print('  Updated state/config.json with TLS mode: letsencrypt')
" 2>/dev/null || true

# --- Install LaunchAgent for renewal ---
if [ "$(uname)" = "Darwin" ]; then
    PLIST_SRC="$SCRIPT_DIR/com.apex.certbot-renew.plist"
    PLIST_DST="$HOME/Library/LaunchAgents/com.apex.certbot-renew.plist"
    if [ -f "$PLIST_SRC" ]; then
        # Substitute paths in the plist
        sed \
            -e "s|__APEX_ROOT__|$APEX_ROOT|g" \
            -e "s|__CRED_DIR__|$CRED_DIR|g" \
            -e "s|__HOME__|$HOME|g" \
            "$PLIST_SRC" > "$PLIST_DST"
        launchctl unload "$PLIST_DST" 2>/dev/null || true
        launchctl load "$PLIST_DST"
        echo "  Installed renewal LaunchAgent: $PLIST_DST"
        echo "  Certbot will check for renewal daily at 3:00 AM."
    fi
fi

echo ""
echo "  ================================================"
echo "  Let's Encrypt setup complete!"
echo ""
echo "  Domain:      $DOMAIN"
echo "  Certificate: $SSL_DIR/le_fullchain.pem"
echo "  Private key: $SSL_DIR/le_privkey.pem"
echo "  CA (mTLS):   $SSL_DIR/ca.crt (unchanged)"
echo ""
echo "  Restart the server to use the new certificate."
echo "  Renewal is automatic (checked daily, renews at <30 days)."
echo ""
