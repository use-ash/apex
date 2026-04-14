#!/opt/homebrew/bin/python3
"""Whisper feedback loop — evaluate whether injected guidance was useful.

Closes the open loop in whisper injection by scoring each injected item
against the model's actual response. Over time, items that are never
useful get deprioritized; items that consistently help get boosted.

Architecture:
  log_injection()  → pending_{chat_id}.json   (called after whisper injects)
  evaluate_turn()  → evaluations.jsonl         (called on next turn)
  rebuild_index()  → index.json                (called nightly by autodream)
  get_adjustment() ← index.json                (called by relevance scorer)

Data lives in .subconscious/whisper_feedback/

This module is designed to be import-safe: no dependency on the
subconscious config/state modules (which collide with server modules
when loaded from context.py).
"""

import datetime
import hashlib
import json
import os
import re
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution (self-contained, no config.py dependency)
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent

# When loaded from context.py, the loader injects the correct workspace
# state dir (since __file__ follows symlinks and may resolve to apex/ instead
# of workspace/ where the actual state lives).
_WS_STATE_DIR: str | None = None  # set by _load_whisper_feedback() in context.py


def _resolve_default_state_dir() -> str:
    """Find the .subconscious dir that actually has state files."""
    # Check workspace first (most common), then apex, then file-relative
    candidates = [
        Path.home() / ".openclaw" / "workspace" / ".subconscious",
        _THIS_DIR.parents[1] / ".subconscious",
    ]
    for c in candidates:
        if c.is_dir() and (c / "guidance.json").exists():
            return str(c)
    # Fallback: create under workspace
    return str(candidates[0])


def _feedback_dir(state_dir: str | None = None) -> str:
    d = os.path.join(
        state_dir or _WS_STATE_DIR or _resolve_default_state_dir(),
        "whisper_feedback",
    )
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USEFUL_THRESHOLD = 0.15      # keyword overlap ratio to count as "useful"
MIN_INJECTIONS_FOR_ADJ = 5   # need N evaluations before adjusting scores
INDEX_CACHE_TTL = 60          # seconds to cache the index in memory

# Stopwords for tokenization (shared with adapters/apex.py)
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "about",
    "between", "through", "during", "before", "after", "above", "below",
    "up", "down", "out", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how",
    "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same", "so",
    "than", "too", "very", "just", "because", "but", "and", "or",
    "if", "while", "that", "this", "what", "which", "who", "whom",
    "it", "its", "i", "me", "my", "we", "our", "you", "your",
    "he", "him", "his", "she", "her", "they", "them", "their",
})

# Structural words in whisper format that should not count as content overlap
_STRUCTURAL_WORDS = frozenset({
    "invariant", "correction", "note", "warning", "attention",
    "enforce", "avoid", "when", "using", "use",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _item_hash(text: str) -> str:
    """Stable hash for a guidance item's text content."""
    return hashlib.md5(text.strip().encode()).hexdigest()[:12]


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens, stopwords and structural words removed."""
    raw = set(re.findall(r"[a-z0-9_]+", text.lower()))
    return raw - _STOPWORDS - _STRUCTURAL_WORDS


# ---------------------------------------------------------------------------
# Injection logging
# ---------------------------------------------------------------------------

def log_injection(chat_id: str, items: list[dict],
                  state_dir: str | None = None) -> None:
    """Log which items were injected for a given chat turn.

    Overwrites the pending file for this chat (only need the most recent).

    Args:
        chat_id: The chat/session ID
        items: list of dicts with keys:
            - text: the item text (up to 500 chars)
            - type: "guidance" or "embedding"
            - source: "guidance" or "embedding"
            - relevance_score: float (optional)
    """
    fd = _feedback_dir(state_dir)
    entry = {
        "chat_id": chat_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "evaluated": False,
        "items": [
            {
                "hash": _item_hash(item.get("text", "")),
                "type": item.get("type", "unknown"),
                "text": item.get("text", "")[:500],
                "relevance_score": item.get("relevance_score", 0),
                "source": item.get("source", "guidance"),
            }
            for item in items
            if item.get("text", "").strip()
        ],
    }
    if not entry["items"]:
        return

    path = os.path.join(fd, f"pending_{chat_id[:16]}.json")
    with open(path, "w") as f:
        json.dump(entry, f, indent=2)


# ---------------------------------------------------------------------------
# Turn evaluation
# ---------------------------------------------------------------------------

def evaluate_turn(chat_id: str, response_text: str,
                  state_dir: str | None = None) -> list[dict] | None:
    """Evaluate the most recent injection against the model's response.

    Called on the NEXT user turn (when the previous assistant response
    is available). Uses keyword overlap as the evaluation signal.

    Returns list of per-item evaluation results, or None if nothing to evaluate.
    """
    if not response_text or len(response_text) < 20:
        return None

    fd = _feedback_dir(state_dir)
    path = os.path.join(fd, f"pending_{chat_id[:16]}.json")

    if not os.path.exists(path):
        return None

    try:
        with open(path) as f:
            injection = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if injection.get("evaluated"):
        return None

    items = injection.get("items", [])
    if not items:
        return None

    # Tokenize the model's response
    response_tokens = _tokenize(response_text)
    if not response_tokens:
        return None

    # Evaluate each injected item
    results = []
    for item in items:
        item_text = item.get("text", "")
        item_tokens = _tokenize(item_text)

        if not item_tokens:
            results.append({
                "hash": item.get("hash", ""),
                "was_useful": False,
                "method": "keyword_overlap",
                "overlap_score": 0.0,
                "overlapping_tokens": [],
            })
            continue

        overlap = response_tokens & item_tokens
        # Normalize by item token count: "did the response reference
        # this item's concepts?"
        overlap_ratio = len(overlap) / len(item_tokens)

        results.append({
            "hash": item.get("hash", ""),
            "text_preview": item_text[:100],
            "was_useful": overlap_ratio >= USEFUL_THRESHOLD,
            "method": "keyword_overlap",
            "overlap_score": round(overlap_ratio, 4),
            "overlapping_tokens": sorted(list(overlap))[:15],
        })

    # Mark pending as evaluated (prevents double-evaluation)
    injection["evaluated"] = True
    injection["eval_timestamp"] = datetime.datetime.now(
        datetime.timezone.utc).isoformat()
    try:
        with open(path, "w") as f:
            json.dump(injection, f, indent=2)
    except OSError:
        pass

    # Append to evaluations log (append-only, for aggregation)
    eval_entry = {
        "chat_id": chat_id,
        "injection_ts": injection.get("timestamp", ""),
        "eval_ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "response_len": len(response_text),
        "items": results,
    }
    eval_path = os.path.join(fd, "evaluations.jsonl")
    try:
        with open(eval_path, "a") as f:
            f.write(json.dumps(eval_entry) + "\n")
    except OSError:
        pass

    return results


# ---------------------------------------------------------------------------
# Index aggregation (nightly via autodream)
# ---------------------------------------------------------------------------

def rebuild_index(state_dir: str | None = None) -> dict:
    """Aggregate evaluations into per-item hit rate index.

    Called nightly by autodream or on-demand via CLI.
    Returns the index dict and writes to index.json.
    """
    fd = _feedback_dir(state_dir)
    eval_path = os.path.join(fd, "evaluations.jsonl")

    if not os.path.exists(eval_path):
        return {"items": {}, "rebuilt_at": "", "total_evaluations": 0}

    # Aggregate per item hash
    stats: dict[str, dict] = {}
    total_entries = 0

    try:
        with open(eval_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    total_entries += 1
                    for item in entry.get("items", []):
                        h = item.get("hash", "")
                        if not h:
                            continue
                        if h not in stats:
                            stats[h] = {
                                "text_preview": item.get("text_preview", ""),
                                "total": 0,
                                "useful": 0,
                                "last_useful": None,
                                "overlap_scores": [],
                            }
                        stats[h]["total"] += 1
                        if item.get("was_useful"):
                            stats[h]["useful"] += 1
                            stats[h]["last_useful"] = entry.get("eval_ts")
                        stats[h]["overlap_scores"].append(
                            item.get("overlap_score", 0))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass

    # Build index
    index_items = {}
    for h, s in stats.items():
        scores = s["overlap_scores"]
        index_items[h] = {
            "text_preview": s["text_preview"],
            "total_injections": s["total"],
            "useful_count": s["useful"],
            "hit_rate": round(s["useful"] / s["total"], 3)
            if s["total"] > 0 else 0,
            "avg_overlap": round(sum(scores) / len(scores), 4)
            if scores else 0,
            "last_useful": s["last_useful"],
        }

    index = {
        "items": index_items,
        "rebuilt_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_evaluations": total_entries,
        "total_items_tracked": len(index_items),
    }

    index_path = os.path.join(fd, "index.json")
    try:
        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)
    except OSError:
        pass

    return index


# ---------------------------------------------------------------------------
# Score adjustment (called by relevance scorer)
# ---------------------------------------------------------------------------

_cached_index: dict | None = None
_index_cache_time: float = 0


def get_adjustment(item_text: str, state_dir: str | None = None) -> float:
    """Get score adjustment multiplier based on historical feedback.

    Returns:
        1.0  = no adjustment (default, or insufficient data)
        >1.0 = historically useful, boost (max 1.5)
        <1.0 = historically not useful, penalize (min 0.5)

    Called by adapters/apex.py._relevance_score() during whisper scoring.
    """
    global _cached_index, _index_cache_time

    h = _item_hash(item_text)
    fd = _feedback_dir(state_dir)
    index_path = os.path.join(fd, "index.json")

    # Cache the index in memory (re-read every INDEX_CACHE_TTL seconds)
    now = time.time()
    if _cached_index is None or (now - _index_cache_time) > INDEX_CACHE_TTL:
        if not os.path.exists(index_path):
            return 1.0
        try:
            with open(index_path) as f:
                _cached_index = json.load(f)
            _index_cache_time = now
        except (json.JSONDecodeError, OSError):
            return 1.0

    item_stats = _cached_index.get("items", {}).get(h)
    if not item_stats:
        return 1.0  # no data yet, neutral

    total = item_stats.get("total_injections", 0)
    if total < MIN_INJECTIONS_FOR_ADJ:
        return 1.0  # not enough data to be confident

    hit_rate = item_stats.get("hit_rate", 0.5)

    # Map hit_rate [0, 1] to multiplier [0.5, 1.5]
    # 0% hit rate  -> 0.5x (halve score, don't zero it)
    # 50% hit rate -> 1.0x (neutral)
    # 100% hit rate -> 1.5x (boost)
    return round(0.5 + hit_rate, 3)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_stats(state_dir: str | None = None):
    fd = _feedback_dir(state_dir)
    index_path = os.path.join(fd, "index.json")

    if not os.path.exists(index_path):
        print("No feedback index yet. Run --rebuild first.")
        return

    with open(index_path) as f:
        index = json.load(f)

    items = index.get("items", {})
    total_evals = index.get("total_evaluations", 0)
    qualified = [v for v in items.values()
                 if v["total_injections"] >= MIN_INJECTIONS_FOR_ADJ]
    hit_rates = [v["hit_rate"] for v in qualified]
    avg_hit = sum(hit_rates) / len(hit_rates) if hit_rates else 0

    print(f"Items tracked:          {len(items)}")
    print(f"Total evaluation turns: {total_evals}")
    print(f"Items with enough data: {len(qualified)}")
    print(f"Average hit rate:       {avg_hit:.1%}")
    print(f"Last rebuilt:           {index.get('rebuilt_at', 'never')}")

    if qualified:
        sorted_q = sorted(qualified, key=lambda x: x["hit_rate"])
        print("\n--- Least useful (bottom 5) ---")
        for item in sorted_q[:5]:
            adj = round(0.5 + item["hit_rate"], 2)
            print(f"  {item['hit_rate']:5.0%} ({item['useful_count']}/{item['total_injections']}) "
                  f"adj={adj}x  {item['text_preview'][:70]}")
        print("\n--- Most useful (top 5) ---")
        for item in sorted_q[-5:]:
            adj = round(0.5 + item["hit_rate"], 2)
            print(f"  {item['hit_rate']:5.0%} ({item['useful_count']}/{item['total_injections']}) "
                  f"adj={adj}x  {item['text_preview'][:70]}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Whisper feedback loop — evaluate and tune guidance injection")
    parser.add_argument("--rebuild", action="store_true",
                        help="Rebuild the feedback index from evaluations")
    parser.add_argument("--stats", action="store_true",
                        help="Show current feedback statistics")
    parser.add_argument("--state-dir", metavar="DIR",
                        help="Override state directory")
    args = parser.parse_args()

    sd = args.state_dir

    if args.rebuild:
        index = rebuild_index(sd)
        n = index.get("total_items_tracked", 0)
        total = index.get("total_evaluations", 0)
        print(f"Index rebuilt: {n} items tracked, {total} evaluation turns")
        _print_stats(sd)
    elif args.stats:
        _print_stats(sd)
    else:
        parser.print_help()
