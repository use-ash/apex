"""Apex logging — rotating file + stderr."""
from __future__ import annotations

import os
import sys
import threading
from datetime import datetime

from env import APEX_ROOT, LOG_NAME

LOG_PATH = APEX_ROOT / "state" / LOG_NAME
LOG_MAX = 5 * 1024 * 1024  # 5MB

_log_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(f"[apex {datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)
    with _log_lock:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(LOG_PATH.parent, 0o700)
            if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX:
                rotated = LOG_PATH.with_suffix(".log.1")
                if rotated.exists():
                    rotated.unlink()
                LOG_PATH.replace(rotated)
            with LOG_PATH.open("a") as f:
                f.write(line + "\n")
        except Exception:
            pass
