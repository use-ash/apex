#!/opt/homebrew/bin/python3
"""Stop hook — queue session for async digest (non-blocking).

Reads the Stop hook payload, checks if enough new content exists since
last digest, and if so spawns batch_digest.py in the background.
Returns immediately (<100ms) to avoid blocking the next turn.

The actual LLM extraction runs asynchronously in a detached process.
"""

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Minimum bytes of new transcript content before triggering a digest
MIN_NEW_BYTES = 20_000  # ~5K tokens, roughly a substantial exchange
# Minimum seconds between digest runs for the same session
DEBOUNCE_SECONDS = 300  # 5 minutes

QUEUE_DIR = Path(__file__).resolve().parent.parent.parent / ".subconscious" / "digest_queue"
BATCH_SCRIPT = Path(__file__).resolve().parent / "batch_digest.py"
PYTHON = "/opt/homebrew/bin/python3"


def main():
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0.2)
        if not ready:
            return
        raw = sys.stdin.read()
        if not raw.strip():
            return
        payload = json.loads(raw)
        session_id = payload.get("session_id", "")
        transcript_path = payload.get("transcript_path", "")

        if not session_id or not transcript_path:
            return

        # Check transcript size — skip tiny sessions
        try:
            size = os.path.getsize(transcript_path)
        except OSError:
            return

        if size < MIN_NEW_BYTES:
            return

        # Debounce: check when we last queued this session
        os.makedirs(QUEUE_DIR, exist_ok=True)
        marker = QUEUE_DIR / f"{session_id[:12]}.queued"
        if marker.exists():
            age = time.time() - marker.stat().st_mtime
            if age < DEBOUNCE_SECONDS:
                return  # Too soon, skip

        # Touch the marker
        marker.write_text(session_id)

        # Check if batch_digest is already running
        lock_file = Path("/tmp/chatmine_locks/batch_digest.lock")
        if lock_file.exists():
            try:
                pid = int(lock_file.read_text().strip())
                if _pid_alive(pid):
                    return  # Already running
            except (ValueError, OSError):
                pass

        # Spawn batch_digest in background (detached, non-blocking)
        log_path = Path(os.path.expanduser("~/.openclaw/workspace/logs/batch_digest.log"))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as log_fd:
            subprocess.Popen(
                [PYTHON, str(BATCH_SCRIPT), "--days", "1"],
                stdout=log_fd,
                stderr=log_fd,
                start_new_session=True,  # Fully detach from parent
            )

    except Exception:
        pass  # Never block the hook on errors


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


if __name__ == "__main__":
    main()
