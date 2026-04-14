#!/opt/homebrew/bin/python3
"""Stop/StopFailure hook — processes session transcript into digest and guidance."""

import datetime
import fcntl
import json
import os
import select
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import state
import llm
from contradiction_detector import check_contradictions, is_overridden

INVARIANT_TTL_DAYS = getattr(config, "INVARIANT_TTL_DAYS", 30)


def _acquire_digest_lock(session_id: str, timeout: float = 30.0):
    """Acquire a per-session digest lock file. Returns fd or None on timeout."""
    lock_path = os.path.join(config.STATE_DIR, f".digest_lock_{session_id[:8]}")
    fd = open(lock_path, "w")
    try:
        # Use non-blocking first, then poll with timeout
        import time
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except (IOError, OSError):
                if time.monotonic() >= deadline:
                    fd.close()
                    return None
                time.sleep(0.1)
    except Exception:
        fd.close()
        return None


def _release_digest_lock(fd):
    """Release and close the digest lock."""
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()
    except Exception:
        pass


def _parse_transcript(path: str, offset: int = 0) -> tuple[list[dict], str, int]:
    """Read JSONL transcript from offset, return (messages, combined_text, new_offset).

    Each JSONL line has: type (user/assistant/system), message/content fields.
    """
    messages = []
    lines_text = []

    try:
        with open(path, "r") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                role = entry.get("type", "unknown")
                content = entry.get("message") or entry.get("content") or ""
                if isinstance(content, dict):
                    content = content.get("text", str(content))

                messages.append({"role": role, "content": str(content)})
                lines_text.append(f"[{role}] {content}")

            new_offset = f.tell()
    except (FileNotFoundError, OSError):
        return [], "", offset

    combined = "\n".join(lines_text)
    return messages, combined, new_offset


def _similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity for deduplication."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / max(len(words_a), len(words_b))


def _merge_guidance(current_guidance: dict, digest: dict) -> dict:
    """Merge digest extractions into existing guidance.

    - Add new corrections, decisions, pending items
    - Mark pending items as resolved if they appear in decisions
    - Prune items older than 7 days
    - Deduplicate (skip items with very similar text)
    """
    items = list(current_guidance.get("items", []))
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Type-aware TTL defaults (days)
    TTL_BY_TYPE = {
        "correction": 90,   # corrections persist — they're authoritative user statements
        "invariant": INVARIANT_TTL_DAYS,  # 30 days, refreshed on reinforcement
        "decision": 14,      # decisions go stale in ~2 weeks
        "context": 7,        # context is ephemeral
        "pending": 3,        # pending items are urgent or irrelevant
    }

    # Collect new items from digest
    new_items = []
    for correction in digest.get("corrections", []):
        new_items.append({
            "type": "correction",
            "text": correction.get("text", ""),
            "confidence": correction.get("confidence", 0.5),
            "created_at": now,
            "ttl_days": TTL_BY_TYPE["correction"],
        })
    for decision in digest.get("decisions", []):
        new_items.append({
            "type": "decision",
            "text": decision.get("text", ""),
            "confidence": decision.get("confidence", 0.5),
            "created_at": now,
            "ttl_days": TTL_BY_TYPE["decision"],
        })
    for pending in digest.get("pending", []):
        new_items.append({
            "type": "pending",
            "text": pending.get("text", ""),
            "confidence": pending.get("confidence", 0.5),
            "created_at": now,
            "ttl_days": TTL_BY_TYPE["pending"],
        })

    # Mark pending items as resolved if they appear in decisions
    decision_texts = [d.get("text", "") for d in digest.get("decisions", [])]
    if decision_texts:
        resolved = set()
        for i, item in enumerate(items):
            if item.get("type") == "pending":
                for dt in decision_texts:
                    if _similarity(item.get("text", ""), dt) > 0.5:
                        resolved.add(i)
                        break
        items = [item for i, item in enumerate(items) if i not in resolved]

    # Contradiction check: flag items that conflict with existing guidance
    try:
        clean_new, flagged_new = check_contradictions(new_items, items, source="digest")
    except Exception:
        clean_new, flagged_new = new_items, []

    # Filter out overridden items
    clean_new = [i for i in clean_new if not is_overridden(i.get("text", ""))]

    # Deduplicate: skip new items too similar to existing ones
    for new_item in clean_new:
        is_dup = False
        for existing in items:
            if _similarity(new_item.get("text", ""), existing.get("text", "")) > 0.7:
                is_dup = True
                break
        if not is_dup:
            items.append(new_item)

    # Merge invariants (MemCollab enforce/avoid pairs)
    for inv in digest.get("invariants", []):
        inv_text = f"When {inv.get('context', '')}: enforce {inv.get('enforce', '')}; avoid {inv.get('avoid', '')}"
        inv_item = {
            "type": "invariant",
            "context": inv.get("context", ""),
            "enforce": inv.get("enforce", ""),
            "avoid": inv.get("avoid", ""),
            "text": inv_text,  # backward compat
            "confidence": inv.get("confidence", 0.85),
            "source": inv.get("source", "single"),
            "created_at": now,
            "ttl_days": INVARIANT_TTL_DAYS,
        }
        # Dedup invariants: use combined text for broader matching,
        # or context-only for high overlap (same topic, different wording)
        is_dup = False
        for existing in items:
            if existing.get("type") == "invariant":
                ctx_sim = _similarity(inv_item.get("context", ""), existing.get("context", ""))
                text_sim = _similarity(inv_text, existing.get("text", ""))
                if ctx_sim > 0.6 or text_sim > 0.5:
                    # Reinforce: bump confidence of existing invariant
                    existing["confidence"] = min(existing.get("confidence", 0.85) + 0.05, 0.99)
                    existing["created_at"] = now  # refresh TTL
                    is_dup = True
                    break
            elif _similarity(inv_text, existing.get("text", "")) > 0.7:
                is_dup = True
                break
        if not is_dup:
            items.append(inv_item)

    # Prune expired items using per-item TTL (falls back to global max age)
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    default_ttl = config.GUIDANCE_MAX_AGE_DAYS
    pruned = []
    for item in items:
        ts = item.get("created_at", "")
        if ts:
            try:
                item_dt = datetime.datetime.fromisoformat(ts)
                ttl = item.get("ttl_days", TTL_BY_TYPE.get(item.get("type", ""), default_ttl))
                cutoff = now_dt - datetime.timedelta(days=ttl)
                if item_dt < cutoff:
                    continue
            except ValueError:
                pass
        pruned.append(item)

    return {"items": pruned, "updated_at": now}


def main():
    try:
        # Read stdin with 200ms timeout
        ready, _, _ = select.select([sys.stdin], [], [], 0.2)
        if not ready:
            return
        raw = sys.stdin.read()
        if not raw.strip():
            return
        payload = json.loads(raw)
        session_id = payload.get("session_id", "")
        transcript_path = payload.get("transcript_path", "")
        cwd = payload.get("cwd", "")

        if not session_id or not transcript_path:
            return

        # Ensure directories exist
        config.ensure_dirs()

        # Acquire per-session digest lock (30s timeout)
        lock_fd = _acquire_digest_lock(session_id, timeout=30.0)
        if lock_fd is None:
            print("digest: failed to acquire lock", file=sys.stderr)
            return

        try:
            # Get session state for offset
            session = state.get_session(session_id)
            offset = 0
            if session:
                offset = session.get("last_digest_offset", 0)

            # Parse transcript from offset
            messages, transcript_text, new_offset = _parse_transcript(
                transcript_path, offset
            )

            # Skip if transcript is empty or too short
            if not messages or len(transcript_text) < 50:
                return

            # Extract structured data via LLM
            digest = llm.extract_session(transcript_text, messages)

            # Save digest
            state.save_digest(session_id, digest)

            # Merge into guidance
            current_guidance = state.read_guidance()
            merged = _merge_guidance(current_guidance, digest)
            state.write_guidance(merged)

            # Update session offset
            state.update_session(session_id, last_digest_offset=new_offset)

        finally:
            _release_digest_lock(lock_fd)

    except Exception as e:
        print(f"digest: error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
