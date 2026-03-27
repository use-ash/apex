#!/bin/bash
# Launch Apex with mTLS (client certificate auth)
# Usage: cd apex && bash server/launch_apex.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APEX_ROOT="$(dirname "$SCRIPT_DIR")"
SSL_DIR="$APEX_ROOT/state/ssl"

# Generate client cert if missing
if [ ! -f "$SSL_DIR/client.p12" ]; then
    echo "Generating client certificate..."
    openssl genrsa -out "$SSL_DIR/client.key" 2048 2>/dev/null
    openssl req -new -key "$SSL_DIR/client.key" -subj "/CN=apex-client" \
      | openssl x509 -req -CA "$SSL_DIR/ca.crt" -CAkey "$SSL_DIR/ca.key" \
        -CAcreateserial -days 825 -sha256 \
        -extfile <(printf "basicConstraints=CA:FALSE\nkeyUsage=digitalSignature\nextendedKeyUsage=clientAuth") \
        -out "$SSL_DIR/client.crt" 2>/dev/null
    openssl pkcs12 -export -out "$SSL_DIR/client.p12" \
      -inkey "$SSL_DIR/client.key" -in "$SSL_DIR/client.crt" \
      -certfile "$SSL_DIR/ca.crt" -passout pass:apex 2>/dev/null
    echo ""
    echo "  Client cert created: $SSL_DIR/client.p12"
    echo "  AirDrop this file to your phone."
    echo "  Install password: apex"
    echo ""
fi

kill $(pgrep -f apex.py) 2>/dev/null
sleep 1

export APEX_SSL_CERT="$SSL_DIR/apex.crt"
export APEX_SSL_KEY="$SSL_DIR/apex.key"
export APEX_SSL_CA="$SSL_DIR/ca.crt"

export APEX_ROOT="$APEX_ROOT"

# Source credentials (.env has XAI_API_KEY, APEX_ALERT_TOKEN, etc.)
if [ -f "$HOME/.openclaw/.env" ]; then
    set -a
    source "$HOME/.openclaw/.env"
    set +a
fi

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

echo "Starting Apex with mTLS..."
python3 "$SCRIPT_DIR/apex.py"
