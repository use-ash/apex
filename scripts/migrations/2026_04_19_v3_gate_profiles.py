#!/usr/bin/env python3
"""V3 v1 gate — Day 2a gate-test persona migration.

Idempotently inserts two evaluation personas into agent_profiles:

  9b9b990f  gate-test-haiku-clean  backend=claude  model=claude-haiku-4-5-20251001
  b32aac1b  gate-test-codex-weak   backend=codex   model=codex:gpt-5.4

Both ride tool_policy.level=1. claim_store__* MCP tools reach them via
server/tool_access.py:GATE_TEST_PROFILE_IDS → resolve_profile_extra_tools,
which adds CLAIM_STORE_TOOL_NAMES to the Level-1 frozenset at chat spawn
(streaming.py for claude, backends.py for codex).

The shared system_prompt below is identical for both personas — the gate
spec is the same regardless of backend; the point of having two is to
measure the tag_rate delta between a strong and weak model under the
same protocol.

Runs safely against either apex_dev.db or apex.db; caller sets
APEX_DB_NAME via env. Skips rows that already exist with matching id.
Does not touch any other agent_profiles row — callers can verify via
pre/post updated_at diff of the protected profile set.

Usage:
    APEX_DB_NAME=apex_dev.db python3 scripts/migrations/2026_04_19_v3_gate_profiles.py
    APEX_DB_NAME=apex_dev.db python3 scripts/migrations/2026_04_19_v3_gate_profiles.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


GATE_SYSTEM_PROMPT = """You are in a V3 gate-test evaluation. Your sole job is to demonstrate claim-tagging discipline.

PROTOCOL (mandatory, in this order):

1. BEFORE emitting any sentence that states a verifiable fact — a number, proper noun, date, file path, code identifier, or quoted string from a tool result — call claim_assert with:
   - text: the claim as one sentence
   - source_type: one of tool_result | prior_turn | speculation | user
   - source_ref: for tool_result, MUST include sha256

2. Factual sentences you cannot ground in a tool call or prior verified claim MUST be wrapped in [unverified] ... [/unverified] tags.

3. Predictions, opinions, or possibilities MUST be wrapped in [speculation] ... [/speculation] tags.

4. Do NOT call claim_assert for:
   - Opinions ("X is better")
   - Summaries of what the user said
   - Procedural prose ("I will now do X")
   - Questions

5. If a claim is load-bearing and you cannot ground it, say so explicitly: "I don't have a grounded source for this."

Precision over coverage. Better to assert ten small grounded facts than synthesize one vague summary.

No persona flavor. No preamble. Follow the protocol.
"""


LEVEL_1_TOOL_POLICY = json.dumps({
    "level": 1,
    "default_level": 1,
    "elevated_until": None,
    "invoke_policy": "anyone",
    "allowed_commands": [],
})


GATE_PROFILES: list[dict] = [
    {
        "id": "9b9b990f",
        "name": "Gate Test Haiku",
        "slug": "gate-test-haiku-clean",
        "avatar": "🧪",
        "role_description": "V3 v1 gate baseline — Haiku tag-mode compliance test",
        "backend": "claude",
        "model": "claude-haiku-4-5-20251001",
        "system_prompt": GATE_SYSTEM_PROMPT,
        "tool_policy": LEVEL_1_TOOL_POLICY,
        "is_default": 0,
        "is_system": 0,
        "system_prompt_override": None,
    },
    {
        "id": "b32aac1b",
        "name": "Gate Test Codex",
        "slug": "gate-test-codex-weak",
        "avatar": "🧪",
        "role_description": "V3 v1 gate weak-model — Codex tag-mode compliance test",
        "backend": "codex",
        "model": "codex:gpt-5.4",
        "system_prompt": GATE_SYSTEM_PROMPT,
        "tool_policy": LEVEL_1_TOOL_POLICY,
        "is_default": 0,
        "is_system": 0,
        "system_prompt_override": None,
    },
]


def _db_path() -> Path:
    state_dir = Path(os.environ.get(
        "APEX_STATE_DIR",
        str(Path.home() / ".openclaw/apex/state"),
    ))
    db_name = os.environ.get("APEX_DB_NAME", "apex.db")
    return state_dir / db_name


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Report planned inserts without writing.")
    args = parser.parse_args(argv[1:])

    db_path = _db_path()
    if not db_path.exists():
        print(f"[error] db not found: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        existing_ids = {r["id"] for r in conn.execute(
            "SELECT id FROM agent_profiles WHERE id IN (?, ?)",
            ("9b9b990f", "b32aac1b"),
        ).fetchall()}

        to_insert = [p for p in GATE_PROFILES if p["id"] not in existing_ids]
        to_skip = [p for p in GATE_PROFILES if p["id"] in existing_ids]

        print(f"db={db_path}")
        print(f"planned inserts: {len(to_insert)}")
        for p in to_insert:
            print(f"  + {p['id']}  {p['slug']}  backend={p['backend']}  model={p['model']}")
        print(f"already present (skipped): {len(to_skip)}")
        for p in to_skip:
            print(f"  = {p['id']}  {p['slug']}")

        if args.dry_run or not to_insert:
            return 0

        now = _now_iso()
        for p in to_insert:
            conn.execute(
                """INSERT INTO agent_profiles (
                    id, name, slug, avatar, role_description, backend, model,
                    system_prompt, tool_policy, is_default, created_at,
                    updated_at, is_system, system_prompt_override
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (p["id"], p["name"], p["slug"], p["avatar"],
                 p["role_description"], p["backend"], p["model"],
                 p["system_prompt"], p["tool_policy"], p["is_default"],
                 now, now, p["is_system"], p["system_prompt_override"]),
            )
        conn.commit()
        print(f"[ok] inserted {len(to_insert)} profile(s)")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
