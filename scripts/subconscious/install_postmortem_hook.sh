#!/bin/bash
# Adds postmortem hook to Stop and StopFailure events in settings.json
# Run: bash /Users/dana/.openclaw/workspace/scripts/subconscious/install_postmortem_hook.sh

SETTINGS="$HOME/.claude/settings.json"

/opt/homebrew/bin/python3 -c "
import json

with open('$SETTINGS') as f:
    cfg = json.load(f)

postmortem = {
    'type': 'command',
    'command': '/opt/homebrew/bin/python3 /Users/dana/.openclaw/workspace/scripts/subconscious/stop_postmortem.py',
    'timeout': 15000
}

for event in ('Stop', 'StopFailure'):
    matchers = cfg.get('hooks', {}).get(event, [])
    for m in matchers:
        hooks = m.get('hooks', [])
        # Skip if already present
        if any('stop_postmortem' in h.get('command', '') for h in hooks):
            print(f'{event}: already installed, skipping')
            continue
        hooks.append(postmortem.copy())
        m['hooks'] = hooks
        print(f'{event}: postmortem hook added')

with open('$SETTINGS', 'w') as f:
    json.dump(cfg, f, indent=2)
    f.write('\n')

print('Done. Verify with: jq .hooks.Stop,.hooks.StopFailure $SETTINGS')
"
