"""Cross-platform compatibility helpers for Apex setup.

Identical to server/compat.py — duplicated here so setup/ can import
without depending on server/ being on sys.path.
"""
from __future__ import annotations

import os
import platform
import stat

IS_WINDOWS = platform.system() == "Windows"


def safe_chmod(path, mode: int) -> None:
    """Set file permissions, skipping gracefully on Windows."""
    if IS_WINDOWS:
        try:
            os.chmod(str(path), stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass
        return
    os.chmod(str(path), mode)
