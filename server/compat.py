"""Cross-platform compatibility helpers for Apex.

Windows does not support Unix file permissions (chmod 0o600). This module
provides safe wrappers so the rest of the codebase can call safe_chmod()
without platform checks everywhere.
"""
from __future__ import annotations

import os
import platform
import stat

IS_WINDOWS = platform.system() == "Windows"


def safe_chmod(path, mode: int) -> None:
    """Set file permissions, skipping gracefully on Windows.

    On Unix: delegates to os.chmod(path, mode) as-is.
    On Windows: ensures the file is read/writable (the intent behind 0o600/0o700)
    since Windows doesn't support Unix permission bits.
    """
    if IS_WINDOWS:
        try:
            os.chmod(str(path), stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass
        return
    os.chmod(str(path), mode)
