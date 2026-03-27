#!/bin/bash
# Dana's personal launcher — overrides distribution defaults with her preferences
# Usage: tmux new-session -d -s apex "cd /Users/dana/.openclaw/apex && bash server/launch_dana.sh"

export APEX_WORKSPACE="/Users/dana/.openclaw/workspace"
export APEX_MODEL="claude-opus-4-6"
export APEX_PERMISSION_MODE="bypassPermissions"
export APEX_DEBUG=1
export APEX_ENABLE_WHISPER=1
export APEX_ALERT_TOKEN="a1zWUJkPtoWXWccbrPAaF37280DWhJrly1ocirDQfwQ"

# Load API keys from .env
if [ -f "$HOME/.openclaw/.env" ]; then
    set -a
    source "$HOME/.openclaw/.env"
    set +a
fi

exec bash server/launch_apex.sh
