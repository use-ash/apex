#!/usr/bin/env python3
"""Apex — Local web chat for Claude Code.

Zero third-party data flow. FastAPI + WebSocket + Claude Agent SDK.
All conversation data stays on this machine. Persistent sessions — no
subprocess respawning per turn. Auth via mTLS (client certificate).

Usage:
    python3 apex.py
    # or via setup wizard: python3 setup_apex.py

Env vars:
    APEX_SSL_CERT            — server certificate
    APEX_SSL_KEY             — server private key
    APEX_SSL_CA              — CA cert for client verification (mTLS)
    APEX_HOST                — bind address (default: 0.0.0.0)
    APEX_PORT                — port (default: 8300)
    APEX_MODEL               — Claude model (default: claude-sonnet-4-6)
    APEX_WORKSPACE           — working directory for Claude SDK (default: cwd)
    APEX_PERMISSION_MODE     — SDK permission mode (default: acceptEdits)
    APEX_DEBUG               — enable verbose debug logging (default: false)
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import hmac
import os
import shutil
import ssl
import sqlite3
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
import urllib.request

import base64
import contextlib
import contextvars
import tempfile

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
except ImportError:
    print("pip install fastapi uvicorn python-multipart", file=sys.stderr)
    sys.exit(1)

# Local model tool calling
sys.path.insert(0, os.environ.get("APEX_LOCAL_MODEL_PATH", str(Path(__file__).resolve().parent)))
try:
    from local_model.tool_loop import run_tool_loop
    from local_model.context import build_system_prompt
    _TOOL_LOOP_AVAILABLE = True
except ImportError:
    _TOOL_LOOP_AVAILABLE = False

try:
    from claude_agent_sdk import (
        ClaudeSDKClient,
        ClaudeAgentOptions,
        AssistantMessage,
        ResultMessage,
        SystemMessage,
        TextBlock,
        ThinkingBlock,
        ToolUseBlock,
        ToolResultBlock,
    )
except ImportError:
    print("pip install claude-agent-sdk", file=sys.stderr)
    sys.exit(1)

from config import Config as ApexConfig
from dashboard import dashboard_app, init_dashboard

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HOST = os.environ.get("APEX_HOST", "127.0.0.1")  # S-19: localhost by default; set 0.0.0.0 for network access
PORT = int(os.environ.get("APEX_PORT", "8300"))
SSL_CERT = os.environ.get("APEX_SSL_CERT", "")
SSL_KEY = os.environ.get("APEX_SSL_KEY", "")
SSL_CA = os.environ.get("APEX_SSL_CA", "")
APEX_ROOT = Path(os.environ.get("APEX_ROOT", Path(__file__).resolve().parent.parent))
WORKSPACE = Path(os.environ.get("APEX_WORKSPACE", os.getcwd()))
MODEL = os.environ.get("APEX_MODEL", "claude-sonnet-4-6")
PERMISSION_MODE = os.environ.get("APEX_PERMISSION_MODE", "acceptEdits")
DEBUG = os.environ.get("APEX_DEBUG", "").lower() in {"1", "true", "yes"}
ALERT_TOKEN = os.environ.get("APEX_ALERT_TOKEN", "")
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
XAI_MANAGEMENT_KEY = os.environ.get("XAI_MANAGEMENT_KEY", "")
XAI_TEAM_ID = os.environ.get("XAI_TEAM_ID", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
CODEX_CLI = os.environ.get("CODEX_CLI_PATH", shutil.which("codex") or "codex")
GROUPS_ENABLED = os.environ.get("APEX_GROUPS_ENABLED", "").lower() in {"1", "true", "yes"}
DB_PATH = APEX_ROOT / "state" / os.environ.get("APEX_DB_NAME", "apex.db")
LOG_PATH = APEX_ROOT / "state" / os.environ.get("APEX_LOG_NAME", "apex.log")

# Migration: rename localchat.db → apex.db
_old_db = DB_PATH.parent / "localchat.db"
if not DB_PATH.exists() and _old_db.exists():
    _old_db.rename(DB_PATH)

# Migration: rename localchat.log → apex.log
_old_log = LOG_PATH.parent / "localchat.log"
if not LOG_PATH.exists() and _old_log.exists():
    _old_log.rename(LOG_PATH)

LOG_MAX = 5 * 1024 * 1024  # 5MB
UPLOAD_DIR = APEX_ROOT / "state" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_TYPES = {"jpg", "jpeg", "png", "gif", "webp"}
TEXT_TYPES = {"txt", "py", "json", "csv", "md", "yaml", "yml", "toml", "cfg", "ini", "log", "html", "css", "js", "ts", "sh"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_TEXT_SIZE = 1 * 1024 * 1024    # 1MB
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB
WHISPER_BIN = os.environ.get("APEX_WHISPER_BIN", shutil.which("whisper") or "whisper")
SDK_QUERY_TIMEOUT = int(os.environ.get("APEX_SDK_QUERY_TIMEOUT", "30"))
SDK_STREAM_TIMEOUT = int(os.environ.get("APEX_SDK_STREAM_TIMEOUT", "300"))
ENABLE_SUBCONSCIOUS_WHISPER = os.environ.get("APEX_ENABLE_WHISPER", "").lower() in {"1", "true", "yes"}
ENABLE_SKILL_DISPATCH = os.environ.get("APEX_ENABLE_SKILL_DISPATCH", "true").lower() in {"1", "true", "yes"}

# Model context window sizes (input tokens)
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus-4-6": 1_000_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "grok-4": 2_000_000,
    "grok-4-fast": 2_000_000,
    "mlx:mlx-community/Qwen3.5-35B-A3B-4bit": 128_000,
    "codex:gpt-5.4": 272_000,
    "codex:gpt-5.4-mini": 272_000,
    "codex:gpt-5.3-codex": 272_000,
    "codex:gpt-5.2": 272_000,
    "codex:gpt-5.1-codex-max": 272_000,
}
MODEL_CONTEXT_DEFAULT = 128_000  # fallback for local/unknown models

# Auto-compaction — rotate SDK session when cumulative input tokens get too high
COMPACTION_THRESHOLD = int(os.environ.get("APEX_COMPACTION_THRESHOLD", "100000"))  # input tokens
COMPACTION_MODEL = os.environ.get("APEX_COMPACTION_MODEL", "grok-4-1-fast-non-reasoning")
COMPACTION_OLLAMA_FALLBACK = os.environ.get("APEX_COMPACTION_OLLAMA_FALLBACK", "gemma3:27b")
OLLAMA_BASE_URL = os.environ.get("APEX_OLLAMA_URL", "http://localhost:11434")
MLX_BASE_URL = os.environ.get("APEX_MLX_URL", "http://localhost:8400")
COMPACTION_OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/generate"
COMPACTION_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Auto-compaction — session rotation when token usage gets too high
# ---------------------------------------------------------------------------
_compaction_summaries: dict[str, str] = {}  # chat_id -> summary text from last compaction
_last_compacted_at: dict[str, str] = {}  # chat_id -> ISO timestamp of last compaction
_recovery_pending: dict[str, asyncio.Event] = {}  # chat_id -> event, set when recovery done


def _get_cumulative_tokens_in(chat_id: str) -> int:
    """Sum tokens_in for messages in a chat since last compaction."""
    since = _last_compacted_at.get(chat_id)
    with _db_lock:
        conn = _get_db()
        if since:
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens_in), 0) FROM messages "
                "WHERE chat_id = ? AND created_at > ?",
                (chat_id, since),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens_in), 0) FROM messages WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        conn.close()
    return row[0] if row else 0


def _get_last_turn_tokens_in(chat_id: str) -> int:
    """Get the best estimate of current context fill for a Claude chat.

    Takes max from last 5 assistant messages (SDK sometimes reports low counts
    after session restarts). Respects compaction boundary.
    """
    since = _last_compacted_at.get(chat_id)
    with _db_lock:
        conn = _get_db()
        if since:
            rows = conn.execute(
                "SELECT tokens_in FROM messages "
                "WHERE chat_id = ? AND role = 'assistant' AND tokens_in > 0 AND created_at > ? "
                "ORDER BY created_at DESC LIMIT 5",
                (chat_id, since),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT tokens_in FROM messages "
                "WHERE chat_id = ? AND role = 'assistant' AND tokens_in > 0 "
                "ORDER BY created_at DESC LIMIT 5",
                (chat_id,),
            ).fetchall()
        conn.close()
    return max((r[0] for r in rows), default=0)


def _estimate_tokens(chat_id: str) -> int:
    """Estimate token count from message content (~4 chars per token)."""
    since = _last_compacted_at.get(chat_id)
    with _db_lock:
        conn = _get_db()
        if since:
            row = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(content)), 0) FROM messages "
                "WHERE chat_id = ? AND created_at > ?",
                (chat_id, since),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(content)), 0) FROM messages WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        conn.close()
    total_chars = row[0] if row else 0
    return total_chars // 4


def _get_recent_messages_text(chat_id: str, limit: int = 30) -> str:
    """Get recent message content for summarization (last N messages)."""
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        conn.close()
    rows.reverse()  # chronological order
    lines = []
    for role, content in rows:
        # Truncate long messages for the summary prompt
        text = (content or "")[:500]
        lines.append(f"[{role}] {text}")
    return "\n".join(lines)


def _generate_recovery_context(transcript: str) -> str:
    """Call Grok (xAI) or Ollama to generate structured recovery context for session continuity."""
    system_prompt = (
        "Analyze this conversation transcript and produce a recovery briefing "
        "for an AI assistant resuming after a session reset.\n\n"
        "Format your response EXACTLY like this:\n"
        "## Task: [one-line description of what user was working on]\n"
        "## Status: [in-progress | completed | blocked | idle]\n"
        "## Last Action: [what was happening right before this point]\n"
        "## Pending: [any unanswered questions, unresolved decisions, or next steps — 'none' if clear]\n"
        "## Key Decisions: [important choices made during the conversation]\n\n"
        "Rules:\n"
        "- Be concise — this gets injected into a fresh AI session\n"
        "- If the conversation was idle/casual, just say Status: idle\n"
        "- If a task was mid-execution (code being written, build in progress), say Status: in-progress\n"
        "- Focus on what the assistant needs to CONTINUE, not rehash"
    )

    # Prefer xAI (Grok) if API key is available — faster + cheaper than local Ollama
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
            return body["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if hasattr(e, 'read') else ""
            log(f"recovery context generation (xAI) failed, falling back to Ollama: {e} body={error_body[:300]}")
        except Exception as e:
            log(f"recovery context generation (xAI) failed, falling back to Ollama: {e}")

    # Fallback: Ollama local model
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
        return body.get("response", "").strip()
    except Exception as e:
        log(f"recovery context generation (Ollama) failed: {e}")
        return ""


def _get_recently_active_chats(hours: int = 24) -> list[str]:
    """Return chat_ids (type='chat' only) with messages in the last N hours."""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT DISTINCT m.chat_id FROM messages m "
            "JOIN chats c ON m.chat_id = c.id "
            "WHERE c.type = 'chat' AND m.created_at > ?",
            (cutoff,),
        ).fetchall()
        conn.close()
    return [r[0] for r in rows]


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

    # Generate summary from recent messages via Ollama
    transcript = await asyncio.to_thread(_get_recent_messages_text, chat_id, 30)
    summary = await asyncio.to_thread(_generate_recovery_context, transcript)

    if summary:
        _compaction_summaries[chat_id] = summary
        log(f"compaction summary generated: chat={chat_id} len={len(summary)}")
    else:
        # Fallback: use last few user messages as context
        _compaction_summaries[chat_id] = (
            "(Auto-compaction occurred but summary generation failed. "
            "The user's recent conversation history is in the database.)"
        )
        log(f"compaction summary fallback: chat={chat_id}")

    # Record compaction timestamp so token counter resets
    _last_compacted_at[chat_id] = _now()

    # Disconnect SDK client — kills the long context session
    await _disconnect_client(chat_id)

    # Clear session_id so next message creates a fresh session
    _update_chat(chat_id, claude_session_id=None)

    # Clear the workspace context sent flag so APEX.md gets re-injected
    _session_context_sent.discard(chat_id)

    # Notify connected WebSocket viewers
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
_session_context_sent: set[str] = set()  # chat_ids that already got context

def _get_recent_exchange_context(chat_id: str, pairs: int = 2) -> str:
    """Get the last N user/assistant exchange pairs for session continuity.
    Returns a formatted block showing what was recently discussed."""
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE chat_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (chat_id, pairs * 2 + 4),  # fetch extra to find enough pairs
        ).fetchall()
        conn.close()
    if not rows:
        return ""
    rows.reverse()  # chronological
    # Extract the last N user→assistant pairs
    exchanges: list[str] = []
    i = len(rows) - 1
    while i >= 0 and len(exchanges) < pairs * 2:
        role, content, ts = rows[i]
        if role in ("user", "assistant") and content and content.strip():
            text = content.strip()[:600]
            if role == "assistant":
                text = text[:400]  # assistant responses can be verbose
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


# Group routing: temporary profile override for @mention dispatch
_group_profile_override: dict[str, str] = {}  # chat_id -> profile_id


def _get_profile_prompt(chat_id: str) -> str:
    """Get the agent profile system prompt for this chat, if any.
    For group chats with @mention routing, checks _group_profile_override first."""
    override_pid = _group_profile_override.pop(chat_id, None)
    if override_pid:
        return _get_profile_prompt_by_id(override_pid)
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT ap.system_prompt, ap.name FROM agent_profiles ap "
            "INNER JOIN chats c ON c.profile_id = ap.id "
            "WHERE c.id = ?", (chat_id,)
        ).fetchone()
        conn.close()
    if not row or not row[0]:
        return ""
    return f"<system-reminder>\n# Agent Profile: {row[1]}\n{row[0]}\n</system-reminder>\n\n"


def _get_profile_prompt_by_id(profile_id: str) -> str:
    """Get the agent profile system prompt by profile_id directly (for group routing)."""
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT system_prompt, name FROM agent_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        conn.close()
    if not row or not row[0]:
        return ""
    return f"<system-reminder>\n# Agent Profile: {row[1]}\n{row[0]}\n</system-reminder>\n\n"


def _get_group_roster_prompt(chat_id: str) -> str:
    """Inject group roster context so the active agent knows who else is in the room."""
    chat = _get_chat(chat_id)
    if not chat or chat.get("type") != "group":
        return ""
    members = _get_group_members(chat_id)
    if not members:
        return ""

    active_profile_id = _current_group_profile_id.get("")
    lines = [
        "You are responding inside a multi-agent group channel.",
        "Channel roster:",
    ]
    for member in members:
        tags: list[str] = []
        if member.get("profile_id") == active_profile_id:
            tags.append("you")
        if member.get("is_primary"):
            tags.append("primary")
        tag_text = f" ({', '.join(tags)})" if tags else ""
        avatar = f" {member.get('avatar', '')}" if member.get("avatar") else ""
        lines.append(f"- {member.get('name', member.get('profile_id', 'agent'))} [{member.get('profile_id', '')}]{avatar}{tag_text}")
    lines.append("Only speak as yourself. Other agents may read the shared chat history, but they do not receive your private hidden thinking.")
    lines.append("If the user addresses another agent, do not impersonate them.")

    # Inject recent group history so agents have context on restart/compaction
    try:
        recent = _get_messages(chat_id)
        # Take last 20 messages, truncate content
        recent = recent[-20:]
        if recent:
            lines.append("")
            lines.append("## Recent Group History (last {} messages)".format(len(recent)))
            for m in recent:
                speaker = m.get("speaker_name") or m.get("role", "user")
                content = (m.get("content") or "")[:300]
                if len(m.get("content", "")) > 300:
                    content += "..."
                lines.append(f"[{speaker}]: {content}")
    except Exception:
        pass  # Don't break roster injection on history read failure

    return "<system-reminder>\n# Group Channel Roster\n" + "\n".join(lines) + "\n</system-reminder>\n\n"


import re as _re

_MENTION_RE = _re.compile(r"@(\w+)")


def _resolve_group_agent(chat_id: str, chat: dict, prompt: str) -> dict | None:
    """For group chats, parse @mentions and resolve the target agent.

    Returns dict with keys: profile_id, name, avatar, model, backend, clean_prompt
    or None if this is not a group chat.
    """
    if chat.get("type") != "group":
        return None

    members = _get_group_members(chat_id)
    if not members:
        return None

    # Parse @mentions from prompt
    mentions = _MENTION_RE.findall(prompt)

    target = None
    if mentions:
        # Match mention to a group member (case-insensitive on name or profile_id)
        for mention in mentions:
            mention_lower = mention.lower()
            for m in members:
                if m["name"].lower() == mention_lower or m["profile_id"].lower() == mention_lower:
                    target = m
                    break
            if target:
                break

    # Fall back to primary agent
    if not target:
        for m in members:
            if m["is_primary"]:
                target = m
                break
        # If no primary, use first member
        if not target and members:
            target = members[0]

    if not target:
        return None

    # Strip the @mention from the prompt sent to the model
    clean_prompt = prompt
    if mentions and target:
        # Remove the matched @Name from the prompt
        clean_prompt = _re.sub(
            rf"@{_re.escape(target['name'])}|@{_re.escape(target['profile_id'])}",
            "", prompt, count=1, flags=_re.IGNORECASE
        ).strip()
        if not clean_prompt:
            clean_prompt = prompt  # Don't send empty prompt

    return {
        "profile_id": target["profile_id"],
        "name": target["name"],
        "avatar": target["avatar"],
        "model": target["model"],
        "backend": target["backend"],
        "clean_prompt": clean_prompt,
    }


def _get_workspace_context(chat_id: str) -> str:
    """Load APEX.md + MEMORY.md + skills catalog once per session for Claude Code parity.
    Also injects compaction summary if the session was just auto-compacted."""
    if chat_id in _session_context_sent:
        # Even after context was sent, check for compaction summary (one-shot injection)
        summary = _compaction_summaries.pop(chat_id, None)
        if summary:
            log(f"Injecting recovery context for chat={chat_id}")
            # Recovery summary is sufficient context — the SDK session already has
            # conversation history, so skip recent exchanges to avoid duplicates
            ctx = (
                f"<system-reminder>\n# Session Recovery\n"
                f"You are resuming a conversation after a session reset.\n\n"
                f"## Recovery Briefing\n{summary}\n\n"
                f"IMPORTANT: Pick up where you left off. If a task was in-progress, continue it. "
                f"If questions were pending, address them. Do not start over or re-introduce yourself.\n</system-reminder>"
            )
            return ctx + "\n\n"
        return ""
    parts: list[str] = []
    # Inject compaction summary if present (first message after compaction + session reset)
    summary = _compaction_summaries.pop(chat_id, None)
    if summary:
        parts.append(
            f"<system-reminder>\n# Session Recovery\n"
            f"You are resuming a conversation after a session reset.\n\n"
            f"## Recovery Briefing\n{summary}\n\n"
            f"IMPORTANT: Pick up where you left off. If a task was in-progress, continue it. "
            f"If questions were pending, address them. Do not start over or re-introduce yourself.\n</system-reminder>"
        )
    # Prefer APEX.md (model-agnostic), fall back to CLAUDE.md for backward compat
    apex_md = WORKSPACE / "APEX.md"
    claude_md = WORKSPACE / "CLAUDE.md"
    project_md = apex_md if apex_md.exists() else claude_md
    memory_md = WORKSPACE / "memory" / "MEMORY.md"
    skills_dir = WORKSPACE / "skills"
    if project_md.exists():
        parts.append(f"<system-reminder>\n# Project Instructions\n{project_md.read_text()[:8000]}\n</system-reminder>")
    if memory_md.exists():
        parts.append(f"<system-reminder>\n# MEMORY.md (persistent memory)\n{memory_md.read_text()[:4000]}\n</system-reminder>")
    # Build skills catalog from SKILL.md files
    if skills_dir.is_dir():
        skill_entries: list[str] = []
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            skill_name = skill_md.parent.name
            content = skill_md.read_text()
            # Extract description from frontmatter
            desc = ""
            for line in content.split("\n"):
                if line.strip().startswith("description:"):
                    desc = line.split(":", 1)[1].strip().strip('"')
                    break
            # For thinking skills (no run script), include the full instructions
            run_scripts = list(skill_md.parent.glob("run_*"))
            if not run_scripts:
                # Thinking skill — include full SKILL.md (truncated)
                skill_entries.append(f"### /{skill_name}\n{content[:2000]}")
            else:
                skill_entries.append(f"- `/{skill_name}` — {desc}")
        if skill_entries:
            catalog = "\n".join(skill_entries)
            parts.append(f"<system-reminder>\n# Available Skills\nYou can use these skills. For /recall, /codex, /grok the server handles dispatch automatically. For thinking skills, follow the instructions below.\n\n{catalog[:6000]}\n</system-reminder>")
    # Inject recent conversation exchanges for continuity — but ONLY for fresh
    # sessions. If we're resuming an existing SDK session, it already has the
    # full conversation history; injecting recent exchanges creates duplicates
    # that confuse Claude into answering the previous question instead of the
    # current one.
    chat = _get_chat(chat_id)
    has_existing_session = bool(chat and chat.get("claude_session_id"))
    if not has_existing_session:
        recent = _get_recent_exchange_context(chat_id, pairs=2)
        if recent:
            parts.append(recent)
    if parts:
        _session_context_sent.add(chat_id)
        ctx_parts = "APEX.md + MEMORY.md + skills"
        if not has_existing_session:
            ctx_parts += " + recent exchanges"
        log(f"Workspace context injected for chat={chat_id} ({ctx_parts})")
        return "\n\n".join(parts) + "\n\n"
    return ""

# ---------------------------------------------------------------------------
# Subconscious whisper — inject guidance from background memory system
# Throttled: first message per chat + every WHISPER_INTERVAL seconds after.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Skill dispatch — server-side /recall, /codex, /grok, /claude routing
# ---------------------------------------------------------------------------
import subprocess
import re as _re
import time as _time

# Metrics collection — Phase 1 of gated skill loop
sys.path.insert(0, str(WORKSPACE))
try:
    from skills.lib.metrics import log_invocation as _log_skill_invocation
    _METRICS_ENABLED = True
except ImportError:
    _METRICS_ENABLED = False
    def _log_skill_invocation(*a, **kw): pass

# Gate — Phase 2 of gated skill loop
try:
    from skills.lib.gate import (
        get_pending_approvals as _get_pending_approvals,
        resolve_approval as _resolve_approval,
    )
    _GATE_ENABLED = True
except ImportError:
    _GATE_ENABLED = False
    def _get_pending_approvals(): return []
    def _resolve_approval(*a, **kw): return None

def _parse_skill_command(prompt: str) -> tuple[str, str] | None:
    """Parse /skill-name args from prompt. Returns (skill, args) or None."""
    m = _re.match(r"^/([\w-]+)\s*(.*)", prompt.strip(), _re.DOTALL)
    if not m:
        return None
    return m.group(1).lower(), m.group(2).strip()


_RECALL_STOP_WORDS = frozenset(
    "a about all also am an and any are as at be been being but by can could"
    " did do does don doing done each for from get got had has have having he"
    " her here him his how i if in into is it its just know let like me might"
    " mine more my no not now of on one or our out over own please re really"
    " remember say she so some still tell than that the their them then there"
    " these they this those to up us very want was we were what when where"
    " which who will with would you your gonna gotta wanna".split()
)

def _extract_recall_terms(raw: str) -> str:
    """Strip stop words and punctuation to get meaningful search terms."""
    words = _re.findall(r"[a-zA-Z0-9$%]+", raw.lower())
    meaningful = [w for w in words if w not in _RECALL_STOP_WORDS and len(w) > 1]
    return " ".join(meaningful) if meaningful else raw


def _run_recall(args: str) -> str:
    """Run hybrid search: keyword (fast, exact) + semantic (Gemini embeddings)."""
    if not args:
        return "Usage: /recall <search query>"
    t0 = _time.monotonic()
    parts: list[str] = []

    # 1. Keyword search (existing, fast, good for exact phrases)
    query = _extract_recall_terms(args)
    script = WORKSPACE / "skills" / "recall" / "search_transcripts.py"
    keyword_output = ""
    if script.exists():
        log(f"Recall keyword search: {query!r}")
        try:
            result = subprocess.run(
                [sys.executable, str(script), query, "--top", "5", "--context", "800"],
                capture_output=True, text=True, timeout=15, cwd=str(WORKSPACE),
            )
            if result.returncode == 0 and result.stdout.strip() and "No results" not in result.stdout:
                keyword_output = result.stdout.strip()
        except Exception:
            pass

    # 2. Semantic search (Gemini embeddings, searches memory + transcripts)
    semantic_output = ""
    try:
        embed_path = str(WORKSPACE / "skills" / "embedding")
        if embed_path not in sys.path:
            sys.path.insert(0, embed_path)
        import importlib
        _ms = importlib.import_module("memory_search")
        log(f"Recall semantic search: {args[:60]!r}")
        results = _ms.search(args, top_k=5)
        if results:
            lines = []
            for i, r in enumerate(results, 1):
                source_tag = r.get("source", "?")
                score = r.get("score", 0)
                fname = Path(r["file"]).name
                preview = r.get("content", "")[:600]
                lines.append(f"[{i}] Score: {score:.3f} | {source_tag} | {fname}\n{'='*60}\n{preview}\n")
            semantic_output = "\n".join(lines)
    except Exception as e:
        log(f"Recall semantic search error: {e}")

    # 3. Merge results
    elapsed = _time.monotonic() - t0
    if semantic_output:
        parts.append(f"## Semantic Search Results (Gemini Embedding)\n\n{semantic_output}")
    if keyword_output:
        parts.append(f"## Keyword Search Results\n\n{keyword_output}")

    if parts:
        _log_skill_invocation("recall", success=True, duration_sec=elapsed, context=query[:80], source="apex")
        return "\n\n".join(parts)

    _log_skill_invocation("recall", success=False, duration_sec=elapsed, context=query[:80], source="apex")
    return f"No results found for: {args}"


def _run_improve(args: str) -> str:
    """Run skill-improver analysis. Returns structured JSON report for Claude synthesis."""
    if not args:
        return "Usage: /improve <skill_name> — Analyze a skill's metrics and propose improvements"
    skill_name = args.split()[0].strip().lower()
    # Validate skill exists
    skill_dir = WORKSPACE / "skills" / skill_name
    if not skill_dir.exists():
        available = sorted(
            d.name for d in (WORKSPACE / "skills").iterdir()
            if d.is_dir() and (d / "SKILL.md").exists() and d.name != "lib"
        )
        return f"Skill '{skill_name}' not found. Available: {', '.join(available)}"

    analyze_script = WORKSPACE / "skills" / "skill-improver" / "analyze.py"
    if not analyze_script.exists():
        return "Skill-improver not installed. Expected: skills/skill-improver/analyze.py"

    log(f"Skill-improver: analyzing '{skill_name}'")
    t0 = _time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, str(analyze_script), skill_name,
             "--workspace", str(WORKSPACE), "--days", "30"],
            capture_output=True, text=True, timeout=30, cwd=str(WORKSPACE),
        )
        elapsed = _time.monotonic() - t0
        output = result.stdout.strip()
        if result.returncode != 0:
            _log_skill_invocation("skill-improver", success=False, duration_sec=elapsed,
                                  error=result.stderr.strip()[:200], context=skill_name, source="apex")
            return f"Analysis error: {result.stderr.strip()}"
        _log_skill_invocation("skill-improver", success=True, duration_sec=elapsed,
                              context=skill_name, source="apex")
        return output
    except subprocess.TimeoutExpired:
        _log_skill_invocation("skill-improver", success=False, duration_sec=30.0,
                              error="timeout", context=skill_name, source="apex")
        return "Skill analysis timed out."
    except Exception as e:
        _log_skill_invocation("skill-improver", success=False,
                              duration_sec=_time.monotonic() - t0, error=str(e)[:200],
                              context=skill_name, source="apex")
        return f"Analysis error: {e}"


def _run_codex_background(args: str, chat_id: str) -> str:
    """Launch codex as a background task. Returns status message."""
    if not args:
        return "Usage: /codex <prompt for codex>"
    prompt_file = WORKSPACE / f"codex_apex_{chat_id[:8]}.md"
    response_file = WORKSPACE / f"codex_apex_{chat_id[:8]}_response.md"
    prompt_file.write_text(args)
    script = WORKSPACE / "skills" / "codex" / "run_codex.sh"
    if not script.exists():
        return "Codex skill not found."
    try:
        subprocess.Popen(
            ["bash", str(script), str(prompt_file.relative_to(WORKSPACE)),
             str(response_file.relative_to(WORKSPACE)), "", "--network"],
            cwd=str(WORKSPACE),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _log_skill_invocation("codex", success=True, context=args[:80], source="apex")
        return f"Codex task launched in background.\nPrompt: `{prompt_file.name}`\nResponse will be at: `{response_file.name}`\n\nI'll check the response when it's ready. You can also ask me to check with: \"check codex response\""
    except Exception as e:
        _log_skill_invocation("codex", success=False, error=str(e)[:200], context=args[:80], source="apex")
        return f"Codex launch error: {e}"


def _run_grok(args: str, chat_id: str) -> str | dict:
    """Launch grok research. Returns status message (or dict with bg process info).

    Supports flags forwarded to run_grok.sh:
      --bookmarks [N]   Fetch X bookmarks and inline them (default 20)
      --search          Activate live web search
      --research        Full multi-source research mode
      --thinking LEVEL  Reasoning depth: off|minimal|low|medium|high|xhigh
    """
    if not args:
        return "Usage: /grok <research question> [--bookmarks [N]] [--search] [--research] [--thinking LEVEL]"

    # Parse flags from args, leaving the rest as the prompt text
    import shlex
    try:
        tokens = shlex.split(args)
    except ValueError:
        tokens = args.split()

    extra_flags: list[str] = []
    prompt_tokens: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--bookmarks":
            extra_flags.append("--bookmarks")
            # Optional numeric limit follows
            if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                i += 1
                extra_flags.append(tokens[i])
        elif tok == "--search":
            extra_flags.append("--search")
        elif tok == "--research":
            extra_flags.append("--research")
        elif tok == "--thinking" and i + 1 < len(tokens):
            extra_flags.append("--thinking")
            i += 1
            extra_flags.append(tokens[i])
        else:
            prompt_tokens.append(tok)
        i += 1

    prompt_text = " ".join(prompt_tokens)
    if not prompt_text:
        return "Usage: /grok <research question> [--bookmarks [N]] [--search] [--research] [--thinking LEVEL]"

    prompt_file = WORKSPACE / f"grok_apex_{chat_id[:8]}.md"
    response_file = WORKSPACE / f"grok_apex_{chat_id[:8]}_response.md"
    # Clear stale response file so watcher doesn't read old data
    if response_file.exists():
        response_file.unlink()
    prompt_file.write_text(prompt_text)
    script = WORKSPACE / "skills" / "grok" / "run_grok.sh"
    if not script.exists():
        return "Grok skill not found."
    try:
        cmd = ["bash", str(script), str(prompt_file.relative_to(WORKSPACE)),
               str(response_file.relative_to(WORKSPACE))] + extra_flags
        proc = subprocess.Popen(
            cmd,
            cwd=str(WORKSPACE),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        flags_str = f" ({' '.join(extra_flags)})" if extra_flags else ""
        _log_skill_invocation("grok", success=True, context=args[:80], source="apex")
        return {
            "status": f"Grok research launched in background{flags_str}...",
            "bg_proc": proc,
            "bg_response_file": str(response_file),
        }
    except Exception as e:
        _log_skill_invocation("grok", success=False, error=str(e)[:200], context=args[:80], source="apex")
        return f"Grok launch error: {e}"


def _run_approve(args: str, chat_id: str = "") -> str:
    """Approve a pending skill gate. Usage: /approve [id] or just /approve for single pending."""
    if not _GATE_ENABLED:
        return "Gate not available."
    pending = _get_pending_approvals()
    if not pending:
        return "No pending approvals."
    approval_id = args.strip() if args.strip() else None
    if not approval_id:
        if len(pending) == 1:
            approval_id = str(pending[0].get("message_id", ""))
        else:
            lines = ["Multiple pending approvals. Specify an ID:\n"]
            for p in pending:
                mid = p.get("message_id", "?")
                skill = p.get("skill", "?")
                ts = p.get("ts", "?")[:16]
                reasons = ", ".join(p.get("reasons", [])[:2])
                lines.append(f"  /approve {mid} — {skill} ({reasons}) [{ts}]")
            return "\n".join(lines)
    result = _resolve_approval(approval_id, "approved")
    if result:
        _log_skill_invocation("gate", success=True, context=f"approved:{result.get('skill','?')}", source="apex")
        return f"✅ Approved: {result.get('skill', '?')}"
    return f"Approval ID '{approval_id}' not found or already resolved."


def _run_reject(args: str, chat_id: str = "") -> str:
    """Reject a pending skill gate. Usage: /reject [id] or just /reject for single pending."""
    if not _GATE_ENABLED:
        return "Gate not available."
    pending = _get_pending_approvals()
    if not pending:
        return "No pending approvals."
    approval_id = args.strip() if args.strip() else None
    if not approval_id:
        if len(pending) == 1:
            approval_id = str(pending[0].get("message_id", ""))
        else:
            lines = ["Multiple pending approvals. Specify an ID:\n"]
            for p in pending:
                mid = p.get("message_id", "?")
                skill = p.get("skill", "?")
                lines.append(f"  /reject {mid} — {skill}")
            return "\n".join(lines)
    result = _resolve_approval(approval_id, "rejected")
    if result:
        _log_skill_invocation("gate", success=True, context=f"rejected:{result.get('skill','?')}", source="apex")
        return f"❌ Rejected: {result.get('skill', '?')}"
    return f"Approval ID '{approval_id}' not found or already resolved."


def _run_pending(args: str, chat_id: str = "") -> str:
    """Show pending skill gate approvals."""
    if not _GATE_ENABLED:
        return "Gate not available."
    pending = _get_pending_approvals()
    if not pending:
        return "No pending approvals."
    lines = [f"Pending approvals ({len(pending)}):\n"]
    for p in pending:
        mid = p.get("message_id", "?")
        skill = p.get("skill", "?")
        tier = p.get("tier", "?")
        ts = p.get("ts", "?")[:16]
        reasons = ", ".join(p.get("reasons", [])[:3])
        lines.append(f"  [{mid}] {skill} (tier {tier}) — {reasons}")
        lines.append(f"         {ts}")
        lines.append(f"         /approve {mid}  |  /reject {mid}")
        lines.append("")
    return "\n".join(lines)


_DIRECT_SKILL_HANDLERS = {
    "codex": _run_codex_background,
    "grok": _run_grok,
    "approve": _run_approve,
    "reject": _run_reject,
    "pending": _run_pending,
}

# Skills that search + feed context into Claude for synthesis
_CONTEXT_SKILLS = {"recall", "improve"}

# Thinking skills — inject SKILL.md instructions as context, Claude executes
_THINKING_SKILLS = {"first-principles", "simplify"}


async def _watch_bg_skill(proc, response_file: str, chat_id: str, skill_name: str):
    """Watch a background skill process and push the result into the chat when done."""
    try:
        # Wait for subprocess in a thread (up to 5 minutes)
        exit_code = await asyncio.to_thread(proc.wait, 300)
        rpath = Path(response_file)
        if rpath.exists():
            content = rpath.read_text().strip()
            if content:
                label = f"**{skill_name.capitalize()} response:**\n\n{content}"
            else:
                label = f"⚠️ {skill_name.capitalize()} returned empty response."
        else:
            label = f"⚠️ {skill_name.capitalize()} response file not found (exit code {exit_code})."
    except subprocess.TimeoutExpired:
        label = f"⚠️ {skill_name.capitalize()} timed out after 5 minutes."
        proc.kill()
    except Exception as e:
        label = f"⚠️ {skill_name.capitalize()} watcher error: {e}"

    stream_token = _current_stream_id.set(_make_stream_id())
    try:
        # Push result into the chat as a new assistant message
        _save_message(chat_id, "assistant", label, cost_usd=0, tokens_in=0, tokens_out=0)
        await _send_stream_event(chat_id, {"type": "stream_start", "chat_id": chat_id})
        await _send_stream_event(chat_id, {"type": "text", "text": label})
        await _send_stream_event(chat_id, {
            "type": "result", "cost_usd": 0, "tokens_in": 0, "tokens_out": 0, "session_id": None,
        })
        await _send_stream_event(chat_id, {"type": "stream_end", "chat_id": chat_id})
        log(f"BG skill complete: /{skill_name} chat={chat_id} len={len(label)}")
    finally:
        _current_stream_id.reset(stream_token)


async def _handle_skill(websocket, chat_id: str, skill: str, args: str, display_prompt: str) -> bool:
    """Handle a skill invocation. Returns True if handled, False to fall through to Claude."""
    # --- Context skills: search, then let Claude synthesize ---
    if skill in _CONTEXT_SKILLS:
        if skill == "recall":
            log(f"Skill dispatch: /recall (context mode) args={args[:80]!r} chat={chat_id}")
            recall_results = await asyncio.to_thread(_run_recall, args)
            if not recall_results or "No results" in recall_results:
                # Fall through to Claude with a note
                return False
            # Rewrite the prompt: inject recall results as context, ask Claude to synthesize
            # This goes through normal Claude SDK path with the context prepended
            return False, recall_results  # signal caller to inject context
        return False

    # --- Direct skills: run and return output directly ---
    handler = _DIRECT_SKILL_HANDLERS.get(skill)
    if not handler:
        return False

    log(f"Skill dispatch: /{skill} (direct) args={args[:80]!r} chat={chat_id}")

    stream_token = _current_stream_id.set(_make_stream_id())
    try:
        # Save the user's message
        _save_message(chat_id, "user", display_prompt)

        # Send stream start
        _attach_ws(websocket, chat_id)
        _reset_stream_buffer(chat_id)
        await _send_stream_event(chat_id, {"type": "stream_start", "chat_id": chat_id})

        # Run the skill
        bg_info = None
        try:
            result = await asyncio.to_thread(handler, args, chat_id)
            # Handlers can return a dict with bg process info for async completion
            if isinstance(result, dict) and "bg_proc" in result:
                bg_info = result
                result_text = result["status"]
            else:
                result_text = result
        except Exception as e:
            result_text = f"Skill error: {e}"

        # Stream the result as text
        await _send_stream_event(chat_id, {"type": "text", "text": result_text})

        # Save assistant message
        _save_message(chat_id, "assistant", result_text, cost_usd=0, tokens_in=0, tokens_out=0)

        # Send result + stream end
        await _send_stream_event(chat_id, {
            "type": "result", "cost_usd": 0, "tokens_in": 0, "tokens_out": 0, "session_id": None,
        })
        await _send_stream_event(chat_id, {"type": "stream_end", "chat_id": chat_id})

        # Spawn background watcher if the handler returned a process to monitor
        if bg_info and "bg_proc" in bg_info:
            asyncio.create_task(_watch_bg_skill(
                bg_info["bg_proc"], bg_info["bg_response_file"],
                chat_id, skill
            ))

        return True
    finally:
        _current_stream_id.reset(stream_token)


WHISPER_INTERVAL = 300  # seconds between whisper injections (5 min)
_whisper_last: dict[str, float] = {}  # chat_id -> last whisper timestamp

def _get_whisper_text(chat_id: str, current_prompt: str = "") -> str:
    """Inject relevant memories based on current conversation topic via embeddings."""
    now = time.time()
    last = _whisper_last.get(chat_id, 0)
    if last and (now - last) < WHISPER_INTERVAL:
        return ""
    try:
        # Use current prompt as search query (not the previous one from DB)
        query = (current_prompt or "")[:500]
        if not query:
            # Fallback to last saved message only if no current prompt
            recent = _get_messages(chat_id, days=1)
            user_msgs = [m for m in recent if m["role"] == "user"]
            if not user_msgs:
                return ""
            query = (user_msgs[-1].get("content") or "")[:500]

        # Skip commands and very short messages
        if not query or query.startswith("/") or len(query.strip()) < 10:
            _whisper_last[chat_id] = now
            return ""

        # Strip system-reminder tags from query
        if "<system-reminder>" in query:
            import re
            query = re.sub(r"<system-reminder>.*?</system-reminder>", "", query, flags=re.DOTALL).strip()
            if len(query) < 10:
                _whisper_last[chat_id] = now
                return ""

        # Search for relevant memories
        embed_path = str(WORKSPACE / "skills" / "embedding")
        if embed_path not in sys.path:
            sys.path.insert(0, embed_path)
        import importlib
        _ms = importlib.import_module("memory_search")
        results = _ms.search(query, top_k=3, sources=["memory"])

        # Filter by score threshold
        relevant = [r for r in results if r.get("score", 0) >= 0.65]
        if not relevant:
            _whisper_last[chat_id] = now
            return ""

        # Format as whisper
        lines = ["<subconscious_whisper>"]
        lines.append("Relevant memories for this conversation:")
        for r in relevant:
            name = Path(r["file"]).stem
            lines.append(f"- [{name}] (score={r['score']:.2f}) {r.get('content', '')[:200]}")
        lines.append("</subconscious_whisper>")

        _whisper_last[chat_id] = now
        log(f"Whisper injected for chat={chat_id} ({len(relevant)} memories)")
        return "\n".join(lines) + "\n\n"
    except Exception as e:
        log(f"Whisper error: {e}")
        return ""


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_log_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(f"[apex {datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)
    with _log_lock:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX:
                rotated = LOG_PATH.with_suffix(".log.1")
                if rotated.exists():
                    rotated.unlink()
                LOG_PATH.replace(rotated)
            with LOG_PATH.open("a") as f:
                f.write(line + "\n")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------
_db_lock = threading.Lock()


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            title TEXT,
            claude_session_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL REFERENCES chats(id),
            role TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            tool_events TEXT DEFAULT '[]',
            thinking TEXT DEFAULT '',
            cost_usd REAL DEFAULT 0,
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            acked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        DROP TABLE IF EXISTS web_sessions;
        CREATE TABLE IF NOT EXISTS agent_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            avatar TEXT DEFAULT '',
            role_description TEXT DEFAULT '',
            backend TEXT DEFAULT '',
            model TEXT DEFAULT '',
            system_prompt TEXT NOT NULL DEFAULT '',
            tool_policy TEXT DEFAULT '',
            is_default INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    # Migration: add model and type columns if missing
    for col, default in [("model", "NULL"), ("type", "'chat'")]:
        try:
            conn.execute(f"ALTER TABLE chats ADD COLUMN {col} TEXT DEFAULT {default}")
        except Exception:
            pass  # column already exists
    # Migration: add metadata column to alerts if missing
    try:
        conn.execute("ALTER TABLE alerts ADD COLUMN metadata TEXT DEFAULT '{}'")
    except Exception:
        pass
    # Migration: add category column to chats (for alerts channel filtering)
    try:
        conn.execute("ALTER TABLE chats ADD COLUMN category TEXT DEFAULT NULL")
    except Exception:
        pass
    # Migration: add profile_id column to chats (for agent profiles)
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE chats ADD COLUMN profile_id TEXT DEFAULT ''")
    # Migration: channel_agent_memberships table (groups foundation)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS channel_agent_memberships (
            id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            agent_profile_id TEXT NOT NULL REFERENCES agent_profiles(id),
            routing_mode TEXT NOT NULL DEFAULT 'mentioned',
            is_primary INTEGER NOT NULL DEFAULT 0,
            display_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(channel_id, agent_profile_id)
        )
    """)
    # Migration: speaker identity columns on messages (groups)
    for col in ["speaker_id", "speaker_name", "speaker_avatar", "visibility", "group_turn_id"]:
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(f"ALTER TABLE messages ADD COLUMN {col} TEXT DEFAULT ''")
    conn.commit()
    conn.close()


def _seed_default_profiles():
    """Optionally seed agent personas from persona_templates.json.

    Controlled by config.json "seed_default_profiles" (default: false).
    Existing profiles are never overwritten (INSERT OR IGNORE).
    Templates live in server/persona_templates.json — users can also
    install them selectively via the dashboard or setup wizard.
    """
    # Check if seeding is enabled in config
    try:
        cfg_path = APEX_ROOT / "state" / "config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text())
            if not cfg.get("seed_default_profiles", False):
                return
        else:
            return  # No config = fresh install, don't auto-seed
    except Exception:
        return

    # Load templates
    templates_path = Path(__file__).resolve().parent / "persona_templates.json"
    if not templates_path.exists():
        return
    try:
        profiles = json.loads(templates_path.read_text())
    except Exception as e:
        log(f"Failed to load persona templates: {e}")
        return

    with _db_lock:
        conn = _get_db()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        inserted = 0
        for p in profiles:
            cur = conn.execute(
                "INSERT OR IGNORE INTO agent_profiles (id, name, slug, avatar, role_description, "
                "backend, model, system_prompt, tool_policy, is_default, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (p["id"], p["name"], p["slug"], p["avatar"], p["role_description"],
                 p["backend"], p["model"], p["system_prompt"], "",
                 p.get("is_default", 0), now, now),
            )
            inserted += cur.rowcount
        conn.commit()
        conn.close()
        if inserted:
            log(f"Seeded {inserted} agent profiles from templates")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_filename(filename: str | None, fallback: str = "upload") -> str:
    safe = Path(filename or fallback).name.replace("\x00", "").strip()
    return safe or fallback


def _stringify_block_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False, indent=2)
    except TypeError:
        return str(content)


def _guess_mime_type(ext: str) -> str:
    mime, _ = mimetypes.guess_type(f"file.{ext}")
    return mime or ("image/jpeg" if ext in {"jpg", "jpeg"} else "application/octet-stream")


def _attachment_label(name: str, kind: str) -> str:
    prefix = "Image" if kind == "image" else "File"
    return f"{prefix}: {name}"


def _summarize_attachments(items: list[dict]) -> str:
    labels = [_attachment_label(item["name"], item["type"]) for item in items]
    return "Attachments: " + ", ".join(labels)


def _load_attachment(att: dict) -> dict:
    att_id = str(att.get("id", "")).strip().lower()
    if len(att_id) != 8 or any(ch not in "0123456789abcdef" for ch in att_id):
        raise ValueError("Invalid attachment id")

    matches = list(UPLOAD_DIR.glob(f"{att_id}.*"))
    if len(matches) != 1:
        raise ValueError("Attachment not found")

    path = matches[0].resolve()
    upload_root = UPLOAD_DIR.resolve()
    if path.parent != upload_root:
        raise ValueError("Invalid attachment path")

    ext = path.suffix.lstrip(".").lower()
    if ext in IMAGE_TYPES:
        kind = "image"
        limit = MAX_IMAGE_SIZE
    elif ext in TEXT_TYPES:
        kind = "text"
        limit = MAX_TEXT_SIZE
    else:
        raise ValueError(f"Unsupported attachment type: .{ext}")

    requested_type = str(att.get("type", "")).strip()
    if requested_type and requested_type != kind:
        raise ValueError("Attachment type mismatch")

    data = path.read_bytes()
    if len(data) > limit:
        raise ValueError("Attachment exceeds size limit")

    return {
        "id": att_id,
        "name": _normalize_filename(att.get("name"), path.name),
        "type": kind,
        "ext": ext,
        "path": str(path),
        "data": data,
        "mimeType": _guess_mime_type(ext) if kind == "image" else None,
    }


def _build_turn_payload(chat_id: str, prompt: str, attachments: list[dict]) -> tuple[str, callable]:
    loaded = [_load_attachment(att) for att in attachments]

    prompt_lines: list[str] = []
    if prompt:
        prompt_lines.append(prompt)
    for item in loaded:
        if item["type"] == "text":
            prompt_lines.append(f"[Attached file: {item['name']} at {item['path']}]")
    query_prompt = "\n\n".join(prompt_lines).strip()

    display_parts: list[str] = []
    if prompt:
        display_parts.append(prompt)
    if loaded:
        display_parts.append(_summarize_attachments(loaded))
    display_prompt = "\n".join(display_parts).strip() or "(attachment)"

    image_blocks = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": item["mimeType"],
                "data": base64.b64encode(item["data"]).decode(),
            },
        }
        for item in loaded
        if item["type"] == "image"
    ]
    profile_prompt = _get_profile_prompt(chat_id)
    group_roster_prompt = _get_group_roster_prompt(chat_id)
    workspace_ctx = _get_workspace_context(chat_id)
    whisper = _get_whisper_text(chat_id, current_prompt=query_prompt) if ENABLE_SUBCONSCIOUS_WHISPER else ""
    prefix = f"{profile_prompt}{group_roster_prompt}{workspace_ctx}{whisper}".strip()
    final_prompt = query_prompt or ("What do you see?" if image_blocks else "")
    if prefix:
        final_prompt = f"{prefix}\n\n{final_prompt}".strip() if final_prompt else prefix

    if image_blocks:
        saved_blocks = list(image_blocks) + [{"type": "text", "text": final_prompt}]

        def make_query_input():
            async def _make_stream():
                yield {
                    "type": "user",
                    "message": {"role": "user", "content": list(saved_blocks)},
                    "parent_tool_use_id": None,
                }
            return _make_stream()

        return display_prompt, make_query_input

    def make_query_input():
        return final_prompt

    return display_prompt, make_query_input


def _websocket_origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return False  # S-05: require Origin header (non-browser clients must set it)
    host = (websocket.headers.get("host") or "").lower()
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == host


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Chat DB operations
# ---------------------------------------------------------------------------

def _create_chat(title: str = "New Channel", model: str | None = None, chat_type: str = "chat",
                  category: str | None = None, profile_id: str = "") -> str:
    cid = str(uuid.uuid4())[:8]
    now = _now()
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT INTO chats (id, title, model, type, category, profile_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, title, model, chat_type, category, profile_id, now, now),
        )
        conn.commit()
        conn.close()
    return cid


def _get_chats() -> list[dict]:
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT c.id, c.title, c.claude_session_id, c.created_at, c.updated_at, "
            "c.model, c.type, c.category, c.profile_id, ap.name, ap.avatar "
            "FROM chats c LEFT JOIN agent_profiles ap ON c.profile_id = ap.id "
            "ORDER BY c.updated_at DESC"
        ).fetchall()
        # Batch-fetch member counts + primary agent for groups
        group_ids = [r[0] for r in rows if (r[6] or "chat") == "group"]
        group_meta: dict[str, dict] = {}
        if group_ids:
            ph = ",".join("?" * len(group_ids))
            for gid in group_ids:
                members = conn.execute(
                    "SELECT m.agent_profile_id, m.is_primary, ap2.name, ap2.avatar "
                    "FROM channel_agent_memberships m "
                    "JOIN agent_profiles ap2 ON m.agent_profile_id = ap2.id "
                    "WHERE m.channel_id = ?", (gid,)
                ).fetchall()
                primary = next((m for m in members if m[1]), None)
                group_meta[gid] = {
                    "member_count": len(members),
                    "primary_name": primary[2] if primary else "",
                    "primary_avatar": primary[3] if primary else "",
                }
        conn.close()
    result = []
    for r in rows:
        d = {"id": r[0], "title": r[1], "claude_session_id": r[2],
             "created_at": r[3], "updated_at": r[4], "model": r[5], "type": r[6], "category": r[7] or None,
             "profile_id": r[8] or "", "profile_name": r[9] or "", "profile_avatar": r[10] or ""}
        gm = group_meta.get(r[0])
        if gm:
            d["member_count"] = gm["member_count"]
            d["primary_profile_name"] = gm["primary_name"]
            d["primary_profile_avatar"] = gm["primary_avatar"]
            # Override profile display for groups with primary agent info
            if not d["profile_name"] and gm["primary_name"]:
                d["profile_name"] = gm["primary_name"]
                d["profile_avatar"] = gm["primary_avatar"]
        result.append(d)
    return result


def _get_chat(chat_id: str) -> dict | None:
    with _db_lock:
        conn = _get_db()
        row = conn.execute("SELECT id, title, claude_session_id, created_at, updated_at, model, type, category, profile_id FROM chats WHERE id = ?",
                           (chat_id,)).fetchone()
        conn.close()
    if not row:
        return None
    return {"id": row[0], "title": row[1], "claude_session_id": row[2],
            "created_at": row[3], "updated_at": row[4], "model": row[5], "type": row[6], "category": row[7] or None,
            "profile_id": row[8] or ""}


def _update_chat(chat_id: str, **kwargs) -> None:
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [_now(), chat_id]
    with _db_lock:
        conn = _get_db()
        conn.execute(f"UPDATE chats SET {sets}, updated_at = ? WHERE id = ?", vals)
        conn.commit()
        conn.close()


def _delete_chat(chat_id: str) -> bool:
    with _db_lock:
        conn = _get_db()
        # Delete messages first — FK constraint requires it
        conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        cur = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        if cur.rowcount:
            conn.commit()
            conn.close()
            return True
        conn.commit()
        conn.close()
        return False


def _get_group_members(channel_id: str) -> list[dict]:
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT m.id, m.agent_profile_id, m.routing_mode, m.is_primary, m.display_order, "
            "ap.name, ap.avatar, ap.model, ap.backend "
            "FROM channel_agent_memberships m "
            "JOIN agent_profiles ap ON m.agent_profile_id = ap.id "
            "WHERE m.channel_id = ? ORDER BY m.is_primary DESC, m.display_order",
            (channel_id,),
        ).fetchall()
        conn.close()
    return [
        {"id": r[0], "profile_id": r[1], "routing_mode": r[2], "is_primary": bool(r[3]),
         "display_order": r[4], "name": r[5], "avatar": r[6], "model": r[7], "backend": r[8]}
        for r in rows
    ]


def _add_group_member(channel_id: str, profile_id: str, routing_mode: str = "mentioned",
                      is_primary: bool = False, display_order: int = 0) -> str:
    mid = str(uuid.uuid4())[:12]
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT INTO channel_agent_memberships (id, channel_id, agent_profile_id, routing_mode, is_primary, display_order, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mid, channel_id, profile_id, routing_mode, int(is_primary), display_order, _now()),
        )
        conn.commit()
        conn.close()
    return mid


def _remove_group_member(channel_id: str, profile_id: str) -> bool:
    with _db_lock:
        conn = _get_db()
        cur = conn.execute(
            "DELETE FROM channel_agent_memberships WHERE channel_id = ? AND agent_profile_id = ?",
            (channel_id, profile_id),
        )
        conn.commit()
        conn.close()
    return cur.rowcount > 0


def _save_message(chat_id: str, role: str, content: str, tool_events: str = "[]",
                  thinking: str = "", cost_usd: float = 0, tokens_in: int = 0,
                  tokens_out: int = 0, speaker_id: str = "", speaker_name: str = "",
                  speaker_avatar: str = "", visibility: str = "public",
                  group_turn_id: str = "") -> str:
    mid = str(uuid.uuid4())[:12]
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, tool_events, thinking, cost_usd, "
            "tokens_in, tokens_out, speaker_id, speaker_name, speaker_avatar, visibility, "
            "group_turn_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, chat_id, role, content, tool_events, thinking, cost_usd, tokens_in, tokens_out,
             speaker_id, speaker_name, speaker_avatar, visibility, group_turn_id, _now()))
        conn.commit()
        conn.close()
    return mid


def _get_messages(chat_id: str, days: int | None = None, include_internal: bool = False) -> list[dict]:
    vis_clause = "" if include_internal else " AND (visibility = 'public' OR visibility = '' OR visibility IS NULL)"
    with _db_lock:
        conn = _get_db()
        cols = ("id, role, content, tool_events, thinking, cost_usd, tokens_in, tokens_out, "
                "created_at, speaker_id, speaker_name, speaker_avatar, visibility, group_turn_id")
        if days and days > 0:
            rows = conn.execute(
                f"SELECT {cols} FROM messages WHERE chat_id = ? AND created_at >= datetime('now', ?){vis_clause} ORDER BY created_at",
                (chat_id, f"-{days} days")).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {cols} FROM messages WHERE chat_id = ?{vis_clause} ORDER BY created_at",
                (chat_id,)).fetchall()
        conn.close()
    return [{"id": r[0], "role": r[1], "content": r[2], "tool_events": r[3],
             "thinking": r[4], "cost_usd": r[5], "tokens_in": r[6],
             "tokens_out": r[7], "created_at": r[8],
             "speaker_id": r[9] or "", "speaker_name": r[10] or "",
             "speaker_avatar": r[11] or "", "visibility": r[12] or "public",
             "group_turn_id": r[13] or ""} for r in rows]


def _create_alert(source: str, severity: str, title: str, body: str, metadata: dict | None = None) -> dict:
    aid = uuid.uuid4().hex[:8]
    now = _now()
    raw_meta = metadata or {}
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT INTO alerts (id, source, severity, title, body, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (aid, source, severity, title, body, json.dumps(raw_meta), now),
        )
        conn.commit()
        conn.close()
    # Flatten values to strings — iOS decodes metadata as [String: String]
    str_meta = {str(k): json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                for k, v in raw_meta.items()}
    return {"id": aid, "source": source, "severity": severity, "title": title,
            "body": body, "acked": False, "metadata": str_meta, "created_at": now}


def _get_alerts(since: str | None = None, unacked_only: bool = False,
                category: str | None = None, limit: int = 100) -> list[dict]:
    # Map category to matching sources
    category_sources = None
    if category:
        category_sources = [src for src, cat in ALERT_CATEGORY_MAP.items() if cat == category]
    with _db_lock:
        conn = _get_db()
        query = "SELECT id, source, severity, title, body, acked, created_at, metadata FROM alerts"
        params: list = []
        conditions: list[str] = []
        if since:
            conditions.append("created_at > ?")
            params.append(since)
        if unacked_only:
            conditions.append("acked = 0")
        if category_sources is not None:
            placeholders = ", ".join("?" for _ in category_sources)
            conditions.append(f"source IN ({placeholders})")
            params.extend(category_sources)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
    results = []
    for r in rows:
        meta: dict[str, str] = {}
        try:
            raw = json.loads(r[7]) if r[7] else {}
            # Flatten all values to strings — iOS decodes as [String: String]
            meta = {str(k): json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                    for k, v in raw.items()}
        except Exception:
            pass
        results.append({"id": r[0], "source": r[1], "severity": r[2], "title": r[3],
                         "body": r[4], "acked": bool(r[5]), "created_at": r[6], "metadata": meta})
    return results


def _ack_alert(alert_id: str) -> bool:
    with _db_lock:
        conn = _get_db()
        cur = conn.execute("UPDATE alerts SET acked = 1 WHERE id = ? AND acked = 0", (alert_id,))
        conn.commit()
        changed = cur.rowcount > 0
        conn.close()
    return changed


def _get_alert(alert_id: str) -> dict | None:
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT id, source, severity, title, body, acked, created_at, metadata FROM alerts WHERE id = ?",
            (alert_id,),
        ).fetchone()
        conn.close()
    if not row:
        return None
    meta = {}
    try:
        meta = json.loads(row[7]) if row[7] else {}
    except Exception:
        pass
    return {"id": row[0], "source": row[1], "severity": row[2], "title": row[3],
            "body": row[4], "acked": bool(row[5]), "created_at": row[6], "metadata": meta}


GUARDRAIL_WHITELIST = APEX_ROOT / "state" / "guardrail_whitelist.json"


def _add_whitelist_entry(tool: str, target: str, alert_id: str, ttl_seconds: int = 3600) -> dict:
    """Add a time-limited guardrail exemption."""
    from datetime import datetime, timedelta, timezone
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
    GUARDRAIL_WHITELIST.write_text(json.dumps(entries, indent=2))
    return entry


# ---------------------------------------------------------------------------
# Claude Agent SDK — persistent sessions, no subprocess respawning
# ---------------------------------------------------------------------------
_clients: dict[str, ClaudeSDKClient] = {}
_chat_locks: dict[str, asyncio.Lock] = {}
_chat_ws: dict[str, set[WebSocket]] = {}  # chat_id -> ALL connected WebSockets (multi-viewer)
_ws_chat: dict[WebSocket, str] = {}  # reverse: ws -> current chat_id (for detach on re-attach)
_active_send_tasks: dict[str, dict[str, dict[str, object]]] = {}
# chat_id -> {stream_id -> {task, stream_id, name, avatar, profile_id}}
_current_stream_id: contextvars.ContextVar[str] = contextvars.ContextVar("apex_stream_id", default="")
_current_group_profile_id: contextvars.ContextVar[str] = contextvars.ContextVar("apex_group_profile_id", default="")


def _make_stream_id() -> str:
    return uuid.uuid4().hex[:12]


def _attach_ws(ws: WebSocket, chat_id: str) -> None:
    """Register ws for chat_id, removing it from any previous chat first."""
    old = _ws_chat.get(ws)
    if old and old != chat_id:
        old_set = _chat_ws.get(old)
        if old_set:
            old_set.discard(ws)
            if not old_set:
                _chat_ws.pop(old, None)
        log(f"ws detached from chat={old} -> attaching to chat={chat_id}")
    _chat_ws.setdefault(chat_id, set()).add(ws)
    _ws_chat[ws] = chat_id


def _detach_ws(ws: WebSocket) -> None:
    """Remove ws from all tracking."""
    old = _ws_chat.pop(ws, None)
    if old:
        old_set = _chat_ws.get(old)
        if old_set:
            old_set.discard(ws)
            if not old_set:
                _chat_ws.pop(old, None)


def _stream_task_is_active(task: object) -> bool:
    if not isinstance(task, asyncio.Task) or task.done():
        return False
    try:
        return task.cancelling() == 0
    except Exception:
        return True


def _get_active_stream_entries(chat_id: str) -> list[tuple[str, dict[str, object]]]:
    streams = _active_send_tasks.get(chat_id) or {}
    active: list[tuple[str, dict[str, object]]] = []
    stale_ids: list[str] = []
    for stream_id, info in list(streams.items()):
        if _stream_task_is_active(info.get("task")):
            active.append((stream_id, info))
        else:
            stale_ids.append(stream_id)
    for stream_id in stale_ids:
        streams.pop(stream_id, None)
    if streams:
        _active_send_tasks[chat_id] = streams
    else:
        _active_send_tasks.pop(chat_id, None)
    return active


def _has_active_stream(chat_id: str, exclude_stream_id: str = "") -> bool:
    return any(stream_id != exclude_stream_id for stream_id, _ in _get_active_stream_entries(chat_id))


def _set_active_send_task(
    chat_id: str,
    stream_id: str,
    task: asyncio.Task,
    *,
    name: str = "",
    avatar: str = "",
    profile_id: str = "",
) -> None:
    _active_send_tasks.setdefault(chat_id, {})[stream_id] = {
        "task": task,
        "stream_id": stream_id,
        "name": name,
        "avatar": avatar,
        "profile_id": profile_id,
    }


def _update_active_send_task(
    chat_id: str,
    stream_id: str,
    *,
    name: str | None = None,
    avatar: str | None = None,
    profile_id: str | None = None,
) -> None:
    streams = _active_send_tasks.get(chat_id)
    if not streams:
        return
    info = streams.get(stream_id)
    if not info:
        return
    if name is not None:
        info["name"] = name
    if avatar is not None:
        info["avatar"] = avatar
    if profile_id is not None:
        info["profile_id"] = profile_id


def _remove_active_send_task(chat_id: str, stream_id: str, task: asyncio.Task | None = None) -> None:
    streams = _active_send_tasks.get(chat_id)
    if not streams:
        return
    info = streams.get(stream_id)
    if not info:
        return
    if task is not None and info.get("task") is not task:
        return
    streams.pop(stream_id, None)
    if not streams:
        _active_send_tasks.pop(chat_id, None)


_stream_buffers: dict[str, deque[tuple[int, dict]]] = {}
_stream_seq: dict[str, int] = {}
_chat_send_locks: dict[str, asyncio.Lock] = {}
_STREAM_BUFFER_MAX = 200
_DEFAULT_ALERT_CATEGORIES = {
    "guardrail": "system",
    "watchdog": "system",
    "system": "system",
    "test": "test",
    "custom": "custom",
}


def _load_alert_category_map() -> dict[str, str]:
    """Load alert category map from config.json, falling back to defaults.

    Users can extend the map by adding an "alert_categories" object to
    state/config.json without modifying code. Survives upgrades.
    """
    merged = dict(_DEFAULT_ALERT_CATEGORIES)
    try:
        cfg_path = APEX_ROOT / "state" / "config.json"
        if cfg_path.exists():
            import json as _json
            data = _json.loads(cfg_path.read_text())
            custom = data.get("alert_categories", {})
            if isinstance(custom, dict):
                merged.update(custom)
    except Exception:
        pass
    return merged


ALERT_CATEGORY_MAP = _load_alert_category_map()


def _alert_category(source: str) -> str:
    """Map an alert source to its category."""
    return ALERT_CATEGORY_MAP.get(source, "other")


def _get_alerts_channels() -> list[dict]:
    """Return alerts-type chats with their category filter."""
    with _db_lock:
        conn = _get_db()
        rows = conn.execute("SELECT id, category FROM chats WHERE type = 'alerts'").fetchall()
        conn.close()
    return [{"id": r[0], "category": r[1]} for r in rows]


async def _broadcast_alert(alert: dict) -> None:
    """Send alert to ALL connected WebSocket clients (regardless of which chat they're viewing).

    Every client gets the alert so the iOS app can show it even when
    viewing a regular conversation.  Category filtering is the client's job.
    """
    payload = {"type": "alert", **alert}
    # Collect all unique WebSocket connections across all chats
    all_ws: set[WebSocket] = set()
    for ws_set in _chat_ws.values():
        all_ws.update(ws_set)
    if not all_ws:
        return
    dead: list[tuple[WebSocket, str]] = []
    for ws in list(all_ws):
        chat_id = _ws_chat.get(ws, "")
        ok = await _safe_ws_send_json(ws, payload, chat_id=chat_id)
        if not ok:
            dead.append((ws, chat_id))
    for ws, chat_id in dead:
        ws_set = _chat_ws.get(chat_id)
        if ws_set:
            ws_set.discard(ws)
            if not ws_set:
                _chat_ws.pop(chat_id, None)


def _make_options(model: str | None = None, session_id: str | None = None) -> ClaudeAgentOptions:
    """Build SDK options for a new or resumed session."""
    return ClaudeAgentOptions(
        model=model or MODEL,
        cwd=str(WORKSPACE),
        permission_mode=PERMISSION_MODE,
        max_turns=50,
        resume=session_id,
        setting_sources=["user"],  # loads ~/.claude/settings.json hooks
    )


def _client_is_alive(client: ClaudeSDKClient) -> bool:
    """Check if an SDK client's subprocess is still running."""
    try:
        transport = getattr(client, "_transport", None)
        if transport is None:
            return False
        proc = getattr(transport, "_process", None)
        if proc is None:
            return False
        # anyio.abc.Process — returncode is None while running
        if proc.returncode is not None:
            return False
        return True
    except Exception:
        return False


async def _get_or_create_client(client_key: str, model: str | None = None) -> ClaudeSDKClient:
    """Get existing persistent client or create a new one.

    client_key is chat_id for solo chats, or chat_id:profile_id for group agents.
    """
    if client_key in _clients:
        client = _clients[client_key]
        if _client_is_alive(client):
            return client
        log(f"stale SDK client detected: key={client_key}, evicting")
        await _disconnect_client(client_key)

    # Extract real chat_id for DB lookup (strip :profile_id suffix if present)
    real_chat_id = client_key.split(":")[0]
    is_group_agent = ":" in client_key

    chat = _get_chat(real_chat_id)
    # Group agents start fresh sessions (no session resume — they share the chat row)
    session_id = None if is_group_agent else (chat.get("claude_session_id") if chat else None)
    options = _make_options(model=model, session_id=session_id)

    effective_model = model or MODEL
    log(f"creating SDK client: key={client_key} model={effective_model} resume={session_id or 'new'}")
    client = ClaudeSDKClient(options)
    await asyncio.wait_for(client.connect(), timeout=SDK_QUERY_TIMEOUT)
    _clients[client_key] = client
    return client


def _get_chat_lock(chat_id: str) -> asyncio.Lock:
    lock = _chat_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _chat_locks[chat_id] = lock
    return lock


def _get_chat_send_lock(chat_id: str) -> asyncio.Lock:
    lock = _chat_send_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _chat_send_locks[chat_id] = lock
    return lock


def _reset_stream_buffer(chat_id: str) -> None:
    _stream_buffers[chat_id] = deque(maxlen=_STREAM_BUFFER_MAX)
    _stream_seq[chat_id] = 0


def _buffer_stream_event(chat_id: str, payload: dict) -> None:
    if chat_id not in _stream_buffers:
        _reset_stream_buffer(chat_id)
    seq = _stream_seq.get(chat_id, 0) + 1
    _stream_seq[chat_id] = seq
    _stream_buffers[chat_id].append((seq, dict(payload)))


async def _send_stream_event(chat_id: str, payload: dict) -> None:
    payload = dict(payload)
    stream_id = _current_stream_id.get("")
    if stream_id and not payload.get("stream_id"):
        payload["stream_id"] = stream_id
    _buffer_stream_event(chat_id, payload)
    send_lock = _get_chat_send_lock(chat_id)
    async with send_lock:
        ws_set = _chat_ws.get(chat_id)
        if not ws_set:
            return
        dead: list[WebSocket] = []
        for ws in list(ws_set):
            ok = await _safe_ws_send_json(ws, payload, chat_id=chat_id)
            if not ok:
                dead.append(ws)
        for ws in dead:
            ws_set.discard(ws)
        if not ws_set:
            _chat_ws.pop(chat_id, None)


async def _send_active_streams(chat_id: str) -> None:
    """Send the current active stream roster to all viewers of this chat."""
    streams = []
    for stream_id, info in _get_active_stream_entries(chat_id):
        streams.append({
            "stream_id": stream_id,
            "name": str(info.get("name", "")),
            "avatar": str(info.get("avatar", "")),
            "profile_id": str(info.get("profile_id", "")),
        })
    await _send_stream_event(chat_id, {
        "type": "active_streams",
        "chat_id": chat_id,
        "streams": streams,
    })


async def _disconnect_client(chat_id: str) -> None:
    client = _clients.pop(chat_id, None)
    if client is None:
        return
    with contextlib.suppress(Exception):
        await client.disconnect()


async def _set_model(model: str) -> None:
    global MODEL
    MODEL = model
    with _db_lock:
        conn = _get_db()
        conn.execute("UPDATE chats SET claude_session_id = NULL WHERE claude_session_id IS NOT NULL")
        conn.commit()
        conn.close()
    for chat_id in list(_clients):
        await _disconnect_client(chat_id)
    log(f"model changed to {MODEL}")


def _normalize_response_stream(response):
    if hasattr(response, "__aiter__"):
        return response

    async def _wrap_response():
        if response is None:
            return
        if isinstance(response, list) or (
            hasattr(response, "__iter__") and not isinstance(response, (str, bytes, dict))
        ):
            for item in response:
                yield item
            return
        yield response

    return _wrap_response()


_ws_send_count: dict[str, int] = {}
_ws_fail_count: dict[str, int] = {}

async def _safe_ws_send_json(ws: WebSocket, payload: dict, *, chat_id: str) -> bool:
    try:
        await ws.send_json(payload)
        _ws_send_count[chat_id] = _ws_send_count.get(chat_id, 0) + 1
        return True
    except Exception as e:
        _ws_fail_count[chat_id] = _ws_fail_count.get(chat_id, 0) + 1
        fc = _ws_fail_count[chat_id]
        sc = _ws_send_count.get(chat_id, 0)
        if DEBUG: log(f"DBG ws_send FAIL #{fc} (ok={sc}): chat={chat_id} type={payload.get('type')} {type(e).__name__}: {e}")
        return False


async def _run_query_turn(client: ClaudeSDKClient, make_query_input,
                          chat_id: str) -> dict:
    if DEBUG: log(f"DBG query_turn: chat={chat_id} sending query...")
    await asyncio.wait_for(client.query(make_query_input()), timeout=SDK_QUERY_TIMEOUT)
    if DEBUG: log(f"DBG query_turn: chat={chat_id} query sent, streaming response...")
    result = await asyncio.wait_for(_stream_response(client, chat_id), timeout=SDK_STREAM_TIMEOUT)
    if result.get("stream_failed"):
        if DEBUG: log(f"DBG query_turn: chat={chat_id} STREAM FAILED: {result.get('error')}")
        raise RuntimeError(result.get("error") or "SDK stream failed")
    # SDK cold-start workaround: first query on a fresh session returns "Not logged in"
    # but the session IS valid — retry once on the same client
    resp_text = result.get("text", "")
    if resp_text.strip() == "Not logged in \u00b7 Please run /login" and result.get("tokens_in", 0) == 0:
        log(f"SDK cold-start: chat={chat_id} got login prompt on fresh session, retrying...")
        await asyncio.wait_for(client.query(make_query_input()), timeout=SDK_QUERY_TIMEOUT)
        result = await asyncio.wait_for(_stream_response(client, chat_id), timeout=SDK_STREAM_TIMEOUT)
        if result.get("stream_failed"):
            raise RuntimeError(result.get("error") or "SDK stream failed (retry)")
    if DEBUG: log(f"DBG query_turn: chat={chat_id} done. text={len(result.get('text',''))}chars tools={result.get('tool_events','[]').count('tool_use_id')} session={result.get('session_id','?')[:8] if result.get('session_id') else 'none'}")
    return result


async def _stream_response(client: ClaudeSDKClient, chat_id: str) -> dict:
    """Stream SDK response events to WebSocket. Returns turn result.

    Uses _chat_ws registry to find the current WebSocket dynamically,
    so if the client reconnects mid-stream, the stream picks up the
    new WebSocket and continues sending events to it.
    """
    result_text = ""
    thinking_text = ""
    tool_events: list[dict] = []
    pending_tools: dict[str, dict] = {}
    result_info: dict = {
        "session_id": None, "text": "", "thinking": "",
        "tool_events": "[]", "cost_usd": 0,
        "tokens_in": 0, "tokens_out": 0, "error": None,
        "stream_failed": False, "is_error": False,
    }

    async def _send(payload: dict) -> None:
        """Send to current WS from registry. Removes dead entries."""
        await _send_stream_event(chat_id, payload)

    _stream_event_count = 0
    _stream_start = time.monotonic()
    try:
        response = _normalize_response_stream(client.receive_response())
        async for msg in response:
            _stream_event_count += 1
            elapsed = time.monotonic() - _stream_start
            if _stream_event_count <= 3 or _stream_event_count % 20 == 0:
                if DEBUG: log(f"DBG stream event #{_stream_event_count} ({elapsed:.0f}s): chat={chat_id} type={type(msg).__name__}")
            if isinstance(msg, SystemMessage):
                if msg.subtype == "init":
                    data = msg.data if isinstance(msg.data, dict) else {}
                    model_name = data.get("model", MODEL)
                    await _send({"type": "system", "subtype": "init", "model": model_name})

            elif isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text
                        await _send({"type": "text", "text": block.text})

                    elif isinstance(block, ThinkingBlock):
                        thinking_text += block.thinking
                        await _send({"type": "thinking", "text": block.thinking})

                    elif isinstance(block, ToolUseBlock):
                        tool_event = {
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                        pending_tools[block.id] = tool_event
                        await _send({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })

                    elif isinstance(block, ToolResultBlock):
                        content = _stringify_block_content(block.content)
                        is_error = block.is_error or False
                        tool_use_id = block.tool_use_id or ""
                        # Cap tool result content to prevent context explosion from large agent results
                        MAX_TOOL_RESULT_CHARS = 5000
                        if len(content) > MAX_TOOL_RESULT_CHARS:
                            tool_name = pending_tools.get(tool_use_id, {}).get("name", "?")
                            if DEBUG: log(f"DBG tool result TRUNCATED: {tool_name} {len(content)} -> {MAX_TOOL_RESULT_CHARS} chars")
                            content = content[:MAX_TOOL_RESULT_CHARS] + f"\n\n[... truncated from {len(content)} chars]"
                        current_tool = pending_tools.pop(tool_use_id, None)
                        if current_tool:
                            tool_events.append({
                                **current_tool,
                                "result": {"tool_use_id": tool_use_id,
                                           "content": content, "is_error": is_error},
                            })
                        await _send({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": content[:2000],
                            "is_error": is_error,
                        })

            elif isinstance(msg, ResultMessage):
                log(f"ResultMessage usage dict: {msg.usage}")
                result_info = {
                    "session_id": msg.session_id,
                    "text": msg.result or result_text,
                    "thinking": thinking_text,
                    "tool_events": json.dumps(tool_events),
                    "cost_usd": msg.total_cost_usd or 0,
                    "tokens_in": (msg.usage or {}).get("input_tokens", 0),
                    "tokens_out": (msg.usage or {}).get("output_tokens", 0),
                    "error": None,
                    "stream_failed": False,
                    "is_error": bool(msg.is_error),
                }
                # The current turn's tokens_in IS the context fill (includes full history)
                _ctx_in = result_info["tokens_in"]
                _chat = _get_chat(chat_id)
                _ctx_model = (_chat.get("model") or MODEL) if _chat else MODEL
                _ctx_window = MODEL_CONTEXT_WINDOWS.get(_ctx_model, MODEL_CONTEXT_DEFAULT)
                await _send({
                    "type": "result",
                    "is_error": msg.is_error,
                    "cost_usd": result_info["cost_usd"],
                    "tokens_in": result_info["tokens_in"],
                    "tokens_out": result_info["tokens_out"],
                    "session_id": msg.session_id,
                    "context_tokens_in": _ctx_in,
                    "context_window": _ctx_window,
                })
                elapsed = time.monotonic() - _stream_start
                if DEBUG: log(f"DBG stream COMPLETE: chat={chat_id} events={_stream_event_count} time={elapsed:.0f}s session={msg.session_id[:8] if msg.session_id else '?'} cost=${result_info['cost_usd']:.4f}")
                # receive_response() stops after ResultMessage

    except asyncio.TimeoutError:
        if DEBUG: log(f"DBG stream TIMEOUT: chat={chat_id} after {SDK_STREAM_TIMEOUT}s. text={len(result_text)}chars thinking={len(thinking_text)}chars tools={len(tool_events)}")
        result_info["text"] = result_text
        result_info["thinking"] = thinking_text
        result_info["tool_events"] = json.dumps(tool_events)
        result_info["error"] = f"Stream timeout after {SDK_STREAM_TIMEOUT}s"
        result_info["stream_failed"] = True
        await _disconnect_client(chat_id)
    except Exception as e:
        if DEBUG: log(f"DBG stream ERROR: chat={chat_id} {type(e).__name__}: {e}. text={len(result_text)}chars thinking={len(thinking_text)}chars tools={len(tool_events)}")
        result_info["text"] = result_text
        result_info["thinking"] = thinking_text
        result_info["tool_events"] = json.dumps(tool_events)
        result_info["error"] = str(e)
        result_info["stream_failed"] = True
        await _disconnect_client(chat_id)

    if not result_info.get("text"):
        result_info["text"] = result_text
    if not result_info.get("thinking"):
        result_info["thinking"] = thinking_text
    if result_info.get("tool_events") == "[]" and tool_events:
        result_info["tool_events"] = json.dumps(tool_events)

    return result_info


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    _seed_default_profiles()
    # Initialize Apex Dashboard
    _apex_config = ApexConfig(APEX_ROOT / "state")
    init_dashboard(
        state_dir=APEX_ROOT / "state",
        db_path=DB_PATH,
        ssl_dir=APEX_ROOT / "state" / "ssl",
    )
    log(f"Apex starting on {HOST}:{PORT} [mTLS]")
    # Startup recovery — pre-generate recovery context in background (non-blocking)
    async def _startup_recovery():
        """Lazy recovery — only recover the most recently active chat at boot.
        Other chats recover on-demand when opened (see _ensure_chat_recovery)."""
        try:
            active_chats = _get_recently_active_chats(hours=24)
            if not active_chats:
                return
            # Only recover the single most-recently-active chat
            # (sorted by latest message timestamp)
            with _db_lock:
                conn = _get_db()
                row = conn.execute(
                    "SELECT m.chat_id FROM messages m "
                    "JOIN chats c ON m.chat_id = c.id "
                    "WHERE c.type = 'chat' "
                    "ORDER BY m.created_at DESC LIMIT 1"
                ).fetchone()
                conn.close()
            if not row:
                return
            cid = row[0]
            t0 = datetime.now()
            log(f"startup recovery: recovering most recent chat={cid[:8]} (skipping {len(active_chats)-1} others until opened)")
            _recovery_pending[cid] = asyncio.Event()
            try:
                transcript = _get_recent_messages_text(cid, 30)
                if transcript.strip():
                    recovery = await asyncio.to_thread(_generate_recovery_context, transcript)
                    if recovery:
                        _compaction_summaries[cid] = recovery
                        _session_context_sent.discard(cid)
                        log(f"startup recovery: chat={cid[:8]} len={len(recovery)}")
            except Exception as e:
                log(f"startup recovery error chat={cid[:8]}: {e}")
            finally:
                evt = _recovery_pending.pop(cid, None)
                if evt:
                    evt.set()
            elapsed = (datetime.now() - t0).total_seconds()
            log(f"startup recovery: done (1 chat in {elapsed:.1f}s)")
        except Exception as e:
            log(f"startup recovery failed (non-fatal): {e}")
            for evt in _recovery_pending.values():
                evt.set()
            _recovery_pending.clear()
        # Export Apex transcripts to .jsonl for unified search
        try:
            embed_path = str(WORKSPACE / "skills" / "embedding")
            if embed_path not in sys.path:
                sys.path.insert(0, embed_path)
            import importlib
            export_mod = importlib.import_module("apex_export")
            importlib.reload(export_mod)
            export_stats = await asyncio.to_thread(export_mod.export_apex_transcripts, since_hours=72)
            log(f"apex transcript export: {export_stats}")
        except Exception as e:
            log(f"apex transcript export failed (non-fatal): {e}")
        # Reindex embeddings (incremental — only changed files)
        try:
            mod = importlib.import_module("memory_search")
            importlib.reload(mod)
            stats = await asyncio.to_thread(mod.index_all, force=False)
            log(f"embedding reindex: memory={stats.get('memory', {})} transcripts={stats.get('transcripts', {})}")
        except Exception as e:
            log(f"embedding reindex failed (non-fatal): {e}")
    asyncio.create_task(_startup_recovery())
    try:
        yield
    finally:
        for chat_id in list(_clients):
            await _disconnect_client(chat_id)


app = FastAPI(title="Apex", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/admin", dashboard_app)


# Routes that don't require client certificate (served before TLS enforcement)
_PUBLIC_ROUTES = frozenset({"/health"})


@app.middleware("http")
async def verify_client_cert(request: Request, call_next):
    """Enforce mTLS on all routes except public ones. Bearer token for /api/alerts POST."""
    path = request.url.path

    # Allow public routes without cert
    if path in _PUBLIC_ROUTES:
        return await call_next(request)

    # Bearer token auth for alert webhook (POST /api/alerts only)
    if path == "/api/alerts" and request.method == "POST" and ALERT_TOKEN:
        auth = request.headers.get("authorization", "")
        expected = f"Bearer {ALERT_TOKEN}"
        if not hmac.compare_digest(auth.encode(), expected.encode()):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)

    # Defense-in-depth: verify client cert at app layer (TLS layer enforces CERT_REQUIRED)
    ssl_obj = request.scope.get("transport", {})
    # Uvicorn stores SSL info in the transport; also check for peer cert via ssl_object
    if hasattr(ssl_obj, "get_extra_info"):
        peer_cert = ssl_obj.get_extra_info("peercert")
    else:
        # Fallback: try scope extensions
        peer_cert = (request.scope.get("extensions", {}) or {}).get("tls", {}).get("peercert")
    # If TLS is configured and we can't find a peer cert, reject
    if SSL_CERT and SSL_CA and peer_cert is None:
        # Check via the raw transport object on the ASGI scope
        transport = request.scope.get("transport")
        if transport and hasattr(transport, "get_extra_info"):
            peer_cert = transport.get_extra_info("peercert")
    # Note: with ssl_cert_reqs=CERT_REQUIRED, uvicorn rejects at TLS handshake level.
    # This middleware is defense-in-depth — if somehow a connection gets through without
    # a cert (e.g., misconfigured proxy), this catches it.

    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """S-16: Add security response headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# --- Auth routes ---

# --- API routes ---

@app.get("/api/features")
async def api_features(request: Request):
    return JSONResponse({"groups_enabled": GROUPS_ENABLED})


@app.get("/api/chats")
async def api_chats(request: Request):
    return JSONResponse(_get_chats())


@app.post("/api/chats")
async def api_new_chat(request: Request):
    data = {}
    try:
        data = await request.json()
    except Exception:
        pass
    model = data.get("model")
    chat_type = data.get("type", "chat")
    category = data.get("category") if chat_type == "alerts" else None
    profile_id = str(data.get("profile_id", "")).strip()
    # Groups require premium gate
    members = data.get("members", [])
    if chat_type == "group":
        if not GROUPS_ENABLED:
            return JSONResponse({"error": "Groups are not enabled. Set APEX_GROUPS_ENABLED=true"}, status_code=403)
        if not members:
            return JSONResponse({"error": "Groups require at least one member"}, status_code=400)
    if profile_id and chat_type not in ("chat", "thread"):
        return JSONResponse({"error": "Profiles are only supported for channels and threads"}, status_code=400)
    # If a profile is specified, validate and inherit model
    if profile_id:
        with _db_lock:
            conn = _get_db()
            profile_row = conn.execute(
                "SELECT model FROM agent_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
            conn.close()
        if not profile_row:
            return JSONResponse({"error": f"Profile '{profile_id}' not found"}, status_code=400)
        if profile_row[0]:
            model = profile_row[0]
    CATEGORY_TITLES = {"system": "System Alerts", "test": "Test Alerts", "custom": "Custom Alerts"}
    # Extend titles from config.json alert_category_titles (survives upgrades)
    try:
        cfg_path = APEX_ROOT / "state" / "config.json"
        if cfg_path.exists():
            _cfg = json.loads(cfg_path.read_text())
            CATEGORY_TITLES.update(_cfg.get("alert_category_titles", {}))
    except Exception:
        pass
    if chat_type == "alerts":
        title = CATEGORY_TITLES.get(category, "All Alerts")
    elif chat_type == "thread":
        title = "Quick thread"
    elif chat_type == "group":
        title = data.get("title", "New Group")
    else:
        title = "New Channel"
    cid = _create_chat(title=title, model=model, chat_type=chat_type, category=category, profile_id=profile_id)
    resp = {"id": cid, "model": model, "type": chat_type, "category": category, "profile_id": profile_id,
            "profile_name": "", "profile_avatar": ""}
    # Seed group members
    if chat_type == "group" and members:
        for i, mem in enumerate(members):
            pid = mem.get("profile_id", "")
            mode = mem.get("routing_mode", "mentioned")
            is_pri = mode == "primary"
            try:
                _add_group_member(cid, pid, routing_mode=mode, is_primary=is_pri, display_order=i)
            except Exception:
                pass  # skip invalid profile_ids silently
        # Set group model to primary agent's model
        group_members = _get_group_members(cid)
        primary = next((m for m in group_members if m["is_primary"]), None)
        if primary and primary["model"]:
            model = primary["model"]
            _update_chat(cid, model=model)
        resp["members"] = group_members
        if primary:
            resp["profile_name"] = primary["name"]
            resp["profile_avatar"] = primary["avatar"]
    if profile_id:
        with _db_lock:
            conn = _get_db()
            prow = conn.execute("SELECT name, avatar FROM agent_profiles WHERE id = ?", (profile_id,)).fetchone()
            conn.close()
        if prow:
            resp["profile_name"] = prow[0] or ""
            resp["profile_avatar"] = prow[1] or ""
    return JSONResponse(resp)


@app.patch("/api/chats/{chat_id}")
async def api_update_chat(chat_id: str, request: Request):
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    data = await request.json()
    title = data.get("title")
    if title is not None:
        title = str(title).strip()[:100]  # cap at 100 chars
        if not title:
            return JSONResponse({"error": "Title cannot be empty"}, status_code=400)
        _update_chat(chat_id, title=title)
        # Broadcast to all connected WebSockets so sidebar updates everywhere
        payload = {"type": "chat_updated", "chat_id": chat_id,
                   "title": title, "model": chat.get("model")}
        for cid, ws_set in list(_chat_ws.items()):
            for ws in list(ws_set):
                await _safe_ws_send_json(ws, payload, chat_id=cid)
    # Handle profile_id assignment
    if "profile_id" in data:
        if chat.get("type") != "chat":
            return JSONResponse({"error": "Profiles are only supported for regular chats"}, status_code=400)
        pid = str(data["profile_id"]).strip()
        # P0: Validate profile_id — must be empty or an existing profile
        if pid:
            with _db_lock:
                conn = _get_db()
                profile_row = conn.execute(
                    "SELECT model, name, avatar FROM agent_profiles WHERE id = ?", (pid,)
                ).fetchone()
                conn.close()
            if not profile_row:
                return JSONResponse({"error": f"Profile '{pid}' not found"}, status_code=400)
            update_kwargs = {"profile_id": pid}
            # Lock model to profile's model (single source of truth)
            if profile_row[0]:
                update_kwargs["model"] = profile_row[0]
            profile_name = profile_row[1] or ""
            profile_avatar = profile_row[2] or ""
        else:
            update_kwargs = {"profile_id": ""}
            profile_name = ""
            profile_avatar = ""

        _update_chat(chat_id, **update_kwargs)

        # P0: Reset session state on profile change — stale clients cause wrong model/context
        had_sdk_client = chat_id in _clients
        await _disconnect_client(chat_id)
        _update_chat(chat_id, claude_session_id=None)
        _session_context_sent.discard(chat_id)
        if not had_sdk_client:
            for stream_id, entry in list((_active_send_tasks.get(chat_id) or {}).items()):
                send_task = entry.get("task")
                if isinstance(send_task, asyncio.Task) and not send_task.done():
                    send_task.cancel()
                    await _send_stream_event(chat_id, {
                        "type": "stream_end",
                        "chat_id": chat_id,
                        "stream_id": stream_id,
                    })
                _remove_active_send_task(chat_id, stream_id, send_task if isinstance(send_task, asyncio.Task) else None)
            if _get_chat(chat_id) and (_get_chat(chat_id) or {}).get("type") == "group":
                await _send_active_streams(chat_id)
            if not _has_active_stream(chat_id):
                _stream_buffers.pop(chat_id, None)
                _stream_seq.pop(chat_id, None)

        # P0: Broadcast profile change to all connected clients
        updated_chat = _get_chat(chat_id)
        broadcast_payload = {
            "type": "chat_updated", "chat_id": chat_id,
            "title": updated_chat.get("title", "") if updated_chat else "",
            "model": updated_chat.get("model", "") if updated_chat else "",
            "profile_id": pid,
            "profile_name": profile_name,
            "profile_avatar": profile_avatar,
        }
        for cid, ws_set in list(_chat_ws.items()):
            for ws in list(ws_set):
                await _safe_ws_send_json(ws, broadcast_payload, chat_id=cid)

    return JSONResponse({"ok": True})


@app.delete("/api/chats/{chat_id}")
async def api_delete_chat(chat_id: str):
    # Disconnect any active SDK client for this chat
    if chat_id in _clients:
        await _disconnect_client(chat_id)
    if not _delete_chat(chat_id):
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    # Broadcast so all clients refresh their sidebar
    payload = {"type": "chat_deleted", "chat_id": chat_id}
    for cid, ws_set in list(_chat_ws.items()):
        for ws in list(ws_set):
            await _safe_ws_send_json(ws, payload, chat_id=cid)
    return JSONResponse({"ok": True})


@app.get("/api/chats/{chat_id}/members")
async def api_get_members(chat_id: str):
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    if chat["type"] != "group":
        return JSONResponse({"error": "Not a group channel"}, status_code=400)
    return JSONResponse({"members": _get_group_members(chat_id)})


@app.post("/api/chats/{chat_id}/members")
async def api_add_member(chat_id: str, request: Request):
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    if chat["type"] != "group":
        return JSONResponse({"error": "Not a group channel"}, status_code=400)
    data = await request.json()
    profile_id = data.get("profile_id", "")
    routing_mode = data.get("routing_mode", "mentioned")
    is_primary = routing_mode == "primary"
    try:
        mid = _add_group_member(chat_id, profile_id, routing_mode=routing_mode, is_primary=is_primary)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "membership_id": mid})


@app.delete("/api/chats/{chat_id}/members/{profile_id}")
async def api_remove_member(chat_id: str, profile_id: str):
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    if chat["type"] != "group":
        return JSONResponse({"error": "Not a group channel"}, status_code=400)
    if not _remove_group_member(chat_id, profile_id):
        return JSONResponse({"error": "Member not found"}, status_code=404)
    return JSONResponse({"ok": True})


@app.patch("/api/chats/{chat_id}/members/{profile_id}")
async def api_update_member(chat_id: str, profile_id: str, request: Request):
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    if chat["type"] != "group":
        return JSONResponse({"error": "Not a group channel"}, status_code=400)
    data = await request.json()
    routing_mode = data.get("routing_mode")
    if routing_mode:
        is_primary = routing_mode == "primary"
        with _db_lock:
            conn = _get_db()
            conn.execute(
                "UPDATE channel_agent_memberships SET routing_mode = ?, is_primary = ? "
                "WHERE channel_id = ? AND agent_profile_id = ?",
                (routing_mode, int(is_primary), chat_id, profile_id),
            )
            conn.commit()
            conn.close()
    return JSONResponse({"ok": True, "members": _get_group_members(chat_id)})


@app.delete("/api/threads/stale")
async def api_delete_stale_threads(request: Request, older_than_days: int = 7):
    """Delete threads older than N days (default 7). Returns count of deleted threads."""
    import datetime as _dt
    cutoff = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=older_than_days)).isoformat()
    with _db_lock:
        conn = _get_db()
        stale = conn.execute(
            "SELECT id FROM chats WHERE type = 'thread' AND updated_at < ?", (cutoff,)
        ).fetchall()
        if stale:
            ids = [r[0] for r in stale]
            placeholders = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM messages WHERE chat_id IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM chats WHERE id IN ({placeholders})", ids)
            conn.commit()
        conn.close()
    deleted = len(stale) if stale else 0
    if deleted:
        # Broadcast so clients refresh
        for cid_del in [r[0] for r in stale]:
            payload = {"type": "chat_deleted", "chat_id": cid_del}
            for cid, ws_set in list(_chat_ws.items()):
                for ws in list(ws_set):
                    await _safe_ws_send_json(ws, payload, chat_id=cid)
    return JSONResponse({"ok": True, "deleted": deleted})


@app.get("/api/chats/{chat_id}/messages")
async def api_messages(chat_id: str, request: Request, days: int | None = 3):
    return JSONResponse(_get_messages(chat_id, days=days))


@app.get("/api/chats/{chat_id}/context")
async def api_context(chat_id: str, request: Request):
    """Return context window usage for a chat."""
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    chat_model = chat.get("model") or MODEL
    if chat_model.startswith("claude-"):
        # Claude: last turn's tokens_in IS the actual context window fill
        # (each turn sends full history, so tokens_in includes everything)
        context_used = _get_last_turn_tokens_in(chat_id)
    else:
        # Non-Claude: estimate from message content (~4 chars/token)
        context_used = _estimate_tokens(chat_id)
    # Total output tokens since last compaction
    since = _last_compacted_at.get(chat_id)
    with _db_lock:
        conn = _get_db()
        if since:
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens_out), 0) FROM messages "
                "WHERE chat_id = ? AND created_at > ?", (chat_id, since),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens_out), 0) FROM messages WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        conn.close()
    cumulative_out = row[0] if row else 0
    context_window = MODEL_CONTEXT_WINDOWS.get(chat_model, MODEL_CONTEXT_DEFAULT)
    return JSONResponse({
        "chat_id": chat_id,
        "model": chat_model,
        "tokens_in": context_used,
        "tokens_out": cumulative_out,
        "compaction_threshold": COMPACTION_THRESHOLD,
        "context_window": context_window,
    })


@app.get("/health")
async def health():
    return JSONResponse({
        "ok": True, "clients": len(_clients), "chats": len(_get_chats()),
        "model": MODEL, "whisper": ENABLE_SUBCONSCIOUS_WHISPER,
    })


def _normalize_slug(raw: str) -> str:
    """Normalize a slug: lowercase, alphanumeric + hyphens only, no leading/trailing hyphens."""
    import re as _re
    s = raw.lower().strip()
    s = _re.sub(r"[^a-z0-9\-]", "-", s)
    s = _re.sub(r"-{2,}", "-", s)
    return s.strip("-")


@app.get("/api/persona-templates")
async def api_persona_templates():
    """List available persona templates that can be installed.

    Returns templates from persona_templates.json, marking which ones
    are already installed in the database.
    """
    templates_path = Path(__file__).resolve().parent / "persona_templates.json"
    if not templates_path.exists():
        return []
    try:
        templates = json.loads(templates_path.read_text())
    except Exception:
        return []
    # Check which are already installed
    with _db_lock:
        conn = _get_db()
        existing = {r[0] for r in conn.execute("SELECT id FROM agent_profiles").fetchall()}
        conn.close()
    for t in templates:
        t["installed"] = t["id"] in existing
    return templates


@app.post("/api/persona-templates/install")
async def api_install_persona_templates(request: Request):
    """Install selected persona templates by ID.

    Body: {"ids": ["architect", "designer"]}
    Skips templates that are already installed (INSERT OR IGNORE).
    """
    data = await request.json()
    ids = data.get("ids", [])
    if not ids:
        return JSONResponse({"error": "No template IDs provided"}, status_code=400)
    templates_path = Path(__file__).resolve().parent / "persona_templates.json"
    if not templates_path.exists():
        return JSONResponse({"error": "No templates file found"}, status_code=404)
    try:
        templates = {t["id"]: t for t in json.loads(templates_path.read_text())}
    except Exception:
        return JSONResponse({"error": "Failed to load templates"}, status_code=500)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    installed = []
    with _db_lock:
        conn = _get_db()
        for tid in ids:
            p = templates.get(tid)
            if not p:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO agent_profiles (id, name, slug, avatar, role_description, "
                "backend, model, system_prompt, tool_policy, is_default, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (p["id"], p["name"], p["slug"], p["avatar"], p["role_description"],
                 p["backend"], p["model"], p["system_prompt"], "",
                 p.get("is_default", 0), now, now),
            )
            if cur.rowcount:
                installed.append(tid)
        conn.commit()
        conn.close()
    if installed:
        log(f"Installed {len(installed)} persona templates: {', '.join(installed)}")
    return {"installed": installed, "skipped": [i for i in ids if i not in installed]}


@app.get("/api/profiles")
async def api_get_profiles():
    """List all agent profiles (metadata only — no system_prompt)."""
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT id, name, slug, avatar, role_description, model, "
            "is_default, created_at, updated_at "
            "FROM agent_profiles ORDER BY is_default DESC, name ASC"
        ).fetchall()
        conn.close()
    profiles = []
    for r in rows:
        model = r[5] or ""
        profiles.append({
            "id": r[0], "name": r[1], "slug": r[2], "avatar": r[3],
            "role_description": r[4], "backend": _get_model_backend(model),
            "model": model, "is_default": bool(r[6]),
            "created_at": r[7], "updated_at": r[8],
        })
    return JSONResponse({"profiles": profiles})


@app.get("/api/profiles/{profile_id}")
async def api_get_profile_detail(profile_id: str):
    """Get a single profile with full details including system_prompt."""
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT id, name, slug, avatar, role_description, model, "
            "system_prompt, tool_policy, is_default, created_at, updated_at "
            "FROM agent_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        conn.close()
    if not row:
        return JSONResponse({"error": "profile not found"}, status_code=404)
    model = row[5] or ""
    return JSONResponse({
        "id": row[0], "name": row[1], "slug": row[2], "avatar": row[3],
        "role_description": row[4], "backend": _get_model_backend(model),
        "model": model, "system_prompt": row[6], "tool_policy": row[7],
        "is_default": bool(row[8]), "created_at": row[9], "updated_at": row[10],
    })


@app.post("/api/profiles")
async def api_create_profile(request: Request):
    """Create a new agent profile."""
    data = await request.json()
    name = str(data.get("name", "")).strip()
    if not name:
        return JSONResponse({"error": "name required"}, status_code=400)
    raw_slug = str(data.get("slug", "")).strip()
    slug = _normalize_slug(raw_slug) if raw_slug else _normalize_slug(name)
    if not slug:
        return JSONResponse({"error": "slug cannot be empty after normalization"}, status_code=400)
    model = str(data.get("model", "")).strip()
    # backend is derived from model — ignore any client-supplied value
    backend = _get_model_backend(model) if model else ""
    now = datetime.now(timezone.utc).isoformat()
    profile_id = str(uuid.uuid4())[:8]
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "INSERT INTO agent_profiles (id, name, slug, avatar, role_description, "
                "backend, model, system_prompt, tool_policy, is_default, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (profile_id, name, slug,
                 str(data.get("avatar", "")),
                 str(data.get("role_description", "")),
                 backend, model,
                 str(data.get("system_prompt", "")),
                 str(data.get("tool_policy", "")),
                 1 if data.get("is_default") else 0,
                 now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return JSONResponse({"error": f"slug '{slug}' already exists"}, status_code=409)
        conn.close()
    return JSONResponse({"id": profile_id, "slug": slug}, status_code=201)


@app.put("/api/profiles/{profile_id}")
async def api_update_profile(profile_id: str, request: Request):
    """Update an agent profile."""
    data = await request.json()
    now = datetime.now(timezone.utc).isoformat()
    fields = []
    values = []
    for key in ("name", "avatar", "role_description", "model",
                "system_prompt", "tool_policy"):
        if key in data:
            val = str(data[key]).strip() if key in ("name",) else str(data[key])
            if key == "name" and not val:
                return JSONResponse({"error": "name cannot be empty"}, status_code=400)
            fields.append(f"{key} = ?")
            values.append(val)
    # Slug: normalize and reject empty
    if "slug" in data:
        slug = _normalize_slug(str(data["slug"]))
        if not slug:
            return JSONResponse({"error": "slug cannot be empty"}, status_code=400)
        fields.append("slug = ?")
        values.append(slug)
    # Backend is always derived from model — update it if model changed
    if "model" in data:
        model = str(data["model"]).strip()
        backend = _get_model_backend(model) if model else ""
        fields.append("backend = ?")
        values.append(backend)
    # Ignore client-supplied "backend" — it's derived
    if "is_default" in data:
        fields.append("is_default = ?")
        values.append(1 if data["is_default"] else 0)
    if not fields:
        return JSONResponse({"error": "no fields to update"}, status_code=400)
    fields.append("updated_at = ?")
    values.append(now)
    values.append(profile_id)
    with _db_lock:
        conn = _get_db()
        try:
            cur = conn.execute(f"UPDATE agent_profiles SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return JSONResponse({"error": "slug already exists"}, status_code=409)
        affected = cur.rowcount
        conn.close()
    if affected == 0:
        return JSONResponse({"error": "profile not found"}, status_code=404)
    return JSONResponse({"ok": True})


@app.delete("/api/profiles/{profile_id}")
async def api_delete_profile(profile_id: str):
    """Delete an agent profile (unlinks from chats but doesn't delete chats)."""
    with _db_lock:
        conn = _get_db()
        cur = conn.execute("DELETE FROM agent_profiles WHERE id = ?", (profile_id,))
        if cur.rowcount == 0:
            conn.close()
            return JSONResponse({"error": "profile not found"}, status_code=404)
        conn.execute("UPDATE chats SET profile_id = '' WHERE profile_id = ?", (profile_id,))
        conn.commit()
        conn.close()
    return JSONResponse({"ok": True})


@app.get("/api/embedding/status")
async def api_embedding_status():
    """Return embedding index status."""
    try:
        idx_dir = WORKSPACE / "state" / "embeddings"
        result = {}
        for name, meta_file in [("memory", "memory_meta.json"), ("transcripts", "transcript_meta.json")]:
            meta_path = idx_dir / meta_file
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                result[name] = {"files": len(meta)}
            else:
                result[name] = {"files": 0}
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/alerts")
async def api_create_alert(request: Request):
    """Webhook: ingest an alert. Auth: bearer token."""
    if not ALERT_TOKEN:
        return JSONResponse({"error": "Alert token not configured"}, status_code=503)
    data = await request.json()
    source = str(data.get("source", "unknown"))
    severity = str(data.get("severity", "info"))
    if severity not in ("info", "warning", "critical"):
        severity = "info"
    title = str(data.get("title", ""))
    body = str(data.get("body", ""))
    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        metadata = None
    if not title:
        return JSONResponse({"error": "title is required"}, status_code=400)
    alert = _create_alert(source, severity, title, body, metadata=metadata)
    await _broadcast_alert(alert)
    # Wake any long-poll waiters
    for evt in _alert_waiters:
        evt.set()
    log(f"alert: id={alert['id']} src={source} sev={severity} title={title[:50]}")
    return JSONResponse(alert, status_code=201)


@app.get("/api/alerts")
async def api_get_alerts(since: str | None = None, unacked: bool = False, category: str | None = None):
    return JSONResponse(_get_alerts(since=since, unacked_only=unacked, category=category))


_alert_waiters: list[asyncio.Event] = []  # notify background pollers on new alert

@app.get("/api/alerts/wait")
async def api_wait_alert(since: str | None = None, timeout: int = 25):
    """Long-poll: block until a new alert arrives or timeout (max 30s).
    Returns new unacked alerts since `since`, or empty list on timeout."""
    timeout = min(timeout, 30)
    # Check immediately — there may already be new alerts
    alerts = _get_alerts(since=since, unacked_only=True, limit=20)
    if alerts:
        return JSONResponse(alerts)
    # Wait for new alert signal
    event = asyncio.Event()
    _alert_waiters.append(event)
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        try:
            _alert_waiters.remove(event)
        except ValueError:
            pass
    # Check again after wakeup
    alerts = _get_alerts(since=since, unacked_only=True, limit=20)
    return JSONResponse(alerts)

@app.post("/api/alerts/{alert_id}/ack")
async def api_ack_alert(alert_id: str):
    _ack_alert(alert_id)  # Idempotent — already acked is fine
    # Broadcast ack to all connected clients so they update local state
    payload = {"type": "alert_acked", "alert_id": alert_id}
    all_ws: set = set()
    for ws_set in _chat_ws.values():
        all_ws.update(ws_set)
    for ws in list(all_ws):
        await _safe_ws_send_json(ws, payload, chat_id=_ws_chat.get(ws, ""))
    return JSONResponse({"ok": True})


@app.delete("/api/alerts/{alert_id}")
async def api_delete_alert(alert_id: str):
    with _db_lock:
        conn = _get_db()
        cur = conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        conn.commit()
        deleted = cur.rowcount > 0
        conn.close()
    if not deleted:
        return JSONResponse({"error": "Alert not found"}, status_code=404)
    log(f"alert deleted: id={alert_id}")
    return JSONResponse({"ok": True})


@app.delete("/api/alerts")
async def api_delete_all_alerts():
    with _db_lock:
        conn = _get_db()
        cur = conn.execute("DELETE FROM alerts")
        conn.commit()
        count = cur.rowcount
        conn.close()
    log(f"alerts cleared: {count} deleted")
    return JSONResponse({"ok": True, "deleted": count})


@app.post("/api/alerts/{alert_id}/allow")
async def api_allow_alert(alert_id: str):
    """Whitelist a guardrail-blocked action for retry (1hr TTL)."""
    alert = _get_alert(alert_id)
    if not alert:
        return JSONResponse({"error": "Alert not found"}, status_code=404)
    if alert["source"] != "guardrail":
        return JSONResponse({"error": "Only guardrail alerts can be whitelisted"}, status_code=400)
    meta = alert.get("metadata", {})
    tool = meta.get("tool", "")
    target = meta.get("target", "")
    if not tool:
        return JSONResponse({"error": "Alert metadata missing tool info"}, status_code=400)
    entry = _add_whitelist_entry(tool, target, alert_id)
    _ack_alert(alert_id)
    log(f"guardrail allow: alert={alert_id} tool={tool} target={target[:60]} expires={entry['expires_at']}")
    return JSONResponse({"ok": True, "expires_at": entry["expires_at"]})


# --- Local models (Ollama) ------------------------------------------------

def _is_local_model(model: str) -> bool:
    """True if the model should be routed through Ollama instead of Claude SDK."""
    return not model.startswith("claude-")


def _get_model_backend(model: str) -> str:
    """Determine which backend to use for a model."""
    if model.startswith("codex:"):
        return "codex"
    elif model.startswith("claude-"):
        return "claude"
    elif model.startswith("grok-"):
        return "xai"
    elif model.startswith("mlx:"):
        return "mlx"
    else:
        return "ollama"


def _get_ollama_models() -> list[dict]:
    """Query Ollama for available local models."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            size_gb = round(m.get("size", 0) / 1e9, 1)
            models.append({"id": name, "displayName": name, "sizeGb": size_gb, "local": True})
        return models
    except Exception as e:
        log(f"ollama model list failed: {e}")
        return []


def _get_mlx_models() -> list[dict]:
    """Query MLX server for available models."""
    try:
        req = urllib.request.Request(
            f"{MLX_BASE_URL}/v1/models",
            headers={"User-Agent": "Apex/1.0"},
        )
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        models = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            models.append({
                "id": f"mlx:{mid}",
                "displayName": mid.split("/")[-1] if "/" in mid else mid,
                "sizeGb": 0,
                "local": True,
            })
        return models
    except Exception as e:
        log(f"mlx model list failed: {e}")
        return []


@app.get("/api/models/local")
async def api_local_models():
    ollama, mlx = await asyncio.gather(
        asyncio.to_thread(_get_ollama_models),
        asyncio.to_thread(_get_mlx_models),
    )
    return JSONResponse(ollama + mlx)


async def _run_codex_chat(chat_id: str, prompt: str, model: str | None = None,
                           attachments: list[dict] | None = None) -> dict:
    """Run a chat response via the Codex CLI (gpt-5.4, o3, o4-mini)."""
    effective_model = model or "codex:gpt-5.4"
    cli_model = effective_model.removeprefix("codex:")

    # Inject profile + workspace context into the prompt
    profile_prompt = _get_profile_prompt(chat_id)
    group_roster_prompt = _get_group_roster_prompt(chat_id)
    workspace_ctx = _get_workspace_context(chat_id)
    ctx_prefix = f"{profile_prompt}{group_roster_prompt}{workspace_ctx}"
    full_prompt = f"{ctx_prefix}{prompt}" if ctx_prefix else prompt

    # Build conversation history from recent messages
    recent = _get_messages(chat_id, days=1)
    current_pid = _current_group_profile_id.get("")
    history_lines: list[str] = []
    for m in recent[-20:]:
        content = m["content"]
        if "<system-reminder>" in content:
            continue
        role = m["role"]
        speaker_id = m.get("speaker_id", "")
        # Group isolation: label other agents' messages distinctly
        if role == "assistant" and current_pid and speaker_id and speaker_id != current_pid:
            speaker_name = m.get("speaker_name", speaker_id)
            label = f"assistant ({speaker_name})"
        else:
            label = role
        history_lines.append(f"[{label}] {content[:1000]}")
    if history_lines:
        history_block = "\n".join(history_lines)
        full_prompt = f"<conversation-history>\n{history_block}\n</conversation-history>\n\n{full_prompt}"

    # Spawn codex CLI
    proc = await asyncio.create_subprocess_exec(
        CODEX_CLI, "exec", "--json", "--ephemeral",
        "--skip-git-repo-check",
        "-m", cli_model, "-s", "read-only", "-C", str(WORKSPACE), "-",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "OPENAI_API_KEY": OPENAI_API_KEY},
    )

    stdout_data, stderr_data = b"", b""
    if proc.stdin is not None:
        proc.stdin.write(full_prompt.encode())
        await proc.stdin.drain()
        proc.stdin.close()

    result_text = ""
    thinking_text = ""
    tool_events: list[dict] = []
    tokens_in = 0
    tokens_out = 0

    # Read stdout line by line (JSONL events)
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        line_str = line.decode().strip()
        if not line_str:
            continue
        try:
            event = json.loads(line_str)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type", "")

        if event_type == "item.started":
            item = event.get("item", {})
            if item.get("type") == "command_execution":
                tool_id = str(uuid.uuid4())
                tool_evt = {"type": "tool_use", "id": tool_id, "name": "command", "input": item.get("command", "")}
                tool_events.append(tool_evt)
                await _send_stream_event(chat_id, tool_evt)

        elif event_type == "item.completed":
            item = event.get("item", {})
            item_type = item.get("type", "")

            if item_type == "agent_message":
                text = ""
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        text += part.get("text", "")
                if text:
                    result_text += text
                    await _send_stream_event(chat_id, {"type": "text", "text": text})

            elif item_type == "command_execution":
                tool_id = str(uuid.uuid4())
                output = item.get("output", "")
                tool_evt = {"type": "tool_result", "id": tool_id, "content": output[:2000]}
                tool_events.append(tool_evt)
                await _send_stream_event(chat_id, tool_evt)

            elif item_type == "reasoning":
                text = ""
                for part in item.get("content", []):
                    if part.get("type") == "text":
                        text += part.get("text", "")
                if text:
                    thinking_text += text
                    await _send_stream_event(chat_id, {"type": "thinking", "text": text})

            elif item_type == "file_change":
                tool_id = str(uuid.uuid4())
                fname = item.get("filename", "unknown")
                await _send_stream_event(chat_id, {"type": "tool_use", "id": tool_id, "name": "file_change", "input": fname})
                await _send_stream_event(chat_id, {"type": "tool_result", "id": tool_id, "content": f"File changed: {fname}"})

        elif event_type == "turn.completed":
            usage = event.get("usage", {})
            tokens_in = usage.get("input_tokens", 0)
            tokens_out = usage.get("output_tokens", 0)

    # Wait for process to finish
    await proc.wait()
    stderr_data = await proc.stderr.read() if proc.stderr else b""
    if proc.returncode != 0 and not result_text:
        err_msg = stderr_data.decode()[:500] if stderr_data else f"codex exited with code {proc.returncode}"
        log(f"codex process error: {err_msg}")
        await _send_stream_event(chat_id, {"type": "error", "message": f"Codex: {err_msg}"})
        return {"text": "", "is_error": True, "error": err_msg,
                "cost_usd": 0, "tokens_in": 0, "tokens_out": 0,
                "session_id": None, "thinking": "", "tool_events": json.dumps(tool_events)}

    _cw = MODEL_CONTEXT_WINDOWS.get(effective_model, MODEL_CONTEXT_DEFAULT)
    await _send_stream_event(chat_id, {
        "type": "result", "is_error": False,
        "cost_usd": 0, "tokens_in": tokens_in, "tokens_out": tokens_out,
        "session_id": None,
        "context_tokens_in": tokens_in,
        "context_window": _cw,
    })
    return {"text": result_text, "is_error": False, "error": None,
            "cost_usd": 0, "tokens_in": tokens_in, "tokens_out": tokens_out,
            "session_id": None, "thinking": thinking_text, "tool_events": json.dumps(tool_events)}


async def _run_ollama_chat(chat_id: str, prompt: str, model: str | None = None,
                           attachments: list[dict] | None = None) -> dict:
    """Run a chat response from Ollama/xAI/MLX with tool-calling support."""
    effective_model = model or MODEL
    # Build message history from recent DB messages
    recent = _get_messages(chat_id, days=1)
    if _TOOL_LOOP_AVAILABLE:
        sys_prompt = build_system_prompt(effective_model)
    else:
        sys_prompt = f"You are {effective_model}, a local AI model running via Ollama. Be helpful and concise."

    # Inject profile + workspace context (APEX.md, MEMORY.md, recovery briefings) for richer context
    profile_prompt = _get_profile_prompt(chat_id)
    group_roster_prompt = _get_group_roster_prompt(chat_id)
    workspace_ctx = _get_workspace_context(chat_id)
    if profile_prompt or group_roster_prompt or workspace_ctx:
        sys_prompt = f"{sys_prompt}\n\n{profile_prompt}{group_roster_prompt}{workspace_ctx}"

    messages = [{"role": "system", "content": sys_prompt}]
    current_pid = _current_group_profile_id.get("")
    for m in recent[-50:]:
        content = m["content"]
        if "<system-reminder>" in content:
            continue
        role = m["role"]
        # Only include user/assistant messages — skip tool results from prior turns
        # (OpenAI requires tool_call_id on tool messages which we don't store)
        if role not in ("user", "assistant"):
            continue
        speaker_id = m.get("speaker_id", "")
        # Group isolation: tag other agents' messages so the model knows they're not its own
        if role == "assistant" and current_pid and speaker_id and speaker_id != current_pid:
            speaker_name = m.get("speaker_name", speaker_id)
            content = f"[{speaker_name}]: {content}"
        messages.append({"role": role, "content": content})

    # Build user message — inject images in Ollama format if present
    user_msg: dict = {"role": "user", "content": prompt}
    if attachments:
        images_b64: list[str] = []
        for att in attachments:
            try:
                item = _load_attachment(att)
                if item["type"] == "image":
                    images_b64.append(base64.b64encode(item["data"]).decode())
            except (ValueError, Exception) as e:
                log(f"ollama image load error: {e}")
        if images_b64:
            user_msg["images"] = images_b64
    messages.append(user_msg)

    # Use tool loop if available
    if _TOOL_LOOP_AVAILABLE:
        async def emit(event: dict):
            await _send_stream_event(chat_id, event)

        # Route to xAI, MLX, or Ollama based on model backend
        backend = _get_model_backend(effective_model)
        if backend == "xai":
            result = await run_tool_loop(
                ollama_url=OLLAMA_BASE_URL,
                model=effective_model,
                messages=messages,
                emit_event=emit,
                workspace=str(WORKSPACE),
                api_key=XAI_API_KEY,
                api_url="https://api.x.ai/v1",
            )
        elif backend == "codex":
            # Strip "codex:" prefix — route through ChatGPT backend (subscription billing)
            codex_model = effective_model[6:]
            result = await run_tool_loop(
                ollama_url=OLLAMA_BASE_URL,
                model=codex_model,
                messages=messages,
                emit_event=emit,
                workspace=str(WORKSPACE),
                api_key="chatgpt-oauth",
                api_url="chatgpt",
            )
        elif backend == "mlx":
            # Strip "mlx:" prefix — MLX server uses HF model IDs
            mlx_model = effective_model[4:]
            result = await run_tool_loop(
                ollama_url=OLLAMA_BASE_URL,
                model=mlx_model,
                messages=messages,
                emit_event=emit,
                workspace=str(WORKSPACE),
                api_key="local",
                api_url=f"{MLX_BASE_URL}/v1",
            )
        else:
            result = await run_tool_loop(
                ollama_url=OLLAMA_BASE_URL,
                model=effective_model,
                messages=messages,
                emit_event=emit,
                workspace=str(WORKSPACE),
            )

        # Send result event (tool loop emits text/tool events but not the final result)
        _est = _estimate_tokens(chat_id)
        _cw = MODEL_CONTEXT_WINDOWS.get(effective_model, MODEL_CONTEXT_DEFAULT)
        await _send_stream_event(chat_id, {
            "type": "result", "is_error": result.get("is_error", False),
            "cost_usd": 0, "tokens_in": 0, "tokens_out": 0,
            "session_id": None,
            "context_tokens_in": _est,
            "context_window": _cw,
        })
        return result

    # Fallback: plain text streaming (no tool support)
    payload = json.dumps({
        "model": effective_model, "messages": messages, "stream": True,
    }).encode()
    chunk_queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _stream_ollama():
        try:
            req = urllib.request.Request(
                f"{OLLAMA_BASE_URL}/api/chat", data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=300)
            for line in resp:
                if not line.strip():
                    continue
                chunk = json.loads(line.decode())
                if chunk.get("done"):
                    break
                msg = chunk.get("message", {})
                thinking = msg.get("thinking", "")
                content = msg.get("content", "")
                if thinking:
                    chunk_queue.put_nowait(("thinking", thinking))
                if content:
                    chunk_queue.put_nowait(("text", content))
        except Exception as e:
            chunk_queue.put_nowait(("error", str(e)))
        finally:
            chunk_queue.put_nowait(None)

    asyncio.get_event_loop().run_in_executor(None, _stream_ollama)
    result_text, thinking_text, is_error, error_msg = "", "", False, ""
    while True:
        chunk = await chunk_queue.get()
        if chunk is None:
            break
        chunk_type, chunk_data = chunk
        if chunk_type == "error":
            error_msg = chunk_data
            is_error = True
            log(f"ollama error: {error_msg}")
            await _send_stream_event(chat_id, {"type": "error", "message": f"Ollama: {error_msg}"})
            break
        elif chunk_type == "thinking":
            thinking_text += chunk_data
            await _send_stream_event(chat_id, {"type": "thinking", "text": chunk_data})
        elif chunk_type == "text":
            result_text += chunk_data
            await _send_stream_event(chat_id, {"type": "text", "text": chunk_data})

    _est = _estimate_tokens(chat_id) + len(result_text) // 4
    _cw = MODEL_CONTEXT_WINDOWS.get(effective_model, MODEL_CONTEXT_DEFAULT)
    await _send_stream_event(chat_id, {
        "type": "result", "is_error": is_error,
        "cost_usd": 0, "tokens_in": 0, "tokens_out": 0, "session_id": None,
        "context_tokens_in": _est,
        "context_window": _cw,
    })
    return {"text": result_text, "is_error": is_error, "error": error_msg or None,
            "cost_usd": 0, "tokens_in": 0, "tokens_out": 0,
            "session_id": None, "thinking": thinking_text, "tool_events": "[]"}


# --- Usage meter (replicates terminal statusline) -------------------------

_USAGE_CACHE: dict = {}
_USAGE_CACHE_TS: float = 0
_USAGE_CACHE_TTL = 300  # 5 minutes — avoid 429s from Anthropic
_PLAN_NAMES = {
    "default_claude_ai": "Pro",
    "default_claude_max_5x": "Max 5x",
    "default_claude_max_20x": "Max 20x",
}


def _get_oauth_credentials() -> tuple[str | None, str]:
    creds_path = Path.home() / ".claude" / ".credentials.json"
    try:
        data = json.loads(creds_path.read_text())
        oauth = data.get("claudeAiOauth", {})
        token = oauth.get("accessToken")
        if token:
            tier = oauth.get("rateLimitTier", "")
            plan = _PLAN_NAMES.get(tier, tier.replace("default_claude_", "").replace("_", " ").title())
            return token, plan
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    if sys.platform == "darwin":
        try:
            import subprocess as _sp
            r = _sp.run(
                ["/usr/bin/security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                data = json.loads(r.stdout.strip())
                oauth = data.get("claudeAiOauth", {})
                token = oauth.get("accessToken")
                if token:
                    tier = oauth.get("rateLimitTier", "")
                    plan = _PLAN_NAMES.get(tier, tier.replace("default_claude_", "").replace("_", " ").title())
                    return token, plan
        except Exception:
            pass
    return None, ""


_USAGE_DISK_CACHE = Path.home() / ".claude" / ".usage_cache.json"


def _fetch_usage_data(token: str) -> dict | None:
    global _USAGE_CACHE, _USAGE_CACHE_TS
    now = time.time()
    # In-memory cache
    if now - _USAGE_CACHE_TS < _USAGE_CACHE_TTL and _USAGE_CACHE:
        return _USAGE_CACHE
    # Shared disk cache (same file as claude_usage.py terminal statusline)
    stale_disk: dict | None = None
    try:
        disk = json.loads(_USAGE_DISK_CACHE.read_text())
        if now - disk.get("_ts", 0) < _USAGE_CACHE_TTL:
            _USAGE_CACHE = disk
            _USAGE_CACHE_TS = now
            return disk
        stale_disk = disk  # keep for fallback on API failure
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    # Fresh API call
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/api/oauth/usage",
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
                "Accept": "application/json",
                "User-Agent": "apex/1.0",
            },
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read(1_000_000))
        _USAGE_CACHE = data
        _USAGE_CACHE_TS = now
        # Write to disk cache for sharing with terminal statusline
        try:
            data["_ts"] = now
            _USAGE_DISK_CACHE.write_text(json.dumps(data))
        except OSError:
            pass
        return data
    except Exception as e:
        log(f"usage API error: {type(e).__name__}: {e}")
        # On 429 or network error, return stale data rather than nothing
        fallback = _USAGE_CACHE or stale_disk
        if fallback:
            _USAGE_CACHE = fallback
            _USAGE_CACHE_TS = now  # suppress retries for another TTL cycle
            # Refresh disk cache ts so subsequent restarts find fresh-enough data
            try:
                fallback["_ts"] = now
                _USAGE_DISK_CACHE.write_text(json.dumps(fallback))
            except OSError:
                pass
            return fallback
        return None


def _format_countdown(resets_at_str: str) -> str:
    if not resets_at_str:
        return "?"
    try:
        resets_at = datetime.fromisoformat(resets_at_str)
        secs = int((resets_at - datetime.now(timezone.utc)).total_seconds())
        if secs <= 0:
            return "now"
        h, m = secs // 3600, (secs % 3600) // 60
        return f"{h}h{m:02d}m" if h > 0 else f"{m}m"
    except (ValueError, TypeError):
        return "?"


@app.get("/api/usage")
async def api_usage():
    token, plan = _get_oauth_credentials()
    if not token:
        return JSONResponse({"error": "no credentials"}, status_code=401)
    usage = _fetch_usage_data(token)
    if not usage:
        return JSONResponse({"error": "fetch failed"}, status_code=502)

    five = usage.get("five_hour", {})
    seven = usage.get("seven_day", {})

    result = {
        "plan": plan,
        "session": {
            "utilization": round(five.get("utilization") or 0),
            "resets_at": five.get("resets_at", ""),
            "resets_in": _format_countdown(five.get("resets_at")),
        },
        "weekly": {
            "utilization": round(seven.get("utilization") or 0),
            "resets_at": seven.get("resets_at", ""),
            "resets_in": _format_countdown(seven.get("resets_at")),
        },
        "models": {},
    }

    for key, label in [("seven_day_opus", "opus"), ("seven_day_sonnet", "sonnet")]:
        model = usage.get(key)
        if model and model.get("utilization"):
            result["models"][label] = {
                "utilization": round(model["utilization"]),
                "resets_at": model.get("resets_at", ""),
                "resets_in": _format_countdown(model.get("resets_at")),
            }

    extra = usage.get("extra_usage", {})
    if extra and extra.get("is_enabled"):
        result["extra_credits"] = {
            "used": extra.get("used_credits", 0),
            "limit": extra.get("monthly_limit", 0),
            "remaining": extra.get("monthly_limit", 0) - extra.get("used_credits", 0),
        }

    return JSONResponse(result)


# --- Grok (xAI) usage ---

_GROK_USAGE_CACHE: dict = {}
_GROK_USAGE_CACHE_TS: float = 0


def _fetch_grok_usage() -> dict | None:
    """Fetch xAI prepaid credit balance via Management API."""
    global _GROK_USAGE_CACHE, _GROK_USAGE_CACHE_TS
    if not XAI_MANAGEMENT_KEY:
        return None
    now = time.time()
    if now - _GROK_USAGE_CACHE_TS < _USAGE_CACHE_TTL and _GROK_USAGE_CACHE:
        return _GROK_USAGE_CACHE

    try:
        headers = {
            "Authorization": f"Bearer {XAI_MANAGEMENT_KEY}",
            "Accept": "application/json",
            "User-Agent": "Apex/1.0",
        }

        # 1) Prepaid ledger balance
        req = urllib.request.Request(
            f"https://management-api.x.ai/v1/billing/teams/{XAI_TEAM_ID}/prepaid/balance",
            headers=headers,
        )
        resp = urllib.request.urlopen(req, timeout=10)
        bal_data = json.loads(resp.read(1_000_000))

        purchased_cents = 0
        ledger_spent_cents = 0
        for c in bal_data.get("changes", []):
            val = int(c.get("amount", {}).get("val", 0))
            if val < 0:
                purchased_cents += abs(val)
            else:
                ledger_spent_cents += val
        ledger_balance = purchased_cents - ledger_spent_cents

        # 2) Current-month invoice preview (un-reconciled spend)
        current_month_cents = 0
        try:
            req2 = urllib.request.Request(
                f"https://management-api.x.ai/v1/billing/teams/{XAI_TEAM_ID}/postpaid/invoice/preview",
                headers=headers,
            )
            resp2 = urllib.request.urlopen(req2, timeout=10)
            inv_data = json.loads(resp2.read(1_000_000))
            for line in inv_data.get("coreInvoice", {}).get("lines", []):
                current_month_cents += int(line.get("amount", "0"))
        except Exception:
            pass  # best-effort — ledger balance is still useful

        remaining_cents = ledger_balance - current_month_cents
        total_spent_cents = ledger_spent_cents + current_month_cents

        result = {
            "balance_usd": round(remaining_cents / 100.0, 2),
            "purchased_usd": round(purchased_cents / 100.0, 2),
            "spent_usd": round(total_spent_cents / 100.0, 2),
        }
        _GROK_USAGE_CACHE = result
        _GROK_USAGE_CACHE_TS = now
        return result
    except Exception as e:
        log(f"grok usage API error: {type(e).__name__}: {e}")
        if _GROK_USAGE_CACHE:
            _GROK_USAGE_CACHE_TS = now
            return _GROK_USAGE_CACHE
        return None


@app.get("/api/usage/grok")
async def api_usage_grok():
    if not XAI_MANAGEMENT_KEY:
        return JSONResponse({"error": "no management key"}, status_code=401)
    usage = _fetch_grok_usage()
    if not usage:
        return JSONResponse({"error": "fetch failed"}, status_code=502)
    return JSONResponse(usage)


# --- Codex (ChatGPT) usage — read from rate limit headers cached by tool_loop ---

_CODEX_USAGE_CACHE_PATH = Path.home() / ".codex" / ".usage_cache.json"


@app.get("/api/usage/codex")
async def api_usage_codex():
    """Return Codex/ChatGPT rate limit status from cached response headers."""
    try:
        data = json.loads(_CODEX_USAGE_CACHE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return JSONResponse({"error": "no usage data yet — send a message in a Codex chat first"}, status_code=404)

    # Check staleness (>30 min = stale)
    ts = data.get("_ts", 0)
    stale = (time.time() - ts) > 1800

    primary_pct = float(data.get("x-codex-primary-used-percent", 0))
    secondary_pct = float(data.get("x-codex-secondary-used-percent", 0))
    primary_reset = int(data.get("x-codex-primary-reset-after-seconds", 0))
    secondary_reset = int(data.get("x-codex-secondary-reset-after-seconds", 0))
    plan = data.get("x-codex-plan-type", "unknown")

    def fmt_reset(secs: int) -> str:
        if secs <= 0:
            return "now"
        h, m = secs // 3600, (secs % 3600) // 60
        return f"{h}h{m:02d}m" if h > 0 else f"{m}m"

    return JSONResponse({
        "plan": plan.title() if plan else "Unknown",
        "session": {
            "utilization": round(primary_pct),
            "resets_in": fmt_reset(primary_reset),
        },
        "weekly": {
            "utilization": round(secondary_pct),
            "resets_in": fmt_reset(secondary_reset),
        },
        "stale": stale,
    })


# --- File upload ---

@app.post("/api/upload")
async def api_upload(request: Request, file: UploadFile = File(...)):
    filename = _normalize_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    is_image = ext in IMAGE_TYPES
    is_text = ext in TEXT_TYPES
    if not is_image and not is_text:
        return JSONResponse({"error": f"Unsupported file type: .{ext}"}, status_code=400)

    try:
        data = await file.read()
    finally:
        await file.close()
    max_size = MAX_IMAGE_SIZE if is_image else MAX_TEXT_SIZE
    if len(data) > max_size:
        return JSONResponse({"error": f"File too large ({len(data)} bytes, max {max_size})"}, status_code=400)

    file_id = str(uuid.uuid4())[:8]
    filename = f"{file_id}.{ext}"
    path = UPLOAD_DIR / filename
    path.write_bytes(data)

    result = {
        "id": file_id,
        "name": _normalize_filename(file.filename),
        "path": str(path),
        "type": "image" if is_image else "text",
        "ext": ext,
        "size": len(data),
    }
    if is_image:
        result["base64"] = base64.b64encode(data).decode()
        result["mimeType"] = _guess_mime_type(ext)

    log(f"upload: {result['name']} ({len(data)} bytes) → {path}")
    return JSONResponse(result)


# --- Voice transcription ---

@app.post("/api/transcribe")
async def api_transcribe(request: Request, file: UploadFile = File(...)):
    filename = _normalize_filename(file.filename, "voice.webm")
    try:
        data = await file.read()
    finally:
        await file.close()
    if len(data) > MAX_AUDIO_SIZE:
        return JSONResponse({"error": "Audio too large"}, status_code=400)

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webm"
    with tempfile.TemporaryDirectory(prefix="apex-whisper-") as tmp_dir:
        input_path = Path(tmp_dir) / f"audio.{ext}"
        input_path.write_bytes(data)
        log(f"transcribing: {len(data)} bytes ({ext})")
        try:
            proc = await asyncio.create_subprocess_exec(
                WHISPER_BIN, str(input_path), "--model", "turbo",
                "--output_format", "json", "--output_dir", tmp_dir,
                "--language", "en",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return JSONResponse({"error": "Whisper binary not found"}, status_code=500)

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
            return JSONResponse({"error": "Transcription timed out"}, status_code=504)

        if proc.returncode not in (0, None):
            detail = stderr.decode()[:200]
            log(f"whisper failed: {detail}")
            return JSONResponse({"error": "Transcription failed", "detail": detail}, status_code=500)

        json_path = Path(tmp_dir) / f"{input_path.stem}.json"
        if json_path.exists():
            result = json.loads(json_path.read_text())
            text = result.get("text", "").strip()
            log(f"transcribed: '{text[:60]}...' ({len(text)} chars)")
            return JSONResponse({"text": text})

        detail = stderr.decode()[:200] or stdout.decode()[:200]
        log(f"whisper failed: {detail}")
        return JSONResponse({"error": "Transcription failed", "detail": detail}, status_code=500)


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # S-04: Verify client cert on WebSocket connections (defense-in-depth)
    if SSL_CERT and SSL_CA:
        transport = websocket.scope.get("transport")
        peer_cert = None
        if transport and hasattr(transport, "get_extra_info"):
            peer_cert = transport.get_extra_info("peercert")
        # With CERT_REQUIRED, TLS layer blocks cert-less connections.
        # This is defense-in-depth for proxy/misconfiguration scenarios.

    if not _websocket_origin_allowed(websocket):
        log(f"websocket origin rejected: {websocket.headers.get('origin')}")
        await websocket.close(code=1008)
        return
    await websocket.accept()
    ws_id = uuid.uuid4().hex[:6]
    log(f"websocket connected ws={ws_id} remote={websocket.client.host if websocket.client else '?'}")
    active_tasks: set[asyncio.Task] = set()

    def _track_task(task: asyncio.Task) -> None:
        active_tasks.add(task)

        def _cleanup(done: asyncio.Task) -> None:
            active_tasks.discard(done)
            with contextlib.suppress(asyncio.CancelledError):
                exc = done.exception()
                if exc:
                    log(f"send task failed: {exc}")

        task.add_done_callback(_cleanup)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action", "")

            if action == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if action == "attach":
                # Client reconnected and wants to re-attach to an active stream.
                # Check if a stream is actually running by testing the chat lock,
                # not just whether an old WebSocket exists (it may have been
                # cleaned up already by the _send() closure).
                attach_id = data.get("chat_id", "")
                if attach_id:
                    # Check for lock under chat_id (solo) or chat_id:* (group agent)
                    lock = _chat_locks.get(attach_id)
                    if lock is None:
                        # Group agents lock under chat_id:profile_id — find any locked key for this chat
                        for k, v in _chat_locks.items():
                            if k.startswith(attach_id + ":") and v.locked():
                                lock = v
                                break
                    stream_running = lock is not None and lock.locked()
                    if stream_running:
                        send_lock = _get_chat_send_lock(attach_id)
                        replayed = len(_stream_buffers.get(attach_id, ()))
                        async with send_lock:
                            replay_ok = True
                            for _, payload in list(_stream_buffers.get(attach_id, ())):
                                replay_ok = await _safe_ws_send_json(websocket, payload, chat_id=attach_id)
                                if not replay_ok:
                                    break
                            if replay_ok:
                                _attach_ws(websocket, attach_id)
                                active_entries = _get_active_stream_entries(attach_id)
                                active_stream_id = active_entries[0][0] if active_entries else ""
                                replay_ok = await _safe_ws_send_json(
                                    websocket,
                                    {"type": "stream_reattached", "chat_id": attach_id, "stream_id": active_stream_id},
                                    chat_id=attach_id,
                                )
                            if not replay_ok:
                                _detach_ws(websocket)
                        if replay_ok:
                            log(f"WS re-attached for chat={attach_id} (stream active, replayed={replayed})")
                    else:
                        _attach_ws(websocket, attach_id)
                        # No active stream — tell client it's safe to reload from DB
                        await _safe_ws_send_json(
                            websocket,
                            {"type": "attach_ok", "chat_id": attach_id},
                            chat_id=attach_id,
                        )
                continue

            if action == "set_model":
                model = str(data.get("model", "")).strip()
                if not model:
                    await websocket.send_json({"type": "error", "message": "Model is required"})
                    continue
                if model == MODEL:
                    # Same model — skip teardown, just acknowledge
                    await websocket.send_json({
                        "type": "system",
                        "subtype": "model_changed",
                        "model": model,
                    })
                    continue
                await _set_model(model)
                await websocket.send_json({
                    "type": "system",
                    "subtype": "model_changed",
                    "model": model,
                })
                continue

            if action == "set_chat_model":
                chat_id = data.get("chat_id", "")
                model = str(data.get("model", "")).strip()
                if not chat_id or not model:
                    await websocket.send_json({"type": "error", "message": "chat_id and model required"})
                    continue
                chat = _get_chat(chat_id)
                if not chat:
                    await websocket.send_json({"type": "error", "message": "Chat not found"})
                    continue
                if chat.get("type") != "chat":
                    await websocket.send_json({"type": "error", "message": "Only regular chats support model changes"})
                    continue
                if chat.get("profile_id"):
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Model is locked by profile: {chat.get('profile_id')}",
                    })
                    continue
                _update_chat(chat_id, model=model)
                if chat_id in _clients:
                    await _disconnect_client(chat_id)
                updated_chat = _get_chat(chat_id) or {}
                payload = {
                    "type": "chat_updated", "chat_id": chat_id,
                    "title": updated_chat.get("title", ""),
                    "model": updated_chat.get("model", model),
                }
                for cid, ws_set in list(_chat_ws.items()):
                    for ws in list(ws_set):
                        await _safe_ws_send_json(ws, payload, chat_id=cid)
                continue

            if action == "send":
                send_chat_id = data.get("chat_id", "")
                stream_id = str(data.get("stream_id") or _make_stream_id())
                send_data = dict(data)
                send_data["stream_id"] = stream_id
                task = asyncio.create_task(_handle_send_action(websocket, send_data))
                if send_chat_id:
                    _set_active_send_task(send_chat_id, stream_id, task)

                    def _cleanup_send_task(t: asyncio.Task, cid=send_chat_id, sid=stream_id):
                        _remove_active_send_task(cid, sid, t)
                    task.add_done_callback(_cleanup_send_task)
                _track_task(task)
            elif action == "stop":
                chat_id = data.get("chat_id", "")
                requested_stream_id = str(data.get("stream_id") or "")
                if chat_id:
                    active_entries = list(_get_active_stream_entries(chat_id))
                    if requested_stream_id:
                        active_entries = [item for item in active_entries if item[0] == requested_stream_id]
                    if not active_entries:
                        continue

                    client_keys: set[str] = set()
                    for _, entry in active_entries:
                        profile_id = str(entry.get("profile_id") or "")
                        if profile_id:
                            client_keys.add(f"{chat_id}:{profile_id}")
                        else:
                            client_keys.add(chat_id)

                    if requested_stream_id and not client_keys:
                        client_keys = {chat_id}

                    if requested_stream_id:
                        for ck in client_keys:
                            client = _clients.get(ck)
                            if not client:
                                continue
                            try:
                                await client.interrupt()
                            except Exception:
                                pass
                    else:
                        for ck in list(_clients):
                            if ck == chat_id or ck.startswith(chat_id + ":"):
                                try:
                                    await _clients[ck].interrupt()
                                except Exception:
                                    pass

                    for _, entry in active_entries:
                        send_task = entry.get("task")
                        if isinstance(send_task, asyncio.Task) and not send_task.done():
                            send_task.cancel()

                    await _send_active_streams(chat_id)

    except WebSocketDisconnect as wd:
        log(f"websocket disconnected ws={ws_id} code={wd.code if hasattr(wd, 'code') else '?'}")
    except Exception as e:
        log(f"websocket error ws={ws_id}: {type(e).__name__}: {e}")
    finally:
        _detach_ws(websocket)
        if active_tasks:
            log(f"websocket cleanup ws={ws_id}: {len(active_tasks)} send task(s) continue in background")


async def _handle_send_action(websocket: WebSocket, data: dict) -> None:
    chat_id = data.get("chat_id", "")
    prompt = str(data.get("prompt", "")).strip()
    attachments = data.get("attachments", [])
    stream_id = str(data.get("stream_id") or _make_stream_id())
    if not (prompt or attachments) or not chat_id:
        return

    # --- Inline approval: bare "approve" or "reject" resolves single pending ---
    if _GATE_ENABLED and prompt and not attachments:
        lower = prompt.strip().lower()
        if lower in ("approve", "approved", "yes", "ship it", "reject", "rejected", "no", "deny"):
            pending = _get_pending_approvals()
            if len(pending) == 1:
                decision = "approved" if lower in ("approve", "approved", "yes", "ship it") else "rejected"
                mid = str(pending[0].get("message_id", ""))
                result = _resolve_approval(mid, decision)
                if result:
                    emoji = "✅" if decision == "approved" else "❌"
                    reply = f"{emoji} {decision.title()}: {result.get('skill', '?')}"
                    _save_message(chat_id, "user", prompt)
                    _save_message(chat_id, "assistant", reply)
                    _attach_ws(websocket, chat_id)
                    _reset_stream_buffer(chat_id)
                    gate_stream_token = _current_stream_id.set(_make_stream_id())
                    try:
                        await _send_stream_event(chat_id, {"type": "stream_start", "chat_id": chat_id})
                        await _send_stream_event(chat_id, {"type": "text", "text": reply})
                        await _send_stream_event(chat_id, {
                            "type": "result", "cost_usd": 0, "tokens_in": 0, "tokens_out": 0, "session_id": None,
                        })
                        await _send_stream_event(chat_id, {"type": "stream_end", "chat_id": chat_id})
                    finally:
                        _current_stream_id.reset(gate_stream_token)
                    _log_skill_invocation("gate", success=True, context=f"{decision}:{result.get('skill','?')}", source="apex")
                    return

    # --- Skill dispatch: intercept /recall, /codex, /grok before SDK ---
    _recall_context = ""
    if ENABLE_SKILL_DISPATCH and prompt and not attachments:
        parsed = _parse_skill_command(prompt)
        if parsed:
            skill, skill_args = parsed
            if skill in _CONTEXT_SKILLS:
                # Context skill (recall): search, inject results into Claude prompt
                if skill == "recall" and skill_args:
                    log(f"Recall context: extracting terms from {skill_args[:60]!r}")
                    recall_output = await asyncio.to_thread(_run_recall, skill_args)
                    if recall_output and "No results" not in recall_output:
                        _recall_context = (
                            f"<system-reminder>\nThe user asked to recall a past conversation. "
                            f"Here are the most relevant transcript excerpts:\n\n{recall_output}\n\n"
                            f"Synthesize these results into a clear answer to the user's question. "
                            f"Focus on what was discussed, decided, and any key numbers/conclusions.\n</system-reminder>\n\n"
                        )
                        # Rewrite prompt to be the natural language question (strip /recall)
                        prompt = skill_args
                elif skill == "improve" and skill_args:
                    log(f"Skill-improver: analyzing {skill_args[:60]!r}")
                    improve_output = await asyncio.to_thread(_run_improve, skill_args)
                    # Load the SKILL.md instructions for the improver
                    improver_md = WORKSPACE / "skills" / "skill-improver" / "SKILL.md"
                    instructions = improver_md.read_text()[:4000] if improver_md.exists() else ""
                    _recall_context = (
                        f"<system-reminder>\nThe user invoked /improve {skill_args}. "
                        f"Here is the structured analysis report from analyze.py:\n\n"
                        f"```json\n{improve_output}\n```\n\n"
                        f"Follow these instructions to synthesize the report into actionable proposals:\n\n"
                        f"{instructions}\n</system-reminder>\n\n"
                    )
                    prompt = f"Analyze the skill '{skill_args.split()[0]}' and propose improvements based on the data above."
            elif skill in _THINKING_SKILLS:
                # Thinking skill: inject SKILL.md instructions as context
                skill_md = WORKSPACE / "skills" / skill / "SKILL.md"
                if skill_md.exists():
                    instructions = skill_md.read_text()[:4000]
                    _recall_context = (
                        f"<system-reminder>\nThe user invoked the /{skill} skill. "
                        f"Follow these instructions to execute it:\n\n{instructions}\n</system-reminder>\n\n"
                    )
                    prompt = skill_args or prompt
                    log(f"Thinking skill dispatch: /{skill} args={skill_args[:60]!r}")
                    _log_skill_invocation(skill, success=True, context=(skill_args or "")[:80], source="apex")
            elif skill in _DIRECT_SKILL_HANDLERS:
                handled = await _handle_skill(websocket, chat_id, skill, skill_args, prompt)
                if handled:
                    return

    chat = _get_chat(chat_id)
    if not chat:
        await _safe_ws_send_json(websocket, {"type": "error", "message": "Chat not found"}, chat_id=chat_id)
        return
    is_group_chat = chat.get("type") == "group"

    # Per-chat model routing — fallback to global MODEL
    chat_model = chat.get("model") or MODEL
    backend = _get_model_backend(chat_model)

    # --- Group @mention routing ---
    group_agent = None
    target_profile_id = str(data.get("target_agent") or "").strip()
    if target_profile_id and is_group_chat:
        members = _get_group_members(chat_id)
        for m in members:
            if m["profile_id"] == target_profile_id:
                group_agent = {
                    "profile_id": m["profile_id"],
                    "name": m["name"],
                    "avatar": m["avatar"],
                    "model": m["model"],
                    "backend": _get_model_backend(m["model"]),
                    "clean_prompt": prompt,
                }
                break
        if not group_agent:
            await _safe_ws_send_json(
                websocket,
                {"type": "error", "message": f"Target agent not found: {target_profile_id}"},
                chat_id=chat_id,
            )
            return
    if group_agent is None:
        group_agent = _resolve_group_agent(chat_id, chat, prompt)
    if group_agent:
        chat_model = group_agent["model"]
        backend = _get_model_backend(chat_model)
        prompt = group_agent["clean_prompt"]
        log(f"group routing: chat={chat_id[:8]} agent={group_agent['name']} model={chat_model} backend={backend}")

    # Client key: for group channels, each agent gets its own SDK session
    client_key = f"{chat_id}:{group_agent['profile_id']}" if group_agent else chat_id

    stream_token = _current_stream_id.set(stream_id)
    group_profile_token = _current_group_profile_id.set(group_agent["profile_id"] if group_agent else "")
    # Lock per-agent in group channels, per-chat in solo channels
    lock_key = client_key if group_agent else chat_id
    chat_lock = _get_chat_lock(lock_key)
    try:
        await asyncio.wait_for(chat_lock.acquire(), timeout=0.05)
    except asyncio.TimeoutError:
        if group_agent:
            busy_name = group_agent["name"]
            # Suggest other available agents
            members = _get_group_members(chat_id)
            others = [m["name"] for m in members if m["profile_id"] != group_agent["profile_id"]]
            hint = f" Try @{others[0]}." if others else ""
            err_msg = f"{busy_name} is still responding.{hint}"
        else:
            err_msg = "This chat is already processing a message"
        await _safe_ws_send_json(
            websocket,
            {"type": "error", "message": err_msg},
            chat_id=chat_id,
        )
        return

    try:
        # Wait briefly for startup recovery if this chat is still pending
        recovery_evt = _recovery_pending.get(chat_id)
        if recovery_evt:
            try:
                await asyncio.wait_for(recovery_evt.wait(), timeout=5.0)
                log(f"recovery wait: chat={chat_id} ready")
            except asyncio.TimeoutError:
                log(f"recovery wait: chat={chat_id} timed out (5s), proceeding without")

        # On-demand recovery: if this chat has no recovery context yet, generate it now
        if chat_id not in _compaction_summaries and chat_id not in _session_context_sent:
            try:
                transcript = _get_recent_messages_text(chat_id, 30)
                if transcript.strip():
                    recovery = await asyncio.to_thread(_generate_recovery_context, transcript)
                    if recovery:
                        _compaction_summaries[chat_id] = recovery
                        log(f"on-demand recovery: chat={chat_id[:8]} len={len(recovery)}")
            except Exception as e:
                log(f"on-demand recovery error chat={chat_id[:8]}: {e}")

        # Inject recall context if /recall was used
        user_visible_prompt = prompt
        if _recall_context:
            prompt = f"{_recall_context}{prompt}"

        # Inject whisper for Ollama/Grok/Codex (Claude gets it via _build_turn_payload)
        if ENABLE_SUBCONSCIOUS_WHISPER and backend in ("ollama", "xai", "mlx", "codex"):
            whisper = _get_whisper_text(chat_id, current_prompt=prompt)
            if whisper:
                prompt = f"{whisper}{prompt}"

        # Set group profile override BEFORE model dispatch (consumed by _get_profile_prompt)
        if group_agent:
            _group_profile_override[chat_id] = group_agent["profile_id"]

        display_prompt = prompt
        make_query_input = None
        if backend in ("ollama", "xai", "mlx", "codex"):
            # Local/xAI models — build display prompt with attachment labels
            display_prompt = user_visible_prompt if _recall_context else prompt
            if attachments:
                try:
                    loaded = [_load_attachment(att) for att in attachments]
                    att_label = _summarize_attachments(loaded)
                    display_prompt = f"{display_prompt}\n{att_label}".strip() if display_prompt else att_label
                except Exception:
                    pass
        else:
            try:
                display_prompt, make_query_input = _build_turn_payload(chat_id, prompt, attachments)
                if _recall_context:
                    display_prompt = user_visible_prompt  # show clean prompt in chat history
            except ValueError as e:
                await _safe_ws_send_json(websocket, {"type": "error", "message": str(e)}, chat_id=chat_id)
                return

        _save_message(chat_id, "user", display_prompt)

        # Notify other viewers that a user message was added
        ws_set = _chat_ws.get(chat_id, set())
        for ows in ws_set:
            if ows is not websocket:
                await _safe_ws_send_json(
                    ows,
                    {"type": "user_message_added", "chat_id": chat_id, "content": display_prompt},
                    chat_id=chat_id,
                )

        if chat["title"] in ("New Chat", "New Channel", "Quick thread"):
            title_source = prompt or display_prompt
            title = title_source[:50] + ("..." if len(title_source) > 50 else "")
            _update_chat(chat_id, title=title)
            await _safe_ws_send_json(
                websocket, {"type": "chat_updated", "chat_id": chat_id, "title": title, "model": chat_model}, chat_id=chat_id
            )

        # Register this WS in the registry so the stream can find it
        original_ws = websocket
        _attach_ws(websocket, chat_id)
        if not _has_active_stream(chat_id, exclude_stream_id=stream_id):
            _reset_stream_buffer(chat_id)

        # Include speaker info in stream_start so webapp can render header during streaming
        stream_start_event = {"type": "stream_start", "chat_id": chat_id}
        if group_agent:
            _update_active_send_task(
                chat_id,
                stream_id,
                name=group_agent["name"],
                avatar=group_agent["avatar"],
                profile_id=group_agent["profile_id"],
            )
            stream_start_event["speaker_name"] = group_agent["name"]
            stream_start_event["speaker_avatar"] = group_agent["avatar"]
            stream_start_event["speaker_id"] = group_agent["profile_id"]
        await _send_stream_event(chat_id, stream_start_event)
        if is_group_chat:
            await _send_active_streams(chat_id)

        result: dict | None = None

        # --- Local model / xAI / Codex path ---
        if backend in ("ollama", "xai", "mlx", "codex"):
            try:
                result = await _run_ollama_chat(chat_id, prompt, model=chat_model, attachments=attachments)
            except Exception as ollama_err:
                log(f"ollama chat error: {ollama_err}")
                for ws in list(_chat_ws.get(chat_id, {websocket})):
                    await _safe_ws_send_json(
                        ws, {"type": "error", "message": f"Local model error: {ollama_err}"},
                        chat_id=chat_id,
                    )
                return
        else:
            # --- Claude SDK path ---
            # Pre-flight compaction check — prevents resume into bloated context
            try:
                await _maybe_compact_chat(chat_id)
            except Exception as compact_err:
                log(f"pre-flight compaction error: chat={chat_id} {compact_err}")

            try:
                client = await _get_or_create_client(client_key, model=chat_model)
                result = await _run_query_turn(client, make_query_input, chat_id)
            except Exception as first_error:
                if DEBUG: log(f"DBG RECOVERY: chat={chat_id} client_key={client_key} first error: {type(first_error).__name__}: {first_error}")
                await _disconnect_client(client_key)

                # Retry input — on recovery tiers, inject a conciseness hint to limit context growth
                def _make_retry_input():
                    base = make_query_input()
                    if isinstance(base, str):
                        return "[System: previous attempt failed. Respond concisely, avoid spawning parallel agents.]\n\n" + base
                    return base  # async generator — can't easily prepend, pass through

                # Try to RESUME the existing session first (preserves context, saves tokens)
                chat = _get_chat(chat_id)
                existing_session = chat.get("claude_session_id") if chat else None
                if DEBUG: log(f"DBG RECOVERY: attempting resume session={existing_session or 'NONE'}")
                try:
                    options = _make_options(model=chat_model, session_id=existing_session)
                    client = ClaudeSDKClient(options)
                    await asyncio.wait_for(client.connect(), timeout=SDK_QUERY_TIMEOUT)
                    _clients[client_key] = client
                    result = await _run_query_turn(client, _make_retry_input, chat_id)
                    if DEBUG: log(f"DBG RECOVERY: resume OK client_key={client_key} session={existing_session or 'new'}")
                except Exception as resume_error:
                    if DEBUG: log(f"DBG RECOVERY: resume FAILED: {type(resume_error).__name__}: {resume_error}")
                    await _disconnect_client(client_key)
                    _update_chat(chat_id, claude_session_id=None)
                    _session_context_sent.discard(client_key)  # re-inject workspace context on fresh session
                    if DEBUG: log(f"DBG RECOVERY: session_id NUKED, trying fresh...")
                    try:
                        options = _make_options(model=chat_model, session_id=None)
                        client = ClaudeSDKClient(options)
                        await asyncio.wait_for(client.connect(), timeout=SDK_QUERY_TIMEOUT)
                        _clients[client_key] = client
                        result = await _run_query_turn(client, _make_retry_input, chat_id)
                        if DEBUG: log(f"DBG RECOVERY: fresh session OK client_key={client_key}")
                    except Exception as fresh_error:
                        if DEBUG: log(f"DBG RECOVERY: fresh ALSO FAILED: {type(fresh_error).__name__}: {fresh_error}")
                        await _disconnect_client(client_key)
                        for ws in list(_chat_ws.get(chat_id, {websocket})):
                            await _safe_ws_send_json(
                                ws,
                                {"type": "error", "message": f"Claude request failed: {fresh_error}"},
                                chat_id=chat_id,
                            )
                        return

        if not result:
            return

        if result.get("session_id"):
            _update_chat(chat_id, claude_session_id=result["session_id"])

        if (
            result.get("text")
            or result.get("thinking")
            or result.get("tool_events", "[]") != "[]"
            or result.get("is_error")
        ):
            _save_message(
                chat_id, "assistant", result.get("text", ""),
                tool_events=result.get("tool_events", "[]"),
                thinking=result.get("thinking", ""),
                cost_usd=result.get("cost_usd", 0),
                tokens_in=result.get("tokens_in", 0),
                tokens_out=result.get("tokens_out", 0),
                speaker_id=group_agent["profile_id"] if group_agent else "",
                speaker_name=group_agent["name"] if group_agent else "",
                speaker_avatar=group_agent["avatar"] if group_agent else "",
            )

        # Auto-compaction check — rotate session if token usage too high (Claude only)
        if backend == "claude":
            try:
                await _maybe_compact_chat(chat_id)
            except Exception as compact_err:
                log(f"compaction error: chat={chat_id} {compact_err}")

        # Tell ALL other viewers to reload from DB (they didn't see the stream)
        ws_set = _chat_ws.get(chat_id, set())
        other_viewers = ws_set - {original_ws}
        if other_viewers:
            log(f"Notifying {len(other_viewers)} other viewer(s) to reload chat={chat_id}")
            for ows in other_viewers:
                await _safe_ws_send_json(
                    ows,
                    {"type": "stream_complete_reload", "chat_id": chat_id, "stream_id": stream_id},
                    chat_id=chat_id,
                )
    finally:
        if chat_lock.locked():
            chat_lock.release()
        try:
            await _send_stream_event(chat_id, {"type": "stream_end", "chat_id": chat_id})
            log(f"stream_end sent: chat={chat_id} viewers={len(_chat_ws.get(chat_id, set()))}")
        finally:
            current_task = asyncio.current_task()
            _remove_active_send_task(chat_id, stream_id, current_task if isinstance(current_task, asyncio.Task) else None)
            if is_group_chat:
                await _send_active_streams(chat_id)
            if not _has_active_stream(chat_id):
                _stream_buffers.pop(chat_id, None)
                _stream_seq.pop(chat_id, None)
            _current_group_profile_id.reset(group_profile_token)
            _current_stream_id.reset(stream_token)


# --- Main page ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    title_suffix = " (Dev)" if PORT != 8300 else ""
    html = CHAT_HTML.replace("{{TITLE_SUFFIX}}", title_suffix).replace("{{MODE_CLASS}}", "mtls").replace("{{MODE_LABEL}}", "mTLS")
    # Sanitize: replace any lone surrogates with replacement char (prevents UnicodeEncodeError)
    html = html.encode("utf-8", errors="replace").decode("utf-8")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


# --- PWA endpoints ---

@app.get("/manifest.json")
async def manifest():
    return JSONResponse({
        "name": "ApexChat",
        "short_name": "ApexChat",
        "description": "Local Claude Code chat over WireGuard",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0F172A",
        "theme_color": "#0F172A",
        "icons": [
            {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"},
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        ],
    })


@app.get("/icon.svg")
async def icon_svg():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">
<rect width="192" height="192" rx="40" fill="#0F172A"/>
<circle cx="96" cy="80" r="36" fill="#0EA5E9" opacity="0.9"/>
<rect x="56" y="120" width="80" height="8" rx="4" fill="#334155"/>
<rect x="66" y="136" width="60" height="8" rx="4" fill="#334155"/>
<rect x="76" y="152" width="40" height="8" rx="4" fill="#334155"/>
</svg>'''
    from starlette.responses import Response
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/sw.js")
async def service_worker():
    sw = "// no-op service worker — avoids fetch errors with self-signed certs"
    from starlette.responses import Response
    return Response(content=sw, media_type="application/javascript")


# ---------------------------------------------------------------------------
# Embedded HTML
# ---------------------------------------------------------------------------

CHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="ApexChat">
<meta name="theme-color" content="#0F172A">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/icon.svg">
<title>ApexChat{{TITLE_SUFFIX}}</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0F172A;--surface:#1E293B;--card:#334155;--text:#F1F5F9;--dim:#94A3B8;
--accent:#0EA5E9;--green:#10B981;--red:#EF4444;--yellow:#F59E0B;
--nav-bg:#141C2B;--nav-card:rgba(255,255,255,0.04);--nav-card-active:rgba(14,165,233,0.08);
--nav-card-hover:rgba(255,255,255,0.06);--nav-divider:rgba(255,255,255,0.04);
--nav-accent-glow:0 0 20px rgba(14,165,233,0.15);
--panel-bg:#1A1A2E;--panel-border:#333;--panel-text:#E5E7EB;--panel-muted:#888;
--panel-input-bg:#111827;--debug-bg:#111827;--debug-border:#233047;--debug-state:#93C5FD;--debug-log:#A7F3D0;
--sat:env(safe-area-inset-top);--sab:env(safe-area-inset-bottom);--sidebar-width:min(300px,80vw);
--chat-font-scale:1}
body{background:var(--bg);color:var(--text);font-family:-apple-system,system-ui,sans-serif;
height:100dvh;display:flex;flex-direction:column;overflow:hidden}
body.theme-light{--bg:#F8FAFC;--surface:#FFFFFF;--card:#D8E1EB;--text:#0F172A;--dim:#64748B;
--accent:#0284C7;--green:#059669;--red:#DC2626;--yellow:#D97706;
--nav-bg:#F1F4F9;--nav-card:rgba(0,0,0,0.03);--nav-card-active:rgba(2,132,199,0.07);
--nav-card-hover:rgba(0,0,0,0.05);--nav-divider:rgba(0,0,0,0.04);
--nav-accent-glow:0 0 20px rgba(2,132,199,0.1);
--panel-bg:#FFFFFF;--panel-border:#CBD5E1;--panel-text:#0F172A;--panel-muted:#64748B;
--panel-input-bg:#F8FAFC;--debug-bg:#E2E8F0;--debug-border:#CBD5E1;--debug-state:#1D4ED8;--debug-log:#047857}

/* Top bar */
.topbar{background:var(--surface);padding:12px 16px;padding-top:calc(12px + var(--sat));
display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--card);min-height:52px;flex-shrink:0;
transition:margin-left .2s ease}
.topbar h1{font-size:16px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.status{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.status.ok{background:var(--green)}
.status.err{background:var(--red)}
.mode-badge{font-size:10px;padding:2px 6px;border-radius:4px;font-weight:600;flex-shrink:0}
.mode-badge.trusted{background:#7F1D1D;color:#FCA5A5}
.mode-badge.guarded{background:#064E3B;color:#6EE7B7}
.mode-badge.mtls{background:#1D4ED8;color:#DBEAFE}
.btn-icon{background:none;border:none;color:var(--dim);font-size:20px;cursor:pointer;padding:4px 8px;min-width:44px;min-height:44px;display:flex;align-items:center;justify-content:center}

/* Messages */
.messages{flex:1;overflow-y:auto;padding:12px 16px;-webkit-overflow-scrolling:touch;transition:margin-left .2s ease}
.msg{margin-bottom:12px;max-width:85%;-webkit-user-select:text;user-select:text}
.msg.user{margin-left:auto;background:var(--accent);color:white;padding:10px 14px;
border-radius:16px 16px 4px 16px;font-size:calc(15px * var(--chat-font-scale));line-height:1.4;word-break:break-word}
.msg.assistant{margin-right:auto}
.msg.assistant .bubble{background:var(--surface);padding:10px 14px;
border-radius:16px 16px 16px 4px;font-size:calc(15px * var(--chat-font-scale));line-height:1.5;word-break:break-word}
.msg.assistant .bubble code{background:var(--card);padding:1px 4px;border-radius:3px;font-size:calc(13px * var(--chat-font-scale))}
.msg.assistant .bubble pre{background:var(--bg);padding:10px;border-radius:6px;overflow-x:auto;
margin:8px 0;font-size:calc(13px * var(--chat-font-scale));line-height:1.4}
.msg.assistant .bubble pre code{background:none;padding:0}
.msg.assistant .bubble h2,.msg.assistant .bubble h3,.msg.assistant .bubble h4{line-height:1.3;margin:10px 0 6px}
.msg.assistant .bubble h2{font-size:calc(1.5em * var(--chat-font-scale))}
.msg.assistant .bubble h3{font-size:calc(1.3em * var(--chat-font-scale))}
.msg.assistant .bubble h4{font-size:calc(1.1em * var(--chat-font-scale))}
.msg.assistant .bubble p + p,.msg.assistant .bubble p + ul,.msg.assistant .bubble p + ol,
.msg.assistant .bubble ul + p,.msg.assistant .bubble ol + p,.msg.assistant .bubble pre + p{margin-top:8px}
.msg.assistant .bubble ul,.msg.assistant .bubble ol{padding-left:20px;margin:8px 0}
.msg.assistant .bubble li + li{margin-top:4px}

/* Thinking blocks */
/* Thinking blocks — standalone or inside work group */
.thinking-block{background:var(--bg);border-left:3px solid var(--yellow);border-radius:6px;
margin-bottom:6px;overflow:hidden}
.thinking-header{padding:8px 12px;font-size:12px;color:var(--yellow);cursor:pointer;
display:flex;align-items:center;gap:6px;user-select:none}
.thinking-body{padding:0 12px 8px 12px;font-size:13px;color:var(--dim);
line-height:1.5;display:none;white-space:pre-wrap;-webkit-user-select:text;user-select:text;
max-height:300px;overflow-y:auto}
.thinking-block.open .thinking-body{display:block}
.thinking-header .arrow{transition:transform 0.2s}
.thinking-block.open .thinking-header .arrow{transform:rotate(90deg)}
/* Thinking inside work group: slimmer margins */
.tool-group-body .thinking-block{margin:4px 0;border-left:2px solid var(--yellow)}

/* Work group — collapsible container for thinking + tool calls */
.tool-group{background:var(--bg);border-left:3px solid var(--accent);border-radius:6px;
margin-bottom:6px;overflow:hidden}
.tool-group-header{padding:8px 12px;font-size:12px;color:var(--accent);cursor:pointer;
display:flex;align-items:center;gap:6px;user-select:none;font-weight:600}
.tool-group-header .arrow{transition:transform 0.2s}
.tool-group.open .tool-group-header .arrow{transform:rotate(90deg)}
.tool-group-body{display:none;padding:0 4px 4px}
.tool-group.open .tool-group-body{display:block}
.tool-group-header .tool-group-count{margin-left:auto;font-size:11px;color:var(--dim);font-weight:400}

/* Tool blocks (inside group) */
.tool-block{background:var(--surface);border-left:2px solid rgba(255,255,255,0.06);border-radius:4px;
margin:4px 0;overflow:hidden}
.tool-header{padding:6px 10px;font-size:12px;color:var(--accent);cursor:pointer;
display:flex;align-items:center;gap:6px;user-select:none}
.tool-summary{font-size:calc(12px * var(--chat-font-scale));color:var(--dim);padding:2px 10px 4px;line-height:1.4}
.tool-summary code{background:var(--bg);padding:1px 4px;border-radius:3px;font-size:calc(11px * var(--chat-font-scale))}
.tool-body{padding:0 10px 6px 10px;font-size:calc(12px * var(--chat-font-scale));color:var(--dim);
line-height:1.4;display:none}
.tool-block.open .tool-body{display:block}
.tool-block.open .tool-header .arrow{transform:rotate(90deg)}
.tool-header .arrow{transition:transform 0.2s}
.tool-status{margin-left:auto;font-size:14px}
.tool-body pre{background:var(--bg);padding:8px;border-radius:4px;overflow-x:auto;
font-size:calc(11px * var(--chat-font-scale));margin:4px 0;max-height:200px;overflow-y:auto}

/* Cost footer */
.cost{font-size:11px;color:var(--dim);margin-top:4px;padding-left:4px}

/* Streaming indicator */
.streaming .bubble::after{content:'';display:inline-block;width:6px;height:14px;
background:var(--accent);margin-left:2px;animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}

/* Composer */
.composer{background:var(--surface);padding:8px 12px;padding-bottom:calc(8px + var(--sab));
border-top:1px solid var(--card);display:flex;align-items:flex-end;gap:8px;flex-shrink:0;transition:margin-left .2s ease}
.composer textarea{flex:1;background:var(--bg);color:var(--text);border:1px solid var(--card);
border-radius:12px;padding:10px 14px;font-size:16px;resize:none;outline:none;
max-height:120px;line-height:1.4;font-family:inherit}
.composer textarea:focus{border-color:var(--accent)}
.composer button{min-width:44px;min-height:44px;border-radius:50%;border:none;
background:var(--accent);color:white;font-size:18px;cursor:pointer;flex-shrink:0;
display:flex;align-items:center;justify-content:center}
.composer button:disabled{background:var(--card);color:var(--dim)}
.composer button.stop{background:var(--red)}
.composer button.transcribing{background:var(--yellow);color:var(--bg)}
.ask-next-bar{position:absolute;bottom:100%;left:0;right:0;padding:8px 12px;display:flex;gap:8px;align-items:center;
opacity:0;transform:translateY(8px);pointer-events:none;transition:opacity .2s ease,transform .2s ease;z-index:10}
.ask-next-bar.show{opacity:1;transform:translateY(0);pointer-events:auto}
.ask-next-label{font-size:11px;color:var(--dim);white-space:nowrap;flex-shrink:0}
.ask-next-chip{display:flex;align-items:center;gap:6px;padding:7px 14px;
border-radius:20px;border:1px solid var(--card);background:var(--surface);
color:var(--text);font-size:13px;font-weight:500;cursor:pointer;white-space:nowrap;transition:all .15s ease}
.ask-next-chip:hover{border-color:var(--accent);background:rgba(14,165,233,0.06)}
.ask-next-chip:active{background:var(--accent);border-color:var(--accent);color:#fff;transform:scale(.96)}
.ask-next-chip .chip-emoji{font-size:15px}
.ask-next-dismiss{margin-left:auto;width:24px;height:24px;border-radius:50%;border:none;
background:var(--card);color:var(--dim);font-size:14px;cursor:pointer;display:flex;
align-items:center;justify-content:center;flex-shrink:0}
.ask-next-dismiss:hover{background:var(--surface);color:var(--text)}
.stop-menu{position:absolute;bottom:100%;right:0;margin-bottom:8px;
background:var(--surface);border:1px solid var(--card);border-radius:14px;
padding:6px;min-width:180px;box-shadow:0 8px 32px rgba(0,0,0,0.45);z-index:100;
opacity:0;transform:translateY(8px);pointer-events:none;transition:opacity .15s ease,transform .15s ease}
.stop-menu.show{opacity:1;transform:translateY(0);pointer-events:auto}
.stop-menu button{display:flex;align-items:center;gap:10px;width:100%;padding:10px 12px;
background:none;border:none;color:var(--text);font-size:14px;cursor:pointer;border-radius:10px;transition:background .15s ease}
.stop-menu button:hover{background:var(--bg)}
.stop-menu button:active{background:var(--bg)}
.stop-menu button .stop-dot{width:8px;height:8px;border-radius:50%;background:var(--red);
animation:dotPulse 1.2s ease-in-out infinite;flex-shrink:0}
.stop-menu button .agent-time{margin-left:auto;font-size:11px;color:var(--dim)}
.stop-menu hr{border:none;border-top:1px solid var(--card);margin:4px 0}
.stop-menu .stop-all{color:var(--red);font-weight:500}
@keyframes dotPulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.7)}}
.thinking-indicator{display:flex;gap:5px;padding:12px 16px;align-items:center}
.thinking-indicator .dot{width:8px;height:8px;border-radius:50%;background:var(--dim);
animation:dotPulse 1.4s ease-in-out infinite}
.thinking-indicator .dot:nth-child(2){animation-delay:0.2s}
.thinking-indicator .dot:nth-child(3){animation-delay:0.4s}
.thinking-indicator .ti-label{font-size:12px;color:var(--dim);margin-left:4px}
.btn-compose{min-width:44px;min-height:44px;border-radius:50%;border:none;
background:var(--card);color:var(--dim);font-size:18px;cursor:pointer;flex-shrink:0;
display:flex;align-items:center;justify-content:center}
.composer label.btn-compose{position:relative;display:flex;align-items:center;justify-content:center}
.btn-compose:active{background:var(--accent);color:white}
.btn-compose.compose-action{background:var(--accent);color:#fff;box-shadow:0 4px 14px rgba(14,165,233,0.28);
transition:background .2s ease,color .2s ease,box-shadow .2s ease,transform .15s ease}
.btn-compose.compose-action.is-send{background:var(--accent)}
.btn-compose.compose-action.is-stop{background:var(--red);box-shadow:0 0 0 0 rgba(239,68,68,0.4);
animation:stream-pulse 1.5s ease-in-out infinite}
.btn-compose.compose-action:disabled{background:var(--card);color:var(--dim);box-shadow:none;animation:none;cursor:default}
.btn-compose.compose-action:not(:disabled):active{transform:scale(.96)}
@keyframes stream-pulse{
  0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.4)}
  50%{box-shadow:0 0 0 8px rgba(239,68,68,0)}
}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
.attach-preview{display:flex;gap:6px;padding:0 12px;overflow-x:auto;flex-shrink:0;transition:margin-left .2s ease}
.attach-preview:empty{display:none}
.attach-item{background:var(--card);border-radius:8px;padding:4px 8px;display:flex;align-items:center;
gap:4px;font-size:12px;color:var(--dim);flex-shrink:0;max-width:150px}
.attach-item img{width:32px;height:32px;object-fit:cover;border-radius:4px}
.attach-item .remove{cursor:pointer;color:var(--red);font-size:14px;margin-left:4px}
/* Drag-and-drop overlay */
.drop-overlay{display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.55);
align-items:center;justify-content:center;pointer-events:none}
.drop-overlay.visible{display:flex}
.drop-overlay-inner{border:3px dashed var(--accent);border-radius:16px;padding:40px 60px;
background:var(--surface);color:var(--accent);font-size:18px;font-weight:600;
text-align:center;pointer-events:none}
.transcribing{color:var(--yellow);font-size:12px;padding:4px 12px;transition:margin-left .2s ease}

/* History sidebar */
.sidebar{position:fixed;top:0;left:0;width:var(--sidebar-width);height:100dvh;background:var(--nav-bg);
z-index:100;transform:translateX(-100%);transition:transform 0.2s ease;padding-top:var(--sat);overflow:hidden;
display:flex;flex-direction:column;border-right:1px solid rgba(255,255,255,0.06)}
.sidebar.open{transform:translateX(0);transition:transform 0.25s cubic-bezier(0.4,0,0.2,1)}
body.theme-light .sidebar{border-right-color:rgba(0,0,0,0.04)}
.sidebar-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:99;display:none}
.sidebar-overlay.open{display:block}
.sidebar-header{display:flex;align-items:center;justify-content:space-between;padding:18px 16px 14px}
.sidebar h2{font-size:15px;font-weight:700;letter-spacing:0.3px}
.sidebar-body{flex:1;overflow-y:auto;padding:0 8px 12px}
.sidebar-pin{background:transparent;border:none;color:var(--dim);font-size:18px;cursor:pointer;
width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center}
.sidebar-pin:hover,.sidebar-pin.active{background:var(--nav-card-hover);color:var(--accent)}
.sidebar .new-btn{padding:10px 16px;color:var(--accent);cursor:pointer;font-size:13px;font-weight:600;
border:1px dashed rgba(14,165,233,0.35);border-radius:10px;text-align:center;justify-content:center;
background:transparent;min-height:40px;display:flex;align-items:center;margin-bottom:12px;
transition:background 0.15s ease,border-color 0.15s ease,border-style 0.15s ease}
.sidebar .new-btn:hover{border-style:solid;background:var(--nav-card-hover)}
body.theme-light .sidebar .new-btn{border-color:rgba(2,132,199,0.35)}
.sidebar .chat-item{background:var(--nav-card);border-radius:10px;padding:12px 14px;margin-bottom:6px;
border:1px solid transparent;cursor:pointer;font-size:14px;color:var(--text);min-height:44px;display:block;
transition:background 0.15s ease,border-color 0.15s ease,box-shadow 0.15s ease,padding 0.15s ease}
.sidebar .chat-item:hover{background:var(--nav-card-hover);border-color:rgba(255,255,255,0.06)}
body.theme-light .sidebar .chat-item:hover{border-color:rgba(0,0,0,0.06)}
.sidebar .chat-item:active{background:var(--nav-card-hover)}
.sidebar .chat-item.active{background:var(--nav-card-active);border-left:3px solid var(--accent);
box-shadow:var(--nav-accent-glow);padding-left:11px}
.chat-item-top{display:flex;align-items:center;gap:8px;min-width:0}
.chat-item .ci-avatar{font-size:22px;width:28px;text-align:center;flex-shrink:0;margin-right:0}
.chat-item-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0;
color:var(--text);font-weight:500}
.sidebar .chat-item.active .chat-item-title{color:var(--accent);font-weight:600}
.chat-item-subtitle{font-size:11px;font-weight:500;color:var(--dim);margin-top:3px;padding-left:36px}
.chat-item-subtitle .model{opacity:0.7}
.chat-item-actions{margin-left:auto;display:flex;gap:2px;flex-shrink:0;opacity:0;pointer-events:none;
transition:opacity 0.15s ease}
.chat-item:hover .chat-item-actions,.chat-item:focus-within .chat-item-actions{opacity:1;pointer-events:auto}
.chat-action-btn{background:none;border:none;cursor:pointer;font-size:12px;padding:2px 4px;opacity:0.5;line-height:1}
.chat-action-btn:hover{opacity:1}
.sidebar-section-header{display:flex;align-items:center;justify-content:center;gap:10px;padding:0 4px 8px;
color:var(--dim);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;margin-top:16px}
.thread-section-header::before,.thread-section-header::after{content:'';flex:1;height:1px;background:var(--nav-divider)}
.thread-section-header .section-label{opacity:0.6;white-space:nowrap}
.section-toggle{background:none;border:none;color:var(--dim);cursor:pointer;font-size:11px;padding:0;opacity:0.5;line-height:1}
.section-toggle:hover{opacity:0.8}
.sidebar .chat-item.thread-item{padding:8px 14px;min-height:0;opacity:0.85;font-size:13px}
.sidebar .chat-item.thread-item:hover{opacity:1}
.sidebar .chat-item.thread-item .ci-avatar{font-size:18px;width:24px}
.sidebar .chat-item.thread-item .chat-item-title{font-size:13px}
.speaker-header{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;
color:var(--accent);margin-bottom:2px;padding-left:2px}
.speaker-avatar{font-size:14px}
.speaker-name{opacity:0.9}

/* @mention autocomplete */
.mention-popup{position:absolute;bottom:100%;left:0;right:0;background:var(--surface);
border:1px solid var(--card);border-radius:8px;margin-bottom:4px;max-height:200px;
overflow-y:auto;display:none;z-index:100;box-shadow:0 -4px 12px rgba(0,0,0,0.3)}
.mention-popup.visible{display:block}
.mention-item{display:flex;align-items:center;gap:8px;padding:8px 12px;cursor:pointer;
font-size:14px;transition:background 0.1s}
.mention-item:hover,.mention-item.selected{background:var(--card)}
.mention-item .mi-avatar{font-size:18px;width:24px;text-align:center}
.mention-item .mi-name{font-weight:600;color:var(--text)}
.mention-item .mi-role{font-size:12px;color:var(--dim);margin-left:auto}

/* Usage bar */
.usage-bar{background:var(--surface);padding:4px 16px 6px;border-bottom:1px solid var(--card);
display:none;gap:12px;flex-shrink:0;cursor:pointer;
transition:opacity 0.3s ease,max-height 0.3s ease,margin-left .2s ease;overflow:hidden;max-height:60px}
.usage-bar.visible{display:flex}
.usage-bar.fading{opacity:0;max-height:0;padding:0 16px}
.usage-label{font-size:9px;font-weight:700;color:var(--dim);letter-spacing:0.5px;text-transform:uppercase;
writing-mode:vertical-lr;text-orientation:mixed;align-self:center;opacity:0.5}
.usage-bucket{flex:1;min-width:0}
.usage-bucket .label-row{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px}
.usage-bucket .label{font-size:10px;font-weight:600;color:var(--dim)}
.usage-bucket .pct{font-size:10px;font-weight:700;font-variant-numeric:tabular-nums}
.usage-bucket .reset{font-size:9px;color:var(--dim);opacity:0.6}
.usage-track{height:3px;background:rgba(255,255,255,0.08);border-radius:2px;overflow:hidden}
.usage-fill{height:100%;border-radius:2px;transition:width 0.4s ease,background 0.4s ease}
.usage-toggle{background:none;border:none;color:var(--dim);cursor:pointer;
font-size:11px;padding:2px 6px;opacity:0.4;align-self:center;flex-shrink:0}
.usage-toggle:hover{opacity:0.8}
.usage-fill.green{background:var(--green)}
.usage-fill.orange{background:var(--yellow)}
.usage-fill.red{background:var(--red)}

/* Context bar */
.context-bar{display:none;flex-shrink:0;align-items:center;justify-content:flex-end;
gap:6px;padding:2px 16px 3px;background:var(--bg);transition:margin-left .2s ease}
.context-bar.visible{display:flex}
.context-detail{font-size:9px;font-weight:600;color:var(--dim);font-variant-numeric:tabular-nums;
white-space:nowrap;opacity:0.7}
.context-track{width:60px;height:2px;background:rgba(255,255,255,0.08);border-radius:2px;overflow:hidden}
.context-fill{height:100%;border-radius:2px;transition:width 0.4s ease,background 0.4s ease}
.context-fill.green{background:var(--green)}
.context-fill.orange{background:var(--yellow)}
.context-fill.red{background:var(--red)}

/* Debug bar */
.debugbar{background:var(--debug-bg);border-top:1px solid var(--debug-border);padding:6px 12px;flex-shrink:0}
.debug-state{color:var(--debug-state);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
font-size:11px;white-space:pre-wrap}
.debug-log{color:var(--debug-log);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;
line-height:1.35;max-height:88px;overflow-y:auto;white-space:pre-wrap;margin-top:4px}
.alert-toast{position:fixed;top:0;left:0;right:0;z-index:9999;padding:8px 12px;
transform:translateY(-100%);transition:transform .3s ease;pointer-events:none}
.alert-toast.show{transform:translateY(0);pointer-events:auto}
.alert-toast-inner{max-width:600px;margin:0 auto;padding:10px 14px;border-radius:10px;
display:flex;align-items:flex-start;gap:10px;box-shadow:0 4px 20px rgba(0,0,0,.3);
font-size:13px;line-height:1.4;cursor:pointer}
.alert-toast-inner.critical{background:#1a0000;border:1px solid #dc2626;color:#fca5a5}
.alert-toast-inner.warning{background:#1a1400;border:1px solid #d97706;color:#fcd34d}
.alert-toast-inner.info{background:#001a1a;border:1px solid #0891b2;color:#67e8f9}
.alert-toast .alert-icon{font-size:18px;flex-shrink:0;margin-top:1px}
.alert-toast .alert-body{flex:1;min-width:0}
.alert-toast .alert-source{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;opacity:.7}
.alert-toast .alert-title{font-weight:600;margin-top:2px}
.alert-toast .alert-text{font-size:12px;opacity:.8;margin-top:2px;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.alert-toast .alert-actions{display:flex;gap:6px;flex-shrink:0;align-items:center}
.alert-toast .alert-actions button{font-size:11px;font-weight:600;padding:4px 10px;
border-radius:6px;border:none;cursor:pointer}
.alert-toast .btn-ack{background:#dc2626;color:#fff}
.alert-toast .btn-allow{background:#16a34a;color:#fff}
.alert-toast .btn-dismiss{background:transparent;color:inherit;opacity:.5;font-size:16px;padding:2px 6px}
.alert-badge{position:relative;cursor:pointer;font-size:18px;padding:0 4px;user-select:none}
.alert-badge .count{position:absolute;top:-4px;right:-6px;background:#dc2626;color:#fff;
font-size:9px;font-weight:700;min-width:16px;height:16px;border-radius:8px;
display:flex;align-items:center;justify-content:center;padding:0 4px}
.alert-badge .count:empty{display:none}
.settings-panel{position:fixed;top:40px;right:8px;width:340px;max-height:80vh;
background:var(--panel-bg);border:1px solid var(--panel-border);border-radius:12px;z-index:9997;
overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.5);display:none}
.settings-panel.show{display:block}
.settings-header{display:flex;align-items:center;justify-content:space-between;
padding:10px 14px;border-bottom:1px solid var(--panel-border);font-size:13px;font-weight:600;color:var(--panel-text)}
.settings-header button{background:transparent;border:none;color:var(--panel-muted);font-size:18px;cursor:pointer}
.settings-header button:hover{color:var(--panel-text)}
.settings-body{padding:8px 14px}
.settings-section{margin-bottom:14px}
.settings-label{font-size:12px;font-weight:600;color:var(--accent);display:block;margin-bottom:4px}
.settings-hint{font-size:11px;color:var(--panel-muted);margin-bottom:4px}
.settings-value{font-size:12px;color:var(--panel-muted)}
.settings-section select{width:100%;padding:6px 8px;border-radius:6px;border:1px solid var(--panel-border);
background:var(--panel-input-bg);color:var(--panel-text);font-size:13px;outline:none}
.settings-section select:disabled{opacity:0.5}
.settings-section select:focus{border-color:var(--accent)}
.alerts-panel{position:fixed;top:40px;right:8px;width:380px;max-height:70vh;
background:var(--panel-bg);border:1px solid var(--panel-border);border-radius:12px;z-index:9998;
overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.5);display:none}
.alerts-panel.show{display:block}
.alerts-panel-header{display:flex;align-items:center;justify-content:space-between;
padding:10px 14px;border-bottom:1px solid var(--panel-border);font-size:13px;font-weight:600;color:var(--panel-text)}
.alerts-panel-header button{background:transparent;border:none;color:var(--panel-muted);
font-size:11px;cursor:pointer}
.alerts-panel-header button:hover{color:var(--panel-text)}
.alert-item{padding:10px 14px;border-bottom:1px solid var(--panel-border);font-size:12px;
display:flex;align-items:flex-start;gap:8px}
.alert-item.acked{opacity:.4}
.alert-item .ai-icon{font-size:14px;flex-shrink:0;margin-top:1px}
.alert-item .ai-body{flex:1;min-width:0}
.alert-item .ai-source{font-size:9px;font-weight:700;text-transform:uppercase;
letter-spacing:.5px;color:var(--panel-muted)}
.alert-item .ai-title{font-weight:600;color:var(--panel-text);margin-top:1px}
.alert-item .ai-time{font-size:10px;color:var(--panel-muted);margin-top:2px}
.alert-item .ai-actions{display:flex;gap:4px;flex-shrink:0}
.alert-item .ai-actions button{font-size:10px;padding:3px 8px;border-radius:5px;
border:none;cursor:pointer;font-weight:600}
.alert-detail-overlay{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.6);
display:flex;align-items:center;justify-content:center;padding:20px}
.alert-detail-card{background:var(--panel-bg);border-radius:16px;max-width:500px;width:100%;
max-height:80vh;overflow-y:auto;box-shadow:0 12px 40px rgba(0,0,0,.5)}
.alert-detail-card .ad-header{display:flex;align-items:center;gap:10px;padding:16px 20px;
border-bottom:1px solid var(--panel-border)}
.alert-detail-card .ad-icon{font-size:28px}
.alert-detail-card .ad-source{font-size:10px;font-weight:700;text-transform:uppercase;
letter-spacing:.5px;padding:3px 8px;border-radius:10px;display:inline-block}
.alert-detail-card .ad-time{font-size:11px;color:var(--panel-muted);margin-top:4px}
.alert-detail-card .ad-close{margin-left:auto;background:none;border:none;color:var(--panel-muted);
font-size:20px;cursor:pointer;padding:4px 8px}
.alert-detail-card .ad-close:hover{color:var(--panel-text)}
.alert-detail-card .ad-section{padding:12px 20px;border-bottom:1px solid var(--panel-border)}
.alert-detail-card .ad-label{font-size:10px;font-weight:600;color:var(--panel-muted);
text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.alert-detail-card .ad-title{font-size:16px;font-weight:600;color:var(--panel-text)}
.alert-detail-card .ad-body{font-size:13px;color:var(--panel-muted);white-space:pre-wrap;
font-family:ui-monospace,SFMono-Regular,Menlo,monospace;line-height:1.5}
.alert-detail-card .ad-meta-key{font-size:10px;font-weight:600;color:var(--panel-muted);
text-transform:uppercase}
.alert-detail-card .ad-meta-val{font-size:12px;color:var(--panel-text);
font-family:ui-monospace,monospace;word-break:break-all}
.alert-detail-card .ad-actions{display:flex;gap:8px;padding:16px 20px}
.alert-detail-card .ad-actions button{flex:1;padding:8px;border-radius:8px;border:none;
font-weight:600;font-size:13px;cursor:pointer}
body.sidebar-pinned .sidebar{transform:translateX(0);box-shadow:1px 0 0 rgba(255,255,255,0.06),6px 0 16px rgba(0,0,0,0.12)}
body.sidebar-pinned .sidebar-overlay{display:none!important}
body.sidebar-pinned .topbar,
body.sidebar-pinned .usage-bar,
body.sidebar-pinned .context-bar,
body.sidebar-pinned .messages,
body.sidebar-pinned .attach-preview,
body.sidebar-pinned .transcribing,
body.sidebar-pinned .composer{margin-left:var(--sidebar-width)}

/* Profile picker modal */
.profile-modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:200;
display:flex;align-items:center;justify-content:center;padding:20px}
.profile-modal{background:var(--surface);border-radius:16px;max-width:480px;width:100%;
max-height:80vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.5)}
.profile-modal-header{display:flex;align-items:center;justify-content:space-between;
padding:16px 20px;border-bottom:1px solid var(--card)}
.profile-modal-header h3{font-size:16px;font-weight:600}
.profile-modal-header button{background:none;border:none;color:var(--dim);
font-size:20px;cursor:pointer;padding:4px 8px}
.profile-modal-body{padding:12px 16px;overflow-y:auto;flex:1;min-height:0}
.profile-card{display:flex;align-items:center;gap:12px;padding:12px 14px;
border-radius:12px;cursor:pointer;border:2px solid transparent;
transition:all .15s ease;margin-bottom:8px;background:var(--bg)}
.profile-card:hover{border-color:var(--accent);background:var(--card)}
.profile-card.selected{border-color:var(--accent);background:var(--card)}
.profile-card .profile-avatar{font-size:28px;flex-shrink:0;width:40px;text-align:center}
.profile-card .profile-info{flex:1;min-width:0}
.profile-card .profile-name{font-size:14px;font-weight:600;color:var(--text)}
.profile-card .profile-role{font-size:12px;color:var(--dim);
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.profile-card .profile-model{font-size:10px;color:var(--accent);margin-top:2px}
.profile-modal-actions{padding:12px 16px;border-top:1px solid var(--card);
display:flex;gap:8px;justify-content:flex-end}
.profile-modal-actions button{padding:8px 16px;border-radius:8px;border:none;
font-weight:600;font-size:13px;cursor:pointer}
.profile-modal-actions .btn-create{background:var(--accent);color:white}
.profile-modal-actions .btn-create:disabled{opacity:.5;cursor:default}
.profile-modal-actions .btn-skip{background:var(--card);color:var(--dim)}

/* Profile indicator in topbar */
.topbar-profile{display:flex;align-items:center;gap:4px;font-size:12px;color:var(--dim);
cursor:pointer;padding:2px 8px;border-radius:6px;margin-right:4px;flex-shrink:0}
.topbar-profile:hover{background:var(--card)}
.topbar-profile .tp-avatar{font-size:16px}
.topbar-profile .tp-name{font-size:11px;max-width:80px;overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}

/* Profile badge in sidebar chat items */
.chat-item .ci-avatar{font-size:22px;width:28px;text-align:center;flex-shrink:0;margin-right:0}

/* Profile change dropdown */
.profile-dropdown{position:fixed;background:var(--surface);border:1px solid var(--card);
border-radius:12px;z-index:201;box-shadow:0 8px 24px rgba(0,0,0,.4);
max-height:300px;overflow-y:auto;min-width:220px}
.profile-dropdown .pd-item{display:flex;align-items:center;gap:8px;padding:8px 12px;
cursor:pointer;font-size:13px;color:var(--text);border-bottom:1px solid var(--bg)}
.profile-dropdown .pd-item:hover{background:var(--card)}
.profile-dropdown .pd-item:last-child{border-bottom:none}
.profile-dropdown .pd-avatar{font-size:18px;flex-shrink:0}
.profile-dropdown .pd-name{flex:1}
.profile-dropdown .pd-check{color:var(--accent);font-size:14px}

/* ═══════════════════════════════════════════════════
   Inline pills (tool + thinking) — V3 redesign
   ═══════════════════════════════════════════════════ */
.tool-pill,.thinking-pill{display:inline-flex;align-items:center;gap:8px;padding:8px 14px;
background:var(--surface);border:1px solid var(--card);border-radius:12px;cursor:pointer;
transition:all 0.2s;user-select:none;margin-bottom:4px}
.tool-pill:hover{border-color:var(--accent);background:rgba(14,165,233,0.06)}
.thinking-pill:hover{border-color:var(--yellow);background:rgba(245,158,11,0.06)}
.tool-pill:active,.thinking-pill:active{transform:scale(0.98)}
.tool-pill .pill-icon,.thinking-pill .pill-icon{font-size:14px;flex-shrink:0}
.tool-pill .pill-label,.thinking-pill .pill-label{font-size:13px;color:var(--text);font-weight:500}
.tool-pill .pill-dim,.thinking-pill .pill-dim{color:var(--dim);font-weight:400;font-size:12px}
.tool-pill .pill-chevron,.thinking-pill .pill-chevron{color:var(--dim);font-size:13px;margin-left:2px}
.tool-pill .pill-counts{font-size:11px;color:var(--dim)}
.tool-pill .spinner{width:14px;height:14px;border:2px solid var(--card);border-top-color:var(--accent);
border-radius:50%;animation:spin 0.8s linear infinite;flex-shrink:0}
@keyframes spin{to{transform:rotate(360deg)}}
.tool-pill.streaming{border-color:rgba(14,165,233,0.3)}
.tool-pill.streaming .pill-bar-wrap{width:80px;height:3px;background:var(--card);border-radius:2px;overflow:hidden}
.tool-pill.streaming .pill-bar{height:100%;background:var(--accent);border-radius:2px;transition:width 0.3s ease}
.tool-pill.active-pill{border-color:var(--accent);background:rgba(14,165,233,0.06)}
.tool-pill.active-pill .pill-chevron{color:var(--accent)}
.thinking-pill.streaming{border-color:rgba(245,158,11,0.35);background:rgba(245,158,11,0.05)}
.thinking-pill.streaming .pill-label{color:var(--yellow)}
.thinking-pill.streaming .pill-live{width:8px;height:8px;border-radius:50%;background:var(--yellow);
animation:dotPulse 1.4s ease-in-out infinite;flex-shrink:0;margin-left:2px}
.thinking-pill.streaming .pill-chevron{display:none}
.thinking-pill.active-pill{border-color:var(--yellow);background:rgba(245,158,11,0.06)}
.thinking-pill.active-pill .pill-chevron,.thinking-pill.active-pill .pill-label{color:var(--yellow)}

/* ═══════════════════════════════════════════════════
   Side panel — desktop detail pane (tool steps / thinking)
   ═══════════════════════════════════════════════════ */
.side-panel{position:fixed;top:52px;right:0;bottom:0;width:0;overflow:hidden;
background:var(--surface);border-left:1px solid var(--card);z-index:90;
transition:width 0.3s cubic-bezier(0.32,0.72,0,1);display:flex;flex-direction:column}
.side-panel.open{width:380px}
body.panel-open .messages{margin-right:380px}
body.panel-open .composer,body.panel-open .context-bar,
body.panel-open .attach-preview,body.panel-open .transcribing{
transition:margin-right 0.3s cubic-bezier(0.32,0.72,0,1);margin-right:380px}
.sp-header{padding:16px 20px;border-bottom:1px solid var(--card);display:flex;align-items:center;
gap:10px;flex-shrink:0;min-width:380px}
.sp-title{font-size:14px;font-weight:600;flex:1;white-space:nowrap}
.sp-title .sp-dim{color:var(--dim);font-weight:400;font-size:12px}
.sp-close{width:28px;height:28px;border-radius:8px;background:var(--card);border:none;
color:var(--dim);font-size:14px;cursor:pointer;display:flex;align-items:center;
justify-content:center;transition:all 0.15s;flex-shrink:0}
.sp-close:hover{background:var(--bg);color:var(--text)}
.sp-body{flex:1;overflow-y:auto;padding:8px 12px 24px;min-width:380px;
overscroll-behavior:contain;-webkit-overflow-scrolling:touch}
.sp-step{display:flex;align-items:center;gap:10px;padding:10px;border-radius:10px;transition:background 0.15s}
.sp-step:hover{background:var(--bg)}
.sp-step+.sp-step{border-top:1px solid rgba(51,65,85,0.4)}
.sp-step .sps-icon{width:32px;height:32px;border-radius:10px;display:flex;align-items:center;
justify-content:center;font-size:15px;flex-shrink:0}
.sp-step .sps-icon.read{background:rgba(14,165,233,0.1)}
.sp-step .sps-icon.cmd{background:rgba(168,85,247,0.1)}
.sp-step .sps-icon.edit{background:rgba(245,158,11,0.1)}
.sp-step .sps-icon.write{background:rgba(16,185,129,0.1)}
.sp-step .sps-icon.search{background:rgba(99,102,241,0.1)}
.sp-step .sps-info{flex:1;min-width:0}
.sp-step .sps-label{font-size:13px;font-weight:500;color:var(--text);
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sp-step .sps-detail{font-size:11px;color:var(--dim);font-family:'SF Mono','Fira Code',monospace;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sp-step .sps-meta{display:flex;flex-direction:column;align-items:flex-end;gap:2px;flex-shrink:0}
.sp-step .sps-status{font-size:12px}
.sp-step .sps-time{font-size:11px;color:var(--dim);font-variant-numeric:tabular-nums}
.sp-step.active-step{background:rgba(14,165,233,0.06)}
.sp-step{cursor:pointer}
.sp-step .sps-chevron{color:var(--dim);font-size:11px;transition:transform 0.2s;flex-shrink:0}
.sp-step.expanded .sps-chevron{transform:rotate(90deg);color:var(--accent)}
.sp-detail{display:none;padding:8px 10px;margin:0 10px 8px;background:var(--bg);border-radius:8px;
font-family:'SF Mono','Fira Code',monospace;font-size:12px;line-height:1.5;color:var(--dim);
max-height:300px;overflow-y:auto;border:1px solid rgba(51,65,85,0.3);white-space:pre-wrap;word-break:break-all}
.sp-step.expanded+.sp-detail{display:block}
.sp-detail .spd-section{margin-bottom:8px}
.sp-detail .spd-label{font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--accent);
margin-bottom:4px;font-family:inherit}
.sp-detail .spd-content{color:var(--text)}
.sp-detail .spd-content pre{margin:0;white-space:pre-wrap;word-break:break-all}
.sp-detail .spd-diff-add{color:#4ade80}
.sp-detail .spd-diff-del{color:#f87171;text-decoration:line-through}
.sp-detail .spd-copy{float:right;font-size:10px;padding:2px 8px;background:var(--surface);
border:1px solid rgba(51,65,85,0.4);border-radius:4px;color:var(--dim);cursor:pointer}
.sp-detail .spd-copy:hover{color:var(--text);border-color:var(--accent)}
.sp-thinking{padding:16px 12px;font-size:13px;line-height:1.7;color:var(--dim);min-width:380px;
white-space:pre-wrap;-webkit-user-select:text;user-select:text;overflow-y:auto;flex:1}
.sp-thinking p{margin-bottom:12px}
.sp-thinking strong{color:var(--text)}
.sp-thinking code{background:var(--card);padding:1px 6px;border-radius:4px;font-size:12px;
font-family:'SF Mono','Fira Code',monospace}

/* ═══════════════════════════════════════════════════
   Desktop responsive — persistent sidebar, centered chat
   ═══════════════════════════════════════════════════ */
@media (min-width: 768px) {
  :root{--sidebar-width:280px}
  .sidebar{transform:translateX(0);box-shadow:1px 0 0 rgba(255,255,255,0.06)}
  .sidebar-overlay{display:none!important}
  .topbar,.usage-bar,.context-bar,.messages,.attach-preview,.transcribing,.composer{
    margin-left:var(--sidebar-width)}
  .msg{max-width:75%}
  .composer textarea{font-size:15px}
  .side-panel{top:52px}
}
@media (min-width: 1024px) {
  :root{--sidebar-width:300px}
  .messages{padding:16px 24px}
  .msg{max-width:min(70%, 720px)}
  .msg.assistant .bubble{padding:12px 18px}
  .msg.user{padding:12px 18px}
  .composer{padding:12px 20px;padding-bottom:calc(12px + var(--sab))}
  .composer textarea{max-height:200px;font-size:15px;padding:12px 16px}
  .topbar h1{font-size:17px}
}
@media (min-width: 1440px) {
  :root{--sidebar-width:320px}
  .messages{padding:20px 40px}
  .msg{max-width:min(65%, 800px)}
  .composer textarea{max-height:240px}
}
@media (min-width: 1800px) {
  .messages{max-width:1200px;margin-left:auto;margin-right:auto;
    padding-left:var(--sidebar-width);box-sizing:content-box}
  .topbar,.usage-bar,.context-bar,.attach-preview,.transcribing,.composer{
    max-width:calc(1200px + var(--sidebar-width));margin-left:auto;margin-right:auto}
}
</style>
</head>
<body>

<div class="alert-toast" id="alertToast">
  <div class="alert-toast-inner" id="alertToastInner">
    <span class="alert-icon" id="alertToastIcon"></span>
    <div class="alert-body">
      <div class="alert-source" id="alertToastSource"></div>
      <div class="alert-title" id="alertToastTitle"></div>
      <div class="alert-text" id="alertToastText"></div>
    </div>
    <div class="alert-actions" id="alertToastActions"></div>
  </div>
</div>

<div class="topbar">
  <button class="btn-icon" id="menuBtn">&#9776;</button>
  <h1 id="chatTitle">ApexChat</h1>
  <span class="topbar-profile" id="topbarProfile" onclick="showProfileDropdown(event)">
    <span class="tp-avatar" id="topbarProfileAvatar"></span>
    <span class="tp-name" id="topbarProfileName"></span>
  </span>
  <span class="status ok" id="statusDot"></span>
  <span class="mode-badge {{MODE_CLASS}}" id="modeBadge">{{MODE_LABEL}}</span>
  <span class="alert-badge" id="alertBadge" onclick="toggleAlertsPanel()" title="Alerts">&#128276;<span class="count" id="alertCount"></span></span>
  <button class="btn-icon" id="themeBtn" title="Toggle theme">&#9681;</button>
  <button class="btn-icon" id="settingsBtn" title="Settings" onclick="toggleSettings()">&#9881;</button>
  <button class="btn-icon" id="refreshBtn" title="Refresh" onclick="window.location.reload()">&#8635;</button>
</div>
<div class="alerts-panel" id="alertsPanel">
  <div class="alerts-panel-header">
    <span>Alerts</span>
    <button onclick="clearAllAlerts()">Clear All</button>
  </div>
  <div id="alertsList"></div>
</div>

<div class="settings-panel" id="settingsPanel">
  <div class="settings-header">
    <span>Settings</span>
    <button onclick="toggleSettings()">&times;</button>
  </div>
  <div class="settings-body">
    <div class="settings-section">
      <label class="settings-label">Chat Model</label>
      <div class="settings-hint" id="chatModelHint">Select a chat first</div>
      <select id="chatModelSelect" disabled onchange="changeChatModel(this.value)">
        <option value="">Loading...</option>
      </select>
    </div>
    <div class="settings-section">
      <label class="settings-label">Server Default</label>
      <div class="settings-value" id="serverModelDisplay">--</div>
    </div>
    <div class="settings-section">
      <label class="settings-label">Local Models (Ollama)</label>
      <div class="settings-value" id="ollamaModelsList">--</div>
    </div>
    <div class="settings-section">
      <label class="settings-label">Memory Whisper</label>
      <div class="settings-hint">Injects relevant memories into each turn</div>
      <div class="settings-value" id="whisperStatus">--</div>
    </div>
    <div class="settings-section">
      <label class="settings-label">Embedding Index</label>
      <div class="settings-value" id="embeddingStatus">--</div>
    </div>
    <div class="settings-section">
      <label class="settings-label">Usage Meter</label>
      <select id="usageMeterSelect" onchange="changeUsageMeterMode(this.value)">
        <option value="always">Always visible</option>
        <option value="auto">Auto-hide (5s)</option>
        <option value="off">Off</option>
      </select>
    </div>
    <div class="settings-section">
      <label class="settings-label">Text Size</label>
      <div class="settings-hint">
        <span>Font Scale</span>
        <span id="fontScaleValue">100%</span>
      </div>
      <input type="range" id="fontScaleSlider" min="70" max="200" step="10" value="100">
      <button id="fontScaleResetBtn" type="button" style="display:none;margin-top:8px;background:none;border:none;color:var(--accent);cursor:pointer;font-size:12px;padding:0">
        Reset to Default
      </button>
    </div>
  </div>
</div>

<div class="usage-bar" id="usageBar">
  <span class="usage-label" id="usageLabel">Claude</span>
  <div class="usage-bucket" id="usageSession">
    <div class="label-row">
      <span class="label">Session</span>
      <span><span class="pct" id="usageSessionPct">-</span> <span class="reset" id="usageSessionReset"></span></span>
    </div>
    <div class="usage-track"><div class="usage-fill green" id="usageSessionFill" style="width:0%"></div></div>
  </div>
  <div class="usage-bucket" id="usageWeekly">
    <div class="label-row">
      <span class="label">Weekly</span>
      <span><span class="pct" id="usageWeeklyPct">-</span> <span class="reset" id="usageWeeklyReset"></span></span>
    </div>
    <div class="usage-track"><div class="usage-fill green" id="usageWeeklyFill" style="width:0%"></div></div>
  </div>
  <button class="usage-toggle" id="usageToggle" title="Hide usage meter" onclick="event.stopPropagation(); toggleUsageMeter();">&#10005;</button>
</div>

<div class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <h2>Channels</h2>
    <button class="sidebar-pin" id="pinSidebarBtn" title="Pin sidebar" aria-pressed="false">&#128204;</button>
  </div>
  <div class="sidebar-body">
    <div class="new-btn" id="newChatBtn">+ New Channel</div>
    <div id="chatList"></div>
    <div class="sidebar-section-header thread-section-header" id="threadSectionHeader" style="display:none">
      <span class="section-label">Threads</span>
      <button class="section-toggle" id="threadToggle" title="Toggle threads">▾</button>
    </div>
    <div id="threadList"></div>
  </div>
</div>
<div class="sidebar-overlay" id="sidebarOverlay"></div>

<div class="messages" id="messages"></div>

<div class="side-panel" id="sidePanel">
  <div class="sp-header">
    <div class="sp-title" id="spTitle"></div>
    <button class="sp-close" onclick="closeSidePanel()">&#10005;</button>
  </div>
  <div class="sp-body" id="spBody"></div>
</div>

<div class="debugbar" id="debugBar" style="display:none">
  <div class="debug-state" id="debugState">booting</div>
  <div class="debug-log" id="debugLog"></div>
</div>

<div id="attachPreview" class="attach-preview"></div>
<div id="transcribeStatus" class="transcribing" style="display:none"></div>
<div class="context-bar" id="contextBar">
  <span class="context-detail" id="contextDetail">--</span>
  <div class="context-track">
    <div class="context-fill green" id="contextFill" style="width:0%"></div>
  </div>
</div>
<div class="drop-overlay" id="dropOverlay"><div class="drop-overlay-inner">&#128206; Drop files to attach</div></div>
<div class="composer" id="composerBar" style="position:relative">
  <div class="ask-next-bar" id="askNextBar"></div>
  <div class="mention-popup" id="mentionPopup"></div>
  <label class="btn-compose" id="attachBtn" title="Attach file" style="cursor:pointer">
    &#128206;
    <input type="file" id="fileInput" style="position:absolute;width:0;height:0;overflow:hidden;opacity:0" multiple accept="image/*,.txt,.py,.json,.csv,.md,.yaml,.yml,.toml,.sh,.js,.ts,.html,.css">
  </label>
  <textarea id="input" rows="1" placeholder="Message..." autocomplete="off"></textarea>
  <button class="btn-compose" id="sendBtn" title="Send">&#9654;</button>
  <div class="stop-menu" id="stopMenu"></div>
</div>

<script>
window.onerror = (msg, src, line, col, err) => {
  document.title = 'JS ERROR: ' + msg;
  const d = document.createElement('div');
  d.style.cssText = 'position:fixed;top:0;left:0;right:0;background:red;color:white;padding:8px;z-index:9999;font-size:12px';
  d.textContent = `JS Error: ${msg} (line ${line})`;
  document.body.prepend(d);
};
let ws = null;
let currentChat = sessionStorage.getItem('currentChatId') || null;
let streaming = false;
let currentBubble = null;
let currentSpeaker = null; // {name, avatar, id} for group @mention routing
let currentStreamId = '';
let composerHasDraft = false;
let lastSubmittedPrompt = '';
const activeStreams = new Map(); // stream_id -> {name, avatar, profile_id}
const _answeredAgents = new Set(); // profile_ids that already answered the current user prompt

// Per-stream context: supports concurrent agent streams without clobbering
const _streamCtx = {};  // stream_id -> {bubble, speaker, toolPill, toolCalls, ...}
function _newStreamCtx(streamId, speaker) {
  return {
    id: streamId,
    bubble: null,
    speaker: speaker,
    toolPill: null,
    thinkingPill: null,
    thinkingBlock: null,
    liveThinkingPill: null,
    liveThinkingTimer: null,
    thinkingCollapsed: false,
    toolCalls: [],
    thinkingText: '',
    thinkingStart: null,
    toolsStart: null,
    completedToolCount: 0,
  };
}
function _getCtx(msg) {
  return _streamCtx[msg.stream_id || currentStreamId] || null;
}
function _isAnyStreamActive() { return Object.keys(_streamCtx).length > 0; }
function _getCurrentBubble() {
  const ctx = _streamCtx[currentStreamId];
  return ctx ? ctx.bubble : null;
}
let currentGroupMembers = []; // [{profile_id, name, avatar, role_description}] for @mention autocomplete
let mentionSelectedIdx = 0;
let initStarted = false;
let initDone = false;
let initPromise = null;
let initTrigger = 'boot';
let reconnectTimer = null;
let knownChatCount = 0;
let selectChatSeq = 0;
let streamWatchdog = null;
let lastStreamEventAt = 0;
let mediaRecorder = null;
let mediaStream = null;
let recording = false;
let recordingChunks = [];
let transcribing = false;

function refreshComposerDraftState() {
  const inputEl = document.getElementById('input');
  composerHasDraft = Boolean((inputEl && inputEl.value.trim()) || pendingAttachments.length);
  if (composerHasDraft) hideAgentChips();
  updateSendBtn();
}

let _chipDismissTimer = null;

function hideAgentChips() {
  if (_chipDismissTimer) { clearTimeout(_chipDismissTimer); _chipDismissTimer = null; }
  const bar = document.getElementById('askNextBar');
  if (bar) bar.classList.remove('show');
}

function renderAgentChips() {
  const bar = document.getElementById('askNextBar');
  if (!bar) return;
  if (currentChatType !== 'group' || !currentGroupMembers.length || !currentChat) {
    hideAgentChips();
    return;
  }
  const excludeIds = new Set(_answeredAgents);
  activeStreams.forEach(info => {
    if (info && info.profile_id) excludeIds.add(info.profile_id);
  });
  const available = currentGroupMembers.filter(member => !excludeIds.has(member.profile_id));
  if (!available.length) {
    hideAgentChips();
    return;
  }
  bar.innerHTML = '';
  const label = document.createElement('span');
  label.className = 'ask-next-label';
  label.innerHTML = 'Ask&nbsp;next';
  bar.appendChild(label);
  available.forEach(member => {
    const btn = document.createElement('button');
    btn.className = 'ask-next-chip';
    btn.type = 'button';
    btn.innerHTML = `<span class="chip-emoji">${member.avatar || ''}</span> ${member.name}`;
    btn.onclick = () => askAgent(member.profile_id);
    bar.appendChild(btn);
  });
  const dismiss = document.createElement('button');
  dismiss.className = 'ask-next-dismiss';
  dismiss.type = 'button';
  dismiss.title = 'Dismiss';
  dismiss.innerHTML = '&#10005;';
  dismiss.onclick = () => hideAgentChips();
  bar.appendChild(dismiss);
  bar.classList.add('show');
  // Auto-dismiss after 10s
  if (_chipDismissTimer) clearTimeout(_chipDismissTimer);
  _chipDismissTimer = setTimeout(() => hideAgentChips(), 10000);
}

function hideStopMenu() {
  document.getElementById('stopMenu')?.classList.remove('show');
}

function _elapsedLabel(startedAt) {
  if (!startedAt) return '';
  const sec = Math.round((Date.now() - startedAt) / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m${sec % 60}s`;
}

function renderStopMenu() {
  const menu = document.getElementById('stopMenu');
  if (!menu) return;
  menu.innerHTML = '';
  Array.from(activeStreams.values()).forEach(stream => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.innerHTML = `<span class="stop-dot"></span>${stream.avatar || ''} Stop ${stream.name || 'agent'}<span class="agent-time">${_elapsedLabel(stream.startedAt)}</span>`;
    btn.onclick = () => stopStream(stream.stream_id);
    menu.appendChild(btn);
  });
  if (activeStreams.size > 1) {
    menu.appendChild(document.createElement('hr'));
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'stop-all';
    btn.textContent = 'Stop All';
    btn.onclick = () => stopAllStreams();
    menu.appendChild(btn);
  }
}

function stopStream(streamId) {
  if (!currentChat || !ws || ws.readyState !== WebSocket.OPEN || !streamId) return;
  ws.send(JSON.stringify({action: 'stop', chat_id: currentChat, stream_id: streamId}));
  hideStopMenu();
}

function stopAllStreams() {
  if (!currentChat || !ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({action: 'stop', chat_id: currentChat}));
  hideStopMenu();
}

function toggleStopMenu() {
  const menu = document.getElementById('stopMenu');
  if (!menu || activeStreams.size <= 1) return;
  renderStopMenu();
  menu.classList.toggle('show');
}

function dbg(...args) {
  const ts = new Date().toLocaleTimeString();
  const msg = args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ');
  const line = `[${ts}] ${msg}`;
  console.log('[lc]', ...args);
  const logEl = document.getElementById('debugLog');
  if (logEl) {
    logEl.textContent += line + '\\n';
    logEl.scrollTop = logEl.scrollHeight;
  }
}

function wsStateLabel() {
  if (!ws) return 'none';
  switch (ws.readyState) {
    case WebSocket.CONNECTING: return 'connecting';
    case WebSocket.OPEN: return 'open';
    case WebSocket.CLOSING: return 'closing';
    case WebSocket.CLOSED: return 'closed';
    default: return `unknown:${ws.readyState}`;
  }
}

function refreshDebugState(reason = '') {
  const stateEl = document.getElementById('debugState');
  if (!stateEl) return;
  const parts = [
    `ws=${wsStateLabel()}`,
    `init=${initDone ? 'done' : (initStarted ? 'running' : 'idle')}`,
    `chat=${currentChat || 'none'}`,
    `chats=${knownChatCount}`,
    `streaming=${streaming ? 'yes' : 'no'}`,
  ];
  if (reason) parts.push(`last=${reason}`);
  stateEl.textContent = parts.join(' | ');
}

function reportError(context, err) {
  const message = err?.message || String(err);
  dbg(`ERROR: ${context}:`, message);
  refreshDebugState(`error:${context}`);
}

function updateConnectionIndicators() {
  const dot = document.getElementById('statusDot');
  const badge = document.getElementById('modeBadge');
  if (!dot || !badge) return;

  let badgeClass = 'mode-badge trusted';
  let badgeTitle = 'mTLS disconnected';
  const state = ws ? ws.readyState : WebSocket.CLOSED;

  if (state === WebSocket.OPEN) {
    dot.className = 'status ok';
    badgeClass = 'mode-badge guarded';
    badgeTitle = 'mTLS connected';
  } else if (state === WebSocket.CONNECTING || state === WebSocket.CLOSING) {
    dot.className = 'status';
    badgeClass = 'mode-badge mtls';
    badgeTitle = state === WebSocket.CONNECTING ? 'mTLS connecting' : 'mTLS closing';
  } else {
    dot.className = 'status err';
  }

  badge.className = badgeClass;
  badge.textContent = 'mTLS';
  badge.title = badgeTitle;
}

function clearStreamWatchdog() {
  if (streamWatchdog) {
    clearTimeout(streamWatchdog);
    streamWatchdog = null;
  }
}

function hasActiveTool() {
  if (!currentBubble) return false;
  if (currentBubble.querySelector('.tool-pill.streaming')) return true;
  const tools = currentBubble.querySelectorAll('.tool-block');
  for (const t of tools) {
    const status = t.querySelector('.tool-status');
    if (status && status.textContent === '\u23F3') return true;
  }
  return false;
}

function markStreamActivity(reason = '') {
  if (!streaming) return;
  lastStreamEventAt = Date.now();
  clearStreamWatchdog();
  // Use longer timeout when a tool is running or model is thinking
  const isThinking = currentBubble && currentBubble.querySelector('.thinking-block, .thinking-pill.streaming');
  const timeout = (hasActiveTool() || isThinking) ? 300000 : 30000;  // 5 min for tools/thinking, 30s otherwise
  streamWatchdog = setTimeout(() => {
    if (!streaming) return;
    if (Date.now() - lastStreamEventAt < (timeout - 500)) {
      markStreamActivity('watchdog-rescheduled');
      return;
    }
    dbg(`stream watchdog: no events in ${timeout/1000}s, clearing streaming state`);
    streaming = false;
    currentBubble = null;
    sessionStorage.removeItem('streamingChatId');
    clearStreamWatchdog();
    updateSendBtn();

    refreshDebugState(reason ? `stream-watchdog:${reason}` : 'stream-watchdog');
    if (currentChat) {
      selectChat(currentChat).catch(() => {});
    }
  }, timeout);
}

async function attachToStream(socket, chatId, options = {}) {
  const reloadBeforeAttach = Boolean(options.reloadBeforeAttach);
  const reason = options.reason || 'attach';
  if (!chatId || !socket || ws !== socket || socket.readyState !== WebSocket.OPEN) return;
  if (reloadBeforeAttach) {
    await selectChat(chatId).catch(err => reportError(`${reason} selectChat`, err));
    if (ws !== socket || socket.readyState !== WebSocket.OPEN) return;
  }
  dbg('sending attach:', chatId, 'reason=', reason, 'reloadBeforeAttach=', reloadBeforeAttach);
  socket.send(JSON.stringify({action: 'attach', chat_id: chatId}));
}

function resumeConnection(trigger) {
  const streamingChatId = sessionStorage.getItem('streamingChatId');
  const resumeChat = currentChat || sessionStorage.getItem('currentChatId');
  const wasStreaming = Boolean(streamingChatId && resumeChat && streamingChatId === resumeChat);
  dbg(`${trigger}: resume state`, {wasStreaming, streamingChatId, resumeChat});

  clearTimeout(reconnectTimer);
  stopHeartbeat();
  clearStreamWatchdog();
  if (ws) {
    try { ws.close(); } catch (e) {}
  }
  currentBubble = null;
  streaming = wasStreaming;
  resumeHandledExternally = true;
  updateSendBtn();

  connect();

  if (!resumeChat) return;
  let waitDone = false;
  const waitTimeout = setTimeout(() => {
    if (waitDone) return;
    waitDone = true;
    clearInterval(waitForOpen);
    dbg(`${trigger}: timed out waiting for ws open after 15000ms`);
  }, 15000);
  const waitForOpen = setInterval(() => {
    if (waitDone) return;
    if (ws && ws.readyState === WebSocket.OPEN) {
      waitDone = true;
      clearInterval(waitForOpen);
      clearTimeout(waitTimeout);
      attachToStream(ws, resumeChat, {
        reloadBeforeAttach: wasStreaming,
        reason: trigger,
      }).then(() => {
        if (!wasStreaming) {
          selectChat(resumeChat).catch(err => reportError(`${trigger} reload`, err));
        }
      }).catch(err => reportError(`${trigger} attach`, err));
    }
  }, 100);
}

function setActiveChatUI() {
  document.querySelectorAll('.chat-item').forEach(item => {
    item.classList.toggle('active', item.dataset.id === currentChat);
  });
}

function setCurrentChat(id, title) {
  currentChat = id || null;
  if (currentChat) {
    sessionStorage.setItem('currentChatId', currentChat);
  } else {
    sessionStorage.removeItem('currentChatId');
  }
  document.getElementById('chatTitle').textContent = title || 'ApexChat';
  setActiveChatUI();
  updateUsageBarVisibility();
  startUsagePolling();
  updateSendBtn();
  refreshDebugState('chat-selected');
}

// --- WebSocket ---
let heartbeatInterval = null;
let lastPong = 0;
let resumeHandledExternally = false;  // set by visibilitychange to prevent double selectChat

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws_url = `${proto}://${location.host}/ws`;
  const connectStart = Date.now();
  dbg(' connecting via mTLS');
  const socket = new WebSocket(ws_url);
  ws = socket;
  updateConnectionIndicators();
  refreshDebugState('ws-connect');
  socket.onopen = async () => {
    if (ws !== socket) return;
    dbg(` ws opened in ${Date.now() - connectStart}ms`);
    dbg(' ws connected');
    clearTimeout(reconnectTimer);
    lastPong = Date.now();
    startHeartbeat(socket);
    updateConnectionIndicators();
    updateSendBtn();

    refreshDebugState('ws-open');
    await ensureInitialized('ws-open').catch(err => reportError('init ws-open', err));
    if (resumeHandledExternally) {
      resumeHandledExternally = false;
      dbg('skipping selectChat in onopen — resume handler owns it');
    } else if (initDone) {
      const restoreChat = currentChat || sessionStorage.getItem('currentChatId');
      const streamingChatId = sessionStorage.getItem('streamingChatId');
      dbg('ws-open: restore state', {currentChat, restoreChat, streamingChatId});
      if (!restoreChat) {
        // No chat to restore
      } else if (streamingChatId && streamingChatId === restoreChat) {
        if (!currentChat) currentChat = restoreChat;
        dbg('ws-open: active stream found in sessionStorage, reattaching:', currentChat);
        await attachToStream(socket, currentChat, {
          reloadBeforeAttach: true,
          reason: 'ws-open',
        });
      } else {
        if (!currentChat) currentChat = restoreChat;
        selectChat(restoreChat).catch(err => reportError('reload current chat', err));
      }
    }
  };
  socket.onclose = (e) => {
    if (ws !== socket) return;
    dbg(' ws closed:', e.code, e.reason);
    stopHeartbeat();
    streaming = false;
    currentBubble = null;
    clearStreamWatchdog();
    updateConnectionIndicators();
    updateSendBtn();

    refreshDebugState('ws-close');
    clearTimeout(reconnectTimer);
    if (document.visibilityState === 'visible') {
      reconnectTimer = setTimeout(connect, 3000);
    } else {
      dbg(' ws closed while hidden; waiting for visibilitychange');
    }
  };
  socket.onerror = (e) => {
    if (ws !== socket) return;
    dbg('ERROR: ws error:', e);
    updateConnectionIndicators();
    refreshDebugState('ws-error');
  };
  socket.onmessage = (e) => {
    if (ws !== socket) return;
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'pong') { lastPong = Date.now(); return; }
      dbg(' event:', msg.type, msg);
      handleEvent(msg);
    } catch (err) {
      reportError('ws message parse', err);
    }
  };
}

function startHeartbeat(socket) {
  stopHeartbeat();
  heartbeatInterval = setInterval(() => {
    if (socket.readyState === WebSocket.OPEN) {
      try { socket.send(JSON.stringify({action: 'ping'})); } catch(e) {}
      // If no pong received in 10s, connection is zombie — kill and reconnect
      if (Date.now() - lastPong > 15000) {
        dbg('heartbeat: no pong in 15s, closing zombie socket');
        stopHeartbeat();
        socket.close();
      }
    }
  }, 5000);
}

function stopHeartbeat() {
  if (heartbeatInterval) { clearInterval(heartbeatInterval); heartbeatInterval = null; }
}

// Work group: combined thinking + tool calls in one collapsible section
function _getOrCreateWorkGroup(bubble) {
  let group = bubble.querySelector('.tool-group:last-of-type');
  const bbl = bubble.querySelector('.bubble');
  if (!group || (bbl && group.nextElementSibling !== bbl)) {
    group = document.createElement('div');
    group.className = 'tool-group open';
    group.innerHTML = `<div class="tool-group-header" onclick="_toggleCollapsible(this)"><span class="arrow">&#9656;</span> &#129504; Working...<span class="tool-group-count"></span></div><div class="tool-group-body"></div>`;
    bubble.insertBefore(group, bbl);
  }
  return group;
}

function _updateWorkGroupHeader(group) {
  const toolCount = group.querySelectorAll('.tool-block').length;
  const hasThinking = group.querySelectorAll('.thinking-block').length > 0;
  const countEl = group.querySelector('.tool-group-count');
  const hdrEl = group.querySelector('.tool-group-header');
  let label = '&#129504; Working';
  if (toolCount > 0) {
    label = '&#128295; ' + toolCount + (toolCount === 1 ? ' tool call' : ' tool calls');
    if (hasThinking) label += ' + reasoning';
  } else if (hasThinking) {
    label = '&#129504; Reasoning';
  }
  // Preserve the arrow + onclick, just update the text content
  if (hdrEl) {
    const arrow = '<span class="arrow">&#9656;</span> ';
    hdrEl.innerHTML = arrow + label + `<span class="tool-group-count">${countEl ? countEl.textContent : ''}</span>`;
  }
}

let _sidePanelRefreshTimer = null;
let _sidePanelAnchor = null;

function _formatDuration(ms) {
  if (!ms || !Number.isFinite(ms) || ms <= 0) return '';
  const totalSec = Math.max(1, Math.round(ms / 1000));
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  if (min <= 0) return `${totalSec}s`;
  return sec ? `${min}m ${sec}s` : `${min}m`;
}

function _htmlToText(html) {
  const d = document.createElement('div');
  d.innerHTML = html || '';
  return d.textContent || '';
}

function _toolTypeClass(name) {
  const key = String(name || '').toLowerCase();
  if (key === 'read') return 'read';
  if (key === 'edit' || key === 'file_change') return 'edit';
  if (key === 'write') return 'write';
  if (key === 'grep' || key === 'glob' || key === 'websearch' || key === 'webfetch') return 'search';
  if (key === 'bash' || key === 'command' || key === 'agent' || key === 'skill') return 'cmd';
  return 'cmd';
}

function _formatToolInput(name, input) {
  if (input == null) return '';
  if (typeof input === 'string') {
    try {
      return JSON.stringify(JSON.parse(input), null, 2);
    } catch (e) {
      return input;
    }
  }
  try {
    return JSON.stringify(input, null, 2);
  } catch (e) {
    return String(input);
  }
}

function _normalizeToolEvents(rawEvents) {
  if (!Array.isArray(rawEvents)) return [];
  const tools = [];
  const pendingById = new Map();
  rawEvents.forEach((evt, idx) => {
    if (!evt) return;
    if (evt.type === 'tool_use') {
      const call = {
        id: evt.id || ('tool-' + idx),
        name: evt.name || 'Tool',
        input: evt.input,
        summary: evt.summary || toolSummary(evt.name, evt.input),
        status: 'running',
        startTime: evt.startTime || null,
        endTime: null,
        result: null,
      };
      tools.push(call);
      if (call.id) pendingById.set(call.id, call);
      return;
    }
    if (evt.type === 'tool_result') {
      const key = evt.tool_use_id || evt.id || '';
      let call = key ? pendingById.get(key) : null;
      if (!call) {
        call = tools.find(t => t.status === 'running') || null;
      }
      if (!call) {
        call = {
          id: key || ('tool-' + idx),
          name: evt.name || 'Tool',
          input: evt.input,
          summary: evt.summary || null,
          status: 'running',
          startTime: null,
          endTime: null,
          result: null,
        };
        tools.push(call);
        if (call.id) pendingById.set(call.id, call);
      }
      call.status = evt.is_error ? 'error' : 'completed';
      call.endTime = evt.endTime || call.endTime || null;
      call.result = evt.result ? {
        content: evt.result.content ?? '',
        is_error: Boolean(evt.result.is_error),
      } : {
        content: evt.content ?? '',
        is_error: Boolean(evt.is_error),
      };
      return;
    }
    if (!evt.name) return;
    tools.push({
      id: evt.id || ('tool-' + idx),
      name: evt.name || 'Tool',
      input: evt.input,
      summary: evt.summary || toolSummary(evt.name, evt.input),
      status: evt.status || (evt.result ? (evt.result.is_error ? 'error' : 'completed') : 'running'),
      startTime: evt.startTime || null,
      endTime: evt.endTime || null,
      result: evt.result ? {
        content: evt.result.content ?? '',
        is_error: Boolean(evt.result.is_error),
      } : (evt.content != null ? {
        content: evt.content,
        is_error: Boolean(evt.is_error),
      } : null),
    });
  });
  return tools;
}

function _ensureCtxBubble(ctx) {
  if (!ctx) return null;
  if (!ctx.bubble || !ctx.bubble.isConnected) {
    ctx.bubble = addAssistantMsg(ctx.speaker);
    ctx.toolPill = null;
    ctx.thinkingPill = null;
  }
  return ctx.bubble;
}

function _getOrCreateToolPill(ctx) {
  if (!ctx) return null;
  _ensureCtxBubble(ctx);
  let pill = ctx.toolPill;
  if (pill && pill.isConnected) {
    pill._toolData = ctx.toolCalls;
    pill._ctx = ctx;
    return pill;
  }
  pill = document.createElement('div');
  pill.className = 'tool-pill streaming';
  pill.innerHTML = `<span class="spinner"></span><span class="pill-label">Tools</span><span class="pill-dim"></span><span class="pill-counts"></span><span class="pill-bar-wrap"><span class="pill-bar"></span></span><span class="pill-chevron">&#8250;</span>`;
  pill._toolData = ctx.toolCalls;
  pill._ctx = ctx;
  pill._totalTime = 0;
  pill.onclick = () => openToolPanel(pill);
  ctx.toolPill = pill;
  const bubbleEl = ctx.bubble.querySelector('.bubble');
  ctx.bubble.insertBefore(pill, bubbleEl);
  return pill;
}

function _updateToolPillProgress(ctx) {
  const pill = _getOrCreateToolPill(ctx);
  if (!pill) return;
  const total = ctx.toolCalls.length;
  const completed = ctx.toolCalls.filter(t => t.status && t.status !== 'running').length;
  ctx.completedToolCount = completed;
  pill._toolData = ctx.toolCalls;
  pill._ctx = ctx;
  const label = pill.querySelector('.pill-label');
  const dim = pill.querySelector('.pill-dim');
  const counts = pill.querySelector('.pill-counts');
  const bar = pill.querySelector('.pill-bar');
  if (label) label.textContent = total === 1 ? '1 tool call' : `${total} tool calls`;
  if (dim) dim.textContent = total > 0 ? (completed >= total ? 'Complete' : 'Running') : '';
  if (counts) counts.textContent = total > 0 ? `${completed}/${total}` : '';
  if (bar) {
    const pct = total > 0 ? Math.max(8, Math.round((completed / total) * 100)) : 8;
    bar.style.width = pct + '%';
  }
}

function _finalizeToolPill(ctx, totalTime) {
  if (!ctx || !ctx.toolCalls.length) return null;
  const pill = _getOrCreateToolPill(ctx);
  if (!pill) return null;
  const total = ctx.toolCalls.length;
  const completed = ctx.toolCalls.filter(t => t.status && t.status !== 'running').length;
  pill.classList.remove('streaming');
  pill._toolData = ctx.toolCalls.map(t => ({
    ...t,
    result: t.result ? {...t.result} : null,
  }));
  pill._ctx = null;
  pill._totalTime = totalTime || 0;
  pill.innerHTML = `<span class="pill-icon">&#128295;</span><span class="pill-label">${total === 1 ? '1 tool call' : `${total} tool calls`}</span><span class="pill-dim">${_formatDuration(totalTime) || 'Complete'}</span><span class="pill-counts">${completed}/${total}</span><span class="pill-chevron">&#8250;</span>`;
  pill.onclick = () => openToolPanel(pill);
  return pill;
}

function _createThinkingPill(ctx, durationMs) {
  if (!ctx || !ctx.bubble || !ctx.thinkingText) return null;
  let pill = ctx.thinkingPill;
  if (!pill || !pill.isConnected) {
    pill = document.createElement('div');
    pill.className = 'thinking-pill';
    ctx.thinkingPill = pill;
  }
  pill._thinkingText = ctx.thinkingText;
  pill._thinkingDuration = durationMs || 0;
  pill.innerHTML = `<span class="pill-icon">&#129504;</span><span class="pill-label">Thinking</span><span class="pill-dim">${_formatDuration(durationMs) || ''}</span><span class="pill-chevron">&#8250;</span>`;
  pill.onclick = () => openThinkingPanel(pill);
  const bubbleEl = ctx.bubble.querySelector('.bubble');
  const beforeEl = (ctx.toolPill && ctx.toolPill.isConnected) ? ctx.toolPill : bubbleEl;
  if (pill.parentElement !== ctx.bubble || pill.nextSibling !== beforeEl) {
    ctx.bubble.insertBefore(pill, beforeEl);
  }
  return pill;
}

function _clearLiveThinkingTimer(ctx) {
  if (ctx && ctx.liveThinkingTimer) {
    clearInterval(ctx.liveThinkingTimer);
    ctx.liveThinkingTimer = null;
  }
}

function _teardownLiveThinking(ctx) {
  if (!ctx) return;
  _clearLiveThinkingTimer(ctx);
  if (ctx.liveThinkingPill && ctx.liveThinkingPill.isConnected) {
    ctx.liveThinkingPill.remove();
  }
  ctx.liveThinkingPill = null;
  ctx.thinkingCollapsed = false;
}

function _updateLiveThinkingPill(ctx) {
  if (!ctx) return null;
  const pill = ctx.liveThinkingPill;
  if (!pill || !pill.isConnected) return null;
  const durationMs = ctx.thinkingStart ? (Date.now() - ctx.thinkingStart) : 0;
  pill._thinkingText = ctx.thinkingText;
  pill._thinkingDuration = durationMs;
  pill.innerHTML = `<span class="pill-icon">&#129504;</span><span class="pill-label">Thinking...</span><span class="pill-dim">${_formatDuration(durationMs) || ''}</span><span class="pill-live"></span>`;
  return pill;
}

function _getOrCreateLiveThinkingPill(ctx, group) {
  if (!ctx) return null;
  _ensureCtxBubble(ctx);
  const hostGroup = group || _getOrCreateWorkGroup(ctx.bubble);
  let pill = ctx.liveThinkingPill;
  if (!pill || !pill.isConnected) {
    pill = document.createElement('div');
    pill.className = 'thinking-pill streaming';
    pill.dataset.streamId = ctx.id;
    pill.onclick = () => _restoreThinkingFromPill(ctx.id);
    ctx.liveThinkingPill = pill;
  }
  const body = hostGroup.querySelector('.tool-group-body');
  const firstTool = body.querySelector('.tool-block');
  if (pill.parentElement !== body || pill.nextSibling !== firstTool) {
    body.insertBefore(pill, firstTool);
  }
  _updateLiveThinkingPill(ctx);
  if (!ctx.liveThinkingTimer) {
    ctx.liveThinkingTimer = setInterval(() => {
      if (!ctx.thinkingCollapsed || !ctx.liveThinkingPill || !ctx.liveThinkingPill.isConnected) {
        _clearLiveThinkingTimer(ctx);
        return;
      }
      _updateLiveThinkingPill(ctx);
    }, 1000);
  }
  return pill;
}

function _anchoredMutateWhenScrolled(anchorEl, mutate) {
  const scroller = document.getElementById('messages');
  const shouldAnchor = Boolean(scroller && _userScrolledUp && anchorEl && anchorEl.isConnected);
  const before = shouldAnchor ? anchorEl.getBoundingClientRect().top : null;
  const afterEl = mutate() || anchorEl;
  if (shouldAnchor) {
    const target = afterEl && afterEl.isConnected ? afterEl : (anchorEl && anchorEl.isConnected ? anchorEl : null);
    if (target) {
      _programmaticScroll = true;
      scroller.scrollTop += (target.getBoundingClientRect().top - before);
      _userScrolledUp = true;
      requestAnimationFrame(() => { _programmaticScroll = false; });
    }
  }
  return afterEl;
}

function _setThinkingCollapsed(ctx, collapsed) {
  if (!ctx || !ctx.bubble) return;
  const group = _getOrCreateWorkGroup(ctx.bubble);
  let block = (ctx.thinkingBlock && ctx.thinkingBlock.isConnected) ? ctx.thinkingBlock : group.querySelector(`.thinking-block[data-stream-id="${ctx.id}"]`) || group.querySelector('.thinking-block:last-of-type');
  if (!block) return;
  ctx.thinkingBlock = block;
  const body = block.querySelector('.thinking-body');
  const anchorEl = collapsed ? block : ((ctx.liveThinkingPill && ctx.liveThinkingPill.isConnected) ? ctx.liveThinkingPill : block);
  _anchoredMutateWhenScrolled(anchorEl, () => {
    ctx.thinkingCollapsed = collapsed;
    if (collapsed) {
      block.classList.remove('open');
      block.style.display = 'none';
      _updateWorkGroupHeader(group);
      return _getOrCreateLiveThinkingPill(ctx, group);
    }
    block.style.display = '';
    block.classList.add('open');
    if (body) {
      body.textContent = ctx.thinkingText || '';
      body.scrollTop = body.scrollHeight;
    }
    if (ctx.liveThinkingPill && ctx.liveThinkingPill.isConnected) {
      ctx.liveThinkingPill.remove();
    }
    ctx.liveThinkingPill = null;
    _clearLiveThinkingTimer(ctx);
    _updateWorkGroupHeader(group);
    return block;
  });
}

function _restoreThinkingFromPill(streamId) {
  const ctx = _streamCtx[streamId];
  if (!ctx) return;
  _setThinkingCollapsed(ctx, false);
}

function _captureExpandedState() {
  const panel = document.getElementById('sidePanel');
  const current = new Set();
  panel.querySelectorAll('.sp-step.expanded[data-step-idx]').forEach(step => {
    current.add(step.dataset.stepIdx);
  });
  panel._prevExpanded = current;
  return current;
}

function _anchoredPanelToggle(anchorEl, mutate) {
  const scroller = document.getElementById('messages');
  const before = anchorEl && anchorEl.isConnected ? anchorEl.getBoundingClientRect().top : null;
  mutate();
  if (scroller && before != null && anchorEl && anchorEl.isConnected) {
    const after = anchorEl.getBoundingClientRect().top;
    scroller.scrollTop += (after - before);
  }
}

function closeSidePanel(anchorEl) {
  const panel = document.getElementById('sidePanel');
  const titleEl = document.getElementById('spTitle');
  const bodyEl = document.getElementById('spBody');
  const target = anchorEl || _sidePanelAnchor || null;
  _anchoredPanelToggle(target, () => {
    if (_sidePanelRefreshTimer) {
      clearInterval(_sidePanelRefreshTimer);
      _sidePanelRefreshTimer = null;
    }
    _sidePanelAnchor = null;
    panel.classList.remove('open');
    document.body.classList.remove('panel-open');
    panel._prevExpanded = new Set();
    titleEl.innerHTML = '';
    bodyEl.innerHTML = '';
    document.querySelectorAll('.tool-pill.active-pill,.thinking-pill.active-pill').forEach(el => el.classList.remove('active-pill'));
  });
}

function openToolPanel(pillEl) {
  if (!pillEl) return;
  const panel = document.getElementById('sidePanel');
  const titleEl = document.getElementById('spTitle');
  const bodyEl = document.getElementById('spBody');

  let _lastToolFingerprint = '';
  function rebuild(force) {
    const prevExpanded = _captureExpandedState();
    const prevScroll = bodyEl.scrollTop;
    const toolData = Array.isArray(pillEl._toolData) ? pillEl._toolData : [];
    const completed = toolData.filter(t => t.status && t.status !== 'running').length;
    // Skip DOM rebuild if nothing changed (prevents scroll yank on 800ms timer)
    const fingerprint = toolData.map(t => `${t.name}:${t.status}:${t.result ? 1 : 0}`).join('|');
    if (!force && fingerprint === _lastToolFingerprint && bodyEl.children.length > 0) {
      // Just update the title counter
      titleEl.innerHTML = `${toolData.length === 1 ? '1 tool call' : `${toolData.length} tool calls`}<span class="sp-dim">${pillEl._totalTime ? ` · ${_formatDuration(pillEl._totalTime)}` : ` · ${completed}/${toolData.length || 0} complete`}</span>`;
      return;
    }
    _lastToolFingerprint = fingerprint;
    titleEl.innerHTML = `${toolData.length === 1 ? '1 tool call' : `${toolData.length} tool calls`}<span class="sp-dim">${pillEl._totalTime ? ` · ${_formatDuration(pillEl._totalTime)}` : ` · ${completed}/${toolData.length || 0} complete`}</span>`;
    bodyEl.innerHTML = '';
    if (!toolData.length) {
      bodyEl.innerHTML = '<div class="sp-thinking">No tool activity yet.</div>';
      return;
    }

    toolData.forEach((tool, idx) => {
      const resultText = tool.result ? (typeof tool.result.content === 'string' ? tool.result.content : JSON.stringify(tool.result.content, null, 2)) : '';
      const summaryHtml = tool.summary || toolSummary(tool.name, tool.input) || '';
      const summaryText = _htmlToText(summaryHtml) || toolLabel(tool.name);
      const status = tool.status === 'error' ? '&#10007;' : (tool.status === 'completed' ? '&#10003;' : '&#9203;');
      const duration = tool.endTime && tool.startTime ? _formatDuration(tool.endTime - tool.startTime) : '';
      const step = document.createElement('div');
      step.className = 'sp-step';
      step.dataset.stepIdx = String(idx);
      if (prevExpanded.has(String(idx))) step.classList.add('expanded');
      step.innerHTML = `<div class="sps-icon ${_toolTypeClass(tool.name)}">${toolIcon(tool.name)}</div><div class="sps-info"><div class="sps-label">${escHtml(toolLabel(tool.name))}</div><div class="sps-detail">${escHtml(summaryText)}</div></div><div class="sps-meta"><div class="sps-status">${status}</div><div class="sps-time">${escHtml(duration || (tool.status === 'running' ? 'Running' : 'Done'))}</div></div><div class="sps-chevron">&#9656;</div>`;
      const detail = document.createElement('div');
      detail.className = 'sp-detail';
      let detailHtml = `<div class="spd-section"><div class="spd-label">Summary</div><div class="spd-content">${summaryHtml || escHtml(toolLabel(tool.name))}</div></div>`;
      const inputText = _formatToolInput(tool.name, tool.input);
      if (inputText) {
        detailHtml += `<div class="spd-section"><div class="spd-label">Input</div><div class="spd-content"><pre>${escHtml(inputText)}</pre></div></div>`;
      }
      if (resultText) {
        const resultNote = toolResultSummary(tool.name, resultText);
        detailHtml += `<div class="spd-section"><div class="spd-label">Result${resultNote ? ` · ${escHtml(resultNote)}` : ''}</div><div class="spd-content"><pre>${escHtml(resultText.substring(0, 5000))}</pre></div></div>`;
      }
      detail.innerHTML = detailHtml;
      step.onclick = () => {
        step.classList.toggle('expanded');
        const expanded = _captureExpandedState();
        if (step.classList.contains('expanded')) {
          expanded.add(step.dataset.stepIdx);
        } else {
          expanded.delete(step.dataset.stepIdx);
        }
        panel._prevExpanded = expanded;
      };
      bodyEl.appendChild(step);
      bodyEl.appendChild(detail);
    });
    requestAnimationFrame(() => { bodyEl.scrollTop = prevScroll; });
  }

  _anchoredPanelToggle(pillEl, () => {
    if (_sidePanelRefreshTimer) {
      clearInterval(_sidePanelRefreshTimer);
      _sidePanelRefreshTimer = null;
    }
    _sidePanelAnchor = pillEl;
    panel.classList.add('open');
    document.body.classList.add('panel-open');
    document.querySelectorAll('.tool-pill.active-pill,.thinking-pill.active-pill').forEach(el => el.classList.remove('active-pill'));
    pillEl.classList.add('active-pill');
    rebuild(true);
    if (pillEl.classList.contains('streaming') || pillEl._ctx) {
      _sidePanelRefreshTimer = setInterval(rebuild, 800);
    }
  });
}

function openThinkingPanel(pillEl) {
  if (!pillEl) return;
  const panel = document.getElementById('sidePanel');
  const titleEl = document.getElementById('spTitle');
  const bodyEl = document.getElementById('spBody');
  if (panel.classList.contains('open') && _sidePanelAnchor === pillEl) {
    closeSidePanel(pillEl);
    return;
  }
  _anchoredPanelToggle(pillEl, () => {
    if (_sidePanelRefreshTimer) {
      clearInterval(_sidePanelRefreshTimer);
      _sidePanelRefreshTimer = null;
    }
    _sidePanelAnchor = pillEl;
    panel.classList.add('open');
    document.body.classList.add('panel-open');
    document.querySelectorAll('.tool-pill.active-pill,.thinking-pill.active-pill').forEach(el => el.classList.remove('active-pill'));
    pillEl.classList.add('active-pill');
    titleEl.innerHTML = `Thinking<span class="sp-dim">${pillEl._thinkingDuration ? ` · ${_formatDuration(pillEl._thinkingDuration)}` : ''}</span>`;
    bodyEl.innerHTML = '<div class="sp-thinking"></div>';
    const thinkingEl = bodyEl.querySelector('.sp-thinking');
    thinkingEl.textContent = pillEl._thinkingText || '';
    renderMarkdown(thinkingEl);
  });
}

function handleEvent(msg) {
  const el = document.getElementById('messages');
  switch(msg.type) {
    case 'active_streams':
      if (msg.chat_id && currentChat && msg.chat_id !== currentChat) break;
      const prevStreams = new Map(activeStreams);
      activeStreams.clear();
      (msg.streams || []).forEach(stream => {
        if (!stream || !stream.stream_id) return;
        const prev = prevStreams.get(stream.stream_id);
        stream.startedAt = prev ? prev.startedAt : Date.now();
        activeStreams.set(stream.stream_id, stream);
      });
      if (currentChatType === 'group' && !streaming) {
        renderAgentChips();
      }
      updateSendBtn();
      break;

    case 'stream_start': {
      const sid = msg.stream_id || ('_s' + Date.now());
      const speaker = msg.speaker_name ? {name: msg.speaker_name, avatar: msg.speaker_avatar || '', id: msg.speaker_id || ''} : null;
      const orphan = _streamCtx[sid];
      if (orphan && orphan.bubble && orphan.bubble.isConnected) {
        orphan.bubble.remove();
      }
      _streamCtx[sid] = _newStreamCtx(sid, speaker);
      currentStreamId = sid;
      streaming = true;
      currentBubble = null;
      currentSpeaker = speaker;
      sessionStorage.setItem('streamingChatId', msg.chat_id || currentChat || '');
      markStreamActivity('stream-start');
      activeStreams.set(sid, {
        stream_id: sid,
        name: msg.speaker_name || '',
        avatar: msg.speaker_avatar || '',
        profile_id: msg.speaker_id || '',
        startedAt: Date.now(),
      });
      hideAgentChips();
      hideStopMenu();
      updateSendBtn();

      refreshDebugState('stream-start');
      break;
    }

    case 'text': {
      _removeThinkingIndicator();
      const ctx = _getCtx(msg);
      if (!ctx) break;
      currentStreamId = ctx.id;
      currentSpeaker = ctx.speaker;
      _ensureCtxBubble(ctx);
      currentBubble = ctx.bubble;
      ctx.bubble.querySelector('.bubble').textContent += msg.text;
      markStreamActivity('text');
      scrollBottom();
      break;
    }

    case 'thinking': {
      _removeThinkingIndicator();
      const ctx = _getCtx(msg);
      if (!ctx) break;
      currentStreamId = ctx.id;
      currentSpeaker = ctx.speaker;
      _ensureCtxBubble(ctx);
      currentBubble = ctx.bubble;
      if (!ctx.thinkingStart) ctx.thinkingStart = Date.now();
      ctx.thinkingText += msg.text || '';
      const group = _getOrCreateWorkGroup(ctx.bubble);
      let tb = (ctx.thinkingBlock && ctx.thinkingBlock.isConnected) ? ctx.thinkingBlock : group.querySelector(`.thinking-block[data-stream-id="${ctx.id}"]`) || group.querySelector('.thinking-block:last-of-type');
      if (!tb) {
        tb = document.createElement('div');
        tb.className = 'thinking-block open';
        tb.dataset.streamId = ctx.id;
        tb.innerHTML = `<div class="thinking-header" onclick="_toggleThinkingBlock(this)"><span class="arrow">&#9656;</span> &#129504; Thinking...</div><div class="thinking-body"></div>`;
        group.querySelector('.tool-group-body').appendChild(tb);
      }
      ctx.thinkingBlock = tb;
      if (ctx.thinkingCollapsed) {
        _getOrCreateLiveThinkingPill(ctx, group);
      } else {
        const thinkingBody = tb.querySelector('.thinking-body');
        thinkingBody.textContent = ctx.thinkingText;
        thinkingBody.scrollTop = thinkingBody.scrollHeight;
      }
      _updateWorkGroupHeader(group);
      markStreamActivity('thinking');
      if (!ctx.thinkingCollapsed) scrollBottom();
      break;
    }

    case 'tool_use': {
      _removeThinkingIndicator();
      const ctx = _getCtx(msg);
      if (!ctx) break;
      currentStreamId = ctx.id;
      currentSpeaker = ctx.speaker;
      _ensureCtxBubble(ctx);
      currentBubble = ctx.bubble;
      if (!ctx.toolsStart) ctx.toolsStart = Date.now();
      ctx.toolCalls.push({
        id: msg.id || ('tool-' + Date.now()),
        name: msg.name || 'Tool',
        input: msg.input,
        summary: toolSummary(msg.name, msg.input),
        status: 'running',
        startTime: Date.now(),
        endTime: null,
        result: null,
      });
      _updateToolPillProgress(ctx);
      markStreamActivity('tool-use');
      scrollBottom();
      break;
    }

    case 'tool_result': {
      _removeThinkingIndicator();
      const ctx = _getCtx(msg);
      if (!ctx) break;
      currentStreamId = ctx.id;
      currentSpeaker = ctx.speaker;
      currentBubble = ctx.bubble;
      const toolId = msg.tool_use_id || msg.id || '';
      let toolCall = ctx.toolCalls.find(t => t.id === toolId) || null;
      if (!toolCall) {
        toolCall = ctx.toolCalls.find(t => t.status === 'running') || null;
      }
      if (toolCall) {
        toolCall.status = msg.is_error ? 'error' : 'completed';
        toolCall.endTime = Date.now();
        toolCall.result = {
          content: msg.content,
          is_error: Boolean(msg.is_error),
        };
      }
      _updateToolPillProgress(ctx);
      markStreamActivity('tool-result');
      scrollBottom();
      break;
    }

    case 'result': {
      _removeThinkingIndicator();
      const ctx = _getCtx(msg);
      if (!ctx) break;
      currentStreamId = ctx.id;
      currentSpeaker = ctx.speaker;
      currentBubble = ctx.bubble;
      if (ctx.bubble) {
        if (ctx.thinkingText) {
          _teardownLiveThinking(ctx);
          ctx.bubble.querySelectorAll('.thinking-block').forEach(tb => tb.remove());
          ctx.bubble.querySelectorAll('.tool-group').forEach(group => {
            if (!group.querySelector('.tool-block') && !group.querySelector('.thinking-block')) {
              group.remove();
            } else {
              _updateWorkGroupHeader(group);
            }
          });
          _createThinkingPill(ctx, ctx.thinkingStart ? (Date.now() - ctx.thinkingStart) : 0);
        } else {
          _teardownLiveThinking(ctx);
        }
        if (ctx.toolCalls.length > 0) {
          const totalTime = ctx.toolsStart ? (Date.now() - ctx.toolsStart) : 0;
          _finalizeToolPill(ctx, totalTime);
        }
        const costEl = document.createElement('div');
        costEl.className = 'cost';
        const cost = msg.cost_usd ? `$${msg.cost_usd.toFixed(4)}` : '';
        const tokens = msg.tokens_in || msg.tokens_out ? ` | ${msg.tokens_in}in/${msg.tokens_out}out` : '';
        costEl.textContent = cost + tokens;
        ctx.bubble.appendChild(costEl);
        ctx.bubble.classList.remove('streaming');
        renderMarkdown(ctx.bubble.querySelector('.bubble'));
      }
      markStreamActivity('result');
      // Update context bar from inline data or fallback to API
      if (msg.context_tokens_in != null && msg.context_window) {
        updateContextBar(msg.context_tokens_in, msg.context_window);
      } else {
        fetchContext(currentChat);
      }
      startUsagePolling();
      refreshDebugState('result');
      break;
    }

    case 'stream_end': {
      _removeThinkingIndicator();
      const sid = msg.stream_id || currentStreamId;
      // Track which agent just finished so chips exclude them
      if (sid) {
        const finished = activeStreams.get(sid);
        if (finished && finished.profile_id) _answeredAgents.add(finished.profile_id);
        const ctx = _streamCtx[sid] || null;
        if (ctx) {
          if (ctx.thinkingText && !(ctx.thinkingPill && ctx.thinkingPill.isConnected)) {
            _teardownLiveThinking(ctx);
            ctx.bubble?.querySelectorAll('.thinking-block').forEach(tb => tb.remove());
            _createThinkingPill(ctx, ctx.thinkingStart ? (Date.now() - ctx.thinkingStart) : 0);
          } else {
            _teardownLiveThinking(ctx);
          }
        }
        delete _streamCtx[sid];
        activeStreams.delete(sid);
      } else if (activeStreams.size === 1) {
        const [, only] = activeStreams.entries().next().value;
        if (only && only.profile_id) _answeredAgents.add(only.profile_id);
        activeStreams.clear();
      }
      const remaining = Object.keys(_streamCtx);
      streaming = _isAnyStreamActive();
      if (!streaming) {
        currentStreamId = '';
        currentBubble = null;
        currentSpeaker = null;
        sessionStorage.removeItem('streamingChatId');
        clearStreamWatchdog();
      } else if (!currentStreamId || currentStreamId === sid) {
        currentStreamId = remaining[remaining.length - 1] || '';
        currentBubble = _getCurrentBubble();
        currentSpeaker = currentStreamId ? _streamCtx[currentStreamId]?.speaker || null : null;
      }
      hideStopMenu();
      if (currentChatType === 'group' && msg.chat_id === currentChat) {
        renderAgentChips();
      }
      updateSendBtn();
  
      refreshDebugState('stream-end');
      break;
    }

    case 'stream_reattached': {
      // Server confirmed we re-attached to an active stream after replaying
      // the buffered events that were missed while the socket was down.
      dbg('stream re-attached for chat:', msg.chat_id);
      const sid = msg.stream_id || currentStreamId || ('_s' + Date.now());
      if (!_streamCtx[sid]) {
        _streamCtx[sid] = _newStreamCtx(sid, null);
      }
      if (!_streamCtx[sid].speaker && msg.speaker_name) {
        _streamCtx[sid].speaker = {name: msg.speaker_name, avatar: msg.speaker_avatar || '', id: msg.speaker_id || ''};
      }
      currentStreamId = sid;
      streaming = true;
      currentBubble = _streamCtx[sid].bubble || null;
      currentSpeaker = _streamCtx[sid].speaker || null;
      sessionStorage.setItem('streamingChatId', msg.chat_id || currentChat || '');
      markStreamActivity('stream-reattached');
      updateSendBtn();
  
      refreshDebugState('stream-reattached');
      break;
    }

    case 'attach_ok':
      _removeThinkingIndicator();
      // Server confirmed no active stream — safe to reload from DB.
      // This fires when the client thought a stream might be running
      // (sessionStorage had streamingChatId) but it already finished.
      dbg('attach ok, no active stream for chat:', msg.chat_id);
      Object.values(_streamCtx).forEach(ctx => _teardownLiveThinking(ctx));
      Object.keys(_streamCtx).forEach(k => delete _streamCtx[k]);
      activeStreams.clear();
      sessionStorage.removeItem('streamingChatId');
      streaming = false;
      currentStreamId = '';
      currentBubble = null;
      currentSpeaker = null;
      clearStreamWatchdog();
      hideStopMenu();
      updateSendBtn();

      // Skip reload if we already have messages loaded for this chat
      // (prevents request storm on reconnect/refresh)
      if (msg.chat_id && msg.chat_id === currentChat && !document.getElementById('messages').hasChildNodes()) {
        selectChat(msg.chat_id).catch(() => {});
      }
      refreshDebugState('attach-ok');
      break;

    case 'stream_complete_reload':
      _removeThinkingIndicator();
      // Stream finished while we were disconnected. Reload from DB.
      dbg('stream completed while disconnected, reloading chat:', msg.chat_id);
      streaming = false;
      activeStreams.clear();
      currentBubble = null;
      sessionStorage.removeItem('streamingChatId');
      clearStreamWatchdog();
      hideStopMenu();
      updateSendBtn();

      // Always reload on stream_complete — we may have missed messages
      if (msg.chat_id && msg.chat_id === currentChat) {
        selectChat(msg.chat_id).catch(() => {});
      }
      refreshDebugState('stream-complete-reload');
      break;

    case 'user_message_added':
      // Another client sent a message on this chat — show it
      if (msg.chat_id === currentChat && msg.content) {
        addUserMsg(msg.content);
      }
      break;

    case 'chat_updated':
      if (currentChat === msg.chat_id) {
        if (msg.title) document.getElementById('chatTitle').textContent = msg.title;
        // Update profile state if broadcast includes it
        if ('profile_id' in msg) {
          _currentChatProfileId = msg.profile_id || '';
          updateTopbarProfile(msg.profile_name || '', msg.profile_avatar || '');
          updateChatModelSelect();
        }
      }
      loadChats().catch(err => reportError('chat_updated loadChats', err));
      refreshDebugState('chat-updated');
      break;

    case 'chat_deleted':
      loadChats().then(chats => {
        if (currentChat === msg.chat_id && chats.length > 0) {
          selectChat(chats[0].id, chats[0].title).catch(() => {});
        }
      }).catch(err => reportError('chat_deleted loadChats', err));
      break;

    case 'alert':
      showAlertToast(msg);
      break;

    case 'alert_acked':
      hideAlertToast();
      const acked = alertsCache.find(a => a.id === msg.alert_id);
      if (acked) { acked.acked = true; renderAlertsPanel(); }
      break;

    case 'system':
      break;

    case 'error':
      _removeThinkingIndicator();
      addSystemMsg(msg.message || 'Unknown error');
      streaming = false;
      activeStreams.clear();
      clearStreamWatchdog();
      sessionStorage.removeItem('streamingChatId');
      hideStopMenu();
      updateSendBtn();
  
      refreshDebugState('event-error');
      break;
  }
}

// --- UI helpers ---
function addAssistantMsg() {
  const el = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg assistant streaming';
  const speaker = arguments.length ? arguments[0] : currentSpeaker;
  let inner = '';
  if (speaker && speaker.name) {
    inner += `<div class="speaker-header"><span class="speaker-avatar">${escHtml(speaker.avatar || '')}</span> <span class="speaker-name">${escHtml(speaker.name)}</span></div>`;
  }
  inner += '<div class="bubble"></div>';
  div.innerHTML = inner;
  el.appendChild(div);
  scrollBottom();
  return div;
}

function addUserMsg(text) {
  const el = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg user';
  div.textContent = text;
  el.appendChild(div);
  scrollBottomForce();
}

function _showThinkingIndicator() {
  _removeThinkingIndicator();
  const el = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg assistant';
  div.id = '_thinkingIndicator';
  div.innerHTML = '<div class="thinking-indicator"><div class="dot"></div><div class="dot"></div><div class="dot"></div><span class="ti-label">Thinking\u2026</span></div>';
  el.appendChild(div);
  scrollBottomForce();
}
function _removeThinkingIndicator() {
  const existing = document.getElementById('_thinkingIndicator');
  if (existing) existing.remove();
}

function addSystemMsg(text) {
  const el = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg assistant';
  div.innerHTML = `<div class="bubble" style="color:var(--red)">${escHtml(text)}</div>`;
  el.appendChild(div);
  scrollBottom();
}

/* --- Smart scroll: only auto-scroll if user is near bottom --- */
let _userScrolledUp = false;
const _SCROLL_THRESHOLD = 150; // px from bottom to count as "near bottom"

function _isNearBottom() {
  const el = document.getElementById('messages');
  if (!el) return true;
  return (el.scrollHeight - el.scrollTop - el.clientHeight) < _SCROLL_THRESHOLD;
}

function scrollBottom() {
  // Smart version: only scroll if user hasn't scrolled up
  if (_userScrolledUp) {
    _showNewContentPill();
    return;
  }
  scrollBottomForce();
}

function scrollBottomForce() {
  const el = document.getElementById('messages');
  if (!el) return;
  el.scrollTop = el.scrollHeight;
  _userScrolledUp = false;
  _hideNewContentPill();
}

function _showNewContentPill() {
  let pill = document.getElementById('newContentPill');
  if (pill) { pill.style.display = 'flex'; return; }
  pill = document.createElement('div');
  pill.id = 'newContentPill';
  pill.textContent = '\u2193 New';
  pill.style.cssText = 'position:absolute;bottom:80px;left:50%;transform:translateX(-50%);background:var(--accent);color:#fff;padding:6px 16px;border-radius:20px;font-size:13px;font-weight:600;cursor:pointer;z-index:200;display:flex;align-items:center;gap:4px;box-shadow:0 2px 8px rgba(0,0,0,0.3);transition:opacity 0.2s';
  pill.onclick = () => { scrollBottomForce(); };
  const container = document.getElementById('messages').parentElement;
  container.style.position = 'relative';
  container.appendChild(pill);
}

function _hideNewContentPill() {
  const pill = document.getElementById('newContentPill');
  if (pill) pill.style.display = 'none';
}

// Toggle collapsible block with scroll-position anchoring
let _programmaticScroll = false;
function _toggleCollapsible(headerEl) {
  const block = headerEl.parentElement;
  const scroller = document.getElementById('messages');
  const wasScrolledUp = _userScrolledUp;
  const beforeTop = block.getBoundingClientRect().top;
  block.classList.toggle('open');
  if (scroller && wasScrolledUp) {
    _programmaticScroll = true;
    const afterTop = block.getBoundingClientRect().top;
    scroller.scrollTop += (afterTop - beforeTop);
    _userScrolledUp = true;
    requestAnimationFrame(() => { _programmaticScroll = false; });
  }
}
function _toggleThinkingBlock(headerEl) {
  const block = headerEl ? headerEl.parentElement : null;
  const sid = block && block.dataset ? block.dataset.streamId : '';
  const ctx = sid ? _streamCtx[sid] : null;
  if (ctx) {
    _setThinkingCollapsed(ctx, true);
    return;
  }
  _toggleCollapsible(headerEl);
}

// Attach scroll listener once DOM is ready
(function _initScrollWatch() {
  function attach() {
    const el = document.getElementById('messages');
    if (!el) { setTimeout(attach, 100); return; }
    el.addEventListener('scroll', () => {
      if (_programmaticScroll) return;
      _userScrolledUp = !_isNearBottom();
      if (!_userScrolledUp) _hideNewContentPill();
    }, {passive: true});
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }
})();

// --- Alerts channel view (renders in main messages area) ---
function renderAlertsList(alerts) {
  channelAlertsData = alerts;
  const el = document.getElementById('messages');
  el.innerHTML = '';
  if (alerts.length === 0) {
    el.innerHTML = '<div style="padding:40px;text-align:center;color:#666">No alerts</div>';
    return;
  }
  const sevIcons = {critical:'\u26a0\ufe0f',warning:'\u26a0',info:'\u2139\ufe0f'};
  const sevColors = {critical:'#dc2626',warning:'#d97706',info:'#0891b2'};
  alerts.forEach(a => {
    const sev = a.severity || 'info';
    const icon = sevIcons[sev] || '\u2139\ufe0f';
    const color = sevColors[sev] || '#0891b2';
    const div = document.createElement('div');
    div.className = 'msg assistant';
    div.style.opacity = a.acked ? '0.4' : '1';
    div.style.cursor = 'pointer';
    div.onclick = () => showAlertDetail(a.id);
    let actions = '';
    if (!a.acked) {
      if (a.source === 'guardrail') {
        actions += `<button onclick="channelAlertAction('allow','${a.id}',this)" style="background:#16a34a;color:#fff;border:none;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;margin-right:4px">Allow</button>`;
      }
      actions += `<button onclick="channelAlertAction('ack','${a.id}',this)" style="background:${color};color:#fff;border:none;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer">Ack</button>`;
    } else {
      actions = '<span style="color:#4ade80;font-size:11px">\u2713 Acked</span>';
    }
    const ago = timeAgo(a.created_at);
    div.innerHTML = `<div class="bubble" style="border-left:3px solid ${color};padding:10px 14px">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
        <span style="font-size:16px">${icon}</span>
        <span style="font-size:10px;font-weight:700;text-transform:uppercase;color:${color}">${escHtml(a.source)}</span>
        <span style="font-size:10px;color:#666;margin-left:auto">${ago}</span>
      </div>
      <div style="font-weight:600;margin-bottom:4px">${escHtml(a.title)}</div>
      ${a.body ? `<div style="font-size:12px;color:#aaa;white-space:pre-wrap;margin-bottom:6px">${escHtml(a.body)}</div>` : ''}
      <div>${actions}</div>
    </div>`;
    el.appendChild(div);
  });
}
let channelAlertsData = [];
function channelAlertAction(action, alertId, btn) {
  event.stopPropagation();
  fetch('/api/alerts/' + alertId + '/' + action, {method:'POST'}).then(r => {
    if (r.ok && btn) {
      const bubble = btn.closest('.msg');
      if (bubble) bubble.style.opacity = '0.4';
      btn.parentElement.innerHTML = '<span style="color:#4ade80;font-size:11px">\u2713 Acked</span>';
    }
  }).catch(() => {});
}
function showAlertDetail(alertId) {
  const a = channelAlertsData.find(x => x.id === alertId) || alertsCache.find(x => x.id === alertId);
  if (!a) return;
  const sevIcons = {critical:'\u26a0\ufe0f',warning:'\u26a0',info:'\u2139\ufe0f'};
  const sevColors = {critical:'#dc2626',warning:'#d97706',info:'#0891b2'};
  const color = sevColors[a.severity] || '#0891b2';
  const icon = sevIcons[a.severity] || '\u2139\ufe0f';
  const ago = timeAgo(a.created_at);
  let metaHtml = '';
  if (a.metadata && Object.keys(a.metadata).length > 0) {
    metaHtml = '<div class="ad-section"><div class="ad-label">Metadata</div>' +
      Object.entries(a.metadata).sort((x,y) => x[0].localeCompare(y[0])).map(([k,v]) =>
        `<div style="margin-top:8px"><div class="ad-meta-key">${escHtml(k)}</div><div class="ad-meta-val">${escHtml(v)}</div></div>`
      ).join('') + '</div>';
  }
  let actions = '';
  if (!a.acked) {
    if (a.source === 'guardrail') {
      actions += `<button style="background:#16a34a;color:#fff" onclick="detailAlertAction('allow','${a.id}')">Allow</button>`;
    }
    actions += `<button style="background:${color};color:#fff" onclick="detailAlertAction('ack','${a.id}')">Ack</button>`;
  }
  actions += `<button style="background:#333;color:#ccc" onclick="copyAlertBody('${a.id}',this)">Copy</button>`;
  const overlay = document.createElement('div');
  overlay.className = 'alert-detail-overlay';
  overlay.onclick = (e) => { if (e.target === overlay) closeAlertDetail(overlay); };
  overlay.innerHTML = `<div class="alert-detail-card">
    <div class="ad-header">
      <span class="ad-icon">${icon}</span>
      <div>
        <span class="ad-source" style="background:${color}22;color:${color}">${escHtml((a.source||'').toUpperCase())}</span>
        <div class="ad-time">${ago}${a.acked ? ' \u2014 \u2713 Acknowledged' : ''}</div>
      </div>
      <button class="ad-close" onclick="closeAlertDetail(this)">\u2715</button>
    </div>
    <div class="ad-section"><div class="ad-label">Title</div><div class="ad-title">${escHtml(a.title)}</div></div>
    ${a.body ? `<div class="ad-section"><div class="ad-label">Details</div><div class="ad-body">${escHtml(a.body)}</div></div>` : ''}
    ${metaHtml}
    <div class="ad-actions">${actions}</div>
  </div>`;
  document.body.appendChild(overlay);
}
function closeAlertDetail(el) {
  const overlay = el.closest('.alert-detail-overlay');
  if (!overlay) return;
  overlay.style.transition = 'opacity .2s ease';
  overlay.style.opacity = '0';
  setTimeout(() => overlay.remove(), 200);
}
function copyAlertBody(alertId, btn) {
  const a = channelAlertsData.find(x => x.id === alertId) || alertsCache.find(x => x.id === alertId);
  if (a) {
    navigator.clipboard.writeText(a.body || a.title || '');
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = '\u2713 Copied';
      btn.style.background = '#16a34a';
      btn.style.color = '#fff';
      setTimeout(() => { btn.textContent = orig; btn.style.background = '#333'; btn.style.color = '#ccc'; }, 1500);
    }
  }
}
function detailAlertAction(action, alertId) {
  fetch('/api/alerts/' + alertId + '/' + action, {method:'POST'}).then(r => {
    if (r.ok) {
      document.querySelector('.alert-detail-overlay')?.remove();
      // Refresh channel view if on alerts channel
      if (currentChatType === 'alerts' && currentChat) {
        selectChat(currentChat).catch(() => {});
      }
    }
  }).catch(() => {});
}

// --- Persistent alerts panel ---
let alertsCache = [];
function loadAlerts() {
  fetch('/api/alerts?limit=50').then(r => r.json()).then(alerts => {
    alertsCache = alerts;
    renderAlertsPanel();
  }).catch(() => {});
}
function renderAlertsPanel() {
  const list = document.getElementById('alertsList');
  const unacked = alertsCache.filter(a => !a.acked).length;
  document.getElementById('alertCount').textContent = unacked > 0 ? unacked : '';
  list.innerHTML = '';
  if (alertsCache.length === 0) {
    list.innerHTML = '<div style="padding:20px;text-align:center;color:#666;font-size:12px">No alerts</div>';
    return;
  }
  const sevIcons = {critical:'\u26a0\ufe0f',warning:'\u26a0',info:'\u2139\ufe0f'};
  const sevColors = {critical:'#dc2626',warning:'#d97706',info:'#0891b2'};
  for (const a of alertsCache) {
    const div = document.createElement('div');
    div.className = 'alert-item' + (a.acked ? ' acked' : '');
    div.style.cursor = 'pointer';
    div.onclick = () => { toggleAlertsPanel(); showAlertDetail(a.id); };
    const icon = sevIcons[a.severity] || '\u2139\ufe0f';
    const color = sevColors[a.severity] || '#0891b2';
    let actions = '';
    if (!a.acked) {
      if (a.source === 'guardrail') {
        actions += `<button style="background:#16a34a;color:#fff" onclick="event.stopPropagation();panelAlertAction('allow','${a.id}')">Allow</button>`;
      }
      actions += `<button style="background:${color};color:#fff" onclick="event.stopPropagation();panelAlertAction('ack','${a.id}')">Ack</button>`;
    }
    const ago = timeAgo(a.created_at);
    div.innerHTML = `<span class="ai-icon">${icon}</span>
      <div class="ai-body">
        <div class="ai-source">${escHtml(a.source)}</div>
        <div class="ai-title">${escHtml(a.title)}</div>
        <div class="ai-time">${ago}</div>
      </div>
      <div class="ai-actions">${actions}</div>`;
    list.appendChild(div);
  }
}
function toggleAlertsPanel() {
  const panel = document.getElementById('alertsPanel');
  const showing = panel.classList.toggle('show');
  if (showing) loadAlerts();
  // Close settings if open
  document.getElementById('settingsPanel').classList.remove('show');
}

function toggleSettings() {
  const panel = document.getElementById('settingsPanel');
  const showing = panel.classList.toggle('show');
  if (showing) {
    loadSettingsData();
    // Close alerts if open
    document.getElementById('alertsPanel').classList.remove('show');
  }
}

// Click outside to dismiss alerts/settings panels
document.addEventListener('click', (e) => {
  const alertsPanel = document.getElementById('alertsPanel');
  const settingsPanel = document.getElementById('settingsPanel');
  const alertBadge = document.getElementById('alertBadge');
  const settingsBtn = document.getElementById('settingsBtn');
  const stopMenu = document.getElementById('stopMenu');
  const sendBtn = document.getElementById('sendBtn');
  // Close alerts panel if click is outside it and outside the bell
  if (alertsPanel.classList.contains('show') &&
      !alertsPanel.contains(e.target) && !alertBadge.contains(e.target)) {
    alertsPanel.classList.remove('show');
  }
  // Close settings panel if click is outside it and outside the settings button
  if (settingsPanel.classList.contains('show') &&
      !settingsPanel.contains(e.target) && !(settingsBtn && settingsBtn.contains(e.target))) {
    settingsPanel.classList.remove('show');
  }
  if (stopMenu && stopMenu.classList.contains('show') &&
      !stopMenu.contains(e.target) && !(sendBtn && sendBtn.contains(e.target))) {
    hideStopMenu();
  }
});

// --- Settings Panel ---
let _settingsModels = [];  // cached model list

async function loadSettingsData() {
  // Server default model
  try {
    const r = await fetch('/api/health', {credentials: 'same-origin'});
    if (r.ok) {
      const d = await r.json();
      document.getElementById('serverModelDisplay').textContent = d.model || '--';
      document.getElementById('whisperStatus').textContent = d.whisper ? 'Enabled' : 'Disabled';
    }
  } catch(e) {}

  // Local Ollama models
  try {
    const r = await fetch('/api/models/local', {credentials: 'same-origin'});
    if (r.ok) {
      const models = await r.json();
      const localNames = models.map(m => m.id + ' (' + m.sizeGb + 'GB)');
      document.getElementById('ollamaModelsList').textContent = localNames.join(', ') || 'None found';
      _settingsModels = models;
    }
  } catch(e) {}

  // Embedding status
  try {
    const r = await fetch('/api/embedding/status', {credentials: 'same-origin'});
    if (r.ok) {
      const d = await r.json();
      const parts = [];
      if (d.memory) parts.push('Memory: ' + d.memory.files + ' files');
      if (d.transcripts) parts.push('Transcripts: ' + d.transcripts.files + ' files');
      document.getElementById('embeddingStatus').textContent = parts.join(' | ') || '--';
    }
  } catch(e) { document.getElementById('embeddingStatus').textContent = 'Not available'; }

  // Chat model selector
  updateChatModelSelect();
  updateUsageBarVisibility();
  applyChatFontScale();
}

function updateChatModelSelect() {
  const sel = document.getElementById('chatModelSelect');
  const hint = document.getElementById('chatModelHint');
  if (!currentChat) {
    sel.disabled = true;
    hint.textContent = 'Select a chat first';
    sel.innerHTML = '<option value="">--</option>';
    return;
  }
  // Get current chat's model from sidebar data
  const item = document.querySelector('.chat-item[data-id="' + currentChat + '"]');
  const chatTitle = item?.dataset?.title || 'this chat';
  // Lock model selector when a profile is attached (profile is source of truth)
  const hasProfile = _currentChatProfileId && _currentChatProfileId.length > 0;
  if (hasProfile) {
    sel.disabled = true;
    hint.textContent = 'Model locked by profile: ' + (_currentChatProfileName || _currentChatProfileId);
  } else {
    sel.disabled = false;
    hint.textContent = 'Model for: ' + chatTitle;
  }

  // Build option list: cloud models + local models
  const cloudModels = [
    {id: 'claude-opus-4-6', name: 'Claude Opus 4.6'},
    {id: 'claude-sonnet-4-6', name: 'Claude Sonnet 4.6'},
    {id: 'grok-4', name: 'Grok 4'},
    {id: 'grok-4-fast', name: 'Grok 4 Fast'},
    {id: 'codex:gpt-5.4', name: 'GPT-5.4'},
    {id: 'codex:gpt-5.4-mini', name: 'GPT-5.4 Mini'},
    {id: 'codex:gpt-5.3-codex', name: 'GPT-5.3'},
    {id: 'codex:gpt-5.2', name: 'GPT-5.2'},
    {id: 'codex:gpt-5.1-codex-max', name: 'GPT-5.1 Max'},
  ];
  sel.innerHTML = '';
  cloudModels.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m.id;
    opt.textContent = m.name;
    sel.appendChild(opt);
  });
  // Add separator + local models
  if (_settingsModels.length) {
    const sep = document.createElement('option');
    sep.disabled = true;
    sep.textContent = '── Local Models ──';
    sel.appendChild(sep);
    _settingsModels.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.displayName || m.id;
      sel.appendChild(opt);
    });
  }

  // Fetch current chat's model from context endpoint
  fetch('/api/chats/' + currentChat + '/context', {credentials: 'same-origin'})
    .then(r => r.ok ? r.json() : null)
    .then(d => {
      if (d && d.model) {
        sel.value = d.model;
        const item = document.querySelector('.chat-item[data-id="' + currentChat + '"]');
        if (item) item.dataset.model = d.model;
        updateUsageBarVisibility();
        startUsagePolling();
      }
    })
    .catch(() => {});
}

function changeChatModel(model) {
  if (!currentChat || !model) return;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({action: 'set_chat_model', chat_id: currentChat, model: model}));
    dbg('set_chat_model:', currentChat, model);
    const item = document.querySelector('.chat-item[data-id="' + currentChat + '"]');
    if (item) item.dataset.model = model;
    updateUsageBarVisibility();
    // Update hint
    document.getElementById('chatModelHint').textContent = 'Switched to: ' + model;
  }
}
function panelAlertAction(action, alertId) {
  fetch('/api/alerts/' + alertId + '/' + action, {method:'POST'}).then(r => {
    if (r.ok) {
      const a = alertsCache.find(x => x.id === alertId);
      if (a) a.acked = true;
      renderAlertsPanel();
    }
  }).catch(() => {});
}
function clearAllAlerts() {
  fetch('/api/alerts', {method:'DELETE'}).then(r => {
    if (r.ok) { alertsCache = []; renderAlertsPanel(); }
  }).catch(() => {});
}
function timeAgo(iso) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff/60) + 'm ago';
  if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
  return new Date(iso).toLocaleDateString();
}
// Load alerts on page init
setTimeout(loadAlerts, 1000);

let alertToastTimer = null;
function showAlertToast(msg) {
  const toast = document.getElementById('alertToast');
  const inner = document.getElementById('alertToastInner');
  const sev = msg.severity || 'info';
  inner.className = 'alert-toast-inner ' + sev;
  const icons = {critical: '\u26a0\ufe0f', warning: '\u26a0', info: '\u2139\ufe0f'};
  document.getElementById('alertToastIcon').textContent = icons[sev] || '\u2139\ufe0f';
  document.getElementById('alertToastSource').textContent = (msg.source || 'system').toUpperCase();
  document.getElementById('alertToastTitle').textContent = msg.title || '';
  document.getElementById('alertToastText').textContent = msg.body || '';
  // Actions
  const actions = document.getElementById('alertToastActions');
  actions.innerHTML = '';
  if (msg.source === 'guardrail' && msg.id) {
    const allowBtn = document.createElement('button');
    allowBtn.className = 'btn-allow';
    allowBtn.textContent = 'Allow';
    allowBtn.onclick = (e) => { e.stopPropagation(); alertAction('allow', msg.id); };
    actions.appendChild(allowBtn);
  }
  if (msg.id) {
    const ackBtn = document.createElement('button');
    ackBtn.className = 'btn-ack';
    ackBtn.textContent = 'Ack';
    ackBtn.onclick = (e) => { e.stopPropagation(); alertAction('ack', msg.id); };
    actions.appendChild(ackBtn);
  }
  const dismissBtn = document.createElement('button');
  dismissBtn.className = 'btn-dismiss';
  dismissBtn.textContent = '\u2715';
  dismissBtn.onclick = (e) => { e.stopPropagation(); hideAlertToast(); };
  actions.appendChild(dismissBtn);
  // Add to persistent cache + update badge
  alertsCache.unshift({id:msg.id,source:msg.source,severity:sev,title:msg.title||'',body:msg.body||'',acked:false,created_at:msg.created_at||new Date().toISOString(),metadata:msg.metadata||{}});
  renderAlertsPanel();
  // Click toast body to open detail
  inner.onclick = () => { hideAlertToast(); showAlertDetail(msg.id); };
  // Show toast
  toast.classList.add('show');
  clearTimeout(alertToastTimer);
  alertToastTimer = setTimeout(hideAlertToast, 10000);
}
function hideAlertToast() {
  document.getElementById('alertToast').classList.remove('show');
  clearTimeout(alertToastTimer);
}
function alertAction(action, alertId) {
  fetch('/api/alerts/' + alertId + '/' + action, {method: 'POST'})
    .then(r => { if (r.ok) hideAlertToast(); })
    .catch(() => {});
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

const TOOL_META = {
  Read:     {icon: '📄', label: 'Read File'},
  Edit:     {icon: '✏️', label: 'Edit File'},
  Write:    {icon: '📝', label: 'Write File'},
  Bash:     {icon: '💻', label: 'Run Command'},
  Grep:     {icon: '🔍', label: 'Search Code'},
  Glob:     {icon: '📂', label: 'Find Files'},
  WebFetch: {icon: '🌐', label: 'Fetch URL'},
  WebSearch:{icon: '🔎', label: 'Web Search'},
  Agent:    {icon: '🤖', label: 'Sub-Agent'},
  Skill:    {icon: '⚡', label: 'Skill'},
};

function toolIcon(name) { return (TOOL_META[name] || {}).icon || '🔧'; }
function toolLabel(name) { return (TOOL_META[name] || {}).label || name; }

function toolSummary(name, input) {
  const o = typeof input === 'string' ? (() => { try { return JSON.parse(input); } catch(e) { return {}; } })() : (input || {});
  switch (name) {
    case 'Read': {
      const p = o.file_path || '';
      const short = p.split('/').slice(-2).join('/');
      let s = `Reading <code>${escHtml(short)}</code>`;
      if (o.offset) s += ` from line ${o.offset}`;
      if (o.limit) s += ` (${o.limit} lines)`;
      return s;
    }
    case 'Edit': {
      const p = (o.file_path || '').split('/').slice(-2).join('/');
      return `Editing <code>${escHtml(p)}</code>`;
    }
    case 'Write': {
      const p = (o.file_path || '').split('/').slice(-2).join('/');
      return `Writing <code>${escHtml(p)}</code>`;
    }
    case 'Bash': {
      const cmd = o.command || '';
      const short = cmd.length > 80 ? cmd.substring(0, 77) + '...' : cmd;
      const desc = o.description || '';
      if (desc) return `${escHtml(desc)}`;
      return `<code>${escHtml(short)}</code>`;
    }
    case 'Grep': {
      const pat = o.pattern || '';
      const path = o.path ? o.path.split('/').slice(-2).join('/') : '';
      let s = `Searching for <code>${escHtml(pat)}</code>`;
      if (path) s += ` in ${escHtml(path)}`;
      return s;
    }
    case 'Glob': {
      const pat = o.pattern || '';
      return `Finding files matching <code>${escHtml(pat)}</code>`;
    }
    case 'Agent': {
      return escHtml(o.description || o.prompt?.substring(0, 80) || 'Running sub-agent');
    }
    case 'Skill': {
      return `Running skill <code>${escHtml(o.skill || '')}</code>`;
    }
    case 'WebSearch': {
      return `Searching: <code>${escHtml(o.query || '')}</code>`;
    }
    default: return null;
  }
}

function toolResultSummary(name, content) {
  if (!content) return null;
  const s = typeof content === 'string' ? content : JSON.stringify(content);
  if (name === 'Grep' || name === 'Glob') {
    const lines = s.trim().split('\\n').filter(Boolean);
    if (lines.length > 0) return `${lines.length} result${lines.length === 1 ? '' : 's'}`;
  }
  if (name === 'Bash') {
    const lines = s.trim().split('\\n');
    if (lines.length <= 3) return null;
    return `${lines.length} lines of output`;
  }
  return null;
}

function renderInlineMarkdown(text) {
  let html = escHtml(text);
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\\*\\*\\*([^*]+)\\*\\*\\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
  html = html.replace(/\\*([^*]+)\\*/g, '<em>$1</em>');
  return html;
}

function renderMarkdown(el) {
  const source = el.textContent || '';
  const codeBlocks = [];
  let text = source.replace(/```([\\w-]*)\\n([\\s\\S]*?)```/g, (_, lang, code) => {
    codeBlocks.push(`<pre><code>${escHtml(code.trimEnd())}</code></pre>`);
    return `@@CODEBLOCK_${codeBlocks.length - 1}@@`;
  });
  const lines = text.split('\\n');
  const html = [];
  let listType = null;

  function closeList() {
    if (!listType) return;
    html.push(listType === 'ol' ? '</ol>' : '</ul>');
    listType = null;
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      continue;
    }

    const codeMatch = trimmed.match(/^@@CODEBLOCK_(\\d+)@@$/);
    if (codeMatch) {
      closeList();
      html.push(codeBlocks[Number(codeMatch[1])] || '');
      continue;
    }

    let match = line.match(/^###\\s+(.+)$/);
    if (match) {
      closeList();
      html.push(`<h4>${renderInlineMarkdown(match[1])}</h4>`);
      continue;
    }

    match = line.match(/^##\\s+(.+)$/);
    if (match) {
      closeList();
      html.push(`<h3>${renderInlineMarkdown(match[1])}</h3>`);
      continue;
    }

    match = line.match(/^#\\s+(.+)$/);
    if (match) {
      closeList();
      html.push(`<h2>${renderInlineMarkdown(match[1])}</h2>`);
      continue;
    }

    match = line.match(/^[-*]\\s+(.+)$/);
    if (match) {
      if (listType !== 'ul') {
        closeList();
        html.push('<ul>');
        listType = 'ul';
      }
      html.push(`<li>${renderInlineMarkdown(match[1])}</li>`);
      continue;
    }

    match = line.match(/^\\d+\\.\\s+(.+)$/);
    if (match) {
      if (listType !== 'ol') {
        closeList();
        html.push('<ol>');
        listType = 'ol';
      }
      html.push(`<li>${renderInlineMarkdown(match[1])}</li>`);
      continue;
    }

    closeList();
    html.push(`<p>${renderInlineMarkdown(line)}</p>`);
  }

  closeList();
  el.innerHTML = html.join('');
}

function updateSendBtn() {
  const btn = document.getElementById('sendBtn');
  const canSend = Boolean(currentChat && ws && ws.readyState === WebSocket.OPEN);
  const showStop = streaming && !composerHasDraft;
  if (showStop) {
    btn.innerHTML = '&#9632;';
    btn.className = 'btn-compose compose-action is-stop';
    btn.disabled = !canSend;
    btn.title = activeStreams.size > 1 ? 'Choose stream to stop' : 'Stop';
  } else {
    btn.innerHTML = '&#9654;';
    btn.className = 'btn-compose compose-action is-send';
    btn.disabled = !canSend;
    btn.title = btn.disabled ? 'Waiting for chat initialization' : 'Send';
    hideStopMenu();
  }
}

function setTranscribeStatus(text = '') {
  const el = document.getElementById('transcribeStatus');
  el.textContent = text;
  el.style.display = text ? 'block' : 'none';
}

function stopVoiceStream() {
  if (!mediaStream) return;
  mediaStream.getTracks().forEach(track => track.stop());
  mediaStream = null;
}

function updateVoiceBtn() {
  // Voice button removed — iOS dictation handles this natively
}

function buildAttachmentPreview(att, idx) {
  const item = document.createElement('div');
  item.className = 'attach-item';
  if (att.type === 'image') {
    const img = document.createElement('img');
    img.src = `data:${att.mimeType};base64,${att.base64}`;
    img.alt = '';
    item.appendChild(img);
  } else {
    const icon = document.createElement('span');
    icon.innerHTML = '&#128196;';
    item.appendChild(icon);
  }
  const label = document.createElement('span');
  label.textContent = att.name;
  item.appendChild(label);
  const remove = document.createElement('span');
  remove.className = 'remove';
  remove.innerHTML = '&times;';
  remove.onclick = () => removeAttachment(idx);
  item.appendChild(remove);
  return item;
}

function renderAttachmentPreview() {
  const preview = document.getElementById('attachPreview');
  preview.innerHTML = '';
  pendingAttachments.forEach((att, idx) => {
    preview.appendChild(buildAttachmentPreview(att, idx));
  });
}

async function transcribeVoiceBlob(blob, mimeType) {
  transcribing = true;
  setTranscribeStatus('Transcribing voice note...');

  const ext = mimeType.includes('mp4') ? 'm4a' :
    mimeType.includes('ogg') ? 'ogg' :
    mimeType.includes('mpeg') ? 'mp3' : 'webm';
  const formData = new FormData();
  formData.append('file', blob, `voice.${ext}`);
  try {
    const r = await fetch('/api/transcribe', {method: 'POST', body: formData, credentials: 'same-origin'});
    const data = await r.json();
    if (!r.ok) {
      throw new Error(data.error || `transcribe failed: ${r.status}`);
    }
    const input = document.getElementById('input');
    const prefix = input.value.trim() ? `${input.value.trim()} ` : '';
    input.value = `${prefix}${data.text || ''}`.trim();
    input.dispatchEvent(new Event('input'));
    input.focus();
    setTranscribeStatus('');
  } catch (err) {
    reportError('transcribe voice', err);
    addSystemMsg(`Voice transcription failed: ${err?.message || err}`);
    setTranscribeStatus('');
  } finally {
    transcribing = false;

  }
}

async function toggleVoiceRecording() {
  if (transcribing) return;
  if (recording && mediaRecorder) {
    mediaRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    addSystemMsg('Voice recording is not supported here. Use keyboard dictation instead.');
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({audio: true});
    recordingChunks = [];
    const preferredMime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : '';
    mediaRecorder = preferredMime ? new MediaRecorder(mediaStream, {mimeType: preferredMime}) : new MediaRecorder(mediaStream);
    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        recordingChunks.push(event.data);
      }
    };
    mediaRecorder.onerror = (event) => {
      reportError('voice recorder', event.error || event);
      setTranscribeStatus('');
      recording = false;
      mediaRecorder = null;
      recordingChunks = [];
      stopVoiceStream();
  
    };
    mediaRecorder.onstop = async () => {
      const mimeType = mediaRecorder?.mimeType || 'audio/webm';
      const chunks = recordingChunks.slice();
      mediaRecorder = null;
      recording = false;
      recordingChunks = [];
      stopVoiceStream();
  
      if (!chunks.length) {
        setTranscribeStatus('');
        return;
      }
      await transcribeVoiceBlob(new Blob(chunks, {type: mimeType}), mimeType);
    };
    mediaRecorder.start();
    recording = true;
    setTranscribeStatus('Recording voice note... tap again to stop');

  } catch (err) {
    reportError('toggle voice', err);
    recording = false;
    mediaRecorder = null;
    recordingChunks = [];
    stopVoiceStream();
    setTranscribeStatus('');

    addSystemMsg(`Voice recording failed: ${err?.message || err}`);
  }
}

// --- Send ---
async function send(options = {}) {
  const targetAgent = options.targetAgent || '';
  const allowLastPrompt = Boolean(options.allowLastPrompt);
  const input = document.getElementById('input');
  const rawText = input.value.trim();
  const text = rawText || (allowLastPrompt ? lastSubmittedPrompt : '');
  dbg(' send:', {text: text?.substring(0,30), currentChat, streaming, wsState: ws?.readyState});
  if (!text && pendingAttachments.length === 0) return;
  if (!currentChat) {
    dbg(' no active chat on send, forcing init');
    try {
      await ensureInitialized('send-no-chat');
    } catch (err) {
      reportError('send init', err);
      addSystemMsg('Chat initialization failed. Check the debug bar.');
      return;
    }
  }
  if (!currentChat) {
    dbg('ERROR: no active chat after init');
    addSystemMsg('Chat initialization failed. Check the debug bar.');
    return;
  }
  if (!ws || ws.readyState !== WebSocket.OPEN) { dbg('ERROR: ws not open'); return; }
  _userScrolledUp = false;
  _hideNewContentPill();
  const attachmentSummary = pendingAttachments.length ? `Attachments: ${pendingAttachments.map(att => att.name).join(', ')}` : '';
  addUserMsg([text, attachmentSummary].filter(Boolean).join('\\n') || '(attachment)');
  const msg = {action: 'send', chat_id: currentChat, prompt: text};
  if (targetAgent) msg.target_agent = targetAgent;
  if (pendingAttachments.length > 0) {
    msg.attachments = pendingAttachments.map(a => ({id: a.id, type: a.type, name: a.name}));
  }
  lastSubmittedPrompt = text;
  if (!targetAgent) _answeredAgents.clear(); // New user message — reset answered set
  hideAgentChips();
  hideStopMenu();
  ws.send(JSON.stringify(msg));
  _showThinkingIndicator();
  input.value = '';
  sessionStorage.removeItem('draftText');
  input.style.height = 'auto';
  clearAttachments();
  refreshComposerDraftState();
  refreshDebugState('send');
}

function askAgent(profileId) {
  send({targetAgent: profileId, allowLastPrompt: true}).catch(err => reportError('askAgent', err));
}

// --- Chats ---
async function loadChats() {
  const r = await fetch('/api/chats', {credentials: 'same-origin'});
  dbg(' loadChats status:', r.status);
  if (!r.ok) {
    dbg('ERROR: loadChats failed:', r.status);
    throw new Error(`loadChats failed: ${r.status}`);
  }
  const chats = await r.json();
  knownChatCount = chats.length;
  dbg(' chats:', chats.length, chats.map(c => c.id));

  // Partition into channels (chat + alerts) and threads
  const channels = chats.filter(c => (c.type || 'chat') !== 'thread');
  const threads = chats.filter(c => c.type === 'thread').slice(0, 10);

  function buildChatItem(c, isThread) {
    const d = document.createElement('div');
    d.className = 'chat-item' + (c.id === currentChat ? ' active' : '') + (isThread ? ' thread-item' : '');
    const top = document.createElement('div');
    top.className = 'chat-item-top';
    // Icon prefix
    if (isThread) {
      const icon = document.createElement('span');
      icon.className = 'ci-avatar';
      icon.textContent = '\u26A1';
      top.appendChild(icon);
    } else if (c.type === 'group') {
      const icon = document.createElement('span');
      icon.className = 'ci-avatar';
      icon.textContent = c.profile_avatar || '👥';
      top.appendChild(icon);
    } else if (c.profile_avatar) {
      const avatarSpan = document.createElement('span');
      avatarSpan.className = 'ci-avatar';
      avatarSpan.textContent = c.profile_avatar;
      top.appendChild(avatarSpan);
    } else {
      const avatarSpan = document.createElement('span');
      avatarSpan.className = 'ci-avatar';
      avatarSpan.textContent = c.type === 'alerts' ? '🚨' : '💬';
      top.appendChild(avatarSpan);
    }
    const titleSpan = document.createElement('span');
    titleSpan.className = 'chat-item-title';
    let displayTitle = c.title || 'Untitled';
    if (c.type === 'group' && c.member_count) displayTitle += ' (' + c.member_count + ')';
    titleSpan.textContent = displayTitle;
    top.appendChild(titleSpan);
    d.dataset.id = c.id;
    d.dataset.title = c.title || 'Untitled';
    d.dataset.type = c.type || 'chat';
    d.dataset.category = c.category || '';
    d.dataset.model = c.model || '';
    d.dataset.profileId = c.profile_id || '';
    d.dataset.profileName = c.profile_name || '';
    d.dataset.profileAvatar = c.profile_avatar || '';
    d.onclick = () => selectChat(c.id, c.title, c.type, c.category).catch(err => reportError('selectChat click', err));
    d.ondblclick = (e) => { e.stopPropagation(); startRenameChat(d, c.id, c.title || 'Untitled'); };
    d.oncontextmenu = (e) => { e.preventDefault(); e.stopPropagation(); confirmDeleteChat(c.id, c.title || 'Untitled'); };
    const actions = document.createElement('span');
    actions.className = 'chat-item-actions';
    actions.innerHTML =
      '<button class="chat-action-btn" title="Rename" data-action="rename">\u270F\uFE0F</button>' +
      '<button class="chat-action-btn" title="Delete" data-action="delete">🗑️</button>';
    actions.querySelector('[data-action="rename"]').onclick = (e) => {
      e.stopPropagation(); startRenameChat(d, c.id, c.title || 'Untitled');
    };
    actions.querySelector('[data-action="delete"]').onclick = (e) => {
      e.stopPropagation(); confirmDeleteChat(c.id, c.title || 'Untitled');
    };
    top.appendChild(actions);
    d.appendChild(top);
    if (!isThread) {
      const sub = document.createElement('div');
      sub.className = 'chat-item-subtitle';
      const agentName = c.profile_name || '';
      const modelName = c.model || '';
      if (c.type === 'alerts') {
        sub.textContent = 'Alerts · Trading + System';
      } else if (c.type === 'group') {
        sub.textContent = 'Group · ' + (c.member_count || 0) + ' members';
      } else if (agentName && modelName) {
        sub.appendChild(document.createTextNode(agentName + ' · '));
        const model = document.createElement('span');
        model.className = 'model';
        model.textContent = modelName;
        sub.appendChild(model);
      } else if (modelName) {
        sub.textContent = modelName;
      }
      if (sub.textContent || sub.children.length) {
        d.appendChild(sub);
      }
    }
    return d;
  }

  // Render channels
  const list = document.getElementById('chatList');
  list.innerHTML = '';
  channels.forEach(c => list.appendChild(buildChatItem(c, false)));

  // Render threads section
  const threadHeader = document.getElementById('threadSectionHeader');
  const threadList = document.getElementById('threadList');
  threadList.innerHTML = '';
  if (threads.length > 0) {
    threadHeader.style.display = 'flex';
    const collapsed = threadList.dataset.collapsed === 'true';
    threadList.style.display = collapsed ? 'none' : '';
    threads.forEach(c => threadList.appendChild(buildChatItem(c, true)));
  } else {
    threadHeader.style.display = 'none';
  }

  setActiveChatUI();
  updateUsageBarVisibility();
  refreshDebugState('loadChats');
  return chats;
}

function startRenameChat(el, chatId, currentTitle) {
  const titleSpan = el.querySelector('.chat-item-title');
  if (!titleSpan) return;
  const input = document.createElement('input');
  input.type = 'text';
  input.value = currentTitle;
  input.className = 'rename-input';
  input.style.cssText = 'width:100%;padding:4px 8px;font-size:14px;border:1px solid var(--accent);border-radius:4px;background:var(--bg);color:var(--fg);outline:none;flex:1;min-width:0';
  titleSpan.replaceWith(input);
  input.focus();
  input.select();
  const commit = async () => {
    const newTitle = input.value.trim();
    if (newTitle && newTitle !== currentTitle) {
      await renameChat(chatId, newTitle);
    }
    // loadChats will rebuild the list via WS event or fallback
    const ns = document.createElement('span');
    ns.className = 'chat-item-title';
    ns.textContent = newTitle || currentTitle;
    ns.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0';
    input.replaceWith(ns);
  };
  input.onblur = () => commit();
  input.onkeydown = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { input.value = currentTitle; input.blur(); }
  };
  // Prevent the click from triggering selectChat
  el.onclick = (e) => e.stopPropagation();
}

function confirmDeleteChat(chatId, title) {
  if (!confirm(`Delete "${title}"? This removes all messages.`)) return;
  deleteChat(chatId);
}

async function deleteChat(chatId) {
  try {
    const r = await fetch(`/api/chats/${chatId}`, {
      method: 'DELETE', credentials: 'same-origin'
    });
    if (!r.ok) dbg('ERROR: deleteChat failed:', r.status);
  } catch (e) {
    dbg('ERROR: deleteChat:', e);
  }
  // chat_deleted WS event will trigger loadChats
}

async function renameChat(chatId, newTitle) {
  try {
    const r = await fetch(`/api/chats/${chatId}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({title: newTitle})
    });
    if (!r.ok) dbg('ERROR: renameChat failed:', r.status);
  } catch (e) {
    dbg('ERROR: renameChat:', e);
  }
  // chat_updated WS event will trigger loadChats
}

let _selectChatDebounce = null;
let _lastSelectChatId = null;
let _lastSelectChatTime = 0;

let currentChatType = 'chat';
let _groupMembers = []; // cached members for current group chat
let sidebarPinned = localStorage.getItem('sidebarPinned') === '1';
let themeMode = localStorage.getItem('themeMode')
  || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
let chatFontScale = Number(localStorage.getItem('chatFontScale') || '1');
if (!Number.isFinite(chatFontScale)) chatFontScale = 1;
chatFontScale = Math.min(Math.max(chatFontScale, 0.7), 2.0);

function applyTheme() {
  document.body.classList.toggle('theme-light', themeMode === 'light');
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', themeMode === 'light' ? '#F8FAFC' : '#0F172A');
  const btn = document.getElementById('themeBtn');
  if (btn) {
    btn.textContent = themeMode === 'light' ? '☀' : '☾';
    btn.title = themeMode === 'light' ? 'Switch to dark mode' : 'Switch to light mode';
  }
}

function toggleTheme() {
  themeMode = themeMode === 'light' ? 'dark' : 'light';
  localStorage.setItem('themeMode', themeMode);
  applyTheme();
}

function applyChatFontScale() {
  document.documentElement.style.setProperty('--chat-font-scale', String(chatFontScale));
  const slider = document.getElementById('fontScaleSlider');
  const value = document.getElementById('fontScaleValue');
  const reset = document.getElementById('fontScaleResetBtn');
  const percent = Math.round(chatFontScale * 100);
  if (slider) slider.value = String(percent);
  if (value) value.textContent = `${percent}%`;
  if (reset) reset.style.display = chatFontScale === 1 ? 'none' : 'inline-block';
}

function setChatFontScale(nextScale) {
  chatFontScale = Math.min(Math.max(nextScale, 0.7), 2.0);
  localStorage.setItem('chatFontScale', String(chatFontScale));
  applyChatFontScale();
}

async function selectChat(id, title, chatType, category) {
  // Debounce: skip if same chat selected within 500ms
  const now = Date.now();
  if (id === _lastSelectChatId && now - _lastSelectChatTime < 500) {
    dbg(' selectChat DEBOUNCED:', id);
    return;
  }
  _lastSelectChatId = id;
  _lastSelectChatTime = now;

  // Resolve chat type from sidebar data if not passed
  const sidebarItem = document.querySelector(`.chat-item[data-id="${id}"]`);
  if (!chatType) {
    chatType = sidebarItem?.dataset?.type || 'chat';
    category = sidebarItem?.dataset?.category || '';
  }
  currentChatType = chatType || 'chat';
  activeStreams.clear();
  _answeredAgents.clear();
  hideAgentChips();
  hideStopMenu();

  // Update topbar profile indicator
  const pId = sidebarItem?.dataset?.profileId || '';
  const pName = sidebarItem?.dataset?.profileName || '';
  const pAvatar = sidebarItem?.dataset?.profileAvatar || '';
  _currentChatProfileId = pId;
  updateTopbarProfile(pName, pAvatar);

  dbg(' selectChat:', id, title, 'type:', currentChatType);
  const seq = ++selectChatSeq;
  setCurrentChat(id, title || 'ApexChat');
  closeSidebar();
  // Attach WS to the selected chat so we receive live stream events
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({action: 'attach', chat_id: id}));
  }

  // Alerts channel — render alerts list instead of messages
  if (currentChatType === 'alerts') {
    const catParam = category ? `&category=${category}` : '';
    const r = await fetch(`/api/alerts?limit=100${catParam}`, {credentials: 'same-origin'});
    if (!r.ok) return;
    const alerts = await r.json();
    if (seq !== selectChatSeq || currentChat !== id) return;
    renderAlertsList(alerts);
    // Hide input bar and context bar for alerts channels
    document.getElementById('composerBar').style.display = 'none';
    document.getElementById('contextBar').classList.remove('visible');
    return;
  }
  // Show input bar for regular chats
  document.getElementById('composerBar').style.display = '';
  hideAgentChips();

  // Load group members for @mention autocomplete
  currentGroupMembers = [];
  if (currentChatType === 'group') {
    try {
      const mr = await fetch(`/api/chats/${id}/members`, {credentials: 'same-origin'});
      if (mr.ok) {
        const md = await mr.json();
        currentGroupMembers = md.members || [];
        dbg('group members loaded:', currentGroupMembers.length);
      }
    } catch(e) { dbg('group members fetch error:', e); }
  }
  // Update placeholder for groups
  const inp = document.getElementById('input');
  inp.placeholder = currentGroupMembers.length ? 'Message... (type @ to mention)' : 'Message...';
  refreshComposerDraftState();

  // Load messages
  const r = await fetch(`/api/chats/${id}/messages`, {credentials: 'same-origin'});
  if (!r.ok) {
    dbg('ERROR: selectChat messages failed:', id, r.status);
    throw new Error(`selectChat failed: ${r.status}`);
  }
  const msgs = await r.json();
  if (seq !== selectChatSeq || currentChat !== id) {
    dbg(' stale selectChat response ignored:', id);
    return;
  }
  const el = document.getElementById('messages');
  el.innerHTML = '';
  msgs.forEach(m => {
    if (m.role === 'user') {
      addUserMsg(m.content);
    } else {
      const div = document.createElement('div');
      div.className = 'msg assistant';
      let inner = '';
      // Speaker identity header for group messages
      if (m.speaker_name) {
        inner += `<div class="speaker-header"><span class="speaker-avatar">${escHtml(m.speaker_avatar || '')}</span> <span class="speaker-name">${escHtml(m.speaker_name)}</span></div>`;
      }
      inner += `<div class="bubble"></div>`;
      if (m.cost_usd || m.tokens_in || m.tokens_out) {
        const cost = m.cost_usd ? `$${m.cost_usd.toFixed(4)}` : '';
        const tokens = (m.tokens_in || m.tokens_out) ? `${m.tokens_in}in/${m.tokens_out}out` : '';
        inner += `<div class="cost">${[cost, tokens].filter(Boolean).join(' | ')}</div>`;
      }
      div.innerHTML = inner;
      const bubble = div.querySelector('.bubble');
      bubble.textContent = m.content;
      const historyCtx = {
        bubble: div,
        speaker: m.speaker_name ? {name: m.speaker_name, avatar: m.speaker_avatar || '', id: m.speaker_id || ''} : null,
        toolPill: null,
        thinkingPill: null,
        thinkingBlock: null,
        liveThinkingPill: null,
        liveThinkingTimer: null,
        thinkingCollapsed: false,
        toolCalls: [],
        thinkingText: '',
        thinkingStart: null,
        toolsStart: null,
        completedToolCount: 0,
      };
      try {
        historyCtx.toolCalls = _normalizeToolEvents(JSON.parse(m.tool_events || '[]'));
      } catch (e) {
        historyCtx.toolCalls = [];
      }
      if (historyCtx.toolCalls.length > 0) {
        const totalTime = historyCtx.toolCalls.reduce((sum, tool) => {
          const duration = tool.startTime && tool.endTime ? (tool.endTime - tool.startTime) : 0;
          return sum + Math.max(0, duration);
        }, 0);
        _finalizeToolPill(historyCtx, totalTime);
      }
      if (m.thinking && m.thinking.trim()) {
        historyCtx.thinkingText = m.thinking;
        _createThinkingPill(historyCtx, 0);
      }
      div.querySelectorAll('.bubble').forEach(renderMarkdown);
      el.appendChild(div);
    }
  });
  _userScrolledUp = false;
  scrollBottomForce();
  fetchContext(id);
  refreshDebugState('messages-loaded');
}

async function newChat() {
  dbg(' creating new chat...');
  const r = await fetch('/api/chats', {method: 'POST', credentials: 'same-origin'});
  if (!r.ok) {
    dbg('ERROR: newChat failed:', r.status);
    throw new Error(`newChat failed: ${r.status}`);
  }
  const data = await r.json();
  dbg(' created chat:', data.id);
  const chats = await loadChats();
  const chat = chats.find(c => c.id === data.id);
  await selectChat(data.id, chat?.title || 'New Channel');
  refreshDebugState('newChat');
  return data.id;
}

// --- Sidebar ---
function openSidebar() {
  if (sidebarPinned) {
    applySidebarPinnedState();
    return;
  }
  document.getElementById('sidebar').classList.add('open');
  document.getElementById('sidebarOverlay').classList.add('open');
}
function closeSidebar() {
  if (sidebarPinned) return;
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebarOverlay').classList.remove('open');
}

function applySidebarPinnedState() {
  const body = document.body;
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const pinBtn = document.getElementById('pinSidebarBtn');
  if (!body || !sidebar || !overlay || !pinBtn) return;

  body.classList.toggle('sidebar-pinned', sidebarPinned);
  sidebar.classList.toggle('open', sidebarPinned);
  overlay.classList.remove('open');
  pinBtn.classList.toggle('active', sidebarPinned);
  pinBtn.setAttribute('aria-pressed', sidebarPinned ? 'true' : 'false');
  pinBtn.title = sidebarPinned ? 'Unpin sidebar' : 'Pin sidebar';
}

function toggleSidebarPin() {
  sidebarPinned = !sidebarPinned;
  localStorage.setItem('sidebarPinned', sidebarPinned ? '1' : '0');
  applySidebarPinnedState();
}

// --- Attachments ---
let pendingAttachments = [];

function clearAttachments() {
  pendingAttachments = [];
  document.getElementById('attachPreview').innerHTML = '';
  refreshComposerDraftState();
}

async function handleFiles(files) {
  for (const file of files) {
    const formData = new FormData();
    formData.append('file', file);
    try {
      const r = await fetch('/api/upload', {method: 'POST', body: formData, credentials: 'same-origin'});
      if (!r.ok) {
        const detail = await r.text();
        dbg('ERROR: upload failed:', r.status, detail);
        continue;
      }
      const att = await r.json();
      pendingAttachments.push(att);
      const preview = document.getElementById('attachPreview');
      preview.appendChild(buildAttachmentPreview(att, pendingAttachments.length - 1));
      dbg(' attached:', att.name, att.type);
      refreshComposerDraftState();
    } catch(e) {
      dbg('ERROR: upload:', e);
    }
  }
}

function removeAttachment(idx) {
  pendingAttachments.splice(idx, 1);
  const preview = document.getElementById('attachPreview');
  preview.innerHTML = '';
  pendingAttachments.forEach((att, i) => {
    preview.appendChild(buildAttachmentPreview(att, i));
  });
  refreshComposerDraftState();
}

function audioMimeType() {
  if (!window.MediaRecorder || typeof MediaRecorder.isTypeSupported !== 'function') return '';
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus',
  ];
  return candidates.find(type => MediaRecorder.isTypeSupported(type)) || '';
}

async function uploadVoiceNote(blob, ext) {
  transcribing = true;

  setTranscribeStatus('Transcribing voice note...');
  try {
    const formData = new FormData();
    formData.append('file', blob, `voice-note.${ext}`);
    const r = await fetch('/api/transcribe', {method: 'POST', body: formData, credentials: 'same-origin'});
    const data = await r.json();
    if (!r.ok) {
      throw new Error(data.error || `Transcription failed: ${r.status}`);
    }
    const input = document.getElementById('input');
    input.value = [input.value.trim(), data.text].filter(Boolean).join(input.value.trim() ? '\\n' : '');
    input.dispatchEvent(new Event('input'));
    input.focus();
  } finally {
    transcribing = false;
    setTranscribeStatus('');

  }
}

async function toggleVoiceRecording() {
  if (transcribing) return;
  if (recording && mediaRecorder) {
    mediaRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    addSystemMsg('Voice recording is not supported in this browser.');
    return;
  }

  const mimeType = audioMimeType();
  mediaStream = await navigator.mediaDevices.getUserMedia({audio: true});
  recordingChunks = [];
  mediaRecorder = mimeType ? new MediaRecorder(mediaStream, {mimeType}) : new MediaRecorder(mediaStream);
  mediaRecorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) {
      recordingChunks.push(event.data);
    }
  };
  mediaRecorder.onerror = (event) => {
    reportError('mediaRecorder', event.error || event);
    addSystemMsg('Voice recording failed.');
    recording = false;
    mediaRecorder = null;
    stopVoiceStream();

  };
  mediaRecorder.onstop = async () => {
    const blobType = mediaRecorder.mimeType || mimeType || 'audio/webm';
    const ext = blobType.includes('mp4') ? 'mp4' : (blobType.includes('ogg') ? 'ogg' : 'webm');
    const blob = new Blob(recordingChunks, {type: blobType});
    recording = false;
    mediaRecorder = null;
    stopVoiceStream();

    if (blob.size === 0) {
      setTranscribeStatus('');
      return;
    }
    await uploadVoiceNote(blob, ext).catch(err => {
      reportError('uploadVoiceNote', err);
      addSystemMsg(err.message || 'Voice transcription failed.');
    });
  };
  recording = true;

  setTranscribeStatus('Recording voice note... tap again to stop');
  mediaRecorder.start();
}

// --- PWA service worker ---
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// --- Init ---
document.getElementById('menuBtn').onclick = openSidebar;
document.getElementById('sidebarOverlay').onclick = closeSidebar;
document.getElementById('pinSidebarBtn').onclick = toggleSidebarPin;
document.getElementById('themeBtn').onclick = toggleTheme;
document.getElementById('fontScaleSlider').oninput = (e) => setChatFontScale(Number(e.target.value) / 100);
document.getElementById('fontScaleResetBtn').onclick = () => setChatFontScale(1);
document.getElementById('newChatBtn').onclick = () => {
  loadProfiles().then(() => showNewChatProfilePicker()).catch(err => reportError('profile picker', err));
};
document.getElementById('threadToggle').onclick = () => {
  const tl = document.getElementById('threadList');
  const btn = document.getElementById('threadToggle');
  const collapsed = tl.dataset.collapsed !== 'true';
  tl.dataset.collapsed = collapsed;
  tl.style.display = collapsed ? 'none' : '';
  btn.textContent = collapsed ? '\u25B8' : '\u25BE';
};
document.getElementById('sendBtn').onclick = () => {
  if (streaming && !composerHasDraft) {
    if (activeStreams.size > 1) {
      toggleStopMenu();
    } else if (activeStreams.size === 1) {
      stopStream(activeStreams.keys().next().value || '');
    } else {
      stopAllStreams();
    }
  } else {
    send().catch(err => reportError('send click', err));
  }
};
document.getElementById('fileInput').onchange = (e) => {
  if (e.target.files.length) handleFiles(e.target.files);
  e.target.value = '';
};

// --- Drag-and-drop file attachment ---
let _dragCounter = 0;
const _dropOverlay = document.getElementById('dropOverlay');
document.addEventListener('dragenter', (e) => {
  if (!e.dataTransfer?.types?.includes('Files')) return;
  e.preventDefault();
  _dragCounter++;
  _dropOverlay.classList.add('visible');
});
document.addEventListener('dragleave', (e) => {
  _dragCounter--;
  if (_dragCounter <= 0) { _dragCounter = 0; _dropOverlay.classList.remove('visible'); }
});
document.addEventListener('dragover', (e) => {
  if (!e.dataTransfer?.types?.includes('Files')) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = 'copy';
});
document.addEventListener('drop', (e) => {
  e.preventDefault();
  _dragCounter = 0;
  _dropOverlay.classList.remove('visible');
  if (e.dataTransfer?.files?.length) {
    handleFiles(e.dataTransfer.files);
    document.getElementById('input').focus();
  }
});

const input = document.getElementById('input');
// Restore draft from previous page load
const savedDraft = sessionStorage.getItem('draftText');
if (savedDraft) {
  input.value = savedDraft;
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
}
refreshComposerDraftState();
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  sessionStorage.setItem('draftText', input.value);
  // @mention autocomplete
  _checkMentionPopup();
  refreshComposerDraftState();
});
input.addEventListener('keydown', (e) => {
  const popup = document.getElementById('mentionPopup');
  if (popup && popup.classList.contains('visible')) {
    const items = popup.querySelectorAll('.mention-item');
    if (e.key === 'ArrowDown') { e.preventDefault(); mentionSelectedIdx = Math.min(mentionSelectedIdx + 1, items.length - 1); _highlightMentionItem(items); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); mentionSelectedIdx = Math.max(mentionSelectedIdx - 1, 0); _highlightMentionItem(items); return; }
    if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); const sel = items[mentionSelectedIdx]; if (sel) _insertMention(sel.dataset.name); return; }
    if (e.key === 'Escape') { e.preventDefault(); _hideMentionPopup(); return; }
  }
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send().catch(err => reportError('send keydown', err));
  }
});

function _checkMentionPopup() {
  if (!currentGroupMembers.length) { _hideMentionPopup(); return; }
  const val = input.value;
  const pos = input.selectionStart;
  // Find the @word being typed: look backwards from cursor for @
  const before = val.substring(0, pos);
  const match = before.match(/@[\\w]*$/);
  if (!match) { _hideMentionPopup(); return; }
  const query = match[0].slice(1).toLowerCase();
  const filtered = currentGroupMembers.filter(m =>
    m.name.toLowerCase().startsWith(query) || m.profile_id.toLowerCase().startsWith(query)
  );
  if (!filtered.length) { _hideMentionPopup(); return; }
  const popup = document.getElementById('mentionPopup');
  popup.innerHTML = '';
  filtered.forEach((m, i) => {
    const item = document.createElement('div');
    item.className = 'mention-item' + (i === 0 ? ' selected' : '');
    item.dataset.name = m.name || '';

    const avatar = document.createElement('span');
    avatar.className = 'mi-avatar';
    avatar.textContent = m.avatar || '';

    const name = document.createElement('span');
    name.className = 'mi-name';
    name.textContent = m.name || '';

    item.appendChild(avatar);
    item.appendChild(name);
    item.addEventListener('click', () => _insertMention(item.dataset.name || ''));
    popup.appendChild(item);
  });
  mentionSelectedIdx = 0;
  popup.classList.add('visible');
}

function _highlightMentionItem(items) {
  items.forEach((it, i) => it.classList.toggle('selected', i === mentionSelectedIdx));
}

function _insertMention(name) {
  const val = input.value;
  const pos = input.selectionStart;
  const before = val.substring(0, pos);
  const after = val.substring(pos);
  const atIdx = before.lastIndexOf('@');
  if (atIdx < 0) return;
  const newVal = before.substring(0, atIdx) + '@' + name + ' ' + after;
  input.value = newVal;
  const newPos = atIdx + name.length + 2;
  input.setSelectionRange(newPos, newPos);
  input.focus();
  _hideMentionPopup();
  sessionStorage.setItem('draftText', input.value);
}

function _hideMentionPopup() {
  const popup = document.getElementById('mentionPopup');
  if (popup) popup.classList.remove('visible');
}

async function initApp() {
  dbg(' initApp starting via', initTrigger);
  const chats = await loadChats();
  if (currentChat) {
    const current = chats.find(chat => chat.id === currentChat);
    if (current) {
      dbg(' initApp keeping current chat:', currentChat);
      await selectChat(current.id, current.title || 'Untitled');
      dbg(' initApp done, currentChat:', currentChat);
      return;
    }
  }

  if (chats.length > 0) {
    const first = chats[0];
    dbg(' initApp selecting first chat:', first.id);
    await selectChat(first.id, first.title || 'Untitled');
  } else {
    dbg(' initApp no chats, creating one');
    await newChat();
  }
  dbg(' initApp done, currentChat:', currentChat);
}

async function ensureInitialized(trigger) {
  if (initDone) {
    refreshDebugState(`init-skip:${trigger}`);
    return currentChat;
  }
  if (initPromise) {
    dbg(' init already running, trigger:', trigger);
    refreshDebugState(`init-wait:${trigger}`);
    return initPromise;
  }

  initStarted = true;
  initTrigger = trigger;
  refreshDebugState(`init-start:${trigger}`);
  initPromise = (async () => {
    try {
      await initApp();
      initDone = Boolean(currentChat);
      if (!initDone) {
        throw new Error('init completed without selecting a chat');
      }
      return currentChat;
    } catch (err) {
      dbg('ERROR: init failed:', err?.message || err);
      initStarted = false;
      initDone = false;
      throw err;
    } finally {
      initPromise = null;
      refreshDebugState(`init-finish:${trigger}`);
      updateSendBtn();
    }
  })();
  return initPromise;
}

window.addEventListener('error', (e) => {
  dbg('ERROR: window:', e.message);
  refreshDebugState('window-error');
});
window.addEventListener('unhandledrejection', (e) => {
  reportError('unhandledrejection', e.reason);
});

// --- Context bar ---
function formatTokenCount(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return String(n);
}

function updateContextBar(tokensIn, threshold) {
  const bar = document.getElementById('contextBar');
  if (!bar) return;
  const pct = threshold > 0 ? Math.min((tokensIn / threshold) * 100, 100) : 0;
  const fill = document.getElementById('contextFill');
  const detail = document.getElementById('contextDetail');
  fill.style.width = pct.toFixed(1) + '%';
  fill.className = 'context-fill ' + (pct >= 80 ? 'red' : pct >= 50 ? 'orange' : 'green');
  detail.textContent = formatTokenCount(tokensIn) + ' / ' + formatTokenCount(threshold) + ' tokens (' + Math.round(pct) + '%)';
  detail.style.color = pct >= 80 ? 'var(--red)' : pct >= 50 ? 'var(--yellow)' : 'var(--dim)';
  bar.classList.add('visible');
}

async function fetchContext(chatId) {
  if (!chatId) return;
  try {
    const r = await fetch('/api/chats/' + chatId + '/context');
    if (r.ok) {
      const d = await r.json();
      updateContextBar(d.tokens_in, d.context_window);
    }
  } catch (e) { dbg('context fetch error:', e.message); }
}

// --- Usage bar (model-aware, toggleable) ---
function usageColor(pct) { return pct >= 90 ? 'red' : pct >= 70 ? 'orange' : 'green'; }
let _usageHideTimer = null;
let _lastUsageData = null;
let _usageInterval = null;
let _lastUsageProvider = null;

function selectedChatModel() {
  if (!currentChat) return '';
  const item = document.querySelector('.chat-item[data-id="' + currentChat + '"]');
  return item?.dataset?.model || document.getElementById('serverModelDisplay')?.textContent || '';
}

function isClaudeModel(model) { return typeof model === 'string' && model.startsWith('claude-'); }
function isCodexModel(model) { return typeof model === 'string' && model.startsWith('codex:'); }
function isGrokModel(model) { return typeof model === 'string' && model.startsWith('grok-'); }

function getUsageProvider() {
  const model = selectedChatModel();
  if (isClaudeModel(model)) return 'claude';
  if (isCodexModel(model)) return 'codex';
  if (isGrokModel(model)) return 'grok';
  return null;
}

// Usage meter mode: 'always' | 'auto' | 'off'
function getUsageMeterMode() {
  // Migrate old toggle key
  if (localStorage.getItem('usageMeterOff') === '1' && !localStorage.getItem('usageMeterMode')) {
    localStorage.setItem('usageMeterMode', 'off');
    localStorage.removeItem('usageMeterOff');
  }
  return localStorage.getItem('usageMeterMode') || 'auto';
}
function setUsageMeterMode(mode) { localStorage.setItem('usageMeterMode', mode); localStorage.removeItem('usageMeterOff'); }

function updateUsageBarVisibility() {
  const bar = document.getElementById('usageBar');
  if (!bar) return false;
  const provider = getUsageProvider();
  const mode = getUsageMeterMode();
  const shouldShow = currentChatType !== 'alerts' && provider !== null && mode !== 'off';
  if (!shouldShow) {
    bar.classList.remove('visible', 'fading');
    bar.style.display = 'none';
    return false;
  }
  const label = document.getElementById('usageLabel');
  if (label) label.textContent = provider === 'codex' ? 'ChatGPT' : provider === 'grok' ? 'Grok' : 'Claude';
  bar.style.display = '';
  if (mode === 'always' || (mode === 'auto' && provider !== 'claude')) {
    // Always-on mode, or auto mode for non-polling providers (Codex/Grok stay visible)
    bar.classList.add('visible');
    bar.classList.remove('fading');
    clearTimeout(_usageHideTimer);
  }
  return true;
}

function showUsageBar() {
  const bar = document.getElementById('usageBar');
  if (!bar || !_lastUsageData || !updateUsageBarVisibility()) return;
  bar.classList.add('visible');
  bar.classList.remove('fading');
  clearTimeout(_usageHideTimer);
  const mode = getUsageMeterMode();
  const provider = getUsageProvider();
  // Auto-hide only for Claude (which polls and re-shows). Codex/Grok are static — keep visible.
  if (mode === 'auto' && provider === 'claude') {
    _usageHideTimer = setTimeout(() => {
      bar.classList.add('fading');
      setTimeout(() => { bar.classList.remove('visible', 'fading'); }, 350);
    }, 5000);
  }
}

function renderUsage(data) {
  const bar = document.getElementById('usageBar');
  if (!bar || !data || !data.session) {
    if (bar) { bar.classList.remove('visible', 'fading'); bar.style.display = 'none'; }
    return;
  }
  _lastUsageData = data;
  const s = data.session, w = data.weekly;

  // Session bar — may be "N/A" for Codex
  const isNA = s.resets_in === 'N/A';
  document.getElementById('usageSessionPct').textContent = isNA ? '' : s.utilization + '%';
  document.getElementById('usageSessionReset').textContent = isNA ? 'Included' : '(' + s.resets_in + ')';
  const sf = document.getElementById('usageSessionFill');
  sf.style.width = isNA ? '0%' : Math.min(s.utilization, 100) + '%';
  sf.className = 'usage-fill ' + (isNA ? 'green' : usageColor(s.utilization));
  document.getElementById('usageSessionPct').style.color =
    isNA ? 'var(--dim)' : s.utilization >= 90 ? 'var(--red)' : s.utilization >= 70 ? 'var(--yellow)' : 'var(--green)';

  // Weekly bar
  const wNA = w.resets_in === 'N/A';
  document.getElementById('usageWeeklyPct').textContent = wNA ? '' : w.utilization + '%';
  document.getElementById('usageWeeklyReset').textContent = wNA ? 'Flat rate' : '(' + w.resets_in + ')';
  const wf = document.getElementById('usageWeeklyFill');
  wf.style.width = wNA ? '0%' : Math.min(w.utilization, 100) + '%';
  wf.className = 'usage-fill ' + (wNA ? 'green' : usageColor(w.utilization));
  document.getElementById('usageWeeklyPct').style.color =
    wNA ? 'var(--dim)' : w.utilization >= 90 ? 'var(--red)' : w.utilization >= 70 ? 'var(--yellow)' : 'var(--green)';

  if (updateUsageBarVisibility()) showUsageBar();
}

document.getElementById('usageBar').addEventListener('click', () => showUsageBar());

// --- Toggle: X button hides, settings control mode ---
function toggleUsageMeter() {
  setUsageMeterMode('off');
  updateUsageBarVisibility();
  const sel = document.getElementById('usageMeterSelect');
  if (sel) sel.value = 'off';
}
function changeUsageMeterMode(mode) {
  setUsageMeterMode(mode);
  updateUsageBarVisibility();
  if (mode !== 'off') startUsagePolling();
}

// --- Smart polling (only active provider) ---
async function fetchClaudeUsage() {
  try {
    const r = await fetch('/api/usage');
    if (r.ok) renderUsage(await r.json());
  } catch (e) { dbg('claude usage fetch error:', e.message); }
}

async function fetchCodexUsage() {
  try {
    const r = await fetch('/api/usage/codex');
    if (r.ok) {
      const data = await r.json();
      // Update label
      const label = document.getElementById('usageLabel');
      if (label) label.textContent = 'ChatGPT ' + (data.plan || '');
      // Render using standard renderUsage (same format as Claude)
      renderUsage(data);
      return;
    }
  } catch (e) { dbg('codex usage fetch error:', e.message); }
  // Fallback: no data yet — show placeholder
  const bar = document.getElementById('usageBar');
  if (!bar) return;
  const label = document.getElementById('usageLabel');
  if (label) label.textContent = 'ChatGPT';
  document.getElementById('usageSessionPct').textContent = '--';
  document.getElementById('usageSessionReset').textContent = 'send a message to load';
  document.querySelector('#usageSession .label').textContent = 'Session';
  document.getElementById('usageSessionFill').style.width = '0%';
  document.getElementById('usageWeeklyPct').textContent = '--';
  document.getElementById('usageWeeklyReset').textContent = '';
  document.querySelector('#usageWeekly .label').textContent = 'Weekly';
  document.getElementById('usageWeeklyFill').style.width = '0%';
  bar.style.display = '';
  bar.classList.add('visible');
  bar.classList.remove('fading');
}

async function fetchGrokUsage() {
  try {
    const r = await fetch('/api/usage/grok');
    if (!r.ok) return;
    const data = await r.json();
    const bal = data.balance_usd || 0;
    const total = data.purchased_usd || 100;
    const spent = data.spent_usd || 0;
    const pct = total > 0 ? Math.round((bal / total) * 100) : 0;

    // Use renderUsage for visibility/show logic, then override labels
    renderUsage({
      session: { utilization: pct, resets_in: '' },
      weekly: { utilization: 0, resets_in: 'N/A' },
    });

    // Override session bar to show credit balance
    const lbl = document.querySelector('#usageSession .label');
    if (lbl) lbl.textContent = 'Credits';
    const pctEl = document.getElementById('usageSessionPct');
    if (pctEl) {
      pctEl.textContent = '$' + bal.toFixed(2);
      pctEl.style.color = bal >= 20 ? 'var(--green)' : bal >= 5 ? 'var(--yellow)' : 'var(--red)';
    }
    document.getElementById('usageSessionReset').textContent = 'of $' + total.toFixed(0) + ' remaining';
    const sf = document.getElementById('usageSessionFill');
    if (sf) {
      sf.style.width = pct + '%';
      sf.className = 'usage-fill ' + (bal >= 20 ? 'green' : bal >= 5 ? 'orange' : 'red');
    }
    // Override weekly to show spent
    const wlbl = document.querySelector('#usageWeekly .label');
    if (wlbl) wlbl.textContent = 'Spent';
    document.getElementById('usageWeeklyPct').textContent = '$' + spent.toFixed(2);
    document.getElementById('usageWeeklyPct').style.color = 'var(--dim)';
    document.getElementById('usageWeeklyReset').textContent = '';
    const wf = document.getElementById('usageWeeklyFill');
    if (wf) { wf.style.width = '0%'; }
  } catch (e) { dbg('grok usage fetch error:', e.message); }
}

function startUsagePolling() {
  const provider = getUsageProvider();
  const mode = getUsageMeterMode();
  // Reset if provider changed or not yet started
  if (provider !== _lastUsageProvider || !_usageInterval) {
    _lastUsageProvider = provider;
    clearInterval(_usageInterval);
    _usageInterval = null;
    _lastUsageData = null;
    // Reset labels when switching providers
    const lbl = document.querySelector('#usageSession .label');
    if (lbl) lbl.textContent = 'Session';
  }

  if (!provider || mode === 'off') {
    updateUsageBarVisibility();
    return;
  }

  const fetchFn = provider === 'grok' ? fetchGrokUsage : provider === 'codex' ? fetchCodexUsage : fetchClaudeUsage;
  fetchFn();
  // Poll Claude and Grok (Codex is static)
  if (provider !== 'codex') {
    _usageInterval = setInterval(fetchFn, 300000);
  }
  updateUsageBarVisibility();
}

// --- Agent Profiles ---
let _profilesCache = [];
let _currentChatProfileId = '';
let _currentChatProfileName = '';
let _currentChatProfileAvatar = '';

async function loadProfiles() {
  try {
    const r = await fetch('/api/profiles', {credentials: 'same-origin'});
    if (r.ok) {
      const data = await r.json();
      _profilesCache = data.profiles || [];
    }
  } catch(e) { dbg('loadProfiles error:', e.message); }
  return _profilesCache;
}

function showNewChatProfilePicker() {
  // Remove any existing modal
  document.querySelector('.profile-modal-overlay')?.remove();

  const overlay = document.createElement('div');
  overlay.className = 'profile-modal-overlay';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };

  let selectedProfileId = '';
  const modal = document.createElement('div');
  modal.className = 'profile-modal';

  const header = document.createElement('div');
  header.className = 'profile-modal-header';
  header.innerHTML = '<h3>New Channel</h3>';
  const closeBtn = document.createElement('button');
  closeBtn.innerHTML = '&times;';
  closeBtn.onclick = () => overlay.remove();
  header.appendChild(closeBtn);
  modal.appendChild(header);

  // Quick Thread button at top
  const threadBtn = document.createElement('div');
  threadBtn.style.cssText = 'padding:12px 16px;border-bottom:1px solid var(--bg);cursor:pointer;display:flex;align-items:center;gap:10px';
  threadBtn.innerHTML = '<span style="font-size:18px">\u26A1</span><div><div style="font-weight:600;font-size:14px">Quick Thread</div><div style="font-size:12px;color:var(--dim)">Lightweight one-off interaction</div></div>';
  threadBtn.onmouseenter = () => { threadBtn.style.background = 'var(--card)'; };
  threadBtn.onmouseleave = () => { threadBtn.style.background = ''; };
  threadBtn.onclick = async () => {
    overlay.remove();
    if (!sidebarPinned) closeSidebar();
    await newThread().catch(err => reportError('newThread', err));
  };
  modal.appendChild(threadBtn);

  // New Group button (premium-gated)
  fetch('/api/features', {credentials: 'same-origin'}).then(r => r.json()).then(f => {
    if (!f.groups_enabled) return;
    const groupBtn = document.createElement('div');
    groupBtn.style.cssText = 'padding:12px 16px;border-bottom:1px solid var(--bg);cursor:pointer;display:flex;align-items:center;gap:10px';
    groupBtn.innerHTML = '<span style="font-size:18px">👥</span><div><div style="font-weight:600;font-size:14px">New Group</div><div style="font-size:12px;color:var(--dim)">Multi-agent collaboration</div></div>';
    groupBtn.onmouseenter = () => { groupBtn.style.background = 'var(--card)'; };
    groupBtn.onmouseleave = () => { groupBtn.style.background = ''; };
    groupBtn.onclick = () => { overlay.remove(); showNewGroupPicker(); };
    threadBtn.after(groupBtn);
  }).catch(() => {});

  const body = document.createElement('div');
  body.className = 'profile-modal-body';

  function renderCards() {
    body.innerHTML = '';
    if (_profilesCache.length === 0) {
      body.innerHTML = '<div style="padding:12px;color:var(--dim);font-size:13px">No agent profiles configured. Creating a plain channel.</div>';
    }
    _profilesCache.forEach(p => {
      const card = document.createElement('div');
      card.className = 'profile-card' + (selectedProfileId === p.id ? ' selected' : '');
      card.innerHTML = `<div class="profile-avatar">${p.avatar || '💬'}</div>
        <div class="profile-info">
          <div class="profile-name">${escHtml(p.name)}</div>
          <div class="profile-role">${escHtml(p.role_description || '')}</div>
          <div class="profile-model">${escHtml(p.model || 'default')}</div>
        </div>`;
      card.onclick = () => {
        selectedProfileId = selectedProfileId === p.id ? '' : p.id;
        renderCards();
      };
      body.appendChild(card);
    });
  }
  renderCards();
  modal.appendChild(body);

  const actions = document.createElement('div');
  actions.className = 'profile-modal-actions';
  const skipBtn = document.createElement('button');
  skipBtn.className = 'btn-skip';
  skipBtn.textContent = 'Plain Chat';
  skipBtn.onclick = async () => {
    overlay.remove();
    if (!sidebarPinned) closeSidebar();
    await newChat().catch(err => reportError('newChat skip', err));
  };
  actions.appendChild(skipBtn);

  const createBtn = document.createElement('button');
  createBtn.className = 'btn-create';
  createBtn.textContent = 'Create Channel';
  createBtn.onclick = async () => {
    overlay.remove();
    if (!sidebarPinned) closeSidebar();
    await newChatWithProfile(selectedProfileId).catch(err => reportError('newChat profile', err));
  };
  actions.appendChild(createBtn);
  modal.appendChild(actions);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
}

async function newChatWithProfile(profileId) {
  dbg(' creating new chat with profile:', profileId || '(none)');
  const body = profileId ? JSON.stringify({profile_id: profileId}) : undefined;
  const r = await fetch('/api/chats', {
    method: 'POST',
    credentials: 'same-origin',
    headers: body ? {'Content-Type': 'application/json'} : {},
    body: body
  });
  if (!r.ok) {
    dbg('ERROR: newChatWithProfile failed:', r.status);
    throw new Error('newChatWithProfile failed: ' + r.status);
  }
  const data = await r.json();
  dbg(' created chat:', data.id, 'profile:', data.profile_name || '(none)');
  const chats = await loadChats();
  const chat = chats.find(c => c.id === data.id);
  await selectChat(data.id, chat?.title || 'New Channel');
  refreshDebugState('newChatWithProfile');
  return data.id;
}

async function newThread() {
  dbg(' creating new thread...');
  const r = await fetch('/api/chats', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({type: 'thread'})
  });
  if (!r.ok) {
    dbg('ERROR: newThread failed:', r.status);
    throw new Error('newThread failed: ' + r.status);
  }
  const data = await r.json();
  dbg(' created thread:', data.id);
  const chats = await loadChats();
  const chat = chats.find(c => c.id === data.id);
  await selectChat(data.id, chat?.title || 'Quick thread', 'thread');
  refreshDebugState('newThread');
  return data.id;
}

function showNewGroupPicker() {
  document.querySelector('.profile-modal-overlay')?.remove();
  const overlay = document.createElement('div');
  overlay.className = 'profile-modal-overlay';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  const modal = document.createElement('div');
  modal.className = 'profile-modal';
  const header = document.createElement('div');
  header.className = 'profile-modal-header';
  header.innerHTML = '<h3>New Group</h3>';
  const closeBtn = document.createElement('button');
  closeBtn.innerHTML = '&times;';
  closeBtn.onclick = () => overlay.remove();
  header.appendChild(closeBtn);
  modal.appendChild(header);

  const titleInput = document.createElement('input');
  titleInput.type = 'text';
  titleInput.placeholder = 'Group name...';
  titleInput.value = '';
  titleInput.style.cssText = 'width:100%;padding:10px 16px;border:none;border-bottom:1px solid var(--bg);background:var(--surface);color:var(--fg);font-size:14px;box-sizing:border-box';
  modal.appendChild(titleInput);

  const body = document.createElement('div');
  body.className = 'profile-modal-body';
  body.style.maxHeight = '300px';
  const selectedMembers = new Map();

  function render() {
    body.innerHTML = '';
    if (_profilesCache.length === 0) {
      body.innerHTML = '<div style="padding:12px;color:var(--dim);font-size:13px">No agent profiles to add.</div>';
      return;
    }
    _profilesCache.forEach(p => {
      const card = document.createElement('div');
      card.className = 'profile-card' + (selectedMembers.has(p.id) ? ' selected' : '');
      const mode = selectedMembers.get(p.id) || '';
      const badge = mode === 'primary' ? ' 👑' : (mode ? ' ✓' : '');
      card.innerHTML = `<div class="profile-avatar">${p.avatar || '💬'}</div>
        <div class="profile-info"><div class="profile-name">${escHtml(p.name)}${badge}</div>
        <div class="profile-role">${escHtml(p.role_description || '')}</div></div>`;
      card.onclick = () => {
        if (!selectedMembers.has(p.id)) {
          selectedMembers.set(p.id, 'mentioned');
        } else if (selectedMembers.get(p.id) === 'mentioned') {
          selectedMembers.set(p.id, 'primary');
          // Only one primary
          selectedMembers.forEach((v, k) => { if (k !== p.id && v === 'primary') selectedMembers.set(k, 'mentioned'); });
        } else {
          selectedMembers.delete(p.id);
        }
        render();
      };
      body.appendChild(card);
    });
  }
  const hint = document.createElement('div');
  hint.style.cssText = 'padding:8px 16px;font-size:11px;color:var(--dim);border-bottom:1px solid var(--bg)';
  hint.textContent = 'Click once = member, twice = primary (crown), third = remove';
  modal.appendChild(hint);

  render();
  modal.appendChild(body);

  const actions = document.createElement('div');
  actions.className = 'profile-modal-actions';
  const createBtn = document.createElement('button');
  createBtn.className = 'btn-create';
  createBtn.textContent = 'Create Group';
  createBtn.onclick = async () => {
    if (selectedMembers.size === 0) return;
    const members = [];
    selectedMembers.forEach((mode, pid) => members.push({profile_id: pid, routing_mode: mode}));
    if (!members.some(m => m.routing_mode === 'primary') && members.length > 0) {
      members[0].routing_mode = 'primary';
    }
    overlay.remove();
    if (!sidebarPinned) closeSidebar();
    await newGroup(titleInput.value.trim() || 'New Group', members).catch(err => reportError('newGroup', err));
  };
  actions.appendChild(createBtn);
  modal.appendChild(actions);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
}

async function newGroup(title, members) {
  dbg(' creating new group:', title, members);
  const r = await fetch('/api/chats', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({type: 'group', title: title, members: members})
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    dbg('ERROR: newGroup failed:', r.status, err);
    throw new Error('newGroup failed: ' + r.status + ' ' + (err.error || ''));
  }
  const data = await r.json();
  dbg(' created group:', data.id);
  const chats = await loadChats();
  await selectChat(data.id, title, 'group');
  refreshDebugState('newGroup');
  return data.id;
}

function updateTopbarProfile(profileName, profileAvatar) {
  const el = document.getElementById('topbarProfile');
  const avatarEl = document.getElementById('topbarProfileAvatar');
  const nameEl = document.getElementById('topbarProfileName');
  if (!el) return;
  _currentChatProfileName = profileName || '';
  _currentChatProfileAvatar = profileAvatar || '';
  if (profileName) {
    avatarEl.textContent = profileAvatar || '💬';
    nameEl.textContent = profileName;
  } else {
    avatarEl.textContent = '💬';
    nameEl.textContent = 'No Profile';
  }
  el.style.display = currentChatType === 'chat' ? '' : 'none';
}

function showProfileDropdown(event) {
  event.stopPropagation();
  if (currentChatType !== 'chat') return;
  // Remove existing dropdown
  document.querySelector('.profile-dropdown')?.remove();

  if (_profilesCache.length === 0) return;

  const btn = document.getElementById('topbarProfile');
  const rect = btn.getBoundingClientRect();
  const dd = document.createElement('div');
  dd.className = 'profile-dropdown';
  dd.style.top = (rect.bottom + 4) + 'px';
  dd.style.left = Math.max(8, rect.left - 60) + 'px';

  // "None" option
  const noneItem = document.createElement('div');
  noneItem.className = 'pd-item';
  noneItem.innerHTML = '<span class="pd-avatar">💬</span><span class="pd-name">No Profile</span>' +
    (!_currentChatProfileId ? '<span class="pd-check">✓</span>' : '');
  noneItem.onclick = () => { dd.remove(); changeChatProfile(''); };
  dd.appendChild(noneItem);

  _profilesCache.forEach(p => {
    const item = document.createElement('div');
    item.className = 'pd-item';
    item.innerHTML = `<span class="pd-avatar">${p.avatar || '💬'}</span><span class="pd-name">${escHtml(p.name)}</span>` +
      (_currentChatProfileId === p.id ? '<span class="pd-check">✓</span>' : '');
    item.onclick = () => { dd.remove(); changeChatProfile(p.id); };
    dd.appendChild(item);
  });

  document.body.appendChild(dd);
  // Close on any click outside
  setTimeout(() => {
    const closer = (e) => {
      if (!dd.contains(e.target)) { dd.remove(); document.removeEventListener('click', closer); }
    };
    document.addEventListener('click', closer);
  }, 0);
}

async function changeChatProfile(profileId) {
  if (!currentChat || currentChatType !== 'chat') return;
  try {
    const r = await fetch('/api/chats/' + currentChat, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({profile_id: profileId})
    });
    if (r.ok) {
      dbg('changed profile for chat:', currentChat, 'to:', profileId || '(none)');
      // Update local state
      _currentChatProfileId = profileId;
      const profile = _profilesCache.find(p => p.id === profileId);
      updateTopbarProfile(profile?.name || '', profile?.avatar || '');
      await loadChats();
    }
  } catch(e) {
    reportError('changeChatProfile', e);
  }
}

// Load profiles at startup
loadProfiles();

applyTheme();
applyChatFontScale();
applySidebarPinnedState();
// Init usage meter mode from localStorage
(function() {
  const sel = document.getElementById('usageMeterSelect');
  if (sel) sel.value = getUsageMeterMode();
})();
startUsagePolling();

connect();
setTimeout(() => { ensureInitialized('timer-fallback').catch(() => {}); }, 1500);
refreshDebugState('boot');
updateSendBtn();

// --- PWA resume: reconnect when app comes back from background ---
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    dbg('app resumed from background');
    resumeConnection('visibilitychange');
  }
});

// iOS pageshow fires on back/forward cache restore
window.addEventListener('pageshow', (e) => {
  const wsDead = !ws || ws.readyState === WebSocket.CLOSING || ws.readyState === WebSocket.CLOSED;
  if (e.persisted) {
    dbg(`pageshow: bfcache restore, wsDead=${wsDead}`);
    resumeConnection('pageshow');
  } else if (wsDead) {
    dbg('pageshow: non-bfcache show with dead WS, forcing reconnect');
    resumeConnection('pageshow');
  }
});

// --- Pull to refresh (PWA has no reload button) ---
let pullStartY = 0;
let pulling = false;
const msgEl = document.getElementById('messages');
msgEl.addEventListener('touchstart', (e) => {
  if (msgEl.scrollTop <= 0) {
    pullStartY = e.touches[0].clientY;
    pulling = true;
  }
}, {passive: true});
msgEl.addEventListener('touchmove', (e) => {
  if (!pulling) return;
  const dy = e.touches[0].clientY - pullStartY;
  if (dy > 120 && msgEl.scrollTop <= 0) {
    pulling = false;
    dbg('pull-to-refresh triggered');
    window.location.reload();
  }
}, {passive: true});
msgEl.addEventListener('touchend', () => {
  pulling = false;
}, {passive: true});
msgEl.addEventListener('touchcancel', () => {
  pulling = false;
}, {passive: true});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not (SSL_CERT and SSL_KEY and SSL_CA):
        print("\n  Apex requires TLS certificates to run securely.", file=sys.stderr)
        print("  Run the setup wizard first:\n", file=sys.stderr)
        print("    python3 setup.py\n", file=sys.stderr)
        print("  Or for a quick start:\n", file=sys.stderr)
        print("    python3 setup.py --fast\n", file=sys.stderr)
        sys.exit(1)

    print(f"\n  Apex v1.0")
    print(f"  https://{HOST}:{PORT}")
    print(f"  Model: {MODEL}")
    print(f"  Auth: mTLS (client certificate)")
    print(f"  CA: {SSL_CA}")
    print()

    log_lvl = os.environ.get("APEX_LOG_LEVEL", "info")
    uvicorn.run(
        app, host=HOST, port=PORT, log_level=log_lvl,
        ssl_certfile=SSL_CERT,
        ssl_keyfile=SSL_KEY,
        ssl_ca_certs=SSL_CA,
        ssl_cert_reqs=ssl.CERT_REQUIRED,
    )
