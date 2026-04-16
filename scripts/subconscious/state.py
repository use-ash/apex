"""State management for the subconscious memory system.
File-based locking and CRUD for sessions, guidance, and digests.
"""
import contextlib
import datetime
import fcntl
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    DIGESTS_DIR, GUIDANCE_FILE, GUIDANCE_MAX_AGE_DAYS,
    GUIDANCE_MAX_CHARS, LOCK_FILE, SESSIONS_DIR, STATE_DIR,
)


def _read_json(path) -> dict | list | None:
    """Read JSON file, return None on missing/corrupt."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

def _atomic_write(path, data) -> None:
    """Write JSON to temp file then os.rename (atomic on same filesystem)."""
    tmp = str(path) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.rename(tmp, path)

@contextlib.contextmanager
def _lock():
    """Acquire file lock using fcntl.flock, yield, release."""
    os.makedirs(STATE_DIR, exist_ok=True)
    fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


def register_session(session_id: str, cwd: str = "") -> dict:
    """Create a new session file."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    session = {
        "session_id": session_id, "cwd": cwd,
        "started_at": now, "last_prompt_at": now,
        "last_digest_offset": 0,
    }
    _atomic_write(os.path.join(SESSIONS_DIR, f"{session_id}.json"), session)
    return session

def get_session(session_id: str) -> dict | None:
    """Read session file."""
    return _read_json(os.path.join(SESSIONS_DIR, f"{session_id}.json"))

def update_session(session_id: str, **kwargs) -> None:
    """Merge kwargs into session file, atomic write."""
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    session = _read_json(path)
    if session is None:
        return
    session.update(kwargs)
    _atomic_write(path, session)

def list_recent_sessions(limit: int = 5) -> list[dict]:
    """List all session files, sort by started_at descending, return top N."""
    sessions = []
    d = Path(SESSIONS_DIR)
    if not d.exists():
        return []
    for p in d.glob("*.json"):
        data = _read_json(p)
        if data:
            sessions.append(data)
    sessions.sort(key=lambda s: s.get("started_at", ""), reverse=True)
    return sessions[:limit]


def _migrate_item(item: dict) -> dict:
    """Ensure item has Type 1/Type 2 pathway fields (transparent migration).

    New fields (defaults):
      - pathway: "type1" for invariants/corrections, "type2" for everything else
      - injection_count: 0
      - promotion_score: 0.0

    Existing guidance.json loads without manual editing — fields are added
    on read, written back on next write_guidance() call.
    """
    if "pathway" not in item:
        itype = item.get("type", "")
        if itype in ("invariant", "correction"):
            item["pathway"] = "type1"
        else:
            item["pathway"] = "type2"
    if "injection_count" not in item:
        item["injection_count"] = 0
    if "promotion_score" not in item:
        item["promotion_score"] = 0.0
    return item


def read_guidance() -> dict:
    """Read guidance, pruning items by per-type TTL.

    Invariants use their own ttl_days (default 30), other types use GUIDANCE_MAX_AGE_DAYS (7).
    Items are transparently migrated to include Type 1/Type 2 pathway fields.
    """
    with _lock():
        data = _read_json(GUIDANCE_FILE)
        if not data or "items" not in data:
            return {"items": [], "updated_at": ""}
        now = datetime.datetime.now(datetime.timezone.utc)
        pruned = []
        for item in data["items"]:
            ts = item.get("created_at", "")
            if ts:
                try:
                    item_dt = datetime.datetime.fromisoformat(ts)
                    ttl = item.get("ttl_days", GUIDANCE_MAX_AGE_DAYS)
                    cutoff = now - datetime.timedelta(days=ttl)
                    if item_dt < cutoff:
                        continue
                except ValueError:
                    pass
            pruned.append(_migrate_item(item))
        data["items"] = pruned
        return data

def _item_text_len(item: dict) -> int:
    """Total text length of a guidance item (handles both flat and structured).

    For invariants: counts context+enforce+avoid AND the redundant text field
    (since both are serialized to JSON and injected into prompts).
    """
    if item.get("type") == "invariant":
        structured = sum(len(item.get(k, "")) for k in ("context", "enforce", "avoid"))
        # The 'text' field is a backward-compat composite; count it if present
        text_field = len(item.get("text", ""))
        return structured + text_field
    return len(item.get("text", ""))


def write_guidance(guidance: dict) -> None:
    """Truncate items if total chars > GUIDANCE_MAX_CHARS.

    Prioritizes invariants (trim corrections/decisions first).
    """
    with _lock():
        items = guidance.get("items", [])
        total = sum(_item_text_len(i) for i in items)
        if total > GUIDANCE_MAX_CHARS:
            # Sort: invariants last (protected), then by created_at ascending (oldest first)
            non_invariants = [i for i in items if i.get("type") != "invariant"]
            invariants = [i for i in items if i.get("type") == "invariant"]
            # Trim oldest non-invariants first
            while total > GUIDANCE_MAX_CHARS and non_invariants:
                total -= _item_text_len(non_invariants.pop(0))
            # If still over, trim oldest invariants
            while total > GUIDANCE_MAX_CHARS and invariants:
                total -= _item_text_len(invariants.pop(0))
            items = non_invariants + invariants
            guidance["items"] = items
        guidance["updated_at"] = datetime.datetime.now(
            datetime.timezone.utc).isoformat()
        _atomic_write(GUIDANCE_FILE, guidance)

def save_digest(session_id: str, digest: dict) -> None:
    """Write digest to DIGESTS_DIR/{session_id}.json."""
    os.makedirs(DIGESTS_DIR, exist_ok=True)
    _atomic_write(os.path.join(DIGESTS_DIR, f"{session_id}.json"), digest)

def load_digest(session_id: str) -> dict | None:
    """Read digest file."""
    return _read_json(os.path.join(DIGESTS_DIR, f"{session_id}.json"))
