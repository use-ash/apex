"""Context assembly for Apex chat sessions.

Handles recovery context generation, auto-compaction, workspace/profile/memory
injection, group roster building, agent routing, and subconscious whisper.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from db import (
    _get_db, _get_chat, _update_chat,
    _get_messages, _get_recent_messages_text, _get_cumulative_tokens_in,
    _get_group_members, _get_persona_memories, _bump_memory_access,
    _get_last_assistant_speaker,
    _now, SYSTEM_PROFILE_ID, _get_chat_settings,
    verify_system_prompt,
)
import env
from log import log
from group_coordinator import _build_group_relay_state_prompt
from model_dispatch import _get_model_backend, OLLAMA_BASE_URL
from streaming import _get_profile_active_stream_stats
from state import (
    _compaction_summaries, _recovery_target, _recovery_skip_count,
    _last_compacted_at, _session_context_sent,
    _group_profile_override, _whisper_last,
    _db_lock, _current_group_profile_id, _queued_turns,
    _chat_ws, _clients,
)

# ---------------------------------------------------------------------------
# Config (from env)
# ---------------------------------------------------------------------------
WORKSPACE = env.WORKSPACE
MODEL = env.MODEL
DEBUG = env.DEBUG

XAI_API_KEY = env.XAI_API_KEY
COMPACTION_THRESHOLD = env.COMPACTION_THRESHOLD
COMPACTION_MODEL = env.COMPACTION_MODEL
COMPACTION_OLLAMA_FALLBACK = env.COMPACTION_OLLAMA_FALLBACK
COMPACTION_OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/generate"
COMPACTION_TIMEOUT = 30

ENABLE_SUBCONSCIOUS_WHISPER = env.ENABLE_SUBCONSCIOUS_WHISPER
WHISPER_INTERVAL = 300  # seconds between whisper injections (5 min)

APEX_ROOT = env.APEX_ROOT
_SELF_PORT = env.PORT

_MENTION_RE = re.compile(r"@(\w+)")

# Transcript tail injection — raw JSONL entries for recovery context
_TRANSCRIPT_TAIL_CHARS = int(os.environ.get("APEX_TRANSCRIPT_TAIL_CHARS", "1500"))
_TRANSCRIPT_DIRS = [
    APEX_ROOT / "state" / "apex_transcripts",
    WORKSPACE / "state" / "apex_transcripts",
]

# ---------------------------------------------------------------------------
# Memory scoring constants
# ---------------------------------------------------------------------------
_CAT_WEIGHT = {"correction": 1.0, "decision": 0.7, "task": 0.5, "context": 0.3}
_MAX_TOKEN_BUDGET = 80


# ---------------------------------------------------------------------------
# Live state snapshot helpers
# ---------------------------------------------------------------------------

def _git_cmd(*args: str, timeout: float = 2.0) -> str:
    """Run a git command against APEX_ROOT, return stdout or '' on failure."""
    try:
        r = subprocess.run(
            ["git", "-C", str(APEX_ROOT), *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _check_port_listening(port: int) -> int | None:
    """Return PID listening on port, or None."""
    try:
        r = subprocess.run(
            ["lsof", "-i", f":{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True, timeout=2.0,
        )
        if r.returncode == 0 and r.stdout.strip():
            return int(r.stdout.strip().split("\n")[0])
    except Exception:
        pass
    return None


def _get_live_state_snapshot() -> str:
    """Build a live operational state block for agent context injection.

    Runs lightweight shell commands (~100ms total). Any failure skips that
    section — never crashes the stream.
    """
    lines: list[str] = []
    try:
        ts = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S ET")
    except Exception:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.append(f"# Live State Snapshot\nGenerated: {ts}")

    # -- Git --
    branch = _git_cmd("branch", "--show-current")
    head = _git_cmd("rev-parse", "--short", "HEAD")
    if branch or head:
        dirty_out = _git_cmd("status", "--porcelain")
        dirty_count = len(dirty_out.splitlines()) if dirty_out else 0
        dirty_label = f"Dirty: {dirty_count} files" if dirty_count else "Clean"
        git_line = f"Branch: {branch or '?'} | HEAD: {head or '?'} | {dirty_label}"

        if branch and branch != "main":
            main_head = _git_cmd("rev-parse", "--short", "main")
            ahead = _git_cmd("rev-list", "--count", f"main..{branch}")
            behind = _git_cmd("rev-list", "--count", f"{branch}..main")
            if main_head:
                git_line += f"\nmain: {main_head} | {branch} is {ahead or '0'} ahead, {behind or '0'} behind main"

        lines.append(f"\n## Git\n{git_line}")

    # -- Servers --
    srv_lines: list[str] = []
    for port, label in [(8300, "Prod"), (8301, "Dev")]:
        pid = _check_port_listening(port)
        marker = " (this server)" if port == _SELF_PORT else ""
        status = f"running (PID {pid}){marker}" if pid else "stopped"
        srv_lines.append(f"{label} (:{port}): {status}")
    ws_count = sum(len(s) for s in _chat_ws.values())
    sdk_count = len(_clients)
    srv_lines.append(f"Connected: {ws_count} WebSocket(s), {sdk_count} SDK client(s)")
    lines.append("\n## Servers\n" + "\n".join(srv_lines))

    # -- Recent commits --
    commits = _git_cmd("log", "--oneline", "-5")
    if commits:
        lines.append(f"\n## Recent Commits ({branch or 'HEAD'})\n" +
                     "\n".join(f"- {c}" for c in commits.splitlines()))
    if branch and branch != "main":
        main_commits = _git_cmd("log", "--oneline", "-3", "main")
        if main_commits:
            lines.append("\n## Recent Commits (main)\n" +
                         "\n".join(f"- {c}" for c in main_commits.splitlines()))

    if len(lines) <= 1:
        return ""
    return "<system-reminder>\n" + "\n".join(lines) + "\n</system-reminder>"


# ---------------------------------------------------------------------------
# Memory scoring
# ---------------------------------------------------------------------------

def _parse_iso(s: str) -> datetime:
    """Parse ISO timestamp to UTC datetime, returning epoch on failure."""
    if not s:
        return datetime(2020, 1, 1, tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime(2020, 1, 1, tzinfo=timezone.utc)


def _apply_superseded_penalty(memories: list[dict]) -> None:
    """Flag and penalize older memories superseded by newer ones on the same topic."""
    word_sets = [(set(m["content"].lower().split()), m) for m in memories]
    for i, (ws_i, mem_i) in enumerate(word_sets):
        for j, (ws_j, mem_j) in enumerate(word_sets):
            if i >= j or not ws_i or not ws_j:
                continue
            overlap = len(ws_i & ws_j) / min(len(ws_i), len(ws_j))
            if overlap >= 0.6:
                older = mem_i if mem_i["created_at"] < mem_j["created_at"] else mem_j
                older["_score"] = max(0, older.get("_score", 0) - 0.05)
                older["_superseded"] = True


_MIN_INJECTION_SCORE = 0.10  # below this, memory is not worth injecting


def _score_memories(memories: list[dict], user_message: str = "") -> list[dict]:
    """Score and rank persona memories. Returns sorted list with '_score' key.

    Memories below _MIN_INJECTION_SCORE or flagged as superseded are excluded
    from the returned list to avoid injecting irrelevant or duplicate content.
    """
    now = datetime.now(timezone.utc)
    user_words = set(user_message.lower().split()) if user_message else set()

    for mem in memories:
        score = 0.0
        created = _parse_iso(mem["created_at"])
        last_acc = _parse_iso(mem.get("last_accessed_at", ""))

        # 1. Recency (0.12) — exponential decay, half-life 7 days
        age_hours = max(0, (now - created).total_seconds() / 3600)
        score += 0.12 * math.exp(-0.693 * age_hours / (7 * 24))

        # 2. Frequency (0.10) — log-scaled access count
        acc = mem.get("access_count", 0)
        score += 0.10 * min(1.0, math.log1p(acc) / math.log1p(50))

        # 3. Category weight (0.12)
        score += 0.12 * _CAT_WEIGHT.get(mem.get("category", ""), 0.3)

        # 4. Task proximity (0.25) — word overlap with user message
        #    Strongest signal when a user message is provided.
        if user_words:
            mem_words = set(mem["content"].lower().split())
            overlap = len(user_words & mem_words)
            score += 0.25 * min(1.0, overlap / max(3, len(user_words) * 0.3))

        # 5. Staleness decay (0.08) — penalize if never accessed or stale
        if mem.get("last_accessed_at"):
            stale_days = max(0, (now - last_acc).total_seconds() / 86400)
            score += 0.08 * math.exp(-0.693 * stale_days / 14)
        else:
            score += 0.02  # never accessed — don't kill new memories

        # 6. Violation frequency (0.10) — boost rules that keep getting broken
        viol = mem.get("violation_count", 0)
        if mem.get("category") == "correction" and viol > 0:
            score += 0.10 * min(1.0, viol / 5)
        elif mem.get("category") == "correction":
            score += 0.05  # corrections get baseline boost

        # 7. Token ROI (0.03) — penalize bloated memories
        tc = mem.get("token_count", 0) or len(mem["content"].split())
        if tc > _MAX_TOKEN_BUDGET:
            score += 0.03 * max(0, 1 - (tc - _MAX_TOKEN_BUDGET) / 200)
        else:
            score += 0.03

        mem["_score"] = score

    # Superseded detection — post-pass (marks duplicates)
    _apply_superseded_penalty(memories)

    # Filter: drop superseded and below-threshold memories
    memories = [m for m in memories if m["_score"] >= _MIN_INJECTION_SCORE
                and not m.get("_superseded")]
    memories.sort(key=lambda m: m["_score"], reverse=True)
    return memories


# ---------------------------------------------------------------------------
# Recovery context generation
# ---------------------------------------------------------------------------

def _store_recovery_context(chat_id: str, summary: str, target_profile_id: str = "",
                            skip_targeting: bool = False) -> None:
    """Write a recovery summary into the compaction store.

    This is the single authorised write path for _compaction_summaries.
    All modules (including ws_handler) must call this instead of writing
    directly to state._compaction_summaries.

    target_profile_id: if set, only this agent should receive the recovery
    context in a group chat. If empty, auto-detects from last assistant message,
    then falls back to active_speaker_id from chat settings (survives crashes
    where the response was never saved to DB).

    skip_targeting: if True, deliver to whichever agent speaks next (no
    auto-detection). Use this for server-restart recovery where ALL agents
    lost context, not just the last speaker.
    """
    _compaction_summaries[chat_id] = summary
    if not skip_targeting:
        if not target_profile_id:
            target_profile_id = _get_last_assistant_speaker(chat_id)
        if not target_profile_id:
            # Crash mid-stream: response never saved, but active_speaker_id was
            # persisted to chat settings when the stream started.
            settings = _get_chat_settings(chat_id)
            target_profile_id = settings.get("active_speaker_id", "")
        if target_profile_id:
            _recovery_target[chat_id] = target_profile_id
    _recovery_skip_count.pop(chat_id, None)
    log(f"recovery context stored: chat={chat_id[:8]} len={len(summary)} target={target_profile_id or 'any'}")


def _generate_recovery_context(transcript: str) -> str:
    """Generate structured recovery context. Fallback chain: Grok → Haiku → Ollama."""
    system_prompt = (
        "Analyze this conversation transcript and produce a recovery briefing "
        "for an AI assistant resuming after a session reset.\n\n"
        "Format your response EXACTLY like this:\n"
        "## Task: [one-line description of what user was working on]\n"
        "## Intent: [what the user is trying to achieve — the WHY, not just the what. "
        "What will they do with the output? What's the end goal?]\n"
        "## Status: [in-progress | completed | blocked | idle]\n"
        "## Last Action: [what was happening right before this point]\n"
        "## Pending: [any unanswered questions, unresolved decisions, or concrete next steps — 'none' if clear]\n"
        "## Key Decisions: [important choices made during the conversation]\n\n"
        "## Guidance\n"
        "Extract actionable directives from the conversation using these tags:\n"
        "- [enforce] things that MUST be done a specific way (e.g., 'enforce: use dev branch for all Apex changes')\n"
        "- [avoid] things that failed or were rejected (e.g., 'avoid: nohup for server launch — use tmux')\n"
        "- [correction] user corrections to assistant mistakes (e.g., 'correction: price data must come from Tradier, not Alpaca')\n"
        "- [decision] choices made that should persist (e.g., 'decision: using Grok 4 Fast for compaction model')\n"
        "- [pending] unresolved items requiring follow-up\n"
        "List each as a bullet with the tag. If none exist for a category, omit it.\n\n"
        "Rules:\n"
        "- Be concise — this gets injected into a fresh AI session\n"
        "- NEVER include raw JSON, tool results, API responses, or code blocks in guidance items. "
        "Distill to plain English facts. 'correction: the DB path was wrong' NOT 'correction: {\"tool_use_id\": \"toolu_01...\", ...}'\n"
        "- Pending items must be SPECIFIC and actionable, not vague. "
        "'pending: user needs to review the 606 session summaries and decide which to feed into redigest' "
        "NOT 'pending: user to decide on next batch after review'\n"
        "- If the conversation was idle/casual, just say Status: idle\n"
        "- If a task was mid-execution (code being written, build in progress), say Status: in-progress\n"
        "- Focus on what the assistant needs to CONTINUE, not rehash\n"
        "- Guidance items must be model-agnostic — no reasoning-style prose, just directives"
    )

    # --- 1. Prefer xAI (Grok) if API key is available ---
    if XAI_API_KEY and _get_model_backend(COMPACTION_MODEL) == "xai":
        payload = json.dumps({
            "model": COMPACTION_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Transcript:\n{transcript}"},
            ],
            "max_tokens": 1024,
        }).encode()
        req = urllib.request.Request(
            "https://api.x.ai/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {XAI_API_KEY}",
                "User-Agent": "Apex/1.0",
            },
        )
        try:
            resp = urllib.request.urlopen(req, timeout=COMPACTION_TIMEOUT)
            body = json.loads(resp.read().decode())
            log("recovery: xai OK")
            return body["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if hasattr(e, 'read') else ""
            log(f"recovery (xAI) failed: {e} body={error_body[:300]}")
        except Exception as e:
            log(f"recovery (xAI) failed: {e}")

    # --- 2. Fallback: Haiku via Anthropic Messages API ---
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        _HAIKU_MODEL = "claude-haiku-4-5-20251001"
        payload = json.dumps({
            "model": _HAIKU_MODEL,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": f"Transcript:\n{transcript}"},
            ],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
                "User-Agent": "Apex/1.0",
            },
        )
        try:
            resp = urllib.request.urlopen(req, timeout=COMPACTION_TIMEOUT)
            body = json.loads(resp.read().decode())
            text = body.get("content", [{}])[0].get("text", "").strip()
            if text:
                log("recovery: haiku OK")
                return text
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if hasattr(e, 'read') else ""
            log(f"recovery (Haiku) failed: {e} body={error_body[:300]}")
        except Exception as e:
            log(f"recovery (Haiku) failed: {e}")

    # --- 3. Fallback: Ollama local model ---
    payload = json.dumps({
        "model": COMPACTION_OLLAMA_FALLBACK,
        "stream": False,
        "prompt": f"{system_prompt}\n\nTranscript:\n{transcript}",
    }).encode()
    req = urllib.request.Request(
        COMPACTION_OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=COMPACTION_TIMEOUT)
        body = json.loads(resp.read().decode())
        text = body.get("response", "").strip()
        if text:
            log("recovery: ollama OK")
            return text
    except Exception as e:
        log(f"recovery (Ollama) failed: {e}")
    return ""


# ---------------------------------------------------------------------------
# Auto-compaction
# ---------------------------------------------------------------------------

async def _maybe_compact_chat(chat_id: str) -> bool:
    """Check if chat needs compaction. If so, summarize + rotate session.

    Returns True if compaction was performed.
    """
    if COMPACTION_THRESHOLD <= 0:
        return False

    cumulative = await asyncio.to_thread(_get_cumulative_tokens_in, chat_id)
    if cumulative < COMPACTION_THRESHOLD:
        return False

    log(f"compaction triggered: chat={chat_id} tokens_in={cumulative} threshold={COMPACTION_THRESHOLD}")

    transcript = await asyncio.to_thread(_get_recent_messages_text, chat_id, 30)
    summary = await asyncio.to_thread(_generate_recovery_context, transcript)

    if summary:
        _store_recovery_context(chat_id, summary)
    else:
        _store_recovery_context(chat_id,
            "(Auto-compaction occurred but summary generation failed. "
            "The user's recent conversation history is in the database.)"
        )

    _last_compacted_at[chat_id] = _now()

    # Lazy import to avoid circular dependency
    from streaming import _disconnect_client, _send_stream_event
    await _disconnect_client(chat_id)
    _update_chat(chat_id, claude_session_id=None)
    _clear_session_context(chat_id)

    await _send_stream_event(chat_id, {
        "type": "system",
        "subtype": "compaction",
        "message": f"Session auto-compacted ({cumulative:,} input tokens). Context preserved via summary.",
    })

    log(f"compaction complete: chat={chat_id}")
    return True


# ---------------------------------------------------------------------------
# Workspace context injection — APEX.md + MEMORY.md on first message
# ---------------------------------------------------------------------------

def _get_recent_exchange_context(chat_id: str, pairs: int = 2) -> str:
    """Get the last N user/assistant exchange pairs for session continuity."""
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE chat_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (chat_id, pairs * 2 + 4),
        ).fetchall()
        conn.close()
    if not rows:
        return ""
    rows.reverse()
    exchanges: list[str] = []
    i = len(rows) - 1
    while i >= 0 and len(exchanges) < pairs * 2:
        role, content, ts = rows[i]
        if role in ("user", "assistant") and content and content.strip():
            text = content.strip()[:600]
            if role == "assistant":
                text = text[:400]
            exchanges.append(f"[{role}] {text}")
        i -= 1
    if not exchanges:
        return ""
    exchanges.reverse()
    block = "\n\n".join(exchanges)
    return (
        f"<system-reminder>\n# Recent Conversation (last {pairs} exchanges)\n"
        f"Here are the most recent messages from this chat for continuity:\n\n"
        f"{block}\n\n"
        f"Use this context to maintain conversational continuity. "
        f"Do not repeat or summarize these messages — just continue naturally.\n</system-reminder>"
    )


def _get_profile_prompt(chat_id: str) -> str:
    """Get the agent profile system prompt for this chat.

    For system personas with signed prompts, verifies integrity against
    the canonical digest. Tampered prompts are rejected and replaced
    with the hardcoded original.
    """
    override_pid = _group_profile_override.pop(chat_id, None)
    if override_pid:
        return _get_profile_prompt_by_id(override_pid)
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT ap.system_prompt, ap.system_prompt_override, ap.name, ap.id, ap.is_system "
            "FROM agent_profiles ap "
            "INNER JOIN chats c ON c.profile_id = ap.id "
            "WHERE c.id = ?", (chat_id,)
        ).fetchone()
        conn.close()
    if not row:
        return ""
    base_prompt, override_prompt, name, profile_id, is_system = row
    # For signed system personas: verify base prompt integrity
    if is_system:
        base_prompt = verify_system_prompt(profile_id, base_prompt or "")
    # Use override if set, otherwise base
    effective = (override_prompt.strip() if override_prompt else "") or base_prompt or ""
    if not effective:
        return ""
    return f"<system-reminder>\n# Agent Profile: {name}\n{effective}\n</system-reminder>\n\n"


def _get_profile_prompt_by_id(profile_id: str) -> str:
    """Get the agent profile system prompt by profile_id directly."""
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT system_prompt, system_prompt_override, name, is_system "
            "FROM agent_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        conn.close()
    if not row:
        return ""
    base_prompt, override_prompt, name, is_system = row
    if is_system:
        base_prompt = verify_system_prompt(profile_id, base_prompt or "")
    effective = (override_prompt.strip() if override_prompt else "") or base_prompt or ""
    if not effective:
        return ""
    return f"<system-reminder>\n# Agent Profile: {name}\n{effective}\n</system-reminder>\n\n"


def _resolve_memory_profile_id(chat_id: str, active_profile_id: str = "") -> str:
    """Return the profile whose persistent memory should be used for this turn."""
    if active_profile_id:
        return active_profile_id
    chat = _get_chat(chat_id)
    if not chat:
        return ""
    chat_type = chat.get("type") or "chat"
    chat_profile_id = str(chat.get("profile_id") or "").strip()
    if chat_type == "group":
        return chat_profile_id
    if chat_profile_id:
        return chat_profile_id
    return SYSTEM_PROFILE_ID


def _get_memory_prompt(chat_id: str, active_profile_id: str = "",
                       limit: int = 30, user_message: str = "") -> str:
    """Build persistent memory instructions for the effective profile of this chat."""
    memory_profile_id = _resolve_memory_profile_id(chat_id, active_profile_id=active_profile_id)
    if not memory_profile_id:
        return ""

    all_memories = _get_persona_memories(memory_profile_id, limit=max(80, limit * 3))
    scored = _score_memories(all_memories, user_message=user_message)
    memories = scored[:limit]

    # Bump access counters (inline — sub-ms on indexed rows)
    injected_ids = [m["id"] for m in memories]
    if injected_ids:
        try:
            _bump_memory_access(injected_ids)
        except Exception:
            pass

    lines: list[str] = []
    if memories:
        title = "## Your Persistent Memory"
        if memory_profile_id == SYSTEM_PROFILE_ID:
            title += " (shared open-model memory)"
        else:
            title += " (across all channels and groups)"
        lines.append(title)
        for mem in memories:
            cat_label = mem["category"].capitalize() if mem["category"] else "Note"
            lines.append(f"- [{cat_label}] {mem['content']}")

    lines.append("")
    lines.append("## Memory System")
    if memory_profile_id == SYSTEM_PROFILE_ID:
        lines.append("You are in an open-model chat with no persona attached.")
        lines.append("Important decisions, corrections, context, and tasks for these open chats are stored in a shared system memory pool.")
    else:
        lines.append("You have persistent memory that follows you across all channels and groups.")
    lines.append("To save something important, include a memory tag in your response:")
    lines.append('  <memory category="decision">What was decided and why</memory>')
    lines.append('  <memory category="correction">User preference or correction to remember</memory>')
    lines.append('  <memory category="context">Important context for future conversations</memory>')
    lines.append('  <memory category="task">Pending task or follow-up</memory>')
    lines.append("The tag will be stripped from the displayed message. Use sparingly — only for things worth remembering across sessions.")
    return "<system-reminder>\n# Persistent Memory\n" + "\n".join(lines).strip() + "\n</system-reminder>\n\n"


# --- Premium stubs: group roster + agent resolution ---
# Injected by apex.py when premium module is loaded. When _premium is None,
# these return empty/None — all downstream `if group_agent:` branches no-op.
_premium = None  # set to context_premium module by apex.py


def _get_group_queue_cap() -> int:
    try:
        from ws_handler import MAX_QUEUED_TURNS_PER_KEY
        return int(MAX_QUEUED_TURNS_PER_KEY)
    except Exception:
        return 2


def _get_profile_queued_turn_count(profile_id: str) -> int:
    if not profile_id:
        return 0
    total = 0
    for queue in _queued_turns.values():
        total += sum(1 for entry in queue if str(entry.get("profile_id") or "") == profile_id)
    return total


def _build_group_load_prompt(chat_id: str) -> str:
    members = _get_group_members(chat_id)
    if not members:
        return ""

    queue_cap = _get_group_queue_cap()
    lines = [
        "# Agent Load",
        "Cross-chat activity for the current group roster:",
    ]
    for member in members:
        profile_id = str(member.get("profile_id") or "")
        active_count, active_age_s = _get_profile_active_stream_stats(profile_id)
        queued_count = _get_profile_queued_turn_count(profile_id)
        if active_count > 1 and active_age_s is not None:
            status = f"\U0001f534 active x{active_count} ({active_age_s}s), queue: {queued_count}/{queue_cap}"
        elif active_count == 1 and active_age_s is not None:
            status = f"\U0001f534 active ({active_age_s}s), queue: {queued_count}/{queue_cap}"
        elif queued_count > 0:
            status = f"\U0001f7e1 queued, queue: {queued_count}/{queue_cap}"
        else:
            status = "\U0001f7e2 idle"
        lines.append(
            f"- {member.get('name', 'Unknown')} [{profile_id}] {member.get('avatar', '')} — {status}"
        )
    return "<system-reminder>\n" + "\n".join(lines) + "\n</system-reminder>\n\n"


def _get_group_roster_prompt(chat_id: str, user_message: str = "") -> str:
    """Delegate to premium module, then append cross-chat load visibility."""
    if not _premium:
        return ""
    roster_prompt = _premium.get_group_roster_prompt(chat_id, user_message)
    if not roster_prompt:
        return ""
    authoritative_note = (
        "The channel roster above is authoritative. "
        "Use it to determine who is in the room and who can be @mentioned. "
        "Do not claim the room roster is unavailable, and ignore SDK client counts or other inferred presence signals.\n"
    )
    if "</system-reminder>" in roster_prompt:
        roster_prompt = roster_prompt.replace(
            "</system-reminder>",
            f"{authoritative_note}</system-reminder>",
            1,
        )
    else:
        roster_prompt = (
            f"{roster_prompt}<system-reminder>\n{authoritative_note}</system-reminder>\n\n"
        )
    load_prompt = _build_group_load_prompt(chat_id)
    relay_prompt = _build_group_relay_state_prompt(chat_id)
    parts = [roster_prompt]
    if load_prompt:
        parts.append(load_prompt)
    if relay_prompt:
        parts.append(relay_prompt)
    return "".join(parts)


def _resolve_group_agent(chat_id: str, chat: dict, prompt: str) -> dict | None:
    """Delegate to premium module, or return None (disabling all group routing)."""
    return _premium.resolve_group_agent(chat_id, chat, prompt) if _premium else None


def _get_transcript_tail(chat_id: str, max_chars: int = 0) -> str:
    """Read the tail of a chat's conversation for recovery injection.

    Tries the DB first (always fresh), falls back to JSONL export files.
    Returns a formatted string of the last N characters of conversation,
    showing content from the most recent entries.
    Returns empty string if no data found.
    """
    if max_chars <= 0:
        max_chars = _TRANSCRIPT_TAIL_CHARS
    if max_chars <= 0:
        log(f"transcript tail SKIP: chat={chat_id[:8]} max_chars={max_chars} (APEX_TRANSCRIPT_TAIL_CHARS={_TRANSCRIPT_TAIL_CHARS})")
        return ""

    # --- Try DB first (always up to date) ---
    tail = _get_transcript_tail_from_db(chat_id, max_chars)
    if tail:
        return tail
    log(f"transcript tail (db): chat={chat_id[:8]} returned empty, trying JSONL fallback")

    # --- Fallback: JSONL export files ---
    tail = _get_transcript_tail_from_jsonl(chat_id, max_chars)
    if not tail:
        log(f"transcript tail: chat={chat_id[:8]} BOTH sources returned empty")
    return tail


def _get_transcript_tail_from_db(chat_id: str, max_chars: int) -> str:
    """Read recent messages directly from the SQLite DB."""
    try:
        result = _get_messages(chat_id, limit=20)
        recent = result.get("messages", []) if isinstance(result, dict) else result
        if not recent:
            log(f"transcript tail (db): chat={chat_id[:8]} _get_messages returned {len(recent) if recent else 0} messages (DB_PATH={getattr(__import__('db'), 'DB_PATH', '?')})")
            return ""

        parts: list[str] = []
        for msg in recent:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if not content:
                continue
            speaker = msg.get("speaker_name", "")
            label = f"{speaker} ({role})" if speaker else role
            parts.append(f"[{label}] {content}")

        if not parts:
            return ""

        transcript = "\n".join(parts)
        if len(transcript) > max_chars:
            transcript = transcript[-max_chars:]
            nl = transcript.find("\n")
            if nl > 0:
                transcript = transcript[nl + 1:]

        log(f"transcript tail (db): chat={chat_id[:8]} chars={len(transcript)}")
        return transcript
    except Exception as e:
        log(f"transcript tail (db) failed: chat={chat_id[:8]} err={e}")
        return ""


def _get_transcript_tail_from_jsonl(chat_id: str, max_chars: int) -> str:
    """Read recent messages from JSONL export files (fallback)."""
    jsonl_name = f"apex_{chat_id}.jsonl"
    jsonl_path = None
    for d in _TRANSCRIPT_DIRS:
        candidate = d / jsonl_name
        if candidate.exists():
            jsonl_path = candidate
            break
    if not jsonl_path:
        return ""

    try:
        with open(jsonl_path, "rb") as f:
            # Seek to tail — read last 64KB max to avoid loading huge files
            f.seek(0, 2)
            size = f.tell()
            read_from = max(0, size - 65536)
            f.seek(read_from)
            tail_bytes = f.read()

        lines = tail_bytes.decode("utf-8", errors="replace").strip().split("\n")
        # Skip partial first line if we seeked mid-file
        if read_from > 0 and lines:
            lines = lines[1:]

        parts: list[str] = []
        for line in lines:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = obj.get("message", {})
            role = msg.get("role", "")
            content = msg.get("content", "")
            thinking = msg.get("thinking", "")
            if not content and not thinking:
                continue
            if thinking:
                parts.append(f"[{role} thinking] {thinking}")
            if content:
                parts.append(f"[{role}] {content}")

        if not parts:
            return ""

        transcript = "\n".join(parts)
        if len(transcript) > max_chars:
            transcript = transcript[-max_chars:]
            nl = transcript.find("\n")
            if nl > 0:
                transcript = transcript[nl + 1:]

        log(f"transcript tail (jsonl): chat={chat_id[:8]} chars={len(transcript)}")
        return transcript
    except Exception as e:
        log(f"transcript tail (jsonl) failed: chat={chat_id[:8]} err={e}")
        return ""


def _build_recovery_block(chat_id: str, summary: str) -> str:
    """Assemble the full recovery system-reminder with summary + transcript tail."""
    transcript_tail = _get_transcript_tail(chat_id)
    tail_block = ""
    if transcript_tail:
        tail_block = (
            f"\n\n## Prior Session Transcript (last {len(transcript_tail)} chars)\n"
            f"This is the raw tail of your conversation just before the reset:\n"
            f"```\n{transcript_tail}\n```\n"
        )
    briefing = summary if summary else "(Summary generation failed — use transcript below.)"
    return (
        f"<system-reminder>\n# Session Recovery\n"
        f"You are resuming a conversation after a session reset.\n\n"
        f"## Recovery Briefing\n{briefing}\n"
        f"{tail_block}\n"
        f"IMPORTANT: Pick up where you left off. If a task was in-progress, continue it. "
        f"If questions were pending, address them. Do not start over or re-introduce yourself.\n</system-reminder>"
    )


def _try_consume_recovery(chat_id: str) -> str | None:
    """Try to consume recovery context for the current agent.

    Returns the summary text if this agent should get it, or None if:
    - No recovery context exists
    - Recovery is targeted at a different agent (left for them)
    Safety valve: after 3 skips, deliver to whoever asks.
    """
    if chat_id not in _compaction_summaries:
        return None
    target_pid = _recovery_target.get(chat_id, "")
    current_pid = _current_group_profile_id.get("")
    if target_pid and current_pid and target_pid != current_pid:
        skip_count = _recovery_skip_count.get(chat_id, 0) + 1
        _recovery_skip_count[chat_id] = skip_count
        if skip_count < 3:
            log(f"recovery skip: chat={chat_id[:8]} target={target_pid} current={current_pid} skip={skip_count}")
            return None
        log(f"recovery safety valve: chat={chat_id[:8]} delivering to {current_pid} after {skip_count} skips (target was {target_pid})")
    summary = _compaction_summaries.pop(chat_id, None)
    _recovery_target.pop(chat_id, None)
    _recovery_skip_count.pop(chat_id, None)
    return summary


def _get_session_context_key(chat_id_or_key: str) -> str:
    """Resolve workspace-context scope to chat_id:profile_id for group turns."""
    if ":" in chat_id_or_key:
        return chat_id_or_key
    current_pid = _current_group_profile_id.get("")
    return f"{chat_id_or_key}:{current_pid}" if current_pid else chat_id_or_key


def _get_workspace_context(chat_id: str) -> str:
    """Load APEX.md + MEMORY.md + skills catalog once per session for Claude Code parity."""
    session_key = _get_session_context_key(chat_id)
    if session_key in _session_context_sent:
        summary = _try_consume_recovery(chat_id)
        if summary is not None:
            log(f"Injecting recovery context for session={session_key}")
            recovery_block = _build_recovery_block(chat_id, summary)
            live = _get_live_state_snapshot()
            return recovery_block + "\n\n" + live + "\n\n" if live else recovery_block + "\n\n"
        return ""
    parts: list[str] = []
    summary = _try_consume_recovery(chat_id)
    if summary is not None:
        parts.append(_build_recovery_block(chat_id, summary))
    apex_md = WORKSPACE / "APEX.md"
    claude_md = WORKSPACE / "CLAUDE.md"
    project_md = apex_md if apex_md.exists() else claude_md
    memory_md = WORKSPACE / "memory" / "MEMORY.md"
    skills_dir = WORKSPACE / "skills"
    if project_md.exists():
        parts.append(f"<system-reminder>\n# Project Instructions\n{project_md.read_text()[:8000]}\n</system-reminder>")
    if memory_md.exists():
        parts.append(f"<system-reminder>\n# MEMORY.md (persistent memory)\n{memory_md.read_text()[:4000]}\n</system-reminder>")
    if skills_dir.is_dir():
        skill_entries: list[str] = []
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            skill_name = skill_md.parent.name
            content = skill_md.read_text()
            desc = ""
            for line in content.split("\n"):
                if line.strip().startswith("description:"):
                    desc = line.split(":", 1)[1].strip().strip('"')
                    break
            run_scripts = list(skill_md.parent.glob("run_*"))
            if not run_scripts:
                skill_entries.append(f"### /{skill_name}\n{content[:2000]}")
            else:
                skill_entries.append(f"- `/{skill_name}` — {desc}")
        if skill_entries:
            catalog = "\n".join(skill_entries)
            parts.append(f"<system-reminder>\n# Available Skills\nYou can use these skills. For /recall, /codex, /grok the server handles dispatch automatically. For thinking skills, follow the instructions below.\n\n{catalog[:6000]}\n</system-reminder>")
    live = _get_live_state_snapshot()
    if live:
        parts.append(live)
    chat = _get_chat(chat_id)
    has_existing_session = bool(chat and chat.get("claude_session_id"))
    if not has_existing_session:
        recent = _get_recent_exchange_context(chat_id, pairs=2)
        if recent:
            parts.append(recent)
    if parts:
        _session_context_sent.add(session_key)
        ctx_parts = "APEX.md + MEMORY.md + skills"
        if not has_existing_session:
            ctx_parts += " + recent exchanges"
        log(f"Workspace context injected for session={session_key} ({ctx_parts})")
        return "\n\n".join(parts) + "\n\n"
    return ""


def _clear_session_context(chat_id_or_key: str) -> None:
    """Remove chat or session keys from the session-context-sent set.

    Use this instead of mutating _session_context_sent directly from outside
    context.py.  Called when a chat's model/profile is changed and the context
    must be re-injected on the next turn.
    """
    if ":" in chat_id_or_key:
        _session_context_sent.discard(chat_id_or_key)
        return
    prefix = f"{chat_id_or_key}:"
    stale_keys = {key for key in _session_context_sent if key == chat_id_or_key or key.startswith(prefix)}
    _session_context_sent.difference_update(stale_keys)


def _has_session_context(chat_id_or_key: str) -> bool:
    """Return True if workspace context has already been sent for this session scope."""
    return _get_session_context_key(chat_id_or_key) in _session_context_sent


# ---------------------------------------------------------------------------
# Subconscious whisper — inject guidance from background memory system
# ---------------------------------------------------------------------------

def _get_whisper_text(chat_id: str, current_prompt: str = "") -> str:
    """Inject relevant memories based on current conversation topic via embeddings."""
    now = time.time()
    last = _whisper_last.get(chat_id, 0)
    if last and (now - last) < WHISPER_INTERVAL:
        return ""
    try:
        query = (current_prompt or "")[:500]
        if not query:
            recent = _get_messages(chat_id, days=1)["messages"]
            user_msgs = [m for m in recent if m["role"] == "user"]
            if not user_msgs:
                return ""
            query = (user_msgs[-1].get("content") or "")[:500]

        if not query or query.startswith("/") or len(query.strip()) < 10:
            _whisper_last[chat_id] = now
            return ""

        if "<system-reminder>" in query:
            query = re.sub(r"<system-reminder>.*?</system-reminder>", "", query, flags=re.DOTALL).strip()
            if len(query) < 10:
                _whisper_last[chat_id] = now
                return ""

        embed_path = str(WORKSPACE / "skills" / "embedding")
        if embed_path not in sys.path:
            sys.path.insert(0, embed_path)
        import importlib
        _ms = importlib.import_module("memory_search")
        results = _ms.search(query, top_k=5, sources=["memory", "transcripts"])

        for r in results:
            if r.get("source") == "transcripts":
                r["score"] *= 0.6
            # Staleness decay: older memory files score lower
            fpath = Path(r.get("file", ""))
            if fpath.exists():
                age_days = (time.time() - fpath.stat().st_mtime) / 86400
                if age_days > 30:
                    r["score"] *= 0.6
                    r["_stale"] = True
                elif age_days > 14:
                    r["score"] *= 0.8
                    r["_stale"] = True
        results.sort(key=lambda x: x.get("score", 0), reverse=True)

        relevant = [r for r in results if r.get("score", 0) >= 0.55][:3]
        if not relevant:
            _whisper_last[chat_id] = now
            return ""

        lines = ["<subconscious_whisper>"]
        lines.append("Relevant memories for this conversation:")
        for r in relevant:
            name = Path(r["file"]).stem
            src = r.get("source", "memory")[:4]
            score_str = f"score={r['score']:.2f}"
            stale_tag = " STALE — verify before using" if r.get("_stale") else ""
            lines.append(f"- [{name}] ({src} {score_str}{stale_tag}) {r.get('content', '')[:200]}")
        lines.append("</subconscious_whisper>")

        _whisper_last[chat_id] = now
        log(f"Whisper injected for chat={chat_id} ({len(relevant)} memories)")
        return "\n".join(lines) + "\n\n"
    except Exception as e:
        log(f"Whisper error: {e}")
        return ""
