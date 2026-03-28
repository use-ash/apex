#!/bin/bash
# Dana's personal launcher — overrides distribution defaults with her preferences
# Usage: tmux new-session -d -s apex "cd /Users/dana/.openclaw/apex && bash server/launch_dana.sh"

export APEX_WORKSPACE="/Users/dana/.openclaw/workspace"
export APEX_MODEL="claude-opus-4-6"
export APEX_PERMISSION_MODE="bypassPermissions"
export APEX_DEBUG=1
export APEX_ENABLE_WHISPER=1
# APEX_ALERT_TOKEN — set in ~/.apex/.env or export before running

# Load API keys from .env
if [ -f "$HOME/.openclaw/.env" ]; then
    set -a
    source "$HOME/.openclaw/.env"
    set +a
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Backup DB before launch (prevents data loss from schema migrations)
bash "$SCRIPT_DIR/backup_db.sh"

cd "$SCRIPT_DIR/.."
exec bash server/launch_apex.sh
