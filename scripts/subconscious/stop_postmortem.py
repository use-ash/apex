#!/opt/homebrew/bin/python3
"""Stop/StopFailure hook — runs session postmortem analysis.

Reads the hook payload from stdin, analyzes the session transcript,
logs verdict to session_deaths.jsonl, and dual-sends alerts on
abnormal terminations (Telegram + LocalChat).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    try:
        # Load .env for alert credentials
        env_path = os.path.expanduser("~/.openclaw/.env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        os.environ.setdefault(k.strip(), v.strip())

        from postmortem import run_from_hook
        run_from_hook()
    except Exception as e:
        print(f"postmortem hook error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
