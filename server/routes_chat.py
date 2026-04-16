"""Chat CRUD, group member management, settings, threads, messages, context.

Layer 4: depends on db/state/model_dispatch plus explicit streaming and
licensing helpers. No runtime back-reference to apex.py.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import env
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from db import (
    _get_db,
    SYSTEM_PROFILE_ID,
    _create_chat, _get_chats, _get_chat, _update_chat, _delete_chat,
    _get_chat_settings, _update_chat_settings,
    _get_chat_tool_policy, _normalize_tool_policy, _set_chat_tool_policy, _log_permission_change,
    _get_group_members,
    _add_group_member,
    _update_group_member,
    _remove_group_member,
    _get_messages,
    _get_last_turn_tokens_in, _estimate_tokens,
)
from group_coordinator import _MAX_RELAY_ROUNDS, _clear_strict_group_relay, _get_strict_group_relay_state
from license import get_license_manager
from model_dispatch import MODEL_CONTEXT_WINDOWS, MODEL_CONTEXT_DEFAULT
from streaming import (
    _cancel_chat_streams, _disconnect_client, _finalize_stream, _safe_ws_send_json,
    _has_client, _get_all_stream_task_entries,
)
from context import _clear_session_context, _estimate_tokens_from_cost
from state import (
    _db_lock, _last_compacted_at,
    _chat_ws, _ws_chat,
)

chat_router = APIRouter()

# ---------------------------------------------------------------------------
# Config (re-derived from env)
# ---------------------------------------------------------------------------
GROUPS_ENABLED = env.GROUPS_ENABLED
MODEL = env.MODEL
APEX_ROOT = env.APEX_ROOT
COMPACTION_THRESHOLD = env.COMPACTION_THRESHOLD

_license_mgr = get_license_manager()


def _serialize_relay_state(chat_id: str, chat: dict | None = None) -> dict | None:
    current_chat = chat or _get_chat(chat_id)
    if not current_chat or str(current_chat.get("type") or "chat") != "group":
        return None
    settings = _get_chat_settings(chat_id)
    if str(settings.get("coordination_protocol") or "freeform") != "sequential":
        return None
    members = _get_group_members(chat_id)
    relay_state = _get_strict_group_relay_state(chat_id, members)
    member_map = {
        str(member.get("profile_id") or ""): member
        for member in members
        if str(member.get("profile_id") or "")
    }
    if not relay_state.active:
        return {
            "active": False,
            "round_number": int(relay_state.round_number or 1),
            "max_rounds": _MAX_RELAY_ROUNDS,
            "agents": [],
        }
    abstained = set(relay_state.round_abstentions or ())
    completed = set(relay_state.completed_profile_ids or [])
    agents: list[dict] = []
    for profile_id in relay_state.ordered_profile_ids:
        member = member_map.get(profile_id) or {}
        if profile_id in abstained:
            status = "abstained"
        elif profile_id in completed:
            status = "responded"
        elif profile_id == relay_state.next_profile_id:
            status = "next"
        else:
            status = "waiting"
        agents.append({
            "profile_id": profile_id,
            "name": str(member.get("name") or profile_id),
            "emoji": str(member.get("avatar") or "🤖"),
            "status": status,
        })
    return {
        "active": True,
        "round_number": int(relay_state.round_number or 1),
        "max_rounds": _MAX_RELAY_ROUNDS,
        "agents": agents,
    }


def _direct_chat_tool_policy_error(chat: dict | None) -> JSONResponse | None:
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    if str(chat.get("type") or "chat").strip() != "chat":
        return JSONResponse({"error": "Chat-level permissions only apply to direct chats"}, status_code=400)
    if str(chat.get("profile_id") or "").strip():
        return JSONResponse({"error": "This chat already inherits permissions from its assigned profile"}, status_code=400)
    return None


async def _refresh_direct_chat_runtime(chat_id: str) -> None:
    """Force direct-chat SDK/tool state to pick up a new chat-level policy."""
    if _has_client(chat_id):
        await _disconnect_client(chat_id)
    _update_chat(chat_id, claude_session_id=None)
    _clear_session_context(chat_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@chat_router.get("/api/chats")
async def api_chats():
    return JSONResponse(_get_chats())


@chat_router.post("/api/chats")
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
    members = data.get("members", [])
    if chat_type == "group":
        if not GROUPS_ENABLED and not _license_mgr.is_feature_enabled("groups"):
            lic = _license_mgr.status()
            trial_str = "expired" if not lic["trial_active"] else f"active ({lic['trial_days_remaining']}d remaining)"
            msg = f"Groups require Apex Pro. Trial {trial_str}. Activate at https://useash.dev/activate"
            return JSONResponse({"error": msg, "premium_required": True}, status_code=403)
        if not members:
            return JSONResponse({"error": "Groups require at least one member"}, status_code=400)
    if profile_id == SYSTEM_PROFILE_ID:
        return JSONResponse({"error": "Reserved profile id"}, status_code=400)
    if profile_id and chat_type not in ("chat", "thread"):
        return JSONResponse({"error": "Profiles are only supported for channels and threads"}, status_code=400)
    if profile_id:
        with _db_lock:
            conn = _get_db()
            profile_row = conn.execute(
                "SELECT COALESCE(o.model, p.model) "
                "FROM agent_profiles p "
                "LEFT JOIN persona_model_overrides o ON o.profile_id = p.id "
                "WHERE p.id = ?",
                (profile_id,),
            ).fetchone()
            conn.close()
        if not profile_row:
            return JSONResponse({"error": f"Profile '{profile_id}' not found"}, status_code=400)
        if profile_row[0]:
            model = profile_row[0]
    CATEGORY_TITLES = {"system": "System Alerts", "test": "Test Alerts", "custom": "Custom Alerts"}
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
    if chat_type == "group" and members:
        for i, mem in enumerate(members):
            pid = mem.get("profile_id", "")
            mode = mem.get("routing_mode", "mentioned")
            is_pri = mode == "primary"
            try:
                _add_group_member(cid, pid, routing_mode=mode, is_primary=is_pri, display_order=i)
            except Exception:
                pass
        group_members = _get_group_members(cid)
        primary = next((m for m in group_members if m["is_primary"]), None)
        if primary and primary["model"]:
            model = primary["model"]
            _update_chat(cid, model=model)
        if group_members:
            owner = primary or group_members[0]
            with _db_lock:
                conn = _get_db()
                conn.execute(
                    "UPDATE channel_agent_memberships SET role = 'owner' "
                    "WHERE channel_id = ? AND agent_profile_id = ?",
                    (cid, owner["profile_id"]),
                )
                conn.commit()
                conn.close()
        resp["members"] = _get_group_members(cid)
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


@chat_router.patch("/api/chats/{chat_id}")
async def api_update_chat(chat_id: str, request: Request):
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    data = await request.json()
    title = data.get("title")
    if title is not None:
        title = str(title).strip()[:100]
        if not title:
            return JSONResponse({"error": "Title cannot be empty"}, status_code=400)
        _update_chat(chat_id, title=title)
        payload = {"type": "chat_updated", "chat_id": chat_id,
                   "title": title, "model": chat.get("model")}
        for cid, ws_set in list(_chat_ws.items()):
            for ws in list(ws_set):
                await _safe_ws_send_json(ws, payload, chat_id=cid)
    if "profile_id" in data:
        if chat.get("type") != "chat":
            return JSONResponse({"error": "Profiles are only supported for regular chats"}, status_code=400)
        pid = str(data["profile_id"]).strip()
        if pid == SYSTEM_PROFILE_ID:
            return JSONResponse({"error": "Reserved profile id"}, status_code=400)
        if pid:
            with _db_lock:
                conn = _get_db()
                profile_row = conn.execute(
                    "SELECT COALESCE(o.model, p.model), p.name, p.avatar "
                    "FROM agent_profiles p "
                    "LEFT JOIN persona_model_overrides o ON o.profile_id = p.id "
                    "WHERE p.id = ?",
                    (pid,),
                ).fetchone()
                conn.close()
            if not profile_row:
                return JSONResponse({"error": f"Profile '{pid}' not found"}, status_code=400)
            update_kwargs = {"profile_id": pid}
            if profile_row[0]:
                update_kwargs["model"] = profile_row[0]
            profile_name = profile_row[1] or ""
            profile_avatar = profile_row[2] or ""
        else:
            update_kwargs = {"profile_id": ""}
            profile_name = ""
            profile_avatar = ""

        _update_chat(chat_id, **update_kwargs)

        had_sdk_client = _has_client(chat_id)
        await _disconnect_client(chat_id)
        _update_chat(chat_id, claude_session_id=None)
        _clear_session_context(chat_id)
        if not had_sdk_client:
            is_group_streams = bool(_get_chat(chat_id) and (_get_chat(chat_id) or {}).get("type") == "group")
            for stream_id, entry in _get_all_stream_task_entries(chat_id):
                send_task = entry.get("task")
                should_send_end = isinstance(send_task, asyncio.Task) and not send_task.done()
                if should_send_end:
                    send_task.cancel()
                await _finalize_stream(
                    chat_id, stream_id,
                    send_task if isinstance(send_task, asyncio.Task) else None,
                    is_group_chat=is_group_streams,
                    send_stream_end=should_send_end,
                )

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


@chat_router.delete("/api/chats/{chat_id}")
async def api_delete_chat(chat_id: str):
    if _has_client(chat_id):
        await _disconnect_client(chat_id)
    if not _delete_chat(chat_id):
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    payload = {"type": "chat_deleted", "chat_id": chat_id}
    for cid, ws_set in list(_chat_ws.items()):
        for ws in list(ws_set):
            await _safe_ws_send_json(ws, payload, chat_id=cid)
    return JSONResponse({"ok": True})


@chat_router.post("/api/chats/{chat_id}/cancel")
async def api_cancel_chat(chat_id: str, request: Request):
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    stream_id = ""
    try:
        data = await request.json()
        if isinstance(data, dict):
            stream_id = str(data.get("stream_id") or "")
    except Exception:
        stream_id = ""
    await _cancel_chat_streams(chat_id, stream_id=stream_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Baseline group member routes — GET always available (read-only).
# Write operations (POST/PATCH/DELETE) require active groups license.
# Premium module may shadow these with enhanced versions when loaded.
# ---------------------------------------------------------------------------

def _require_groups_license() -> JSONResponse | None:
    """Return a 403 JSONResponse if groups are not licensed, else None."""
    if GROUPS_ENABLED or _license_mgr.is_feature_enabled("groups"):
        return None
    lic = _license_mgr.status()
    trial_str = "expired" if not lic["trial_active"] else f"active ({lic['trial_days_remaining']}d remaining)"
    return JSONResponse(
        {"error": f"Groups require Apex Pro. Trial {trial_str}. Activate at https://useash.dev/activate",
         "premium_required": True},
        status_code=403,
    )


@chat_router.get("/api/chats/{chat_id}/members")
async def api_get_members(chat_id: str):
    """Return the active members of a group channel (always available)."""
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    if (chat.get("type") or "chat") != "group":
        return JSONResponse({"error": "Not a group channel"}, status_code=400)
    return JSONResponse({"members": _get_group_members(chat_id)})


@chat_router.post("/api/chats/{chat_id}/members")
async def api_add_member(chat_id: str, request: Request):
    """Add an agent profile to a group channel (premium)."""
    gate = _require_groups_license()
    if gate:
        return gate
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    if (chat.get("type") or "chat") != "group":
        return JSONResponse({"error": "Not a group channel"}, status_code=400)
    data = await request.json()
    profile_id = data.get("profile_id", "")
    if not profile_id:
        return JSONResponse({"error": "profile_id required"}, status_code=400)
    routing_mode = data.get("routing_mode", "mentioned")
    is_primary = data.get("is_primary", False) or routing_mode == "primary"
    _add_group_member(chat_id, profile_id, routing_mode=routing_mode, is_primary=is_primary)
    return JSONResponse({"ok": True, "members": _get_group_members(chat_id)})


@chat_router.patch("/api/chats/{chat_id}/members/{profile_id}")
async def api_update_member(chat_id: str, profile_id: str, request: Request):
    """Update a group member's routing mode (premium)."""
    gate = _require_groups_license()
    if gate:
        return gate
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    if (chat.get("type") or "chat") != "group":
        return JSONResponse({"error": "Not a group channel"}, status_code=400)
    data = await request.json()
    routing_mode = data.get("routing_mode")
    if routing_mode not in ("primary", "mentioned"):
        return JSONResponse({"error": "routing_mode must be 'primary' or 'mentioned'"}, status_code=400)
    updated = _update_group_member(chat_id, profile_id, routing_mode=routing_mode)
    if not updated:
        return JSONResponse({"error": "Member not found"}, status_code=404)
    return JSONResponse({"ok": True, "members": _get_group_members(chat_id)})


@chat_router.delete("/api/chats/{chat_id}/members/{profile_id}")
async def api_remove_member(chat_id: str, profile_id: str):
    """Remove (soft-delete) an agent from a group channel (premium)."""
    gate = _require_groups_license()
    if gate:
        return gate
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    if (chat.get("type") or "chat") != "group":
        return JSONResponse({"error": "Not a group channel"}, status_code=400)
    removed = _remove_group_member(chat_id, profile_id)
    if not removed:
        return JSONResponse({"error": "Member not found or is the last member"}, status_code=400)
    return JSONResponse({"ok": True, "members": _get_group_members(chat_id)})


@chat_router.get("/api/chats/{chat_id}/settings")
async def api_get_chat_settings(chat_id: str):
    """Get settings for a chat (group settings, premium flags, etc.)."""
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    settings = dict(_get_chat_settings(chat_id))
    settings["relay_state"] = _serialize_relay_state(chat_id, chat)
    return JSONResponse({"settings": settings})


@chat_router.patch("/api/chats/{chat_id}/settings")
async def api_update_chat_settings(chat_id: str, request: Request):
    """Update settings for a chat. Merges with existing settings."""
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    current_settings = _get_chat_settings(chat_id)
    data = await request.json()
    allowed = {"agent_mentions_enabled", "auto_title", "notification_level", "auto_reply", "shared_memory", "coordination_protocol"}
    filtered = {k: v for k, v in data.items() if k in allowed}
    if not filtered:
        return JSONResponse({"error": f"No valid settings. Allowed: {', '.join(sorted(allowed))}"}, status_code=400)
    if (
        str(current_settings.get("coordination_protocol") or "freeform") == "sequential"
        and str(filtered.get("coordination_protocol") or "sequential") == "freeform"
    ):
        _clear_strict_group_relay(chat_id)
    updated = _update_chat_settings(chat_id, filtered)
    updated = dict(updated)
    updated["relay_state"] = _serialize_relay_state(chat_id, chat)
    return JSONResponse({"ok": True, "settings": updated})


@chat_router.get("/api/chats/{chat_id}/tool-policy")
async def api_get_chat_tool_policy(chat_id: str):
    chat = _get_chat(chat_id)
    err = _direct_chat_tool_policy_error(chat)
    if err:
        return err
    return JSONResponse({"tool_policy": _get_chat_tool_policy(chat_id)})


@chat_router.put("/api/chats/{chat_id}/tool-policy")
async def api_set_chat_tool_policy(chat_id: str, request: Request):
    chat = _get_chat(chat_id)
    err = _direct_chat_tool_policy_error(chat)
    if err:
        return err
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    if not isinstance(data, dict):
        return JSONResponse({"error": "Request body must be a JSON object"}, status_code=400)
    current_policy = _get_chat_tool_policy(chat_id)
    old_level = int(current_policy.get("level", current_policy.get("default_level", 2)))
    default_level = int(current_policy.get("default_level", 2))
    policy = _normalize_tool_policy(data, default_level=default_level)
    policy = _set_chat_tool_policy(chat_id, policy, default_level=default_level)
    _log_permission_change(chat_id, "set", old_level, int(policy.get("level", default_level)))
    await _refresh_direct_chat_runtime(chat_id)
    return JSONResponse({"ok": True, "tool_policy": policy})


@chat_router.post("/api/chats/{chat_id}/tool-policy/elevate")
async def api_elevate_chat_tool_policy(chat_id: str, request: Request):
    chat = _get_chat(chat_id)
    err = _direct_chat_tool_policy_error(chat)
    if err:
        return err
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        minutes = int(data.get("minutes", data.get("duration_minutes", 15)))
    except (TypeError, ValueError):
        return JSONResponse({"error": "minutes must be an integer"}, status_code=400)
    try:
        target_level = int(data.get("level", 3))
    except (TypeError, ValueError):
        return JSONResponse({"error": "level must be an integer"}, status_code=400)
    if minutes < 1 or minutes > 24 * 60:
        return JSONResponse({"error": "minutes must be between 1 and 1440"}, status_code=400)
    current = _get_chat_tool_policy(chat_id)
    default_level = int(current.get("default_level", current.get("level", 2)))
    old_level = int(current.get("level", default_level))
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(timespec="seconds")
    current["default_level"] = default_level
    current["level"] = max(default_level, min(4, target_level))
    current["elevated_until"] = expires_at
    policy = _set_chat_tool_policy(chat_id, current, default_level=default_level)
    _log_permission_change(chat_id, "elevate", old_level, int(policy.get("level", default_level)), elevated_until=expires_at)
    await _refresh_direct_chat_runtime(chat_id)
    return JSONResponse({"ok": True, "chat_id": chat_id, "tool_policy": policy, "expires_at": expires_at})


@chat_router.post("/api/chats/{chat_id}/tool-policy/revoke")
async def api_revoke_chat_tool_policy(chat_id: str):
    chat = _get_chat(chat_id)
    err = _direct_chat_tool_policy_error(chat)
    if err:
        return err
    current = _get_chat_tool_policy(chat_id)
    default_level = int(current.get("default_level", current.get("level", 2)))
    old_level = int(current.get("level", default_level))
    current["level"] = default_level
    current["elevated_until"] = None
    policy = _set_chat_tool_policy(chat_id, current, default_level=default_level)
    _log_permission_change(chat_id, "revoke", old_level, default_level)
    await _refresh_direct_chat_runtime(chat_id)
    return JSONResponse({"ok": True, "chat_id": chat_id, "tool_policy": policy})


@chat_router.get("/api/chats/{chat_id}/tool-policy/audit")
async def api_get_permission_audit(chat_id: str, limit: int = 50):
    chat = _get_chat(chat_id)
    err = _direct_chat_tool_policy_error(chat)
    if err:
        return err
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT event_type, old_level, new_level, elevated_until, changed_at"
            " FROM permission_audit_log WHERE chat_id = ?"
            " ORDER BY changed_at DESC, rowid DESC LIMIT ?",
            (chat_id, max(1, min(limit, 200))),
        ).fetchall()
        conn.close()
    return JSONResponse({"chat_id": chat_id, "audit": [
        {"event_type": r[0], "old_level": r[1], "new_level": r[2], "elevated_until": r[3], "changed_at": r[4]}
        for r in rows
    ]})


@chat_router.delete("/api/threads/stale")
async def api_delete_stale_threads(older_than_days: int = 7):
    """Delete threads older than N days (default 7)."""
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
        for cid_del in [r[0] for r in stale]:
            payload = {"type": "chat_deleted", "chat_id": cid_del}
            for cid, ws_set in list(_chat_ws.items()):
                for ws in list(ws_set):
                    await _safe_ws_send_json(ws, payload, chat_id=cid)
    return JSONResponse({"ok": True, "deleted": deleted})


@chat_router.get("/api/chats/{chat_id}/messages")
async def api_messages(
    chat_id: str,
    days: int | None = None,
    limit: int | None = 100,
    before_id: str | None = None,
):
    return JSONResponse(_get_messages(chat_id, days=days, limit=limit, before_id=before_id))


@chat_router.get("/api/chats/{chat_id}/context")
async def api_context(chat_id: str):
    """Return context window usage for a chat."""
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    # Resolve model: chat override → profile model → server default
    chat_model = chat.get("model") or ""
    if not chat_model:
        profile_id = chat.get("profile_id", "")
        if profile_id:
            with _db_lock:
                conn = _get_db()
                prow = conn.execute(
                    "SELECT COALESCE(o.model, p.model) FROM agent_profiles p "
                    "LEFT JOIN persona_model_overrides o ON o.profile_id = p.id "
                    "WHERE p.id = ?", (profile_id,)
                ).fetchone()
                conn.close()
            if prow and prow[0]:
                chat_model = prow[0]
    chat_model = chat_model or MODEL
    context_window = MODEL_CONTEXT_WINDOWS.get(chat_model, MODEL_CONTEXT_DEFAULT)
    # 3-signal max — same logic as context.py fuel gauge.
    # SDK tokens_in is often garbage (3-24), so always cross-check with
    # char-based estimation and cost-based reverse engineering.
    sdk_tokens = _get_last_turn_tokens_in(chat_id)
    est_tokens = _estimate_tokens(chat_id, context_window=context_window)
    cost_tokens = _estimate_tokens_from_cost(chat_id, chat_model)
    context_used = min(max(sdk_tokens, est_tokens, cost_tokens), context_window)
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
    return JSONResponse({
        "chat_id": chat_id,
        "model": chat_model,
        "tokens_in": context_used,
        "tokens_out": cumulative_out,
        "compaction_threshold": COMPACTION_THRESHOLD,
        "context_window": context_window,
    })
