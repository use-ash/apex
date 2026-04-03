"""Profile CRUD, persona templates, persona memories.

Layer 4: imports from db (Layer 1), state (Layer 0), model_dispatch (Layer 1).
No imports from apex.py — self-contained.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from db import (
    _db_lock, _get_db,
    SYSTEM_PROFILE_ID,
    _normalize_tool_policy_text,
    _add_persona_memory, _get_persona_memories, _delete_persona_memory,
    _get_persona_model_override, _set_persona_model_override,
    _get_groups_using_persona,
)
from model_dispatch import _get_model_backend

profiles_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_slug(raw: str) -> str:
    """Normalize a slug: lowercase, alphanumeric + hyphens only, no leading/trailing hyphens."""
    s = raw.lower().strip()
    s = re.sub(r"[^a-z0-9\-]", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")


def _profile_payload(row) -> dict:
    """Convert a joined profile row into the API payload shape.

    Expected column order (from the list query):
    0=id, 1=name, 2=slug, 3=avatar, 4=role_description,
    5=p.model, 6=o.model (override), 7=is_default, 8=created_at, 9=updated_at,
    10=is_system, 11=system_prompt_override
    """
    base_model = row[5] or ""
    override_model = row[6] or ""
    prompt_override = row[11] or "" if len(row) > 11 else ""
    effective_model = override_model or base_model
    return {
        "id": row[0],
        "name": row[1],
        "slug": row[2],
        "avatar": row[3],
        "role_description": row[4],
        "backend": _get_model_backend(effective_model) if effective_model else "",
        "model": effective_model,
        "base_model": base_model,
        "override_model": override_model,
        "model_source": "override" if override_model else "base",
        "is_default": bool(row[7]),
        "created_at": row[8],
        "updated_at": row[9],
        "is_system": bool(row[10]) if len(row) > 10 else False,
        "has_prompt_override": bool(prompt_override),
    }


# ---------------------------------------------------------------------------
# Persona template routes
# ---------------------------------------------------------------------------

@profiles_router.get("/api/persona-templates")
async def api_persona_templates():
    """List available persona templates that can be installed.

    Templates that require a local model (Ollama) are flagged with
    available=false when Ollama is not running, so the frontend can
    grey them out.
    """
    templates_path = Path(__file__).resolve().parent / "persona_templates.json"
    if not templates_path.exists():
        return []
    try:
        templates = json.loads(templates_path.read_text())
    except Exception:
        return []

    # Check Ollama availability once for all templates
    ollama_available = False
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2) as resp:
            ollama_available = resp.status == 200
    except Exception:
        pass

    with _db_lock:
        conn = _get_db()
        existing = {r[0] for r in conn.execute("SELECT id FROM agent_profiles").fetchall()}
        conn.close()
    for t in templates:
        t["installed"] = t["id"] in existing
        is_local = t.get("backend", "") in ("ollama", "mlx")
        t["available"] = ollama_available if is_local else True
        if is_local and not ollama_available:
            t["unavailable_reason"] = "Ollama is not running"
    return templates


@profiles_router.post("/api/persona-templates/install")
async def api_install_persona_templates(request: Request):
    """Install selected persona templates by ID. Body: {"ids": [...]}"""
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
                 p["backend"], p["model"], p["system_prompt"],
                 _normalize_tool_policy_text(""),
                 p.get("is_default", 0), now, now),
            )
            if cur.rowcount:
                installed.append(tid)
        conn.commit()
        conn.close()
    from log import log
    if installed:
        log(f"Installed {len(installed)} persona templates: {', '.join(installed)}")
    return {"installed": installed, "skipped": [i for i in ids if i not in installed]}


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------

@profiles_router.get("/api/profiles")
async def api_get_profiles():
    """List all agent profiles, including effective model metadata."""
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT p.id, p.name, p.slug, p.avatar, p.role_description, "
            "p.model, o.model, p.is_default, p.created_at, p.updated_at, p.is_system, p.system_prompt_override "
            "FROM agent_profiles p "
            "LEFT JOIN persona_model_overrides o ON o.profile_id = p.id "
            "WHERE p.id != ? ORDER BY p.is_system DESC, p.is_default DESC, p.name ASC",
            (SYSTEM_PROFILE_ID,)
        ).fetchall()
        conn.close()
    return JSONResponse({"profiles": [_profile_payload(r) for r in rows]})


@profiles_router.get("/api/profiles/{profile_id}")
async def api_get_profile_detail(profile_id: str):
    """Get a single profile with full details including system_prompt."""
    if profile_id == SYSTEM_PROFILE_ID:
        return JSONResponse({"error": "profile not found"}, status_code=404)
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT p.id, p.name, p.slug, p.avatar, p.role_description, p.model, o.model, "
            "p.system_prompt, p.system_prompt_override, p.tool_policy, p.is_default, p.created_at, p.updated_at, p.is_system "
            "FROM agent_profiles p "
            "LEFT JOIN persona_model_overrides o ON o.profile_id = p.id "
            "WHERE p.id = ?",
            (profile_id,)
        ).fetchone()
        conn.close()
    if not row:
        return JSONResponse({"error": "profile not found"}, status_code=404)
    base_model = row[5] or ""
    override_model = row[6] or ""
    effective_model = override_model or base_model
    prompt_override = row[8] or ""
    effective_prompt = prompt_override or (row[7] or "")
    return JSONResponse({
        "id": row[0],
        "name": row[1],
        "slug": row[2],
        "avatar": row[3],
        "role_description": row[4],
        "backend": _get_model_backend(effective_model) if effective_model else "",
        "model": effective_model,
        "base_model": base_model,
        "override_model": override_model,
        "model_source": "override" if override_model else "base",
        "system_prompt": effective_prompt,
        "default_system_prompt": row[7] or "",
        "system_prompt_override": prompt_override,
        "has_prompt_override": bool(prompt_override),
        "tool_policy": _normalize_tool_policy_text(row[9]),
        "is_default": bool(row[10]),
        "created_at": row[11],
        "updated_at": row[12],
        "is_system": bool(row[13]),
    })


@profiles_router.post("/api/profiles")
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
                 _normalize_tool_policy_text(data.get("tool_policy", "")),
                 1 if data.get("is_default") else 0,
                 now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return JSONResponse({"error": f"slug '{slug}' already exists"}, status_code=409)
        conn.close()
    return JSONResponse({"id": profile_id, "slug": slug}, status_code=201)


@profiles_router.put("/api/profiles/{profile_id}")
async def api_update_profile(profile_id: str, request: Request):
    """Update an agent profile."""
    if profile_id == SYSTEM_PROFILE_ID:
        return JSONResponse({"error": "reserved profile"}, status_code=403)
    data = await request.json()
    now = datetime.now(timezone.utc).isoformat()
    with _db_lock:
        conn = _get_db()
        existing = conn.execute(
            "SELECT is_system FROM agent_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        if not existing:
            conn.close()
            return JSONResponse({"error": "profile not found"}, status_code=404)
        is_system = bool(existing[0])

        fields = []
        values = []
        # System personas: only allow avatar, role_description, and model override changes.
        # model and tool_policy are locked to prevent tampering with built-in personas.
        allowed_keys = ("name", "avatar", "role_description", "model", "tool_policy")
        if is_system:
            allowed_keys = ("avatar", "role_description")
        for key in allowed_keys:
            if key in data:
                if key == "tool_policy":
                    val = _normalize_tool_policy_text(data[key])
                else:
                    val = str(data[key]).strip() if key == "name" else str(data[key])
                if key == "name" and not val:
                    conn.close()
                    return JSONResponse({"error": "name cannot be empty"}, status_code=400)
                fields.append(f"{key} = ?")
                values.append(val)
        if "system_prompt" in data:
            prompt_value = str(data["system_prompt"])
            if is_system:
                normalized_prompt = prompt_value.strip()
                fields.append("system_prompt_override = ?")
                values.append(normalized_prompt or None)
            else:
                fields.append("system_prompt = ?")
                values.append(prompt_value)
        if "slug" in data:
            if is_system:
                conn.close()
                return JSONResponse({
                    "error": "Built-in personas keep their system slug. Create a new persona if you want a custom identity."
                }, status_code=403)
            slug = _normalize_slug(str(data["slug"]))
            if not slug:
                conn.close()
                return JSONResponse({"error": "slug cannot be empty"}, status_code=400)
            fields.append("slug = ?")
            values.append(slug)
        if "model" in data:
            model = str(data["model"]).strip()
            backend = _get_model_backend(model) if model else ""
            fields.append("backend = ?")
            values.append(backend)
        if "is_default" in data:
            fields.append("is_default = ?")
            values.append(1 if data["is_default"] else 0)
        if not fields:
            conn.close()
            return JSONResponse({"error": "no fields to update"}, status_code=400)
        fields.append("updated_at = ?")
        values.append(now)
        values.append(profile_id)
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


@profiles_router.post("/api/profiles/{profile_id}/reset")
async def api_reset_profile_prompt(profile_id: str):
    """Reset a system persona prompt override back to the shipped default."""
    if profile_id == SYSTEM_PROFILE_ID:
        return JSONResponse({"error": "reserved profile"}, status_code=403)
    now = datetime.now(timezone.utc).isoformat()
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT is_system, system_prompt FROM agent_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        if not row:
            conn.close()
            return JSONResponse({"error": "profile not found"}, status_code=404)
        if not row[0]:
            conn.close()
            return JSONResponse({
                "error": "Only built-in personas can be reset to a shipped default prompt."
            }, status_code=400)
        conn.execute(
            "UPDATE agent_profiles SET system_prompt_override = NULL, updated_at = ? WHERE id = ?",
            (now, profile_id),
        )
        conn.commit()
        conn.close()
    return JSONResponse({
        "ok": True,
        "message": "Persona prompt reset to the built-in default.",
        "system_prompt": row[1] or "",
        "has_prompt_override": False,
    })


@profiles_router.delete("/api/profiles/{profile_id}")
async def api_delete_profile(profile_id: str):
    """Delete an agent profile (unlinks from chats but doesn't delete chats)."""
    if profile_id == SYSTEM_PROFILE_ID:
        return JSONResponse({"error": "reserved profile"}, status_code=403)

    # Guard: fetch profile to check existence and system flag
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT id, is_system FROM agent_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        conn.close()

    if not row:
        return JSONResponse({"error": "Persona not found."}, status_code=404)
    if row[1]:
        return JSONResponse({
            "error": "This is a built-in persona. You can customize it, but you can’t delete it.",
            "code": "system_persona",
        }, status_code=403)

    # Guard: check if persona is assigned to any groups
    groups = _get_groups_using_persona(profile_id)
    if groups:
        return JSONResponse({
            "error": f"This persona is assigned to {', '.join(groups)}. Remove it from all groups before deleting.",
            "code": "persona_in_group",
            "groups": groups,
        }, status_code=409)

    with _db_lock:
        conn = _get_db()
        cur = conn.execute("DELETE FROM agent_profiles WHERE id = ?", (profile_id,))
        if cur.rowcount == 0:
            conn.close()
            return JSONResponse({"error": "Persona not found."}, status_code=404)
        conn.execute("UPDATE chats SET profile_id = '' WHERE profile_id = ?", (profile_id,))
        conn.commit()
        conn.close()
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Persona model overrides
# ---------------------------------------------------------------------------

@profiles_router.get("/api/profiles/{profile_id}/model-override")
async def api_get_profile_model_override(profile_id: str):
    """Get the effective/base/override model info for a persona."""
    if profile_id == SYSTEM_PROFILE_ID:
        return JSONResponse({"error": "reserved profile"}, status_code=403)
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT model FROM agent_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        conn.close()
    if not row:
        return JSONResponse({"error": "profile not found"}, status_code=404)
    base_model = row[0] or ""
    override_model = _get_persona_model_override(profile_id)
    effective_model = override_model or base_model
    return JSONResponse({
        "profile_id": profile_id,
        "base_model": base_model,
        "override_model": override_model,
        "effective_model": effective_model,
        "model_source": "override" if override_model else "base",
    })


@profiles_router.put("/api/profiles/{profile_id}/model-override")
async def api_put_profile_model_override(profile_id: str, request: Request):
    """Set or clear a persona model override. Body: {"model": "..."}."""
    if profile_id == SYSTEM_PROFILE_ID:
        return JSONResponse({"error": "reserved profile"}, status_code=403)
    data = await request.json()
    model = str(data.get("model", "")).strip()
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT model FROM agent_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        conn.close()
    if not row:
        return JSONResponse({"error": "profile not found"}, status_code=404)
    _set_persona_model_override(profile_id, model)
    base_model = row[0] or ""
    effective_model = model or base_model
    return JSONResponse({
        "ok": True,
        "profile_id": profile_id,
        "base_model": base_model,
        "override_model": model,
        "effective_model": effective_model,
        "model_source": "override" if model else "base",
        "backend": _get_model_backend(effective_model) if effective_model else "",
    })


@profiles_router.delete("/api/profiles/{profile_id}/model-override")
async def api_delete_profile_model_override(profile_id: str):
    """Clear a persona model override and fall back to the base profile model."""
    if profile_id == SYSTEM_PROFILE_ID:
        return JSONResponse({"error": "reserved profile"}, status_code=403)
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT model FROM agent_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        conn.close()
    if not row:
        return JSONResponse({"error": "profile not found"}, status_code=404)
    _set_persona_model_override(profile_id, "")
    base_model = row[0] or ""
    return JSONResponse({
        "ok": True,
        "profile_id": profile_id,
        "base_model": base_model,
        "override_model": "",
        "effective_model": base_model,
        "model_source": "base",
        "backend": _get_model_backend(base_model) if base_model else "",
    })


# ---------------------------------------------------------------------------
# Persona memory routes
# ---------------------------------------------------------------------------

@profiles_router.get("/api/profiles/{profile_id}/memories")
async def api_get_persona_memories(profile_id: str, limit: int = 50):
    """Get all memories for a persona agent."""
    return JSONResponse({"memories": _get_persona_memories(profile_id, limit=limit)})


@profiles_router.post("/api/profiles/{profile_id}/memories")
async def api_add_persona_memory(profile_id: str, request: Request):
    """Add a memory entry for a persona."""
    data = await request.json()
    content = str(data.get("content", "")).strip()
    if not content:
        return JSONResponse({"error": "Memory content required"}, status_code=400)
    category = data.get("category", "decision")
    source_chat_id = data.get("source_chat_id", "")
    mid = _add_persona_memory(profile_id, content, category=category, source_chat_id=source_chat_id)
    return JSONResponse({"ok": True, "id": mid})


@profiles_router.delete("/api/profiles/{profile_id}/memories/{memory_id}")
async def api_delete_persona_memory(profile_id: str, memory_id: str):
    """Delete a specific persona memory."""
    if not _delete_persona_memory(memory_id):
        return JSONResponse({"error": "Memory not found"}, status_code=404)
    return JSONResponse({"ok": True})
