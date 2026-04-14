#!/opt/homebrew/bin/python3
"""Bridge chatmine Claude Code extractions into the guidance pipeline.

Reads chatmine/claude/{session_id}/{date}.json files,
transforms to digest format, and merges into guidance.json
via the existing _merge_guidance() pipeline in digest.py.

Mapping:
    chatmine decisions  → guidance decisions  (confidence 0.4)
    chatmine bugs_fixed → guidance decisions   (confidence 0.4)
    chatmine lessons    → guidance corrections (confidence 0.4)
    chatmine features   → skipped (historical, not guidance-worthy)
    chatmine topics     → skipped

State tracking:
    Writes .bridged marker with mtime per session/day to avoid re-processing.

Usage:
    python3 chatmine_bridge.py                  # Bridge all un-bridged
    python3 chatmine_bridge.py --session ID     # Bridge specific session
    python3 chatmine_bridge.py --recent N       # Bridge N most recently modified sessions
    python3 chatmine_bridge.py --dry-run        # Show what would be bridged
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import state
from digest import _merge_guidance, _similarity
from contradiction_detector import check_contradictions, check_intra_session, is_overridden

CHATMINE_CLAUDE_DIR = Path(config.STATE_DIR) / "chatmine" / "claude"
BRIDGE_STATE_FILE = Path(config.STATE_DIR) / "chatmine_bridge_state.json"

# Lower confidence than real-time digests (0.5) because chatmine
# runs through a small model and has dedup issues
CHATMINE_CONFIDENCE = 0.4


def _load_bridge_state() -> dict:
    """Load {session_id: {date: mtime_epoch}} tracking what's been bridged."""
    try:
        with open(BRIDGE_STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_bridge_state(bs: dict) -> None:
    tmp = str(BRIDGE_STATE_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(bs, f, indent=2)
    os.rename(tmp, str(BRIDGE_STATE_FILE))


def _pre_dedup(items: list[str], threshold: float = 0.7) -> list[str]:
    """Remove near-duplicate strings from a list before feeding into guidance merge."""
    unique = []
    for item in items:
        is_dup = False
        for existing in unique:
            if _similarity(item, existing) > threshold:
                is_dup = True
                break
        if not is_dup:
            unique.append(item)
    return unique


def _find_unbridged(session_filter: str = None) -> list[tuple[str, str, Path]]:
    """Find day files that haven't been bridged yet.

    Returns list of (session_id, date, path) tuples.
    """
    if not CHATMINE_CLAUDE_DIR.exists():
        return []

    bridge_state = _load_bridge_state()
    unbridged = []

    for session_dir in CHATMINE_CLAUDE_DIR.iterdir():
        if not session_dir.is_dir():
            continue
        sid = session_dir.name
        if session_filter and not sid.startswith(session_filter):
            continue

        sid_state = bridge_state.get(sid, {})

        for day_file in sorted(session_dir.glob("????-??-??.json")):
            day = day_file.stem
            current_mtime = day_file.stat().st_mtime
            bridged_mtime = sid_state.get(day, 0)

            if current_mtime > bridged_mtime:
                unbridged.append((sid, day, day_file))

    return unbridged


def bridge_day_file(day_file: Path) -> dict | None:
    """Transform a chatmine day JSON into digest format for _merge_guidance().

    Returns a digest dict with corrections, decisions, pending keys.
    """
    try:
        with open(day_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # Collect raw items
    raw_decisions = list(data.get("decisions", []))
    raw_bugs = list(data.get("bugs_fixed", []))
    raw_lessons = list(data.get("lessons", []))

    # Pre-dedup within each category
    decisions = _pre_dedup(raw_decisions)
    bugs = _pre_dedup(raw_bugs)
    lessons = _pre_dedup(raw_lessons)

    # Also cross-dedup: bugs that are too similar to decisions
    deduped_bugs = []
    for bug in bugs:
        is_dup = False
        for dec in decisions:
            if _similarity(bug, dec) > 0.6:
                is_dup = True
                break
        if not is_dup:
            deduped_bugs.append(bug)

    # Build digest format
    all_corrections = [
        {"text": lesson, "confidence": CHATMINE_CONFIDENCE, "type": "correction"}
        for lesson in lessons
    ]
    all_decisions = [
        {"text": d, "confidence": CHATMINE_CONFIDENCE, "type": "decision"}
        for d in decisions + deduped_bugs
    ]

    # Intra-session contradiction check: later items override earlier
    clean_corrections, suppressed_c = check_intra_session(all_corrections)
    clean_decisions, suppressed_d = check_intra_session(all_decisions)

    # Filter out items that have been explicitly overridden by user
    clean_corrections = [c for c in clean_corrections if not is_overridden(c.get("text", ""))]
    clean_decisions = [d for d in clean_decisions if not is_overridden(d.get("text", ""))]

    digest = {
        "corrections": clean_corrections,
        "decisions": clean_decisions,
        "pending": [],
        "invariants": [],
    }

    return digest


def run_bridge(session_filter: str = None, recent: int = None,
               dry_run: bool = False, verbose: bool = False) -> dict:
    """Bridge un-bridged chatmine output into guidance.json.

    Returns stats dict.
    """
    unbridged = _find_unbridged(session_filter)

    if not unbridged:
        if verbose:
            print("Nothing to bridge (all up to date)")
        return {"bridged": 0, "skipped": 0}

    # If --recent, sort by modification time and take top N sessions
    if recent:
        # Group by session, find max mtime per session
        session_mtimes = {}
        for sid, day, path in unbridged:
            mt = path.stat().st_mtime
            if sid not in session_mtimes or mt > session_mtimes[sid]:
                session_mtimes[sid] = mt
        top_sessions = sorted(session_mtimes, key=session_mtimes.get, reverse=True)[:recent]
        unbridged = [(s, d, p) for s, d, p in unbridged if s in top_sessions]

    if verbose:
        print(f"Found {len(unbridged)} day files to bridge across "
              f"{len(set(s for s,_,_ in unbridged))} sessions")

    bridge_state = _load_bridge_state()
    stats = {"bridged": 0, "skipped": 0, "items_added": 0,
             "decisions": 0, "corrections": 0, "contradictions_flagged": 0}

    for sid, day, path in unbridged:
        digest = bridge_day_file(path)
        if not digest:
            stats["skipped"] += 1
            continue

        n_decisions = len(digest["decisions"])
        n_corrections = len(digest["corrections"])
        total = n_decisions + n_corrections

        if total == 0:
            stats["skipped"] += 1
            continue

        if verbose:
            print(f"  {sid[:12]} / {day}: {n_decisions} decisions, "
                  f"{n_corrections} corrections")

        if not dry_run:
            # Read current guidance, check for contradictions, then merge
            current = state.read_guidance()
            existing_items = current.get("items", [])

            # Cross-session contradiction check
            all_new = digest.get("corrections", []) + digest.get("decisions", [])
            clean, flagged = check_contradictions(all_new, existing_items, source="chatmine_bridge")

            # Rebuild digest with only clean items
            digest["corrections"] = [i for i in digest["corrections"] if i in clean]
            digest["decisions"] = [i for i in digest["decisions"] if i in clean]

            if flagged and verbose:
                print(f"    ⚠ {len(flagged)} contradictions flagged for review")

            merged = _merge_guidance(current, digest)
            state.write_guidance(merged)

            # Mark as bridged
            if sid not in bridge_state:
                bridge_state[sid] = {}
            bridge_state[sid][day] = path.stat().st_mtime

        stats["bridged"] += 1
        stats["decisions"] += n_decisions
        stats["corrections"] += n_corrections
        stats["items_added"] += total

    if not dry_run:
        _save_bridge_state(bridge_state)

    if verbose:
        print(f"\nBridged {stats['bridged']} day files "
              f"({stats['decisions']} decisions, {stats['corrections']} corrections)")

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bridge chatmine → guidance.json")
    parser.add_argument("--session", type=str, help="Bridge specific session ID (prefix match)")
    parser.add_argument("--recent", type=int, help="Bridge N most recently modified sessions")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be bridged")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    stats = run_bridge(
        session_filter=args.session,
        recent=args.recent,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    if not args.verbose:
        print(json.dumps(stats))
