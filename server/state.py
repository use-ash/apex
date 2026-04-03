"""Shared mutable state for the Apex server.

All cross-module mutable globals live here so modules can import
what they need without circular dependencies.

Ownership contract
------------------
Each state group documents its *primary writer* — the module responsible for
all mutations.  Read access is unrestricted; direct writes from outside the
owning module are a contract violation and should be replaced with the owning
module's accessor functions.

  State group              Primary writer       Key accessors
  ─────────────────────────────────────────────────────────────────────────
  Compaction               context.py           _store_recovery_context()
  Session context          context.py           _clear_session_context()
  Group routing            context.py / ws_handler (read + init only)
  Whisper                  context.py           _get_whisper_text()
  Stream text filters      memory_extract.py    (direct dict ops, isolated)
  SDK clients              streaming.py         _get_or_create_client(),
                                                _register_client()
  WebSocket connections    streaming.py         _attach_ws(), _detach_ws()
  Active send tasks        streaming.py         _set_active_send_task(),
                                                _update_active_send_task(),
                                                _remove_active_send_task()
  Stream buffers           streaming.py         _buffer_stream_event(),
                                                _reset_stream_buffer()
  Stream locks             streaming.py         _get_chat_lock(),
                                                _get_chat_send_lock()
  WebSocket counters       streaming.py         (direct increment, isolated)
  Rate limiting            routes_misc.py       (direct dict ops, isolated)
  Alerts                   routes_alerts.py     (list append/pop, isolated)
  Task registry            tasks.py             get_task(), create_task(),
                                                update_task_status()
  Recovery pending         apex.py              (startup lifecycle only)
  DB lock                  (global shared lock) —
  Context vars             streaming.py         _current_stream_id
                           ws_handler.py        _current_group_profile_id
"""
from __future__ import annotations

import asyncio
import contextvars
import threading
from collections import deque
from typing import Any

# ---------------------------------------------------------------------------
# Compaction
# Primary writer: context.py — use _store_recovery_context() for writes.
# apex.py also manages _recovery_pending lifecycle (startup only).
# ---------------------------------------------------------------------------
_compaction_summaries: dict[str, str] = {}    # chat_id -> summary text
_recovery_target: dict[str, str] = {}         # chat_id -> profile_id of agent that should get recovery
_recovery_skip_count: dict[str, int] = {}     # chat_id -> times recovery was skipped (safety valve)
_last_compacted_at: dict[str, str] = {}       # chat_id -> ISO timestamp
_recovery_pending: dict[str, asyncio.Event] = {}  # chat_id -> set when ready

# ---------------------------------------------------------------------------
# Session context
# Primary writer: context.py — use _clear_session_context() for writes.
# ---------------------------------------------------------------------------
_session_context_sent: set[str] = set()  # session keys that got workspace context

# ---------------------------------------------------------------------------
# Group routing
# Primary writer: context.py / ws_handler.py (reads and lazy-init only).
# ---------------------------------------------------------------------------
_group_profile_override: dict[str, str] = {}  # chat_id -> profile_id

# ---------------------------------------------------------------------------
# Whisper
# Primary writer: context.py — managed inside _get_whisper_text().
# ---------------------------------------------------------------------------
_whisper_last: dict[str, float] = {}  # chat_id -> last injection timestamp

# ---------------------------------------------------------------------------
# Stream text filters (memory tag stripping)
# Primary writer: memory_extract.py — dict ops isolated to that module.
# ---------------------------------------------------------------------------
_STREAM_TEXT_FILTERS: dict[tuple[str, str], dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# SDK clients & WebSocket connections
# Primary writer: streaming.py — use its accessor functions, never write
#   directly from route modules.
#   _clients      — _get_or_create_client(), _register_client()
#   _chat_ws      — _attach_ws(), _detach_ws()
#   _ws_chat      — _attach_ws(), _detach_ws()
#   _active_send_tasks — _set_active_send_task(), _remove_active_send_task()
# ---------------------------------------------------------------------------
_clients: dict[str, Any] = {}                            # client_key -> ClaudeSDKClient
_client_sessions: dict[str, str] = {}                    # client_key -> session_id (group agents)
_client_last_used: dict[str, float] = {}                 # client_key -> timestamp (for LRU eviction)
_client_permission_levels: dict[str, int] = {}          # client_key -> effective SDK permission level
_codex_threads: dict[str, str] = {}                      # session_key -> codex thread_id (for resume)
_codex_thread_turns: dict[str, int] = {}                 # session_key -> turn count (for thread rotation)
_chat_locks: dict[str, asyncio.Lock] = {}                # chat_id -> processing lock
_chat_ws: dict[str, set[Any]] = {}                       # chat_id -> set[WebSocket]
_ws_chat: dict[Any, str] = {}                            # WebSocket -> chat_id
_active_send_tasks: dict[str, dict[str, dict[str, Any]]] = {}
# chat_id -> {stream_id -> {task, stream_id, name, avatar, profile_id}}
_queued_turns: dict[str, deque[dict[str, Any]]] = {}
# lock_key -> deque[{websocket, data, chat_id, stream_id, name, avatar, profile_id}]

# ---------------------------------------------------------------------------
# Stream buffers
# Primary writer: streaming.py — _buffer_stream_event(), _reset_stream_buffer()
# ---------------------------------------------------------------------------
_stream_buffers: dict[str, deque] = {}   # stream_id -> deque of (seq, payload)
_stream_seq: dict[str, int] = {}         # stream_id -> sequence counter
_chat_send_locks: dict[str, asyncio.Lock] = {}  # chat_id -> ws send lock

# ---------------------------------------------------------------------------
# WebSocket counters
# Primary writer: streaming.py — incremented inside _send_stream_event().
# ---------------------------------------------------------------------------
_ws_send_count: dict[str, int] = {}
_ws_fail_count: dict[str, int] = {}

# ---------------------------------------------------------------------------
# Rate limiting
# Primary writer: routes_misc.py — direct dict ops, isolated to that module.
# ---------------------------------------------------------------------------
_rate_buckets: dict[str, list[float]] = {}  # "ip:path" -> [timestamps]

# ---------------------------------------------------------------------------
# Alerts
# Primary writer: routes_alerts.py — list append/pop, isolated to that module.
# ---------------------------------------------------------------------------
_alert_waiters: list[asyncio.Event] = []  # notify background pollers

# ---------------------------------------------------------------------------
# Task registry
# Primary writer: tasks.py — use get_task(), create_task(), update_task_status().
# No direct access to _tasks from outside tasks.py.
# ---------------------------------------------------------------------------
_tasks: dict[str, Any] = {}                            # task_id -> TaskRecord
_task_output_waiters: dict[str, list[asyncio.Event]] = {}  # task_id -> SSE waiters

# ---------------------------------------------------------------------------
# Locks
# ---------------------------------------------------------------------------
_db_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Context variables
# ---------------------------------------------------------------------------
_current_stream_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "apex_stream_id", default=""
)
_current_group_profile_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "apex_group_profile_id", default=""
)
