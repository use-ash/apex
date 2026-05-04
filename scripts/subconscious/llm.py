"""LLM extraction for subconscious memory system.

Calls Ollama locally; falls back to heuristic keyword matching.
"""
import datetime as _dt
import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    OLLAMA_MODEL, OLLAMA_URL, OLLAMA_TIMEOUT, OLLAMA_OPTIONS,
    redact_secrets,
    INVARIANT_CONFIDENCE_THRESHOLD, INVARIANT_MAX_PER_SESSION,
    OLLAMA_VALIDATION_MODEL, OLLAMA_VALIDATION_TIMEOUT,
)

_CORRECTION_WORDS = re.compile(
    r"\b(no|wrong|not that|don't|stop)\b", re.IGNORECASE
)
_TOOL_RESULT_PATTERN = re.compile(
    r"^\s*\{['\"](?:role|tool_use_id|type)['\"]"
)

# Relative-date anchoring: bind natural-language relatives to absolute dates
# at extraction time, so a saved rule containing "yesterday" stays correct
# weeks later. Idempotent — won't re-anchor an already-anchored phrase.
_REL_DATE_PATTERN = re.compile(
    r"\b(yesterday|today|tomorrow|last week|this week|next week|"
    r"last month|this month|next month)\b"
    r"(?!\s*\(\d{4}-\d{2}-\d{2}\))",
    re.IGNORECASE,
)


def _anchor_relatives(text: str, anchor: _dt.date | None = None) -> str:
    """Append (YYYY-MM-DD) to natural-language relative date references.

    'yesterday' -> 'yesterday (2026-05-02)'. Anchors to `anchor` (default today).
    Idempotent via a negative lookahead: won't double-anchor.
    """
    if not text:
        return text
    if anchor is None:
        anchor = _dt.date.today()

    def _resolve(word: str) -> _dt.date:
        w = word.lower()
        if w == "yesterday":   return anchor - _dt.timedelta(days=1)
        if w == "today":       return anchor
        if w == "tomorrow":    return anchor + _dt.timedelta(days=1)
        if w == "last week":   return anchor - _dt.timedelta(days=7)
        if w == "this week":   return anchor
        if w == "next week":   return anchor + _dt.timedelta(days=7)
        if w == "last month":  return anchor - _dt.timedelta(days=30)
        if w == "this month":  return anchor
        if w == "next month":  return anchor + _dt.timedelta(days=30)
        return anchor

    def _sub(m: re.Match) -> str:
        word = m.group(1)
        return f"{word} ({_resolve(word).isoformat()})"

    return _REL_DATE_PATTERN.sub(_sub, text)


def _anchor_extraction(result: dict, anchor: _dt.date | None = None) -> dict:
    """Walk an extract_session result dict and anchor relatives in all text fields."""
    if anchor is None:
        anchor = _dt.date.today()
    for key in ("corrections", "decisions", "pending"):
        for item in result.get(key, []) or []:
            if isinstance(item, dict) and "text" in item:
                item["text"] = _anchor_relatives(item["text"], anchor)
    summary = result.get("summary")
    if isinstance(summary, dict) and "text" in summary:
        summary["text"] = _anchor_relatives(summary["text"], anchor)
    for inv in result.get("invariants", []) or []:
        if not isinstance(inv, dict):
            continue
        for field in ("context", "enforce", "avoid"):
            if field in inv:
                inv[field] = _anchor_relatives(inv[field], anchor)
    return result


def _normalize(text: str, max_len: int = 200) -> str:
    """Collapse whitespace, strip, truncate to max_len with '...' suffix."""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] + "..." if len(text) > max_len else text


def _clean_llm_json(raw: str) -> str:
    """Clean LLM output: strip thinking token leaks, markdown fencing, etc.

    Gemma 4 on /api/generate wraps output in {"type":"thought","content":"..."}.
    This guard handles that plus standard markdown ```json fencing.
    """
    raw = raw.strip()
    # Strip thinking token wrapper (Gemma 4 artifact)
    try:
        maybe = json.loads(raw)
        if isinstance(maybe, dict) and maybe.get("type") == "thought" and "content" in maybe:
            raw = maybe["content"]
            # Content often starts with junk before the actual JSON
            raw = re.sub(r'^[^[{]*', '', raw, count=1)
    except (json.JSONDecodeError, ValueError):
        pass
    # Strip markdown JSON fencing
    raw = re.sub(r"^```json\s*", "", raw.strip())
    raw = re.sub(r"\s*```\s*$", "", raw.strip())
    return raw


def extract_session(transcript: str, messages: list[dict],
                    session_date: _dt.date | None = None) -> dict:
    """Extract corrections, decisions, pending, summary, and invariants from a session.

    `session_date` anchors relative date phrases ('yesterday', 'last week')
    to absolute dates at extraction time. Defaults to today.
    """
    try:
        result = _extract_via_llm(transcript)
    except Exception:
        result = _extract_heuristic(messages)
    # Extract invariants independently (MemCollab contrastive pipeline)
    result["invariants"] = extract_invariants(transcript, session_date=session_date)
    # Anchor natural-language relatives to absolute dates so saved rules
    # don't drift as the calendar advances.
    return _anchor_extraction(result, anchor=session_date)


def _extract_via_llm(transcript: str) -> dict:
    """Primary path: call Ollama for structured extraction."""
    clean = redact_secrets(transcript)
    prompt = (
        "Analyze the following session transcript and extract:\n"
        "- corrections: things the user corrected or said no/wrong/stop about\n"
        "- decisions: architectural or technical decisions made\n"
        "- pending: unresolved items, things left incomplete\n"
        "- summary: 1-2 sentence session summary\n\n"
        "Return valid JSON with keys: corrections (list), decisions (list), "
        "pending (list), summary (string).\n\n"
        f"Transcript:\n{clean}"
    )
    payload = json.dumps({
        "model": OLLAMA_MODEL, "stream": False, "think": False,
        "messages": [
            {"role": "system", "content": "You are a JSON extraction engine. Return ONLY valid JSON, no prose, no markdown fencing, no explanation."},
            {"role": "user", "content": prompt},
        ],
        "format": "json",
        "options": OLLAMA_OPTIONS,
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)
    body = json.loads(resp.read().decode())
    raw = body["message"]["content"]
    raw = _clean_llm_json(raw)
    parsed = json.loads(raw)

    def _tag(items):
        return [
            {"text": _normalize(str(i)), "confidence": 0.8, "source": "llm"}
            for i in (items if isinstance(items, list) else [])
        ]

    return {
        "corrections": _tag(parsed.get("corrections", [])),
        "decisions": _tag(parsed.get("decisions", [])),
        "pending": _tag(parsed.get("pending", [])),
        "summary": {
            "text": _normalize(str(parsed.get("summary", ""))),
            "confidence": 0.8, "source": "llm",
        },
    }


def extract_invariants(transcript: str,
                       session_date: _dt.date | None = None) -> list[dict]:
    """Extract enforce/avoid invariants from a session transcript.

    MemCollab-inspired: produces model-agnostic behavioral rules structured as
    (context, enforce, avoid) tuples. Uses contrastive validation across two
    different model families to filter out model-specific reasoning artifacts.

    `session_date` anchors relative date phrases. Defaults to today.
    """
    try:
        candidates = _extract_invariants_pass1(transcript)
        if not candidates:
            return []
        validated = _validate_invariants_pass2(candidates, transcript)
        validated = validated[:INVARIANT_MAX_PER_SESSION]
        # Anchor relatives in extracted invariants
        anchor = session_date or _dt.date.today()
        for inv in validated:
            for field in ("context", "enforce", "avoid"):
                if field in inv:
                    inv[field] = _anchor_relatives(inv[field], anchor)
        return validated
    except Exception:
        return []


def _extract_invariants_pass1(transcript: str) -> list[dict]:
    """Pass 1: Extract candidate invariants from transcript via primary model."""
    clean = redact_secrets(transcript)
    # Truncate to last ~6000 chars to fit context and focus on recent activity
    if len(clean) > 6000:
        clean = clean[-6000:]

    prompt = (
        "Analyze this development session transcript and extract durable behavioral rules "
        "based on user corrections, preferences, and decisions.\n\n"
        "For each rule, produce a JSON object with:\n"
        '- "context": when does this rule apply (short phrase, e.g. "launching the server")\n'
        '- "enforce": what to do — be SPECIFIC and actionable, include tool names, paths, '
        "or techniques the user insisted on\n"
        '- "avoid": what NOT to do — the specific mistake or approach the user corrected\n'
        '- "confidence": 0.0-1.0 how confident this is a real, durable rule\n\n'
        "Extraction guidelines:\n"
        "- Focus on moments where the user corrected the assistant or stated a preference\n"
        "- Include specific tool names, file names, and paths that the user mentioned\n"
        "- The rule must be actionable: another AI assistant reading it should know exactly "
        "what to do and what to avoid\n"
        "- Do NOT include rules that are just generic good practices (e.g. 'write clean code')\n"
        "- Do NOT describe what happened in the session — extract the underlying RULE\n"
        "- Maximum 5 candidates\n\n"
        "Return a JSON array of objects. If no durable rules are found, return [].\n\n"
        f"Transcript:\n{clean}"
    )
    payload = json.dumps({
        "model": OLLAMA_MODEL, "stream": False, "think": False,
        "messages": [
            {"role": "system", "content": "You are a JSON extraction engine. Return ONLY a valid JSON array of objects. No prose, no markdown fencing, no explanation."},
            {"role": "user", "content": prompt},
        ],
        "format": "json",
        "options": OLLAMA_OPTIONS,
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)
    body = json.loads(resp.read().decode())
    raw = body["message"]["content"]
    raw = _clean_llm_json(raw)
    parsed = json.loads(raw)

    # Handle {"invariants": [...]}, direct [...], or single object {...}
    if isinstance(parsed, dict):
        inner = parsed.get("invariants", parsed.get("rules"))
        if inner is not None:
            parsed = inner
        elif all(k in parsed for k in ("context", "enforce", "avoid")):
            parsed = [parsed]  # single invariant object → wrap in list
        else:
            return []
    if not isinstance(parsed, list):
        return []

    results = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        ctx = str(item.get("context", "")).strip()
        enforce = str(item.get("enforce", "")).strip()
        avoid = str(item.get("avoid", "")).strip()
        conf = float(item.get("confidence", 0.5))
        if ctx and enforce and avoid and conf >= INVARIANT_CONFIDENCE_THRESHOLD:
            results.append({
                "context": _normalize(ctx, 120),
                "enforce": _normalize(enforce, 200),
                "avoid": _normalize(avoid, 200),
                "confidence": round(conf, 2),
                "source": "single",
            })
    return results


def _validate_invariants_pass2(candidates: list[dict], transcript: str) -> list[dict]:
    """Pass 2: Contrastive validation via a different model family.

    Filters out invariants that encode model-specific reasoning style rather
    than genuine task-structural knowledge (the core MemCollab insight).
    """
    if not candidates:
        return []

    clean = redact_secrets(transcript)
    if len(clean) > 3000:
        clean = clean[-3000:]

    candidates_text = json.dumps(candidates, indent=2)
    prompt = (
        "You are a validator for AI behavioral rules. Review these candidate rules "
        "and determine which ones are genuinely model-agnostic.\n\n"
        "REMOVE any rule that:\n"
        "- Encodes a specific AI model's reasoning style or preferences\n"
        "- Is too vague to be actionable (e.g., 'be careful', 'think thoroughly')\n"
        "- Describes transient session state rather than a durable principle\n"
        "- Would only make sense to the specific model that generated it\n"
        "- Restates obvious software engineering practices without specific context\n\n"
        "KEEP rules that:\n"
        "- Capture specific user preferences or workspace conventions\n"
        "- Encode domain-specific knowledge learned from corrections\n"
        "- Would help ANY AI model working in this codebase\n"
        "- Are grounded in observable patterns from the transcript\n\n"
        f"Candidate rules:\n{candidates_text}\n\n"
        f"Session context (for verification):\n{clean}\n\n"
        'Return a JSON array of the rules that PASS validation. '
        "Keep the same format. If none pass, return []."
    )
    try:
        payload = json.dumps({
            "model": OLLAMA_MODEL, "stream": False, "think": False,
            "messages": [
                {"role": "system", "content": "You are a JSON validation engine. Return ONLY a valid JSON array. No prose, no markdown fencing, no explanation."},
                {"role": "user", "content": prompt},
            ],
            "format": "json",
            "options": OLLAMA_OPTIONS,
        }).encode()
        req = urllib.request.Request(
            OLLAMA_URL, data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=OLLAMA_VALIDATION_TIMEOUT)
        body = json.loads(resp.read().decode())
        raw = body["message"]["content"]
        raw = _clean_llm_json(raw)
        parsed = json.loads(raw)

        # Flexible key discovery: find the list of items in the response
        if isinstance(parsed, dict):
            # Try known keys, then fall back to first list-valued key
            for key in ("invariants", "rules", "validated", "result", "items"):
                if key in parsed and isinstance(parsed[key], list):
                    parsed = parsed[key]
                    break
            else:
                # Try first list value in the dict
                for v in parsed.values():
                    if isinstance(v, list):
                        parsed = v
                        break
        if not isinstance(parsed, list):
            # Validation failed to parse — downgrade confidence, return all
            for c in candidates:
                c["confidence"] = min(c["confidence"], 0.75)
            return candidates

        # Build validated list; preserve original confidence, mark as contrastive
        validated = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            ctx = str(item.get("context", "")).strip()
            enforce = str(item.get("enforce", "")).strip()
            avoid = str(item.get("avoid", "")).strip()
            if ctx and enforce and avoid:
                # Find matching candidate to preserve its original confidence
                orig_conf = 0.85
                for c in candidates:
                    if _normalize(c.get("context", ""), 120) == _normalize(ctx, 120):
                        orig_conf = c.get("confidence", 0.85)
                        break
                validated.append({
                    "context": _normalize(ctx, 120),
                    "enforce": _normalize(enforce, 200),
                    "avoid": _normalize(avoid, 200),
                    "confidence": round(min(orig_conf, 0.95), 2),
                    "source": "contrastive",
                })
        return validated if validated else candidates

    except Exception as e:
        # Contrastive validation unavailable (model swap, timeout, etc.)
        # Return candidates as-is — single-pass extraction is still valuable
        print(f"invariant validation skipped ({e}), using single-pass", file=sys.stderr)
        return candidates


def _is_tool_noise(text: str) -> bool:
    """Return True if text looks like a raw tool_result blob, not real user input."""
    s = str(text)
    return bool(_TOOL_RESULT_PATTERN.match(s)) or s.startswith("{'role':")


def _extract_heuristic(messages: list[dict]) -> dict:
    """Fallback: keyword scanning when LLM unavailable.

    Filters out tool_result blobs that were polluting guidance with raw JSON.
    """
    user_msgs = [
        m for m in messages
        if m.get("role") == "user" and not _is_tool_noise(m.get("content", ""))
    ]
    corrections = [
        {"text": _normalize(m["content"]), "confidence": 0.3, "source": "heuristic"}
        for m in user_msgs
        if _CORRECTION_WORDS.search(m.get("content", ""))
    ]
    pending = []
    if user_msgs:
        pending = [{"text": _normalize(user_msgs[-1]["content"]),
                     "confidence": 0.3, "source": "heuristic"}]
    summary_text = ""
    if user_msgs:
        first = _normalize(user_msgs[0].get("content", ""), max_len=100)
        last = _normalize(user_msgs[-1].get("content", ""), max_len=100)
        summary_text = f"{first} ... {last}" if len(user_msgs) > 1 else first
    return {
        "corrections": corrections,
        "decisions": [],
        "pending": pending,
        "summary": {"text": summary_text, "confidence": 0.3, "source": "heuristic"},
    }
