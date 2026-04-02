"""Memory tag extraction from agent responses.

Parses <memory category="...">...</memory> tags from streamed text,
saves to persona_memories, and strips tags from displayed output.
Also manages time-limited guardrail whitelist entries.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone

from db import _add_persona_memory, _get_persona_memories, _bump_memory_violation
from env import APEX_ROOT
from log import log
from state import _STREAM_TEXT_FILTERS

GUARDRAIL_WHITELIST = APEX_ROOT / "state" / "guardrail_whitelist.json"

# ---------------------------------------------------------------------------
# Memory tag regex
# ---------------------------------------------------------------------------
_MEMORY_TAG_RE = re.compile(
    r'<memory\s+category="([^"]*)">(.*?)</memory>',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Stream text filtering — strip <memory> tags from streamed chunks
# ---------------------------------------------------------------------------

def _filter_stream_text_for_memory_tags(chat_id: str, stream_id: str, text: str) -> str:
    """Strip <memory> tags from streamed text chunks without leaking partial tags.

    Streaming responses arrive chunk-by-chunk, so memory tags may be split across
    multiple websocket events. We buffer partial tag fragments per stream and only
    emit user-visible text.
    """
    if not text:
        return ""
    key = (chat_id, stream_id)
    state = _STREAM_TEXT_FILTERS.get(key)
    if state is None:
        state = {"partial": "", "inside": False}
        _STREAM_TEXT_FILTERS[key] = state

    data = f"{state['partial']}{text}"
    state['partial'] = ""
    inside = bool(state.get("inside"))
    out: list[str] = []
    i = 0

    while i < len(data):
        if inside:
            close_idx = data.find("</memory>", i)
            if close_idx == -1:
                state['partial'] = data[i:]
                state['inside'] = True
                return "".join(out)
            i = close_idx + len("</memory>")
            inside = False
            state['inside'] = False
            continue

        open_idx = data.find("<memory", i)
        if open_idx == -1:
            tail = data[i:]
            partial_start = -1
            for n in range(1, min(len(tail), len("<memory")) + 1):
                candidate = tail[-n:]
                if "<memory".startswith(candidate):
                    partial_start = len(tail) - n
            if partial_start > 0:
                out.append(tail[:partial_start])
                state['partial'] = tail[partial_start:]
            elif partial_start == 0:
                state['partial'] = tail
            else:
                out.append(tail)
            return "".join(out)

        out.append(data[i:open_idx])
        tag_end = data.find(">", open_idx)
        if tag_end == -1:
            state['partial'] = data[open_idx:]
            state['inside'] = False
            return "".join(out)
        i = tag_end + 1
        inside = True
        state['inside'] = True

    return "".join(out)


def _clear_stream_text_filter(chat_id: str, stream_id: str) -> None:
    if chat_id and stream_id:
        _STREAM_TEXT_FILTERS.pop((chat_id, stream_id), None)


# ---------------------------------------------------------------------------
# Violation detection
# ---------------------------------------------------------------------------

def _check_and_bump_violations(profile_id: str, new_content: str) -> None:
    """If a new correction overlaps with an existing one, bump the older one's violation_count.

    Heuristic: 50%+ word overlap between the new correction and an existing
    correction means the agent violated the earlier rule (it needed re-correction).
    """
    try:
        existing = _get_persona_memories(profile_id, limit=80)
        new_words = set(new_content.lower().split())
        if len(new_words) < 3:
            return
        for mem in existing:
            if mem.get("category") != "correction":
                continue
            mem_words = set(mem["content"].lower().split())
            if not mem_words:
                continue
            overlap = len(new_words & mem_words) / min(len(new_words), len(mem_words))
            if overlap >= 0.5:
                _bump_memory_violation(mem["id"])
                log(f"memory violation bump: id={mem['id']} overlap={overlap:.0%} with new correction")
    except Exception as e:
        log(f"violation check error (non-fatal): {e}")


# ---------------------------------------------------------------------------
# Memory extraction + persistence
# ---------------------------------------------------------------------------

def _extract_and_save_memories(text: str, profile_id: str, chat_id: str) -> str:
    """Parse <memory category="...">...</memory> tags from agent response.

    Saves each memory to persona_memories, strips tags from displayed text.
    Returns the cleaned text with memory tags removed.
    """
    if not profile_id or "<memory" not in text:
        return text

    matches = _MEMORY_TAG_RE.findall(text)
    for category, content in matches:
        content = content.strip()
        if content:
            # If saving a correction, check for existing corrections on the same topic.
            # A re-correction implies the agent violated the earlier rule — bump violation_count.
            if category == "correction":
                _check_and_bump_violations(profile_id, content)
            mid = _add_persona_memory(
                profile_id, content,
                category=category or "note",
                source_chat_id=chat_id,
            )
            log(f"persona memory saved: profile={profile_id} cat={category} id={mid} len={len(content)}")

    # Strip memory tags from displayed text
    cleaned = _MEMORY_TAG_RE.sub("", text).strip()
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned


# ---------------------------------------------------------------------------
# Guardrail whitelist
# ---------------------------------------------------------------------------

def _add_whitelist_entry(tool: str, target: str, alert_id: str, ttl_seconds: int = 3600) -> dict:
    """Add a time-limited guardrail exemption."""
    expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
    entry = {"tool": tool, "target": target, "alert_id": alert_id, "expires_at": expires}
    entries = []
    if GUARDRAIL_WHITELIST.exists():
        try:
            entries = json.loads(GUARDRAIL_WHITELIST.read_text())
        except Exception:
            pass
    # Prune expired
    now = datetime.now(timezone.utc).isoformat()
    entries = [e for e in entries if e.get("expires_at", "") > now]
    entries.append(entry)
    GUARDRAIL_WHITELIST.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(GUARDRAIL_WHITELIST.parent, 0o700)
    GUARDRAIL_WHITELIST.write_text(json.dumps(entries, indent=2))
    os.chmod(GUARDRAIL_WHITELIST, 0o600)
    return entry
