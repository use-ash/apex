"""WebSocket streaming infrastructure and SDK client lifecycle.

Manages stream IDs, WS attach/detach, stream task tracking, journal
persistence, buffer management, alert broadcast, and Claude SDK client
creation/teardown.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import time
import uuid
from collections import deque
from pathlib import Path

from env import APEX_ROOT, WORKSPACE, WORKSPACE_PATHS, MODEL, DEBUG, SDK_QUERY_TIMEOUT
from compat import safe_chmod

from fastapi import WebSocket

from db import _get_db, _get_chat, _update_chat, _get_chat_tool_policy, _get_profile_tool_policy
from log import log
from local_model.safety import ensure_workspace_path, validate_command, validate_path
from memory_extract import _filter_stream_text_for_memory_tags, _clear_stream_text_filter
from state import (
    _clients, _client_sessions, _client_last_used, _client_permission_levels, _client_permission_policies,
    _chat_locks, _chat_ws, _ws_chat,
    _active_send_tasks, _stream_buffers, _stream_seq, _chat_send_locks,
    _ws_send_count, _ws_fail_count, _db_lock, _current_stream_id,
)

try:
    from claude_agent_sdk import (
        ClaudeSDKClient,
        ClaudeAgentOptions,
        HookMatcher,
        PermissionResultAllow,
        PermissionResultDeny,
    )
except ImportError:
    ClaudeSDKClient = None  # type: ignore[misc,assignment]
    ClaudeAgentOptions = None  # type: ignore[misc,assignment]

# Config imported from env.py

_STREAM_BUFFER_MAX = 200
_STREAM_JOURNAL_DIR = APEX_ROOT / "state" / "streams"
_STREAM_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
safe_chmod(_STREAM_JOURNAL_DIR, 0o700)
_CHAT_ID_RE = re.compile(r"^[0-9a-f]{8,12}$")
_STANDARD_SDK_TOOLS = frozenset({"Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch"})
_SDK_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_SDK_PATH_INPUT_KEYS = (
    "path",
    "file_path",
    "new_path",
    "old_path",
    "notebook_path",
)


# ---------------------------------------------------------------------------
# Stream ID
# ---------------------------------------------------------------------------

def _make_stream_id() -> str:
    return uuid.uuid4().hex[:12]


def _is_valid_chat_id(chat_id: str) -> bool:
    return bool(_CHAT_ID_RE.fullmatch(chat_id or ""))


# ---------------------------------------------------------------------------
# WebSocket registry
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Stream task tracking
# ---------------------------------------------------------------------------

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


def _get_all_active_stream_entries() -> list[tuple[str, str, dict[str, object]]]:
    """Return active stream entries across all chats after stale cleanup."""
    active: list[tuple[str, str, dict[str, object]]] = []
    empty_chat_ids: list[str] = []
    for chat_id, streams in list(_active_send_tasks.items()):
        stale_ids: list[str] = []
        for stream_id, info in list(streams.items()):
            if _stream_task_is_active(info.get("task")):
                active.append((chat_id, stream_id, info))
            else:
                stale_ids.append(stream_id)
        for stream_id in stale_ids:
            streams.pop(stream_id, None)
        if streams:
            _active_send_tasks[chat_id] = streams
        else:
            empty_chat_ids.append(chat_id)
    for chat_id in empty_chat_ids:
        _active_send_tasks.pop(chat_id, None)
    return active


def _get_profile_active_stream_stats(profile_id: str) -> tuple[int, int | None]:
    """Return active stream count and oldest active age for one profile across all chats."""
    if not profile_id:
        return 0, None

    active_count = 0
    oldest_started_at: float | None = None
    for _, _, info in _get_all_active_stream_entries():
        if str(info.get("profile_id") or "") != profile_id:
            continue
        started_at = float(info.get("started_at") or 0.0)
        if started_at <= 0:
            continue
        active_count += 1
        if oldest_started_at is None or started_at < oldest_started_at:
            oldest_started_at = started_at

    if oldest_started_at is None:
        return active_count, None
    return active_count, max(0, int(time.monotonic() - oldest_started_at))


def _has_active_stream(chat_id: str, exclude_stream_id: str = "") -> bool:
    return any(stream_id != exclude_stream_id for stream_id, _ in _get_active_stream_entries(chat_id))


def _get_profile_active_stream_stats(profile_id: str) -> tuple[int, int | None]:
    """Return (active_count, oldest_age_seconds) across ALL chats for a profile.

    Uses _stream_task_is_active() for stale cleanup.  Returns age as integer
    seconds since the oldest started_at, or None if no active streams.
    """
    now = time.monotonic()
    count = 0
    oldest_age: float | None = None
    for chat_id in list(_active_send_tasks):
        for _sid, info in _get_active_stream_entries(chat_id):
            if info.get("profile_id") != profile_id:
                continue
            count += 1
            sa = info.get("started_at")
            if sa is not None:
                age = now - sa
                if oldest_age is None or age > oldest_age:
                    oldest_age = age
    return count, int(oldest_age) if oldest_age is not None else None


def _set_active_send_task(
    chat_id: str,
    stream_id: str,
    task: asyncio.Task,
    *,
    name: str = "",
    avatar: str = "",
    profile_id: str = "",
    started_at: float = 0.0,
) -> None:
    _active_send_tasks.setdefault(chat_id, {})[stream_id] = {
        "task": task,
        "stream_id": stream_id,
        "name": name,
        "avatar": avatar,
        "profile_id": profile_id,
        "started_at": started_at,
    }


def _update_active_send_task(
    chat_id: str,
    stream_id: str,
    *,
    name: str | None = None,
    avatar: str | None = None,
    profile_id: str | None = None,
    started_at: float | None = None,
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
    if started_at is not None:
        info["started_at"] = started_at


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


# ---------------------------------------------------------------------------
# Stream cancellation
# ---------------------------------------------------------------------------

async def _cancel_chat_streams(chat_id: str, stream_id: str = "") -> bool:
    if not chat_id:
        return False
    active_entries = list(_get_active_stream_entries(chat_id))
    if stream_id:
        active_entries = [item for item in active_entries if item[0] == stream_id]
    if not active_entries:
        return False

    client_keys: set[str] = set()
    for _, entry in active_entries:
        profile_id = str(entry.get("profile_id") or "")
        if profile_id:
            client_keys.add(f"{chat_id}:{profile_id}")
        else:
            client_keys.add(chat_id)

    if stream_id and not client_keys:
        client_keys = {chat_id}

    if stream_id:
        selected_keys = client_keys
    else:
        selected_keys = {ck for ck in list(_clients) if ck == chat_id or ck.startswith(chat_id + ":")}
        if not selected_keys:
            selected_keys = client_keys

    for ck in selected_keys:
        client = _clients.pop(ck, None)
        if not client:
            continue
        try:
            await client.interrupt()
        except Exception:
            pass

    tasks_to_drain: list[asyncio.Task] = []
    for _, entry in active_entries:
        send_task = entry.get("task")
        if isinstance(send_task, asyncio.Task) and not send_task.done():
            send_task.cancel()
            tasks_to_drain.append(send_task)

    if tasks_to_drain:
        await asyncio.wait(tasks_to_drain, timeout=2.0)

    await _send_active_streams(chat_id)
    return True


# ---------------------------------------------------------------------------
# Alert broadcast
# ---------------------------------------------------------------------------

async def _broadcast_alert(alert: dict) -> None:
    """Send alert to ALL connected WebSocket clients (regardless of which chat they're viewing)."""
    payload = {"type": "alert", **alert}
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


# ---------------------------------------------------------------------------
# Claude SDK client management
# ---------------------------------------------------------------------------

def _load_mcp_servers() -> dict[str, dict]:
    """Load enabled MCP server configs from state/mcp_servers.json."""
    mcp_path = APEX_ROOT / "state" / "mcp_servers.json"
    if not mcp_path.exists():
        return {}
    try:
        data = json.loads(mcp_path.read_text())
        servers = data.get("mcpServers", {})
        if not isinstance(servers, dict):
            return {}
        return {
            name: {k: v for k, v in cfg.items() if k != "enabled"}
            for name, cfg in servers.items()
            if isinstance(cfg, dict) and cfg.get("enabled", True)
        }
    except (json.JSONDecodeError, OSError) as e:
        log(f"MCP config load failed: {e}")
        return {}


def _resolve_sdk_permission_level(client_key: str | None, chat_id: str | None = None) -> int:
    if not client_key:
        return 2
    real_chat_id = chat_id or client_key.split(":")[0]
    profile_id = client_key.split(":", 1)[1] if ":" in client_key else ""
    if profile_id:
        policy = _get_profile_tool_policy(profile_id)
    else:
        policy = _get_chat_tool_policy(real_chat_id)
    return int(policy.get("level", 2))


def _sdk_permission_mode_for_level(level: int) -> str:
    if level <= 1:
        return "plan"
    if level >= 4:
        return "bypassPermissions"
    return "acceptEdits"


def _sdk_tool_input_paths(tool_input: dict) -> list[str]:
    paths: list[str] = []
    if not isinstance(tool_input, dict):
        return paths
    for key in _SDK_PATH_INPUT_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(value.strip())
    return paths


def _sdk_resolve_path(path: str) -> str:
    expanded = os.path.expanduser(path)
    if os.path.isabs(expanded):
        return os.path.realpath(expanded)
    return os.path.realpath(os.path.join(str(WORKSPACE), expanded))


def _sdk_path_error(tool_name: str, tool_input: dict, *, permission_level: int = 2) -> str | None:
    if permission_level >= 4:
        return None
    allow_write = tool_name in _SDK_WRITE_TOOLS
    for raw_path in _sdk_tool_input_paths(tool_input):
        _, err = ensure_workspace_path(
            raw_path,
            str(WORKSPACE_PATHS),
            allow_write=allow_write,
            permission_level=permission_level,
        )
        if err:
            return err
    return None


def _make_sdk_tool_gate(level: int, *, allowed_commands: list[str] | None = None):
    async def _can_use_tool(tool_name: str, tool_input: dict, _context):
        if level <= 0:
            return PermissionResultDeny(
                message="This agent is Restricted and cannot use tools or access files.",
                interrupt=True,
            )
        if level >= 4:
            return PermissionResultAllow()
        path_err = _sdk_path_error(tool_name, tool_input, permission_level=level)
        if path_err:
            return PermissionResultDeny(message=path_err, interrupt=True)
        if tool_name == "Bash":
            command = str((tool_input or {}).get("command") or "").strip()
            command_err = validate_command(
                command,
                str(WORKSPACE),
                permission_level=level,
                allowed_commands=allowed_commands,
            )
            if command_err:
                return PermissionResultDeny(message=command_err, interrupt=True)
        if level == 1 and tool_name not in _STANDARD_SDK_TOOLS:
            return PermissionResultDeny(
                message="This action requires Elevated or Admin permissions.",
                interrupt=True,
            )
        return PermissionResultAllow()

    return _can_use_tool


def _sdk_pre_tool_use_decision(
    tool_name: str,
    tool_input: dict,
    *,
    level: int,
    allowed_commands: list[str] | None = None,
) -> tuple[bool, str]:
    if level <= 0:
        return False, "This agent is Restricted and cannot use tools or access files."
    if level >= 4:
        return True, ""
    path_err = _sdk_path_error(tool_name, tool_input, permission_level=level)
    if path_err:
        return False, path_err
    if tool_name == "Bash":
        command = str((tool_input or {}).get("command") or "").strip()
        command_err = validate_command(
            command,
            str(WORKSPACE),
            permission_level=level,
            allowed_commands=allowed_commands,
        )
        if command_err:
            return False, command_err
    if level == 1 and tool_name not in _STANDARD_SDK_TOOLS:
        return False, "This action requires Elevated or Admin permissions."
    return True, ""


def _make_sdk_pre_tool_use_hook(level: int, *, allowed_commands: list[str] | None = None):
    async def _hook(hook_input, _tool_use_id, _context):
        tool_name = str((hook_input or {}).get("tool_name") or "")
        tool_input = hook_input.get("tool_input") if isinstance(hook_input, dict) else {}
        if not isinstance(tool_input, dict):
            tool_input = {}
        allowed, message = _sdk_pre_tool_use_decision(
            tool_name,
            tool_input,
            level=level,
            allowed_commands=allowed_commands,
        )
        if allowed:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                }
            }
        return {
            "decision": "block",
            "systemMessage": message,
            "reason": message,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": message,
            },
        }

    return _hook


def _make_options(
    model: str | None = None,
    session_id: str | None = None,
    *,
    client_key: str | None = None,
    chat_id: str | None = None,
    permission_level: int | None = None,
    allowed_commands: list[str] | None = None,
) -> ClaudeAgentOptions:
    """Build SDK options for a new or resumed session."""
    if permission_level is None:
        permission_level = _resolve_sdk_permission_level(client_key, chat_id)
    # Extra workspace roots beyond the primary (colon-separated APEX_WORKSPACE)
    extra_dirs = [
        r.strip() for r in WORKSPACE_PATHS.split(":")[1:]
        if r.strip() and r.strip() != str(WORKSPACE)
    ]
    opts = ClaudeAgentOptions(
        model=model or MODEL,
        cwd=str(WORKSPACE),
        permission_mode=_sdk_permission_mode_for_level(permission_level),
        max_turns=50,
        resume=session_id,
        setting_sources=["user"],
        add_dirs=extra_dirs,
        can_use_tool=_make_sdk_tool_gate(permission_level, allowed_commands=allowed_commands),
        hooks={
            "PreToolUse": [
                HookMatcher(
                    matcher="Bash|Read|Write|Edit|MultiEdit|NotebookEdit|Grep|Glob|LS|WebFetch|WebSearch",
                    hooks=[_make_sdk_pre_tool_use_hook(permission_level, allowed_commands=allowed_commands)],
                )
            ]
        },
    )
    mcp_servers = _load_mcp_servers()
    if mcp_servers:
        opts.mcp_servers = mcp_servers
        log(f"MCP: {len(mcp_servers)} server(s) attached to SDK options")
    if extra_dirs:
        log(f"SDK: {len(extra_dirs)} additional dir(s): {extra_dirs}")
    return opts


def _client_is_alive(client: ClaudeSDKClient) -> bool:
    """Check if an SDK client's subprocess is still running."""
    try:
        transport = getattr(client, "_transport", None)
        if transport is None:
            return False
        proc = getattr(transport, "_process", None)
        if proc is None:
            return False
        if proc.returncode is not None:
            return False
        return True
    except Exception:
        return False


_MAX_SDK_CLIENTS = int(os.environ.get("APEX_MAX_SDK_CLIENTS", "5"))


def _permission_policy_signature(level: int | None, allowed_commands: list[str] | None) -> str:
    payload = {
        "level": int(level if level is not None else 2),
        "allowed_commands": [str(cmd).strip() for cmd in (allowed_commands or []) if str(cmd).strip()],
    }
    return json.dumps(payload, separators=(",", ":"))


async def _evict_lru_client() -> None:
    """Evict the least-recently-used idle SDK client to make room."""
    if len(_clients) < _MAX_SDK_CLIENTS:
        return

    # Find idle clients (not currently locked)
    idle = []
    for key in _clients:
        lock = _chat_locks.get(key)
        if lock and lock.locked():
            continue  # actively processing — skip
        idle.append(key)

    if not idle:
        log(f"SDK pool: all {len(_clients)} clients are busy, cannot evict")
        return

    # Sort by last-used timestamp, evict oldest
    idle.sort(key=lambda k: _client_last_used.get(k, 0))
    victim = idle[0]
    log(f"SDK pool: evicting LRU client key={victim} (pool={len(_clients)}/{_MAX_SDK_CLIENTS})")
    await _disconnect_client(victim)


async def _get_or_create_client(
    client_key: str,
    model: str | None = None,
    *,
    permission_level: int | None = None,
    allowed_commands: list[str] | None = None,
) -> ClaudeSDKClient:
    """Get existing persistent client or create a new one.

    client_key is chat_id for solo chats, or chat_id:profile_id for group agents.
    Enforces a max pool size — evicts LRU idle client when at capacity.
    Group agents persist session_id for resume across client evictions.
    """
    if permission_level is None:
        permission_level = _resolve_sdk_permission_level(client_key)
    policy_signature = _permission_policy_signature(permission_level, allowed_commands)
    if client_key in _clients:
        client = _clients[client_key]
        if (
            _client_is_alive(client)
            and _client_permission_levels.get(client_key) == permission_level
            and _client_permission_policies.get(client_key) == policy_signature
        ):
            _client_last_used[client_key] = time.time()
            return client
        log(f"stale SDK client detected: key={client_key}, evicting")
        await _disconnect_client(client_key)

    # Proactive OAuth check before creating a new client
    from agent_sdk import ensure_fresh_token
    await asyncio.to_thread(ensure_fresh_token)

    # Enforce pool limit
    await _evict_lru_client()

    real_chat_id = client_key.split(":")[0]
    is_group_agent = ":" in client_key

    chat = _get_chat(real_chat_id)
    if is_group_agent:
        # Group agents: look up session from in-memory cache
        session_id = _client_sessions.get(client_key)
    else:
        session_id = chat.get("claude_session_id") if chat else None

    options = _make_options(
        model=model,
        session_id=session_id,
        client_key=client_key,
        chat_id=real_chat_id,
        permission_level=permission_level,
        allowed_commands=allowed_commands,
    )

    effective_model = model or MODEL
    log(f"creating SDK client: key={client_key} model={effective_model} resume={session_id or 'new'} pool={len(_clients)+1}/{_MAX_SDK_CLIENTS}")
    client = ClaudeSDKClient(options)
    await asyncio.wait_for(client.connect(), timeout=SDK_QUERY_TIMEOUT)
    _clients[client_key] = client
    _client_last_used[client_key] = time.time()
    _client_permission_levels[client_key] = permission_level
    _client_permission_policies[client_key] = policy_signature
    return client


def _register_client(
    client_key: str,
    client: ClaudeSDKClient,
    permission_level: int | None = None,
    *,
    allowed_commands: list[str] | None = None,
) -> None:
    """Register an externally-created SDK client in the shared registry.

    Use this instead of writing to _clients directly.  The recovery path in
    ws_handler creates clients manually (custom session_id logic) and calls
    this to publish the result without bypassing the single-owner contract.
    """
    _clients[client_key] = client
    _client_last_used[client_key] = time.time()
    if permission_level is None:
        _client_permission_levels.pop(client_key, None)
        _client_permission_policies.pop(client_key, None)
    else:
        _client_permission_levels[client_key] = permission_level
        _client_permission_policies[client_key] = _permission_policy_signature(permission_level, allowed_commands)


def store_client_session(client_key: str, session_id: str) -> None:
    """Store session_id for a client key (used for group agent resume)."""
    _client_sessions[client_key] = session_id


def _has_client(client_key: str) -> bool:
    """Return True if a client is registered for the given key."""
    return client_key in _clients


def _get_all_stream_task_entries(chat_id: str) -> list[tuple[str, dict[str, object]]]:
    """Return all stream task entries for chat_id, including completed ones.

    Unlike _get_active_stream_entries, this does NOT prune stale entries —
    callers that need to finalize every task (active or done) should use this.
    """
    return list((_active_send_tasks.get(chat_id) or {}).items())


# ---------------------------------------------------------------------------
# Locks
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Stream journal (crash recovery)
# ---------------------------------------------------------------------------

def _stream_journal_path(chat_id: str) -> Path:
    if not _is_valid_chat_id(chat_id):
        raise ValueError(f"invalid chat_id for stream journal: {chat_id!r}")
    return _STREAM_JOURNAL_DIR / f"{chat_id}.jsonl"


def _recovery_journal_path(chat_id: str) -> Path:
    if not _is_valid_chat_id(chat_id):
        raise ValueError(f"invalid chat_id for recovery journal: {chat_id!r}")
    return _STREAM_JOURNAL_DIR / f"{chat_id}.recovery.jsonl"


def _reset_stream_buffer(chat_id: str) -> None:
    if not _is_valid_chat_id(chat_id):
        return
    _stream_buffers[chat_id] = deque(maxlen=_STREAM_BUFFER_MAX)
    _stream_seq[chat_id] = 0
    try:
        _stream_journal_path(chat_id).write_text("")
    except (OSError, ValueError):
        pass


def _cleanup_stream_journal(chat_id: str) -> None:
    """Remove journal file when stream completes successfully."""
    try:
        _stream_journal_path(chat_id).unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def _archive_stream_journal(chat_id: str) -> bool:
    """Move journal to .recovery.jsonl for crash recovery. Returns True if archived."""
    try:
        jpath = _stream_journal_path(chat_id)
        rpath = _recovery_journal_path(chat_id)
    except ValueError:
        return False
    if not jpath.exists() or jpath.stat().st_size == 0:
        return False
    try:
        jpath.rename(rpath)
        log(f"journal archived for recovery: chat={chat_id[:8]}")
        return True
    except OSError:
        return False


def _load_journal_events(chat_id: str) -> list[tuple[int, dict]]:
    """Load events from journal file for recovery after disconnect."""
    try:
        jpath = _stream_journal_path(chat_id)
    except ValueError:
        return []
    if not jpath.exists():
        return []
    events = []
    try:
        for i, line in enumerate(jpath.read_text().splitlines(), 1):
            if line.strip():
                events.append((i, json.loads(line)))
    except (OSError, json.JSONDecodeError):
        pass
    return events


def _load_recovery_journal(chat_id: str) -> list[tuple[int, dict]]:
    """Load events from recovery archive. Same format as _load_journal_events."""
    try:
        rpath = _recovery_journal_path(chat_id)
    except ValueError:
        return []
    if not rpath.exists():
        return []
    events = []
    try:
        for i, line in enumerate(rpath.read_text().splitlines(), 1):
            if line.strip():
                events.append((i, json.loads(line)))
    except (OSError, json.JSONDecodeError):
        pass
    return events


def _cleanup_recovery_journal(chat_id: str) -> None:
    """Remove recovery archive after it has been consumed."""
    try:
        _recovery_journal_path(chat_id).unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def _buffer_stream_event(chat_id: str, payload: dict) -> None:
    if not _is_valid_chat_id(chat_id):
        return
    if chat_id not in _stream_buffers:
        _reset_stream_buffer(chat_id)
    seq = _stream_seq.get(chat_id, 0) + 1
    _stream_seq[chat_id] = seq
    _stream_buffers[chat_id].append((seq, dict(payload)))
    try:
        with open(_stream_journal_path(chat_id), "a") as f:
            f.write(json.dumps(payload) + "\n")
    except (OSError, ValueError):
        pass


# ---------------------------------------------------------------------------
# Stream event sending
# ---------------------------------------------------------------------------

async def _send_stream_event(chat_id: str, payload: dict) -> None:
    payload = dict(payload)
    stream_id = _current_stream_id.get("")
    if stream_id and not payload.get("stream_id"):
        payload["stream_id"] = stream_id
    payload_stream_id = str(payload.get("stream_id") or "")
    if payload.get("type") == "text" and isinstance(payload.get("text"), str) and payload_stream_id:
        filtered_text = _filter_stream_text_for_memory_tags(chat_id, payload_stream_id, payload.get("text") or "")
        if not filtered_text:
            return
        payload["text"] = filtered_text
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


async def _finalize_stream(chat_id: str, stream_id: str, task: asyncio.Task | None = None,
                           *, is_group_chat: bool = False, send_stream_end: bool = True,
                           preserve_journal: bool = False) -> None:
    try:
        if send_stream_end:
            await _send_stream_event(chat_id, {"type": "stream_end", "chat_id": chat_id, "stream_id": stream_id})
            log(f"stream_end sent: chat={chat_id} viewers={len(_chat_ws.get(chat_id, set()))}")
    finally:
        _clear_stream_text_filter(chat_id, stream_id)
        _remove_active_send_task(chat_id, stream_id, task if isinstance(task, asyncio.Task) else None)
        if is_group_chat:
            await _send_active_streams(chat_id)
        if not _has_active_stream(chat_id):
            _stream_buffers.pop(chat_id, None)
            _stream_seq.pop(chat_id, None)
            if preserve_journal:
                _archive_stream_journal(chat_id)
            else:
                _cleanup_stream_journal(chat_id)


# ---------------------------------------------------------------------------
# Client disconnect / model switch
# ---------------------------------------------------------------------------

async def _disconnect_client(chat_id: str) -> None:
    client = _clients.pop(chat_id, None)
    _client_last_used.pop(chat_id, None)
    _client_permission_levels.pop(chat_id, None)
    _client_permission_policies.pop(chat_id, None)
    # NOTE: _client_sessions is NOT cleared here — we want to preserve
    # the session_id so group agents can resume after eviction.
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


# ---------------------------------------------------------------------------
# Response stream normalization
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Safe WebSocket send
# ---------------------------------------------------------------------------

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
