#!/usr/bin/env python3
"""V3 Day 4.5 — claims table migration.

Goals:
1. Expand `status` CHECK constraint to permit 'invalid_legacy'.
2. Add `status_comment` column for audit notes on legacy rows.
3. Mark known orphan rows (chat_id='default' from Codex mis-attribution,
   and the Day 2b hollow rows with 62-char sha256 / empty prior_turn) as
   status='invalid_legacy' with a human-readable comment.

SQLite doesn't support DROP/ALTER on CHECK constraints directly, so this
is a copy-and-swap migration. Uses a transaction so either it all lands
or nothing changes. Idempotent: detects new schema and skips if already
migrated.

Target: apex_dev.db (APEX_DB_NAME=apex_dev.db). Does not touch prod apex.db
unless explicitly targeted via env var. Read-only inspection first; prompts
for confirmation before swap.

Usage:
    python3 migrate_claims_v45.py            # dry-run (inspect only)
    python3 migrate_claims_v45.py --apply    # execute migration
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def _db_path() -> Path:
    state_dir = Path(os.environ.get(
        "APEX_STATE_DIR",
        str(Path.home() / ".openclaw/apex/state"),
    ))
    db_name = os.environ.get("APEX_DB_NAME", "apex_dev.db")
    return state_dir / db_name


NEW_CLAIMS_SQL = """
CREATE TABLE claims_new (
    claim_id        TEXT PRIMARY KEY,
    chat_id         TEXT NOT NULL,
    turn_id         INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    revised_at      TEXT,
    text            TEXT NOT NULL,
    confidence      REAL NOT NULL
                    CHECK (confidence >= 0.0 AND confidence <= 1.0),
    source_type     TEXT NOT NULL
                    CHECK (source_type IN (
                        'tool_result', 'prior_turn', 'speculation', 'user'
                    )),
    source_tool     TEXT,
    source_path     TEXT,
    source_byte_lo  INTEGER,
    source_byte_hi  INTEGER,
    source_sha256   TEXT,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'revised', 'retracted', 'invalid_legacy')),
    supersedes      TEXT REFERENCES claims(claim_id),
    superseded_by   TEXT REFERENCES claims(claim_id),
    status_comment  TEXT
)
"""

ORPHAN_COMMENT = (
    "pre-hardening test artifact, retained for audit; "
    "see workspace/v3/experiments/day3_findings.md"
)

# Specific orphan categories and their comments
CODEX_DEFAULT_COMMENT = (
    "Day 3 Codex mis-attribution (chat_id='default'); "
    "root cause: tool_loop.py missing chat_id inject; "
    "fixed by commit fix(v3):...chat_id auto-populate (Day 4). "
    "Retained for audit; not reachable via claim_list."
)

DAY2B_TOOL_RESULT_COMMENT = (
    "Day 2b hollow validation row; sha256 is 62-char mnemonic hallucination, "
    "not a real SHA-256 digest. Passed the server's pre-Day-4.5 truthy-only "
    "guard. chat_id is the Claude SDK session_id, not an Apex chat_id."
)

DAY2B_PRIOR_TURN_COMMENT = (
    "Day 2b hollow validation row; source_type='prior_turn' with no "
    "provenance fields. Passed because pre-Day-4.5 server had no prior_turn "
    "guard. chat_id is the Claude SDK session_id, not an Apex chat_id."
)


def has_new_schema(conn: sqlite3.Connection) -> bool:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(claims)").fetchall()}
    return "status_comment" in cols


def inspect(conn: sqlite3.Connection) -> dict:
    rows_total = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    rows_default = conn.execute(
        "SELECT COUNT(*) FROM claims WHERE chat_id='default'"
    ).fetchone()[0]
    rows_day2b = conn.execute(
        "SELECT COUNT(*) FROM claims WHERE chat_id IN "
        "('ef028a52-f8ba-46f9-b56e-a6b4b141d19e', "
        " 'edb61805-d150-4767-9528-e01c7bc67c58')"
    ).fetchone()[0]
    rows_clean = rows_total - rows_default - rows_day2b
    return {
        "total": rows_total,
        "chat_id_default": rows_default,
        "day2b_hollow": rows_day2b,
        "clean": rows_clean,
    }


def migrate(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("BEGIN")
    try:
        # Ensure FK deferred since we are moving rows within the same tx.
        cur.execute("PRAGMA defer_foreign_keys = ON")

        # Inventory existing indexes so we can recreate them.
        existing_indexes = [
            r[0] for r in cur.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='claims' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]

        cur.execute(NEW_CLAIMS_SQL)

        # Copy all rows, computing new status + comment inline.
        cur.execute(
            """
            INSERT INTO claims_new (
                claim_id, chat_id, turn_id, created_at, revised_at,
                text, confidence, source_type,
                source_tool, source_path, source_byte_lo, source_byte_hi,
                source_sha256, status, supersedes, superseded_by,
                status_comment
            )
            SELECT
                claim_id, chat_id, turn_id, created_at, revised_at,
                text, confidence, source_type,
                source_tool, source_path, source_byte_lo, source_byte_hi,
                source_sha256,
                CASE
                    WHEN chat_id = 'default' THEN 'invalid_legacy'
                    WHEN chat_id IN (
                        'ef028a52-f8ba-46f9-b56e-a6b4b141d19e',
                        'edb61805-d150-4767-9528-e01c7bc67c58'
                    ) THEN 'invalid_legacy'
                    ELSE status
                END AS status,
                supersedes, superseded_by,
                CASE
                    WHEN chat_id = 'default' THEN ?
                    WHEN chat_id = 'ef028a52-f8ba-46f9-b56e-a6b4b141d19e'
                        AND source_type = 'tool_result' THEN ?
                    WHEN chat_id = 'edb61805-d150-4767-9528-e01c7bc67c58'
                        AND source_type = 'prior_turn' THEN ?
                    ELSE NULL
                END AS status_comment
            FROM claims
            """,
            (CODEX_DEFAULT_COMMENT, DAY2B_TOOL_RESULT_COMMENT, DAY2B_PRIOR_TURN_COMMENT),
        )

        cur.execute("DROP TABLE claims")
        cur.execute("ALTER TABLE claims_new RENAME TO claims")

        # Recreate indexes.
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_claims_chat_turn     ON claims(chat_id, turn_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_claims_source_sha256 ON claims(source_sha256)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_claims_supersedes    ON claims(supersedes)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_claims_chat_active   ON claims(chat_id) WHERE status='active'"
        )

        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise


def main() -> int:
    dry = "--apply" not in sys.argv
    path = _db_path()
    if not path.exists():
        print(f"! db not found: {path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        print(f"db:   {path}")
        print(f"mode: {'DRY-RUN' if dry else 'APPLY'}")
        print()
        if has_new_schema(conn):
            print("[skip] status_comment column already present — migration is a no-op.")
            return 0

        inv = inspect(conn)
        print("pre-migration inventory:")
        for k, v in inv.items():
            print(f"  {k:>20} : {v}")
        print()
        print("migration plan:")
        print(f"  {inv['chat_id_default']} rows → status='invalid_legacy'  (Codex chat_id='default' mis-attribution)")
        print(f"  {inv['day2b_hollow']} rows → status='invalid_legacy'  (Day 2b hollow validation artifacts)")
        print(f"  {inv['clean']} rows kept as-is (no known-orphan pattern)")
        print()

        if dry:
            print("(dry-run — pass --apply to execute)")
            return 0

        migrate(conn)
        print("migration applied.")

        # Post-flight check.
        after = conn.execute(
            "SELECT status, COUNT(*) FROM claims GROUP BY status ORDER BY 2 DESC"
        ).fetchall()
        print()
        print("post-migration status distribution:")
        for s, n in after:
            print(f"  {s:>16} : {n}")
        n_comments = conn.execute(
            "SELECT COUNT(*) FROM claims WHERE status_comment IS NOT NULL"
        ).fetchone()[0]
        print(f"  rows with status_comment: {n_comments}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
