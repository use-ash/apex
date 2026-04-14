#!/opt/homebrew/bin/python3
"""Contradiction detector for the subconscious memory pipeline.

Detects conflicts between new chatmine/digest extractions and existing
guidance.json items. Flags contradictions for human review instead of
silently merging wrong facts.

Three contradiction types:
  1. intra-session  — same session says X then not-X (e.g., "exited FCX" then "kept FCX")
  2. cross-session  — new extraction contradicts existing guidance item
  3. correction-override — a <memory category="correction"> tag conflicts with extraction

Priority hierarchy (highest → lowest):
  1. User overrides (explicit resolution)
  2. <memory category="correction"> tags (persistent memory)
  3. Later statements in same session
  4. Earlier statements
  5. Cross-session extractions

Usage:
    # Check new items against existing guidance (called from bridge/digest)
    from contradiction_detector import check_contradictions
    flagged = check_contradictions(new_items, existing_items, source="chatmine_bridge")

    # Review pending contradictions
    python3 contradiction_detector.py --list
    python3 contradiction_detector.py --resolve ID --keep a|b|both|neither
    python3 contradiction_detector.py --stats
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config

PENDING_REVIEW_FILE = Path(config.STATE_DIR) / "pending_review.json"
OVERRIDES_FILE = Path(config.STATE_DIR) / "overrides.json"

# Similarity thresholds
TOPIC_SIMILARITY_THRESHOLD = 0.25   # items about the same topic (lowered from 0.45 — real-world FCX case has 0.31)
ENTITY_BOOST = 0.20                 # bonus when both texts share a named entity (ticker, filename, etc.)

# Patterns for named entity extraction (tickers, filenames, function names)
_ENTITY_PATTERN = re.compile(
    r'\b[A-Z]{2,5}\b'              # stock tickers (FCX, BAC, GE, etc.)
    r'|(?:\w+\.(?:py|js|ts|md))'   # filenames
    r'|(?:_\w{4,})'               # underscore-prefixed identifiers
)


def _similarity(a: str, b: str) -> float:
    """Word-overlap similarity (same as digest.py)."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / max(len(words_a), len(words_b))


def _entity_boosted_similarity(a: str, b: str) -> float:
    """Word-overlap similarity with a boost when shared named entities are found.

    Two texts mentioning the same ticker (FCX), filename, or function are
    likely about the same topic even if phrased very differently.
    """
    base_sim = _similarity(a, b)
    entities_a = set(_ENTITY_PATTERN.findall(a))
    entities_b = set(_ENTITY_PATTERN.findall(b))
    shared_entities = entities_a & entities_b
    if shared_entities:
        # Boost proportional to how many entities overlap
        boost = min(len(shared_entities) * ENTITY_BOOST, 0.40)
        return min(base_sim + boost, 1.0)
    return base_sim


def _item_text(item: dict) -> str:
    """Extract readable text from a guidance item."""
    if item.get("type") == "invariant":
        return item.get("text", f"When {item.get('context','')}: {item.get('enforce','')}")
    return item.get("text", "")


def _make_id(text_a: str, text_b: str) -> str:
    """Deterministic short ID from two texts."""
    combined = f"{text_a}||{text_b}"
    return hashlib.sha256(combined.encode()).hexdigest()[:12]


def _has_negation_flip(text_a: str, text_b: str) -> bool:
    """Detect if two similar texts have opposing assertions.

    Checks for:
    1. Negation asymmetry (one text negates, the other doesn't)
    2. Opposing action verbs (kept vs exited, open vs closed)
    3. "not X" patterns where X is an action verb in the other text
    """
    lower_a = text_a.lower()
    lower_b = text_b.lower()
    words_a = set(lower_a.split())
    words_b = set(lower_b.split())

    # Check for negation asymmetry
    neg_words = {"not", "no", "never", "don't", "didn't", "doesn't",
                 "wasn't", "weren't", "isn't", "can't", "won't"}
    neg_in_a = bool(words_a & neg_words)
    neg_in_b = bool(words_b & neg_words)
    if neg_in_a != neg_in_b:
        return True

    # Check for opposing action pairs
    opposites = [
        ("kept", "exited"), ("kept", "sold"), ("kept", "closed"),
        ("open", "closed"), ("entered", "exited"),
        ("bought", "sold"), ("added", "removed"),
        ("enabled", "disabled"), ("true", "false"),
        ("maintained", "exited"), ("maintained", "closed"),
        ("held", "sold"), ("held", "exited"),
        ("open", "exited"), ("open", "sold"),
        ("still", "exited"), ("still", "sold"), ("still", "closed"),
    ]
    for w1, w2 in opposites:
        if (w1 in words_a and w2 in words_b) or (w2 in words_a and w1 in words_b):
            return True

    # Check for "not <verb>" in one text where <verb> appears un-negated in other
    action_verbs = {"sold", "exited", "closed", "removed", "disabled", "cut",
                    "bought", "entered", "opened", "added", "enabled", "kept"}
    not_pattern = re.compile(r'\bnot\s+(\w+)')
    for negated in not_pattern.findall(lower_a):
        if negated in action_verbs and negated in words_b:
            return True
    for negated in not_pattern.findall(lower_b):
        if negated in action_verbs and negated in words_a:
            return True

    return False


def _load_pending() -> list[dict]:
    """Load pending contradictions."""
    try:
        with open(PENDING_REVIEW_FILE) as f:
            data = json.load(f)
            return data.get("contradictions", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_pending(items: list[dict]) -> None:
    """Save pending contradictions atomically."""
    data = {
        "contradictions": items,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    tmp = str(PENDING_REVIEW_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.rename(tmp, str(PENDING_REVIEW_FILE))


def _load_overrides() -> list[dict]:
    """Load user-resolved overrides."""
    try:
        with open(OVERRIDES_FILE) as f:
            data = json.load(f)
            return data.get("overrides", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_overrides(items: list[dict]) -> None:
    """Save overrides atomically."""
    data = {
        "overrides": items,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    tmp = str(OVERRIDES_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.rename(tmp, str(OVERRIDES_FILE))


def is_overridden(item_text: str) -> bool:
    """Check if an item has been explicitly overridden (suppressed) by user."""
    overrides = _load_overrides()
    for override in overrides:
        suppressed = override.get("suppressed_text", "")
        if suppressed and _similarity(item_text, suppressed) > 0.6:
            return True
    return False


def check_contradictions(
    new_items: list[dict],
    existing_items: list[dict],
    source: str = "unknown",
) -> tuple[list[dict], list[dict]]:
    """Check new items against existing guidance for contradictions.

    Args:
        new_items: Items about to be merged into guidance
        existing_items: Current guidance items
        source: Origin label (e.g., "chatmine_bridge", "digest")

    Returns:
        (clean_items, flagged_items) — clean pass through, flagged go to pending_review
    """
    clean = []
    flagged = []
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    pending = _load_pending()
    existing_ids = {c.get("id") for c in pending}

    for new_item in new_items:
        new_text = _item_text(new_item)
        if not new_text.strip():
            continue

        # Skip if this item was already overridden/suppressed
        if is_overridden(new_text):
            continue

        found_contradiction = False

        for existing in existing_items:
            existing_text = _item_text(existing)
            if not existing_text.strip():
                continue

            sim = _entity_boosted_similarity(new_text, existing_text)

            # High similarity = same topic. Check for opposing assertions.
            if sim > TOPIC_SIMILARITY_THRESHOLD and _has_negation_flip(new_text, existing_text):
                cid = _make_id(new_text, existing_text)

                # Skip if already flagged
                if cid in existing_ids:
                    found_contradiction = True
                    break

                contradiction = {
                    "id": cid,
                    "type": "cross_session" if source == "chatmine_bridge" else "merge_conflict",
                    "source": source,
                    "claim_a": {
                        "text": existing_text,
                        "item_type": existing.get("type", "unknown"),
                        "confidence": existing.get("confidence", 0),
                        "created_at": existing.get("created_at", ""),
                    },
                    "claim_b": {
                        "text": new_text,
                        "item_type": new_item.get("type", "unknown"),
                        "confidence": new_item.get("confidence", 0),
                    },
                    "similarity": round(sim, 3),
                    "flagged_at": now,
                    "status": "pending",
                    "resolution": None,
                }
                pending.append(contradiction)
                existing_ids.add(cid)
                flagged.append(new_item)
                found_contradiction = True
                break

        if not found_contradiction:
            clean.append(new_item)

    # Save updated pending list
    if flagged:
        _save_pending(pending)

    return clean, flagged


def check_intra_session(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Check for contradictions within a single extraction batch.

    Later items override earlier ones (temporal priority).
    Returns (survivors, suppressed).
    """
    survivors = []
    suppressed = []

    for i, item in enumerate(items):
        text_i = _item_text(item) if isinstance(item, dict) else str(item)
        is_contradicted = False

        # Check against all LATER items (later = higher authority)
        for j in range(i + 1, len(items)):
            text_j = _item_text(items[j]) if isinstance(items[j], dict) else str(items[j])
            sim = _entity_boosted_similarity(text_i, text_j)
            if sim > TOPIC_SIMILARITY_THRESHOLD and _has_negation_flip(text_i, text_j):
                is_contradicted = True
                suppressed.append(item)
                break

        if not is_contradicted:
            survivors.append(item)

    return survivors, suppressed


def resolve(contradiction_id: str, keep: str, notes: str = "") -> bool:
    """Resolve a flagged contradiction.

    Args:
        contradiction_id: The 'id' field from pending_review.json
        keep: One of 'a' (keep existing), 'b' (keep new), 'both', 'neither'
        notes: Optional resolution notes

    Returns True if found and resolved.
    """
    pending = _load_pending()
    overrides = _load_overrides()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    found = None
    remaining = []
    for item in pending:
        if item.get("id") == contradiction_id:
            found = item
        else:
            remaining.append(item)

    if not found:
        return False

    # Create override record
    override = {
        "id": contradiction_id,
        "resolution": keep,
        "notes": notes,
        "resolved_at": now,
        "claim_a": found.get("claim_a", {}),
        "claim_b": found.get("claim_b", {}),
    }

    # Determine what gets suppressed
    if keep == "a":
        override["suppressed_text"] = found.get("claim_b", {}).get("text", "")
        override["kept_text"] = found.get("claim_a", {}).get("text", "")
    elif keep == "b":
        override["suppressed_text"] = found.get("claim_a", {}).get("text", "")
        override["kept_text"] = found.get("claim_b", {}).get("text", "")
    elif keep == "neither":
        # Suppress both — save two override entries
        override["suppressed_text"] = found.get("claim_a", {}).get("text", "")
        override2 = dict(override)
        override2["suppressed_text"] = found.get("claim_b", {}).get("text", "")
        overrides.append(override2)
    # keep == "both" — no suppression needed, just dismiss the flag

    overrides.append(override)
    _save_overrides(overrides)
    _save_pending(remaining)
    return True


def list_pending(verbose: bool = False) -> list[dict]:
    """List all pending contradictions."""
    pending = _load_pending()
    active = [c for c in pending if c.get("status") == "pending"]
    if verbose:
        for c in active:
            print(f"\n{'='*60}")
            print(f"ID: {c['id']}")
            print(f"Type: {c.get('type', '?')}  Source: {c.get('source', '?')}")
            print(f"Similarity: {c.get('similarity', '?')}")
            print(f"Flagged: {c.get('flagged_at', '?')}")
            print(f"\n  [A] {c.get('claim_a', {}).get('text', '?')}")
            print(f"      type={c.get('claim_a', {}).get('item_type', '?')} "
                  f"conf={c.get('claim_a', {}).get('confidence', '?')}")
            print(f"\n  [B] {c.get('claim_b', {}).get('text', '?')}")
            print(f"      type={c.get('claim_b', {}).get('item_type', '?')} "
                  f"conf={c.get('claim_b', {}).get('confidence', '?')}")
        if not active:
            print("No pending contradictions.")
    return active


def stats() -> dict:
    """Return summary stats."""
    pending = _load_pending()
    overrides = _load_overrides()
    active = [c for c in pending if c.get("status") == "pending"]
    return {
        "pending": len(active),
        "total_flagged": len(pending),
        "overrides": len(overrides),
        "by_type": {},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Contradiction detector for subconscious pipeline")
    parser.add_argument("--list", action="store_true", help="List pending contradictions")
    parser.add_argument("--resolve", type=str, metavar="ID", help="Resolve a contradiction by ID")
    parser.add_argument("--keep", choices=["a", "b", "both", "neither"],
                        help="Which claim to keep (used with --resolve)")
    parser.add_argument("--notes", type=str, default="", help="Resolution notes")
    parser.add_argument("--stats", action="store_true", help="Show summary statistics")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.list:
        list_pending(verbose=True)
    elif args.resolve:
        if not args.keep:
            print("--keep is required with --resolve (a, b, both, neither)")
            sys.exit(1)
        ok = resolve(args.resolve, args.keep, args.notes)
        if ok:
            print(f"Resolved {args.resolve} → keep {args.keep}")
        else:
            print(f"Contradiction {args.resolve} not found")
            sys.exit(1)
    elif args.stats:
        s = stats()
        print(json.dumps(s, indent=2))
    else:
        parser.print_help()
