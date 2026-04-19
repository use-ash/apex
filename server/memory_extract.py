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

from compat import safe_chmod
from db import (
    _add_persona_memory, _get_persona_memories, _bump_memory_violation,
    _retire_persona_memories,
)
from env import APEX_ROOT
from log import log
from state import _STREAM_TEXT_FILTERS

GUARDRAIL_WHITELIST = APEX_ROOT / "state" / "guardrail_whitelist.json"

# ---------------------------------------------------------------------------
# Memory tag regex
# ---------------------------------------------------------------------------
# Tags now carry optional attributes in any order:
#   <memory category="decision" subject="scope.topic">body</memory>
#   <memory category="task" subject="x" ttl="14d">body</memory>
#   <memory action="retire" id="mem_abc123">reason</memory>
#   <memory action="retire" subject="x" status="superseded">reason</memory>
# _MEMORY_TAG_RE captures the whole opening-tag attrs blob + body; attribute
# parsing is a second pass via _ATTR_RE.
_MEMORY_TAG_RE = re.compile(
    r'<memory\s+([^>]*)>(.*?)</memory>',
    re.DOTALL,
)
_ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
_TTL_RE = re.compile(r'^\s*(\d+)\s*([smhdw]?)\s*$', re.IGNORECASE)
_TTL_MULT = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 7 * 86400}


def _parse_ttl(raw: str) -> int | None:
    """Parse '14d', '7d', '3600s', '2w'. Returns seconds, or None on bad input."""
    if not raw:
        return None
    m = _TTL_RE.match(raw)
    if not m:
        return None
    n = int(m.group(1))
    unit = (m.group(2) or "").lower()
    return n * _TTL_MULT.get(unit, 1)


def _parse_memory_attrs(blob: str) -> dict:
    """Parse the space-separated `key="value"` blob inside <memory ...>."""
    out = {}
    for k, v in _ATTR_RE.findall(blob):
        out[k.lower()] = v
    return out


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
    """Parse <memory ...>body</memory> tags from agent response.

    Two tag shapes:
      <memory category="..." [subject="..."] [ttl="14d"]>body</memory>
        -> insert row; auto-supersede older same-subject rows of equal/lower rank.

      <memory action="retire" [id="..."] [subject="..."] [status="retired|superseded"]>reason</memory>
        -> retire one row by id, or all active same-subject rows. `status` selects
           between 'retired' (deemed wrong) and 'superseded' (replaced elsewhere);
           defaults to 'retired'.

    Saves each memory, strips tags from displayed text.
    """
    if not profile_id or "<memory" not in text:
        return text

    for attr_blob, body in _MEMORY_TAG_RE.findall(text):
        attrs = _parse_memory_attrs(attr_blob)
        body = body.strip()
        action = (attrs.get("action") or "").lower()

        if action == "retire":
            subj = attrs.get("subject")
            mid_arg = attrs.get("id")
            status = (attrs.get("status") or "retired").lower()
            if status not in ("retired", "superseded"):
                log(f"memory retire skipped: bad status={status!r}")
                continue
            if not (subj or mid_arg):
                log("memory retire skipped: neither id nor subject given")
                continue
            try:
                affected = _retire_persona_memories(
                    profile_id, memory_id=mid_arg, subject=subj,
                    status=status, reason=body,
                )
                log(f"persona memory retired: profile={profile_id} status={status} "
                    f"id={mid_arg} subject={subj} affected={len(affected)}")
            except Exception as e:
                log(f"memory retire error (non-fatal): {e}")
            continue

        # Normal save path.
        category = (attrs.get("category") or "").lower() or "note"
        subject = attrs.get("subject")
        ttl_seconds = _parse_ttl(attrs.get("ttl", ""))
        if not body:
            continue

        # Corrections: bump violation_count on existing overlapping corrections.
        if category == "correction":
            _check_and_bump_violations(profile_id, body)
        mid = _add_persona_memory(
            profile_id, body,
            category=category,
            source_chat_id=chat_id,
            subject=subject,
            ttl_seconds=ttl_seconds,
        )
        log(f"persona memory saved: profile={profile_id} cat={category} "
            f"subject={subject!r} ttl={ttl_seconds} id={mid} len={len(body)}")

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
    safe_chmod(GUARDRAIL_WHITELIST.parent, 0o700)
    GUARDRAIL_WHITELIST.write_text(json.dumps(entries, indent=2))
    safe_chmod(GUARDRAIL_WHITELIST, 0o600)
    return entry
