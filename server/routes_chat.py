"""Chat CRUD, group member management, settings, threads, messages, context.

Layer 4: depends on db/state/model_dispatch plus explicit streaming and
licensing helpers. No runtime back-reference to apex.py.
"""
from __future__ import annotations

import asyncio
import json

import env
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from db import (
    _get_db, _now,
    SYSTEM_PROFILE_ID,
    _create_chat, _get_chats, _get_chat, _update_chat, _delete_chat,
    _get_chat_settings, _update_chat_settings,
    _get_group_members,
    _add_group_member,
    _get_messages,
    _get_last_turn_tokens_in, _estimate_tokens,
)
from license import get_license_manager
from model_dispatch import MODEL_CONTEXT_WINDOWS, MODEL_CONTEXT_DEFAULT
from streaming import (
    _cancel_chat_streams, _disconnect_client, _finalize_stream, _safe_ws_send_json,
    _has_client, _get_all_stream_task_entries,
)
from context import _clear_session_context
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
                "SELECT model FROM agent_profiles WHERE id = ?", (profile_id,)
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
                    "SELECT model, name, avatar FROM agent_profiles WHERE id = ?", (pid,)
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


# Group member CRUD routes (GET/POST/DELETE/PATCH members) are registered
# by routes_chat_premium.py when the premium module is loaded.


@chat_router.get("/api/chats/{chat_id}/settings")
async def api_get_chat_settings(chat_id: str):
    """Get settings for a chat (group settings, premium flags, etc.)."""
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    return JSONResponse({"settings": _get_chat_settings(chat_id)})


@chat_router.patch("/api/chats/{chat_id}/settings")
async def api_update_chat_settings(chat_id: str, request: Request):
    """Update settings for a chat. Merges with existing settings."""
    chat = _get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    data = await request.json()
    allowed = {"agent_mentions_enabled", "auto_title", "notification_level", "auto_reply", "shared_memory"}
    filtered = {k: v for k, v in data.items() if k in allowed}
    if not filtered:
        return JSONResponse({"error": f"No valid settings. Allowed: {', '.join(sorted(allowed))}"}, status_code=400)
    updated = _update_chat_settings(chat_id, filtered)
    return JSONResponse({"ok": True, "settings": updated})


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
    context_used = _get_last_turn_tokens_in(chat_id)
    if context_used == 0:
        context_used = _estimate_tokens(chat_id, context_window=context_window)
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
