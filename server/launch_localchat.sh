#!/bin/bash
# Launch LocalChat with mTLS (client certificate auth)
# Usage: cd localchat && bash server/launch_localchat.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCALCHAT_ROOT="$(dirname "$SCRIPT_DIR")"
SSL_DIR="$LOCALCHAT_ROOT/state/ssl"

# Generate client cert if missing
if [ ! -f "$SSL_DIR/client.p12" ]; then
    echo "Generating client certificate..."
    openssl genrsa -out "$SSL_DIR/client.key" 2048 2>/dev/null
    openssl req -new -key "$SSL_DIR/client.key" -subj "/CN=localchat-client" \
      | openssl x509 -req -CA "$SSL_DIR/ca.crt" -CAkey "$SSL_DIR/ca.key" \
        -CAcreateserial -days 825 -sha256 \
        -extfile <(printf "basicConstraints=CA:FALSE\nkeyUsage=digitalSignature\nextendedKeyUsage=clientAuth") \
        -out "$SSL_DIR/client.crt" 2>/dev/null
    openssl pkcs12 -export -out "$SSL_DIR/client.p12" \
      -inkey "$SSL_DIR/client.key" -in "$SSL_DIR/client.crt" \
      -certfile "$SSL_DIR/ca.crt" -passout pass:localchat 2>/dev/null
    echo ""
    echo "  Client cert created: $SSL_DIR/client.p12"
    echo "  AirDrop this file to your phone."
    echo "  Install password: localchat"
    echo ""
fi

kill $(pgrep -f localchat.py) 2>/dev/null
sleep 1

export LOCALCHAT_SSL_CERT="$SSL_DIR/localchat.crt"
export LOCALCHAT_SSL_KEY="$SSL_DIR/localchat.key"
export LOCALCHAT_SSL_CA="$SSL_DIR/ca.crt"

export LOCALCHAT_ROOT="$LOCALCHAT_ROOT"

echo "Starting LocalChat with mTLS..."
python3 "$SCRIPT_DIR/localchat.py"
