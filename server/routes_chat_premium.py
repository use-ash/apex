"""Premium chat routes — group member CRUD.

Extracted from routes_chat.py. Loaded by PremiumLoader at startup.
Registers GET/POST/DELETE/PATCH member endpoints on the chat router.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from db import (
    _get_db, _get_chat, _get_group_members,
    _add_group_member, _remove_group_member,
    _normalize_group_primary_locked,
)
from state import _db_lock


def register_premium_chat_routes(router: APIRouter) -> None:
    """Register group member management endpoints on the given router."""

    @router.get("/api/chats/{chat_id}/members")
    async def api_get_members(chat_id: str):
        chat = _get_chat(chat_id)
        if not chat:
            return JSONResponse({"error": "Chat not found"}, status_code=404)
        if chat["type"] != "group":
            return JSONResponse({"error": "Not a group channel"}, status_code=400)
        return JSONResponse({"members": _get_group_members(chat_id)})

    @router.post("/api/chats/{chat_id}/members")
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

    @router.delete("/api/chats/{chat_id}/members/{profile_id}")
    async def api_remove_member(chat_id: str, profile_id: str):
        chat = _get_chat(chat_id)
        if not chat:
            return JSONResponse({"error": "Chat not found"}, status_code=404)
        if chat["type"] != "group":
            return JSONResponse({"error": "Not a group channel"}, status_code=400)
        if not _remove_group_member(chat_id, profile_id):
            return JSONResponse({"error": "Member not found"}, status_code=404)
        return JSONResponse({"ok": True})

    @router.patch("/api/chats/{chat_id}/members/{profile_id}")
    async def api_update_member(chat_id: str, profile_id: str, request: Request):
        chat = _get_chat(chat_id)
        if not chat:
            return JSONResponse({"error": "Chat not found"}, status_code=404)
        if chat["type"] != "group":
            return JSONResponse({"error": "Not a group channel"}, status_code=400)
        data = await request.json()
        routing_mode = data.get("routing_mode")
        if routing_mode:
            if routing_mode not in {"primary", "mentioned"}:
                return JSONResponse({"error": "Invalid routing_mode"}, status_code=400)
            with _db_lock:
                conn = _get_db()
                exists = conn.execute(
                    "SELECT 1 FROM channel_agent_memberships "
                    "WHERE channel_id = ? AND agent_profile_id = ? AND COALESCE(status, 'active') = 'active'",
                    (chat_id, profile_id),
                ).fetchone()
                if not exists:
                    conn.close()
                    return JSONResponse({"error": "Member not found"}, status_code=404)
                if routing_mode == "primary":
                    _normalize_group_primary_locked(conn, chat_id, preferred_profile_id=profile_id)
                else:
                    primary_count = conn.execute(
                        "SELECT COUNT(*) FROM channel_agent_memberships "
                        "WHERE channel_id = ? AND agent_profile_id != ? AND COALESCE(status, 'active') = 'active' "
                        "AND (is_primary = 1 OR routing_mode = 'primary')",
                        (chat_id, profile_id),
                    ).fetchone()[0]
                    if primary_count <= 0:
                        conn.close()
                        return JSONResponse({"error": "At least one member must be primary"}, status_code=400)
                    conn.execute(
                        "UPDATE channel_agent_memberships SET routing_mode = 'mentioned', is_primary = 0 "
                        "WHERE channel_id = ? AND agent_profile_id = ?",
                        (chat_id, profile_id),
                    )
                    _normalize_group_primary_locked(conn, chat_id)
                conn.commit()
                conn.close()
        return JSONResponse({"ok": True, "members": _get_group_members(chat_id)})
