"""WebSocket endpoint and message dispatch.

Layer 5: imports from all lower layers (streaming, context, skills,
agent_sdk, backends, db, state, etc.).  Registers a single
``/ws`` WebSocket route via an APIRouter so apex.py can
``app.include_router(ws_router)``.
"""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import os
import re
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import env
from env import SSL_CERT, SSL_CA, MODEL, DEBUG, WORKSPACE, ENABLE_SKILL_DISPATCH, SDK_QUERY_TIMEOUT

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from license import get_license_manager

from log import log
from db import (
    _get_chat, _update_chat, _update_chat_settings,
    _get_group_members,
    _get_chat_tool_policy, _get_profile_tool_policy, _set_profile_tool_policy,
    _get_recent_messages_text,
    _save_message,
    _get_latest_user_attachments,
)
from model_dispatch import _get_model_backend, get_available_model_ids
from state import (
    _compaction_summaries, _recovery_pending,
    _group_profile_override,
    _chat_locks, _chat_ws, _ws_chat,
    _stream_buffers,
    _current_stream_id, _current_group_profile_id,
    _queued_turns,
)
from streaming import (
    _make_stream_id, _attach_ws, _detach_ws,
    _get_active_stream_entries, _has_active_stream,
    _set_active_send_task, _update_active_send_task, _remove_active_send_task,
    _cancel_chat_streams,
    _make_options, _get_or_create_client,
    _register_client, _has_client,
    _get_chat_lock, _get_chat_send_lock,
    _reset_stream_buffer, _cleanup_stream_journal, _load_journal_events,
    _send_stream_event, _send_active_streams, _finalize_stream,
    _disconnect_client, _set_model,
    _safe_ws_send_json, _is_valid_chat_id,
)
from context import (
    _generate_recovery_context, _store_recovery_context, _maybe_compact_chat,
    _get_whisper_text,
    _resolve_group_agent, _resolve_memory_profile_id,
    _clear_session_context, _has_session_context,
    ENABLE_SUBCONSCIOUS_WHISPER,
)
from skills import (
    _parse_skill_command, _run_recall, _run_improve, _handle_skill,
    _DIRECT_SKILL_HANDLERS, _CONTEXT_SKILLS, _THINKING_SKILLS,
    _GATE_ENABLED, _get_pending_approvals, _resolve_approval, _log_skill_invocation,
)
from agent_sdk import (
    _build_turn_payload, _websocket_origin_allowed, _run_query_turn,
    _load_attachment,
)
from memory_extract import _extract_and_save_memories
from backends import (
    _public_codex_error_message,
    _run_codex_chat,
    _run_ollama_chat,
    validate_backend_attachments,
)
from mtls import has_verified_peer_cert, mtls_required

try:
    from claude_agent_sdk import ClaudeSDKClient
except ImportError:
    ClaudeSDKClient = None  # type: ignore[misc,assignment]

# Config imported from env.py

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
ws_router = APIRouter()
MAX_QUEUED_TURNS_PER_KEY = 2
MAX_MENTION_DEPTH = 25

# Premium module — injected by apex.py when loaded. Provides group routing
# and agent relay functions. When None, all group routing is disabled.
_ws_premium = None


def _group_member_aliases(member: dict) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    candidates = [
        str(member.get("name") or "").strip(),
        str(member.get("profile_id") or "").strip(),
    ]
    profile_id = str(member.get("profile_id") or "").strip()
    if profile_id:
        candidates.append(re.sub(r"[-_]+", " ", profile_id).strip())
    for candidate in candidates:
        alias = " ".join(candidate.split())
        if not alias:
            continue
        folded = alias.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        aliases.append(alias)
    aliases.sort(key=len, reverse=True)
    return aliases


def _match_group_mention_prefix(text: str, alias: str) -> int:
    if not text or not alias:
        return 0
    prefix = f"@{alias}"
    if text[: len(prefix)].casefold() != prefix.casefold():
        return 0
    next_char = text[len(prefix): len(prefix) + 1]
    if next_char and not re.match(r"[\s:,.!?-]", next_char):
        return 0
    return len(prefix)


def _find_group_mention_matches(prompt: str, members: list[dict]) -> list[tuple[int, int, dict | None]]:
    matches: list[tuple[int, int, dict | None]] = []
    idx = 0
    while idx < len(prompt):
        at_pos = prompt.find("@", idx)
        if at_pos < 0:
            break
        prev_char = prompt[at_pos - 1: at_pos] if at_pos > 0 else ""
        if prev_char and re.match(r"[\w]", prev_char):
            idx = at_pos + 1
            continue
        text = prompt[at_pos:]
        matched_member: dict | None = None
        matched_len = _match_group_mention_prefix(text, "all")
        for member in members:
            for alias in _group_member_aliases(member):
                prefix_len = _match_group_mention_prefix(text, alias)
                if prefix_len > matched_len:
                    matched_member = member
                    matched_len = prefix_len
        if not matched_len:
            idx = at_pos + 1
            continue
        matches.append((at_pos, at_pos + matched_len, matched_member))
        idx = at_pos + matched_len
    return matches


def _strip_group_leading_mentions(prompt: str, members: list[dict] | None = None) -> str:
    if not members:
        return prompt.strip()
    matches = _find_group_mention_matches(prompt, members)
    if not matches:
        return prompt.strip()
    parts: list[str] = []
    cursor = 0
    for start, end, _member in matches:
        parts.append(prompt[cursor:start])
        cursor = end
        while cursor < len(prompt) and prompt[cursor] in " \t:,.!?-":
            cursor += 1
    parts.append(prompt[cursor:])
    stripped = "".join(parts)
    stripped = re.sub(r"\s{2,}", " ", stripped)
    return stripped.strip()


def _find_group_mentioned_members(prompt: str, members: list[dict]) -> list[dict]:
    mentioned: list[dict] = []
    seen_profile_ids: set[str] = set()
    for _start, _end, matched_member in _find_group_mention_matches(prompt, members):
        if matched_member is None:
            for member in members:
                profile_id = str(member.get("profile_id") or "")
                if not profile_id or profile_id in seen_profile_ids:
                    continue
                seen_profile_ids.add(profile_id)
                mentioned.append(member)
            continue
        profile_id = str(matched_member.get("profile_id") or "")
        if profile_id and profile_id not in seen_profile_ids:
            seen_profile_ids.add(profile_id)
            mentioned.append(matched_member)
    return mentioned


def _find_specific_group_mentioned_members(prompt: str, members: list[dict]) -> list[dict]:
    mentioned: list[dict] = []
    seen_profile_ids: set[str] = set()
    for _start, _end, matched_member in _find_group_mention_matches(prompt, members):
        if matched_member is None:
            continue
        profile_id = str(matched_member.get("profile_id") or "")
        if profile_id and profile_id not in seen_profile_ids:
            seen_profile_ids.add(profile_id)
            mentioned.append(matched_member)
    return mentioned


def _has_group_broadcast_mention(prompt: str, members: list[dict]) -> bool:
    return any(matched_member is None for _start, _end, matched_member in _find_group_mention_matches(prompt, members))


def _resolve_group_agent_fallback(chat_id: str, prompt: str) -> dict | None:
    members = _get_group_members(chat_id)
    if not members:
        return None
    mentioned = _find_group_mentioned_members(prompt, members)
    if not mentioned:
        return None
    return {
        **mentioned[0],
        "clean_prompt": _strip_group_leading_mentions(prompt, members),
    }


def _get_multi_dispatch_targets_fallback(chat_id: str, prompt: str, group_agent: dict | None) -> list[dict]:
    if not group_agent:
        return []
    members = _get_group_members(chat_id)
    if not members:
        return []
    return _find_group_mentioned_members(prompt, members)


def _merge_group_dispatch_targets(*target_lists: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen_profile_ids: set[str] = set()
    for target_list in target_lists:
        for target in target_list:
            profile_id = str(target.get("profile_id") or "")
            if not profile_id or profile_id in seen_profile_ids:
                continue
            seen_profile_ids.add(profile_id)
            merged.append(target)
    return merged


def _strip_group_target_prefix(prompt: str, member: dict) -> str:
    text = prompt.lstrip()
    leading_ws = prompt[: len(prompt) - len(text)]
    for alias in _group_member_aliases(member):
        matched_len = _match_group_mention_prefix(text, alias)
        if not matched_len:
            continue
        stripped = text[matched_len:].lstrip(" \t:,.!?-")
        return f"{leading_ws}{stripped}".strip()
    return prompt


def _resolve_direct_group_agent(chat_id: str, prompt: str, target_profile_id: str) -> dict | None:
    for member in _get_group_members(chat_id):
        if str(member.get("profile_id") or "") != target_profile_id:
            continue
        return {**member, "clean_prompt": _strip_group_target_prefix(prompt, member)}
    return None


def _resolve_primary_group_agent(chat_id: str, prompt: str) -> dict | None:
    members = _get_group_members(chat_id)
    if not members:
        return None
    primary = next((m for m in members if m.get("is_primary")), members[0])
    return {**primary, "clean_prompt": prompt}


def _resolve_effective_tool_policy(chat_id: str, chat: dict, group_agent: dict | None) -> dict:
    profile_id = str(group_agent.get("profile_id") or "").strip() if group_agent else str(chat.get("profile_id") or "").strip()
    policy = _get_profile_tool_policy(profile_id) if profile_id else _get_chat_tool_policy(chat_id)
    effective_policy = dict(policy)
    elevated_until = str(effective_policy.get("elevated_until") or "").strip()
    if not profile_id or not elevated_until:
        return effective_policy
    try:
        expires_at = datetime.fromisoformat(elevated_until)
    except ValueError:
        expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at > datetime.now(timezone.utc):
        return effective_policy
    effective_policy["level"] = int(effective_policy.get("default_level", effective_policy.get("level", 1)))
    effective_policy["elevated_until"] = None
    try:
        _set_profile_tool_policy(
            profile_id,
            effective_policy,
            default_level=int(effective_policy.get("default_level", effective_policy.get("level", 1))),
        )
    except KeyError:
        pass
    return effective_policy


def _public_backend_error_message(backend: str, err: Exception | str) -> str:
    raw = str(err or "").strip()
    if backend == "codex":
        return _public_codex_error_message(raw)
    if backend in {"ollama", "xai", "mlx"}:
        return "The model backend hit an internal error while responding. Retry the turn."
    # Auth errors — give the user something actionable
    _AUTH_HINTS = ("Not logged in", "Invalid API key", "auth error", "Please run /login")
    if any(h in raw for h in _AUTH_HINTS):
        return ("Claude is not authenticated. Open Terminal and run: claude auth login — "
                "then retry. If using an API key, check it in [Credentials](/admin/#models).")
    return "The request failed while generating a response. Retry the turn."


def _attachment_refs_json(loaded: list[dict]) -> tuple[str, list[dict]]:
    refs = [
        {
            "id": item["id"],
            "type": item["type"],
            "name": item["name"],
            "url": f"/api/uploads/{item['id']}.{item['ext']}",
            "mimeType": item.get("mimeType") or "",
            "size": len(item.get("data") or b""),
        }
        for item in loaded
    ]
    return json.dumps(refs), refs


async def _broadcast_chat_event(chat_id: str, payload: dict) -> None:
    for ws in list(_chat_ws.get(chat_id, set())):
        await _safe_ws_send_json(ws, payload, chat_id=chat_id)


def _enqueue_turn(
    lock_key: str,
    websocket: WebSocket,
    data: dict,
    *,
    chat_id: str,
    stream_id: str,
    group_agent: dict | None,
) -> int | None:
    queue = _queued_turns.setdefault(lock_key, deque())
    if len(queue) >= MAX_QUEUED_TURNS_PER_KEY:
        return None
    queue.append({
        "websocket": websocket,
        "data": dict(data),
        "chat_id": chat_id,
        "stream_id": stream_id,
        "name": group_agent["name"] if group_agent else "",
        "avatar": group_agent["avatar"] if group_agent else "",
        "profile_id": group_agent["profile_id"] if group_agent else "",
    })
    return len(queue)


def _purge_queued_turns_for_ws(websocket: WebSocket) -> int:
    removed = 0
    empty_keys: list[str] = []
    for lock_key, queue in list(_queued_turns.items()):
        kept = deque(item for item in queue if item.get("websocket") is not websocket)
        removed += len(queue) - len(kept)
        if kept:
            _queued_turns[lock_key] = kept
        else:
            empty_keys.append(lock_key)
    for lock_key in empty_keys:
        _queued_turns.pop(lock_key, None)
    return removed


def _launch_next_queued_turn(lock_key: str) -> None:
    queue = _queued_turns.get(lock_key)
    if not queue:
        return

    entry = queue.popleft()
    if not queue:
        _queued_turns.pop(lock_key, None)

    websocket = entry["websocket"]
    send_data = dict(entry["data"])
    chat_id = str(entry.get("chat_id") or send_data.get("chat_id") or "")
    stream_id = str(entry.get("stream_id") or send_data.get("stream_id") or "")
    task = asyncio.create_task(_handle_send_action(websocket, send_data))
    if chat_id and stream_id:
        _set_active_send_task(
            chat_id,
            stream_id,
            task,
            name=str(entry.get("name") or ""),
            avatar=str(entry.get("avatar") or ""),
            profile_id=str(entry.get("profile_id") or ""),
        )

        def _cleanup_send_task(t: asyncio.Task, cid=chat_id, sid=stream_id):
            _remove_active_send_task(cid, sid, t)

        task.add_done_callback(_cleanup_send_task)


async def _emit_stream_queued(
    chat_id: str,
    stream_id: str,
    *,
    websocket: WebSocket,
    group_agent: dict | None,
    position: int,
) -> None:
    payload = {
        "type": "stream_queued",
        "chat_id": chat_id,
        "stream_id": stream_id,
        "position": position,
        "queued_label": (
            f"Queued for {group_agent['name']}"
            if group_agent
            else "Queued for this chat"
        ),
    }
    if group_agent:
        payload["speaker_name"] = group_agent["name"]
        payload["speaker_avatar"] = group_agent["avatar"]
        payload["speaker_id"] = group_agent["profile_id"]
    await _broadcast_chat_event(chat_id, payload)
    if _ws_chat.get(websocket) != chat_id:
        await _safe_ws_send_json(websocket, payload, chat_id=chat_id)


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # S-04: Verify client cert on WebSocket connections (defense-in-depth)
    if mtls_required(SSL_CERT, SSL_CA) and not has_verified_peer_cert(websocket.scope):
        await websocket.close(code=1008)
        return

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
                attach_id = data.get("chat_id", "")
                if attach_id:
                    if not _is_valid_chat_id(attach_id):
                        await websocket.send_json({"type": "error", "message": "Invalid chat_id"})
                        continue
                    _attach_ws(websocket, attach_id)  # B-42: move WS subscription immediately
                    lock = _chat_locks.get(attach_id)
                    if lock is None:
                        for k, v in _chat_locks.items():
                            if k.startswith(attach_id + ":") and v.locked():
                                lock = v
                                break
                    stream_running = bool(_get_active_stream_entries(attach_id))
                    if stream_running:
                        send_lock = _get_chat_send_lock(attach_id)
                        replayed = len(_stream_buffers.get(attach_id, ()))
                        async with send_lock:
                            replay_ok = True
                            active_entries = _get_active_stream_entries(attach_id)
                            active_stream_id = active_entries[0][0] if active_entries else ""
                            replay_ok = await _safe_ws_send_json(
                                websocket,
                                {"type": "stream_reattached", "chat_id": attach_id, "stream_id": active_stream_id},
                                chat_id=attach_id,
                            )
                            if replay_ok:
                                buffer_events = list(_stream_buffers.get(attach_id, ()))
                                if not buffer_events:
                                    buffer_events = _load_journal_events(attach_id)
                                    replayed = len(buffer_events)
                                for _, payload in buffer_events:
                                    replay_ok = await _safe_ws_send_json(websocket, payload, chat_id=attach_id)
                                    if not replay_ok:
                                        break
                            if replay_ok:
                                _attach_ws(websocket, attach_id)
                            if not replay_ok:
                                _detach_ws(websocket)
                        if replay_ok:
                            log(f"WS re-attached for chat={attach_id} (stream active, replayed={replayed})")
                    else:
                        _attach_ws(websocket, attach_id)

                        journal_events = _load_journal_events(attach_id)
                        if journal_events:
                            partial_parts = []
                            tool_chain_parts = []
                            tool_id_to_name = {}
                            for _, evt in journal_events:
                                evt_type = evt.get("type", "")
                                if evt_type == "text" and evt.get("text"):
                                    partial_parts.append(evt["text"])
                                elif evt_type == "tool_use":
                                    name = evt.get("name", "tool")
                                    inp = str(evt.get("input", ""))[:200]
                                    tool_chain_parts.append(f"- {name}: {inp}")
                                    tid = evt.get("id", "")
                                    if tid:
                                        tool_id_to_name[tid] = name
                                elif evt_type == "tool_result":
                                    content = str(evt.get("content", "")).strip()[:300]
                                    tid = evt.get("tool_use_id") or evt.get("id", "")
                                    tool_name = tool_id_to_name.get(tid, "")
                                    label = f"result ({tool_name})" if tool_name else "result"
                                    if content:
                                        tool_chain_parts.append(f"  {label}: {content}")
                                    else:
                                        tool_chain_parts.append(f"  {label}: (completed)")
                                elif evt_type == "result":
                                    # Backend terminal event — extract thinking if present
                                    thinking = str(evt.get("thinking", "")).strip()
                                    if thinking and not partial_parts:
                                        partial_parts.append(thinking[:500])
                            partial_text = "".join(partial_parts).strip()

                            if partial_text or tool_chain_parts:
                                save_content = partial_text or "(No text output)"
                                if tool_chain_parts:
                                    save_content += "\n\n**Tool chain in progress:**\n" + "\n".join(tool_chain_parts)
                                _save_message(attach_id, "assistant",
                                              save_content + "\n\n\u26a0\ufe0f _Response interrupted_",
                                              cost_usd=0, tokens_in=0, tokens_out=0)

                                if tool_chain_parts:
                                    tool_summary = "\n".join(tool_chain_parts[-6:])
                                    cont_prompt = (
                                        "Your previous response was interrupted mid-execution. "
                                        "The partial output and tool chain have been saved.\n\n"
                                        f"Tool chain at time of interruption:\n{tool_summary}\n\n"
                                        "Continue exactly where you left off. Do not repeat completed work."
                                    )
                                else:
                                    cont_prompt = (
                                        "Your previous response was interrupted mid-stream. "
                                        "The partial output has been saved. "
                                        "Please continue exactly where you left off."
                                    )

                                continuation_data = {
                                    "chat_id": attach_id,
                                    "prompt": cont_prompt,
                                    "stream_id": _make_stream_id(),
                                }
                                task = asyncio.create_task(_handle_send_action(websocket, continuation_data))
                                _set_active_send_task(attach_id, continuation_data["stream_id"], task)

                                def _cleanup_recovery(t, cid=attach_id, sid=continuation_data["stream_id"]):
                                    _remove_active_send_task(cid, sid, t)
                                task.add_done_callback(_cleanup_recovery)

                                log(f"stream recovery: chat={attach_id} partial={len(partial_text)} "
                                    f"tools={len(tool_chain_parts)} auto-continuing")
                            _cleanup_stream_journal(attach_id)

                        await _safe_ws_send_json(
                            websocket,
                            {"type": "attach_ok", "chat_id": attach_id},
                            chat_id=attach_id,
                        )
                continue

            if action == "set_model":
                model = str(data.get("model", "")).strip()
                admin_token = str(data.get("admin_token", ""))
                if not model:
                    await websocket.send_json({"type": "error", "message": "Model is required"})
                    continue
                if not env.ADMIN_TOKEN:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Global model changes over WebSocket are disabled; use the admin API",
                    })
                    continue
                if not hmac.compare_digest(admin_token.encode(), env.ADMIN_TOKEN.encode()):
                    await websocket.send_json({"type": "error", "message": "Admin authorization required"})
                    continue
                if model not in get_available_model_ids():
                    await websocket.send_json({"type": "error", "message": "Unsupported model"})
                    continue
                if model == MODEL:
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
                if model not in get_available_model_ids():
                    await websocket.send_json({"type": "error", "message": "Unsupported model"})
                    continue
                if not _is_valid_chat_id(chat_id):
                    await websocket.send_json({"type": "error", "message": "Invalid chat_id"})
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
                if _has_client(chat_id):
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
                if send_chat_id and not _is_valid_chat_id(send_chat_id):
                    await websocket.send_json({"type": "error", "message": "Invalid chat_id"})
                    continue
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
                    if not _is_valid_chat_id(chat_id):
                        await websocket.send_json({"type": "error", "message": "Invalid chat_id"})
                        continue
                    await _cancel_chat_streams(chat_id, stream_id=requested_stream_id)

    except WebSocketDisconnect as wd:
        log(f"websocket disconnected ws={ws_id} code={wd.code if hasattr(wd, 'code') else '?'}")
    except Exception as e:
        log(f"websocket error ws={ws_id}: {type(e).__name__}: {e}")
    finally:
        purged = _purge_queued_turns_for_ws(websocket)
        _detach_ws(websocket)
        if purged:
            log(f"websocket cleanup ws={ws_id}: purged {purged} queued turn(s)")
        if active_tasks:
            log(f"websocket cleanup ws={ws_id}: {len(active_tasks)} send task(s) continue in background")


async def _handle_send_action(websocket: WebSocket, data: dict) -> None:
    chat_id = data.get("chat_id", "")
    prompt = str(data.get("prompt", "")).strip()
    attachments = data.get("attachments", [])
    stream_id = str(data.get("stream_id") or _make_stream_id())
    if not (prompt or attachments) or not chat_id:
        return
    if not _is_valid_chat_id(chat_id):
        await websocket.send_json({"type": "error", "message": "Invalid chat_id"})
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
                        await _send_stream_event(chat_id, {"type": "stream_end", "chat_id": chat_id, "stream_id": stream_id})
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
                        prompt = skill_args
                elif skill == "improve" and skill_args:
                    log(f"Skill-improver: analyzing {skill_args[:60]!r}")
                    improve_output = await asyncio.to_thread(_run_improve, skill_args)
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

    # --- Groups are read-only after trial/license expiry ---
    if is_group_chat:
        _lm = get_license_manager()
        if not (env.GROUPS_ENABLED or _lm.is_feature_enabled("groups")):
            lic = _lm.status()
            trial_str = "expired" if not lic["trial_active"] else f"active ({lic['trial_days_remaining']}d remaining)"
            await _safe_ws_send_json(websocket, {
                "type": "error",
                "message": f"Groups are read-only — trial {trial_str}. Upgrade to Apex Pro at https://useash.dev/activate",
                "premium_required": True,
            }, chat_id=chat_id)
            return

    chat_model = chat.get("model") or MODEL
    backend = _get_model_backend(chat_model)
    mention_depth = int(data.get("_mention_depth", 0) or 0)
    mention_chain: list[str] = list(data.get("_mention_chain") or [])
    handoff_source = str(data.get("_source") or "").strip().lower()
    suppress_user_message = bool(data.get("_suppress_user_message"))

    # --- Group @mention routing (premium) ---
    group_agent = None
    target_profile_id = str(data.get("target_agent") or "").strip()
    if target_profile_id and is_group_chat:
        if _ws_premium:
            group_agent = _ws_premium.resolve_target_agent(chat_id, prompt, target_profile_id)
        if not group_agent:
            group_agent = _resolve_direct_group_agent(chat_id, prompt, target_profile_id)
        if not group_agent:
            await _safe_ws_send_json(
                websocket,
                {"type": "error", "message": f"Target agent not found: {target_profile_id}"},
                chat_id=chat_id,
            )
            return
    if group_agent is None:
        group_agent = _resolve_group_agent(chat_id, chat, prompt)
        if group_agent is None and is_group_chat:
            group_agent = _resolve_group_agent_fallback(chat_id, prompt)
        if group_agent is None and is_group_chat:
            group_agent = _resolve_primary_group_agent(chat_id, prompt)
    permission_policy = _resolve_effective_tool_policy(chat_id, chat, group_agent)
    permission_level = int(permission_policy.get("level", 1))
    allowed_commands = list(permission_policy.get("allowed_commands") or [])
    if (
        group_agent
        and is_group_chat
        and handoff_source == "agent"
        and permission_policy.get("invoke_policy") == "owner_only"
    ):
        log(
            f"owner-only dispatch blocked: chat={chat_id[:8]} "
            f"agent={group_agent['name']} source=agent"
        )
        return
    mention_prompt = prompt
    if (
        group_agent
        and is_group_chat
        and not suppress_user_message
        and handoff_source != "agent"
    ):
        premium_multi_targets: list[dict] = []
        get_multi_dispatch_targets = getattr(_ws_premium, "get_multi_dispatch_targets", None) if _ws_premium else None
        if get_multi_dispatch_targets:
            premium_multi_targets = get_multi_dispatch_targets(chat_id, prompt, group_agent, data) or []
        fallback_multi_targets = _get_multi_dispatch_targets_fallback(chat_id, prompt, group_agent)
        multi_targets = _merge_group_dispatch_targets(premium_multi_targets, fallback_multi_targets)
        for t in multi_targets:
            if str(t.get("profile_id") or "") == str(group_agent.get("profile_id") or ""):
                log(f"user multi-dispatch blocked (self-target): {group_agent['name']} chat={chat_id[:8]}")
                continue
            # Pass attachment refs directly so secondary agents don't race
            # with the primary's _save_message DB write (which hasn't happened
            # yet at task-creation time).
            _parent_att_refs = [
                {
                    "name": att.get("name", ""),
                    # Prefer the URL the client already computed from the upload
                    # response. Fallback constructs it from id+ext in case an
                    # older client omits the url field.
                    "url": att.get("url") or f"/api/uploads/{att['id']}.{att.get('ext', '')}",
                }
                for att in attachments
                if att.get("id")
            ] if attachments else []
            extra_data = {
                "chat_id": chat_id,
                "prompt": prompt,
                "target_agent": t["profile_id"],
                "stream_id": _make_stream_id(),
                "_mention_depth": 0,
                "_mention_chain": [],
                "_source": "user_multi",
                "_suppress_user_message": True,
                "_parent_attachment_refs": _parent_att_refs,
            }
            log(f"user multi-dispatch: @{t['name']} in chat={chat_id[:8]}")
            extra_task = asyncio.create_task(
                _handle_send_action(websocket, extra_data)
            )
            _set_active_send_task(chat_id, extra_data["stream_id"], extra_task,
                                  name=t["name"], avatar=t["avatar"],
                                  profile_id=t["profile_id"])
    if group_agent:
        chat_model = group_agent["model"]
        backend = _get_model_backend(chat_model)
        prompt = group_agent["clean_prompt"]
        log(f"group routing: chat={chat_id[:8]} agent={group_agent['name']} model={chat_model} backend={backend}")
    is_agent_handoff = bool(
        is_group_chat and group_agent and (
            mention_depth > 0 or handoff_source == "agent" or suppress_user_message
        )
    )

    # Inject attachment path refs into secondary-agent prompts.
    # Secondary agents are dispatched without the original attachments payload, so
    # they would otherwise see the user text with no awareness of shared images/files.
    # Primary agent already received full base64; non-primary agents get a lightweight
    # text reference — "[Attached: name — /api/uploads/...]" — at zero image token cost.
    # Condition: suppress_user_message means this is a multi-dispatch secondary turn.
    if suppress_user_message and not attachments and is_group_chat:
        # Prefer refs passed from primary dispatch — avoids racing with the primary's
        # _save_message DB write, which hasn't executed yet when secondary tasks run.
        # Fall back to DB lookup for agent-to-agent handoffs that don't carry refs.
        _recent_atts = data.get("_parent_attachment_refs") or _get_latest_user_attachments(chat_id)
        if _recent_atts:
            ref_lines = "\n".join(
                f"[Attached: {a['name']} — {a['url']}]"
                for a in _recent_atts
                if a.get("name") and a.get("url")
            )
            if ref_lines:
                prompt = (f"{prompt}\n\n{ref_lines}" if prompt else ref_lines).strip()

    try:
        attachment_error = validate_backend_attachments(backend, attachments)
    except ValueError as e:
        await _safe_ws_send_json(websocket, {"type": "error", "message": str(e)}, chat_id=chat_id)
        return
    if attachment_error:
        await _safe_ws_send_json(websocket, {"type": "error", "message": attachment_error}, chat_id=chat_id)
        return

    client_key = f"{chat_id}:{group_agent['profile_id']}" if group_agent else chat_id

    stream_token = _current_stream_id.set(stream_id)
    group_profile_token = _current_group_profile_id.set(group_agent["profile_id"] if group_agent else "")
    lock_key = client_key if group_agent else chat_id
    chat_lock = _get_chat_lock(lock_key)
    lock_acquired = False
    acquire_task = asyncio.create_task(chat_lock.acquire())
    try:
        await asyncio.wait_for(asyncio.shield(acquire_task), timeout=0.05)
        lock_acquired = True
    except asyncio.TimeoutError:
        acquire_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            if await acquire_task:
                chat_lock.release()
        position = _enqueue_turn(
            lock_key,
            websocket,
            data,
            chat_id=chat_id,
            stream_id=stream_id,
            group_agent=group_agent,
        )
        if position is None:
            label = group_agent["name"] if group_agent else "this chat"
            await _safe_ws_send_json(
                websocket,
                {
                    "type": "error",
                    "message": f"{label} already has {MAX_QUEUED_TURNS_PER_KEY} queued turns. Wait for the queue to drain.",
                    "chat_id": chat_id,
                    "stream_id": stream_id,
                },
                chat_id=chat_id,
            )
            return
        await _emit_stream_queued(
            chat_id,
            stream_id,
            websocket=websocket,
            group_agent=group_agent,
            position=position,
        )
        return

    result: dict | None = None
    try:
        ack_payload = {"type": "stream_ack", "chat_id": chat_id, "stream_id": stream_id}
        if group_agent:
            ack_payload["speaker_name"] = group_agent["name"]
            ack_payload["speaker_avatar"] = group_agent["avatar"]
            ack_payload["speaker_id"] = group_agent["profile_id"]
        await _safe_ws_send_json(websocket, ack_payload, chat_id=chat_id)

        recovery_evt = _recovery_pending.get(chat_id)
        if recovery_evt:
            try:
                await asyncio.wait_for(recovery_evt.wait(), timeout=5.0)
                log(f"recovery wait: chat={chat_id} ready")
            except asyncio.TimeoutError:
                log(f"recovery wait: chat={chat_id} timed out (5s), proceeding without")

        if chat_id not in _compaction_summaries and not _has_session_context(chat_id):
            try:
                transcript = _get_recent_messages_text(chat_id, 30)
                if transcript.strip():
                    recovery = await asyncio.to_thread(_generate_recovery_context, transcript)
                    if recovery:
                        _store_recovery_context(chat_id, recovery, skip_targeting=True)
                        log(f"on-demand recovery: chat={chat_id[:8]} len={len(recovery)}")
            except Exception as e:
                log(f"on-demand recovery error chat={chat_id[:8]}: {e}")

        user_visible_prompt = prompt
        if _recall_context:
            prompt = f"{_recall_context}{prompt}"

        if ENABLE_SUBCONSCIOUS_WHISPER and backend in ("ollama", "xai", "mlx", "codex"):
            whisper = _get_whisper_text(chat_id, current_prompt=prompt)
            if whisper:
                prompt = f"{whisper}{prompt}"

        if group_agent:
            _group_profile_override[chat_id] = group_agent["profile_id"]

        display_prompt = user_visible_prompt
        make_query_input = None
        loaded_attachments: list[dict] = []
        attachment_refs_json = "[]"
        attachment_refs: list[dict] = []
        if attachments:
            try:
                loaded_attachments = [_load_attachment(att) for att in attachments]
                attachment_refs_json, attachment_refs = _attachment_refs_json(loaded_attachments)
            except ValueError as e:
                await _safe_ws_send_json(websocket, {"type": "error", "message": str(e)}, chat_id=chat_id)
                return
        if backend in ("ollama", "xai", "mlx", "codex"):
            display_prompt = user_visible_prompt
        else:
            try:
                _, make_query_input = _build_turn_payload(chat_id, prompt, attachments)
            except ValueError as e:
                await _safe_ws_send_json(websocket, {"type": "error", "message": str(e)}, chat_id=chat_id)
                return

        if group_agent and mention_prompt != group_agent.get("clean_prompt", ""):
            display_prompt = mention_prompt

        if not is_agent_handoff:
            _save_message(chat_id, "user", display_prompt, attachments=attachment_refs_json)

            ws_set = _chat_ws.get(chat_id, set())
            for ows in ws_set:
                if ows is not websocket:
                    await _safe_ws_send_json(
                        ows,
                        {
                            "type": "user_message_added",
                            "chat_id": chat_id,
                            "content": display_prompt,
                            "attachments": attachment_refs,
                        },
                        chat_id=chat_id,
                    )

            if chat["title"] in ("New Chat", "New Channel", "Quick thread"):
                title_source = prompt or display_prompt
                title = title_source[:50] + ("..." if len(title_source) > 50 else "")
                _update_chat(chat_id, title=title)
                await _safe_ws_send_json(
                    websocket, {"type": "chat_updated", "chat_id": chat_id, "title": title, "model": chat_model}, chat_id=chat_id
                )

        original_ws = websocket
        _attach_ws(websocket, chat_id)
        if not _has_active_stream(chat_id, exclude_stream_id=stream_id):
            _reset_stream_buffer(chat_id)

        stream_start_event = {"type": "stream_start", "chat_id": chat_id}
        if group_agent:
            _update_active_send_task(
                chat_id,
                stream_id,
                name=group_agent["name"],
                avatar=group_agent["avatar"],
                profile_id=group_agent["profile_id"],
                started_at=time.monotonic(),
            )
            # Persist active speaker to DB so recovery routing survives a crash
            _update_chat_settings(chat_id, {"active_speaker_id": group_agent["profile_id"]})
            stream_start_event["speaker_name"] = group_agent["name"]
            stream_start_event["speaker_avatar"] = group_agent["avatar"]
            stream_start_event["speaker_id"] = group_agent["profile_id"]
        await _send_stream_event(chat_id, stream_start_event)
        if is_group_chat:
            await _send_active_streams(chat_id)

        # --- Codex CLI path ---
        if backend == "codex":
            try:
                if chat_model in {"codex:o3", "codex:o4-mini"} and env.OPENAI_API_KEY:
                    result = await _run_ollama_chat(
                        chat_id,
                        prompt,
                        model=chat_model,
                        attachments=attachments,
                        permission_policy=permission_policy,
                    )
                else:
                    result = await _run_codex_chat(chat_id, prompt, model=chat_model, attachments=attachments)
            except Exception as codex_err:
                log(f"codex chat error: {codex_err}")
                message = _public_backend_error_message("codex", codex_err)
                for ws in list(_chat_ws.get(chat_id, {websocket})):
                    await _safe_ws_send_json(
                        ws,
                        {
                            "type": "error",
                            "message": message,
                            "retryable": True,
                            "target_agent": group_agent["profile_id"] if group_agent else "",
                            "stream_id": stream_id,
                        },
                        chat_id=chat_id,
                    )
                return
        # --- Local model / xAI path ---
        elif backend in ("ollama", "xai", "mlx"):
            try:
                result = await _run_ollama_chat(
                    chat_id,
                    prompt,
                    model=chat_model,
                    attachments=attachments,
                    permission_policy=permission_policy,
                )
            except Exception as ollama_err:
                log(f"ollama chat error: {ollama_err}")
                message = _public_backend_error_message(backend, ollama_err)
                for ws in list(_chat_ws.get(chat_id, {websocket})):
                    await _safe_ws_send_json(
                        ws,
                        {
                            "type": "error",
                            "message": message,
                            "retryable": True,
                            "target_agent": group_agent["profile_id"] if group_agent else "",
                            "stream_id": stream_id,
                        },
                        chat_id=chat_id,
                    )
                return
        else:
            # --- Claude SDK path ---
            try:
                await _maybe_compact_chat(chat_id)
            except Exception as compact_err:
                log(f"pre-flight compaction error: chat={chat_id} {compact_err}")

            try:
                client = await _get_or_create_client(
                    client_key,
                    model=chat_model,
                    permission_level=permission_level,
                    allowed_commands=allowed_commands,
                )
                result = await _run_query_turn(client, make_query_input, chat_id)
            except Exception as first_error:
                if DEBUG: log(f"DBG RECOVERY: chat={chat_id} client_key={client_key} first error: {type(first_error).__name__}: {first_error}")
                await _disconnect_client(client_key)

                def _make_retry_input():
                    base = make_query_input()
                    if isinstance(base, str):
                        return "[System: previous attempt failed. Respond concisely, avoid spawning parallel agents.]\n\n" + base
                    return base

                chat = _get_chat(chat_id)
                existing_session = chat.get("claude_session_id") if chat else None
                if DEBUG: log(f"DBG RECOVERY: attempting resume session={existing_session or 'NONE'}")
                try:
                    options = _make_options(
                        model=chat_model,
                        session_id=existing_session,
                        client_key=client_key,
                        chat_id=chat_id,
                        permission_level=permission_level,
                        allowed_commands=allowed_commands,
                    )
                    client = ClaudeSDKClient(options)
                    await asyncio.wait_for(client.connect(), timeout=SDK_QUERY_TIMEOUT)
                    _register_client(client_key, client, permission_level=permission_level)
                    result = await _run_query_turn(client, _make_retry_input, chat_id)
                    if DEBUG: log(f"DBG RECOVERY: resume OK client_key={client_key} session={existing_session or 'new'}")
                except Exception as resume_error:
                    if DEBUG: log(f"DBG RECOVERY: resume FAILED: {type(resume_error).__name__}: {resume_error}")
                    await _disconnect_client(client_key)
                    _update_chat(chat_id, claude_session_id=None)
                    _clear_session_context(client_key)
                    if DEBUG: log(f"DBG RECOVERY: session_id NUKED, trying fresh...")
                    try:
                        options = _make_options(
                            model=chat_model,
                            session_id=None,
                            client_key=client_key,
                            chat_id=chat_id,
                            permission_level=permission_level,
                            allowed_commands=allowed_commands,
                        )
                        client = ClaudeSDKClient(options)
                        await asyncio.wait_for(client.connect(), timeout=SDK_QUERY_TIMEOUT)
                        _register_client(client_key, client, permission_level=permission_level)
                        result = await _run_query_turn(client, _make_retry_input, chat_id)
                        if DEBUG: log(f"DBG RECOVERY: fresh session OK client_key={client_key}")
                    except Exception as fresh_error:
                        if DEBUG: log(f"DBG RECOVERY: fresh ALSO FAILED: {type(fresh_error).__name__}: {fresh_error}")
                        await _disconnect_client(client_key)
                        message = _public_backend_error_message("claude", fresh_error)
                        for ws in list(_chat_ws.get(chat_id, {websocket})):
                            await _safe_ws_send_json(
                                ws,
                                {
                                    "type": "error",
                                    "message": message,
                                    "retryable": True,
                                    "target_agent": group_agent["profile_id"] if group_agent else "",
                                    "stream_id": stream_id,
                                },
                                chat_id=chat_id,
                            )
                        return

        if not result:
            return

        if result.get("session_id") and backend != "codex":
            # Codex threads persisted via chat settings, not claude_session_id
            _update_chat(chat_id, claude_session_id=result["session_id"])
            # Store session_id for group agents so they can resume after eviction
            if group_agent:
                from streaming import store_client_session
                store_client_session(client_key, result["session_id"])

        response_text = result.get("text", "") if result else ""
        if (
            result.get("text")
            or result.get("thinking")
            or result.get("tool_events", "[]") != "[]"
            or result.get("is_error")
        ):
            active_pid = _resolve_memory_profile_id(chat_id, active_profile_id=group_agent["profile_id"] if group_agent else "")
            if active_pid:
                response_text = _extract_and_save_memories(response_text, active_pid, chat_id)

            _save_message(
                chat_id, "assistant", response_text,
                tool_events=result.get("tool_events", "[]"),
                thinking=result.get("thinking", ""),
                cost_usd=result.get("cost_usd", 0),
                tokens_in=result.get("tokens_in", 0),
                tokens_out=result.get("tokens_out", 0),
                speaker_id=group_agent["profile_id"] if group_agent else "",
                speaker_name=group_agent["name"] if group_agent else "",
                speaker_avatar=group_agent["avatar"] if group_agent else "",
            )

        # Clear active speaker now that response is persisted to DB
        if group_agent:
            _update_chat_settings(chat_id, {"active_speaker_id": ""})

        # Agent-to-agent @mention relay (premium)
        if is_group_chat and group_agent and response_text and _ws_premium:
            relay_members = _get_group_members(chat_id)
            broadcast_mention_present = _has_group_broadcast_mention(response_text, relay_members)
            explicit_relay_targets = _find_specific_group_mentioned_members(response_text, relay_members)
            explicit_relay_target_ids = {
                str(member.get("profile_id") or "")
                for member in explicit_relay_targets
                if str(member.get("profile_id") or "")
            }
            explicit_relay_target_names = {
                str(member.get("name") or "")
                for member in explicit_relay_targets
                if str(member.get("name") or "")
            }
            relay = _ws_premium.get_agent_relay_actions(
                chat_id, response_text, group_agent, mention_chain, mention_depth,
            )
            if broadcast_mention_present:
                log(f"relay blocked (@all reserved for user): {group_agent['name']} chat={chat_id[:8]}")
                filtered_actions: list[dict] = []
                for action in relay.get("actions") or []:
                    action_type = str(action.get("type") or "")
                    if action_type in {"relay", "redirect"}:
                        target = action.get("target") or {}
                        target_profile_id = str(target.get("profile_id") or "")
                        if target_profile_id and target_profile_id in explicit_relay_target_ids:
                            filtered_actions.append(action)
                    elif action_type == "pair_blocked":
                        target_name = str(action.get("target_name") or "")
                        if target_name and target_name in explicit_relay_target_names:
                            filtered_actions.append(action)
                relay = {**relay, "actions": filtered_actions}
            log(
                f"mention check: chat={chat_id[:8]} agent={group_agent['name']} "
                f"mentions_enabled={relay['mentions_enabled']} "
                f"found={relay['mentioned_names']} depth={mention_depth} "
                f"response_tail={response_text[-300:] if response_text else 'EMPTY'!r}"
            )
            sender_profile_id = str(group_agent.get("profile_id") or "")
            for action in relay["actions"]:
                atype = action["type"]
                if atype == "relay":
                    target = action["target"]
                    if str(target.get("profile_id") or "") == sender_profile_id:
                        log(f"relay blocked (self-mention): {group_agent['name']} chat={chat_id[:8]}")
                        continue
                    log(f"agent-to-agent mention: {group_agent['name']} -> @{target['name']} in chat={chat_id[:8]}")
                    follow_up_data = {
                        "chat_id": chat_id,
                        "prompt": action["prompt"],
                        "target_agent": target["profile_id"],
                        "stream_id": _make_stream_id(),
                        "_mention_depth": action["depth"],
                        "_mention_chain": relay["current_chain"],
                        "_source": "agent",
                        "_suppress_user_message": True,
                    }
                    follow_task = asyncio.create_task(
                        _handle_send_action(original_ws, follow_up_data)
                    )
                    _set_active_send_task(chat_id, follow_up_data["stream_id"], follow_task,
                                          name=target["name"], avatar=target["avatar"],
                                          profile_id=target["profile_id"])
                elif atype == "redirect":
                    target = action["target"]
                    if str(target.get("profile_id") or "") == sender_profile_id:
                        log(f"relay blocked (self-redirect): {group_agent['name']} chat={chat_id[:8]}")
                        continue
                    log(f"relay redirect to ops: {action['reason']} chat={chat_id[:8]}")
                    await _safe_ws_send_json(
                        original_ws,
                        {"type": "system_message", "chat_id": chat_id,
                         "text": f"{action['reason']}. Redirecting to @{target['name']} for realignment."},
                        chat_id=chat_id,
                    )
                    follow_up_data = {
                        "chat_id": chat_id,
                        "prompt": action["prompt"],
                        "target_agent": target["profile_id"],
                        "stream_id": _make_stream_id(),
                        "_mention_depth": action["depth"],
                        "_mention_chain": relay["current_chain"],
                        "_source": "agent",
                        "_suppress_user_message": True,
                    }
                    follow_task = asyncio.create_task(
                        _handle_send_action(original_ws, follow_up_data)
                    )
                    _set_active_send_task(chat_id, follow_up_data["stream_id"], follow_task,
                                          name=target["name"], avatar=target["avatar"],
                                          profile_id=target["profile_id"])
                elif atype == "blocked":
                    log(f"relay blocked (no ops redirect): {action['reason']} chat={chat_id[:8]}")
                    await _safe_ws_send_json(
                        original_ws,
                        {"type": "system_message", "chat_id": chat_id,
                         "text": f"{action['reason']}. No further agents auto-invoked."},
                        chat_id=chat_id,
                    )
                elif atype == "pair_blocked":
                    log(f"relay blocked (pair limit): {action['agent_name']} <-> {action['target_name']} chat={chat_id[:8]}")
                    await _safe_ws_send_json(
                        original_ws,
                        {"type": "system_message", "chat_id": chat_id,
                         "text": f"{action['reason']}. @{action['target_name']} was not auto-invoked."},
                        chat_id=chat_id,
                    )

        if backend == "claude":
            try:
                await _maybe_compact_chat(chat_id)
            except Exception as compact_err:
                log(f"compaction error: chat={chat_id} {compact_err}")

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
        if lock_acquired and chat_lock.locked():
            chat_lock.release()
        try:
            current_task = asyncio.current_task()
            # Preserve journal for crash recovery if codex errored
            _preserve = backend == "codex" and (result is None or result.get("is_error"))
            await _finalize_stream(
                chat_id,
                stream_id,
                current_task if isinstance(current_task, asyncio.Task) else None,
                is_group_chat=is_group_chat,
                preserve_journal=_preserve,
            )
        finally:
            _current_group_profile_id.reset(group_profile_token)
            _current_stream_id.reset(stream_token)
        if lock_acquired:
            _launch_next_queued_turn(lock_key)
