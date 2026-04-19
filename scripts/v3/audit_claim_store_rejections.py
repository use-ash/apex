#!/usr/bin/env python3
"""Audit silent rejections in the v3 claim_store.

Cross-references attempted ``claim_store__claim_assert`` tool calls (recorded in
``messages.tool_events`` JSON arrays) against rows that actually landed in the
``claims`` table, broken out per chat_id and per agent profile. The gap is the
set of silent rejections: the SDK thought the tool succeeded, but no DB row was
written (typically because ``mcp_claim_store.py`` raised a ``ValueError`` that
the SDK swallowed, or a host permission denial flipped is_error=True after the
fact).

READ-ONLY. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths / constants
# --------------------------------------------------------------------------- #

DB_PATH = Path("/Users/dana/.openclaw/apex/state/apex_dev.db")
LOG_CANDIDATES = [
    Path("/Users/dana/.openclaw/apex/state/apex_dev.log"),
    Path("/Users/dana/.openclaw/apex/state/apex.log"),
    Path("/Users/dana/.openclaw/apex/state/apex.log.1"),
]
DAY3_DIR = Path("/Users/dana/.openclaw/workspace/v3/experiments/day3_runs")

# The MCP tool appears in tool_events under several canonical names depending on
# whether the SDK namespaces it: ``mcp__claim_store__claim_assert`` (Anthropic
# SDK), ``claim_store__claim_assert`` (tool_loop allowed list).
CLAIM_ASSERT_NAMES = {
    "mcp__claim_store__claim_assert",
    "claim_store__claim_assert",
}

EXPECTED_CLAIMS_COLS = {"chat_id", "created_at"}
EXPECTED_CHATS_COLS = {"id", "profile_id"}
EXPECTED_PROFILES_COLS = {"id", "slug"}
EXPECTED_MESSAGES_COLS = {"chat_id", "tool_events", "created_at"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def parse_iso(ts: str) -> datetime | None:
    """Best-effort parse of the mixed timestamp formats we see in apex."""
    if not ts:
        return None
    s = ts.strip()
    # Normalise trailing Z to +00:00 so fromisoformat handles it.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def probe_schema(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """Return {table: set(columns)} for tables we care about."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}
    schema: dict[str, set[str]] = {}
    for t in ("claims", "messages", "chats", "agent_profiles"):
        if t not in tables:
            schema[t] = set()
            continue
        cur.execute(f"PRAGMA table_info({t})")
        schema[t] = {r[1] for r in cur.fetchall()}
    schema["__tables__"] = tables
    return schema


def verify_schema(schema: dict[str, set[str]]) -> list[str]:
    issues: list[str] = []
    checks = [
        ("claims", EXPECTED_CLAIMS_COLS),
        ("chats", EXPECTED_CHATS_COLS),
        ("agent_profiles", EXPECTED_PROFILES_COLS),
        ("messages", EXPECTED_MESSAGES_COLS),
    ]
    for table, needed in checks:
        cols = schema.get(table, set())
        if not cols:
            issues.append(f"missing table: {table}")
            continue
        missing = needed - cols
        if missing:
            issues.append(f"{table}: missing columns {sorted(missing)}")
    return issues


def load_profiles(conn: sqlite3.Connection) -> dict[str, str]:
    """Map profile_id -> slug (or name if slug is missing)."""
    cur = conn.cursor()
    cur.execute("SELECT id, slug, name FROM agent_profiles")
    out: dict[str, str] = {}
    for pid, slug, name in cur.fetchall():
        out[pid] = slug or name or pid
    return out


def load_chats(conn: sqlite3.Connection) -> dict[str, str]:
    """Map chat_id -> profile_id."""
    cur = conn.cursor()
    cur.execute("SELECT id, profile_id FROM chats")
    return {row[0]: (row[1] or "") for row in cur.fetchall()}


def iter_tool_events(conn: sqlite3.Connection, since: datetime | None):
    """Yield (chat_id, msg_created_at_dt, event_dict) for every tool event.

    ``tool_events`` is a JSON array of dicts. We tolerate malformed rows.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT chat_id, created_at, tool_events FROM messages "
        "WHERE tool_events IS NOT NULL AND tool_events != '' AND tool_events != '[]'"
    )
    for chat_id, created_at, blob in cur.fetchall():
        dt = parse_iso(created_at)
        if since and dt and dt < since:
            continue
        try:
            events = json.loads(blob)
        except (TypeError, ValueError):
            continue
        if not isinstance(events, list):
            continue
        for ev in events:
            if isinstance(ev, dict):
                yield chat_id, dt, ev


def count_attempts(
    conn: sqlite3.Connection, since: datetime | None
) -> tuple[dict[str, int], dict[str, tuple[datetime | None, datetime | None]]]:
    """Return (attempts per chat_id, time range per chat_id).

    An "attempt" is any tool_use whose ``name`` matches claim_assert. We also
    track the [min, max] message timestamp per chat so the log-grep step can
    scope to a window.
    """
    attempts: Counter[str] = Counter()
    windows: dict[str, tuple[datetime | None, datetime | None]] = {}
    for chat_id, dt, ev in iter_tool_events(conn, since):
        name = ev.get("name") or ""
        if name not in CLAIM_ASSERT_NAMES:
            continue
        # Skip if this is actually a tool_result row (some pipelines emit both
        # under the same list; tool_result objects usually have no ``input``).
        if ev.get("type") == "tool_result":
            continue
        attempts[chat_id] += 1
        lo, hi = windows.get(chat_id, (dt, dt))
        if dt is not None:
            lo = dt if lo is None or dt < lo else lo
            hi = dt if hi is None or dt > hi else hi
        windows[chat_id] = (lo, hi)
    return dict(attempts), windows


def count_landed(conn: sqlite3.Connection, since: datetime | None) -> dict[str, int]:
    """Count rows in ``claims`` per chat_id."""
    cur = conn.cursor()
    if since:
        cur.execute(
            "SELECT chat_id, COUNT(*) FROM claims WHERE created_at >= ? GROUP BY chat_id",
            (since.strftime("%Y-%m-%dT%H:%M:%SZ"),),
        )
    else:
        cur.execute("SELECT chat_id, COUNT(*) FROM claims GROUP BY chat_id")
    return {row[0]: row[1] for row in cur.fetchall()}


# --------------------------------------------------------------------------- #
# Log scanning for ValueError context
# --------------------------------------------------------------------------- #

LOG_TS_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
VALUE_ERROR_RE = re.compile(r"ValueError: (.+)$")


def load_log_errors() -> list[tuple[datetime, str]]:
    """Scan every candidate log for ValueError lines originating anywhere near
    mcp_claim_store. We keep (ts, message) tuples; deduplication happens later.
    """
    hits: list[tuple[datetime, str]] = []
    for path in LOG_CANDIDATES:
        if not path.exists():
            continue
        try:
            with path.open("r", errors="replace") as fh:
                current_ts: datetime | None = None
                near_claim_store = False
                for line in fh:
                    m = LOG_TS_RE.match(line)
                    if m:
                        parsed = parse_iso(m.group(1).replace(" ", "T") + "+00:00")
                        current_ts = parsed
                        near_claim_store = "claim_store" in line or "mcp_claim_store" in line
                    else:
                        if "claim_store" in line or "mcp_claim_store" in line:
                            near_claim_store = True
                    ve = VALUE_ERROR_RE.search(line)
                    if ve and (near_claim_store or "claim" in line.lower()):
                        msg = ve.group(1).strip()
                        hits.append((current_ts or datetime.min.replace(tzinfo=timezone.utc), msg))
        except OSError:
            continue
    return hits


def sample_reasons(
    log_errors: list[tuple[datetime, str]],
    window: tuple[datetime | None, datetime | None],
    limit: int = 3,
) -> list[str]:
    lo, hi = window
    counter: Counter[str] = Counter()
    for ts, msg in log_errors:
        if lo and ts < lo:
            continue
        if hi and ts > hi:
            continue
        counter[msg] += 1
    return [f"{msg} (x{n})" for msg, n in counter.most_common(limit)]


# --------------------------------------------------------------------------- #
# Day 3 JSON backfill
# --------------------------------------------------------------------------- #

def scan_day3_backfill() -> dict[str, dict[str, int]]:
    """Return {chat_id_short: {"attempts": n, "claims": n, "profile": slug}}.

    Day 3 JSONs record chat_id as an 8-char prefix. We keep the shortened key so
    downstream reporting can surface them even if the message/claims row has
    been pruned from the DB.
    """
    out: dict[str, dict[str, int]] = {}
    if not DAY3_DIR.exists():
        return out
    for path in sorted(DAY3_DIR.glob("*.json")):
        try:
            with path.open("r") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        meta = doc.get("meta") or {}
        chat_id = meta.get("chat_id") or ""
        profile = meta.get("profile_slug") or meta.get("profile_id") or ""
        tool_uses = doc.get("tool_uses") or []
        claims = doc.get("claims") or []
        attempts = 0
        for tu in tool_uses:
            name = (tu or {}).get("name") or ""
            if name in CLAIM_ASSERT_NAMES or name.endswith("claim_assert"):
                attempts += 1
        if chat_id:
            bucket = out.setdefault(
                chat_id,
                {"attempts": 0, "claims": 0, "profile": profile, "sources": []},
            )
            bucket["attempts"] += attempts
            bucket["claims"] += len(claims)
            bucket["sources"].append(path.name)
    return out


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def build_rows(
    attempts: dict[str, int],
    landed: dict[str, int],
    windows: dict[str, tuple[datetime | None, datetime | None]],
    chats: dict[str, str],
    profiles: dict[str, str],
    log_errors: list[tuple[datetime, str]],
    filter_chat: str | None,
    filter_profile: str | None,
) -> list[dict]:
    chat_ids = set(attempts) | set(landed)
    rows: list[dict] = []
    for cid in sorted(chat_ids):
        profile_id = chats.get(cid, "")
        slug = profiles.get(profile_id, profile_id or "<unknown>")
        if filter_chat and cid != filter_chat and not cid.startswith(filter_chat):
            continue
        if filter_profile and filter_profile not in (profile_id, slug):
            continue
        a = attempts.get(cid, 0)
        l = landed.get(cid, 0)
        rej = max(a - l, 0)
        rate = f"{rej / a:.1%}" if a else "n/a"
        reasons = sample_reasons(log_errors, windows.get(cid, (None, None))) if rej else []
        rows.append(
            {
                "chat_id": cid,
                "profile_slug": slug,
                "attempts": a,
                "landed": l,
                "rejected": rej,
                "rejection_rate": rate,
                "sample_reasons": reasons,
            }
        )
    return rows


def render_text(rows: list[dict], day3: dict[str, dict]) -> str:
    # Column widths.
    chat_w = max([len("chat_id"), *[len(r["chat_id"]) for r in rows]]) if rows else len("chat_id")
    prof_w = max([len("profile"), *[len(r["profile_slug"]) for r in rows]]) if rows else len("profile")
    chat_w = min(chat_w, 40)
    prof_w = min(prof_w, 30)

    lines: list[str] = []
    header = (
        f"{'chat_id':<{chat_w}}  {'profile':<{prof_w}}  "
        f"{'attempts':>8}  {'landed':>6}  {'rejected':>8}  {'rate':>6}  reasons"
    )
    lines.append(header)
    lines.append("-" * len(header))
    tot_a = tot_l = tot_r = 0
    for r in rows:
        reasons = "; ".join(r["sample_reasons"]) if r["sample_reasons"] else "-"
        lines.append(
            f"{r['chat_id'][:chat_w]:<{chat_w}}  "
            f"{r['profile_slug'][:prof_w]:<{prof_w}}  "
            f"{r['attempts']:>8}  {r['landed']:>6}  {r['rejected']:>8}  "
            f"{r['rejection_rate']:>6}  {reasons}"
        )
        tot_a += r["attempts"]
        tot_l += r["landed"]
        tot_r += r["rejected"]
    lines.append("-" * len(header))
    total_rate = f"{tot_r / tot_a:.1%}" if tot_a else "n/a"
    lines.append(
        f"{'TOTAL':<{chat_w}}  {'':<{prof_w}}  "
        f"{tot_a:>8}  {tot_l:>6}  {tot_r:>8}  {total_rate:>6}  -"
    )

    if day3:
        lines.append("")
        lines.append("Day 3 matrix backfill (chat_id shown as 8-char prefix from JSON meta):")
        lines.append(f"{'chat_id':<10}  {'profile':<30}  {'attempts':>8}  {'claims':>6}")
        for cid, info in sorted(day3.items()):
            lines.append(
                f"{cid:<10}  {str(info.get('profile',''))[:30]:<30}  "
                f"{info.get('attempts',0):>8}  {info.get('claims',0):>6}"
            )

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat", help="Filter to a specific chat_id (accepts prefix).")
    parser.add_argument("--profile", help="Filter to a profile_id or slug.")
    parser.add_argument("--since", help="ISO timestamp; only count events at or after this time.")
    parser.add_argument("--json", action="store_true", help="Emit the structured payload to stdout.")
    args = parser.parse_args(argv)

    since = parse_iso(args.since) if args.since else None
    if args.since and since is None:
        print(f"error: could not parse --since value: {args.since!r}", file=sys.stderr)
        return 2

    if not DB_PATH.exists():
        print(f"error: database not found at {DB_PATH}", file=sys.stderr)
        return 2

    # Open read-only.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        schema = probe_schema(conn)
        issues = verify_schema(schema)
        if issues:
            print("schema mismatch — cannot proceed safely:", file=sys.stderr)
            for iss in issues:
                print(f"  - {iss}", file=sys.stderr)
            print("tables found:", sorted(schema.get("__tables__", set())), file=sys.stderr)
            for t in ("claims", "messages", "chats", "agent_profiles"):
                print(f"  {t} columns: {sorted(schema.get(t, set()))}", file=sys.stderr)
            return 3

        profiles = load_profiles(conn)
        chats = load_chats(conn)
        attempts, windows = count_attempts(conn, since)
        landed = count_landed(conn, since)
    finally:
        conn.close()

    log_errors = load_log_errors()

    rows = build_rows(
        attempts=attempts,
        landed=landed,
        windows=windows,
        chats=chats,
        profiles=profiles,
        log_errors=log_errors,
        filter_chat=args.chat,
        filter_profile=args.profile,
    )
    day3 = scan_day3_backfill()
    if args.chat:
        day3 = {k: v for k, v in day3.items() if k == args.chat or k.startswith(args.chat)}
    if args.profile:
        day3 = {k: v for k, v in day3.items() if args.profile in (v.get("profile"), v.get("profile", ""))}

    if args.json:
        payload = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "filters": {"chat": args.chat, "profile": args.profile, "since": args.since},
            "rows": rows,
            "totals": {
                "attempts": sum(r["attempts"] for r in rows),
                "landed": sum(r["landed"] for r in rows),
                "rejected": sum(r["rejected"] for r in rows),
            },
            "day3_backfill": day3,
            "log_sources_scanned": [str(p) for p in LOG_CANDIDATES if p.exists()],
        }
        # sort_keys for idempotency.
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print(render_text(rows, day3))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
