"""Apex adapter — translates ContextEnvelope into Apex whisper format.

Apex context injection:
  1. context.py._get_whisper_text() — embedding-based semantic search
     whispered into system messages on each user prompt
  2. context.py._build_system_prompt() — persona/instructions at session start

This adapter provides:
  - Canonical guidance items formatted for Apex's <subconscious_whisper> blocks
  - Merging logic: canonical guidance + embedding results = unified whisper

The key difference from Claude Code / Codex: Apex has its OWN embedding-based
memory search (memory_search.py). The canonical store provides the GUIDANCE
layer (invariants, corrections) while Apex's embeddings provide the MEMORY
layer (relevant past context). This adapter merges both.
"""

import datetime
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from canonical_store import ContextEnvelope, Memory


# Apex whisper budget is tighter — it fires every prompt
WHISPER_BUDGET = 3000  # chars


# ---------------------------------------------------------------------------
# Date-anchor refresh — rewrite TODAY=YYYY-MM-DD literals to the live date
# at emission time so stale invariants don't leak frozen anchors into the
# model's context. See whisper.py for the same fix on the hook-side path.
# ---------------------------------------------------------------------------

_DATE_LITERAL_RE = re.compile(r"\b(?:TODAY|today)\s*=\s*\d{4}-\d{2}-\d{2}\b")


def _refresh_today(text: str) -> str:
    if not text:
        return text
    return _DATE_LITERAL_RE.sub(
        f"TODAY={datetime.date.today().isoformat()}", text
    )


# ---------------------------------------------------------------------------
# Relevance scoring — match guidance items to current conversation context
# ---------------------------------------------------------------------------

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


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens for matching, stopwords removed."""
    raw = set(re.findall(r"[a-z0-9_]+", text.lower()))
    return raw - _STOPWORDS


def _relevance_score(mem: Memory, query_tokens: set[str],
                     model_hint: str = "") -> float:
    """Score a guidance item's relevance to the current query/model context.

    Returns -1.0 to 1.0:
      - Positive: relevant to query/model context
      - Zero: neutral (no signal either way)
      - Negative: actively irrelevant (domain mismatch with model/query)
    """
    if not query_tokens:
        return 0.5  # no query context = neutral, use confidence only

    ctx = getattr(mem, "context_when", "") or ""
    enf = getattr(mem, "enforce", "") or ""
    avd = getattr(mem, "avoid", "") or ""
    full_text = f"{ctx} {enf} {avd} {mem.text}"
    mem_tokens = _tokenize(full_text)

    if not mem_tokens:
        return 0.0

    # Word overlap
    overlap = query_tokens & mem_tokens
    overlap_ratio = len(overlap) / min(len(query_tokens), len(mem_tokens), 20)
    score = min(overlap_ratio, 1.0)

    # Boost if context_when has strong overlap (it's the "when to apply" field)
    ctx_tokens = _tokenize(ctx)
    if ctx_tokens:
        ctx_overlap = query_tokens & ctx_tokens
        if ctx_overlap:
            score = max(score, len(ctx_overlap) / min(len(ctx_tokens), 10))

    # Model/backend affinity: return negative score for domain mismatches
    # (negative means "actively exclude", not just "low relevance")
    ctx_lower = ctx.lower()
    if model_hint:
        model_lower = model_hint.lower()
        query_str = " ".join(query_tokens)

        # iOS-specific items are irrelevant to non-iOS backends
        if any(kw in ctx_lower for kw in ("ios", "swift", "chatview",
                                           "xcode", "testflight")):
            if not any(kw in model_lower for kw in ("ios", "swift")):
                if not any(kw in query_str for kw in
                           ("ios", "swift", "mobile", "app", "chatview")):
                    return -0.5  # hard exclude

        # CSS/frontend items
        if any(kw in ctx_lower for kw in ("css", "frontend", "viewport",
                                           "mobile viewport")):
            if "css" not in query_str and "frontend" not in query_str:
                return -0.3

        # Trading-specific items irrelevant to dev work
        if any(kw in ctx_lower for kw in ("trading analysis",
                                           "trading strategies")):
            if not any(kw in query_str for kw in
                       ("trading", "trade", "plan_m", "plan_h", "screener",
                        "resistance", "support", "order block", "zone",
                        "ob", "ticker", "stock", "option", "call", "put",
                        "bullish", "bearish", "signal", "nine", "ovtlyr",
                        "sector", "earnings", "position")):
                return -0.3

    score = min(score, 1.0)

    # Apply historical feedback adjustment (contextual bandit signal)
    # Items that are never useful get penalized; consistently useful ones get boosted
    try:
        from whisper_feedback import get_adjustment
        adjustment = get_adjustment(full_text)
        score *= adjustment
        score = min(score, 1.0)
    except Exception:
        pass  # feedback index may not exist yet

    return score


def render_type1_whisper(envelope: ContextEnvelope,
                         query: str = "",
                         model_hint: str = "") -> str:
    """Render Type 1 (procedural) guidance as a <subconscious_whisper> block.

    Type 1 items are always-on, no cooldown.  They are invariants and
    corrections that should fire every turn — the proceduralized knowledge
    that operates "outside working memory."

    Selection logic:
      - Items with confidence >= 0.9 are always included (unconditional)
      - Remaining items scored by 0.4*confidence + 0.6*relevance, top N
      - Hard cap at TYPE1_MAX_CHARS / TYPE1_MAX_ITEMS

    Returns formatted <subconscious_whisper> block (with XML tags) or "".
    """
    try:
        from config import TYPE1_MAX_CHARS, TYPE1_MAX_ITEMS
    except ImportError:
        TYPE1_MAX_CHARS = 2000
        TYPE1_MAX_ITEMS = 10

    # Filter to invariants + corrections only (Type 1 pathway)
    type1_items = [m for m in envelope.guidance
                   if m.type in ("invariant", "correction")]
    if not type1_items:
        return ""

    query_tokens = _tokenize(query) if query else set()

    def _render_item(mem):
        ctx = _refresh_today(getattr(mem, "context_when", ""))
        enf = _refresh_today(getattr(mem, "enforce", ""))
        avd = _refresh_today(getattr(mem, "avoid", ""))
        tag = "invariant" if mem.type == "invariant" else "correction"
        if ctx and enf and avd:
            return f"- [{tag}] When {ctx}: enforce {enf}; avoid {avd}"
        return f"- [{tag}] {_refresh_today(mem.display_text())}"

    # Score ALL items by blended confidence + relevance.
    # With 40-50 items at high confidence, pure confidence ordering
    # wastes budget on irrelevant invariants.  Relevance determines
    # which high-confidence items matter for THIS turn.
    if query_tokens or model_hint:
        scored = []
        for m in type1_items:
            rel = _relevance_score(m, query_tokens, model_hint)
            if rel < 0.0:
                continue  # domain mismatch — hard exclude
            combined = 0.4 * m.confidence + 0.6 * rel
            scored.append((combined, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        ranked = [m for _, m in scored]
    else:
        # No query context — sort by confidence only
        ranked = sorted(type1_items, key=lambda m: m.confidence, reverse=True)

    # Build output lines within budget
    lines = ["<subconscious_whisper>", "## Guidance"]
    chars_used = 0
    item_count = 0

    for mem in ranked:
        if item_count >= TYPE1_MAX_ITEMS:
            break
        line = _render_item(mem)
        if chars_used + len(line) > TYPE1_MAX_CHARS:
            break
        lines.append(line)
        chars_used += len(line)
        item_count += 1

    if item_count == 0:
        return ""

    lines.append("</subconscious_whisper>")
    return "\n".join(lines) + "\n\n"


def render_guidance_whisper(envelope: ContextEnvelope,
                            max_items: int = 10,
                            query: str = "",
                            model_hint: str = "") -> list[str]:
    """Render canonical guidance items as whisper lines.

    Returns list of formatted lines (without XML wrapper) for merging
    with Apex's embedding-based memory results.

    Args:
        envelope: The context envelope from canonical store
        max_items: Maximum items to include
        query: Current user prompt for relevance filtering
        model_hint: Model name (e.g., "qwen3:32b") for context affinity
    """
    lines = []
    chars_used = 0

    query_tokens = _tokenize(query) if query else set()

    # Separate by type
    invariants = [m for m in envelope.guidance if m.type == "invariant"]
    corrections = [m for m in envelope.guidance
                   if m.type == "correction" and m.confidence >= 0.6]
    others = [m for m in envelope.guidance
              if m.type not in ("invariant", "correction")]

    # Score and rank invariants by relevance to current context
    if query_tokens or model_hint:
        scored = []
        for m in invariants:
            rel = _relevance_score(m, query_tokens, model_hint)
            # Blend: 40% confidence + 60% relevance
            combined = 0.4 * m.confidence + 0.6 * rel
            scored.append((combined, rel, m))
        scored.sort(key=lambda x: x[0], reverse=True)

        # Negative relevance = domain mismatch, never include
        eligible = [(c, r, m) for c, r, m in scored if r >= 0.0]
        relevant = [(c, r, m) for c, r, m in eligible if r >= 0.15]

        if len(relevant) >= 3:
            invariants = [m for _, _, m in relevant]
        else:
            # Pad from eligible (non-negative) items only
            used_ids = {id(m) for _, _, m in relevant}
            invariants = [m for _, _, m in relevant]
            for _, _, m in eligible:
                if id(m) not in used_ids and len(invariants) < 3:
                    invariants.append(m)
                    used_ids.add(id(m))
    else:
        # No query context — take top items by confidence
        invariants = invariants[:max_items]

    for mem in invariants[:max_items]:
        ctx = _refresh_today(getattr(mem, "context_when", ""))
        enf = _refresh_today(getattr(mem, "enforce", ""))
        avd = _refresh_today(getattr(mem, "avoid", ""))
        if ctx and enf and avd:
            line = f"- [invariant] When {ctx}: enforce {enf}; avoid {avd}"
        else:
            line = f"- [invariant] {_refresh_today(mem.display_text())}"

        if chars_used + len(line) > WHISPER_BUDGET:
            break
        lines.append(line)
        chars_used += len(line)

    for mem in corrections[:3]:
        line = f"- [correction] {_refresh_today(mem.text[:200])}"
        if chars_used + len(line) > WHISPER_BUDGET:
            break
        lines.append(line)
        chars_used += len(line)

    for mem in others[:3]:
        line = f"- [{mem.type}] {_refresh_today(mem.display_text()[:200])}"
        if chars_used + len(line) > WHISPER_BUDGET:
            break
        lines.append(line)
        chars_used += len(line)

    return lines


def merge_with_embeddings(guidance_lines: list[str],
                          embedding_results: list[dict],
                          max_embedding_results: int = 3) -> str:
    """Merge canonical guidance lines with Apex embedding search results.

    Returns formatted <subconscious_whisper> block ready for injection.

    Args:
        guidance_lines: Lines from render_guidance_whisper()
        embedding_results: Results from memory_search.search() — list of
            dicts with keys: file, content, score, source, _stale
        max_embedding_results: Max embedding results to include
    """
    lines = ["<subconscious_whisper>"]

    # Guidance section (canonical store)
    if guidance_lines:
        lines.append("Guidance:")
        lines.extend(guidance_lines)

    # Embedding section (Apex memory search)
    relevant = [r for r in embedding_results
                if r.get("score", 0) >= 0.55][:max_embedding_results]
    if relevant:
        lines.append("")
        lines.append("Relevant memories for this conversation:")
        for r in relevant:
            name = Path(r.get("file", "unknown")).stem
            src = r.get("source", "memory")[:4]
            score_str = f"score={r['score']:.2f}"
            stale_tag = " STALE — verify before using" if r.get("_stale") else ""
            lines.append(
                f"- [{name}] ({src} {score_str}{stale_tag}) "
                f"{r.get('content', '')[:200]}"
            )

    lines.append("</subconscious_whisper>")

    if len(lines) <= 2:  # only wrapper tags
        return ""

    return "\n".join(lines) + "\n\n"


def render_session_context(envelope: ContextEnvelope) -> str:
    """Render full context for Apex session initialization.

    Used by context.py._build_system_prompt() to inject canonical
    guidance alongside persona instructions.
    """
    lines = [
        "<subconscious_context>",
        f"Background memory active. Session: {envelope.session.session_id[:8]}...",
    ]

    guidance = envelope.guidance
    if guidance:
        lines.append("")
        lines.append("## Guidance")
        for mem in guidance:
            if mem.type == "invariant":
                ctx = _refresh_today(getattr(mem, "context_when", ""))
                enf = _refresh_today(getattr(mem, "enforce", ""))
                avd = _refresh_today(getattr(mem, "avoid", ""))
                if ctx and enf and avd:
                    lines.append(
                        f"- [invariant] When {ctx}: enforce {enf}; avoid {avd}"
                    )
                else:
                    lines.append(f"- [invariant] {_refresh_today(mem.display_text())}")
            else:
                lines.append(f"- [{mem.type}] {_refresh_today(mem.display_text())}")

    lines.append("</subconscious_context>")
    return "\n".join(lines)
