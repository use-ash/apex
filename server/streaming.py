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
import sys
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import env
from env import APEX_ROOT, MODEL, DEBUG, SDK_QUERY_TIMEOUT
from compat import safe_chmod

from fastapi import WebSocket

from db import _get_db, _get_chat, _update_chat, _get_chat_tool_policy, _get_profile_tool_policy
from log import log
from tool_access import (
    tool_access_decision,
    GUIDE_TOOL_NAMES,
    resolve_profile_extra_tools,
)
from memory_extract import _filter_stream_text_for_memory_tags, _clear_stream_text_filter
from state import (
    _clients, _client_sessions, _client_last_used, _client_permission_levels, _client_permission_policies,
    _chat_locks, _chat_ws, _ws_chat,
    _active_send_tasks, _stream_buffers, _stream_seq, _stream_epoch_nonce, _chat_send_locks,
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

_STREAM_BUFFER_MAX = 2000

# --- V3 v2 Step 3 Commit 4 — claim_gate_summary emit (2026-04-20) -----------
# Gated by APEX_CLAIM_GATE_SUMMARY env var; OFF by default. When enabled, we
# run server/claim_gate.py::extract_and_tag against the assistant's final
# prose + that turn's claim_assert rows after stream_end, persist the full
# trace JSON to claim_gate_traces (UNIQUE(chat_id, turn_id) covers replay
# race), and emit one claim_gate_summary WS event carrying counts + tag_rate
# + trace_ref. Fail-open: any error is logged at WARN, never aborts stream.
# Normative spec: workspace/v3/experiments/claim_gate_summary_spec.md (02c3c2c).
_CLAIM_GATE_SUMMARY_ENABLED = os.environ.get("APEX_CLAIM_GATE_SUMMARY") == "1"
_CLAIM_GATE_SUMMARY_SCHEMA_VERSION = 1
_CLAIM_GATE_SUMMARY_WIRE_CAP = 4096  # hard cap on wire-payload bytes (spec §2)

# --- Zombie-reload guard (2026-04-20) ---------------------------------------
# Tracks which WebSockets were attached to a chat at the moment a given
# stream began (_stream_attached_at_start) and which of those dropped off
# while the stream was still running (_stream_disconnected_during). Used at
# post-stream broadcast in ws_handler to emit `stream_complete_reload` ONLY
# to rejoiners + latecomers, not to viewers that stayed attached end-to-end
# and already hold every frame in their live client context.
# Keyed by (chat_id, stream_id). Both dicts popped after the broadcast.
_stream_attached_at_start: "dict[tuple[str, str], set]" = {}
_stream_disconnected_during: "dict[tuple[str, str], set]" = {}


def _record_disconnect_mid_stream(ws, chat_id: str) -> None:
    """If any stream is mid-flight for chat_id, record ws as having dropped."""
    for key in list(_stream_attached_at_start.keys()):
        if key[0] == chat_id and ws in _stream_attached_at_start[key]:
            _stream_disconnected_during.setdefault(key, set()).add(ws)


# Server epoch — monotonic-ish ID stamped on every stream event so clients can
# detect server restart and reset their seq dedup state. Generated fresh each
# time this module loads (i.e., each server process).
_SERVER_EPOCH = str(int(time.time() * 1000))
_STREAM_JOURNAL_DIR = APEX_ROOT / "state" / "streams"
_STREAM_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
safe_chmod(_STREAM_JOURNAL_DIR, 0o700)
_CHAT_ID_RE = re.compile(r"^[0-9a-f]{8,12}$")

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

def _ws_is_alive(ws: WebSocket) -> bool:
    """Return True iff the WebSocket is still in CONNECTED state on both sides.

    Starlette tracks client_state (what the client has sent us) and
    application_state (what we have sent the client). Either side in
    DISCONNECTED means any subsequent send_json will raise
    RuntimeError("Cannot call 'send' once a close message has been sent").
    We detect that here and refuse to register such sockets, so that
    stream frames don't get wasted on zombies.
    """
    try:
        from starlette.websockets import WebSocketState
    except ImportError:
        return True  # can't probe; assume alive and rely on reactive eviction
    try:
        client_ok = getattr(ws, "client_state", None) == WebSocketState.CONNECTED
        app_ok = getattr(ws, "application_state", None) == WebSocketState.CONNECTED
        return bool(client_ok and app_ok)
    except Exception:
        return True


def _vacuum_dead_ws(chat_id: str) -> int:
    """Drop any disconnected WebSockets from the chat's viewer set.

    Returns count vacuumed. Keeps _ws_chat in sync. Called before a new
    attach or the first send of a frame so zombies never absorb traffic.
    """
    ws_set = _chat_ws.get(chat_id)
    if not ws_set:
        return 0
    dead = [w for w in list(ws_set) if not _ws_is_alive(w)]
    for w in dead:
        # Record pre-discard so mid-stream guard sees the viewer leave.
        _record_disconnect_mid_stream(w, chat_id)
        ws_set.discard(w)
        _ws_chat.pop(w, None)
    if not ws_set:
        _chat_ws.pop(chat_id, None)
    if dead:
        log(f"WSDIAG vacuum chat={chat_id[:8]} dead={len(dead)} remaining={len(ws_set)}")
    return len(dead)


def _attach_ws(ws: WebSocket, chat_id: str) -> None:
    """Register ws for chat_id, removing it from any previous chat first."""
    old = _ws_chat.get(ws)
    if old and old != chat_id:
        old_set = _chat_ws.get(old)
        if old_set:
            _record_disconnect_mid_stream(ws, old)
            old_set.discard(ws)
            if not old_set:
                _chat_ws.pop(old, None)
        log(f"ws detached from chat={old} -> attaching to chat={chat_id}")
    # Vacuum any zombie WebSockets that never got cleanly detached (e.g.
    # abrupt TCP drops from iOS cellular<->WiFi transitions, browser tab
    # kill during send). Must happen BEFORE we add this ws, or the zombie
    # will absorb seq=1 of the next stream and the real viewer misses
    # the opening frame. See ws_send FAIL "Cannot call 'send' once a
    # close message has been sent" in apex.log.
    _vacuum_dead_ws(chat_id)
    _chat_ws.setdefault(chat_id, set()).add(ws)
    _ws_chat[ws] = chat_id
    # Seed the ping-ts map so a just-attached socket gets a full grace period
    # before the prober can evict it for staleness.
    _last_client_ping.setdefault(ws, time.time())
    # WSDIAG: observability for WS streaming race bug. Correlate by ws_id+chat.
    log(f"WSDIAG attach ws={id(ws) & 0xFFFFFF:06x} old={(old or '_')[:8]} new={chat_id[:8]} set={len(_chat_ws.get(chat_id, ()))}")


def _detach_ws(ws: WebSocket) -> None:
    """Remove ws from all tracking."""
    old = _ws_chat.pop(ws, None)
    _last_client_ping.pop(ws, None)
    if old:
        old_set = _chat_ws.get(old)
        if old_set:
            _record_disconnect_mid_stream(ws, old)
            old_set.discard(ws)
            if not old_set:
                _chat_ws.pop(old, None)
        # WSDIAG
        log(f"WSDIAG detach ws={id(ws) & 0xFFFFFF:06x} was={old[:8]} set={len(_chat_ws.get(old, ()))}")


# ---------------------------------------------------------------------------
# Active WS liveness probe
# ---------------------------------------------------------------------------
#
# Starlette's client_state is REACTIVE — it only flips to DISCONNECTED when
# an I/O call raises. TCP connections that die silently (iOS cellular↔WiFi
# handoff, NAT rebind, laptop lid close) leave client_state == CONNECTED
# until the next send fails. Between fan-out frames the viewer set can go
# to 0 before the client reconnects, so subsequent sends fall into the void.
#
# Fix: periodic server→client ping. A successful send keeps the socket warm
# and detects dead sockets via the send exception. Evict on failure.

_LIVENESS_INTERVAL_SEC = 15
# If no client ping has arrived in this many seconds, consider the ws dead
# even if outbound sends still appear to succeed (half-open TCP — outbound
# buffer still accepts writes, but the client has stopped reading). The web
# client heartbeats every 5s and iOS similar, so 30s = 6 missed heartbeats.
_PING_STALE_SEC = 30
_liveness_task: asyncio.Task | None = None

# Per-ws timestamp of the most recent client→server ping. Seeded on attach
# (fresh sockets get a full grace period) and refreshed each time the WS
# handler receives {action:"ping"} via mark_client_ping().
_last_client_ping: "dict[WebSocket, float]" = {}


def mark_client_ping(ws: WebSocket) -> None:
    """Record the arrival time of a client ping. Called from the WS handler."""
    _last_client_ping[ws] = time.time()


async def _force_close_ws(ws: WebSocket) -> None:
    """Best-effort close so the client's onclose fires and triggers reconnect.

    Without this, evicting from _chat_ws only removes the ws from the
    server's fan-out set — the client still sees readyState=OPEN and thinks
    everything is healthy, so no reconnect is scheduled. Closing the socket
    forces web/iOS onclose handlers to run and re-attach.
    """
    try:
        await ws.close(code=1011, reason="liveness_eviction")
    except Exception:
        pass


async def _probe_one_ws(ws: WebSocket) -> bool:
    """Send a server_ping frame. Return True if the send succeeded."""
    try:
        await ws.send_json({"type": "server_ping", "ts": int(time.time())})
        return True
    except Exception:
        return False


async def _ws_liveness_prober() -> None:
    """Periodically probe every attached WebSocket with a JSON ping.

    Runs forever. Each tick: snapshot _chat_ws, try send_json on each ws,
    evict any that fail. The send itself is the liveness signal — we don't
    need a pong because the client already tolerates unknown {type:...}
    messages and starlette raises immediately on a dead socket.
    """
    log("WSDIAG liveness prober started")
    while True:
        try:
            await asyncio.sleep(_LIVENESS_INTERVAL_SEC)
            # Snapshot to avoid mutating during iteration
            snapshot: list[tuple[str, WebSocket]] = []
            for chat_id, ws_set in list(_chat_ws.items()):
                for ws in list(ws_set):
                    snapshot.append((chat_id, ws))
            if not snapshot:
                continue
            evicted = 0
            now = time.time()
            for chat_id, ws in snapshot:
                # Skip if ws is clearly dead by state check (reactive path)
                if not _ws_is_alive(ws):
                    _vacuum_dead_ws(chat_id)
                    _last_client_ping.pop(ws, None)
                    await _force_close_ws(ws)
                    evicted += 1
                    continue
                # Ping-staleness check: half-open TCP sockets still accept
                # outbound writes (server_ping send succeeds) but the client
                # has stopped reading. The client-side heartbeat running every
                # 5s is the only end-to-end signal. If no ping has arrived in
                # _PING_STALE_SEC, treat the ws as dead regardless of whether
                # our outbound send would succeed.
                last_ping = _last_client_ping.get(ws, now)
                if now - last_ping > _PING_STALE_SEC:
                    ws_set = _chat_ws.get(chat_id)
                    if ws_set:
                        ws_set.discard(ws)
                        if not ws_set:
                            _chat_ws.pop(chat_id, None)
                    _ws_chat.pop(ws, None)
                    _last_client_ping.pop(ws, None)
                    await _force_close_ws(ws)
                    evicted += 1
                    log(
                        f"WSDIAG stale_ping_evict ws={id(ws) & 0xFFFFFF:06x} "
                        f"chat={chat_id[:8]} age={int(now - last_ping)}s"
                    )
                    continue
                ok = await _probe_one_ws(ws)
                if not ok:
                    # Send failed — ws is dead. Remove now, before a real
                    # stream frame gets wasted on it. Also close so the
                    # client's onclose fires and triggers reconnect.
                    ws_set = _chat_ws.get(chat_id)
                    if ws_set:
                        ws_set.discard(ws)
                        if not ws_set:
                            _chat_ws.pop(chat_id, None)
                    _ws_chat.pop(ws, None)
                    _last_client_ping.pop(ws, None)
                    await _force_close_ws(ws)
                    evicted += 1
                    log(f"WSDIAG probe_evict ws={id(ws) & 0xFFFFFF:06x} chat={chat_id[:8]}")
            if evicted:
                log(f"WSDIAG liveness tick probed={len(snapshot)} evicted={evicted}")
        except asyncio.CancelledError:
            log("WSDIAG liveness prober cancelled")
            raise
        except Exception as e:
            log(f"WSDIAG liveness prober error (non-fatal): {e}")


def start_liveness_prober() -> None:
    """Kick off the liveness prober exactly once. Idempotent."""
    global _liveness_task
    if _liveness_task is not None and not _liveness_task.done():
        return
    _liveness_task = asyncio.create_task(_ws_liveness_prober())


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

    # Save partial results from cancelled turn so they persist across refresh
    try:
        from agent_sdk import _partial_results
        partial = _partial_results.pop(chat_id, None)
        if partial and (partial.get("text") or partial.get("thinking") or partial.get("tool_events")):
            from db import _save_message
            duration_ms = int((time.monotonic() - partial.get("start", time.monotonic())) * 1000)
            tool_events_json = json.dumps(partial.get("tool_events", []))
            text = partial.get("text", "")
            if not text:
                text = "[Response canceled]"
            # Extract speaker info from the active entry
            speaker_id = ""
            speaker_name = ""
            speaker_avatar = ""
            for _, entry in active_entries:
                speaker_id = str(entry.get("profile_id") or "")
                speaker_name = str(entry.get("name") or "")
                speaker_avatar = str(entry.get("avatar") or "")
                break
            _save_message(
                chat_id, "assistant", text,
                tool_events=tool_events_json,
                thinking=partial.get("thinking", ""),
                duration_ms=duration_ms,
                speaker_id=speaker_id,
                speaker_name=speaker_name,
                speaker_avatar=speaker_avatar,
                canceled=True,
            )
            log(f"cancel-save: chat={chat_id} text={len(text)}chars thinking={len(partial.get('thinking',''))}chars tools={len(partial.get('tool_events',[]))} duration={duration_ms}ms")
    except Exception as e:
        log(f"cancel-save FAILED: chat={chat_id} {type(e).__name__}: {e}")

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
        _detach_ws(ws)


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
        servers = {
            name: {k: v for k, v in cfg.items() if k != "enabled"}
            for name, cfg in servers.items()
            if isinstance(cfg, dict) and cfg.get("enabled", True)
        }
        return env.rewrite_mcp_servers_for_workspace(servers)
    except (json.JSONDecodeError, OSError) as e:
        log(f"MCP config load failed: {e}")
        return {}


def _inject_execute_code_mcp(servers: dict, *, chat_id: str | None = None,
                              workspace: str | None = None,
                              permission_level: int = 2) -> dict:
    """Auto-inject the execute_code MCP server if Jupyter is installed."""
    if "execute_code" in servers:
        return servers  # user already configured it manually
    try:
        # Check if jupyter_client is available
        import jupyter_client  # noqa: F401
    except ImportError:
        return servers  # no Jupyter — skip
    mcp_script = APEX_ROOT / "server" / "local_model" / "mcp_execute_code.py"
    if not mcp_script.exists():
        return servers
    # Build env vars so the MCP server knows the chat context
    mcp_env = {"APEX_PERMISSION_LEVEL": str(permission_level)}
    if chat_id:
        mcp_env["APEX_CHAT_ID"] = chat_id
    if workspace:
        mcp_env["APEX_WORKSPACE"] = workspace
    servers = dict(servers)  # don't mutate caller's dict
    servers["execute_code"] = {
        "command": sys.executable,
        "args": [str(mcp_script)],
        "env": mcp_env,
    }
    return servers


def _inject_claim_store_mcp(servers: dict, *, chat_id: str | None = None) -> dict:
    """V3 v2 Step 1a — propagate the Apex chat_id to the claim_store MCP
    subprocess via APEX_CHAT_ID env, so the subprocess resolves chat_id
    server-side rather than trusting model-supplied args. Mirrors the
    Codex-path inject at tool_loop.py:999-1001, backend-agnostic.

    Idempotent and narrow: no-op when claim_store isn't configured (static
    config path absent) or when chat_id is None (sub-chat, dry-run).
    Mutates only env['APEX_CHAT_ID'] — preserves the static config's other
    env vars (APEX_DB_NAME, etc.).
    """
    if not chat_id or "claim_store" not in servers:
        return servers
    servers = dict(servers)  # don't mutate caller's dict
    spec = dict(servers["claim_store"])
    env = dict(spec.get("env") or {})
    env["APEX_CHAT_ID"] = chat_id
    spec["env"] = env
    servers["claim_store"] = spec
    return servers


def _inject_computer_use_mcp(servers: dict, *, chat_id: str | None = None,
                              permission_level: int = 2,
                              computer_use_target: str | None = None) -> dict:
    """Auto-inject the computer_use MCP server for macOS GUI automation.

    Only injects when:
      - platform is darwin
      - computer_use_target is a non-empty string
      - MCP script exists at server/local_model/mcp_computer_use.py
    """
    if sys.platform != "darwin":
        return servers
    if not (isinstance(computer_use_target, str) and computer_use_target.strip()):
        return servers
    if "computer_use" in servers:
        return servers  # user already configured it manually
    mcp_script = APEX_ROOT / "server" / "local_model" / "mcp_computer_use.py"
    if not mcp_script.exists():
        return servers
    mcp_env = {
        "APEX_CU_TARGET_BUNDLE": computer_use_target.strip(),
        "APEX_CU_CHAT_ID": chat_id or "",
        "APEX_CU_STATE_DIR": str(APEX_ROOT / "state" / "computer_use"),
        "APEX_PERMISSION_LEVEL": str(permission_level),
    }
    servers = dict(servers)  # don't mutate caller's dict
    servers["computer_use"] = {
        "command": sys.executable,
        "args": [str(mcp_script)],
        "env": mcp_env,
    }
    return servers


def _inject_interceptor_mcp(servers: dict, *, chat_id: str | None = None,
                             interceptor_enabled: bool = False) -> dict:
    """Auto-inject the Interceptor (browser-agent) MCP server.

    Only injects when:
      - interceptor_enabled is truthy on the chat row
      - MCP script exists at server/local_model/mcp_interceptor.py
      - The interceptor binary exists (~/.interceptor/bin/interceptor by
        default; override via env APEX_INTERCEPTOR_BIN)

    The MCP server itself is platform-agnostic, but Interceptor is macOS-only
    today so we skip on non-darwin to avoid spawning a doomed subprocess.
    """
    if not interceptor_enabled:
        return servers
    if sys.platform != "darwin":
        return servers
    if "interceptor" in servers:
        return servers
    mcp_script = APEX_ROOT / "server" / "local_model" / "mcp_interceptor.py"
    if not mcp_script.exists():
        return servers
    bin_path = os.environ.get("APEX_INTERCEPTOR_BIN") or str(
        (APEX_ROOT.parent.parent / ".interceptor" / "bin" / "interceptor").resolve()
        if False else os.path.expanduser("~/.interceptor/bin/interceptor")
    )
    if not os.path.exists(bin_path):
        # No binary installed — skip rather than injecting a guaranteed-fail tool.
        log(f"interceptor MCP skipped: binary missing at {bin_path}")
        return servers
    mcp_env = {
        "APEX_INT_CHAT_ID": chat_id or "",
        "APEX_INT_STATE_DIR": str(APEX_ROOT / "state" / "interceptor"),
        "APEX_INTERCEPTOR_BIN": bin_path,
    }
    servers = dict(servers)
    servers["interceptor"] = {
        "command": sys.executable,
        "args": [str(mcp_script)],
        "env": mcp_env,
    }
    return servers


_GUIDE_PROFILE_ID = "sys-guide"


def _inject_guide_tools_mcp(servers: dict) -> dict:
    """Auto-inject the guide config tools MCP server for guide sessions."""
    if "guide_tools" in servers:
        return servers  # already configured
    mcp_script = APEX_ROOT / "server" / "local_model" / "mcp_guide_tools.py"
    if not mcp_script.exists():
        return servers
    servers = dict(servers)
    servers["guide_tools"] = {
        "command": sys.executable,
        "args": [str(mcp_script)],
        "env": {"APEX_ROOT": str(APEX_ROOT)},
    }
    return servers


def _is_guide_session(client_key: str | None) -> bool:
    """Check if the client_key corresponds to a guide persona session."""
    if not client_key:
        return False
    # client_key is chat_id:profile_id for group agents, or just chat_id for solo
    if ":" in client_key:
        profile_id = client_key.split(":", 1)[1]
        return profile_id == _GUIDE_PROFILE_ID
    # Solo chat — check if the chat's profile is the guide
    chat_id = client_key
    try:
        chat = _get_chat(chat_id)
        if chat and str(chat.get("profile_id", "")) == _GUIDE_PROFILE_ID:
            return True
    except Exception:
        pass
    return False


def _resolve_profile_id_from_client_key(client_key: str | None) -> str:
    """Resolve the active profile ID for this SDK session.

    Group-agent client keys are formatted `chat_id:profile_id`; solo chats are
    just `chat_id` and the profile ID lives on the chat row.
    """
    if not client_key:
        return ""
    if ":" in client_key:
        return client_key.split(":", 1)[1]
    chat_id = client_key
    try:
        chat = _get_chat(chat_id)
        if chat:
            return str(chat.get("profile_id", "") or "")
    except Exception:
        return ""
    return ""


def _resolve_guide_extra_tools(client_key: str | None) -> frozenset[str] | None:
    """Return per-profile extra tool names (guide config, claim-store gate, etc).

    Kept under the original name so callers in the rest of streaming.py don't
    need to change; the implementation now delegates to the shared resolver in
    tool_access so the tool-loop path can re-use the same mapping.
    """
    profile_id = _resolve_profile_id_from_client_key(client_key)
    extras = resolve_profile_extra_tools(profile_id)
    return extras if extras else None


# V3 v1 gate-test personas that need claim_store__* MCP tool extras at
# chat-spawn. These profiles carry Level 1 tool_policy on their agent_profiles
# row (no way to express MCP patterns there), so the claim_store tools must be
# injected via extra_allowed_tools. Extend by adding IDs to this frozenset —
# no other code changes required.
#   9b9b990f = gate-test-haiku-clean  (backend=claude, model=haiku-4-5)
#   b32aac1b = gate-test-codex-weak   (backend=codex,  model=codex:gpt-5.4)
_CLAIM_STORE_GATE_PROFILES: frozenset[str] = frozenset({
    "9b9b990f",
    "b32aac1b",
})


def _resolve_claim_store_extra_tools(profile_id: str) -> frozenset[str] | None:
    """Return `claim_store__*` prefix for gate-test profiles, else None.

    Mirrors the shape of `_resolve_guide_extra_tools` but keyed on profile_id
    directly rather than tunneling through client_key → tool_access. The
    returned extras are unioned with the guide extras at the single call-site
    in `_build_sdk_options`.
    """
    if profile_id and profile_id in _CLAIM_STORE_GATE_PROFILES:
        return frozenset({"claim_store__*"})
    return None


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


def _make_sdk_tool_gate(
    level: int,
    *,
    allowed_commands: list[str] | None = None,
    client_key: str | None = None,
    chat_id: str | None = None,
    extra_allowed_tools: frozenset[str] | set[str] | None = None,
):
    async def _can_use_tool(tool_name: str, tool_input: dict, _context):
        allowed, message = tool_access_decision(
            tool_name,
            tool_input if isinstance(tool_input, dict) else {},
            level=level,
            allowed_commands=allowed_commands,
            workspace_paths=env.get_runtime_workspace_paths(),
            audit_context={
                "source": "sdk",
                "client_key": client_key or "",
                "chat_id": chat_id or "",
            },
            extra_allowed_tools=extra_allowed_tools,
        )
        if not allowed:
            return PermissionResultDeny(
                message=message,
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
    client_key: str | None = None,
    chat_id: str | None = None,
    extra_allowed_tools: frozenset[str] | set[str] | None = None,
) -> tuple[bool, str]:
    return tool_access_decision(
        tool_name,
        tool_input if isinstance(tool_input, dict) else {},
        level=level,
        allowed_commands=allowed_commands,
        workspace_paths=env.get_runtime_workspace_paths(),
        audit_context={
            "source": "sdk",
            "client_key": client_key or "",
            "chat_id": chat_id or "",
        },
        extra_allowed_tools=extra_allowed_tools,
    )


def _make_sdk_pre_tool_use_hook(
    level: int,
    *,
    allowed_commands: list[str] | None = None,
    client_key: str | None = None,
    chat_id: str | None = None,
    extra_allowed_tools: frozenset[str] | set[str] | None = None,
):
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
            client_key=client_key,
            chat_id=chat_id,
            extra_allowed_tools=extra_allowed_tools,
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
    workspace_root = env.get_runtime_workspace_root()
    workspace_paths = env.get_runtime_workspace_paths_list()
    # Extra workspace roots beyond the primary (colon-separated APEX_WORKSPACE)
    extra_dirs = [
        root for root in workspace_paths[1:]
        if root and root != str(workspace_root)
    ]
    # Resolve guide-specific extra tools if this is a guide session
    extra_allowed_tools = _resolve_guide_extra_tools(client_key)
    # Union in claim_store__* for V3 gate-test profiles (Day 2b).
    _profile_id_for_extras = _resolve_profile_id_from_client_key(client_key)
    _claim_store_extras = _resolve_claim_store_extra_tools(_profile_id_for_extras)
    if _claim_store_extras:
        extra_allowed_tools = frozenset((extra_allowed_tools or frozenset()) | _claim_store_extras)
    opts = ClaudeAgentOptions(
        model=model or MODEL,
        cwd=str(workspace_root),
        permission_mode=_sdk_permission_mode_for_level(permission_level),
        max_turns=50,
        resume=session_id,
        setting_sources=["user"],
        add_dirs=extra_dirs,
        # Extended thinking for Opus 4.7:
        #   - 4.7 defaults thinking.display="omitted" → empty pills.
        #   - {"type":"enabled",budget_tokens:N} returns 400 on 4.7 — use
        #     adaptive; effort="high" tunes depth (GA, no beta header).
        #   - `display` isn't a first-class SDK field yet, so route via
        #     extra_args → bundled CLI's hidden --thinking-display flag
        #     (requires CLI >= 2.1.111 / claude-agent-sdk >= 0.1.60).
        thinking={"type": "adaptive"},
        effort="high",
        extra_args={"thinking-display": "summarized"},
        can_use_tool=_make_sdk_tool_gate(
            permission_level,
            allowed_commands=allowed_commands,
            client_key=client_key,
            chat_id=chat_id,
            extra_allowed_tools=extra_allowed_tools,
        ),
        hooks={
            "PreToolUse": [
                HookMatcher(
                    matcher=".*",
                    hooks=[
                        _make_sdk_pre_tool_use_hook(
                            permission_level,
                            allowed_commands=allowed_commands,
                            client_key=client_key,
                            chat_id=chat_id,
                            extra_allowed_tools=extra_allowed_tools,
                        )
                    ],
                )
            ]
        },
    )
    mcp_servers = _load_mcp_servers()
    # Auto-inject execute_code MCP server if Jupyter is available
    mcp_servers = _inject_execute_code_mcp(mcp_servers, chat_id=chat_id,
                                             workspace=str(workspace_root),
                                             permission_level=permission_level)
    # V3 v2 Step 1a — propagate chat_id to claim_store subprocess env.
    mcp_servers = _inject_claim_store_mcp(mcp_servers, chat_id=chat_id)
    # Auto-inject computer_use MCP server when the chat has a target bundle-ID
    # set (macOS only). Absence of a target means no injection, so the tools
    # are simply unavailable — no chat-aware allowlist needed.
    computer_use_target: str | None = None
    if chat_id:
        try:
            _chat_row = _get_chat(chat_id)
            if _chat_row:
                computer_use_target = _chat_row.get("computer_use_target") or None
        except Exception:
            computer_use_target = None
    mcp_servers = _inject_computer_use_mcp(mcp_servers, chat_id=chat_id,
                                            permission_level=permission_level,
                                            computer_use_target=computer_use_target)
    # Auto-inject Interceptor (browser-agent) MCP when the chat has opted in.
    interceptor_enabled = False
    if chat_id:
        try:
            _chat_row2 = _get_chat(chat_id)
            if _chat_row2:
                interceptor_enabled = bool(_chat_row2.get("interceptor_enabled"))
        except Exception:
            interceptor_enabled = False
    mcp_servers = _inject_interceptor_mcp(mcp_servers, chat_id=chat_id,
                                           interceptor_enabled=interceptor_enabled)
    # Auto-inject guide config tools MCP server for guide sessions
    if extra_allowed_tools:
        mcp_servers = _inject_guide_tools_mcp(mcp_servers)
        log(f"Guide tools MCP injected for client_key={client_key}")
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
    _stream_epoch_nonce[chat_id] = uuid.uuid4().hex[:8]
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
    # Attach seq + server_epoch to payload so client can dedupe events
    # that arrive via both live-send and attach-replay paths.
    payload["seq"] = seq
    payload["epoch"] = f"{_SERVER_EPOCH}:{_stream_epoch_nonce.get(chat_id, '0')}"
    _stream_buffers[chat_id].append((seq, dict(payload)))
    try:
        with open(_stream_journal_path(chat_id), "a") as f:
            f.write(json.dumps(payload) + "\n")
    except (OSError, ValueError):
        pass


# ---------------------------------------------------------------------------
# Stream event sending
# ---------------------------------------------------------------------------

_drop_logged: set[str] = set()  # tracks (chat:stream) combos already logged as dropped
_wsdiag_text_logged: set[str] = set()  # WSDIAG: first text frame per stream only (avoid flood)

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
    # WSDIAG: observability for WS streaming race bug. Log non-text frames
    # always; text frames only on first-per-stream to avoid flooding.
    _ptype = str(payload.get("type") or "")
    _should_log = False
    if _ptype != "text":
        _should_log = True
    elif payload_stream_id:
        _tkey = f"{chat_id}:{payload_stream_id}"
        if _tkey not in _wsdiag_text_logged:
            _wsdiag_text_logged.add(_tkey)
            _should_log = True
    send_lock = _get_chat_send_lock(chat_id)
    async with send_lock:
        # Vacuum zombie WebSockets (disconnected but still registered) before
        # iterating, so the first frame of a new stream doesn't get wasted on
        # a dead socket. This is the defense against the race where _detach_ws
        # hasn't run yet (e.g. client closed during a prior send, iOS network
        # transition, browser tab backgrounded).
        _vacuum_dead_ws(chat_id)
        ws_set = _chat_ws.get(chat_id)
        if _should_log:
            _recips = len(ws_set) if ws_set else 0
            _seq = payload.get("seq", "_")
            log(f"WSDIAG send chat={chat_id[:8]} type={_ptype} sid={payload_stream_id[:8]} seq={_seq} recips={_recips}")
        if not ws_set:
            drop_key = f"{chat_id}:{payload_stream_id}"
            if drop_key not in _drop_logged:
                _drop_logged.add(drop_key)
                log(f"stream events dropping: chat={chat_id[:8]} sid={payload_stream_id[:8]} (no viewers, suppressing repeats)")
            return
        dead: list[WebSocket] = []
        for ws in list(ws_set):
            ok = await _safe_ws_send_json(ws, payload, chat_id=chat_id)
            if not ok:
                dead.append(ws)
        for ws in dead:
            ws_set.discard(ws)
            log(f"ws evicted from chat={chat_id[:8]} after send failure (remaining viewers={len(ws_set)})")
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


async def _emit_claim_gate_summary(chat_id: str, stream_id: str) -> None:
    """V3 v2 Step 3 Commit 4 — post-stream claim gate summary.

    Runs `claim_gate.extract_and_tag` against the assistant's final prose
    + this turn's claim_assert rows, persists the full trace JSON to the
    `claim_gate_traces` side-table, and emits exactly one
    `claim_gate_summary` WS event to the chat's viewers.

    MUST be called AFTER `stream_end` in the same coroutine (ordering is
    part of the wire contract — clients gate their summary handling on
    having already received stream_end).

    Fail-open: every exception path here logs at WARN and returns. The
    streaming lifecycle must never observe an error out of this helper.
    """
    if not _CLAIM_GATE_SUMMARY_ENABLED:
        return
    t0 = time.monotonic()
    turn_id: int = 0
    try:
        # The assistant message for this turn is persisted by
        # ws_handler._save_message BEFORE _finalize_stream runs, so we can
        # read it back here to derive (turn_id, assistant_text).
        with _db_lock:
            conn = _get_db()
            try:
                row = conn.execute(
                    "SELECT content FROM messages "
                    "WHERE chat_id=? AND role='assistant' "
                    "ORDER BY created_at DESC, id DESC LIMIT 1",
                    (chat_id,),
                ).fetchone()
                if row is None:
                    return
                assistant_text = (row[0] or "")
                turn_id = int(conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE chat_id=? AND role='assistant'",
                    (chat_id,),
                ).fetchone()[0])
                assert_rows = conn.execute(
                    "SELECT text FROM claims "
                    "WHERE chat_id=? AND turn_id=? AND status='active'",
                    (chat_id, turn_id),
                ).fetchall()
            finally:
                conn.close()

        asserts = [{"text": (r[0] or "")} for r in assert_rows]

        # Lazy import so module load doesn't pay for the regexes unless
        # the gate is actually enabled.
        from claim_gate import extract_and_tag
        trace = extract_and_tag(assistant_text, asserts)

        trace_json = json.dumps(trace, separators=(",", ":"), sort_keys=True)
        byte_len = len(trace_json.encode("utf-8"))
        now_iso = (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        trace_id = str(uuid.uuid7())
        with _db_lock:
            conn = _get_db()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO claim_gate_traces "
                    "(id, chat_id, turn_id, created_at, trace_json, byte_len, schema_version) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (trace_id, chat_id, turn_id, now_iso, trace_json, byte_len,
                     _CLAIM_GATE_SUMMARY_SCHEMA_VERSION),
                )
                conn.commit()
            finally:
                conn.close()

        counts = {
            "grounded": len(trace.get("grounded", [])),
            "unverified": len(trace.get("unverified", [])),
            "speculation": len(trace.get("speculation", [])),
        }
        tag_rate = float(trace.get("tag_rate", 0.0))
        # v1 gate has no failure codes; Room E/F will populate this list
        # once the refusal-code taxonomy lands (spec §8 Q2 held-pending).
        failure_codes: list[str] = []

        payload = {
            "type": "claim_gate_summary",
            "chat_id": chat_id,
            "turn_id": turn_id,
            "tag_rate": round(tag_rate, 4),
            "counts": counts,
            "failure_codes": failure_codes,
            "trace_ref": {
                "chat_id": chat_id,
                "turn_id": turn_id,
                "schema_version": _CLAIM_GATE_SUMMARY_SCHEMA_VERSION,
            },
            "emitted_at": now_iso,
            "stream_id": stream_id,
        }
        wire_bytes = len(json.dumps(payload).encode("utf-8"))
        if wire_bytes > _CLAIM_GATE_SUMMARY_WIRE_CAP:
            # Defensive (current payload has no extracted-claim detail so
            # we're already minimal; reserve space for future field growth
            # by trimming failure_codes first).
            payload["failure_codes"] = []
            wire_bytes = len(json.dumps(payload).encode("utf-8"))

        await _send_stream_event(chat_id, payload)
        dt_ms = int((time.monotonic() - t0) * 1000)
        log(
            f"claim_gate_summary emit: chat={chat_id[:8]} turn={turn_id} "
            f"tag_rate={tag_rate:.3f} byte_len={byte_len} wire={wire_bytes}B ms={dt_ms}"
        )
    except Exception as e:  # noqa: BLE001 — fail-open is the contract
        log(
            f"claim_gate_summary emit FAILED (swallowed): "
            f"chat={chat_id[:8]} turn={turn_id} err={type(e).__name__}: {e}"
        )


async def _finalize_stream(chat_id: str, stream_id: str, task: asyncio.Task | None = None,
                           *, is_group_chat: bool = False, send_stream_end: bool = True,
                           preserve_journal: bool = False) -> None:
    try:
        if send_stream_end:
            await _send_stream_event(chat_id, {"type": "stream_end", "chat_id": chat_id, "stream_id": stream_id})
            log(f"stream_end sent: chat={chat_id} viewers={len(_chat_ws.get(chat_id, set()))}")
            # V3 v2 Step 3 Commit 4 — emit claim_gate_summary AFTER stream_end
            # in the same coroutine (ordering invariant per spec §5.3).
            await _emit_claim_gate_summary(chat_id, stream_id)
    finally:
        _drop_logged.discard(f"{chat_id}:{stream_id}")
        _clear_stream_text_filter(chat_id, stream_id)
        _remove_active_send_task(chat_id, stream_id, task if isinstance(task, asyncio.Task) else None)
        if is_group_chat:
            await _send_active_streams(chat_id)
        if not _has_active_stream(chat_id):
            _stream_buffers.pop(chat_id, None)
            _stream_seq.pop(chat_id, None)
            _stream_epoch_nonce.pop(chat_id, None)
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
        log(f"ws_send FAIL #{fc} (ok={sc}): chat={chat_id[:8]} type={payload.get('type')} sid={str(payload.get('stream_id',''))[:8]} {type(e).__name__}: {e}")
        return False
