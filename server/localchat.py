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

# ---------------------------------------------------------------------------
# Subconscious whisper — inject guidance from background memory system
# Throttled: first message per chat + every WHISPER_INTERVAL seconds after.
# ---------------------------------------------------------------------------
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
        DROP TABLE IF EXISTS web_sessions;
    """)
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
    whisper = _get_whisper_text(chat_id) if ENABLE_SUBCONSCIOUS_WHISPER else ""
    final_prompt = query_prompt or ("What do you see?" if image_blocks else "")
    if whisper:
        final_prompt = f"{whisper}{final_prompt}".strip() if final_prompt else whisper.strip()

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

def _create_chat(title: str = "New Chat") -> str:
    cid = str(uuid.uuid4())[:8]
    now = _now()
    with _db_lock:
        conn = _get_db()
        conn.execute("INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                     (cid, title, now, now))
        conn.commit()
        conn.close()
    return cid


def _get_chats() -> list[dict]:
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT id, title, claude_session_id, created_at, updated_at FROM chats ORDER BY updated_at DESC"
        ).fetchall()
        conn.close()
    return [{"id": r[0], "title": r[1], "claude_session_id": r[2],
             "created_at": r[3], "updated_at": r[4]} for r in rows]


def _get_chat(chat_id: str) -> dict | None:
    with _db_lock:
        conn = _get_db()
        row = conn.execute("SELECT id, title, claude_session_id, created_at, updated_at FROM chats WHERE id = ?",
                           (chat_id,)).fetchone()
        conn.close()
    if not row:
        return None
    return {"id": row[0], "title": row[1], "claude_session_id": row[2],
            "created_at": row[3], "updated_at": row[4]}


def _update_chat(chat_id: str, **kwargs) -> None:
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [_now(), chat_id]
    with _db_lock:
        conn = _get_db()
        conn.execute(f"UPDATE chats SET {sets}, updated_at = ? WHERE id = ?", vals)
        conn.commit()
        conn.close()


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


def _get_messages(chat_id: str) -> list[dict]:
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT id, role, content, tool_events, thinking, cost_usd, tokens_in, tokens_out, created_at FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,)).fetchall()
        conn.close()
    return [{"id": r[0], "role": r[1], "content": r[2], "tool_events": r[3],
             "thinking": r[4], "cost_usd": r[5], "tokens_in": r[6],
             "tokens_out": r[7], "created_at": r[8]} for r in rows]


# ---------------------------------------------------------------------------
# Claude Agent SDK — persistent sessions, no subprocess respawning
# ---------------------------------------------------------------------------
_clients: dict[str, ClaudeSDKClient] = {}
_chat_locks: dict[str, asyncio.Lock] = {}
_chat_ws: dict[str, WebSocket] = {}  # chat_id -> current WebSocket (for stream re-attach)
_stream_buffers: dict[str, deque[tuple[int, dict]]] = {}
_stream_seq: dict[str, int] = {}
_chat_send_locks: dict[str, asyncio.Lock] = {}
_STREAM_BUFFER_MAX = 200


def _make_options(session_id: str | None = None) -> ClaudeAgentOptions:
    """Build SDK options for a new or resumed session."""
    return ClaudeAgentOptions(
        model=MODEL,
        cwd=str(WORKSPACE),
        permission_mode=PERMISSION_MODE,
        max_turns=50,
        resume=session_id,
        setting_sources=["user"],  # loads ~/.claude/settings.json hooks
    )


async def _get_or_create_client(chat_id: str) -> ClaudeSDKClient:
    """Get existing persistent client or create a new one."""
    if chat_id in _clients:
        return _clients[chat_id]

    chat = _get_chat(chat_id)
    session_id = chat.get("claude_session_id") if chat else None
    options = _make_options(session_id)

    log(f"creating SDK client: chat={chat_id} model={MODEL} resume={session_id or 'new'}")
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
        ws = _chat_ws.get(chat_id)
        if not ws:
            return
        ok = await _safe_ws_send_json(ws, payload, chat_id=chat_id)
        if not ok and _chat_ws.get(chat_id) is ws:
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
    """Verify client cert on HTTP requests. WebSocket bypasses this (same TLS session)."""
    if SSL_CA:
        # Check if the TLS transport has a peercert
        transport = request.scope.get("transport")
        peercert = None
        if transport and hasattr(transport, "get_extra_info"):
            peercert = transport.get_extra_info("peercert")
        if not peercert:
            # Try via the ASGI scope extensions
            tls = request.scope.get("extensions", {}).get("tls", {})
            peercert = tls.get("peercert") if tls else None
        # With CERT_OPTIONAL, no peercert means no client cert was sent
        # Allow anyway — the browser may send it for some requests and not others
        # The TLS layer still protects against non-CA-signed certs
    return await call_next(request)


# --- Auth routes ---

# --- API routes ---

@app.get("/api/chats")
async def api_chats(request: Request):
    return JSONResponse(_get_chats())


@app.post("/api/chats")
async def api_new_chat(request: Request):
    cid = _create_chat()
    return JSONResponse({"id": cid})


@app.get("/api/chats/{chat_id}/messages")
async def api_messages(chat_id: str, request: Request):
    return JSONResponse(_get_messages(chat_id))


@app.get("/health")
async def health():
    return JSONResponse({"ok": True, "clients": len(_clients), "chats": len(_get_chats())})


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
                                _chat_ws[attach_id] = websocket
                                replay_ok = await _safe_ws_send_json(
                                    websocket,
                                    {"type": "stream_reattached", "chat_id": attach_id},
                                    chat_id=attach_id,
                                )
                            if not replay_ok and _chat_ws.get(attach_id) is websocket:
                                _chat_ws.pop(attach_id, None)
                        if replay_ok:
                            log(f"WS re-attached for chat={attach_id} (stream active, replayed={replayed})")
                    else:
                        _chat_ws[attach_id] = websocket
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

            if action == "send":
                task = asyncio.create_task(_handle_send_action(websocket, data))
                _track_task(task)

            elif action == "stop":
                chat_id = data.get("chat_id", "")
                if chat_id and chat_id in _clients:
                    try:
                        await _clients[chat_id].interrupt()
                    except Exception:
                        pass

    except WebSocketDisconnect as wd:
        log(f"websocket disconnected ws={ws_id} code={wd.code if hasattr(wd, 'code') else '?'}")
    except Exception as e:
        log(f"websocket error ws={ws_id}: {type(e).__name__}: {e}")
    finally:
        if active_tasks:
            log(f"websocket cleanup ws={ws_id}: {len(active_tasks)} send task(s) continue in background")


async def _handle_send_action(websocket: WebSocket, data: dict) -> None:
    chat_id = data.get("chat_id", "")
    prompt = str(data.get("prompt", "")).strip()
    attachments = data.get("attachments", [])
    if not (prompt or attachments) or not chat_id:
        return

    chat = _get_chat(chat_id)
    if not chat:
        await _safe_ws_send_json(websocket, {"type": "error", "message": "Chat not found"}, chat_id=chat_id)
        return

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
        try:
            display_prompt, make_query_input = _build_turn_payload(chat_id, prompt, attachments)
        except ValueError as e:
            await _safe_ws_send_json(websocket, {"type": "error", "message": str(e)}, chat_id=chat_id)
            return

        _save_message(chat_id, "user", display_prompt)

        if chat["title"] == "New Chat":
            title_source = prompt or display_prompt
            title = title_source[:50] + ("..." if len(title_source) > 50 else "")
            _update_chat(chat_id, title=title)
            await _safe_ws_send_json(
                websocket, {"type": "chat_updated", "chat_id": chat_id, "title": title}, chat_id=chat_id
            )

        # Register this WS in the registry so the stream can find it
        original_ws = websocket
        _chat_ws[chat_id] = websocket
        _reset_stream_buffer(chat_id)
        await _send_stream_event(chat_id, {"type": "stream_start", "chat_id": chat_id})

        result: dict | None = None
        try:
            client = await _get_or_create_client(chat_id)
            result = await _run_query_turn(client, make_query_input, chat_id)
        except Exception as first_error:
            if DEBUG: log(f"DBG RECOVERY: chat={chat_id} first error: {type(first_error).__name__}: {first_error}")
            await _disconnect_client(chat_id)

            # Try to RESUME the existing session first (preserves context, saves tokens)
            chat = _get_chat(chat_id)
            existing_session = chat.get("claude_session_id") if chat else None
            if DEBUG: log(f"DBG RECOVERY: attempting resume session={existing_session or 'NONE'}")
            try:
                options = _make_options(session_id=existing_session)
                client = ClaudeSDKClient(options)
                await asyncio.wait_for(client.connect(), timeout=SDK_QUERY_TIMEOUT)
                _clients[chat_id] = client
                result = await _run_query_turn(client, make_query_input, chat_id)
                if DEBUG: log(f"DBG RECOVERY: resume OK chat={chat_id} session={existing_session or 'new'}")
            except Exception as resume_error:
                if DEBUG: log(f"DBG RECOVERY: resume FAILED: {type(resume_error).__name__}: {resume_error}")
                await _disconnect_client(chat_id)
                _update_chat(chat_id, claude_session_id=None)
                if DEBUG: log(f"DBG RECOVERY: session_id NUKED, trying fresh...")
                try:
                    options = _make_options(session_id=None)
                    client = ClaudeSDKClient(options)
                    await asyncio.wait_for(client.connect(), timeout=SDK_QUERY_TIMEOUT)
                    _clients[chat_id] = client
                    result = await _run_query_turn(client, make_query_input, chat_id)
                    if DEBUG: log(f"DBG RECOVERY: fresh session OK chat={chat_id}")
                except Exception as fresh_error:
                    if DEBUG: log(f"DBG RECOVERY: fresh ALSO FAILED: {type(fresh_error).__name__}: {fresh_error}")
                    await _disconnect_client(chat_id)
                    ws = _chat_ws.get(chat_id, websocket)
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

        # If WS was swapped mid-stream (user reconnected), tell the new WS
        # to reload the chat from DB so it gets the complete response
        current_ws = _chat_ws.get(chat_id)
        if current_ws and current_ws is not original_ws:
            log(f"WS swapped during stream for chat={chat_id}, sending reload")
            await _safe_ws_send_json(
                current_ws,
                {"type": "stream_complete_reload", "chat_id": chat_id},
                chat_id=chat_id,
            )
    finally:
        chat_lock.release()
        ws = _chat_ws.pop(chat_id, websocket)
        await _safe_ws_send_json(ws, {"type": "stream_end", "chat_id": chat_id}, chat_id=chat_id)
        _stream_buffers.pop(chat_id, None)
        _stream_seq.pop(chat_id, None)


# --- Main page ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    html = CHAT_HTML.replace("{{MODE_CLASS}}", "mtls").replace("{{MODE_LABEL}}", "mTLS")
    return HTMLResponse(html)


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
.thinking-body{padding:0 12px 8px 12px;font-size:12px;color:var(--dim);
line-height:1.4;display:none;white-space:pre-wrap;-webkit-user-select:text;user-select:text}
.thinking-block.open .thinking-body{display:block}
.thinking-header .arrow{transition:transform 0.2s}
.thinking-block.open .thinking-header .arrow{transform:rotate(90deg)}

/* Tool blocks */
.tool-block{background:var(--bg);border-left:3px solid var(--accent);border-radius:6px;
margin-bottom:6px;overflow:hidden}
.tool-header{padding:8px 12px;font-size:12px;color:var(--accent);cursor:pointer;
display:flex;align-items:center;gap:6px;user-select:none}
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

/* Debug bar */
.debugbar{background:#111827;border-top:1px solid #233047;padding:6px 12px;flex-shrink:0}
.debug-state{color:#93C5FD;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
font-size:11px;white-space:pre-wrap}
.debug-log{color:#A7F3D0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;
line-height:1.35;max-height:88px;overflow-y:auto;white-space:pre-wrap;margin-top:4px}
</style>
</head>
<body>

<div class="topbar">
  <button class="btn-icon" id="menuBtn">&#9776;</button>
  <h1 id="chatTitle">LocalChat</h1>
  <span class="status ok" id="statusDot"></span>
  <span class="mode-badge {{MODE_CLASS}}" id="modeBadge">{{MODE_LABEL}}</span>
  <button class="btn-icon" id="refreshBtn" title="Refresh" onclick="window.location.reload()">&#8635;</button>
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
<div class="composer">
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

function markStreamActivity(reason = '') {
  if (!streaming) return;
  lastStreamEventAt = Date.now();
  clearStreamWatchdog();
  streamWatchdog = setTimeout(() => {
    if (!streaming) return;
    if (Date.now() - lastStreamEventAt < 29500) {
      markStreamActivity('watchdog-rescheduled');
      return;
    }
    dbg('stream watchdog: no events in 30s, clearing streaming state');
    streaming = false;
    currentBubble = null;
    sessionStorage.removeItem('streamingChatId');
    clearStreamWatchdog();
    updateSendBtn();

    refreshDebugState(reason ? `stream-watchdog:${reason}` : 'stream-watchdog');
    if (currentChat) {
      selectChat(currentChat).catch(() => {});
    }
  }, 30000);
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
        tb.className = 'thinking-block';
        tb.innerHTML = `<div class="thinking-header" onclick="this.parentElement.classList.toggle(&quot;open&quot;)"><span class="arrow">&#9656;</span> &#129504; Thinking</div><div class="thinking-body"></div>`;
        currentBubble.insertBefore(tb, currentBubble.querySelector('.bubble'));
      }
      tb.querySelector('.thinking-body').textContent += msg.text;
      markStreamActivity('thinking');
      scrollBottom();
      break;

    case 'tool_use':
      if (!currentBubble) currentBubble = addAssistantMsg();
      const toolBlock = document.createElement('div');
      toolBlock.className = 'tool-block';
      toolBlock.id = 'tool-' + msg.id;
      const inputStr = typeof msg.input === 'string' ? msg.input : JSON.stringify(msg.input, null, 2);
      toolBlock.innerHTML = `<div class="tool-header" onclick="this.parentElement.classList.toggle(&quot;open&quot;)"><span class="arrow">&#9656;</span> &#128295; ${escHtml(msg.name)}<span class="tool-status">&#9203;</span></div><div class="tool-body"><b>Input:</b><pre>${escHtml(inputStr)}</pre><div class="tool-result-area"></div></div>`;
      currentBubble.insertBefore(toolBlock, currentBubble.querySelector('.bubble'));
      markStreamActivity('tool-use');
      scrollBottom();
      break;

    case 'tool_result':
      const tb2 = document.getElementById('tool-' + msg.tool_use_id);
      if (tb2) {
        const area = tb2.querySelector('.tool-result-area');
        const content = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content);
        area.innerHTML = `<b>Result:</b><pre>${escHtml(content.substring(0, 2000))}</pre>`;
        const icon = tb2.querySelector('.tool-status');
        icon.textContent = msg.is_error ? '\u2717' : '\u2713';
        icon.style.color = msg.is_error ? 'var(--red)' : 'var(--green)';
      }
      markStreamActivity('tool-result');
      scrollBottom();
      break;

    case 'result':
      if (currentBubble) {
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
  
      if (msg.chat_id && msg.chat_id === currentChat) {
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
  
      if (msg.chat_id && msg.chat_id === currentChat) {
        selectChat(msg.chat_id).catch(() => {});
      }
      refreshDebugState('stream-complete-reload');
      break;

    case 'chat_updated':
      if (currentChat === msg.chat_id) {
        document.getElementById('chatTitle').textContent = msg.title;
      }
      loadChats().catch(err => reportError('chat_updated loadChats', err));
      refreshDebugState('chat-updated');
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

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
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
    d.onclick = () => selectChat(c.id, c.title).catch(err => reportError('selectChat click', err));
    list.appendChild(d);
  });
  setActiveChatUI();
  refreshDebugState('loadChats');
  return chats;
}

async function selectChat(id, title) {
  dbg(' selectChat:', id, title);
  const seq = ++selectChatSeq;
  setCurrentChat(id, title || 'LocalChat');
  closeSidebar();
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
          inner += `<div class="tool-block"><div class="tool-header" onclick="this.parentElement.classList.toggle(&quot;open&quot;)"><span class="arrow">&#9656;</span> &#128295; ${escHtml(t.name)}<span class="tool-status" style="color:${color}">${icon}</span></div><div class="tool-body"><b>Input:</b><pre>${escHtml(inputStr)}</pre><b>Result:</b><pre>${escHtml(resultStr.substring(0, 2000))}</pre></div></div>`;
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
