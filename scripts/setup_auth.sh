#!/bin/bash
# setup_auth.sh — Set up persistent Anthropic authentication for Apex
#
# Three methods supported:
#   1. API Key (all platforms) — paste key, saved to .env
#   2. Claude Code OAuth (macOS) — extract token from Claude Code session
#   3. Environment variable — just set ANTHROPIC_API_KEY before starting
#
# Usage: bash scripts/setup_auth.sh
set -euo pipefail

# --- Config ---
ENV_DIR="${APEX_ENV_DIR:-$HOME/.apex}"
ENV_FILE="${APEX_ENV_FILE:-$ENV_DIR/.env}"
TOKEN_FILE="${APEX_SHARED_TOKEN_PATH:-$ENV_DIR/.anthropic_token}"
VALIDATE_URL="https://api.anthropic.com/v1/messages"

# --- Helpers ---
validate_token() {
    local token="$1"
    local result
    result=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "x-api-key: $token" \
        -H "anthropic-version: 2023-06-01" \
        -H "content-type: application/json" \
        -d '{"model":"claude-haiku-4-5-20251001","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}' \
        "$VALIDATE_URL" 2>/dev/null || echo "000")
    [ "$result" = "200" ]
}

save_to_env() {
    local key="$1"
    mkdir -p "$(dirname "$ENV_FILE")"
    # Remove existing entry if present
    if [ -f "$ENV_FILE" ]; then
        grep -v "^ANTHROPIC_API_KEY=" "$ENV_FILE" > "${ENV_FILE}.tmp" 2>/dev/null || true
        mv "${ENV_FILE}.tmp" "$ENV_FILE"
    fi
    echo "ANTHROPIC_API_KEY=$key" >> "$ENV_FILE"
    chmod 600 "$ENV_FILE"
}

save_to_token_file() {
    local token="$1"
    mkdir -p "$(dirname "$TOKEN_FILE")"
    printf '%s' "$token" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
}

# --- Detect platform ---
IS_MACOS=false
[ "$(uname)" = "Darwin" ] && IS_MACOS=true

HAS_CLAUDE=false
command -v claude >/dev/null 2>&1 && HAS_CLAUDE=true

# --- UI ---
echo ""
echo "  Apex Authentication Setup"
echo "  ========================="
echo ""
echo "  Choose an authentication method:"
echo ""

if $IS_MACOS && $HAS_CLAUDE; then
    echo "  1) Claude Subscription (recommended)"
    echo "     Use your Max/Pro subscription — no per-token costs"
    echo "     Requires: claude auth login (run first if needed)"
    echo ""
    echo "  2) API Key"
    echo "     Pay-per-token from console.anthropic.com"
    echo "     Saved to: $ENV_FILE"
    echo ""
    echo "  3) Skip — set ANTHROPIC_API_KEY env var yourself"
    echo ""
    read -p "  Choice [1]: " CHOICE
    CHOICE="${CHOICE:-1}"
    # Remap: 1=oauth, 2=apikey, 3=skip
    case "$CHOICE" in
        1) CHOICE=2 ;;  # maps to OAuth case below
        2) CHOICE=1 ;;  # maps to API key case below
        3) CHOICE=3 ;;
    esac
else
    echo "  1) API Key (recommended)"
    echo "     Paste your Anthropic API key (sk-ant-...)"
    echo "     Saved to: $ENV_FILE"
    echo ""
    echo "  2) Skip — set ANTHROPIC_API_KEY env var yourself"
    echo ""
    read -p "  Choice [1]: " CHOICE
    CHOICE="${CHOICE:-1}"
    # Remap: 2=skip
    [ "$CHOICE" = "2" ] && CHOICE=3
fi

case "$CHOICE" in
    1)
        echo ""
        read -sp "  Paste API key (hidden): " API_KEY
        echo ""

        if [ -z "$API_KEY" ]; then
            echo "  No key entered. Exiting."
            exit 1
        fi

        # Basic format check
        if [[ ! "$API_KEY" =~ ^sk-ant- ]]; then
            echo "  Warning: Key doesn't start with 'sk-ant-' — are you sure this is correct?"
            read -p "  Continue anyway? [y/N]: " CONFIRM
            [ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ] || exit 1
        fi

        echo "  Validating..."
        if validate_token "$API_KEY"; then
            echo "  Token is valid."
        else
            echo "  Warning: Token validation failed (may be a network issue)."
            read -p "  Save anyway? [y/N]: " CONFIRM
            [ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ] || exit 1
        fi

        save_to_env "$API_KEY"
        echo "  Saved to $ENV_FILE"
        echo ""
        echo "  Done. Start Apex with: bash server/launch_apex.sh"
        ;;

    2)
        if ! $IS_MACOS; then
            echo "  Claude Code OAuth is only supported on macOS."
            exit 1
        fi
        if ! $HAS_CLAUDE; then
            echo "  Claude Code not found. Install it first: https://claude.ai/download"
            exit 1
        fi

        echo ""
        echo "  Extracting token from Claude Code..."

        # Try setup-token entry first (account=username), then default
        USER=$(whoami)
        RAW=$(security find-generic-password -s "Claude Code-credentials" -a "$USER" -w 2>/dev/null || echo "")
        if [ -z "$RAW" ]; then
            RAW=$(security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null || echo "")
        fi

        if [ -z "$RAW" ]; then
            echo "  No Claude Code credentials found in Keychain."
            echo "  Run 'claude auth login' first, then try again."
            exit 1
        fi

        # Extract access token from JSON blob
        TOKEN=$(python3 -c "
import sys, json
data = '''$RAW'''.strip()
try:
    d = json.loads(data)
    t = d.get('claudeAiOauth',{}).get('accessToken','') or d.get('token','') or data
except json.JSONDecodeError:
    t = data
print(t)
" 2>/dev/null || echo "")

        if [ -z "$TOKEN" ]; then
            echo "  Could not extract token from Keychain data."
            exit 1
        fi

        echo "  Token: ${TOKEN:0:20}... (${#TOKEN} chars)"
        echo "  Validating..."

        if validate_token "$TOKEN"; then
            echo "  Token is valid."
        else
            echo "  Warning: Token validation failed. It may be expired."
            echo "  Run 'claude auth login' to refresh, then try again."
            read -p "  Save anyway? [y/N]: " CONFIRM
            [ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ] || exit 1
        fi

        save_to_token_file "$TOKEN"
        save_to_env "$TOKEN"
        echo ""
        echo "  Saved to:"
        echo "    $TOKEN_FILE (shared token file)"
        echo "    $ENV_FILE (environment)"
        echo ""
        echo "  Apex will auto-refresh via Keychain on future restarts."
        echo "  Done. Start Apex with: bash server/launch_apex.sh"
        ;;

    3)
        echo ""
        echo "  No changes made. Before starting Apex, set:"
        echo ""
        echo "    export ANTHROPIC_API_KEY=sk-ant-..."
        echo ""
        echo "  Or add it to $ENV_FILE:"
        echo "    echo 'ANTHROPIC_API_KEY=sk-ant-...' >> $ENV_FILE"
        ;;

    *)
        echo "  Invalid choice."
        exit 1
        ;;
esac
