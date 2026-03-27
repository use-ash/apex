#!/bin/bash
# Dana's personal launcher — overrides distribution defaults with her preferences
# Usage: tmux new-session -d -s localchat "cd /Users/dana/.openclaw/localchat && bash server/launch_dana.sh"

export LOCALCHAT_WORKSPACE="/Users/dana/.openclaw/workspace"
export LOCALCHAT_MODEL="claude-opus-4-6"
export LOCALCHAT_PERMISSION_MODE="bypassPermissions"
export LOCALCHAT_DEBUG=1
export LOCALCHAT_ENABLE_WHISPER=1
export LOCALCHAT_ALERT_TOKEN="a1zWUJkPtoWXWccbrPAaF37280DWhJrly1ocirDQfwQ"

# Load API keys from .env
if [ -f "$HOME/.openclaw/.env" ]; then
    set -a
    source "$HOME/.openclaw/.env"
    set +a
fi

exec bash server/launch_localchat.sh
