#!/opt/homebrew/bin/python3
"""Fast heuristic-only digest — skip Ollama, process transcripts directly.

Usage: /opt/homebrew/bin/python3 fast_digest.py <session_id1> <session_id2> ...

Reads transcripts from ~/.claude/projects/, extracts corrections/pending/summary
using keyword heuristics only (no LLM). Writes digests + merges guidance.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import state

TRANSCRIPTS_DIR = Path.home() / ".claude/projects/-Users-dana--openclaw-workspace"

_CORRECTION_WORDS = re.compile(
    r"\b(no|wrong|not that|don't|stop|didn't|isn't|won't|can't|shouldn't|"
    r"that's not|fix this|broken|failed|error|rejected|denied)\b", re.IGNORECASE
)

_DECISION_WORDS = re.compile(
    r"\b(decided|let's go with|use this|correct approach|the plan is|"
    r"we'll use|going forward|from now on|always|never)\b", re.IGNORECASE
)

_PENDING_WORDS = re.compile(
    r"\b(todo|still need|next step|later|haven't|pending|remaining|"
    r"not yet|come back to|follow up|unfinished)\b", re.IGNORECASE
)


def _normalize(text: str, max_len: int = 200) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] + "..." if len(text) > max_len else text


def _extract_content(entry: dict) -> str:
    content = entry.get("message") or entry.get("content") or ""
    if isinstance(content, dict):
        return content.get("text", str(content))
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                t = block.get("text", block.get("content", ""))
                if t and isinstance(t, str) and len(t) > 5:
                    parts.append(t)
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return str(content)


def parse_and_extract(session_id: str) -> dict:
    path = TRANSCRIPTS_DIR / f"{session_id}.jsonl"
    if not path.exists():
        return {}

    user_msgs = []
    assistant_msgs = []

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = entry.get("type", "unknown")
            content = _extract_content(entry)
            if not content or len(content) < 3:
                continue
            if role == "user":
                user_msgs.append(content)
            elif role == "assistant":
                assistant_msgs.append(content)

    if not user_msgs:
        return {}

    # Extract corrections (user messages with correction words)
    corrections = []
    for msg in user_msgs:
        if _CORRECTION_WORDS.search(msg) and len(msg) > 10:
            corrections.append({
                "text": _normalize(msg),
                "confidence": 0.4,
                "source": "heuristic",
            })

    # Extract decisions (assistant messages with decision words)
    decisions = []
    for msg in assistant_msgs[-20:]:  # last 20 assistant msgs
        if _DECISION_WORDS.search(msg) and len(msg) > 20:
            decisions.append({
                "text": _normalize(msg),
                "confidence": 0.3,
                "source": "heuristic",
            })

    # Pending: last few user messages that mention pending work
    pending = []
    for msg in user_msgs[-5:]:
        if _PENDING_WORDS.search(msg):
            pending.append({
                "text": _normalize(msg),
                "confidence": 0.3,
                "source": "heuristic",
            })
    # Always add last user msg as pending context
    if user_msgs:
        pending.append({
            "text": _normalize(user_msgs[-1]),
            "confidence": 0.3,
            "source": "heuristic",
        })

    # Summary: first + last user message
    first = _normalize(user_msgs[0], 100)
    last = _normalize(user_msgs[-1], 100)
    summary_text = f"{first} ... {last}" if len(user_msgs) > 1 else first

    return {
        "corrections": corrections[:30],  # cap to avoid bloat
        "decisions": decisions[:10],
        "pending": pending[:5],
        "summary": {"text": summary_text, "confidence": 0.4, "source": "heuristic"},
    }


def _similarity(a: str, b: str) -> float:
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / max(len(words_a), len(words_b))


def _merge_guidance(current: dict, digest: dict) -> dict:
    import datetime
    items = list(current.get("items", []))
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    new_items = []
    for cat in ("corrections", "decisions", "pending"):
        for item in digest.get(cat, []):
            new_items.append({
                "type": cat.rstrip("s") if cat != "pending" else "pending",
                "text": item.get("text", ""),
                "confidence": item.get("confidence", 0.3),
                "created_at": now,
            })

    # Dedup
    for new_item in new_items:
        is_dup = any(
            _similarity(new_item["text"], ex.get("text", "")) > 0.7
            for ex in items
        )
        if not is_dup:
            items.append(new_item)

    # Prune > 7 days
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
    pruned = []
    for item in items:
        ts = item.get("created_at", "")
        if ts:
            try:
                if datetime.datetime.fromisoformat(ts) < cutoff:
                    continue
            except ValueError:
                pass
        pruned.append(item)

    return {"items": pruned, "updated_at": now}


def main():
    session_ids = sys.argv[1:]
    if not session_ids:
        print("Usage: fast_digest.py <session_id1> [session_id2] ...")
        sys.exit(1)

    config.ensure_dirs()
    processed = 0

    for sid in session_ids:
        size_kb = 0
        path = TRANSCRIPTS_DIR / f"{sid}.jsonl"
        if path.exists():
            size_kb = path.stat().st_size // 1024

        print(f"  {sid[:8]} ({size_kb}KB)...", end=" ", flush=True)
        try:
            digest = parse_and_extract(sid)
            if not digest:
                print("empty")
                continue

            state.save_digest(sid, digest)

            current_guidance = state.read_guidance()
            merged = _merge_guidance(current_guidance, digest)
            state.write_guidance(merged)

            if not state.get_session(sid):
                state.register_session(sid, str(config.WORKSPACE))

            nc = len(digest.get("corrections", []))
            np_ = len(digest.get("pending", []))
            summary = digest.get("summary", {}).get("text", "")[:60]
            print(f"OK c={nc} p={np_} | {summary}")
            processed += 1
        except Exception as e:
            print(f"FAIL: {e}")

    print(f"\nDone: {processed}/{len(session_ids)}")


if __name__ == "__main__":
    main()
