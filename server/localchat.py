#!/usr/bin/env python3
"""LocalChat — Local web chat for Claude Code.

Zero third-party data flow. FastAPI + WebSocket + Claude Agent SDK.
All conversation data stays on this machine. Persistent sessions — no
subprocess respawning per turn. Auth via mTLS (client certificate).

Usage:
    python3 localchat.py
    # or via setup wizard: python3 setup_localchat.py

Env vars:
    LOCALCHAT_SSL_CERT       — server certificate
    LOCALCHAT_SSL_KEY        — server private key
    LOCALCHAT_SSL_CA         — CA cert for client verification (mTLS)
    LOCALCHAT_HOST           — bind address (default: 0.0.0.0)
    LOCALCHAT_PORT           — port (default: 8300)
    LOCALCHAT_MODEL          — Claude model (default: claude-sonnet-4-6)
    LOCALCHAT_WORKSPACE      — working directory for Claude SDK (default: cwd)
    LOCALCHAT_PERMISSION_MODE — SDK permission mode (default: acceptEdits)
    LOCALCHAT_DEBUG          — enable verbose debug logging (default: false)
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import shutil
import ssl
import sqlite3
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import urllib.request

import base64
import contextlib
import tempfile

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
except ImportError:
    print("pip install fastapi uvicorn python-multipart", file=sys.stderr)
    sys.exit(1)

# Local model tool calling
sys.path.insert(0, str(Path.home() / ".openclaw"))
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

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HOST = os.environ.get("LOCALCHAT_HOST", "0.0.0.0")
PORT = int(os.environ.get("LOCALCHAT_PORT", "8300"))
SSL_CERT = os.environ.get("LOCALCHAT_SSL_CERT", "")
SSL_KEY = os.environ.get("LOCALCHAT_SSL_KEY", "")
SSL_CA = os.environ.get("LOCALCHAT_SSL_CA", "")
LOCALCHAT_ROOT = Path(os.environ.get("LOCALCHAT_ROOT", Path(__file__).resolve().parent.parent))
WORKSPACE = Path(os.environ.get("LOCALCHAT_WORKSPACE", os.getcwd()))
MODEL = os.environ.get("LOCALCHAT_MODEL", "claude-sonnet-4-6")
PERMISSION_MODE = os.environ.get("LOCALCHAT_PERMISSION_MODE", "acceptEdits")
DEBUG = os.environ.get("LOCALCHAT_DEBUG", "").lower() in {"1", "true", "yes"}
ALERT_TOKEN = os.environ.get("LOCALCHAT_ALERT_TOKEN", "")
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
DB_PATH = LOCALCHAT_ROOT / "state" / "localchat.db"
LOG_PATH = LOCALCHAT_ROOT / "state" / "localchat.log"
LOG_MAX = 5 * 1024 * 1024  # 5MB
UPLOAD_DIR = LOCALCHAT_ROOT / "state" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_TYPES = {"jpg", "jpeg", "png", "gif", "webp"}
TEXT_TYPES = {"txt", "py", "json", "csv", "md", "yaml", "yml", "toml", "cfg", "ini", "log", "html", "css", "js", "ts", "sh"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_TEXT_SIZE = 1 * 1024 * 1024    # 1MB
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB
WHISPER_BIN = os.environ.get("LOCALCHAT_WHISPER_BIN", shutil.which("whisper") or "whisper")
SDK_QUERY_TIMEOUT = 30
SDK_STREAM_TIMEOUT = 300
ENABLE_SUBCONSCIOUS_WHISPER = os.environ.get("LOCALCHAT_ENABLE_WHISPER", "").lower() in {"1", "true", "yes"}
ENABLE_SKILL_DISPATCH = True  # server-side /recall, /codex, /grok dispatch

# Auto-compaction — rotate SDK session when cumulative input tokens get too high
COMPACTION_THRESHOLD = int(os.environ.get("LOCALCHAT_COMPACTION_THRESHOLD", "100000"))  # input tokens
COMPACTION_OLLAMA_MODEL = os.environ.get("LOCALCHAT_COMPACTION_MODEL", "gemma3:27b")
OLLAMA_BASE_URL = os.environ.get("LOCALCHAT_OLLAMA_URL", "http://localhost:11434")
COMPACTION_OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/generate"
COMPACTION_OLLAMA_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Auto-compaction — session rotation when token usage gets too high
# ---------------------------------------------------------------------------
_compaction_summaries: dict[str, str] = {}  # chat_id -> summary text from last compaction
_last_compacted_at: dict[str, str] = {}  # chat_id -> ISO timestamp of last compaction


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


def _generate_compaction_summary(transcript: str) -> str:
    """Call Ollama to generate a conversation summary for compaction."""
    prompt = (
        "Summarize this conversation in 3-5 bullet points. Focus on:\n"
        "- What the user was working on\n"
        "- Key decisions made\n"
        "- Unfinished tasks or pending items\n"
        "- Any corrections the user gave\n\n"
        "Be concise. This summary will be injected into a fresh AI session "
        "so the assistant can continue seamlessly.\n\n"
        f"Conversation:\n{transcript}"
    )
    payload = json.dumps({
        "model": COMPACTION_OLLAMA_MODEL,
        "stream": False,
        "prompt": prompt,
    }).encode()
    req = urllib.request.Request(
        COMPACTION_OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=COMPACTION_OLLAMA_TIMEOUT)
        body = json.loads(resp.read().decode())
        return body.get("response", "").strip()
    except Exception as e:
        log(f"compaction summary failed: {e}")
        return ""


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
    summary = await asyncio.to_thread(_generate_compaction_summary, transcript)

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

    # Clear the workspace context sent flag so CLAUDE.md gets re-injected
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
# Workspace context injection — CLAUDE.md + MEMORY.md on first message
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


def _get_workspace_context(chat_id: str) -> str:
    """Load CLAUDE.md + MEMORY.md + skills catalog once per session for Claude Code parity.
    Also injects compaction summary if the session was just auto-compacted."""
    if chat_id in _session_context_sent:
        # Even after context was sent, check for compaction summary (one-shot injection)
        summary = _compaction_summaries.pop(chat_id, None)
        if summary:
            log(f"Injecting compaction summary for chat={chat_id}")
            recent = _get_recent_exchange_context(chat_id, pairs=2)
            ctx = (
                f"<system-reminder>\n# Session Continuity (auto-compacted)\n"
                f"This conversation was automatically compacted to save tokens. "
                f"Here is the summary of the prior conversation:\n\n{summary}\n\n"
                f"Continue seamlessly from where the conversation left off.\n</system-reminder>"
            )
            if recent:
                ctx += "\n\n" + recent
            return ctx + "\n\n"
        return ""
    parts: list[str] = []
    # Inject compaction summary if present (first message after compaction + session reset)
    summary = _compaction_summaries.pop(chat_id, None)
    if summary:
        parts.append(
            f"<system-reminder>\n# Session Continuity (auto-compacted)\n"
            f"This conversation was automatically compacted to save tokens. "
            f"Here is the summary of the prior conversation:\n\n{summary}\n\n"
            f"Continue seamlessly from where the conversation left off.\n</system-reminder>"
        )
    claude_md = WORKSPACE / "CLAUDE.md"
    memory_md = WORKSPACE / "memory" / "MEMORY.md"
    skills_dir = WORKSPACE / "skills"
    if claude_md.exists():
        parts.append(f"<system-reminder>\n# CLAUDE.md (project instructions)\n{claude_md.read_text()[:8000]}\n</system-reminder>")
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
    # Inject recent conversation exchanges for continuity
    recent = _get_recent_exchange_context(chat_id, pairs=2)
    if recent:
        parts.append(recent)
    if parts:
        _session_context_sent.add(chat_id)
        log(f"Workspace context injected for chat={chat_id} (CLAUDE.md + MEMORY.md + skills + recent exchanges)")
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
    """Run transcript search and return formatted results."""
    if not args:
        return "Usage: /recall <search query>"
    query = _extract_recall_terms(args)
    script = WORKSPACE / "skills" / "recall" / "search_transcripts.py"
    if not script.exists():
        return "Recall skill not found."
    log(f"Recall search terms: {query!r}")
    t0 = _time.monotonic()
    try:
        result = subprocess.run(
            ["/opt/homebrew/bin/python3", str(script), query, "--top", "8", "--context", "800"],
            capture_output=True, text=True, timeout=15, cwd=str(WORKSPACE),
        )
        elapsed = _time.monotonic() - t0
        output = result.stdout.strip()
        if result.returncode != 0:
            _log_skill_invocation("recall", success=False, duration_sec=elapsed, error=result.stderr.strip()[:200], context=query[:80], source="localchat")
            return f"Recall error: {result.stderr.strip()}"
        success = bool(output) and "No results" not in output
        _log_skill_invocation("recall", success=success, duration_sec=elapsed, context=query[:80], source="localchat")
        return output or f"No results found for: {args}"
    except subprocess.TimeoutExpired:
        _log_skill_invocation("recall", success=False, duration_sec=15.0, error="timeout", context=query[:80], source="localchat")
        return "Recall timed out."
    except Exception as e:
        _log_skill_invocation("recall", success=False, duration_sec=_time.monotonic() - t0, error=str(e)[:200], context=query[:80], source="localchat")
        return f"Recall error: {e}"


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
            ["/opt/homebrew/bin/python3", str(analyze_script), skill_name,
             "--workspace", str(WORKSPACE), "--days", "30"],
            capture_output=True, text=True, timeout=30, cwd=str(WORKSPACE),
        )
        elapsed = _time.monotonic() - t0
        output = result.stdout.strip()
        if result.returncode != 0:
            _log_skill_invocation("skill-improver", success=False, duration_sec=elapsed,
                                  error=result.stderr.strip()[:200], context=skill_name, source="localchat")
            return f"Analysis error: {result.stderr.strip()}"
        _log_skill_invocation("skill-improver", success=True, duration_sec=elapsed,
                              context=skill_name, source="localchat")
        return output
    except subprocess.TimeoutExpired:
        _log_skill_invocation("skill-improver", success=False, duration_sec=30.0,
                              error="timeout", context=skill_name, source="localchat")
        return "Skill analysis timed out."
    except Exception as e:
        _log_skill_invocation("skill-improver", success=False,
                              duration_sec=_time.monotonic() - t0, error=str(e)[:200],
                              context=skill_name, source="localchat")
        return f"Analysis error: {e}"


def _run_codex_background(args: str, chat_id: str) -> str:
    """Launch codex as a background task. Returns status message."""
    if not args:
        return "Usage: /codex <prompt for codex>"
    prompt_file = WORKSPACE / f"codex_localchat_{chat_id[:8]}.md"
    response_file = WORKSPACE / f"codex_localchat_{chat_id[:8]}_response.md"
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
        _log_skill_invocation("codex", success=True, context=args[:80], source="localchat")
        return f"Codex task launched in background.\nPrompt: `{prompt_file.name}`\nResponse will be at: `{response_file.name}`\n\nI'll check the response when it's ready. You can also ask me to check with: \"check codex response\""
    except Exception as e:
        _log_skill_invocation("codex", success=False, error=str(e)[:200], context=args[:80], source="localchat")
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

    prompt_file = WORKSPACE / f"grok_localchat_{chat_id[:8]}.md"
    response_file = WORKSPACE / f"grok_localchat_{chat_id[:8]}_response.md"
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
        _log_skill_invocation("grok", success=True, context=args[:80], source="localchat")
        return {
            "status": f"Grok research launched in background{flags_str}...",
            "bg_proc": proc,
            "bg_response_file": str(response_file),
        }
    except Exception as e:
        _log_skill_invocation("grok", success=False, error=str(e)[:200], context=args[:80], source="localchat")
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
        _log_skill_invocation("gate", success=True, context=f"approved:{result.get('skill','?')}", source="localchat")
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
        _log_skill_invocation("gate", success=True, context=f"rejected:{result.get('skill','?')}", source="localchat")
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

    # Push result into the chat as a new assistant message
    _save_message(chat_id, "assistant", label, cost_usd=0, tokens_in=0, tokens_out=0)
    await _send_stream_event(chat_id, {"type": "stream_start", "chat_id": chat_id})
    await _send_stream_event(chat_id, {"type": "text", "text": label})
    await _send_stream_event(chat_id, {
        "type": "result", "cost_usd": 0, "tokens_in": 0, "tokens_out": 0, "session_id": None,
    })
    await _send_stream_event(chat_id, {"type": "stream_end", "chat_id": chat_id})
    log(f"BG skill complete: /{skill_name} chat={chat_id} len={len(label)}")


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


WHISPER_INTERVAL = 300  # seconds between whisper injections (5 min)
_whisper_last: dict[str, float] = {}  # chat_id -> last whisper timestamp

def _get_whisper_text(chat_id: str) -> str:
    """Run subconscious whisper and return text to prepend, or empty string."""
    now = time.time()
    last = _whisper_last.get(chat_id, 0)
    if last and (now - last) < WHISPER_INTERVAL:
        return ""
    try:
        sys.path.insert(0, str(WORKSPACE / "scripts"))
        from subconscious.whisper import _filtered_items, _hash_items, _render_full, _render_diff
        from subconscious.state import get_session as _sc_get_session, update_session as _sc_update_session
        from subconscious.config import ensure_dirs

        ensure_dirs()
        sc_session_id = f"localchat-{chat_id}"
        current_items = _filtered_items()
        current_hash = _hash_items(current_items)

        session = _sc_get_session(sc_session_id) or {}
        previous_hash = str(session.get("last_whisper_hash", "") or "")
        previous_items = session.get("last_whisper_items")
        previous_items = previous_items if isinstance(previous_items, list) else None

        lines: list[str] = []
        if not previous_hash or previous_items is None:
            lines = _render_full(current_items)
        elif previous_hash != current_hash:
            lines = _render_diff(previous_items, current_items)

        _sc_update_session(
            sc_session_id,
            last_prompt_at=datetime.now(timezone.utc).isoformat(),
            last_whisper_hash=current_hash,
            last_whisper_items=current_items,
        )
        _whisper_last[chat_id] = now
        if lines:
            log(f"Whisper injected for chat={chat_id} ({len(lines)} lines)")
            return "\n".join(lines) + "\n\n"
        return ""
    except Exception as e:
        log(f"Whisper error: {e}")
        return ""


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_log_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(f"[localchat {datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)
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
    conn.commit()
    conn.close()


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
    workspace_ctx = _get_workspace_context(chat_id)
    whisper = _get_whisper_text(chat_id) if ENABLE_SUBCONSCIOUS_WHISPER else ""
    prefix = f"{workspace_ctx}{whisper}".strip()
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
        return True
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

def _create_chat(title: str = "New Chat", model: str | None = None, chat_type: str = "chat",
                  category: str | None = None) -> str:
    cid = str(uuid.uuid4())[:8]
    now = _now()
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT INTO chats (id, title, model, type, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cid, title, model, chat_type, category, now, now),
        )
        conn.commit()
        conn.close()
    return cid


def _get_chats() -> list[dict]:
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT id, title, claude_session_id, created_at, updated_at, model, type, category FROM chats ORDER BY updated_at DESC"
        ).fetchall()
        conn.close()
    return [{"id": r[0], "title": r[1], "claude_session_id": r[2],
             "created_at": r[3], "updated_at": r[4], "model": r[5], "type": r[6], "category": r[7] or None} for r in rows]


def _get_chat(chat_id: str) -> dict | None:
    with _db_lock:
        conn = _get_db()
        row = conn.execute("SELECT id, title, claude_session_id, created_at, updated_at, model, type, category FROM chats WHERE id = ?",
                           (chat_id,)).fetchone()
        conn.close()
    if not row:
        return None
    return {"id": row[0], "title": row[1], "claude_session_id": row[2],
            "created_at": row[3], "updated_at": row[4], "model": row[5], "type": row[6], "category": row[7] or None}


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


def _save_message(chat_id: str, role: str, content: str, tool_events: str = "[]",
                  thinking: str = "", cost_usd: float = 0, tokens_in: int = 0,
                  tokens_out: int = 0) -> str:
    mid = str(uuid.uuid4())[:12]
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, tool_events, thinking, cost_usd, tokens_in, tokens_out, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, chat_id, role, content, tool_events, thinking, cost_usd, tokens_in, tokens_out, _now()))
        conn.commit()
        conn.close()
    return mid


def _get_messages(chat_id: str, days: int | None = None) -> list[dict]:
    with _db_lock:
        conn = _get_db()
        if days and days > 0:
            rows = conn.execute(
                "SELECT id, role, content, tool_events, thinking, cost_usd, tokens_in, tokens_out, created_at FROM messages WHERE chat_id = ? AND created_at >= datetime('now', ?) ORDER BY created_at",
                (chat_id, f"-{days} days")).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, role, content, tool_events, thinking, cost_usd, tokens_in, tokens_out, created_at FROM messages WHERE chat_id = ? ORDER BY created_at",
                (chat_id,)).fetchall()
        conn.close()
    return [{"id": r[0], "role": r[1], "content": r[2], "tool_events": r[3],
             "thinking": r[4], "cost_usd": r[5], "tokens_in": r[6],
             "tokens_out": r[7], "created_at": r[8]} for r in rows]


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


GUARDRAIL_WHITELIST = LOCALCHAT_ROOT / "state" / "guardrail_whitelist.json"


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
_active_send_tasks: dict[str, asyncio.Task] = {}  # chat_id -> running send task (for stop/cancel)


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


_stream_buffers: dict[str, deque[tuple[int, dict]]] = {}
_stream_seq: dict[str, int] = {}
_chat_send_locks: dict[str, asyncio.Lock] = {}
_STREAM_BUFFER_MAX = 200
ALERT_CATEGORY_MAP = {
    "plan_h": "trading",
    "plan_c": "trading",
    "plan_h_backstop": "trading",
    "plan_m": "trading",
    "plan_alpha": "trading",
    "regime": "trading",
    "guardrail": "system",
    "watchdog": "system",
    "system": "system",
    "test": "test",
}


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


async def _get_or_create_client(chat_id: str, model: str | None = None) -> ClaudeSDKClient:
    """Get existing persistent client or create a new one."""
    if chat_id in _clients:
        client = _clients[chat_id]
        if _client_is_alive(client):
            return client
        # Stale client — clean up before creating a new one
        log(f"stale SDK client detected: chat={chat_id}, evicting")
        await _disconnect_client(chat_id)

    chat = _get_chat(chat_id)
    session_id = chat.get("claude_session_id") if chat else None
    options = _make_options(model=model, session_id=session_id)

    effective_model = model or MODEL
    log(f"creating SDK client: chat={chat_id} model={effective_model} resume={session_id or 'new'}")
    client = ClaudeSDKClient(options)
    await asyncio.wait_for(client.connect(), timeout=SDK_QUERY_TIMEOUT)
    _clients[chat_id] = client
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
                await _send({
                    "type": "result",
                    "is_error": msg.is_error,
                    "cost_usd": result_info["cost_usd"],
                    "tokens_in": result_info["tokens_in"],
                    "tokens_out": result_info["tokens_out"],
                    "session_id": msg.session_id,
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
    log(f"LocalChat starting on {HOST}:{PORT} [mTLS]")
    try:
        yield
    finally:
        for chat_id in list(_clients):
            await _disconnect_client(chat_id)


app = FastAPI(title="LocalChat", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.middleware("http")
async def verify_client_cert(request: Request, call_next):
    """Verify client cert on HTTP requests. Bearer token accepted for /api/alerts."""
    path = request.url.path
    # Bearer token auth for alert creation (POST /api/alerts only)
    if path == "/api/alerts" and request.method == "POST" and ALERT_TOKEN:
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {ALERT_TOKEN}":
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return await call_next(request)


# --- Auth routes ---

# --- API routes ---

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
    CATEGORY_TITLES = {"trading": "Trading Alerts", "system": "System Alerts", "test": "Test Alerts"}
    if chat_type == "alerts":
        title = CATEGORY_TITLES.get(category, "All Alerts")
    else:
        title = "New Chat"
    cid = _create_chat(title=title, model=model, chat_type=chat_type, category=category)
    return JSONResponse({"id": cid, "model": model, "type": chat_type, "category": category})


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


@app.get("/api/chats/{chat_id}/messages")
async def api_messages(chat_id: str, request: Request, days: int | None = 3):
    return JSONResponse(_get_messages(chat_id, days=days))


@app.get("/health")
async def health():
    return JSONResponse({"ok": True, "clients": len(_clients), "chats": len(_get_chats())})


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
    log(f"alert: id={alert['id']} src={source} sev={severity} title={title[:50]}")
    return JSONResponse(alert, status_code=201)


@app.get("/api/alerts")
async def api_get_alerts(since: str | None = None, unacked: bool = False, category: str | None = None):
    return JSONResponse(_get_alerts(since=since, unacked_only=unacked, category=category))


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
    if model.startswith("claude-"):
        return "claude"
    elif model.startswith("grok-"):
        return "xai"
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


@app.get("/api/models/local")
async def api_local_models():
    models = await asyncio.to_thread(_get_ollama_models)
    return JSONResponse(models)


async def _run_ollama_chat(chat_id: str, prompt: str, model: str | None = None) -> dict:
    """Run a chat response from Ollama/xAI with tool-calling support."""
    effective_model = model or MODEL
    # Build message history from recent DB messages
    recent = _get_messages(chat_id, days=1)
    if _TOOL_LOOP_AVAILABLE:
        sys_prompt = build_system_prompt(effective_model)
    else:
        sys_prompt = f"You are {effective_model}, a local AI model running via Ollama. Be helpful and concise."
    messages = [{"role": "system", "content": sys_prompt}]
    for m in recent[-20:]:
        content = m["content"]
        if "<system-reminder>" in content:
            continue
        messages.append({"role": m["role"], "content": content})
    messages.append({"role": "user", "content": prompt})

    # Use tool loop if available
    if _TOOL_LOOP_AVAILABLE:
        async def emit(event: dict):
            await _send_stream_event(chat_id, event)

        # Route to xAI or Ollama based on model backend
        if _get_model_backend(effective_model) == "xai":
            result = await run_tool_loop(
                ollama_url=OLLAMA_BASE_URL,
                model=effective_model,
                messages=messages,
                emit_event=emit,
                workspace=str(WORKSPACE),
                api_key=XAI_API_KEY,
                api_url="https://api.x.ai/v1",
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
        await _send_stream_event(chat_id, {
            "type": "result", "is_error": result.get("is_error", False),
            "cost_usd": 0, "tokens_in": 0, "tokens_out": 0,
            "session_id": None,
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
                content = chunk.get("message", {}).get("content", "")
                if content:
                    chunk_queue.put_nowait(content)
        except Exception as e:
            chunk_queue.put_nowait(f"__ERROR__:{e}")
        finally:
            chunk_queue.put_nowait(None)

    asyncio.get_event_loop().run_in_executor(None, _stream_ollama)
    result_text, is_error, error_msg = "", False, ""
    while True:
        chunk = await chunk_queue.get()
        if chunk is None:
            break
        if chunk.startswith("__ERROR__:"):
            error_msg = chunk[10:]
            is_error = True
            log(f"ollama error: {error_msg}")
            await _send_stream_event(chat_id, {"type": "error", "message": f"Ollama: {error_msg}"})
            break
        result_text += chunk
        await _send_stream_event(chat_id, {"type": "text", "text": chunk})

    await _send_stream_event(chat_id, {
        "type": "result", "is_error": is_error,
        "cost_usd": 0, "tokens_in": 0, "tokens_out": 0, "session_id": None,
    })
    return {"text": result_text, "is_error": is_error, "error": error_msg or None,
            "cost_usd": 0, "tokens_in": 0, "tokens_out": 0,
            "session_id": None, "thinking": "", "tool_events": "[]"}


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
                "User-Agent": "localchat/1.0",
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
    with tempfile.TemporaryDirectory(prefix="localchat-whisper-") as tmp_dir:
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
                    lock = _chat_locks.get(attach_id)
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
                                replay_ok = await _safe_ws_send_json(
                                    websocket,
                                    {"type": "stream_reattached", "chat_id": attach_id},
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
                _update_chat(chat_id, model=model)
                # Disconnect only this chat's SDK client if it exists
                if chat_id in _clients:
                    await _disconnect_client(chat_id)
                await websocket.send_json({
                    "type": "chat_updated", "chat_id": chat_id,
                    "title": (_get_chat(chat_id) or {}).get("title", ""),
                    "model": model,
                })
                continue

            if action == "send":
                send_chat_id = data.get("chat_id", "")
                task = asyncio.create_task(_handle_send_action(websocket, data))
                if send_chat_id:
                    _active_send_tasks[send_chat_id] = task
                    task.add_done_callback(
                        lambda t, cid=send_chat_id: _active_send_tasks.pop(cid, None)
                        if _active_send_tasks.get(cid) is t else None
                    )
                _track_task(task)

            elif action == "stop":
                chat_id = data.get("chat_id", "")
                if chat_id:
                    if chat_id in _clients:
                        # Claude SDK — interrupt triggers graceful stream end
                        try:
                            await _clients[chat_id].interrupt()
                        except Exception:
                            pass
                    else:
                        # Local/xAI model — cancel the send task directly
                        send_task = _active_send_tasks.pop(chat_id, None)
                        if send_task and not send_task.done():
                            send_task.cancel()
                            await _send_stream_event(chat_id, {"type": "stream_end", "chat_id": chat_id})

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
                    await _safe_ws_send_json(websocket, {"type": "stream_start", "chat_id": chat_id}, chat_id=chat_id)
                    await _safe_ws_send_json(websocket, {"type": "stream_delta", "chat_id": chat_id, "delta": reply}, chat_id=chat_id)
                    await _safe_ws_send_json(websocket, {"type": "stream_end", "chat_id": chat_id}, chat_id=chat_id)
                    _log_skill_invocation("gate", success=True, context=f"{decision}:{result.get('skill','?')}", source="localchat")
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
                    _log_skill_invocation(skill, success=True, context=(skill_args or "")[:80], source="localchat")
            elif skill in _DIRECT_SKILL_HANDLERS:
                handled = await _handle_skill(websocket, chat_id, skill, skill_args, prompt)
                if handled:
                    return

    chat = _get_chat(chat_id)
    if not chat:
        await _safe_ws_send_json(websocket, {"type": "error", "message": "Chat not found"}, chat_id=chat_id)
        return

    # Per-chat model routing — fallback to global MODEL
    chat_model = chat.get("model") or MODEL
    backend = _get_model_backend(chat_model)

    chat_lock = _get_chat_lock(chat_id)
    try:
        await asyncio.wait_for(chat_lock.acquire(), timeout=0.05)
    except asyncio.TimeoutError:
        await _safe_ws_send_json(
            websocket,
            {"type": "error", "message": "This chat is already processing a message"},
            chat_id=chat_id,
        )
        return

    try:
        # Inject recall context if /recall was used
        user_visible_prompt = prompt
        if _recall_context:
            prompt = f"{_recall_context}{prompt}"

        display_prompt = prompt
        make_query_input = None
        if backend in ("ollama", "xai"):
            # Local/xAI models use raw prompt — no SDK payload needed
            display_prompt = user_visible_prompt if _recall_context else prompt
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

        if chat["title"] == "New Chat":
            title_source = prompt or display_prompt
            title = title_source[:50] + ("..." if len(title_source) > 50 else "")
            _update_chat(chat_id, title=title)
            await _safe_ws_send_json(
                websocket, {"type": "chat_updated", "chat_id": chat_id, "title": title, "model": chat_model}, chat_id=chat_id
            )

        # Register this WS in the registry so the stream can find it
        original_ws = websocket
        _attach_ws(websocket, chat_id)
        _reset_stream_buffer(chat_id)
        await _send_stream_event(chat_id, {"type": "stream_start", "chat_id": chat_id})

        result: dict | None = None

        # --- Local model / xAI path (Ollama or xAI API) ---
        if backend in ("ollama", "xai"):
            try:
                result = await _run_ollama_chat(chat_id, prompt, model=chat_model)
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
                client = await _get_or_create_client(chat_id, model=chat_model)
                result = await _run_query_turn(client, make_query_input, chat_id)
            except Exception as first_error:
                if DEBUG: log(f"DBG RECOVERY: chat={chat_id} first error: {type(first_error).__name__}: {first_error}")
                await _disconnect_client(chat_id)

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
                    _clients[chat_id] = client
                    result = await _run_query_turn(client, _make_retry_input, chat_id)
                    if DEBUG: log(f"DBG RECOVERY: resume OK chat={chat_id} session={existing_session or 'new'}")
                except Exception as resume_error:
                    if DEBUG: log(f"DBG RECOVERY: resume FAILED: {type(resume_error).__name__}: {resume_error}")
                    await _disconnect_client(chat_id)
                    _update_chat(chat_id, claude_session_id=None)
                    if DEBUG: log(f"DBG RECOVERY: session_id NUKED, trying fresh...")
                    try:
                        options = _make_options(model=chat_model, session_id=None)
                        client = ClaudeSDKClient(options)
                        await asyncio.wait_for(client.connect(), timeout=SDK_QUERY_TIMEOUT)
                        _clients[chat_id] = client
                        result = await _run_query_turn(client, _make_retry_input, chat_id)
                        if DEBUG: log(f"DBG RECOVERY: fresh session OK chat={chat_id}")
                    except Exception as fresh_error:
                        if DEBUG: log(f"DBG RECOVERY: fresh ALSO FAILED: {type(fresh_error).__name__}: {fresh_error}")
                        await _disconnect_client(chat_id)
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
                    {"type": "stream_complete_reload", "chat_id": chat_id},
                    chat_id=chat_id,
                )
    finally:
        chat_lock.release()
        # Send stream_end to ALL connected viewers — also add to buffer for replay
        end_event = {"type": "stream_end", "chat_id": chat_id}
        buf = _stream_buffers.get(chat_id)
        if buf is not None:
            seq = _stream_seq.get(chat_id, 0) + 1
            end_event["seq"] = seq
            buf.append(end_event)
        ws_set = _chat_ws.get(chat_id, set())
        for ws in list(ws_set):
            await _safe_ws_send_json(ws, end_event, chat_id=chat_id)
        log(f"stream_end sent: chat={chat_id} viewers={len(ws_set)}")
        _stream_buffers.pop(chat_id, None)
        _stream_seq.pop(chat_id, None)


# --- Main page ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    html = CHAT_HTML.replace("{{MODE_CLASS}}", "mtls").replace("{{MODE_LABEL}}", "mTLS")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


# --- PWA endpoints ---

@app.get("/manifest.json")
async def manifest():
    return JSONResponse({
        "name": "LocalChat",
        "short_name": "LocalChat",
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
<meta name="apple-mobile-web-app-title" content="LocalChat">
<meta name="theme-color" content="#0F172A">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/icon.svg">
<title>LocalChat</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0F172A;--surface:#1E293B;--card:#334155;--text:#F1F5F9;--dim:#94A3B8;
--accent:#0EA5E9;--green:#10B981;--red:#EF4444;--yellow:#F59E0B;
--sat:env(safe-area-inset-top);--sab:env(safe-area-inset-bottom)}
body{background:var(--bg);color:var(--text);font-family:-apple-system,system-ui,sans-serif;
height:100dvh;display:flex;flex-direction:column;overflow:hidden}

/* Top bar */
.topbar{background:var(--surface);padding:12px 16px;padding-top:calc(12px + var(--sat));
display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--card);min-height:52px;flex-shrink:0}
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
.messages{flex:1;overflow-y:auto;padding:12px 16px;-webkit-overflow-scrolling:touch}
.msg{margin-bottom:12px;max-width:85%;-webkit-user-select:text;user-select:text}
.msg.user{margin-left:auto;background:var(--accent);color:white;padding:10px 14px;
border-radius:16px 16px 4px 16px;font-size:15px;line-height:1.4;word-break:break-word}
.msg.assistant{margin-right:auto}
.msg.assistant .bubble{background:var(--surface);padding:10px 14px;
border-radius:16px 16px 16px 4px;font-size:15px;line-height:1.5;word-break:break-word}
.msg.assistant .bubble code{background:var(--card);padding:1px 4px;border-radius:3px;font-size:13px}
.msg.assistant .bubble pre{background:var(--bg);padding:10px;border-radius:6px;overflow-x:auto;
margin:8px 0;font-size:13px;line-height:1.4}
.msg.assistant .bubble pre code{background:none;padding:0}
.msg.assistant .bubble h2,.msg.assistant .bubble h3,.msg.assistant .bubble h4{line-height:1.3;margin:10px 0 6px}
.msg.assistant .bubble p + p,.msg.assistant .bubble p + ul,.msg.assistant .bubble p + ol,
.msg.assistant .bubble ul + p,.msg.assistant .bubble ol + p,.msg.assistant .bubble pre + p{margin-top:8px}
.msg.assistant .bubble ul,.msg.assistant .bubble ol{padding-left:20px;margin:8px 0}
.msg.assistant .bubble li + li{margin-top:4px}

/* Thinking blocks */
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

/* Tool blocks */
.tool-block{background:var(--bg);border-left:3px solid var(--accent);border-radius:6px;
margin-bottom:6px;overflow:hidden}
.tool-header{padding:8px 12px;font-size:12px;color:var(--accent);cursor:pointer;
display:flex;align-items:center;gap:6px;user-select:none}
.tool-summary{font-size:12px;color:var(--dim);padding:4px 12px 6px;line-height:1.4}
.tool-summary code{background:var(--surface);padding:1px 4px;border-radius:3px;font-size:11px}
.tool-body{padding:0 12px 8px 12px;font-size:12px;color:var(--dim);
line-height:1.4;display:none}
.tool-block.open .tool-body{display:block}
.tool-block.open .tool-header .arrow{transform:rotate(90deg)}
.tool-header .arrow{transition:transform 0.2s}
.tool-status{margin-left:auto;font-size:14px}
.tool-body pre{background:var(--surface);padding:8px;border-radius:4px;overflow-x:auto;
font-size:11px;margin:4px 0;max-height:200px;overflow-y:auto}

/* Cost footer */
.cost{font-size:11px;color:var(--dim);margin-top:4px;padding-left:4px}

/* Streaming indicator */
.streaming .bubble::after{content:'';display:inline-block;width:6px;height:14px;
background:var(--accent);margin-left:2px;animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}

/* Composer */
.composer{background:var(--surface);padding:8px 12px;padding-bottom:calc(8px + var(--sab));
border-top:1px solid var(--card);display:flex;align-items:flex-end;gap:8px;flex-shrink:0}
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
.btn-compose{min-width:44px;min-height:44px;border-radius:50%;border:none;
background:var(--card);color:var(--dim);font-size:18px;cursor:pointer;flex-shrink:0;
display:flex;align-items:center;justify-content:center}
.composer label.btn-compose{position:relative;display:flex;align-items:center;justify-content:center}
.btn-compose:active{background:var(--accent);color:white}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
.attach-preview{display:flex;gap:6px;padding:0 12px;overflow-x:auto;flex-shrink:0}
.attach-preview:empty{display:none}
.attach-item{background:var(--card);border-radius:8px;padding:4px 8px;display:flex;align-items:center;
gap:4px;font-size:12px;color:var(--dim);flex-shrink:0;max-width:150px}
.attach-item img{width:32px;height:32px;object-fit:cover;border-radius:4px}
.attach-item .remove{cursor:pointer;color:var(--red);font-size:14px;margin-left:4px}
.transcribing{color:var(--yellow);font-size:12px;padding:4px 12px}

/* History sidebar */
.sidebar{position:fixed;top:0;left:0;width:min(300px,80vw);height:100dvh;background:var(--surface);
z-index:100;transform:translateX(-100%);transition:transform 0.2s;padding-top:var(--sat);overflow-y:auto}
.sidebar.open{transform:translateX(0)}
.sidebar-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:99;display:none}
.sidebar-overlay.open{display:block}
.sidebar h2{padding:16px;font-size:16px;border-bottom:1px solid var(--card)}
.sidebar .chat-item{padding:12px 16px;border-bottom:1px solid var(--bg);cursor:pointer;
font-size:14px;color:var(--dim);min-height:44px;display:flex;align-items:center}
.sidebar .chat-item:active{background:var(--card)}
.sidebar .chat-item.active{color:var(--accent);font-weight:600}
.sidebar .new-btn{padding:12px 16px;color:var(--accent);cursor:pointer;font-size:14px;
font-weight:600;border-bottom:1px solid var(--bg);min-height:44px;display:flex;align-items:center}

/* Usage bar */
.usage-bar{background:var(--surface);padding:4px 16px 6px;border-bottom:1px solid var(--card);
display:none;gap:12px;flex-shrink:0;cursor:pointer;
transition:opacity 0.3s ease,max-height 0.3s ease;overflow:hidden;max-height:60px}
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
.usage-fill.green{background:var(--green)}
.usage-fill.orange{background:var(--yellow)}
.usage-fill.red{background:var(--red)}

/* Debug bar */
.debugbar{background:#111827;border-top:1px solid #233047;padding:6px 12px;flex-shrink:0}
.debug-state{color:#93C5FD;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
font-size:11px;white-space:pre-wrap}
.debug-log{color:#A7F3D0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;
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
.alerts-panel{position:fixed;top:40px;right:8px;width:380px;max-height:70vh;
background:#1a1a2e;border:1px solid #333;border-radius:12px;z-index:9998;
overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.5);display:none}
.alerts-panel.show{display:block}
.alerts-panel-header{display:flex;align-items:center;justify-content:space-between;
padding:10px 14px;border-bottom:1px solid #333;font-size:13px;font-weight:600;color:#ccc}
.alerts-panel-header button{background:transparent;border:none;color:#888;
font-size:11px;cursor:pointer}
.alerts-panel-header button:hover{color:#fff}
.alert-item{padding:10px 14px;border-bottom:1px solid #222;font-size:12px;
display:flex;align-items:flex-start;gap:8px}
.alert-item.acked{opacity:.4}
.alert-item .ai-icon{font-size:14px;flex-shrink:0;margin-top:1px}
.alert-item .ai-body{flex:1;min-width:0}
.alert-item .ai-source{font-size:9px;font-weight:700;text-transform:uppercase;
letter-spacing:.5px;color:#888}
.alert-item .ai-title{font-weight:600;color:#e5e5e5;margin-top:1px}
.alert-item .ai-time{font-size:10px;color:#666;margin-top:2px}
.alert-item .ai-actions{display:flex;gap:4px;flex-shrink:0}
.alert-item .ai-actions button{font-size:10px;padding:3px 8px;border-radius:5px;
border:none;cursor:pointer;font-weight:600}
.alert-detail-overlay{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.6);
display:flex;align-items:center;justify-content:center;padding:20px}
.alert-detail-card{background:#1a1a2e;border-radius:16px;max-width:500px;width:100%;
max-height:80vh;overflow-y:auto;box-shadow:0 12px 40px rgba(0,0,0,.5)}
.alert-detail-card .ad-header{display:flex;align-items:center;gap:10px;padding:16px 20px;
border-bottom:1px solid #333}
.alert-detail-card .ad-icon{font-size:28px}
.alert-detail-card .ad-source{font-size:10px;font-weight:700;text-transform:uppercase;
letter-spacing:.5px;padding:3px 8px;border-radius:10px;display:inline-block}
.alert-detail-card .ad-time{font-size:11px;color:#888;margin-top:4px}
.alert-detail-card .ad-close{margin-left:auto;background:none;border:none;color:#888;
font-size:20px;cursor:pointer;padding:4px 8px}
.alert-detail-card .ad-close:hover{color:#fff}
.alert-detail-card .ad-section{padding:12px 20px;border-bottom:1px solid #222}
.alert-detail-card .ad-label{font-size:10px;font-weight:600;color:#888;
text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.alert-detail-card .ad-title{font-size:16px;font-weight:600;color:#e5e5e5}
.alert-detail-card .ad-body{font-size:13px;color:#bbb;white-space:pre-wrap;
font-family:ui-monospace,SFMono-Regular,Menlo,monospace;line-height:1.5}
.alert-detail-card .ad-meta-key{font-size:10px;font-weight:600;color:#888;
text-transform:uppercase}
.alert-detail-card .ad-meta-val{font-size:12px;color:#ccc;
font-family:ui-monospace,monospace;word-break:break-all}
.alert-detail-card .ad-actions{display:flex;gap:8px;padding:16px 20px}
.alert-detail-card .ad-actions button{flex:1;padding:8px;border-radius:8px;border:none;
font-weight:600;font-size:13px;cursor:pointer}
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
  <h1 id="chatTitle">LocalChat</h1>
  <span class="status ok" id="statusDot"></span>
  <span class="mode-badge {{MODE_CLASS}}" id="modeBadge">{{MODE_LABEL}}</span>
  <span class="alert-badge" id="alertBadge" onclick="toggleAlertsPanel()" title="Alerts">&#128276;<span class="count" id="alertCount"></span></span>
  <button class="btn-icon" id="refreshBtn" title="Refresh" onclick="window.location.reload()">&#8635;</button>
</div>
<div class="alerts-panel" id="alertsPanel">
  <div class="alerts-panel-header">
    <span>Alerts</span>
    <button onclick="clearAllAlerts()">Clear All</button>
  </div>
  <div id="alertsList"></div>
</div>

<div class="usage-bar" id="usageBar">
  <span class="usage-label">Claude</span>
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
</div>

<div class="sidebar" id="sidebar">
  <h2>Chats</h2>
  <div class="new-btn" id="newChatBtn">+ New Chat</div>
  <div id="chatList"></div>
</div>
<div class="sidebar-overlay" id="sidebarOverlay"></div>

<div class="messages" id="messages"></div>

<div class="debugbar" id="debugBar" style="display:none">
  <div class="debug-state" id="debugState">booting</div>
  <div class="debug-log" id="debugLog"></div>
</div>

<div id="attachPreview" class="attach-preview"></div>
<div id="transcribeStatus" class="transcribing" style="display:none"></div>
<div class="composer" id="composerBar">
  <label class="btn-compose" id="attachBtn" title="Attach file" style="cursor:pointer">
    &#128206;
    <input type="file" id="fileInput" style="position:absolute;width:0;height:0;overflow:hidden;opacity:0" multiple accept="image/*,.txt,.py,.json,.csv,.md,.yaml,.yml,.toml,.sh,.js,.ts,.html,.css">
  </label>
  <textarea id="input" rows="1" placeholder="Message Claude..." autocomplete="off"></textarea>
  <button class="btn-compose" id="sendBtn" title="Send">&#9654;</button>
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
  // Check if any tool block is still pending (hourglass icon = no result yet)
  if (!currentBubble) return false;
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
  // Use longer timeout when a tool is actively running (Codex, Grok can take minutes)
  const timeout = hasActiveTool() ? 300000 : 30000;  // 5 min for tools, 30s otherwise
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
  document.getElementById('chatTitle').textContent = title || 'LocalChat';
  setActiveChatUI();
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

function handleEvent(msg) {
  const el = document.getElementById('messages');
  switch(msg.type) {
    case 'stream_start':
      streaming = true;
      currentBubble = null;
      sessionStorage.setItem('streamingChatId', msg.chat_id || currentChat || '');
      markStreamActivity('stream-start');
      updateSendBtn();
  
      refreshDebugState('stream-start');
      break;

    case 'text':
      if (!currentBubble) {
        currentBubble = addAssistantMsg();
      }
      const bubble = currentBubble.querySelector('.bubble');
      bubble.textContent += msg.text;
      markStreamActivity('text');
      scrollBottom();
      break;

    case 'thinking':
      if (!currentBubble) currentBubble = addAssistantMsg();
      let tb = currentBubble.querySelector('.thinking-block:last-of-type');
      if (!tb || tb.classList.contains('closed')) {
        tb = document.createElement('div');
        tb.className = 'thinking-block open';
        tb.innerHTML = `<div class="thinking-header" onclick="this.parentElement.classList.toggle(&quot;open&quot;)"><span class="arrow">&#9656;</span> &#129504; Thinking...</div><div class="thinking-body"></div>`;
        currentBubble.insertBefore(tb, currentBubble.querySelector('.bubble'));
      }
      tb.querySelector('.thinking-body').textContent += msg.text;
      tb.querySelector('.thinking-body').scrollTop = tb.querySelector('.thinking-body').scrollHeight;
      markStreamActivity('thinking');
      scrollBottom();
      break;

    case 'tool_use': {
      if (!currentBubble) currentBubble = addAssistantMsg();
      const toolBlock = document.createElement('div');
      toolBlock.className = 'tool-block';
      toolBlock.id = 'tool-' + msg.id;
      const inputStr = typeof msg.input === 'string' ? msg.input : JSON.stringify(msg.input, null, 2);
      const summary = toolSummary(msg.name, msg.input);
      const summaryHtml = summary ? `<div class="tool-summary">${summary}</div>` : '';
      toolBlock.innerHTML = `<div class="tool-header" onclick="this.parentElement.classList.toggle(&quot;open&quot;)"><span class="arrow">&#9656;</span> ${toolIcon(msg.name)} ${escHtml(toolLabel(msg.name))}<span class="tool-status">&#9203;</span></div>${summaryHtml}<div class="tool-body"><b>Input:</b><pre>${escHtml(inputStr)}</pre><div class="tool-result-area"></div></div>`;
      currentBubble.insertBefore(toolBlock, currentBubble.querySelector('.bubble'));
      markStreamActivity('tool-use');
      scrollBottom();
      break;
    }

    case 'tool_result': {
      const tb2 = document.getElementById('tool-' + msg.tool_use_id);
      if (tb2) {
        const area = tb2.querySelector('.tool-result-area');
        const content = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content);
        area.innerHTML = `<b>Result:</b><pre>${escHtml(content.substring(0, 2000))}</pre>`;
        const icon = tb2.querySelector('.tool-status');
        icon.textContent = msg.is_error ? '\u2717' : '\u2713';
        icon.style.color = msg.is_error ? 'var(--red)' : 'var(--green)';
        // Update summary with result info
        const summaryEl = tb2.querySelector('.tool-summary');
        const toolName = tb2.querySelector('.tool-header')?.textContent?.trim();
        const origName = Object.keys(TOOL_META).find(k => toolLabel(k) === toolName?.replace(/[^a-zA-Z ]/g, '').trim()) || '';
        const resultNote = toolResultSummary(origName, content);
        if (resultNote && summaryEl) {
          summaryEl.innerHTML += ` — ${escHtml(resultNote)}`;
        }
      }
      markStreamActivity('tool-result');
      scrollBottom();
      break;
    }

    case 'result':
      if (currentBubble) {
        // Collapse thinking blocks and update label
        currentBubble.querySelectorAll('.thinking-block.open').forEach(tb => {
          tb.classList.remove('open');
          const hdr = tb.querySelector('.thinking-header');
          if (hdr) hdr.innerHTML = hdr.innerHTML.replace('Thinking...', 'Thinking');
        });
        const costEl = document.createElement('div');
        costEl.className = 'cost';
        const cost = msg.cost_usd ? `$${msg.cost_usd.toFixed(4)}` : '';
        const tokens = msg.tokens_in || msg.tokens_out ? ` | ${msg.tokens_in}in/${msg.tokens_out}out` : '';
        costEl.textContent = cost + tokens;
        currentBubble.appendChild(costEl);
        currentBubble.classList.remove('streaming');
        renderMarkdown(currentBubble.querySelector('.bubble'));
      }
      markStreamActivity('result');
      fetchUsage();
      refreshDebugState('result');
      break;

    case 'stream_end':
      streaming = false;
      currentBubble = null;
      sessionStorage.removeItem('streamingChatId');
      clearStreamWatchdog();
      updateSendBtn();
  
      refreshDebugState('stream-end');
      break;

    case 'stream_reattached':
      // Server confirmed we re-attached to an active stream after replaying
      // the buffered events that were missed while the socket was down.
      dbg('stream re-attached for chat:', msg.chat_id);
      streaming = true;
      sessionStorage.setItem('streamingChatId', msg.chat_id || currentChat || '');
      markStreamActivity('stream-reattached');
      updateSendBtn();
  
      refreshDebugState('stream-reattached');
      break;

    case 'attach_ok':
      // Server confirmed no active stream — safe to reload from DB.
      // This fires when the client thought a stream might be running
      // (sessionStorage had streamingChatId) but it already finished.
      dbg('attach ok, no active stream for chat:', msg.chat_id);
      sessionStorage.removeItem('streamingChatId');
      streaming = false;
      currentBubble = null;
      clearStreamWatchdog();
      updateSendBtn();

      // Skip reload if we already have messages loaded for this chat
      // (prevents request storm on reconnect/refresh)
      if (msg.chat_id && msg.chat_id === currentChat && !document.getElementById('messages').hasChildNodes()) {
        selectChat(msg.chat_id).catch(() => {});
      }
      refreshDebugState('attach-ok');
      break;

    case 'stream_complete_reload':
      // Stream finished while we were disconnected. Reload from DB.
      dbg('stream completed while disconnected, reloading chat:', msg.chat_id);
      streaming = false;
      currentBubble = null;
      sessionStorage.removeItem('streamingChatId');
      clearStreamWatchdog();
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
        scrollBottom();
      }
      break;

    case 'chat_updated':
      if (currentChat === msg.chat_id) {
        document.getElementById('chatTitle').textContent = msg.title;
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
      addSystemMsg(msg.message || 'Unknown error');
      streaming = false;
      clearStreamWatchdog();
      sessionStorage.removeItem('streamingChatId');
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
  div.innerHTML = '<div class="bubble"></div>';
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
  scrollBottom();
}

function addSystemMsg(text) {
  const el = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg assistant';
  div.innerHTML = `<div class="bubble" style="color:var(--red)">${escHtml(text)}</div>`;
  el.appendChild(div);
  scrollBottom();
}

function scrollBottom() {
  const el = document.getElementById('messages');
  el.scrollTop = el.scrollHeight;
}

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
  actions += `<button style="background:#333;color:#ccc" onclick="navigator.clipboard.writeText(${JSON.stringify(a.body||'')})">Copy</button>`;
  const overlay = document.createElement('div');
  overlay.className = 'alert-detail-overlay';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  overlay.innerHTML = `<div class="alert-detail-card">
    <div class="ad-header">
      <span class="ad-icon">${icon}</span>
      <div>
        <span class="ad-source" style="background:${color}22;color:${color}">${escHtml((a.source||'').toUpperCase())}</span>
        <div class="ad-time">${ago}${a.acked ? ' \u2014 \u2713 Acknowledged' : ''}</div>
      </div>
      <button class="ad-close" onclick="this.closest('.alert-detail-overlay').remove()">\u2715</button>
    </div>
    <div class="ad-section"><div class="ad-label">Title</div><div class="ad-title">${escHtml(a.title)}</div></div>
    ${a.body ? `<div class="ad-section"><div class="ad-label">Details</div><div class="ad-body">${escHtml(a.body)}</div></div>` : ''}
    ${metaHtml}
    <div class="ad-actions">${actions}</div>
  </div>`;
  document.body.appendChild(overlay);
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
    const icon = sevIcons[a.severity] || '\u2139\ufe0f';
    const color = sevColors[a.severity] || '#0891b2';
    let actions = '';
    if (!a.acked) {
      if (a.source === 'guardrail') {
        actions += `<button style="background:#16a34a;color:#fff" onclick="panelAlertAction('allow','${a.id}')">Allow</button>`;
      }
      actions += `<button style="background:${color};color:#fff" onclick="panelAlertAction('ack','${a.id}')">Ack</button>`;
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
  d.textContent = s;
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
  if (streaming) {
    btn.innerHTML = '&#9632;';
    btn.className = 'stop';
    btn.disabled = false;
    btn.title = 'Stop';
  } else {
    btn.innerHTML = '&#9654;';
    btn.className = '';
    btn.disabled = !currentChat || !ws || ws.readyState !== WebSocket.OPEN;
    btn.title = btn.disabled ? 'Waiting for chat initialization' : 'Send';
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
async function send() {
  const input = document.getElementById('input');
  const text = input.value.trim();
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
  if (streaming) { dbg(' already streaming'); return; }
  if (!ws || ws.readyState !== WebSocket.OPEN) { dbg('ERROR: ws not open'); return; }
  const attachmentSummary = pendingAttachments.length ? `Attachments: ${pendingAttachments.map(att => att.name).join(', ')}` : '';
  addUserMsg([text, attachmentSummary].filter(Boolean).join('\\n') || '(attachment)');
  const msg = {action: 'send', chat_id: currentChat, prompt: text};
  if (pendingAttachments.length > 0) {
    msg.attachments = pendingAttachments.map(a => ({id: a.id, type: a.type, name: a.name}));
  }
  ws.send(JSON.stringify(msg));
  input.value = '';
  sessionStorage.removeItem('draftText');
  input.style.height = 'auto';
  clearAttachments();
  refreshDebugState('send');
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
  const list = document.getElementById('chatList');
  list.innerHTML = '';
  chats.forEach(c => {
    const d = document.createElement('div');
    d.className = 'chat-item' + (c.id === currentChat ? ' active' : '');
    d.textContent = c.title || 'Untitled';
    d.dataset.id = c.id;
    d.dataset.title = c.title || 'Untitled';
    d.dataset.type = c.type || 'chat';
    d.dataset.category = c.category || '';
    d.onclick = () => selectChat(c.id, c.title, c.type, c.category).catch(err => reportError('selectChat click', err));
    d.ondblclick = (e) => { e.stopPropagation(); startRenameChat(d, c.id, c.title || 'Untitled'); };
    d.oncontextmenu = (e) => { e.preventDefault(); e.stopPropagation(); confirmDeleteChat(c.id, c.title || 'Untitled'); };
    list.appendChild(d);
  });
  setActiveChatUI();
  refreshDebugState('loadChats');
  return chats;
}

function startRenameChat(el, chatId, currentTitle) {
  const input = document.createElement('input');
  input.type = 'text';
  input.value = currentTitle;
  input.className = 'rename-input';
  input.style.cssText = 'width:100%;padding:4px 8px;font-size:14px;border:1px solid var(--accent);border-radius:4px;background:var(--bg);color:var(--fg);outline:none;';
  el.textContent = '';
  el.appendChild(input);
  input.focus();
  input.select();
  const commit = async () => {
    const newTitle = input.value.trim();
    if (newTitle && newTitle !== currentTitle) {
      await renameChat(chatId, newTitle);
    } else {
      el.textContent = currentTitle;
    }
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
  if (!chatType) {
    const item = document.querySelector(`.chat-item[data-id="${id}"]`);
    chatType = item?.dataset?.type || 'chat';
    category = item?.dataset?.category || '';
  }
  currentChatType = chatType || 'chat';

  dbg(' selectChat:', id, title, 'type:', currentChatType);
  const seq = ++selectChatSeq;
  setCurrentChat(id, title || 'LocalChat');
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
    // Hide input bar for alerts channels
    document.getElementById('composerBar').style.display = 'none';
    return;
  }
  // Show input bar for regular chats
  document.getElementById('composerBar').style.display = '';

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
      if (m.thinking) {
        inner += `<div class="thinking-block"><div class="thinking-header" onclick="this.parentElement.classList.toggle(&quot;open&quot;)"><span class="arrow">&#9656;</span> &#129504; Thinking</div><div class="thinking-body">${escHtml(m.thinking)}</div></div>`;
      }
      try {
        const tools = JSON.parse(m.tool_events || '[]');
        tools.forEach(t => {
          const inputStr = typeof t.input === 'string' ? t.input : JSON.stringify(t.input, null, 2);
          const resultStr = t.result ? (typeof t.result.content === 'string' ? t.result.content : JSON.stringify(t.result.content)) : '';
          const icon = t.result && t.result.is_error ? '\u2717' : '\u2713';
          const color = t.result && t.result.is_error ? 'var(--red)' : 'var(--green)';
          const summary = toolSummary(t.name, t.input);
          const resultNote = toolResultSummary(t.name, resultStr);
          const summaryParts = [summary, resultNote ? escHtml(resultNote) : null].filter(Boolean).join(' — ');
          const summaryHtml = summaryParts ? `<div class="tool-summary">${summaryParts}</div>` : '';
          inner += `<div class="tool-block"><div class="tool-header" onclick="this.parentElement.classList.toggle(&quot;open&quot;)"><span class="arrow">&#9656;</span> ${toolIcon(t.name)} ${escHtml(toolLabel(t.name))}<span class="tool-status" style="color:${color}">${icon}</span></div>${summaryHtml}<div class="tool-body"><b>Input:</b><pre>${escHtml(inputStr)}</pre><b>Result:</b><pre>${escHtml(resultStr.substring(0, 2000))}</pre></div></div>`;
        });
      } catch(e) {}
      inner += `<div class="bubble"></div>`;
      if (m.cost_usd || m.tokens_in || m.tokens_out) {
        const cost = m.cost_usd ? `$${m.cost_usd.toFixed(4)}` : '';
        const tokens = (m.tokens_in || m.tokens_out) ? `${m.tokens_in}in/${m.tokens_out}out` : '';
        inner += `<div class="cost">${[cost, tokens].filter(Boolean).join(' | ')}</div>`;
      }
      div.innerHTML = inner;
      const bubble = div.querySelector('.bubble');
      bubble.textContent = m.content;
      div.querySelectorAll('.bubble').forEach(renderMarkdown);
      el.appendChild(div);
    }
  });
  scrollBottom();
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
  await selectChat(data.id, chat?.title || 'New Chat');
  refreshDebugState('newChat');
  return data.id;
}

// --- Sidebar ---
function openSidebar() {
  document.getElementById('sidebar').classList.add('open');
  document.getElementById('sidebarOverlay').classList.add('open');
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebarOverlay').classList.remove('open');
}

// --- Attachments ---
let pendingAttachments = [];

function clearAttachments() {
  pendingAttachments = [];
  document.getElementById('attachPreview').innerHTML = '';
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
document.getElementById('newChatBtn').onclick = () => { closeSidebar(); newChat().catch(err => reportError('newChat click', err)); };
document.getElementById('sendBtn').onclick = () => {
  if (streaming) {
    ws.send(JSON.stringify({action: 'stop', chat_id: currentChat}));
  } else {
    send().catch(err => reportError('send click', err));
  }
};
document.getElementById('fileInput').onchange = (e) => {
  if (e.target.files.length) handleFiles(e.target.files);
  e.target.value = '';
};
const input = document.getElementById('input');
// Restore draft from previous page load
const savedDraft = sessionStorage.getItem('draftText');
if (savedDraft) {
  input.value = savedDraft;
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
}
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  sessionStorage.setItem('draftText', input.value);
});
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send().catch(err => reportError('send keydown', err));
  }
});

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

// --- Usage bar ---
function usageColor(pct) { return pct >= 90 ? 'red' : pct >= 70 ? 'orange' : 'green'; }
let _usageHideTimer = null;
let _lastUsageData = null;

function showUsageBar() {
  const bar = document.getElementById('usageBar');
  if (!bar || !_lastUsageData) return;
  bar.classList.add('visible');
  bar.classList.remove('fading');
  clearTimeout(_usageHideTimer);
  _usageHideTimer = setTimeout(() => {
    bar.classList.add('fading');
    setTimeout(() => { bar.classList.remove('visible', 'fading'); }, 350);
  }, 5000);
}

function renderUsage(data) {
  const bar = document.getElementById('usageBar');
  if (!bar || !data || !data.session) { if (bar) bar.classList.remove('visible'); return; }
  _lastUsageData = data;
  const s = data.session, w = data.weekly;
  document.getElementById('usageSessionPct').textContent = s.utilization + '%';
  document.getElementById('usageSessionReset').textContent = '(' + s.resets_in + ')';
  const sf = document.getElementById('usageSessionFill');
  sf.style.width = Math.min(s.utilization, 100) + '%';
  sf.className = 'usage-fill ' + usageColor(s.utilization);
  document.getElementById('usageSessionPct').style.color =
    s.utilization >= 90 ? 'var(--red)' : s.utilization >= 70 ? 'var(--yellow)' : 'var(--green)';

  document.getElementById('usageWeeklyPct').textContent = w.utilization + '%';
  document.getElementById('usageWeeklyReset').textContent = '(' + w.resets_in + ')';
  const wf = document.getElementById('usageWeeklyFill');
  wf.style.width = Math.min(w.utilization, 100) + '%';
  wf.className = 'usage-fill ' + usageColor(w.utilization);
  document.getElementById('usageWeeklyPct').style.color =
    w.utilization >= 90 ? 'var(--red)' : w.utilization >= 70 ? 'var(--yellow)' : 'var(--green)';
  showUsageBar();
}

document.getElementById('usageBar').addEventListener('click', () => showUsageBar());

async function fetchUsage() {
  try {
    const r = await fetch('/api/usage');
    if (r.ok) renderUsage(await r.json());
  } catch (e) { dbg('usage fetch error:', e.message); }
}

fetchUsage();
setInterval(fetchUsage, 300000);

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
        print("ERROR: mTLS requires LOCALCHAT_SSL_CERT, LOCALCHAT_SSL_KEY, and LOCALCHAT_SSL_CA", file=sys.stderr)
        print("Usage: ./scripts/launch_localchat.sh", file=sys.stderr)
        sys.exit(1)

    print(f"\n  LocalChat v1.0")
    print(f"  https://{HOST}:{PORT}")
    print(f"  Model: {MODEL}")
    print(f"  Auth: mTLS (client certificate)")
    print(f"  CA: {SSL_CA}")
    print()

    log_lvl = os.environ.get("LOCALCHAT_LOG_LEVEL", "info")
    uvicorn.run(
        app, host=HOST, port=PORT, log_level=log_lvl,
        ssl_certfile=SSL_CERT,
        ssl_keyfile=SSL_KEY,
        ssl_ca_certs=SSL_CA,
        ssl_cert_reqs=ssl.CERT_OPTIONAL,
    )
