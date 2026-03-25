#!/bin/bash
# Dana's personal launcher — overrides distribution defaults with her preferences
# Usage: tmux new-session -d -s localchat "cd /Users/dana/.openclaw/localchat && bash server/launch_dana.sh"

export LOCALCHAT_WORKSPACE="/Users/dana/.openclaw/workspace"
export LOCALCHAT_MODEL="claude-opus-4-6"
export LOCALCHAT_PERMISSION_MODE="bypassPermissions"
export LOCALCHAT_DEBUG=1

exec bash server/launch_localchat.sh
