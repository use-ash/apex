"""
pytest configuration and test isolation.

CRITICAL SAFETY GUARANTEE
--------------------------
This file is loaded by pytest BEFORE any test module is imported.
It hard-sets APEX_ROOT and APEX_DB_NAME to a temporary directory so
that no test ever opens, reads, or writes the real apex.db.

Rules:
  - All assignments here use os.environ["KEY"] = value (NOT setdefault).
    setdefault allows a pre-existing shell env var to leak in, which is
    exactly how the real database was wiped in the April 2026 incident.
  - The session fixture _guard_real_db aborts immediately if db.DB_PATH
    ever resolves to the real database path. This is the last line of
    defense against mis-configuration.

Never remove these assignments. Never weaken them to setdefault.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Establish hermetic environment BEFORE any server module is imported
# ---------------------------------------------------------------------------

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="apex-test-"))

# Hard-set — always wins, regardless of shell environment.
os.environ["APEX_ROOT"] = str(_TEST_ROOT)
os.environ["APEX_WORKSPACE"] = str(_TEST_ROOT)
os.environ["APEX_DB_NAME"] = "test_apex.db"
os.environ["APEX_LOG_NAME"] = "test_apex.log"
os.environ["APEX_ALERT_TOKEN"] = "test-alert-token"
os.environ["APEX_ADMIN_TOKEN"] = "test-admin-token"
os.environ["APEX_SSL_CERT"] = ""
os.environ["APEX_SSL_KEY"] = ""
os.environ["APEX_SSL_CA"] = ""

# Add server/ to sys.path so test modules can import server packages.
_SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

# ---------------------------------------------------------------------------
# Real-database guard — fail fast, fail loud
# ---------------------------------------------------------------------------

# Known real database paths that must never be touched by tests.
_REAL_DB_PATHS = {
    Path.home() / ".openclaw" / "apex" / "state" / "apex.db",
    Path.home() / ".apex-prod" / "state" / "apex.db",
}


@pytest.fixture(autouse=True, scope="session")
def _guard_real_db() -> None:
    """Abort the entire test session if db.DB_PATH points at the real database.

    This fixture runs once before any test and checks that db.DB_PATH is
    pointing at a temp/test path.  If it isn't, something has gone wrong with
    environment isolation and we stop immediately rather than risk data loss.
    """
    try:
        import db as db_mod  # noqa: PLC0415 — intentional late import
    except ImportError:
        return  # db not loaded yet; nothing to check

    db_path = Path(str(db_mod.DB_PATH)).resolve()
    for real in _REAL_DB_PATHS:
        try:
            real_resolved = real.resolve()
        except OSError:
            continue
        if db_path == real_resolved:
            pytest.fail(
                f"\n\nABORT: db.DB_PATH is pointing at the REAL database!\n"
                f"  db.DB_PATH = {db_mod.DB_PATH}\n"
                f"  Matches real DB: {real}\n\n"
                f"Tests must NEVER touch the live apex.db.  "
                f"Check that APEX_ROOT and APEX_DB_NAME are set correctly "
                f"before any server module is imported.\n",
                pytrace=False,
            )
