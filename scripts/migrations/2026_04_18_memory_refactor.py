#!/usr/bin/env python3
"""Persistent Memory refactor migration — 2026-04-18.

Spec: /Users/dana/.openclaw/workspace/v3/memory_refactor_spec.md

This script runs AFTER the server has booted once against the target DB so
that server/db.py:_init_db has already added the six new columns
(subject, status, superseded_by, retired_at, retire_reason, ttl_seconds).
If those columns aren't present yet, the script adds them itself (idempotent).

It then hand-curates ~30 subject clusters covering the high-traffic topics
from the 2026-03-29 → 2026-04-18 window, assigns each matching active row
a `subject`, and marks older same-subject rows of equal-or-lower rank as
`status='superseded'` (with `superseded_by` pointing at the winner).

Usage:
    python3 scripts/migrations/2026_04_18_memory_refactor.py \
        --db ~/.openclaw/apex/state/apex_dev.db --dry-run
    python3 scripts/migrations/2026_04_18_memory_refactor.py \
        --db ~/.openclaw/apex/state/apex_dev.db --apply

Modes:
  --dry-run (default): prints every UPDATE that WOULD run. Zero writes.
  --apply:             executes inside a transaction, commits at the end.

Safety:
  - No DELETEs.
  - Only rows where status is currently NULL or 'active' are touched.
  - Unmigrated rows (no subject keyword match) keep status='active' and
    continue to appear in injection as today.
  - Rerunning is a no-op: subject is only written if currently NULL; the
    supersession pass only touches rows whose status is still 'active'.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


# --- Supersession rules ----------------------------------------------------

CATEGORY_RANK = {"decision": 3, "correction": 3, "task": 2, "context": 1}

# The subject clusters. Each entry:
#   subject:      dotted-path subject string (written to persona_memories.subject)
#   match_any:    list of lowercase substrings; a row matches if ANY substring
#                 is present in content.lower()
#   profile_scope: optional set of profile_ids; if set, only rows owned by
#                 one of these profiles are matched (reduces false positives
#                 when a keyword is ambiguous, e.g. "codex")
#
# Order matters: the first matching cluster wins (a row is only assigned one
# subject). Put the narrowest clusters first.
SUBJECT_CLUSTERS: list[dict] = [
    # --- V3 v1 claim_store / gate build (the primary acceptance-test subject) -
    {
        "subject": "v3.v1_gate.build",
        "match_any": [
            "v3 v1 gate",          # "V3 v1 gate build plan", "Day 1 shipped", etc.
            "v3 day 1",
            "v3 day 2",
            "claim_store mcp",
            "claim_assert",
            "gate-test-haiku",
            "gate-test-codex",
        ],
    },
    {
        "subject": "v3.v1_gate.mode",
        "match_any": ["v3 v1 gate experiment uses tag mode", "tag mode, not block mode"],
    },
    {
        "subject": "v3.v1_gate.persona_plan",
        "match_any": ["v3 v1 gate experiment — persona plan", "gate experiment - persona plan"],
    },
    # --- V3 elicitation rooms & architecture -----------------------------------
    {
        "subject": "v3.elicitation.room_c",
        "match_any": ["room c (chat c3a7b2d5)", "v3 room c"],
    },
    {
        "subject": "v3.elicitation.room_d",
        "match_any": ["room d close", "v3 elicitation lattice result"],
    },
    {
        "subject": "v3.elicitation.room",
        "match_any": [
            "v3 architecture elicitation room",
            "v3d elicitation",
            "v3 design-journal",
            "chat 1253d946",
        ],
    },
    {
        "subject": "v3.architecture.clock_subagent",
        "match_any": ["clock sub-agent at l0 percepti", "v3 architecture addition"],
    },
    {
        "subject": "v3.architecture.time_grounding",
        "match_any": ["v3 time-grounding"],
    },
    {
        "subject": "v3.research.next_action",
        "match_any": ["v3 research next action"],
    },
    # --- Apex SQLite writer lock ----------------------------------------------
    {
        "subject": "apex.db.writer_lock",
        "match_any": [
            "writer-lock starvation",
            "writer_lock",
            "sqlite writer-lock",
        ],
    },
    # --- Apex Interceptor (browser-agent) MCP ---------------------------------
    {
        "subject": "apex.interceptor.mcp",
        "match_any": [
            "interceptor (github.com",
            "interceptor × apex",
            "interceptor x apex",
            "interceptor (browser-agent)",
            "interceptor chrome extension",
        ],
    },
    # --- Apex computer_use sub-clusters (each is its own subject) -------------
    {
        "subject": "apex.computer_use.activate_target_app",
        "match_any": [
            "activate_target_app",
            "computer_use activate_target_app",
        ],
    },
    {
        "subject": "apex.computer_use.type_text",
        "match_any": [
            "computer_use type_text",
            "chunked-type_text",
            "chunked-with-wait",
            "pause-mid-type",
        ],
    },
    {
        "subject": "apex.computer_use.pause_ui",
        "match_any": [
            "computer_use pause",
            "pause-button",
            "pause pill cross-chat leak",
            "persistent resume ui",
        ],
    },
    {
        "subject": "apex.computer_use.textedit",
        "match_any": [
            "textedit scratch fallback",
            "textedit cold-launch",
            "preemptive `open -e` for textedit",
            "open -e` for textedit",
        ],
    },
    {
        "subject": "apex.computer_use.dock_hide",
        "match_any": ["mcp python dock-hide", "dock-hide fix"],
    },
    {
        "subject": "apex.computer_use.mcp",
        "match_any": [
            "computer-use feature shipped",
            "computer-use (gui agent)",
            "cgeventposttopid",
            "computer_use ui toggle",
            "computer_use full-stack validation",
            "computer_use mcp",
        ],
    },
    # --- Apex thinking-pill family --------------------------------------------
    {
        "subject": "apex.thinking_pill.blinker",
        "match_any": [
            "b-4 blinker",
            "b-4 fix",
            "b-4 thinking pill",
            "b-4 final fix",
            "blinker/active indicator",
            "b-32",  # same family (blinker variant)
        ],
    },
    {
        "subject": "apex.thinking_pill.collapse",
        "match_any": [
            "thinking pill stays expand",
            "b-2 (thinking pill)",
            "b-2 thinking pill",
            "thinking pill collapse",
            "thinking pill ux approved",
        ],
    },
    {
        "subject": "apex.thinking_pill.leak",
        "match_any": [
            "thinking pill in every chat",
            "cross-chat leak",  # thinking_pill disappear variant
        ],
    },
    # --- Subconscious / memory killswitch -------------------------------------
    {
        "subject": "apex.subconscious.killswitch",
        "match_any": [
            "subconscious_disabled",
            "per-chat subconscious toggle",
        ],
    },
    # --- Chatmine model attribution (per project invariant) -------------------
    {
        "subject": "chatmine.model.attribution",
        "match_any": [
            "chatmine extractor backfill",
            "chatmine_trigger_cc.py",
            "codex sdk (model `codex:gpt-5.4`",
            "codex:gpt-5.4",
        ],
    },
    # --- Chatmine pipeline / extractor ----------------------------------------
    {
        "subject": "chatmine.extractor.prompt_fix",
        "match_any": ["chatmine extractor prompt architecture fix"],
    },
    {
        "subject": "chatmine.pipeline.stop_hooks",
        "match_any": [
            "stop and stopfailure hooks installed",
            "stop/stopfailure hooks",
        ],
    },
    # --- DeepThought OB sensitivity (3-row cluster from 2026-04-17) -----------
    {
        "subject": "deepthought.ob_sensitivity",
        "match_any": [
            "ob sensitivity knob",
            "ob sensitivity backtest",
            "deepthought v4.2 ob sensitivity",
        ],
    },
    {
        "subject": "deepthought.cvx.position_state",
        "match_any": ["active cvx position", "cvx position as of"],
    },
    # --- Apex mention validator bug (known open task) -------------------------
    {
        "subject": "apex.group_coordinator.mention_validator",
        "match_any": [
            "mention validator bug",
            "_match_group_mention_prefix",
        ],
    },
    # --- Audit log v3 (old completed UI work) ---------------------------------
    {
        "subject": "apex.ui.audit_log_v3",
        "match_any": ["audit log v3"],
    },
    # --- LLM provider expansion -----------------------------------------------
    {
        "subject": "apex.model_dispatch.providers",
        "match_any": ["4 new llm providers", "xai (grok), deepseek, google (gemini), zhipu"],
    },
    # --- code-review-graph MCP ------------------------------------------------
    {
        "subject": "apex.code_review_graph.install",
        "match_any": ["code-review-graph v1.8.2"],
    },
    # --- DB wipeout incident (correction row) ---------------------------------
    {
        "subject": "apex.test_security_fixes.db_wipeout",
        "match_any": ["db wipeout root cause"],
    },
]


# --- Utilities -------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_SCHEMA_DDL: list[tuple[str, str]] = [
    ("subject",       "ALTER TABLE persona_memories ADD COLUMN subject TEXT"),
    ("status",        "ALTER TABLE persona_memories ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"),
    ("superseded_by", "ALTER TABLE persona_memories ADD COLUMN superseded_by TEXT REFERENCES persona_memories(id)"),
    ("retired_at",    "ALTER TABLE persona_memories ADD COLUMN retired_at TEXT"),
    ("retire_reason", "ALTER TABLE persona_memories ADD COLUMN retire_reason TEXT"),
    ("ttl_seconds",   "ALTER TABLE persona_memories ADD COLUMN ttl_seconds INTEGER"),
]
_SCHEMA_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_pm_subject_status ON persona_memories(subject, status)",
    "CREATE INDEX IF NOT EXISTS idx_pm_status_created ON persona_memories(status, created_at DESC)",
]


def _missing_schema(conn: sqlite3.Connection) -> list[str]:
    """Return list of DDL statements that WOULD need to run (schema diff only, no writes)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(persona_memories)").fetchall()}
    return [stmt for colname, stmt in _SCHEMA_DDL if colname not in cols]


def _apply_schema(conn: sqlite3.Connection) -> list[str]:
    """Idempotently add the six new columns + two indexes. Returns the DDL
    statements that were actually executed. Writes immediately on the connection."""
    executed: list[str] = []
    cols = {r[1] for r in conn.execute("PRAGMA table_info(persona_memories)").fetchall()}
    for colname, stmt in _SCHEMA_DDL:
        if colname not in cols:
            conn.execute(stmt)
            executed.append(stmt)
    for idx in _SCHEMA_INDEXES:
        conn.execute(idx)
    return executed


def _fetch_active(conn: sqlite3.Connection) -> list[tuple]:
    """Return all active rows with (id, profile_id, category, subject, created_at, content_lc)."""
    rows = conn.execute(
        "SELECT id, profile_id, category, subject, created_at, LOWER(content) "
        "FROM persona_memories "
        "WHERE COALESCE(status, 'active') = 'active'"
    ).fetchall()
    return rows


def _assign_subjects(rows: list[tuple]) -> dict[str, str]:
    """For each row, pick the first matching cluster. Returns id->subject map
    for rows whose current subject is NULL and a cluster matched."""
    assignments: dict[str, str] = {}
    for (rid, _pid, _cat, cur_subject, _created, content_lc) in rows:
        if cur_subject:
            continue  # keep manual/prior subject
        for cluster in SUBJECT_CLUSTERS:
            prof_scope = cluster.get("profile_scope")
            if prof_scope and _pid not in prof_scope:
                continue
            if any(kw in content_lc for kw in cluster["match_any"]):
                assignments[rid] = cluster["subject"]
                break
    return assignments


def _plan_supersession(conn: sqlite3.Connection,
                       new_subject_by_id: dict[str, str]) -> list[tuple[str, str]]:
    """Compute which rows should be superseded by which winner.

    Returns list of (loser_id, winner_id). Rules:
      - Group active rows by (profile_id, effective_subject).
      - In each group, sort by (rank DESC, created_at DESC). Highest-rank newest = winner.
      - For each other row in the same group where rank(winner) >= rank(row),
        the row is superseded by the winner.
      - Rows with rank strictly higher than all winners are left active
        (cannot happen under "rank DESC" sort, but defensive).
    """
    # Fetch (id, profile_id, category, subject, created_at) for every row we
    # care about, combining current subject with pending assignments.
    rows = conn.execute(
        "SELECT id, profile_id, category, subject, created_at "
        "FROM persona_memories "
        "WHERE COALESCE(status, 'active') = 'active'"
    ).fetchall()

    groups: dict[tuple[str, str], list[tuple]] = {}
    for (rid, pid, cat, cur_subj, created) in rows:
        effective = new_subject_by_id.get(rid) or cur_subj
        if not effective:
            continue
        groups.setdefault((pid, effective), []).append((rid, cat, created))

    plan: list[tuple[str, str]] = []
    for _key, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(
            key=lambda r: (CATEGORY_RANK.get(r[1] or "", 0), r[2] or ""),
            reverse=True,
        )
        winner_id, winner_cat, _ = members[0]
        winner_rank = CATEGORY_RANK.get(winner_cat or "", 0)
        for rid, cat, _created in members[1:]:
            rank = CATEGORY_RANK.get(cat or "", 0)
            if winner_rank >= rank:
                plan.append((rid, winner_id))
    return plan


def _format_update_assign(rid: str, subject: str) -> str:
    return (f"UPDATE persona_memories SET subject='{subject}' "
            f"WHERE id='{rid}' AND subject IS NULL;")


def _format_update_supersede(loser_id: str, winner_id: str, now: str) -> str:
    return (f"UPDATE persona_memories SET status='superseded', "
            f"superseded_by='{winner_id}', retired_at='{now}' "
            f"WHERE id='{loser_id}' AND COALESCE(status,'active')='active';")


# --- Main ------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="Print UPDATEs, do not commit (default)")
    g.add_argument("--apply", action="store_true", help="Execute + commit")
    parser.add_argument("--db", required=True, help="Path to apex_dev.db or apex.db")
    args = parser.parse_args()

    dry = not args.apply  # default is dry-run
    db_path = Path(args.db).expanduser()
    if not db_path.exists():
        print(f"ERROR: db not found: {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # isolation_level=None would let us manage txns manually; by default Python's
    # sqlite3 auto-BEGINs on DML but NOT on DDL. We want one atomic unit that
    # can be rolled back in dry-run, so we manage the txn explicitly.
    conn.isolation_level = None

    mode = "DRY-RUN" if dry else "APPLY"
    print(f"=== memory_refactor 2026-04-18 [{mode}] db={db_path} ===\n")

    rc = 0
    try:
        conn.execute("BEGIN")

        # 1) Schema (DDL inside the txn — SQLite ALTER TABLE is transactional)
        ddl_run = _apply_schema(conn)
        if ddl_run:
            print(f"Schema: {len(ddl_run)} column adds queued")
            for s in ddl_run:
                print(f"  + {s}")
        else:
            print("Schema: all new columns already present.")

        # 2) Subject assignment
        rows = _fetch_active(conn)
        print(f"\nActive rows to scan: {len(rows)}")
        assignments = _assign_subjects(rows)
        print(f"Subject assignments planned: {len(assignments)}")

        per_subject_counts: dict[str, int] = {}
        for subj in assignments.values():
            per_subject_counts[subj] = per_subject_counts.get(subj, 0) + 1
        for subj in sorted(per_subject_counts, key=lambda s: -per_subject_counts[s]):
            print(f"  {subj:46s} {per_subject_counts[subj]:3d}")

        # 3) Execute assignments (so supersession plan sees them through normal
        #    reads; will be rolled back in dry-run)
        for rid, subj in assignments.items():
            conn.execute(
                "UPDATE persona_memories SET subject=? WHERE id=? AND subject IS NULL",
                (subj, rid),
            )

        # 4) Supersession plan
        plan = _plan_supersession(conn, {})
        print(f"\nSupersessions planned: {len(plan)}")

        now = _now_iso()
        print("\n--- UPDATE statements ---")
        for rid, subj in assignments.items():
            print(_format_update_assign(rid, subj))
        for loser_id, winner_id in plan:
            print(_format_update_supersede(loser_id, winner_id, now))
            conn.execute(
                "UPDATE persona_memories SET status='superseded', superseded_by=?, retired_at=? "
                "WHERE id=? AND COALESCE(status,'active')='active'",
                (winner_id, now, loser_id),
            )

        # 5) Post-migration visibility — flag the acceptance-test marker row
        marker = conn.execute(
            "SELECT id, status, superseded_by FROM persona_memories "
            "WHERE content LIKE '%V3 v1 gate build plan%'"
        ).fetchall()
        summary = conn.execute(
            "SELECT COALESCE(status,'active'), COUNT(*) FROM persona_memories GROUP BY 1"
        ).fetchall()

        if dry:
            conn.execute("ROLLBACK")
            print(f"\n[DRY-RUN] {len(assignments)} subject assigns + {len(plan)} supersessions. "
                  f"No writes (rolled back).")
            print("Projected post-migration status counts:")
            for status, n in summary:
                print(f"  {status:12s} {n}")
            if marker:
                print("\nAcceptance-test marker rows ('V3 v1 gate build plan'):")
                for r in marker:
                    print(f"  id={r[0]} status={r[1]} superseded_by={r[2]}")
        else:
            conn.execute("COMMIT")
            print(f"\n[APPLIED]")
            print("Post-migration status counts:")
            for status, n in summary:
                print(f"  {status:12s} {n}")
            if marker:
                print("\nAcceptance-test marker rows ('V3 v1 gate build plan'):")
                for r in marker:
                    print(f"  id={r[0]} status={r[1]} superseded_by={r[2]}")
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        print(f"\nFAILED, rolled back: {e}", file=sys.stderr)
        rc = 3

    conn.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
