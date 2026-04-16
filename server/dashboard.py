"""Apex Dashboard — FastAPI sub-app for server management.

Phase 1: Foundation + Health Dashboard.
Phase 2: TLS Certificate Management.
Mounted at /admin on the main server. Shares mTLS auth.

Endpoints:
    GET  /                      — Dashboard HTML
    GET  /api/docs              — OpenAPI schema
    GET  /api/status            — Server health
    GET  /api/status/db         — Database stats
    GET  /api/status/tls        — TLS certificate status
    GET  /api/status/models     — Model provider reachability
    GET  /api/config            — Full config (secrets redacted)
    GET  /api/config/schema     — Config schema for UI forms
    PUT  /api/config/server     — Update server config
    PUT  /api/config/models     — Update models config
    PUT  /api/config/workspace  — Update workspace config
    POST /api/server/restart    — Signal restart required

    Phase 2 — TLS Certificate Management:
    GET    /api/tls/ca                — CA cert details
    GET    /api/tls/server            — Server cert details + SANs
    GET    /api/tls/clients           — List all client certs
    POST   /api/tls/clients           — Generate new client cert
    GET    /api/tls/clients/{cn}/p12  — Download .p12 bundle
    GET    /api/tls/clients/{cn}/qr   — QR code / URL card for .p12
    DELETE /api/tls/clients/{cn}      — Revoke/delete client cert
    POST   /api/tls/server/renew      — Renew server cert from CA
    POST   /api/tls/ca/generate       — Generate new CA (first-run or re-key)
    GET    /api/tls/sans              — Current SAN list from ext.cnf
    PUT    /api/tls/sans              — Update SANs in ext.cnf

    Phase 3 — Models, Credentials, Alerts:
    PUT    /api/config/models/default           — Set default model
    PUT    /api/config/models/permission         — Set SDK permission mode
    GET    /api/models/claude                    — Claude API status (env + keychain)
    GET    /api/models/ollama                    — Ollama detailed status + running models
    GET    /api/models/grok                      — Grok API key status
    GET    /api/credentials                      — Which keys are configured (booleans)
    PUT    /api/credentials/{provider}           — Set API key in .env
    POST   /api/credentials/alert-token/rotate   — Rotate alert token
    GET    /api/alerts/config                    — Alert configuration overview
    PUT    /api/alerts/config/telegram           — Update telegram config
    POST   /api/alerts/test                      — Fire test alert (DB + Telegram)

    Phase 4 — Workspace, Skills, Guardrails, Sessions:
    GET    /api/workspace                          — Workspace summary
    GET    /api/workspace/project-md                — Read APEX.md content
    PUT    /api/workspace/project-md                — Update APEX.md (backup first)
    GET    /api/workspace/memory                    — List memory files
    GET    /api/workspace/memory/{name}              — Read memory file content
    PUT    /api/workspace/memory/{name}              — Update memory file (backup first)
    GET    /api/skills                              — List installed skills
    PUT    /api/skills/{name}/enabled               — Enable/disable skill
    GET    /api/guardrails/whitelist                — Read guardrail whitelist
    DELETE /api/guardrails/whitelist/{id}           — Remove whitelist entry by index
    GET    /api/sessions                            — List active sessions
    POST   /api/sessions/{chat_id}/compact          — Force compaction
    DELETE /api/sessions/{chat_id}                  — Kill session

    Phase 5 — Logs, Storage, Backups:
    GET    /api/logs                             — Read log lines (tail, search, level filter)
    GET    /api/logs/stream                      — SSE live tail of log file
    POST   /api/logs/clear                       — Rotate log file
    GET    /api/db/stats                         — Database stats (size, tables, WAL, pragmas)
    POST   /api/db/vacuum                        — VACUUM database
    GET    /api/db/export                        — Download database file
    DELETE /api/db/messages                       — Purge old messages
    GET    /api/uploads                          — List uploaded files
    POST   /api/uploads/cleanup                  — Delete old uploads
    POST   /api/backup                           — Create backup tarball
    GET    /api/backups                          — List available backups
    GET    /api/backups/{filename}               — Download backup file
    POST   /api/backup/restore                   — Restore from backup
"""

from __future__ import annotations

import asyncio
import ast
import csv
import glob as _glob_mod
import html
import hmac
import contextlib
import hashlib
import importlib.util
import io
import ipaddress
import json
import logging
import math
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.responses import StreamingResponse

from config import Config, SCHEMA
from context import _parse_iso
from db import (
    SYSTEM_PROFILE_ID,
    _db_lock,
    _get_db,
    _get_persona_memories,
    _normalize_tool_policy,
    _set_profile_tool_policy,
)
import env
from log import LOG_PATH
from model_dispatch import get_available_model_ids
from routes_models import api_usage as provider_api_usage
from routes_models import api_usage_codex as provider_api_usage_codex
from tool_access import get_tool_catalog, get_workspace_tool_patterns
from local_model.safety import (
    get_policy_blocked_path_prefixes,
    get_policy_never_allowed_commands,
)

# ---------------------------------------------------------------------------
# Module state — set by init_dashboard() at server startup
# ---------------------------------------------------------------------------

_log = logging.getLogger("apex.dashboard")

_start_time: float = time.time()
_vacuum_lock = asyncio.Lock()
_last_vacuum: float = 0.0
_cert_gen_times: list[float] = []
_backup_lock = asyncio.Lock()
_last_backup: float = 0.0
_BACKUP_COOLDOWN = 60.0
_cert_lock = asyncio.Lock()

_state_dir: Path | None = None
_db_path: Path | None = None
_ssl_dir: Path | None = None
_config: Config | None = None

_USAGE_TRACK_BY_BACKEND = {
    "claude": "subscription",
    "codex": "subscription",
    "openai": "api",
    "xai": "api",
    "grok": "api",
    "gemini": "api",
    "ollama": "local",
    "mlx": "local",
    "local": "local",
}

_MODEL_PRICING: dict[str, dict[str, Any]] = {
    "claude-haiku-4-5-20251001": {"display": "Haiku 4.5", "track": "subscription", "price_in": 0.80, "price_out": 4.00, "provider": "claude"},
    "claude-sonnet-4-6": {"display": "Sonnet 4.6", "track": "subscription", "price_in": 3.00, "price_out": 15.00, "provider": "claude"},
    "claude-opus-4-6": {"display": "Opus 4.6", "track": "subscription", "price_in": 15.00, "price_out": 75.00, "provider": "claude"},
    "codex:gpt-5.4": {"display": "Codex GPT-5.4", "track": "subscription", "price_in": 1.50, "price_out": 6.00, "provider": "codex"},
    "codex:gpt-5.4-mini": {"display": "Codex GPT-5.4 Mini", "track": "subscription", "price_in": 0.30, "price_out": 1.20, "provider": "codex"},
    "codex:o3": {"display": "Codex o3", "track": "subscription", "price_in": 2.00, "price_out": 8.00, "provider": "codex"},
    "grok-4": {"display": "Grok 4", "track": "api", "price_in": 5.00, "price_out": 15.00, "provider": "xai"},
    "gemma4:26b": {"display": "Gemma 4 26B", "track": "local", "price_in": 0.0, "price_out": 0.0, "provider": "local"},
    "qwen3.5:35b-a3b": {"display": "Qwen 3.5 35B A3B", "track": "local", "price_in": 0.0, "price_out": 0.0, "provider": "local"},
}


def _normalize_workspace_path_value(raw: object) -> str:
    """Normalize UI-entered workspace paths into APEX_WORKSPACE format."""
    if raw is None:
        return ""
    text = str(raw).replace("\r\n", "\n").replace("\r", "\n")
    parts: list[str] = []
    for line in text.split("\n"):
        for chunk in str(line).split(":"):
            item = chunk.strip()
            if item and item not in parts:
                parts.append(item)
    return ":".join(parts)


def _workspace_paths_list(raw: str | None = None) -> list[str]:
    value = raw if raw is not None else env.get_runtime_workspace_paths()
    return [part.strip() for part in str(value).split(":") if part.strip()]


def _workspace_root() -> Path:
    return env.get_runtime_workspace_root()


def _sync_filesystem_mcp_workspace_roots(workspace_value: str) -> None:
    """Keep filesystem MCP roots aligned with the configured workspace."""
    data = _read_mcp_config()
    servers = data.get("mcpServers", {})
    rewritten = env.rewrite_mcp_servers_for_workspace(servers, workspace_value)
    if rewritten != servers:
        data["mcpServers"] = rewritten
        _write_mcp_config(data)


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def _safe_error(
    public_msg: str,
    code: str,
    exc: Exception | None = None,
    status: int = 500,
) -> JSONResponse:
    """Return a generic error to the client; log the real exception server-side."""
    if exc is not None:
        _log.error(f"{code}: {exc}")
    return _error(public_msg, code, status=status)


def init_dashboard(
    state_dir: Path | str,
    db_path: Path | str,
    ssl_dir: Path | str,
) -> None:
    """Initialize dashboard module refs. Called once from lifespan."""
    global _state_dir, _db_path, _ssl_dir, _config
    _state_dir = Path(state_dir)
    _db_path = Path(db_path)
    _ssl_dir = Path(ssl_dir)
    _config = Config(_state_dir)


# ---------------------------------------------------------------------------
# Sub-app
# ---------------------------------------------------------------------------

dashboard_app = FastAPI(
    title="Apex Dashboard",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


# V2-05: Admin auth — optional bearer token for defense-in-depth.
# Set APEX_ADMIN_TOKEN env var to require it. Without it, mTLS is the sole boundary.
_ADMIN_TOKEN = env.ADMIN_TOKEN

# Read-only endpoints exempt from admin token (still behind mTLS)
_ADMIN_READ_ONLY = frozenset({
    "/", "/security-config", "/api/status", "/api/status/db", "/api/status/tls",
    "/api/status/models", "/api/config", "/api/config/schema",
    "/api/db/stats", "/api/backups",
    "/api/admin/usage", "/api/admin/usage/config", "/api/admin/usage/export",
    "/api/docs",
    "/api/memory/status", "/api/memory/guidance", "/api/memory/contradictions",
    "/api/memory/metacognition", "/api/memory/feedback", "/api/memory/backends",
    "/api/memory/schedule",
})


@dashboard_app.middleware("http")
async def admin_auth(request: Request, call_next):
    """V2-05: Admin bearer token + CSRF on state-changing requests."""
    path = request.url.path
    if path.startswith("/admin"):
        path = path[len("/admin"):] or "/"
    is_read_only = path in _ADMIN_READ_ONLY or path.startswith("/api/memory-scores/")
    if _ADMIN_TOKEN and not is_read_only:
        auth = request.headers.get("authorization", "")
        cookie_token = request.cookies.get("apex_admin_token", "")
        has_header = hmac.compare_digest(auth.encode(), f"Bearer {_ADMIN_TOKEN}".encode())
        has_cookie = hmac.compare_digest(cookie_token.encode(), _ADMIN_TOKEN.encode())
        if not (has_header or has_cookie):
            return JSONResponse(
                {"error": "Admin authorization required", "code": "ADMIN_AUTH_REQUIRED"},
                status_code=401,
            )

    # CSRF protection on state-changing requests
    if request.method in ("PUT", "POST", "DELETE"):
        if request.headers.get("x-requested-with") != "XMLHttpRequest":
            return JSONResponse(
                {"error": "Missing X-Requested-With header", "code": "CSRF_REJECTED"},
                status_code=403,
            )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

def _error(message: str, code: str, status: int = 500) -> JSONResponse:
    """Standard error response."""
    return JSONResponse(
        {"error": message, "code": code},
        status_code=status,
    )


def _not_initialized() -> JSONResponse:
    return _error(
        "Dashboard not initialized — call init_dashboard() first",
        "NOT_INITIALIZED",
        status_code=503,
    )


def _render_dashboard_html(markup: str) -> HTMLResponse:
    """Serve inline HTML with the admin CSP applied."""
    nonce = secrets.token_hex(16)
    rendered = markup.replace("{{CSP_NONCE}}", nonce)
    try:
        import apex as _lc
        app_version = getattr(_lc, "APP_VERSION", "") or "dev"
    except Exception:
        app_version = "dev"
    rendered = rendered.replace("{{APP_VERSION}}", html.escape(app_version))
    rendered = rendered.encode("utf-8", errors="replace").decode("utf-8")
    csp = (
        f"default-src 'self'; "
        f"script-src 'nonce-{nonce}'; "
        f"style-src 'self' 'unsafe-inline'; "
        f"img-src 'self' data: blob:; "
        f"connect-src 'self' ws: wss:; "
        f"font-src 'self'; "
        f"object-src 'none'; "
        f"base-uri 'self'; "
        f"frame-ancestors 'none';"
    )
    return HTMLResponse(rendered, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Content-Security-Policy": csp,
    })


def _get_persona_row(profile_id: str):
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT id, name, tool_policy FROM agent_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        conn.close()
    return row


# ---------------------------------------------------------------------------
# GET / — Dashboard HTML
# ---------------------------------------------------------------------------

@dashboard_app.get("/", response_class=HTMLResponse)
async def dashboard_index():
    """Serve the Apex Dashboard single-page app."""
    try:
        from dashboard_html import DASHBOARD_HTML
        return _render_dashboard_html(DASHBOARD_HTML)
    except ImportError:
        return HTMLResponse(
            "<html><body style='background:#111;color:#eee;font-family:system-ui;'>"
            "<h1>Apex Dashboard</h1>"
            "<p>dashboard_html.py not found. API endpoints are available at /admin/api/</p>"
            "</body></html>",
            status_code=200,
        )


@dashboard_app.get("/security-config", response_class=HTMLResponse)
async def security_config_index():
    """Serve the standalone security configuration page."""
    try:
        from dashboard_security_html import DASHBOARD_SECURITY_HTML
        return _render_dashboard_html(DASHBOARD_SECURITY_HTML)
    except ImportError:
        return HTMLResponse(
            "<html><body style='background:#111;color:#eee;font-family:system-ui;'>"
            "<h1>Apex Security</h1>"
            "<p>dashboard_security_html.py not found. Security APIs remain available at /admin/api/security/.</p>"
            "</body></html>",
            status_code=200,
        )


# ---------------------------------------------------------------------------
# POST /api/personas/{id}/elevate | /revoke
# ---------------------------------------------------------------------------

@dashboard_app.post("/api/personas/{profile_id}/elevate")
async def api_persona_elevate(profile_id: str, request: Request):
    """Grant temporary Admin access to a persona."""
    if profile_id == SYSTEM_PROFILE_ID:
        return _error("reserved profile", "RESERVED_PROFILE", status=403)
    row = _get_persona_row(profile_id)
    if not row:
        return _error("profile not found", "PROFILE_NOT_FOUND", status=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        minutes = int(body.get("minutes", body.get("duration_minutes", 15)))
    except (TypeError, ValueError):
        return _error("minutes must be an integer", "INVALID_DURATION", status=400)
    if minutes < 1 or minutes > 24 * 60:
        return _error("minutes must be between 1 and 1440", "INVALID_DURATION", status=400)
    try:
        target_level = int(body.get("level", 3))
    except (TypeError, ValueError):
        return _error("level must be an integer", "INVALID_LEVEL", status=400)
    if target_level not in (3, 4):
        return _error("level must be 3 or 4", "INVALID_LEVEL", status=400)

    policy = _normalize_tool_policy(row[2])
    default_level = int(policy.get("default_level", policy.get("level", 1)))
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(timespec="seconds")
    policy["default_level"] = default_level
    policy["level"] = target_level
    policy["elevated_until"] = expires_at
    policy = _set_profile_tool_policy(profile_id, policy, default_level=default_level)
    return JSONResponse({
        "ok": True,
        "profile_id": row[0],
        "name": row[1],
        "tool_policy": policy,
        "expires_at": expires_at,
    })


@dashboard_app.post("/api/personas/{profile_id}/revoke")
async def api_persona_revoke(profile_id: str):
    """Drop a persona back to its default level and clear elevation expiry."""
    if profile_id == SYSTEM_PROFILE_ID:
        return _error("reserved profile", "RESERVED_PROFILE", status=403)
    row = _get_persona_row(profile_id)
    if not row:
        return _error("profile not found", "PROFILE_NOT_FOUND", status=404)
    policy = _normalize_tool_policy(row[2])
    default_level = int(policy.get("default_level", policy.get("level", 1)))
    policy["level"] = default_level
    policy["elevated_until"] = None
    policy = _set_profile_tool_policy(profile_id, policy, default_level=default_level)
    return JSONResponse({
        "ok": True,
        "profile_id": row[0],
        "name": row[1],
        "tool_policy": policy,
    })


# ---------------------------------------------------------------------------
# GET /api/status — Server health overview
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/status")
async def api_status():
    """Server health: uptime, connected clients, model, active sessions."""
    if _config is None:
        return _not_initialized()

    uptime_seconds = time.time() - _start_time

    # Import live state from main server module
    connected_clients = 0
    active_sessions = 0
    model = "unknown"
    try:
        import apex as _lc
        connected_clients = len(getattr(_lc, "_chat_ws", {}))
        active_sessions = len(getattr(_lc, "_clients", {}))
        model = getattr(_lc, "MODEL", "unknown")
    except Exception:
        pass

    return JSONResponse({
        "status": "ok",
        "uptime_seconds": round(uptime_seconds, 1),
        "uptime_human": _format_uptime(uptime_seconds),
        "connected_clients": connected_clients,
        "active_sessions": active_sessions,
        "model": model,
        "started_at": datetime.fromtimestamp(
            _start_time, tz=timezone.utc
        ).isoformat(),
    })


def _format_uptime(seconds: float) -> str:
    """Format seconds into a human-readable string like '2d 5h 13m'."""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _month_window(month: str | None) -> tuple[str, datetime, datetime]:
    """Return normalized month key plus UTC start/end datetimes."""
    if month:
        try:
            start = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError("month must be YYYY-MM") from exc
    else:
        now = datetime.now(timezone.utc)
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if start.month == 12:
        end = datetime(start.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(start.year, start.month + 1, 1, tzinfo=timezone.utc)
    return start.strftime("%Y-%m"), start, end


def _days_in_month(start: datetime, end: datetime) -> int:
    return max(1, (end - start).days)


def _month_label(month_key: str) -> str:
    start = datetime.strptime(month_key, "%Y-%m")
    return start.strftime("%B %Y")


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _price_for_model(model: str) -> dict[str, Any]:
    model_id = str(model or "").strip()
    if model_id in _MODEL_PRICING:
        return dict(_MODEL_PRICING[model_id])
    provider = "local"
    lower = model_id.lower()
    if lower.startswith("claude"):
        provider = "claude"
    elif lower.startswith("codex") or lower.startswith("gpt") or lower.startswith("o3"):
        provider = "codex"
    elif lower.startswith("grok"):
        provider = "xai"
    elif lower:
        provider = "local"
    track = _USAGE_TRACK_BY_BACKEND.get(provider, "local")
    return {
        "display": model_id or "Default",
        "track": track,
        "price_in": 0.0,
        "price_out": 0.0,
        "provider": provider,
    }


def _compute_equivalent_cost(tokens_in: int, tokens_out: int, price_in: float, price_out: float) -> float:
    return round(((tokens_in * price_in) + (tokens_out * price_out)) / 1_000_000.0, 6)


def _message_cost_fields(row: sqlite3.Row) -> dict[str, Any]:
    model = row["model"] or row["profile_model"] or ""
    price = _price_for_model(model)
    tokens_in = _safe_int(row["tokens_in"])
    tokens_out = _safe_int(row["tokens_out"])
    actual_cost = round(_safe_float(row["cost_usd"]), 6)
    equivalent_cost = _compute_equivalent_cost(tokens_in, tokens_out, price["price_in"], price["price_out"])
    profile_backend = (row["profile_backend"] or "").strip().lower()
    track = price["track"]
    provider = price["provider"]
    if profile_backend:
        provider = profile_backend
        track = _USAGE_TRACK_BY_BACKEND.get(profile_backend, track)
    if track == "api":
        display_cost = actual_cost if actual_cost > 0 else equivalent_cost
        equivalent_cost = display_cost
        cost_source = "reported" if actual_cost > 0 else ("estimated" if display_cost > 0 else "missing")
    elif track == "subscription":
        display_cost = 0.0
        cost_source = "estimated" if equivalent_cost > 0 else "missing"
    else:
        display_cost = 0.0
        equivalent_cost = 0.0
        cost_source = "local"
    return {
        "model": model,
        "display": price["display"],
        "provider": provider,
        "track": track,
        "price_in": price["price_in"],
        "price_out": price["price_out"],
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(display_cost, 6),
        "equivalent_cost_usd": round(equivalent_cost, 6),
        "cost_source": cost_source,
    }


def _pct(part: float, total: float) -> int:
    if total <= 0:
        return 0
    return int(round((part / total) * 100))


def _usage_user_label(chat_type: str | None, category: str | None, primary_user_label: str) -> str:
    ctype = (chat_type or "").strip().lower()
    ccat = (category or "").strip().lower()
    if ctype in {"api"} or ccat in {"alerts", "system", "custom", "test"}:
        return "API / Cron"
    return primary_user_label


def _serialize_provider_utilization(payload: dict[str, Any], *, codex: bool = False) -> dict[str, Any]:
    session = payload.get("session") or {}
    resets_at = session.get("resets_at") if not codex else None
    resets_in = session.get("resets_in")
    utilization = session.get("utilization")
    return {
        "utilization_pct": _safe_int(utilization),
        "resets_at": resets_at,
        "resets_in": resets_in,
        "label": "current window",
        "stale": bool(payload.get("stale", False)),
        "plan": payload.get("plan") or "",
    }


def _generate_usage_insight(cost_track: dict[str, Any], subscription_track: dict[str, Any], provider_utilization: dict[str, Any], by_model: list[dict[str, Any]]) -> dict[str, str]:
    top_api = None
    api_rows = [row for row in by_model if row.get("track") == "api" and row.get("cost_usd", 0) > 0]
    if api_rows:
        top_api = max(api_rows, key=lambda row: row.get("cost_usd", 0))
    claude_util = provider_utilization.get("claude") or {}
    codex_util = provider_utilization.get("codex") or {}
    if claude_util.get("utilization_pct", 0) >= 80:
        return {
            "title": "Usage insight",
            "body": f"Claude window is {claude_util['utilization_pct']}% used. Consider routing lighter drafts to Codex or API models until it resets.",
        }
    if codex_util and codex_util.get("utilization_pct", 0) <= 10 and subscription_track.get("tokens_total", 0) > 0:
        return {
            "title": "Usage insight",
            "body": "Codex utilization is low relative to included capacity. You may be able to shift more drafting there without increasing API spend.",
        }
    if top_api and cost_track.get("total_usd", 0) > 0:
        share = _pct(top_api.get("cost_usd", 0), cost_track["total_usd"])
        return {
            "title": "Usage insight",
            "body": f"{top_api.get('display') or top_api.get('model')} is {share}% of API spend this month. Review whether some of that workload can move to a cheaper tier.",
        }
    if subscription_track.get("tokens_total", 0) > 0:
        return {
            "title": "Usage insight",
            "body": "Subscription usage is the primary driver this month. Watch current provider windows to avoid hitting included-capacity limits.",
        }
    return {
        "title": "Usage insight",
        "body": "Usage is light this month so far. No immediate optimization action stands out yet.",
    }


async def _provider_utilization_snapshot() -> dict[str, Any]:
    providers: dict[str, Any] = {}
    try:
        response = await provider_api_usage()
        if hasattr(response, "body"):
            payload = json.loads(response.body.decode("utf-8"))
            if response.status_code < 400:
                providers["claude"] = _serialize_provider_utilization(payload)
    except Exception as exc:
        _log.debug("usage provider snapshot (claude) failed: %s", exc)
    try:
        response = await provider_api_usage_codex()
        if hasattr(response, "body"):
            payload = json.loads(response.body.decode("utf-8"))
            if response.status_code < 400:
                providers["codex"] = _serialize_provider_utilization(payload, codex=True)
    except Exception as exc:
        _log.debug("usage provider snapshot (codex) failed: %s", exc)
    return providers


def _usage_export_rows(month_start_iso: str, month_end_iso: str) -> list[dict[str, Any]]:
    with _db_lock:
        conn = _get_db()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT m.created_at, m.chat_id, m.speaker_name, m.cost_usd, m.tokens_in, m.tokens_out,
                   c.model, c.type AS chat_type, c.category, p.backend AS profile_backend, p.model AS profile_model
            FROM messages m
            JOIN chats c ON c.id = m.chat_id
            LEFT JOIN agent_profiles p ON p.id = c.profile_id
            WHERE m.role = 'assistant'
              AND m.created_at >= ?
              AND m.created_at < ?
            ORDER BY m.created_at ASC
            """,
            (month_start_iso, month_end_iso),
        ).fetchall()
        conn.close()
    export_rows: list[dict[str, Any]] = []
    for row in rows:
        cost_fields = _message_cost_fields(row)
        export_rows.append({
            "date": row["created_at"],
            "chat_id": row["chat_id"],
            "agent": row["speaker_name"] or "Chat",
            "model": cost_fields["model"] or "default",
            "track": cost_fields["track"],
            "provider": cost_fields["provider"],
            "tokens_in": cost_fields["tokens_in"],
            "tokens_out": cost_fields["tokens_out"],
            "cost_usd": round(cost_fields["cost_usd"], 6),
            "equivalent_cost_usd": round(cost_fields["equivalent_cost_usd"], 6),
            "cost_source": cost_fields["cost_source"],
        })
    return export_rows


async def _build_usage_payload(month: str | None) -> dict[str, Any]:
    if _config is None:
        raise RuntimeError("Dashboard not initialized")
    month_key, month_start, month_end = _month_window(month)
    month_start_iso = month_start.isoformat()
    month_end_iso = month_end.isoformat()
    days_in_month = _days_in_month(month_start, month_end)
    now = datetime.now(timezone.utc)
    elapsed_end = min(now, month_end)
    days_elapsed = min(max(1, (elapsed_end - month_start).days + 1), days_in_month) if elapsed_end >= month_start else 1
    primary_user_label = str(_config.get("usage", "primary_user_label") or "Dana")
    budget_usd = _safe_int(_config.get("usage", "budget_usd") or 100)
    alert_pct = _safe_int(_config.get("usage", "alert_pct") or 80)
    reset_day = _safe_int(_config.get("usage", "reset_day") or 1)

    with _db_lock:
        conn = _get_db()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT m.created_at, m.chat_id, m.speaker_name, m.cost_usd, m.tokens_in, m.tokens_out,
                   c.model, c.type AS chat_type, c.category, c.profile_id,
                   p.backend AS profile_backend, p.model AS profile_model
            FROM messages m
            JOIN chats c ON c.id = m.chat_id
            LEFT JOIN agent_profiles p ON p.id = c.profile_id
            WHERE m.role = 'assistant'
              AND m.created_at >= ?
              AND m.created_at < ?
            ORDER BY m.created_at ASC
            """,
            (month_start_iso, month_end_iso),
        ).fetchall()
        conn.close()

    daily_api_spend: dict[str, float] = defaultdict(float)
    agent_rollup: dict[str, dict[str, Any]] = defaultdict(lambda: {"name": "", "cost_usd": 0.0, "equivalent_cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0, "api_cost_usd": 0.0, "subscription_equivalent_cost_usd": 0.0, "local_tokens": 0})
    user_rollup: dict[str, dict[str, Any]] = defaultdict(lambda: {"name": "", "cost_usd": 0.0, "equivalent_cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0, "api_cost_usd": 0.0, "subscription_equivalent_cost_usd": 0.0})
    model_rollup: dict[str, dict[str, Any]] = {}

    total_api_cost = 0.0
    subscription_tokens_total = 0
    tokens_by_provider: dict[str, int] = defaultdict(int)
    cost_sources_seen: set[str] = set()

    for row in rows:
        cost_fields = _message_cost_fields(row)
        cost_sources_seen.add(cost_fields["cost_source"])
        date_key = str(row["created_at"] or "")[:10]
        agent_name = row["speaker_name"] or "Chat"
        user_name = _usage_user_label(row["chat_type"], row["category"], primary_user_label)
        model_key = cost_fields["model"] or "default"

        if cost_fields["track"] == "api":
            total_api_cost += cost_fields["cost_usd"]
            daily_api_spend[date_key] += cost_fields["cost_usd"]
        elif cost_fields["track"] == "subscription":
            token_total = cost_fields["tokens_in"] + cost_fields["tokens_out"]
            subscription_tokens_total += token_total
            tokens_by_provider[cost_fields["provider"]] += token_total

        agent_entry = agent_rollup[agent_name]
        agent_entry["name"] = agent_name
        agent_entry["cost_usd"] += cost_fields["cost_usd"]
        agent_entry["equivalent_cost_usd"] += cost_fields["equivalent_cost_usd"]
        agent_entry["tokens_in"] += cost_fields["tokens_in"]
        agent_entry["tokens_out"] += cost_fields["tokens_out"]
        if cost_fields["track"] == "api":
            agent_entry["api_cost_usd"] += cost_fields["cost_usd"]
        elif cost_fields["track"] == "subscription":
            agent_entry["subscription_equivalent_cost_usd"] += cost_fields["equivalent_cost_usd"]
        else:
            agent_entry["local_tokens"] += cost_fields["tokens_in"] + cost_fields["tokens_out"]

        user_entry = user_rollup[user_name]
        user_entry["name"] = user_name
        user_entry["cost_usd"] += cost_fields["cost_usd"]
        user_entry["equivalent_cost_usd"] += cost_fields["equivalent_cost_usd"]
        user_entry["tokens_in"] += cost_fields["tokens_in"]
        user_entry["tokens_out"] += cost_fields["tokens_out"]
        if cost_fields["track"] == "api":
            user_entry["api_cost_usd"] += cost_fields["cost_usd"]
        elif cost_fields["track"] == "subscription":
            user_entry["subscription_equivalent_cost_usd"] += cost_fields["equivalent_cost_usd"]

        if model_key not in model_rollup:
            model_rollup[model_key] = {
                "model": model_key,
                "display": cost_fields["display"],
                "track": cost_fields["track"],
                "provider": cost_fields["provider"],
                "price_in": cost_fields["price_in"],
                "price_out": cost_fields["price_out"],
                "cost_usd": 0.0,
                "equivalent_cost_usd": 0.0,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_source": cost_fields["cost_source"],
            }
        model_entry = model_rollup[model_key]
        model_entry["cost_usd"] += cost_fields["cost_usd"]
        model_entry["equivalent_cost_usd"] += cost_fields["equivalent_cost_usd"]
        model_entry["tokens_in"] += cost_fields["tokens_in"]
        model_entry["tokens_out"] += cost_fields["tokens_out"]
        if model_entry["cost_source"] == "missing" and cost_fields["cost_source"] != "missing":
            model_entry["cost_source"] = cost_fields["cost_source"]

    total_api_cost = round(total_api_cost, 2)
    daily_pace_usd = round(total_api_cost / days_elapsed, 2) if days_elapsed else 0.0
    projected_month_end_usd = round(daily_pace_usd * days_in_month, 2)
    budget_used_pct = _pct(total_api_cost, budget_usd) if budget_usd > 0 else 0

    day_cursor = month_start
    daily_spend: list[dict[str, Any]] = []
    while day_cursor < month_end:
        key = day_cursor.strftime("%Y-%m-%d")
        daily_spend.append({"date": key, "amount": round(daily_api_spend.get(key, 0.0), 2)})
        day_cursor += timedelta(days=1)

    by_agent = []
    for entry in agent_rollup.values():
        by_agent.append({
            "name": entry["name"],
            "cost_usd": round(entry["cost_usd"], 2),
            "equivalent_cost_usd": round(entry["equivalent_cost_usd"], 2),
            "tokens_in": entry["tokens_in"],
            "tokens_out": entry["tokens_out"],
            "pct": _pct(entry["cost_usd"], total_api_cost),
            "track_mix": {
                "api_cost_usd": round(entry["api_cost_usd"], 2),
                "subscription_equivalent_cost_usd": round(entry["subscription_equivalent_cost_usd"], 2),
            },
        })
    by_agent.sort(key=lambda item: (item["cost_usd"], item["equivalent_cost_usd"], item["tokens_out"]), reverse=True)

    by_user = []
    for entry in user_rollup.values():
        by_user.append({
            "name": entry["name"],
            "cost_usd": round(entry["cost_usd"], 2),
            "equivalent_cost_usd": round(entry["equivalent_cost_usd"], 2),
            "tokens_in": entry["tokens_in"],
            "tokens_out": entry["tokens_out"],
            "pct": _pct(entry["cost_usd"], total_api_cost),
            "track_mix": {
                "api_cost_usd": round(entry["api_cost_usd"], 2),
                "subscription_equivalent_cost_usd": round(entry["subscription_equivalent_cost_usd"], 2),
            },
        })
    by_user.sort(key=lambda item: (item["cost_usd"], item["equivalent_cost_usd"], item["tokens_out"]), reverse=True)

    by_model = list(model_rollup.values())
    for entry in by_model:
        entry["cost_usd"] = round(entry["cost_usd"], 2)
        entry["equivalent_cost_usd"] = round(entry["equivalent_cost_usd"], 2)
        entry["pct"] = _pct(entry["cost_usd"], total_api_cost)
    by_model.sort(key=lambda item: (item["cost_usd"], item["equivalent_cost_usd"], item["tokens_out"]), reverse=True)

    subscription_track = {
        "tokens_total": subscription_tokens_total,
        "tokens_by_provider": dict(sorted(tokens_by_provider.items())),
        "equivalent_cost_usd": round(sum(item["equivalent_cost_usd"] for item in by_model if item["track"] == "subscription"), 2),
    }
    cost_track = {
        "total_usd": total_api_cost,
        "daily_pace_usd": daily_pace_usd,
        "projected_month_end_usd": projected_month_end_usd,
        "budget_usd": budget_usd,
        "budget_used_pct": budget_used_pct,
    }

    provider_utilization = await _provider_utilization_snapshot()
    payload = {
        "month": month_key,
        "month_label": _month_label(month_key),
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
        "cost_track": cost_track,
        "subscription_track": subscription_track,
        "daily_spend": daily_spend,
        "by_agent": by_agent,
        "by_user": by_user,
        "by_model": by_model,
        "provider_utilization": provider_utilization,
        "budget": {
            "budget_usd": budget_usd,
            "alert_pct": alert_pct,
            "reset_day": reset_day,
        },
        "cost_source": "reported" if cost_sources_seen == {"reported"} else ("estimated" if "estimated" in cost_sources_seen else "mixed"),
    }
    payload["insight"] = _generate_usage_insight(cost_track, subscription_track, provider_utilization, by_model)
    return payload


@dashboard_app.get("/api/admin/usage")
async def api_admin_usage(month: str | None = None):
    """Return Usage page data for the V2 admin dashboard."""
    if _config is None:
        return _not_initialized()
    try:
        payload = await _build_usage_payload(month)
        return JSONResponse(payload)
    except ValueError as exc:
        return _error(str(exc), "INVALID_MONTH", 400)
    except sqlite3.Error as exc:
        _log.error("Usage query failed: %s", exc)
        return _error("Usage query failed", "USAGE_QUERY_FAILED")


@dashboard_app.get("/api/admin/usage/config")
async def api_admin_usage_config():
    """Return saved Usage budget settings."""
    if _config is None:
        return _not_initialized()
    return JSONResponse({
        "budget_usd": _safe_int(_config.get("usage", "budget_usd") or 100),
        "alert_pct": _safe_int(_config.get("usage", "alert_pct") or 80),
        "reset_day": _safe_int(_config.get("usage", "reset_day") or 1),
        "primary_user_label": str(_config.get("usage", "primary_user_label") or "Dana"),
    })


@dashboard_app.post("/api/admin/usage/config")
async def api_admin_usage_config_update(request: Request):
    """Update saved Usage budget settings."""
    if _config is None:
        return _not_initialized()
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON", "INVALID_JSON", 400)
    if not isinstance(body, dict):
        return _error("Request body must be a JSON object", "INVALID_BODY", 400)
    updates: dict[str, Any] = {}
    for key in ("budget_usd", "alert_pct", "reset_day", "primary_user_label"):
        if key in body:
            updates[key] = body[key]
    if not updates:
        return _error("No usage settings provided", "EMPTY_UPDATE", 400)
    try:
        values, restart_required = _config.update_section("usage", updates)
        return JSONResponse({
            "status": "ok",
            "section": "usage",
            "config": values,
            "restart_required": restart_required,
        })
    except ValueError as exc:
        _log.warning("Usage config validation error: %s", exc)
        return _error("Invalid usage configuration", "VALIDATION_ERROR", 422)


@dashboard_app.get("/api/admin/usage/export")
async def api_admin_usage_export(month: str | None = None):
    """Export assistant-message usage rows for the selected month as CSV."""
    try:
        _, month_start, month_end = _month_window(month)
    except ValueError as exc:
        return _error(str(exc), "INVALID_MONTH", 400)
    rows = _usage_export_rows(month_start.isoformat(), month_end.isoformat())
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "date", "chat_id", "agent", "model", "track", "provider",
            "tokens_in", "tokens_out", "cost_usd", "equivalent_cost_usd", "cost_source",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)
    month_key = month_start.strftime("%Y-%m")
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="usage-{month_key}.csv"'},
    )


# ---------------------------------------------------------------------------
# GET /api/status/db — Database statistics
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/status/db")
async def api_status_db():
    """Database stats: row counts and file size."""
    if _db_path is None:
        return _not_initialized()

    if not _db_path.exists():
        return _error("Database file not found", "DB_NOT_FOUND", 404)

    try:
        file_size = _db_path.stat().st_size
        conn = sqlite3.connect(str(_db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        chat_count = conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
        message_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        alert_count = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]

        # Recent activity
        latest_message = conn.execute(
            "SELECT created_at FROM messages ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        latest_alert = conn.execute(
            "SELECT created_at FROM alerts ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

        conn.close()

        return JSONResponse({
            "status": "ok",
            "file_size_bytes": file_size,
            "file_size_human": _format_bytes(file_size),
            "chat_count": chat_count,
            "message_count": message_count,
            "alert_count": alert_count,
            "latest_message_at": latest_message[0] if latest_message else None,
            "latest_alert_at": latest_alert[0] if latest_alert else None,
        })
    except sqlite3.Error as e:
        _log.error(f"Database error in status/db: {e}")
        return _error("Database operation failed", "DB_ERROR")


def _format_bytes(n: int) -> str:
    """Format byte count to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------------------
# GET /api/status/tls — Certificate expiry and status
# ---------------------------------------------------------------------------

def _get_tls_status_data() -> dict[str, Any]:
    """TLS certificate expiry dates, days remaining, and warnings."""
    if _ssl_dir is None:
        raise RuntimeError("Dashboard not initialized")

    if not _ssl_dir.exists():
        raise FileNotFoundError("SSL directory not found")

    certs = {
        "ca": _ssl_dir / "ca.crt",
        "server": _ssl_dir / "apex.crt",
        "client": _ssl_dir / "client.crt",
    }

    results: dict[str, Any] = {}
    warnings: list[str] = []

    for name, path in certs.items():
        if not path.exists():
            results[name] = {"status": "missing", "path": str(path)}
            warnings.append(f"{name} certificate not found")
            continue

        info = _parse_cert(path)
        if info is None:
            results[name] = {"status": "error", "path": str(path)}
            warnings.append(f"Failed to parse {name} certificate")
            continue

        results[name] = {
            "status": "ok",
            "path": str(path),
            "subject": info["subject"],
            "expires": info["expires"],
            "days_remaining": info["days_remaining"],
        }

        if info["days_remaining"] < 0:
            results[name]["status"] = "expired"
            warnings.append(f"{name} certificate has expired")
        elif info["days_remaining"] < 30:
            results[name]["status"] = "expiring_soon"
            warnings.append(
                f"{name} certificate expires in {info['days_remaining']} days"
            )

    overall = "ok"
    if any(r.get("status") == "expired" for r in results.values()):
        overall = "critical"
    elif any(r.get("status") in ("expiring_soon", "missing", "error")
             for r in results.values()):
        overall = "warning"

    return {
        "status": overall,
        "certificates": results,
        "warnings": warnings,
    }


@dashboard_app.get("/api/status/tls")
async def api_status_tls():
    """TLS certificate expiry dates, days remaining, and warnings."""
    if _ssl_dir is None:
        return _not_initialized()
    if not _ssl_dir.exists():
        return _error("SSL directory not found", "SSL_DIR_NOT_FOUND", 404)
    try:
        return JSONResponse(_get_tls_status_data())
    except RuntimeError:
        return _not_initialized()
    except FileNotFoundError:
        return _error("SSL directory not found", "SSL_DIR_NOT_FOUND", 404)


def _parse_cert(path: Path) -> dict[str, Any] | None:
    """Parse certificate with openssl and return subject, expiry, days remaining."""
    try:
        result = subprocess.run(
            [
                "openssl", "x509", "-in", str(path),
                "-noout", "-enddate", "-subject",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None

        output = result.stdout

        # Parse expiry: notAfter=Mar 24 21:27:00 2027 GMT
        expires_str = ""
        days_remaining = -1
        match = re.search(r"notAfter=(.+)", output)
        if match:
            expires_str = match.group(1).strip()
            try:
                expires_dt = datetime.strptime(
                    expires_str, "%b %d %H:%M:%S %Y %Z"
                )
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
                delta = expires_dt - datetime.now(timezone.utc)
                days_remaining = delta.days
            except ValueError:
                pass

        # Parse subject
        subject = ""
        match = re.search(r"subject=(.+)", output)
        if match:
            subject = match.group(1).strip()

        return {
            "subject": subject,
            "expires": expires_str,
            "days_remaining": days_remaining,
        }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _set_live_alert_token(new_token: str) -> None:
    """Update the in-process alert token source of truth without a restart."""
    os.environ["APEX_ALERT_TOKEN"] = new_token
    env.ALERT_TOKEN = new_token
    try:
        import apex as _lc
        _lc.ALERT_TOKEN = _lc._Secret(new_token)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# GET /api/status/models — Model provider reachability
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/status/models")
async def api_status_models():
    """Check reachability of Claude, Ollama, and Grok providers."""
    if _config is None:
        return _not_initialized()

    ollama_url = _config.get("models", "ollama_url") or "http://localhost:11434"

    results: dict[str, Any] = {}

    # Claude — check for API key or Agent SDK
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    sdk_available = False
    try:
        import claude_agent_sdk  # noqa: F401
        sdk_available = True
    except ImportError:
        pass
    if anthropic_key or sdk_available:
        detail = "Agent SDK" if sdk_available else "ANTHROPIC_API_KEY"
        results["claude"] = {
            "status": "configured",
            "detail": f"{detail} is available",
        }
    else:
        results["claude"] = {
            "status": "not_configured",
            "detail": "No API key or Agent SDK found",
        }

    # Ollama — ping /api/tags
    results["ollama"] = _ping_ollama(ollama_url)

    # Grok — check for API key
    xai_key = os.environ.get("XAI_API_KEY", "")
    if xai_key:
        results["grok"] = {
            "status": "configured",
            "detail": "XAI_API_KEY is set",
        }
    else:
        results["grok"] = {
            "status": "not_configured",
            "detail": "XAI_API_KEY not found in environment",
        }

    # Codex — check for OpenAI API key
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        results["codex"] = {
            "status": "configured",
            "detail": "OPENAI_API_KEY is set",
        }
    else:
        results["codex"] = {
            "status": "not_configured",
            "detail": "OPENAI_API_KEY not found in environment",
        }

    # Overall status
    statuses = [r["status"] for r in results.values()]
    if all(s in ("reachable", "configured") for s in statuses):
        overall = "ok"
    elif any(s in ("reachable", "configured") for s in statuses):
        overall = "partial"
    else:
        overall = "down"

    return JSONResponse({
        "status": overall,
        "providers": results,
    })


def _validate_ollama_url(url: str) -> bool:
    """Only allow http/https to localhost/known hosts."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    allowed_hosts = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
    if parsed.hostname not in allowed_hosts:
        return False
    return True


def _ping_ollama(base_url: str) -> dict[str, Any]:
    """Ping Ollama /api/tags and return status + available models."""
    if not _validate_ollama_url(base_url):
        return {
            "status": "invalid_url",
            "url": base_url,
            "detail": "URL must be http/https to localhost or known local hosts",
        }
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            models = [m.get("name", "?") for m in data.get("models", [])]
            return {
                "status": "reachable",
                "url": base_url,
                "models": models,
                "model_count": len(models),
            }
    except urllib.error.URLError as e:
        _log.debug(f"Ollama ping failed: {e}")
        return {
            "status": "unreachable",
            "url": base_url,
            "detail": "Connection failed",
        }
    except Exception as e:
        _log.debug(f"Ollama ping error: {e}")
        return {
            "status": "unreachable",
            "url": base_url,
            "detail": "Connection failed",
        }


# ---------------------------------------------------------------------------
# GET /api/config — Full config (secrets redacted)
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/config")
async def api_config():
    """Return full configuration with readonly fields computed at runtime."""
    if _config is None:
        return _not_initialized()

    try:
        data = _config.get_all()
        return JSONResponse({
            "status": "ok",
            "config": data,
        })
    except Exception as e:
        _log.error(f"Config read error: {e}")
        return _error("Failed to read configuration", "CONFIG_READ_ERROR")


# ---------------------------------------------------------------------------
# GET /api/config/schema — Schema for UI form rendering
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/config/schema")
async def api_config_schema():
    """Return the config schema for dynamic UI form generation."""
    return JSONResponse({
        "status": "ok",
        "schema": Config.get_schema(),
    })


# ---------------------------------------------------------------------------
# PUT /api/config/server — Update server section
# ---------------------------------------------------------------------------

@dashboard_app.put("/api/config/server")
async def api_config_update_server(request: Request):
    """Update server configuration (host, port, debug)."""
    return await _update_config_section("server", request)


# ---------------------------------------------------------------------------
# PUT /api/config/models — Update models section
# ---------------------------------------------------------------------------

@dashboard_app.put("/api/config/models")
async def api_config_update_models(request: Request):
    """Update model configuration (default model, Ollama URL, etc)."""
    return await _update_config_section("models", request)


# ---------------------------------------------------------------------------
# PUT /api/config/workspace — Update workspace section
# ---------------------------------------------------------------------------

@dashboard_app.put("/api/config/workspace")
async def api_config_update_workspace(request: Request):
    """Update workspace configuration (path, whisper, etc).

    The browser setup wizard sends permission_mode in the workspace payload,
    but it belongs in the models section — intercept and route it correctly.
    """
    if _config is None:
        return _not_initialized()

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON in request body", "INVALID_JSON", status=400)

    if not isinstance(body, dict):
        return _error("Request body must be a JSON object", "INVALID_BODY", status=400)

    if not body:
        return _error("No fields to update", "EMPTY_UPDATE", status=400)

    if "path" in body:
        body["path"] = _normalize_workspace_path_value(body.get("path"))

    # permission_mode belongs in models, not workspace — route it there.
    perm = body.pop("permission_mode", None)
    if perm:
        try:
            _config.update_section("models", {"permission_mode": perm})
        except (KeyError, ValueError) as e:
            _log.warning("Config permission_mode routing failed: %s", e)

    if not body:
        # Only permission_mode was sent — nothing left for workspace
        return JSONResponse({
            "status": "ok",
            "section": "workspace",
            "config": {"permission_mode": perm},
            "restart_required": False,
        })

    try:
        new_values, restart_required = _config.update_section("workspace", body)
        _sync_filesystem_mcp_workspace_roots(str(new_values.get("path", "")))
        if perm:
            new_values["permission_mode"] = perm
        return JSONResponse({
            "status": "ok",
            "section": "workspace",
            "config": new_values,
            "restart_required": restart_required,
        })
    except KeyError as e:
        _log.warning("Config update unknown section: %s", e)
        return _error("Unknown configuration section", "UNKNOWN_SECTION", status=400)
    except ValueError as e:
        _log.warning("Config validation error: %s", e)
        return _error("Invalid configuration value", "VALIDATION_ERROR", status=422)
    except Exception as e:
        _log.error("Config update failed: %s", e)
        return _error("Configuration update failed", "CONFIG_WRITE_ERROR")


async def _update_config_section(section: str, request: Request) -> JSONResponse:
    """Generic config section updater with validation."""
    if _config is None:
        return _not_initialized()

    try:
        body = await request.json()
    except Exception:
        return _error(
            "Invalid JSON in request body",
            "INVALID_JSON",
            status=400,
        )

    if not isinstance(body, dict):
        return _error(
            "Request body must be a JSON object",
            "INVALID_BODY",
            status=400,
        )

    if not body:
        return _error(
            "No fields to update",
            "EMPTY_UPDATE",
            status=400,
        )

    try:
        new_values, restart_required = _config.update_section(section, body)
        return JSONResponse({
            "status": "ok",
            "section": section,
            "config": new_values,
            "restart_required": restart_required,
        })
    except KeyError as e:
        _log.warning(f"Config update unknown section: {e}")
        return _error("Unknown configuration section", "UNKNOWN_SECTION", status=400)
    except ValueError as e:
        _log.warning(f"Config validation error: {e}")
        return _error("Invalid configuration value", "VALIDATION_ERROR", status=422)
    except Exception as e:
        _log.error(f"Config update failed: {e}")
        return _error("Configuration update failed", "CONFIG_WRITE_ERROR")


@dashboard_app.get("/api/policy/tools")
async def api_policy_tools():
    """Return normalized tool catalog and current Workspace + Browser selection."""
    if _config is None:
        return _not_initialized()
    return JSONResponse(
        {
            "workspace_tools": get_workspace_tool_patterns(),
            "never_allowed_commands": get_policy_never_allowed_commands(),
            "blocked_path_prefixes": get_policy_blocked_path_prefixes(),
            "catalog": get_tool_catalog(),
        }
    )


@dashboard_app.put("/api/policy/tools")
async def api_policy_tools_update(request: Request):
    """Update policy-controlled tool and guardrail settings."""
    if _config is None:
        return _not_initialized()
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON", "INVALID_JSON", 400)
    updates: dict[str, str] = {}
    for key in ("workspace_tools", "never_allowed_commands", "blocked_path_prefixes"):
        if key not in body:
            continue
        raw = body.get(key, [])
        if isinstance(raw, list):
            text = "\n".join(str(item).strip() for item in raw if str(item).strip())
        else:
            text = str(raw or "")
        updates[key] = text
    if not updates:
        return _error("No policy fields provided", "MISSING_POLICY_FIELDS", 400)
    try:
        new_values, restart_required = _config.update_section("policy", updates)
        return JSONResponse(
            {
                "status": "ok",
                "section": "policy",
                "config": new_values,
                "workspace_tools": get_workspace_tool_patterns(),
                "never_allowed_commands": get_policy_never_allowed_commands(),
                "blocked_path_prefixes": get_policy_blocked_path_prefixes(),
                "catalog": get_tool_catalog(),
                "restart_required": restart_required,
            }
        )
    except ValueError as e:
        _log.warning("Policy tool config validation error: %s", e)
        return _error("Invalid policy tool configuration", "VALIDATION_ERROR", 422)


@dashboard_app.get("/api/policy/denials")
async def api_policy_denials(request: Request):
    """Summarize recent blocked tool activity from saved tool events."""
    try:
        hours = max(1, min(int(request.query_params.get("hours", "24")), 24 * 14))  # type: ignore[name-defined]
    except (TypeError, ValueError):
        hours = 24
    chat_id = (request.query_params.get("chat_id", "") or "").strip()  # type: ignore[name-defined]

    where_parts = [
        "m.created_at >= datetime('now', ?)",
        "CAST(json_extract(j.value, '$.result.is_error') AS INTEGER) = 1",
    ]
    params: list[Any] = [f"-{hours} hours"]
    if chat_id:
        where_parts.append("m.chat_id = ?")
        params.append(chat_id)

    base_cte = f"""
        WITH ev AS (
            SELECT
                m.chat_id AS chat_id,
                c.title AS chat_title,
                m.created_at AS created_at,
                COALESCE(NULLIF(m.speaker_name, ''), m.role, 'unknown') AS speaker_name,
                COALESCE(json_extract(j.value, '$.name'), '') AS tool_name,
                COALESCE(
                    json_extract(j.value, '$.input.command'),
                    json_extract(j.value, '$.input.file_path'),
                    json_extract(j.value, '$.input.path'),
                    ''
                ) AS target,
                COALESCE(json_extract(j.value, '$.result.content'), '') AS reason
            FROM messages m
            JOIN chats c ON c.id = m.chat_id
            JOIN json_each(m.tool_events) j
            WHERE {" AND ".join(where_parts)}
        )
    """

    def _rows(sql: str) -> list[dict[str, Any]]:
        with _db_lock:
            conn = _get_db()
            try:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
            finally:
                conn.close()

    top_tools = _rows(
        base_cte
        + """
        SELECT tool_name, COUNT(*) AS count
        FROM ev
        GROUP BY tool_name
        ORDER BY count DESC, tool_name ASC
        LIMIT 12
        """
    )
    top_reasons = _rows(
        base_cte
        + """
        SELECT substr(reason, 1, 180) AS reason, COUNT(*) AS count
        FROM ev
        GROUP BY substr(reason, 1, 180)
        ORDER BY count DESC, reason ASC
        LIMIT 12
        """
    )
    by_speaker = _rows(
        base_cte
        + """
        SELECT speaker_name, COUNT(*) AS count
        FROM ev
        GROUP BY speaker_name
        ORDER BY count DESC, speaker_name ASC
        LIMIT 12
        """
    )
    examples = _rows(
        base_cte
        + """
        SELECT
            chat_id,
            chat_title,
            speaker_name,
            tool_name,
            target,
            substr(reason, 1, 220) AS reason,
            created_at
        FROM ev
        ORDER BY created_at DESC
        LIMIT 20
        """
    )
    total_rows = _rows(
        base_cte
        + """
        SELECT COUNT(*) AS total_denials
        FROM ev
        """
    )

    return JSONResponse(
        {
            "status": "ok",
            "hours": hours,
            "chat_id": chat_id or None,
            "total_denials": int((total_rows[0]["total_denials"] if total_rows else 0) or 0),
            "top_tools": top_tools,
            "top_reasons": top_reasons,
            "by_speaker": by_speaker,
            "examples": examples,
        }
    )


# ===========================================================================
# MCP Server Management
# ===========================================================================

_MCP_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
_MCP_VALID_TYPES = frozenset({"stdio", "sse", "http"})
_MCP_ALLOWED_STDIO_COMMANDS = frozenset({"npx", "uvx", "node", "python3", "deno", "docker"})
_MCP_ALLOWED_STDIO_PREFIXES = ("mcp-", "mcp_")
_MCP_BLOCKED_STDIO_PATHS = frozenset({"/bin/sh", "/bin/bash", "/bin/zsh"})
_MCP_BLOCKED_STDIO_NAMES = frozenset({"sh", "bash", "zsh"})
_MCP_BLOCKED_ENV_KEYS = frozenset({
    "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH", "PYTHONPATH", "NODE_OPTIONS", "BASH_ENV",
})
_MCP_SHELL_META_TOKENS = ("&&", "||", "$(", "`", "|", ";")


def _mcp_path() -> Path:
    """Path to MCP server config file."""
    return _state_dir / "mcp_servers.json" if _state_dir else Path("/dev/null")


def _read_mcp_config() -> dict:
    p = _mcp_path()
    if not p.exists():
        return {"mcpServers": {}}
    try:
        data = json.loads(p.read_text())
        if not isinstance(data.get("mcpServers"), dict):
            data["mcpServers"] = {}
        return data
    except (json.JSONDecodeError, OSError):
        return {"mcpServers": {}}


def _write_mcp_config(data: dict) -> None:
    p = _mcp_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, str(p))
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _validate_mcp_server(body: dict) -> str | None:
    """Validate MCP server config. Returns error message or None if valid."""
    stype = body.get("type", "")
    if stype not in _MCP_VALID_TYPES:
        return f"Invalid type: {stype}. Must be one of: {', '.join(sorted(_MCP_VALID_TYPES))}"
    if stype == "stdio":
        cmd = body.get("command", "")
        if not cmd or not isinstance(cmd, str):
            return "stdio servers require a 'command' string"
        if ".." in cmd:
            return "Path traversal not allowed in command"
        resolved = shutil.which(cmd)
        if not resolved:
            return f"Command not found: {cmd}"
        resolved_path = Path(resolved)
        resolved_name = resolved_path.name.lower()
        if (
            str(resolved_path) in _MCP_BLOCKED_STDIO_PATHS
            or resolved_name in _MCP_BLOCKED_STDIO_NAMES
        ):
            return "Shell interpreters are not allowed for MCP stdio servers"
        if not (
            resolved_name in _MCP_ALLOWED_STDIO_COMMANDS
            or resolved_name.startswith(_MCP_ALLOWED_STDIO_PREFIXES)
        ):
            return (
                "Unsupported stdio command. Allowed launchers are npx, uvx, node, "
                "python3, deno, or binaries prefixed with 'mcp-'"
            )
    else:
        url = body.get("url", "")
        if not url or not isinstance(url, str):
            return f"{stype} servers require a 'url' string"
        from urllib.parse import urlparse as _urlparse
        parsed = _urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return "URL must use http or https scheme"
    args = body.get("args")
    if args is not None:
        if not isinstance(args, list) or len(args) > 50:
            return "'args' must be a list of max 50 entries"
        if not all(isinstance(a, str) for a in args):
            return "'args' must contain only strings"
        for arg in args:
            if any(token in arg for token in _MCP_SHELL_META_TOKENS):
                return "Shell metacharacters are not allowed in MCP args"
    env = body.get("env")
    if env is not None:
        if not isinstance(env, dict):
            return "'env' must be a dict"
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            return "'env' keys and values must be strings"
        blocked = sorted(k for k in env if k.upper() in _MCP_BLOCKED_ENV_KEYS)
        if blocked:
            return f"Blocked environment variables are not allowed: {', '.join(blocked)}"
    headers = body.get("headers")
    if headers is not None:
        if not isinstance(headers, dict):
            return "'headers' must be a dict"
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
            return "'headers' keys and values must be strings"
    return None


@dashboard_app.get("/api/mcp/servers")
async def api_mcp_servers():
    """List all configured MCP servers."""
    if _state_dir is None:
        return _not_initialized()
    data = _read_mcp_config()
    data["mcpServers"] = env.rewrite_mcp_servers_for_workspace(data.get("mcpServers", {}))
    return JSONResponse({
        "mcpServers": data.get("mcpServers", {}),
        "count": len(data.get("mcpServers", {})),
    })


@dashboard_app.post("/api/mcp/servers")
async def api_mcp_add_server(request: Request):
    """Add a new MCP server."""
    if _state_dir is None:
        return _not_initialized()
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON", "INVALID_JSON", 400)

    name = str(body.get("name", "")).strip()
    if not name or not _MCP_NAME_RE.match(name):
        return _error(
            "Server name must be 1-64 alphanumeric chars, dashes, or underscores",
            "INVALID_NAME", 400,
        )

    err = _validate_mcp_server(body)
    if err:
        return _error(err, "INVALID_CONFIG", 400)

    data = _read_mcp_config()
    if name in data["mcpServers"]:
        return _error(f"Server '{name}' already exists", "DUPLICATE", 409)

    # Build config — only include known fields
    cfg: dict[str, Any] = {"type": body["type"], "enabled": body.get("enabled", True)}
    for field in ("command", "args", "env", "url", "headers"):
        if field in body:
            cfg[field] = body[field]

    data["mcpServers"][name] = cfg
    _write_mcp_config(data)
    _log.info(f"MCP server added: {name} ({body['type']})")
    return JSONResponse({"status": "ok", "name": name, "config": cfg}, status_code=201)


@dashboard_app.put("/api/mcp/servers/{name}")
async def api_mcp_update_server(name: str, request: Request):
    """Update an MCP server config."""
    if _state_dir is None:
        return _not_initialized()
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON", "INVALID_JSON", 400)

    data = _read_mcp_config()
    if name not in data["mcpServers"]:
        return _error(f"Server '{name}' not found", "NOT_FOUND", 404)

    existing = data["mcpServers"][name]

    # If type is changing or present, validate the full config
    merged = {**existing, **body}
    if "type" in body or any(f in body for f in ("command", "url", "args", "env", "headers")):
        err = _validate_mcp_server(merged)
        if err:
            return _error(err, "INVALID_CONFIG", 400)

    # Apply updates — only known fields
    for field in ("type", "command", "args", "env", "url", "headers", "enabled"):
        if field in body:
            existing[field] = body[field]

    _write_mcp_config(data)
    _log.info(f"MCP server updated: {name}")
    return JSONResponse({"status": "ok", "name": name, "config": existing})


@dashboard_app.delete("/api/mcp/servers/{name}")
async def api_mcp_delete_server(name: str):
    """Remove an MCP server."""
    if _state_dir is None:
        return _not_initialized()
    data = _read_mcp_config()
    if name not in data["mcpServers"]:
        return _error(f"Server '{name}' not found", "NOT_FOUND", 404)
    del data["mcpServers"][name]
    _write_mcp_config(data)
    _log.info(f"MCP server removed: {name}")
    return JSONResponse({"status": "ok", "name": name})


@dashboard_app.get("/api/mcp/status")
async def api_mcp_status():
    """Get live MCP status from active SDK clients."""
    if _state_dir is None:
        return _not_initialized()
    from state import _clients
    statuses = []
    for key, client in list(_clients.items()):
        try:
            if hasattr(client, "get_mcp_status"):
                status = client.get_mcp_status()
                statuses.append({"client_key": key, "mcp": status})
        except Exception as e:
            statuses.append({"client_key": key, "error": str(e)})
    config = _read_mcp_config()
    return JSONResponse({
        "configured": len(config.get("mcpServers", {})),
        "active_clients": len(statuses),
        "statuses": statuses,
    })


# ---------------------------------------------------------------------------
# POST /api/server/restart — Signal restart required
# ---------------------------------------------------------------------------

@dashboard_app.post("/api/server/restart")
async def api_server_restart():
    """Signal that a server restart is needed.

    Does not actually restart — the operator must restart manually
    or the process supervisor will handle it.
    """
    return JSONResponse({
        "status": "ok",
        "restart_required": True,
        "message": "Server restart required. Restart the process manually or "
                   "via your process supervisor.",
    })


# ===========================================================================
# Phase 2 — TLS Certificate Management
# ===========================================================================

_CN_RE = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")
# Each DNS label: starts+ends with alnum, may contain hyphens, max 63 chars.
_DNS_LABEL_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$")


def _require_ssl_dir() -> Path | None:
    """Return _ssl_dir or None (caller should return _not_initialized())."""
    return _ssl_dir


def _require_ca() -> tuple[Path, Path] | None:
    """Return (ca.crt, ca.key) paths if both exist, else None."""
    if _ssl_dir is None:
        return None
    ca_crt = _ssl_dir / "ca.crt"
    ca_key = _ssl_dir / "ca.key"
    if not ca_crt.exists() or not ca_key.exists():
        return None
    return ca_crt, ca_key


# ---------------------------------------------------------------------------
# Encrypted key helpers (Phase 2 of SSL keystore)
# ---------------------------------------------------------------------------

def _get_ssl_keystore():
    """Lazy-import setup.ssl_keystore; returns module or None."""
    try:
        import setup.ssl_keystore as mod
        return mod
    except ImportError:
        # Add APEX_ROOT to sys.path and retry
        apex_root = str(_state_dir.parent) if _state_dir else None
        if apex_root and apex_root not in sys.path:
            sys.path.insert(0, apex_root)
            try:
                import setup.ssl_keystore as mod
                return mod
            except ImportError:
                pass
    return None


class _DecryptedCAKey:
    """Context manager that provides a usable CA key path.

    If the key is encrypted, decrypts to a temp file and shreds on exit.
    If unencrypted or keystore unavailable, returns the original path.
    """
    def __init__(self, ca_key: Path):
        self._ca_key = ca_key
        self._tmp: Path | None = None
        self.path = ca_key

    def __enter__(self):
        ks = _get_ssl_keystore()
        if ks and ks.is_key_encrypted(self._ca_key):
            pw = ks.retrieve_passphrase()
            if pw:
                self._tmp = ks.decrypt_key_to_tempfile(self._ca_key, pw)
                self.path = self._tmp
        return self

    def __exit__(self, *exc):
        if self._tmp is not None:
            ks = _get_ssl_keystore()
            if ks:
                ks.shred_file(self._tmp)
            else:
                self._tmp.unlink(missing_ok=True)
            self._tmp = None


def _encrypt_new_key(key_path: Path) -> None:
    """Encrypt a newly generated private key if the keystore is active.

    DISABLED: auto-encryption broke cert management (keys encrypted with
    unrecoverable passwords, forcing full CA regeneration + device reinstall).
    Re-enable once proper keystore password management is built.
    """
    return


def _harden_ssl_dir(ssl_dir: Path) -> None:
    """Lock down the SSL directory and any private key files inside it.

    - Directory: 0700 (owner-only access)
    - Private keys (.key, .pem, .p12, .pfx): 0600 (owner read/write only)
    - Certificates (.crt, .csr, .cnf, .srl): 0644 (world-readable is fine)
    """
    try:
        ssl_dir.chmod(0o700)
    except OSError:
        _log.warning("Could not chmod SSL directory %s", ssl_dir)
    _KEY_SUFFIXES = frozenset({".key", ".pem", ".p12", ".pfx"})
    for item in ssl_dir.iterdir():
        if not item.is_file():
            continue
        try:
            if item.suffix.lower() in _KEY_SUFFIXES:
                item.chmod(0o600)
            else:
                item.chmod(0o644)
        except OSError:
            _log.warning("Could not chmod %s", item)


def _parse_cert_full(path: Path) -> dict[str, Any] | None:
    """Parse a certificate for full details: subject, issuer, expiry,
    serial, fingerprint, SANs."""
    try:
        result = subprocess.run(
            [
                "openssl", "x509", "-in", str(path),
                "-noout", "-subject", "-issuer", "-enddate",
                "-serial", "-fingerprint", "-text",
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None

        out = result.stdout

        def _extract(label: str) -> str:
            m = re.search(rf"{label}=(.+)", out)
            return m.group(1).strip() if m else ""

        subject = _extract("subject")
        issuer = _extract("issuer")
        expires_str = _extract("notAfter")
        serial = _extract("serial")

        # Fingerprint line: SHA1 Fingerprint=AA:BB:...
        fingerprint = ""
        m = re.search(r"Fingerprint=([0-9A-Fa-f:]+)", out)
        if m:
            fingerprint = m.group(1)

        # Expiry as days remaining
        days_remaining = -1
        if expires_str:
            try:
                expires_dt = datetime.strptime(
                    expires_str, "%b %d %H:%M:%S %Y %Z"
                )
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
                delta = expires_dt - datetime.now(timezone.utc)
                days_remaining = delta.days
            except ValueError:
                pass

        # SANs — look for "X509v3 Subject Alternative Name" block
        sans: list[str] = []
        san_match = re.search(
            r"X509v3 Subject Alternative Name:\s*\n\s*(.+)", out
        )
        if san_match:
            raw = san_match.group(1).strip()
            sans = [s.strip() for s in raw.split(",") if s.strip()]

        return {
            "subject": subject,
            "issuer": issuer,
            "expires": expires_str,
            "days_remaining": days_remaining,
            "serial": serial,
            "fingerprint": fingerprint,
            "sans": sans,
        }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _validate_cn(cn: str) -> str | None:
    """Return error message if CN is invalid, else None."""
    if not cn:
        return "cn is required"
    if not _CN_RE.match(cn):
        return "cn must be alphanumeric/hyphens only, max 64 chars"
    return None


def _validate_san_entry(entry: str) -> str | None:
    """Return error message if SAN entry is invalid, else None.

    Rejects newlines and control characters (S-DA2: newline injection into
    ext.cnf writes arbitrary OpenSSL config sections).  IP values are
    validated via the ipaddress stdlib module; DNS values are validated
    label-by-label with _DNS_LABEL_RE.
    """
    if not isinstance(entry, str):
        return "SAN entries must be strings"
    # Reject newlines and any other control characters before anything else —
    # these are the injection vector for ext.cnf manipulation.
    if re.search(r"[\x00-\x1f\x7f]", entry):
        return f"SAN entry contains control characters: {entry!r}"
    san_type, sep, san_val = entry.partition(":")
    if sep != ":" or san_type not in ("IP", "DNS"):
        return f"Invalid SAN entry '{entry}': must start with 'IP:' or 'DNS:'"
    if not san_val:
        return f"SAN value is empty in '{entry}'"
    # Whitespace in the value portion would also corrupt ext.cnf.
    if re.search(r"\s", san_val):
        return f"SAN value contains whitespace: {san_val!r}"
    if san_type == "IP":
        try:
            ipaddress.ip_address(san_val)
        except ValueError:
            return f"Invalid IP address in SAN: {san_val!r}"
    else:  # DNS
        # Strip leading wildcard prefix before label validation.
        hostname = san_val[2:] if san_val.startswith("*.") else san_val
        labels = hostname.split(".")
        if not labels or any(
            not _DNS_LABEL_RE.match(lbl) for lbl in labels
        ):
            return f"Invalid DNS hostname in SAN: {san_val!r}"
    return None


# ---------------------------------------------------------------------------
# GET /api/tls/ca — CA certificate details
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/tls/ca")
async def api_tls_ca():
    """CA certificate details: subject, issuer, expiry, serial, fingerprint."""
    if _ssl_dir is None:
        return _not_initialized()

    ca_path = _ssl_dir / "ca.crt"
    if not ca_path.exists():
        return _error("CA certificate not found", "CA_NOT_FOUND", 404)

    info = _parse_cert_full(ca_path)
    if info is None:
        return _error("Failed to parse CA certificate", "CERT_PARSE_ERROR")

    return JSONResponse({"status": "ok", **info})


# ---------------------------------------------------------------------------
# GET /api/tls/server — Server certificate details + SANs
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/tls/server")
async def api_tls_server():
    """Server certificate details including SANs."""
    if _ssl_dir is None:
        return _not_initialized()

    srv_path = _ssl_dir / "apex.crt"
    if not srv_path.exists():
        return _error("Server certificate not found", "SERVER_CERT_NOT_FOUND", 404)

    info = _parse_cert_full(srv_path)
    if info is None:
        return _error("Failed to parse server certificate", "CERT_PARSE_ERROR")

    return JSONResponse({"status": "ok", **info})


# ---------------------------------------------------------------------------
# GET /api/tls/clients — List all client certificates
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/tls/clients")
async def api_tls_clients_list():
    """List all client certificates found in the SSL directory."""
    if _ssl_dir is None:
        return _not_initialized()

    clients: list[dict[str, Any]] = []
    for crt_path in sorted(_ssl_dir.glob("*.crt")):
        name = crt_path.stem
        # Skip CA and server certs
        if name in ("ca", "apex"):
            continue
        info = _parse_cert_full(crt_path)
        entry: dict[str, Any] = {"cn": name}
        if info:
            entry["subject"] = info["subject"]
            entry["expires"] = info["expires"]
            entry["days_remaining"] = info["days_remaining"]
            entry["fingerprint"] = info["fingerprint"]
        else:
            entry["error"] = "Failed to parse certificate"
        # Check for companion files
        entry["has_key"] = (_ssl_dir / f"{name}.key").exists()
        entry["has_p12"] = (_ssl_dir / f"{name}.p12").exists()
        clients.append(entry)

    return JSONResponse({"status": "ok", "clients": clients, "count": len(clients)})


# ---------------------------------------------------------------------------
# POST /api/tls/clients — Generate a new client certificate
# ---------------------------------------------------------------------------

@dashboard_app.post("/api/tls/clients")
async def api_tls_clients_create(request: Request):
    """Generate a new client certificate signed by the CA.

    Body: {"cn": "device-name"}
    """
    if _ssl_dir is None:
        return _not_initialized()

    ca = _require_ca()
    if ca is None:
        return _error("CA certificate or key not found", "CA_NOT_FOUND", 404)
    ca_crt, ca_key = ca

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON in request body", "INVALID_JSON", status=400)

    cn = body.get("cn", "").strip() if isinstance(body, dict) else ""
    err = _validate_cn(cn)
    if err:
        return _error(err, "INVALID_CN", status=400)

    async with _cert_lock:
        # Check for existing cert with same CN
        if (_ssl_dir / f"{cn}.crt").exists():
            return _error(
                f"Client certificate '{cn}' already exists",
                "CN_EXISTS",
                status=409,
            )

        # Rate limit: max 10 certs per hour
        now = time.time()
        _cert_gen_times[:] = [t for t in _cert_gen_times if now - t < 3600]
        if len(_cert_gen_times) >= 10:
            return _error("Rate limit: max 10 certificates per hour", "RATE_LIMITED", 429)
        _cert_gen_times.append(now)

        p12_password = secrets.token_urlsafe(16)

        key_path = _ssl_dir / f"{cn}.key"
        csr_path = _ssl_dir / f"{cn}.csr"
        crt_path = _ssl_dir / f"{cn}.crt"
        p12_path = _ssl_dir / f"{cn}.p12"

        try:
            with _DecryptedCAKey(ca_key) as dca:
                steps = [
                    # 1. Generate private key
                    ["openssl", "genrsa", "-out", str(key_path), "2048"],
                    # 2. Generate CSR
                    ["openssl", "req", "-new",
                     "-key", str(key_path),
                     "-out", str(csr_path),
                     "-subj", f"/CN={cn}"],
                    # 3. Sign with CA
                    ["openssl", "x509", "-req",
                     "-in", str(csr_path),
                     "-CA", str(ca_crt),
                     "-CAkey", str(dca.path),
                     "-CAcreateserial",
                     "-out", str(crt_path),
                     "-days", "825",
                     "-sha256"],
                    # 4. Create .p12 bundle
                    ["openssl", "pkcs12", "-export",
                     "-out", str(p12_path),
                     "-inkey", str(key_path),
                     "-in", str(crt_path),
                     "-certfile", str(ca_crt),
                     "-passout", f"pass:{p12_password}"],
                ]

                for cmd in steps:
                    try:
                        result = subprocess.run(
                            cmd, capture_output=True, text=True, timeout=30,
                        )
                        if result.returncode != 0:
                            # Clean up partial artifacts
                            for f in (key_path, csr_path, crt_path, p12_path):
                                f.unlink(missing_ok=True)
                            _log.error(f"openssl failed during client cert gen: {result.stderr.strip()}")
                            return _error(
                                "Certificate operation failed",
                                "OPENSSL_ERROR",
                            )
                    except subprocess.TimeoutExpired:
                        for f in (key_path, csr_path, crt_path, p12_path):
                            f.unlink(missing_ok=True)
                        return _error("openssl command timed out", "OPENSSL_TIMEOUT")

                # Encrypt the new client key at rest
                _encrypt_new_key(key_path)
        except RuntimeError as exc:
            _log.error(f"CA key decryption failed: {exc}")
            return _error("CA key decryption failed", "DECRYPT_ERROR")

        # 5. Clean up CSR
        csr_path.unlink(missing_ok=True)

        # Lock down key file permissions
        _harden_ssl_dir(_ssl_dir)

        # Parse the new cert for expiry
        info = _parse_cert_full(crt_path)
        expires = info["expires"] if info else "unknown"

        return JSONResponse({
            "status": "ok",
            "cn": cn,
            "expires": expires,
            "p12_url": f"/admin/api/tls/clients/{cn}/p12",
            "p12_password": p12_password,
        })


# ---------------------------------------------------------------------------
# GET /api/tls/clients/{cn}/p12 — Download .p12 bundle
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/tls/clients/{cn}/p12")
async def api_tls_clients_download_p12(cn: str):
    """Download a client .p12 certificate bundle."""
    if _ssl_dir is None:
        return _not_initialized()

    err = _validate_cn(cn)
    if err:
        return _error(err, "INVALID_CN", status=400)

    p12_path = _ssl_dir / f"{cn}.p12"
    if not p12_path.exists():
        return _error(
            f"No .p12 bundle for '{cn}'",
            "P12_NOT_FOUND",
            status=404,
        )

    data = p12_path.read_bytes()
    return Response(
        content=data,
        media_type="application/x-pkcs12",
        headers={
            "Content-Disposition": f'attachment; filename="{cn}.p12"',
        },
    )


# ---------------------------------------------------------------------------
# GET /api/tls/clients/{cn}/qr — QR code or URL card for .p12
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/tls/clients/{cn}/qr")
async def api_tls_clients_qr(cn: str, request: Request):
    """Return a QR code as inline SVG for the .p12 download URL.

    Falls back to a plain URL card if the qrcode library is not installed.
    """
    if _ssl_dir is None:
        return _not_initialized()

    err = _validate_cn(cn)
    if err:
        return _error(err, "INVALID_CN", status=400)

    p12_path = _ssl_dir / f"{cn}.p12"
    if not p12_path.exists():
        return _error(
            f"No .p12 bundle for '{cn}'",
            "P12_NOT_FOUND",
            status=404,
        )

    # Build the full download URL from the request
    safe_cn = html.escape(cn)
    safe_base = html.escape(str(request.base_url).rstrip("/"))
    download_url = f"{str(request.base_url).rstrip('/')}/admin/api/tls/clients/{cn}/p12"
    safe_download_url = html.escape(download_url)

    # Try qrcode library for SVG generation
    try:
        import qrcode  # type: ignore
        import qrcode.image.svg  # type: ignore

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(download_url)
        qr.make(fit=True)

        factory = qrcode.image.svg.SvgPathImage
        img = qr.make_image(image_factory=factory)

        import io
        buf = io.BytesIO()
        img.save(buf)
        svg_str = buf.getvalue().decode("utf-8")

        page_html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>QR — {cn}</title>"
            "<style>body{{background:#111;color:#eee;font-family:system-ui;"
            "display:flex;flex-direction:column;align-items:center;padding:2em}}"
            "svg{{background:white;padding:1em;border-radius:8px;max-width:300px}}"
            "a{{color:#6cf;word-break:break-all}}</style></head><body>"
            f"<h2>Client cert: {safe_cn}</h2>"
            f"{svg_str}"
            f"<p style='margin-top:1em'>Or copy: <a href='{safe_download_url}'>"
            f"{safe_download_url}</a></p>"
            f"<p>Install password was shown at certificate generation time.</p>"
            "</body></html>"
        )
        return HTMLResponse(page_html)

    except ImportError:
        # Fallback: URL card without QR
        page_html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>Download — {safe_cn}</title>"
            "<style>body{background:#111;color:#eee;font-family:system-ui;"
            "display:flex;flex-direction:column;align-items:center;padding:2em}"
            ".card{background:#222;padding:2em;border-radius:12px;max-width:500px;"
            "text-align:center;border:1px solid #444}"
            "a{color:#6cf;font-size:1.1em;word-break:break-all}"
            "code{background:#333;padding:2px 8px;border-radius:4px}</style></head>"
            "<body><div class='card'>"
            f"<h2>Client cert: {safe_cn}</h2>"
            f"<p>Download URL:</p>"
            f"<p><a href='{safe_download_url}'>{safe_download_url}</a></p>"
            f"<p style='margin-top:1em'>Install password was shown at certificate generation time.</p>"
            "<p style='color:#888;font-size:0.85em;margin-top:1em'>"
            "QR code unavailable — install <code>qrcode</code> package for SVG QR.</p>"
            "</div></body></html>"
        )
        return HTMLResponse(page_html)


# ---------------------------------------------------------------------------
# DELETE /api/tls/clients/{cn} — Revoke/delete client cert
# ---------------------------------------------------------------------------

@dashboard_app.delete("/api/tls/clients/{cn}")
async def api_tls_clients_delete(cn: str):
    """Delete a client certificate and its key/p12 files."""
    if _ssl_dir is None:
        return _not_initialized()

    err = _validate_cn(cn)
    if err:
        return _error(err, "INVALID_CN", status=400)

    crt_path = _ssl_dir / f"{cn}.crt"
    if not crt_path.exists():
        return _error(
            f"Client certificate '{cn}' not found",
            "CLIENT_NOT_FOUND",
            status=404,
        )

    removed: list[str] = []
    for ext in (".crt", ".key", ".p12", ".csr"):
        f = _ssl_dir / f"{cn}{ext}"
        if f.exists():
            f.unlink()
            removed.append(f.name)

    return JSONResponse({
        "status": "ok",
        "cn": cn,
        "removed_files": removed,
    })


# ---------------------------------------------------------------------------
# POST /api/tls/server/renew — Renew server certificate using existing CA
# ---------------------------------------------------------------------------

@dashboard_app.post("/api/tls/server/renew")
async def api_tls_server_renew():
    """Regenerate the server certificate signed by the existing CA.

    Uses ext.cnf for SAN extensions. Returns restart_required=true.
    """
    if _ssl_dir is None:
        return _not_initialized()

    ca = _require_ca()
    if ca is None:
        return _error("CA certificate or key not found", "CA_NOT_FOUND", 404)
    ca_crt, ca_key = ca

    ext_cnf = _ssl_dir / "ext.cnf"
    if not ext_cnf.exists():
        return _error("ext.cnf not found — cannot determine SANs", "EXT_CNF_NOT_FOUND", 404)

    key_path = _ssl_dir / "apex.key"
    csr_path = _ssl_dir / "apex.csr"
    crt_path = _ssl_dir / "apex.crt"

    try:
        with _DecryptedCAKey(ca_key) as dca:
            steps = [
                # 1. Generate new server key
                ["openssl", "genrsa", "-out", str(key_path), "2048"],
                # 2. Generate CSR
                ["openssl", "req", "-new",
                 "-key", str(key_path),
                 "-out", str(csr_path),
                 "-subj", "/CN=apex"],
                # 3. Sign with CA using ext.cnf for SANs
                ["openssl", "x509", "-req",
                 "-in", str(csr_path),
                 "-CA", str(ca_crt),
                 "-CAkey", str(dca.path),
                 "-CAcreateserial",
                 "-out", str(crt_path),
                 "-days", "825",
                 "-sha256",
                 "-extfile", str(ext_cnf),
                 "-extensions", "v3_req"],
            ]

            for cmd in steps:
                try:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=30,
                    )
                    if result.returncode != 0:
                        _log.error(f"openssl failed during server cert renewal: {result.stderr.strip()}")
                        return _error(
                            "Certificate operation failed",
                            "OPENSSL_ERROR",
                        )
                except subprocess.TimeoutExpired:
                    return _error("openssl command timed out", "OPENSSL_TIMEOUT")

            # Encrypt the new server key at rest
            _encrypt_new_key(key_path)
    except RuntimeError as exc:
        _log.error(f"CA key decryption failed: {exc}")
        return _error("CA key decryption failed", "DECRYPT_ERROR")

    # Clean up CSR
    csr_path.unlink(missing_ok=True)

    # Lock down key file permissions
    _harden_ssl_dir(_ssl_dir)

    # Parse the renewed cert for expiry
    info = _parse_cert_full(crt_path)
    expires = info["expires"] if info else "unknown"

    return JSONResponse({
        "status": "ok",
        "restart_required": True,
        "expires": expires,
        "message": "Server certificate renewed. Restart the server to use the new cert.",
    })


# ---------------------------------------------------------------------------
# GET /api/tls/sans — Current SAN list from ext.cnf
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/tls/sans")
async def api_tls_sans():
    """Parse ext.cnf and return the current Subject Alternative Names."""
    if _ssl_dir is None:
        return _not_initialized()

    ext_cnf = _ssl_dir / "ext.cnf"
    if not ext_cnf.exists():
        return _error("ext.cnf not found", "EXT_CNF_NOT_FOUND", 404)

    sans = _parse_ext_cnf_sans(ext_cnf)

    return JSONResponse({
        "status": "ok",
        "sans": sans,
        "ext_cnf_path": str(ext_cnf),
    })


def _parse_ext_cnf_sans(ext_cnf: Path) -> list[str]:
    """Parse the [alt_names] section from ext.cnf into a list like
    ['IP:127.0.0.1', 'DNS:localhost']."""
    sans: list[str] = []
    in_alt = False
    for line in ext_cnf.read_text().splitlines():
        stripped = line.strip()
        if stripped == "[alt_names]":
            in_alt = True
            continue
        if in_alt:
            if stripped.startswith("[") and stripped.endswith("]"):
                break  # next section
            if "=" in stripped:
                # e.g. "IP.1 = 127.0.0.1" or "DNS.1 = localhost"
                key, _, val = stripped.partition("=")
                key = key.strip()
                val = val.strip()
                # Extract type from key: IP.1 -> IP, DNS.2 -> DNS
                type_part = key.split(".")[0].strip()
                sans.append(f"{type_part}:{val}")
    return sans


# ---------------------------------------------------------------------------
# PUT /api/tls/sans — Update SANs in ext.cnf
# ---------------------------------------------------------------------------

@dashboard_app.put("/api/tls/sans")
async def api_tls_sans_update(request: Request):
    """Update Subject Alternative Names in ext.cnf.

    Body: {"sans": ["IP:192.168.1.5", "DNS:myserver.local"]}
    Writes a new ext.cnf. Returns restart_required + renew_required.
    """
    if _ssl_dir is None:
        return _not_initialized()

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON in request body", "INVALID_JSON", status=400)

    if not isinstance(body, dict) or "sans" not in body:
        return _error(
            'Request body must contain "sans" array',
            "INVALID_BODY",
            status=400,
        )

    raw_sans = body["sans"]
    if not isinstance(raw_sans, list) or len(raw_sans) == 0:
        return _error(
            '"sans" must be a non-empty array',
            "INVALID_SANS",
            status=400,
        )

    # Validate each SAN entry — rejects newline injection and malformed values
    # (S-DA2: loose regex previously allowed newlines to inject OpenSSL config sections)
    for entry in raw_sans:
        err = _validate_san_entry(entry)
        if err:
            return _error(err, "INVALID_SAN_ENTRY", status=400)

    # Build the new ext.cnf
    alt_lines: list[str] = []
    ip_idx = 0
    dns_idx = 0
    for entry in raw_sans:
        san_type, _, san_val = entry.partition(":")
        if san_type == "IP":
            ip_idx += 1
            alt_lines.append(f"IP.{ip_idx} = {san_val}")
        elif san_type == "DNS":
            dns_idx += 1
            alt_lines.append(f"DNS.{dns_idx} = {san_val}")

    ext_cnf_content = (
        "[req]\n"
        "req_extensions = v3_req\n"
        "distinguished_name = req_dn\n"
        "\n"
        "[req_dn]\n"
        "CN = apex\n"
        "\n"
        "[v3_req]\n"
        "basicConstraints = CA:FALSE\n"
        "keyUsage = digitalSignature, keyEncipherment\n"
        "extendedKeyUsage = serverAuth\n"
        "subjectAltName = @alt_names\n"
        "\n"
        "[alt_names]\n"
    )
    ext_cnf_content += "\n".join(alt_lines) + "\n"

    ext_cnf = _ssl_dir / "ext.cnf"
    ext_cnf.write_text(ext_cnf_content)

    return JSONResponse({
        "status": "ok",
        "sans": raw_sans,
        "restart_required": True,
        "renew_required": True,
        "message": "SANs updated. Renew the server certificate then restart.",
    })


# ---------------------------------------------------------------------------
# POST /api/tls/ca/generate — Generate a new CA (first-run or re-key)
# ---------------------------------------------------------------------------

@dashboard_app.post("/api/tls/ca/generate")
async def api_tls_ca_generate(request: Request):
    """Generate a new Certificate Authority.

    Creates a self-signed CA cert + key in the ssl directory.
    If a CA already exists, requires {"force": true} to overwrite.
    After re-keying, all existing client/server certs become invalid.

    Body (optional): {"cn": "Apex CA", "days": 3650, "force": false}
    """
    if _ssl_dir is None:
        return _not_initialized()

    try:
        body = await request.json()
    except Exception:
        body = {}

    if not isinstance(body, dict):
        body = {}

    cn = body.get("cn", "Apex CA").strip() or "Apex CA"
    days = body.get("days", 3650)
    force = body.get("force", False)

    # S-DA1: validate CN the same way client certs do — rejects '/', '\',
    # and other characters that would inject extra subject fields into -subj.
    cn_err = _validate_cn(cn)
    if cn_err:
        return _error(cn_err, "INVALID_CN", status=400)

    if not isinstance(days, int) or days < 1 or days > 7300:
        return _error("days must be an integer between 1 and 7300", "INVALID_DAYS", 400)

    async with _cert_lock:
        ca_crt = _ssl_dir / "ca.crt"
        ca_key = _ssl_dir / "ca.key"

        if ca_crt.exists() and not force:
            return _error(
                "CA already exists. Pass {\"force\": true} to overwrite. "
                "WARNING: This invalidates ALL existing client and server certs.",
                "CA_EXISTS",
                status=409,
            )

        # Ensure ssl directory exists
        _ssl_dir.mkdir(parents=True, exist_ok=True)

        steps = [
            # 1. Generate CA private key
            ["openssl", "genrsa", "-out", str(ca_key), "4096"],
            # 2. Generate self-signed CA certificate
            ["openssl", "req", "-x509", "-new", "-nodes",
             "-key", str(ca_key),
             "-sha256",
             "-days", str(days),
             "-out", str(ca_crt),
             "-subj", f"/CN={cn}"],
        ]

        for cmd in steps:
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    # Clean up partial artifacts
                    ca_key.unlink(missing_ok=True)
                    ca_crt.unlink(missing_ok=True)
                    _log.error(f"openssl failed during CA generation: {result.stderr.strip()}")
                    return _error(
                        "Certificate operation failed",
                        "OPENSSL_ERROR",
                    )
            except subprocess.TimeoutExpired:
                ca_key.unlink(missing_ok=True)
                ca_crt.unlink(missing_ok=True)
                return _error("openssl command timed out", "OPENSSL_TIMEOUT")

        # Encrypt the new CA key at rest
        _encrypt_new_key(ca_key)

        # Lock down SSL directory and key file permissions
        _harden_ssl_dir(_ssl_dir)

        # Parse the new CA cert for details
        info = _parse_cert_full(ca_crt)

        return JSONResponse({
            "status": "ok",
            "cn": cn,
            "days": days,
            "expires": info["expires"] if info else "unknown",
            "fingerprint": info["fingerprint"] if info else "unknown",
            "restart_required": True,
            "message": "CA generated. Generate a server cert and client certs, then restart.",
        })


# ===========================================================================
# Phase 3 — Models, Credentials, Alerts
# ===========================================================================

ENV_PATH = Path(os.environ.get("APEX_ENV_FILE", str(Path.home() / ".apex" / ".env")))

_PROVIDER_KEY_MAP: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "xai_management": "XAI_MANAGEMENT_KEY",
    "xai_team_id": "XAI_TEAM_ID",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
    "google": "GOOGLE_API_KEY",
    "telegram_bot": "TELEGRAM_BOT_TOKEN",
    "telegram_chat": "TELEGRAM_CHAT_ID",
    "alert_token": "APEX_ALERT_TOKEN",
}

_CODEX_MODEL_OPTIONS: list[str] = [
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.3-codex",
    "gpt-5.2",
    "gpt-5.1-codex-max",
    "o4-mini",
]


def _read_env_file() -> str:
    """Read the .env file, returning empty string if missing."""
    try:
        return ENV_PATH.read_text()
    except FileNotFoundError:
        return ""


def _update_env_var(key: str, value: str) -> None:
    """Set key=value in the .env file using atomic write.

    Reads existing content, replaces the line if found, appends if not.
    Writes via temp file + rename for atomicity.
    """
    if any(c in value for c in '\n\r\0'):
        raise ValueError("Value contains invalid characters (newline or null)")

    import tempfile as _tf

    content = _read_env_file()
    lines = content.splitlines()
    found = False
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"export {key}="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")

    # Ensure trailing newline
    final = "\n".join(new_lines)
    if not final.endswith("\n"):
        final += "\n"

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = _tf.mkstemp(dir=str(ENV_PATH.parent), suffix=".env.tmp")
    try:
        os.write(fd, final.encode())
        os.close(fd)
        os.rename(tmp_path, str(ENV_PATH))
    except Exception:
        os.close(fd) if not os.get_inheritable(fd) else None  # noqa: best-effort
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _env_has_key(key: str) -> bool:
    """Check whether key is set in environment or .env file (non-empty)."""
    if os.environ.get(key, ""):
        return True
    content = _read_env_file()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            val = stripped[len(key) + 1:]
            return bool(val.strip())
        if stripped.startswith(f"export {key}="):
            val = stripped[len(f"export {key}="):]
            return bool(val.strip())
    return False


# ---------------------------------------------------------------------------
# PUT /api/config/models/default — Set default model
# ---------------------------------------------------------------------------

@dashboard_app.put("/api/config/models/default")
async def api_config_models_default(request: Request):
    """Set the default model. Updates config and the module-level MODEL var."""
    if _config is None:
        return _not_initialized()

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON in request body", "INVALID_JSON", status=400)

    model = body.get("model", "") if isinstance(body, dict) else ""
    if not model or not isinstance(model, str):
        return _error("'model' field is required", "MISSING_MODEL", status=400)
    if model not in get_available_model_ids():
        return _error("Unsupported model", "UNSUPPORTED_MODEL", status=422)

    try:
        new_values, restart_required = _config.update_section(
            "models", {"default_model": model}
        )
    except ValueError as e:
        _log.warning(f"Config validation error: {e}")
        return _error("Invalid configuration value", "VALIDATION_ERROR", status=422)
    except Exception as e:
        _log.error(f"Config update failed: {e}")
        return _error("Configuration update failed", "CONFIG_WRITE_ERROR")

    # Update module-level MODEL var in the main server module
    try:
        import apex as _lc
        _lc.MODEL = model
    except Exception:
        pass

    return JSONResponse({
        "status": "ok",
        "model": model,
        "restart_required": restart_required,
    })


# ---------------------------------------------------------------------------
# PUT /api/config/models/permission — Set SDK permission mode
# ---------------------------------------------------------------------------

@dashboard_app.put("/api/config/models/permission")
async def api_config_models_permission(request: Request):
    """Set the Claude SDK permission mode."""
    if _config is None:
        return _not_initialized()

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON in request body", "INVALID_JSON", status=400)

    mode = body.get("mode", "") if isinstance(body, dict) else ""
    if not mode or not isinstance(mode, str):
        return _error("'mode' field is required", "MISSING_MODE", status=400)

    try:
        new_values, restart_required = _config.update_section(
            "models", {"permission_mode": mode}
        )
    except ValueError as e:
        _log.warning(f"Config validation error: {e}")
        return _error("Invalid configuration value", "VALIDATION_ERROR", status=422)
    except Exception as e:
        _log.error(f"Config update failed: {e}")
        return _error("Configuration update failed", "CONFIG_WRITE_ERROR")

    return JSONResponse({
        "status": "ok",
        "permission_mode": mode,
        "restart_required": restart_required,
    })


# ---------------------------------------------------------------------------
# GET /api/models/claude — Claude API status
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/models/claude")
async def api_models_claude():
    """Check Claude API key status: environment variable and macOS keychain."""
    env_set = bool(os.environ.get("ANTHROPIC_API_KEY", ""))

    # Check macOS keychain
    keychain_set = False
    keychain_error: str | None = None
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "anthropic-api-key", "-w"],
            capture_output=True, text=True, timeout=5,
        )
        keychain_set = result.returncode == 0 and bool(result.stdout.strip())
    except subprocess.TimeoutExpired:
        keychain_error = "keychain lookup timed out"
    except FileNotFoundError:
        keychain_error = "security command not found (not macOS?)"
    except Exception as e:
        _log.debug(f"Keychain error: {e}")
        keychain_error = "keychain lookup failed"

    # Also check if Claude Agent SDK is available (used by Apex for Claude access)
    sdk_available = False
    try:
        import claude_agent_sdk  # noqa: F401
        sdk_available = True
    except ImportError:
        pass

    status = "configured" if (env_set or keychain_set or sdk_available) else "not_configured"

    resp: dict[str, Any] = {
        "status": status,
        "env_var_set": env_set,
        "keychain_set": keychain_set,
        "sdk_available": sdk_available,
        "api_key_configured": env_set or keychain_set or sdk_available,
    }
    if keychain_error:
        resp["keychain_error"] = keychain_error

    return JSONResponse(resp)


# ---------------------------------------------------------------------------
# GET /api/models/ollama — Ollama detailed status
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/models/ollama")
async def api_models_ollama():
    """Ollama status: reachability, model list with sizes, running models."""
    if _config is None:
        return _not_initialized()

    ollama_url = (_config.get("models", "ollama_url")
                  or "http://localhost:11434")

    if not _validate_ollama_url(ollama_url):
        return JSONResponse({
            "status": "invalid_url",
            "url": ollama_url,
            "detail": "URL must be http/https to localhost or known local hosts",
            "models": [],
            "model_count": 0,
            "running": [],
        })

    base = ollama_url.rstrip("/")

    # Fetch model list from /api/tags
    models_list: list[dict[str, Any]] = []
    tags_error: str | None = None
    try:
        req = urllib.request.Request(f"{base}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            for m in data.get("models", []):
                models_list.append({
                    "name": m.get("name", "?"),
                    "size": m.get("size", 0),
                    "size_human": _format_bytes(m.get("size", 0)),
                    "modified_at": m.get("modified_at", ""),
                    "digest": m.get("digest", "")[:12],
                })
    except urllib.error.URLError as e:
        _log.debug(f"Ollama tags failed: {e}")
        tags_error = "Connection failed"
    except Exception as e:
        _log.debug(f"Ollama tags error: {e}")
        tags_error = "Connection failed"

    # Fetch running models from /api/ps
    running: list[dict[str, Any]] = []
    ps_error: str | None = None
    try:
        req = urllib.request.Request(f"{base}/api/ps", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            for m in data.get("models", []):
                running.append({
                    "name": m.get("name", "?"),
                    "size": m.get("size", 0),
                    "size_human": _format_bytes(m.get("size", 0)),
                    "expires_at": m.get("expires_at", ""),
                })
    except urllib.error.URLError as e:
        _log.debug(f"Ollama ps failed: {e}")
        ps_error = "Connection failed"
    except Exception as e:
        _log.debug(f"Ollama ps error: {e}")
        ps_error = "Connection failed"

    reachable = tags_error is None
    resp: dict[str, Any] = {
        "status": "reachable" if reachable else "unreachable",
        "url": ollama_url,
        "models": models_list,
        "model_count": len(models_list),
        "running": running,
    }
    if tags_error:
        resp["tags_error"] = tags_error
    if ps_error:
        resp["ps_error"] = ps_error

    return JSONResponse(resp)


# ---------------------------------------------------------------------------
# GET /api/models/grok — Grok API status
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/models/grok")
async def api_models_grok():
    """Check Grok API key status (XAI_API_KEY presence)."""
    env_set = bool(os.environ.get("XAI_API_KEY", ""))
    dotenv_set = _env_has_key("XAI_API_KEY") if not env_set else False

    status = "configured" if (env_set or dotenv_set) else "not_configured"

    return JSONResponse({
        "status": status,
        "env_var_set": env_set,
        "dotenv_set": dotenv_set,
        "api_key_configured": env_set or dotenv_set,
    })


# ---------------------------------------------------------------------------
# GET /api/models/codex — Codex (OpenAI) API status
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/models/codex")
async def api_models_codex():
    """Check Codex (OpenAI) API key status and CLI availability."""
    import subprocess
    env_set = bool(os.environ.get("OPENAI_API_KEY", ""))
    dotenv_set = _env_has_key("OPENAI_API_KEY") if not env_set else False

    cli_available = False
    cli_version = None
    try:
        result = subprocess.run(
            [shutil.which("codex") or "codex", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            cli_available = True
            cli_version = result.stdout.strip()
    except Exception:
        pass

    status = "configured" if ((env_set or dotenv_set) and cli_available) else "not_configured"

    return JSONResponse({
        "status": status,
        "env_var_set": env_set,
        "dotenv_set": dotenv_set,
        "api_key_configured": env_set or dotenv_set,
        "cli_available": cli_available,
        "cli_version": cli_version,
        "default_model": _CODEX_MODEL_OPTIONS[0],
        "models": _CODEX_MODEL_OPTIONS,
    })


# ---------------------------------------------------------------------------
# GET /api/credentials — Which keys are configured (booleans only)
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/credentials")
async def api_credentials():
    """Return boolean flags for which API keys/tokens are configured."""
    return JSONResponse({
        "status": "ok",
        "credentials": {
            "anthropic": _env_has_key("ANTHROPIC_API_KEY"),
            "xai": _env_has_key("XAI_API_KEY"),
            "xai_management": _env_has_key("XAI_MANAGEMENT_KEY"),
            "xai_team_id": _env_has_key("XAI_TEAM_ID"),
            "openai": _env_has_key("OPENAI_API_KEY"),
            "deepseek": _env_has_key("DEEPSEEK_API_KEY"),
            "zhipu": _env_has_key("ZHIPU_API_KEY"),
            "google": _env_has_key("GOOGLE_API_KEY"),
            "telegram_bot": _env_has_key("TELEGRAM_BOT_TOKEN"),
            "telegram_chat": _env_has_key("TELEGRAM_CHAT_ID"),
            "alert_token": _env_has_key("APEX_ALERT_TOKEN"),
        },
    })


# ---------------------------------------------------------------------------
# PUT /api/credentials/{provider} — Set API key in .env
# ---------------------------------------------------------------------------

_CREDENTIAL_KEY_PATTERNS: dict[str, tuple[str, int, int]] = {
    # provider: (prefix_or_empty, min_length, max_length)
    "anthropic": ("sk-ant-", 20, 200),
    "xai": ("xai-", 20, 200),
    "xai_management": ("xai-token-", 20, 200),
    "xai_team_id": ("", 20, 60),  # UUID format
    "openai": ("sk-", 20, 200),
    "deepseek": ("sk-", 20, 200),
    "zhipu": ("", 20, 200),
    "telegram_bot": ("", 30, 100),   # format: 123456:ABC-DEF...
    "telegram_chat": ("", 5, 20),    # numeric chat ID
    "google": ("AIza", 20, 200),
}
_credential_rate: dict[str, float] = {}  # provider -> last update timestamp
_CREDENTIAL_RATE_LIMIT = 5.0  # seconds between updates per provider


@dashboard_app.put("/api/credentials/{provider}")
async def api_credentials_update(provider: str, request: Request):
    """Set an API key/token in the .env file (atomic write).

    Providers: anthropic, xai, telegram_bot, telegram_chat.
    Body: {"key": "sk-..."}
    Security: mTLS required, rate-limited, format-validated, audit-logged.
    """
    import time as _time

    if provider not in _PROVIDER_KEY_MAP:
        return _error(
            f"Unknown provider: '{provider}'. "
            f"Valid: {', '.join(sorted(_PROVIDER_KEY_MAP))}",
            "UNKNOWN_PROVIDER",
            status=400,
        )

    # Rate limit: one update per provider every N seconds
    now = _time.time()
    last = _credential_rate.get(provider, 0)
    if now - last < _CREDENTIAL_RATE_LIMIT:
        _log.warning(f"credential update rate-limited: provider={provider}")
        return _error("Too many requests. Try again shortly.", "RATE_LIMITED", status=429)
    _credential_rate[provider] = now

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON in request body", "INVALID_JSON", status=400)

    key_value = body.get("key", "") if isinstance(body, dict) else ""
    if not key_value or not isinstance(key_value, str):
        return _error("'key' field is required", "MISSING_KEY", status=400)

    # Strip whitespace (common paste artifact)
    key_value = key_value.strip()

    # Format validation
    pattern = _CREDENTIAL_KEY_PATTERNS.get(provider)
    if pattern:
        prefix, min_len, max_len = pattern
        if prefix and not key_value.startswith(prefix):
            return _error(
                f"Invalid key format. Expected prefix: {prefix}...",
                "INVALID_FORMAT",
                status=400,
            )
        if len(key_value) < min_len:
            return _error(
                f"Key too short (minimum {min_len} characters)",
                "INVALID_FORMAT",
                status=400,
            )
        if len(key_value) > max_len:
            return _error(
                f"Key too long (maximum {max_len} characters)",
                "INVALID_FORMAT",
                status=400,
            )

    # Block control characters
    if any(ord(c) < 32 for c in key_value):
        return _error("Key contains invalid control characters", "INVALID_FORMAT", status=400)

    env_var_name = _PROVIDER_KEY_MAP[provider]

    try:
        _update_env_var(env_var_name, key_value)
    except Exception as e:
        _log.error(f"Failed to update .env: {e}")
        return _error("Failed to update credentials file", "ENV_WRITE_ERROR")

    # Also update the current process environment
    os.environ[env_var_name] = key_value

    # Audit log — never log the key itself
    masked = key_value[:8] + "..." + key_value[-4:] if len(key_value) > 16 else "***"
    remote = request.client.host if request.client else "unknown"
    _log.info(f"AUDIT: credential updated provider={provider} masked={masked} remote={remote}")

    return JSONResponse({
        "status": "ok",
        "provider": provider,
        "env_var": env_var_name,
        "message": f"{env_var_name} updated successfully",
    })


# ---------------------------------------------------------------------------
# POST /api/credentials/alert-token/rotate — Generate new alert token
# ---------------------------------------------------------------------------

@dashboard_app.post("/api/credentials/alert-token/rotate")
async def api_credentials_alert_token_rotate():
    """Generate a new random alert token (32 bytes, base64url).

    Updates APEX_ALERT_TOKEN in .env and the running config.
    Returns the new token (only time it is exposed).
    """
    import secrets
    import base64

    token_bytes = secrets.token_bytes(32)
    new_token = base64.urlsafe_b64encode(token_bytes).decode().rstrip("=")

    try:
        _update_env_var("APEX_ALERT_TOKEN", new_token)
    except Exception as e:
        _log.error(f"Failed to update .env: {e}")
        return _error("Failed to update credentials file", "ENV_WRITE_ERROR")

    _set_live_alert_token(new_token)

    return JSONResponse({
        "status": "ok",
        "alert_token": new_token,
        "message": "New alert token generated. Update any clients using the old token.",
    })


# ---------------------------------------------------------------------------
# GET /api/alerts/config — Current alert configuration
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/alerts/config")
async def api_alerts_config():
    """Alert configuration: telegram status, alert token, DB categories."""
    telegram_configured = (
        _env_has_key("TELEGRAM_BOT_TOKEN") and _env_has_key("TELEGRAM_CHAT_ID")
    )
    alert_token_set = _env_has_key("APEX_ALERT_TOKEN")

    # Fetch distinct alert categories from DB
    categories: list[str] = []
    if _db_path and _db_path.exists():
        try:
            conn = sqlite3.connect(str(_db_path), check_same_thread=False)
            rows = conn.execute(
                "SELECT DISTINCT category FROM alerts WHERE category IS NOT NULL "
                "ORDER BY category"
            ).fetchall()
            categories = [r[0] for r in rows]
            conn.close()
        except sqlite3.Error:
            pass

    return JSONResponse({
        "status": "ok",
        "telegram_configured": telegram_configured,
        "alert_token_set": alert_token_set,
        "categories": categories,
    })


# ---------------------------------------------------------------------------
# PUT /api/alerts/config/telegram — Update telegram config in .env
# ---------------------------------------------------------------------------

@dashboard_app.put("/api/alerts/config/telegram")
async def api_alerts_config_telegram(request: Request):
    """Update TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.

    Body: {"bot_token": "123456:ABC...", "chat_id": "-100..."}
    """
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON in request body", "INVALID_JSON", status=400)

    if not isinstance(body, dict):
        return _error("Request body must be a JSON object", "INVALID_BODY", status=400)

    bot_token = body.get("bot_token", "")
    chat_id = body.get("chat_id", "")

    if not bot_token or not isinstance(bot_token, str):
        return _error("'bot_token' field is required", "MISSING_BOT_TOKEN", status=400)
    if not chat_id or not isinstance(chat_id, str):
        return _error("'chat_id' field is required", "MISSING_CHAT_ID", status=400)

    try:
        _update_env_var("TELEGRAM_BOT_TOKEN", bot_token)
        _update_env_var("TELEGRAM_CHAT_ID", chat_id)
    except Exception as e:
        _log.error(f"Failed to update .env: {e}")
        return _error("Failed to update credentials file", "ENV_WRITE_ERROR")

    os.environ["TELEGRAM_BOT_TOKEN"] = bot_token
    os.environ["TELEGRAM_CHAT_ID"] = chat_id

    return JSONResponse({
        "status": "ok",
        "message": "Telegram bot token and chat ID updated in .env",
    })


# ---------------------------------------------------------------------------
# POST /api/alerts/test — Fire a test alert through the full pipeline
# ---------------------------------------------------------------------------

@dashboard_app.post("/api/alerts/test")
async def api_alerts_test():
    """Fire a test alert through Apex's real alert pipeline plus Telegram."""
    results: dict[str, Any] = {}
    now_iso = datetime.now(timezone.utc).isoformat()
    title = "Dashboard Test Alert"
    body = f"Dashboard test alert fired at {now_iso}"

    try:
        import apex as _lc

        alert = _lc._create_alert(
            source="dashboard",
            severity="info",
            title=title,
            body=body,
            metadata={"kind": "dashboard_test", "fired_at": now_iso},
        )
        await _lc._broadcast_alert(alert)

        for evt in getattr(_lc, "_alert_waiters", []):
            evt.set()

        push_fn = getattr(_lc, "_push_to_all_devices", None)
        if callable(push_fn):
            asyncio.create_task(push_fn(
                title="[INFO] Dashboard Test Alert",
                body=body[:200],
                extra={"alert_id": alert["id"], "source": "dashboard", "chat_id": ""},
            ))

        log_fn = getattr(_lc, "log", None)
        if callable(log_fn):
            log_fn(f"dashboard test alert: id={alert['id']} title={title}")

        results["apex"] = {
            "status": "ok",
            "detail": "Inserted and broadcast via Apex alert pipeline",
            "alert_id": alert["id"],
        }
    except Exception as e:
        _log.error(f"Test alert Apex pipeline error: {e}")
        results["apex"] = {"status": "error", "detail": "Apex alert pipeline failed"}

    # 2. Send via Telegram
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        # Try reading from .env if not in environment
        content = _read_env_file()
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("TELEGRAM_BOT_TOKEN=") and not bot_token:
                bot_token = stripped.split("=", 1)[1].strip()
            elif stripped.startswith("TELEGRAM_CHAT_ID=") and not chat_id:
                chat_id = stripped.split("=", 1)[1].strip()

    if not bot_token or not chat_id:
        results["telegram"] = {
            "status": "not_configured",
            "detail": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set",
        }
    else:
        try:
            tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = json.dumps({
                "chat_id": chat_id,
                "text": (
                    "🔔 Apex Dashboard Test Alert\n\n"
                    "This is a test alert from the Apex Dashboard.\n"
                    f"Time: {now_iso}"
                ),
                "parse_mode": "HTML",
            }).encode()
            req = urllib.request.Request(
                tg_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                tg_resp = json.loads(resp.read().decode())
                if tg_resp.get("ok"):
                    results["telegram"] = {
                        "status": "ok",
                        "detail": "Test message sent",
                        "message_id": tg_resp.get("result", {}).get("message_id"),
                    }
                else:
                    results["telegram"] = {
                        "status": "error",
                        "detail": tg_resp.get("description", "Unknown error"),
                    }
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode())
                detail = err_body.get("description", "Telegram API error")
            except Exception:
                detail = "Telegram API error"
            results["telegram"] = {"status": "error", "detail": detail}
        except urllib.error.URLError as e:
            _log.debug(f"Telegram connection error: {e}")
            results["telegram"] = {
                "status": "error",
                "detail": "Connection to Telegram failed",
            }
        except Exception as e:
            _log.error(f"Telegram test error: {e}")
            results["telegram"] = {"status": "error", "detail": "Telegram request failed"}

    all_ok = all(
        r.get("status") == "ok"
        for r in results.values()
        if r.get("status") != "not_configured"
    )

    return JSONResponse({
        "status": "ok" if all_ok else "partial",
        "results": results,
        "fired_at": now_iso,
    })


# ===========================================================================
# Phase 4 — Workspace, Skills, Guardrails, Sessions
# ===========================================================================

# ---------------------------------------------------------------------------
# GET /api/workspace — Workspace summary
# ---------------------------------------------------------------------------

def _find_project_md() -> Path | None:
    """Search all workspace paths for APEX.md or CLAUDE.md (first match wins)."""
    for p in _workspace_paths_list():
        root = Path(p)
        apex_md = root / "APEX.md"
        if apex_md.exists():
            return apex_md
        claude_md = root / "CLAUDE.md"
        if claude_md.exists():
            return claude_md
    return None


@dashboard_app.get("/api/workspace")
async def api_workspace():
    """Workspace overview: path, project md exists, memory count, skills count."""
    workspace = _workspace_root()

    # Scan all workspace paths for project md, memory, and skills
    project_md = _find_project_md()
    _paths_debug = _workspace_paths_list()
    print(f"[dashboard] api_workspace: paths={_paths_debug} project_md={project_md}", flush=True)

    memory_count = 0
    skills_count = 0
    for p in _workspace_paths_list():
        root = Path(p)
        mem_dir = root / "memory"
        if mem_dir.is_dir():
            memory_count += len(list(mem_dir.glob("*.md")))
    skills_count = len(env.iter_workspace_skill_files(_workspace_paths_list()))

    return JSONResponse({
        "workspace": str(workspace),
        "workspace_paths": _workspace_paths_list(),
        "project_md_exists": project_md is not None and project_md.exists(),
        "project_md_name": project_md.name if project_md else "APEX.md",
        "memory_file_count": memory_count,
        "skills_count": skills_count,
    })


# ---------------------------------------------------------------------------
# GET /api/workspace/project-md — Read APEX.md (or CLAUDE.md fallback)
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/workspace/project-md")
async def api_workspace_project_md_get():
    """Return the contents of APEX.md (or CLAUDE.md fallback), scanning all workspace paths."""
    project_md = _find_project_md()
    if not project_md:
        return _error("Project instructions file not found (tried APEX.md and CLAUDE.md in all workspace paths)", "NOT_FOUND", status=404)
    try:
        content = project_md.read_text(encoding="utf-8")
    except Exception as e:
        _log.error(f"Failed to read {project_md.name}: {e}")
        return _error(f"Failed to read {project_md.name}", "READ_ERROR")
    return JSONResponse({
        "content": content,
        "filename": project_md.name,
        "size_bytes": project_md.stat().st_size,
    })


# ---------------------------------------------------------------------------
# PUT /api/workspace/project-md — Update APEX.md (backup first)
# ---------------------------------------------------------------------------

@dashboard_app.put("/api/workspace/project-md")
async def api_workspace_project_md_put(request: Request):
    """Write APEX.md (or CLAUDE.md fallback) after backing up. Scans all workspace paths."""
    body = await request.json()
    content = body.get("content")
    if content is None:
        return _error("Missing 'content' field", "BAD_REQUEST", status=400)

    # Find existing file across all workspace paths, or create in primary root
    project_md = _find_project_md()
    if not project_md:
        # No existing file — create APEX.md in the primary workspace root
        project_md = _workspace_root() / "APEX.md"
    bak = project_md.parent / f"{project_md.name}.bak"

    try:
        if project_md.exists():
            shutil.copy2(str(project_md), str(bak))
        project_md.write_text(content, encoding="utf-8")
    except Exception as e:
        _log.error(f"Failed to write {project_md.name}: {e}")
        return _error(f"Failed to write {project_md.name}", "WRITE_ERROR")

    return JSONResponse({
        "status": "ok",
        "message": f"{project_md.name} updated (backup saved to {bak.name})",
        "size_bytes": project_md.stat().st_size,
    })


# ---------------------------------------------------------------------------
# GET /api/workspace/memory — List memory files
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/workspace/memory")
async def api_workspace_memory():
    """List all memory/*.md files with name, size, and modified time."""
    files = []
    seen_names: set[str] = set()
    for root in env.get_runtime_workspace_paths_list():
        memory_dir = Path(root) / "memory"
        if not memory_dir.is_dir():
            continue
        for p in sorted(memory_dir.glob("*.md")):
            if p.name in seen_names:
                continue
            seen_names.add(p.name)
            st = p.stat()
            files.append({
                "name": p.name,
                "size_bytes": st.st_size,
                "modified": datetime.fromtimestamp(
                    st.st_mtime, tz=timezone.utc
                ).isoformat(),
                "root": str(root),
            })

    return JSONResponse({"files": files, "count": len(files)})


# ---------------------------------------------------------------------------
# GET /api/workspace/memory/{name} — Read a memory file
# ---------------------------------------------------------------------------

_MEMORY_NAME_RE = re.compile(r"^[\w\-]+\.md$")


@dashboard_app.get("/api/workspace/memory/{name}")
async def api_workspace_memory_read(name: str):
    """Read a single memory file's content."""
    if not _MEMORY_NAME_RE.match(name):
        return _error("Invalid memory file name", "INVALID_NAME", 400)

    # Search all workspace roots for the memory file
    path: Path | None = None
    memory_dir: Path | None = None
    for root in env.get_runtime_workspace_paths_list():
        candidate_dir = Path(root) / "memory"
        candidate = candidate_dir / name
        if candidate.exists():
            path = candidate
            memory_dir = candidate_dir
            break

    if path is None or memory_dir is None:
        return _error(f"Memory file '{name}' not found", "NOT_FOUND", 404)

    # Prevent path traversal
    try:
        path.resolve().relative_to(memory_dir.resolve())
    except ValueError:
        return _error("Invalid memory file path", "PATH_TRAVERSAL", 400)

    try:
        content = path.read_text(encoding="utf-8")
        st = path.stat()
        return JSONResponse({
            "status": "ok",
            "name": name,
            "content": content,
            "size_bytes": st.st_size,
            "modified": datetime.fromtimestamp(
                st.st_mtime, tz=timezone.utc
            ).isoformat(),
        })
    except Exception as e:
        _log.error(f"Memory file read error: {e}")
        return _error("Failed to read memory file", "READ_ERROR")


# ---------------------------------------------------------------------------
# PUT /api/workspace/memory/{name} — Update a memory file (with backup)
# ---------------------------------------------------------------------------

@dashboard_app.put("/api/workspace/memory/{name}")
async def api_workspace_memory_write(name: str, request: Request):
    """Write a memory file, backing up the original first."""
    if not _MEMORY_NAME_RE.match(name):
        return _error("Invalid memory file name", "INVALID_NAME", 400)

    memory_dir = _workspace_root() / "memory"
    path = memory_dir / name
    try:
        path.resolve().relative_to(memory_dir.resolve())
    except ValueError:
        return _error("Invalid memory file path", "PATH_TRAVERSAL", 400)

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON", "INVALID_JSON", 400)

    content = body.get("content")
    if content is None:
        return _error("Missing 'content' field", "BAD_REQUEST", 400)

    # Backup existing file
    if path.exists():
        bak = memory_dir / f"{name}.bak"
        try:
            shutil.copy2(str(path), str(bak))
        except Exception:
            pass  # best-effort backup

    # Atomic write
    memory_dir.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=str(memory_dir), suffix=".tmp")
        try:
            os.write(fd, content.encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, str(path))
    except Exception as e:
        _log.error(f"Memory file write error: {e}")
        return _error("Failed to write memory file", "WRITE_ERROR")

    st = path.stat()
    return JSONResponse({
        "status": "ok",
        "name": name,
        "size_bytes": st.st_size,
        "modified": datetime.fromtimestamp(
            st.st_mtime, tz=timezone.utc
        ).isoformat(),
        "message": f"Memory file '{name}' saved.",
    })


# ---------------------------------------------------------------------------
# GET /api/skills — List installed skills
# ---------------------------------------------------------------------------

def _parse_skill_frontmatter(skill_path: Path) -> dict[str, str]:
    """Parse YAML frontmatter from a SKILL.md file.

    Expects the file to start with '---' and contain a second '---' closing
    the frontmatter block. Returns {name, description} from the YAML.
    """
    try:
        text = skill_path.read_text(encoding="utf-8")
    except Exception:
        return {"name": skill_path.parent.name, "description": ""}

    if not text.startswith("---"):
        return {"name": skill_path.parent.name, "description": ""}

    end = text.find("---", 3)
    if end == -1:
        return {"name": skill_path.parent.name, "description": ""}

    try:
        import yaml
        fm = yaml.safe_load(text[3:end])
        if not isinstance(fm, dict):
            fm = {}
    except Exception:
        fm = {}

    return {
        "name": fm.get("name", skill_path.parent.name),
        "description": fm.get("description", ""),
    }


@dashboard_app.get("/api/skills")
async def api_skills():
    """List installed skills by scanning skills/*/SKILL.md across all workspace roots."""
    # Load disabled list
    skills_config_path = _state_dir / "skills_config.json" if _state_dir else None
    disabled: list[str] = []
    if skills_config_path and skills_config_path.exists():
        try:
            disabled = json.loads(
                skills_config_path.read_text(encoding="utf-8")
            ).get("disabled", [])
        except Exception:
            pass

    skills = []
    seen_dirs: set[str] = set()
    for skill_md in env.iter_workspace_skill_files():
        dir_name = skill_md.parent.name
        if dir_name in seen_dirs:
            continue
        seen_dirs.add(dir_name)
        info = _parse_skill_frontmatter(skill_md)
        skills.append({
            "dir": dir_name,
            "name": info["name"],
            "description": info["description"],
            "enabled": dir_name not in disabled,
        })

    return JSONResponse({"skills": skills, "count": len(skills)})


# ---------------------------------------------------------------------------
# PUT /api/skills/{name}/enabled — Enable/disable a skill
# ---------------------------------------------------------------------------

@dashboard_app.put("/api/skills/{name}/enabled")
async def api_skills_enabled(name: str, request: Request):
    """Enable or disable a skill by updating state/skills_config.json."""
    if _state_dir is None:
        return _not_initialized()

    body = await request.json()
    enabled = body.get("enabled")
    if enabled is None:
        return _error("Missing 'enabled' field", "BAD_REQUEST", status=400)

    skills_config_path = _state_dir / "skills_config.json"

    # Load existing config
    config: dict[str, Any] = {}
    if skills_config_path.exists():
        try:
            config = json.loads(
                skills_config_path.read_text(encoding="utf-8")
            )
        except Exception:
            config = {}

    disabled: list[str] = config.get("disabled", [])

    if enabled and name in disabled:
        disabled.remove(name)
    elif not enabled and name not in disabled:
        disabled.append(name)

    config["disabled"] = disabled
    skills_config_path.write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )

    return JSONResponse({
        "status": "ok",
        "skill": name,
        "enabled": bool(enabled),
    })


# ---------------------------------------------------------------------------
# GET /api/guardrails/whitelist — Read guardrail whitelist
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/guardrails/whitelist")
async def api_guardrails_whitelist():
    """Return the guardrail whitelist entries with expiry info."""
    if _state_dir is None:
        return _not_initialized()

    wl_path = _state_dir / "guardrail_whitelist.json"
    if not wl_path.exists():
        return JSONResponse({"entries": [], "count": 0})

    try:
        entries = json.loads(wl_path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            entries = []
    except Exception as e:
        _log.error(f"Failed to read whitelist: {e}")
        return _error("Failed to read whitelist", "READ_ERROR")

    # Annotate each entry with whether it's expired
    now = datetime.now(timezone.utc).isoformat()
    for i, entry in enumerate(entries):
        entry["_index"] = i
        expires = entry.get("expires", "")
        entry["_expired"] = bool(expires and expires < now)

    return JSONResponse({"entries": entries, "count": len(entries)})


# ---------------------------------------------------------------------------
# DELETE /api/guardrails/whitelist/{id} — Remove entry by index
# ---------------------------------------------------------------------------

@dashboard_app.delete("/api/guardrails/whitelist/{entry_id}")
async def api_guardrails_whitelist_delete(entry_id: int):
    """Remove a whitelist entry by its array index."""
    if _state_dir is None:
        return _not_initialized()

    wl_path = _state_dir / "guardrail_whitelist.json"
    if not wl_path.exists():
        return _error("Whitelist file not found", "NOT_FOUND", status=404)

    try:
        entries = json.loads(wl_path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            return _error("Whitelist is not an array", "BAD_FORMAT", status=500)
    except Exception as e:
        _log.error(f"Failed to read whitelist: {e}")
        return _error("Failed to read whitelist", "READ_ERROR")

    if entry_id < 0 or entry_id >= len(entries):
        return _error(
            f"Index {entry_id} out of range (0..{len(entries) - 1})",
            "OUT_OF_RANGE",
            status=400,
        )

    removed = entries.pop(entry_id)
    wl_path.write_text(
        json.dumps(entries, indent=2) + "\n", encoding="utf-8"
    )

    return JSONResponse({
        "status": "ok",
        "removed": removed,
        "remaining": len(entries),
    })


# ---------------------------------------------------------------------------
# GET /api/sessions — List active sessions
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/sessions")
async def api_sessions():
    """List chats with active Claude sessions."""
    if _db_path is None or not _db_path.exists():
        return _error("Database not available", "DB_ERROR")

    try:
        conn = sqlite3.connect(str(_db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, title, claude_session_id, model, created_at "
            "FROM chats WHERE claude_session_id IS NOT NULL "
            "AND claude_session_id != '' "
            "ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
    except sqlite3.Error as e:
        _log.error(f"Database error in sessions list: {e}")
        return _error("Database operation failed", "DB_ERROR")

    sessions = []
    for r in rows:
        sessions.append({
            "chat_id": r["id"],
            "chat_title": r["title"],
            "session_id": r["claude_session_id"],
            "model": r["model"],
            "created_at": r["created_at"],
        })

    return JSONResponse({"sessions": sessions, "count": len(sessions)})


# ---------------------------------------------------------------------------
# POST /api/sessions/{chat_id}/compact — Force compaction
# ---------------------------------------------------------------------------

@dashboard_app.post("/api/sessions/{chat_id}/compact")
async def api_sessions_compact(chat_id: str):
    """Force compaction on a chat session."""
    try:
        import apex as lc
        result = await lc._maybe_compact_chat(chat_id)
    except AttributeError:
        return _error(
            "_maybe_compact_chat not available in apex module",
            "NOT_IMPLEMENTED",
            status=501,
        )
    except Exception as e:
        _log.error(f"Compaction failed: {e}")
        return _error("Compaction failed", "COMPACT_ERROR")

    return JSONResponse({
        "status": "ok",
        "chat_id": chat_id,
        "result": result,
    })


# ---------------------------------------------------------------------------
# DELETE /api/sessions/{chat_id} — Kill session
# ---------------------------------------------------------------------------

@dashboard_app.delete("/api/sessions/{chat_id}")
async def api_sessions_delete(chat_id: str):
    """Kill a session: disconnect client and clear session_id in DB."""
    # Disconnect the client
    try:
        import apex as lc
        await lc._disconnect_client(chat_id)
    except AttributeError:
        pass  # Function may not exist yet — still clear DB below
    except Exception as e:
        _log.error(f"Failed to disconnect client: {e}")
        return _error("Failed to disconnect client", "DISCONNECT_ERROR")

    # Clear session_id in database
    if _db_path and _db_path.exists():
        try:
            conn = sqlite3.connect(str(_db_path), check_same_thread=False)
            conn.execute(
                "UPDATE chats SET claude_session_id = NULL WHERE id = ?",
                (chat_id,),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            _log.error(f"Failed to clear session in DB: {e}")
            return _error("Failed to clear session in database", "DB_ERROR")

    return JSONResponse({
        "status": "ok",
        "chat_id": chat_id,
        "message": "Session killed and cleared from database",
    })


# ===========================================================================
# Phase 5 — Logs, Storage, Backups
# ===========================================================================

_LOG_LINE_RE = re.compile(
    r"^\[apex\s+(\d{2}:\d{2}:\d{2})\]\s*(\w+)?\s*(.*)",
)
_LOG_LINE_STD_RE = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]\s*(.*)",
)
_LOG_LINE_UVICORN_RE = re.compile(
    r"^(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL):\s*(.*)",
)


def _normalize_log_level(level: str) -> str:
    lvl = (level or '').strip().upper()
    if lvl == 'WARNING':
        return 'WARN'
    return lvl


def _extract_level_from_text(text: str) -> str:
    upper = (text or '').upper()
    if 'CRITICAL' in upper:
        return 'CRITICAL'
    if 'ERROR' in upper or 'EXCEPTION' in upper or 'TRACEBACK' in upper:
        return 'ERROR'
    if 'WARNING' in upper or ' WARN ' in f' {upper} ' or upper.startswith('WARN '):
        return 'WARN'
    if 'DEBUG' in upper or upper.startswith('DBG '):
        return 'DEBUG'
    if upper.startswith('INFO') or ' INFO ' in f' {upper} ':
        return 'INFO'
    return ''


def _get_dashboard_log_path() -> Path:
    return Path(LOG_PATH)


def _tail_lines(filepath: Path, n: int) -> list[str]:
    """Read the last *n* lines from a file efficiently (seek from end)."""
    if not filepath.exists() or filepath.stat().st_size == 0:
        return []
    try:
        with open(filepath, "rb") as f:
            f.seek(0, 2)
            end = f.tell()
            if end == 0:
                return []
            block_size = 8192
            blocks: list[bytes] = []
            remaining = end
            lines_found = 0
            while remaining > 0 and lines_found <= n:
                read_size = min(block_size, remaining)
                remaining -= read_size
                f.seek(remaining)
                block = f.read(read_size)
                blocks.append(block)
                lines_found += block.count(b"\n")
            raw = b"".join(reversed(blocks))
            all_lines = raw.decode("utf-8", errors="replace").splitlines()
            return all_lines[-n:]
    except OSError:
        return []


def _parse_log_line(line: str) -> dict[str, str]:
    """Parse supported Apex/uvicorn log lines into {timestamp, level, message}."""
    m = _LOG_LINE_RE.match(line)
    if m:
        message = m.group(3).strip()
        level = _normalize_log_level(m.group(2) or _extract_level_from_text(message) or 'INFO')
        return {
            "timestamp": m.group(1),
            "level": level,
            "message": message,
        }

    m = _LOG_LINE_STD_RE.match(line)
    if m:
        message = m.group(2).strip()
        level = _normalize_log_level(_extract_level_from_text(message))
        return {
            "timestamp": m.group(1),
            "level": level,
            "message": message,
        }

    m = _LOG_LINE_UVICORN_RE.match(line)
    if m:
        return {
            "timestamp": "",
            "level": _normalize_log_level(m.group(1)),
            "message": m.group(2).strip(),
        }

    return {"timestamp": "", "level": _normalize_log_level(_extract_level_from_text(line)), "message": line}


# ---------------------------------------------------------------------------
# GET /api/logs — Read log lines
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/logs")
async def api_logs(lines: int = 100, search: str = "", level: str = ""):
    """Read last N log lines with optional search/level filter."""
    if _state_dir is None:
        return _not_initialized()

    log_path = _get_dashboard_log_path()
    if not log_path.exists():
        return JSONResponse({"lines": [], "total": 0, "file_exists": False})

    n = max(1, min(lines, 1000))
    raw_lines = _tail_lines(log_path, n)

    parsed = [_parse_log_line(l) for l in raw_lines if l.strip()]

    if level:
        level_upper = level.upper()
        parsed = [p for p in parsed if p["level"].upper() == level_upper]

    if search:
        pat = re.compile(re.escape(search), re.IGNORECASE)
        parsed = [p for p in parsed if pat.search(p["message"])]

    return JSONResponse({
        "lines": parsed,
        "total": len(parsed),
        "file_exists": True,
    })


# ---------------------------------------------------------------------------
# GET /api/logs/stream — SSE live tail
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/logs/stream")
async def api_logs_stream():
    """Server-Sent Events live tail of the log file."""
    if _state_dir is None:
        return _not_initialized()

    log_path = _get_dashboard_log_path()

    async def _event_generator():
        """Async generator that tails the log file and yields SSE events."""
        try:
            if not log_path.exists():
                yield f"data: {json.dumps({'type': 'error', 'message': 'Log file not found'})}\n\n"
                return

            with open(log_path, "r") as f:
                f.seek(0, 2)
                last_heartbeat = time.time()
                while True:
                    line = f.readline()
                    if line:
                        line = line.rstrip("\n")
                        if line.strip():
                            parsed = _parse_log_line(line)
                            yield f"data: {json.dumps(parsed)}\n\n"
                    else:
                        now = time.time()
                        if now - last_heartbeat >= 15:
                            yield ": heartbeat\n\n"
                            last_heartbeat = now
                        await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            _log.error(f"Log stream error: {exc}")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Stream error'})}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# POST /api/logs/clear — Rotate log file
# ---------------------------------------------------------------------------

@dashboard_app.post("/api/logs/clear")
async def api_logs_clear():
    """Rotate the active Apex log file to *.log.1 and create a fresh log."""
    if _state_dir is None:
        return _not_initialized()

    log_path = _get_dashboard_log_path()
    backup_path = log_path.with_suffix(log_path.suffix + ".1")

    if not log_path.exists():
        return JSONResponse({"status": "ok", "detail": "No log file to rotate"})

    try:
        old_size = log_path.stat().st_size
        shutil.move(str(log_path), str(backup_path))
        log_path.touch()
        return JSONResponse({
            "status": "ok",
            "rotated_size": old_size,
            "detail": f"Rotated {old_size} bytes to {backup_path.name}",
        })
    except OSError as e:
        _log.error(f"Failed to rotate log: {e}")
        return _error("Failed to rotate log file", "LOG_ROTATE_FAILED")


# ---------------------------------------------------------------------------
# GET /api/db/stats — Database statistics
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/db/stats")
async def api_db_stats():
    """Database stats: file size, table row counts, WAL size, pragmas."""
    if _db_path is None or not _db_path.exists():
        return _error("Database not found", "DB_NOT_FOUND", 404)

    try:
        db_size = _db_path.stat().st_size

        wal_path = Path(str(_db_path) + "-wal")
        wal_size = wal_path.stat().st_size if wal_path.exists() else 0

        conn = sqlite3.connect(str(_db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        freelist_count = conn.execute("PRAGMA freelist_count").fetchone()[0]
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]

        tables_raw = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_counts = {}
        for row in tables_raw:
            tname = row[0]
            try:
                safe_name = tname.replace('"', '""')
                cnt = conn.execute(f'SELECT COUNT(*) FROM "{safe_name}"').fetchone()[0]
                table_counts[tname] = cnt
            except sqlite3.Error:
                table_counts[tname] = -1

        conn.close()

        return JSONResponse({
            "db_size_bytes": db_size,
            "wal_size_bytes": wal_size,
            "page_count": page_count,
            "page_size": page_size,
            "freelist_count": freelist_count,
            "tables": table_counts,
        })
    except sqlite3.Error as e:
        _log.error(f"Database error in db/stats: {e}")
        return _error("Database operation failed", "DB_ERROR")
    except OSError as e:
        _log.error(f"OS error in db/stats: {e}")
        return _error("File system error", "OS_ERROR")


# ---------------------------------------------------------------------------
# POST /api/db/vacuum — VACUUM database
# ---------------------------------------------------------------------------

@dashboard_app.post("/api/db/vacuum")
async def api_db_vacuum():
    """Run VACUUM on the database, return before/after sizes."""
    global _last_vacuum

    if _db_path is None or not _db_path.exists():
        return _error("Database not found", "DB_NOT_FOUND", 404)

    if time.time() - _last_vacuum < 3600:
        return _error("Vacuum already ran recently — wait 1 hour", "RATE_LIMITED", 429)
    if _vacuum_lock.locked():
        return _error("Vacuum already in progress", "ALREADY_RUNNING", 409)

    try:
        size_before = _db_path.stat().st_size

        async with _vacuum_lock:
            db_path_str = str(_db_path)

            def _do_vacuum():
                conn = sqlite3.connect(db_path_str, check_same_thread=False)
                conn.execute("VACUUM")
                conn.close()

            await asyncio.to_thread(_do_vacuum)
            _last_vacuum = time.time()

        size_after = _db_path.stat().st_size

        return JSONResponse({
            "status": "ok",
            "size_before": size_before,
            "size_after": size_after,
            "freed_bytes": size_before - size_after,
        })
    except sqlite3.Error as e:
        _log.error(f"VACUUM failed: {e}")
        return _error("VACUUM operation failed", "VACUUM_FAILED")


# ---------------------------------------------------------------------------
# GET /api/db/export — Download database file
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/db/export")
async def api_db_export():
    """Download the database file as a streaming binary blob."""
    if _db_path is None or not _db_path.exists():
        return _error("Database not found", "DB_NOT_FOUND", 404)

    def _stream_file(path: Path):
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(
        _stream_file(_db_path),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{_db_path.name}"'},
    )


# ---------------------------------------------------------------------------
# DELETE /api/db/messages — Purge old messages
# ---------------------------------------------------------------------------

@dashboard_app.delete("/api/db/messages")
async def api_db_messages_purge(days: int = 30):
    """Delete messages older than N days. Return count deleted."""
    if _db_path is None or not _db_path.exists():
        return _error("Database not found", "DB_NOT_FOUND", 404)

    if days <= 0:
        return _error("Days must be at least 1", "INVALID_DAYS", 400)

    try:
        conn = sqlite3.connect(str(_db_path), check_same_thread=False)
        cursor = conn.execute(
            "DELETE FROM messages WHERE created_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return JSONResponse({
            "status": "ok",
            "deleted": deleted,
            "older_than_days": days,
        })
    except sqlite3.Error as e:
        _log.error(f"Message purge failed: {e}")
        return _error("Message purge failed", "PURGE_FAILED")


# ---------------------------------------------------------------------------
# GET /api/uploads — List uploaded files
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/uploads")
async def api_uploads_list():
    """List files in state/uploads/ with name, size, modified, type."""
    if _state_dir is None:
        return _not_initialized()

    uploads_dir = _state_dir / "uploads"
    if not uploads_dir.exists():
        return JSONResponse({"files": [], "total": 0})

    files = []
    try:
        with os.scandir(str(uploads_dir)) as entries:
            for entry in entries:
                if entry.is_file():
                    stat = entry.stat()
                    suffix = Path(entry.name).suffix.lstrip(".")
                    files.append({
                        "name": entry.name,
                        "size_bytes": stat.st_size,
                        "modified": datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat(),
                        "type": suffix or "unknown",
                    })
    except OSError as e:
        _log.error(f"Failed to list uploads: {e}")
        return _error("Failed to list uploaded files", "UPLOADS_LIST_FAILED")

    files.sort(key=lambda f: f["modified"], reverse=True)
    return JSONResponse({"files": files, "total": len(files)})


# ---------------------------------------------------------------------------
# POST /api/uploads/cleanup — Delete old uploads
# ---------------------------------------------------------------------------

@dashboard_app.post("/api/uploads/cleanup")
async def api_uploads_cleanup(days: int = 7):
    """Delete uploaded files older than N days."""
    if _state_dir is None:
        return _not_initialized()

    uploads_dir = _state_dir / "uploads"
    if not uploads_dir.exists():
        return JSONResponse({"status": "ok", "deleted": 0})

    days = max(1, days)
    cutoff = time.time() - (days * 86400)
    deleted = 0

    try:
        with os.scandir(str(uploads_dir)) as entries:
            for entry in entries:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    os.unlink(entry.path)
                    deleted += 1
    except OSError as e:
        _log.error(f"Upload cleanup failed: {e}")
        return _error("Cleanup failed", "CLEANUP_FAILED")

    return JSONResponse({
        "status": "ok",
        "deleted": deleted,
        "older_than_days": days,
    })


# ---------------------------------------------------------------------------
# POST /api/backup — Create backup tarball
# ---------------------------------------------------------------------------

_BACKUP_FILES = ["apex.db", "config.json", "guardrail_whitelist.json"]

# Exclude private key material from standard backups (security: V2-04)
_BACKUP_SSL_EXCLUDE = {".key", ".p12", ".pfx", ".pem"}


@dashboard_app.post("/api/backup")
async def api_backup_create():
    """Create a backup tarball of key state files + ssl dir."""
    global _last_backup

    if _state_dir is None:
        return _not_initialized()

    if time.time() - _last_backup < _BACKUP_COOLDOWN:
        return _error("Backup cooldown — try again later", "RATE_LIMITED", status=429)

    async with _backup_lock:
        backups_dir = _state_dir / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"apex-backup-{ts}.tar.gz"
        backup_path = backups_dir / filename

        try:
            with tarfile.open(str(backup_path), "w:gz") as tar:
                for name in _BACKUP_FILES:
                    fpath = _state_dir / name
                    if fpath.exists():
                        tar.add(str(fpath), arcname=name)

                ssl_dir = _state_dir / "ssl"
                if ssl_dir.exists() and ssl_dir.is_dir():
                    for item in ssl_dir.rglob("*"):
                        if item.is_file() and item.suffix.lower() not in _BACKUP_SSL_EXCLUDE:
                            arcname = f"ssl/{item.relative_to(ssl_dir)}"
                            tar.add(str(item), arcname=arcname)

            size = backup_path.stat().st_size
            _last_backup = time.time()
            return JSONResponse({
                "status": "ok",
                "id": ts,
                "filename": filename,
                "size_bytes": size,
            })
        except (OSError, tarfile.TarError) as e:
            _log.error(f"Backup creation failed: {e}")
            return _error("Backup creation failed", "BACKUP_FAILED")


# ---------------------------------------------------------------------------
# GET /api/backups — List available backups
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/backups")
async def api_backups_list():
    """List backup tarballs in state/backups/."""
    if _state_dir is None:
        return _not_initialized()

    backups_dir = _state_dir / "backups"
    if not backups_dir.exists():
        return JSONResponse({"backups": [], "total": 0})

    backups = []
    try:
        with os.scandir(str(backups_dir)) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.endswith(".tar.gz"):
                    stat = entry.stat()
                    backups.append({
                        "filename": entry.name,
                        "size_bytes": stat.st_size,
                        "created": datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat(),
                    })
    except OSError as e:
        _log.error(f"Failed to list backups: {e}")
        return _error("Failed to list backups", "BACKUPS_LIST_FAILED")

    backups.sort(key=lambda b: b["created"], reverse=True)
    return JSONResponse({"backups": backups, "total": len(backups)})


# ---------------------------------------------------------------------------
# GET /api/backups/{filename} — Download backup file
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/backups/{filename}")
async def api_backup_download(filename: str):
    """Download a backup tarball."""
    if _state_dir is None:
        return _not_initialized()

    if "/" in filename or "\\" in filename or ".." in filename:
        return _error("Invalid filename", "INVALID_FILENAME", 400)

    backups_dir = _state_dir / "backups"
    backup_path = backups_dir / filename

    if not backup_path.exists():
        return _error(f"Backup not found: {filename}", "BACKUP_NOT_FOUND", 404)

    def _stream_file(path: Path):
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    try:
        return StreamingResponse(
            _stream_file(backup_path),
            media_type="application/gzip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except OSError as e:
        _log.error(f"Failed to read backup: {e}")
        return _error("Failed to read backup file", "BACKUP_READ_FAILED")


# ---------------------------------------------------------------------------
# POST /api/backup/restore — Restore from backup
# ---------------------------------------------------------------------------

@dashboard_app.post("/api/backup/restore")
async def api_backup_restore(request: Request):
    """Restore state from a backup tarball. Extracts to temp, validates, moves."""
    if _state_dir is None:
        return _not_initialized()

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body", "BAD_REQUEST", 400)

    filename = body.get("filename", "")
    if not filename:
        return _error("filename is required", "BAD_REQUEST", 400)

    if "/" in filename or "\\" in filename or ".." in filename:
        return _error("Invalid filename", "INVALID_FILENAME", 400)

    backups_dir = _state_dir / "backups"
    backup_path = backups_dir / filename

    if not backup_path.exists():
        return _error(f"Backup not found: {filename}", "BACKUP_NOT_FOUND", 404)

    tmp_dir = None
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="apex-restore-"))

        with tarfile.open(str(backup_path), "r:gz") as tar:
            for member in tar.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    return _error("Unsafe path in archive", "UNSAFE_ARCHIVE", status=400)
                if member.issym() or member.islnk():
                    return _error("Unsafe archive member", "UNSAFE_ARCHIVE", status=400)
                dest = (tmp_dir / member.name).resolve()
                if not str(dest).startswith(str(tmp_dir.resolve())):
                    return _error("Path escape in archive", "UNSAFE_ARCHIVE", status=400)
                tar.extract(member, path=str(tmp_dir))

        extracted = list(tmp_dir.rglob("*"))
        extracted_names = [p.name for p in extracted if p.is_file()]
        if not any(n in extracted_names for n in ("apex.db", "localchat.db", "config.json")):
            return _error(
                "Archive does not contain apex.db or config.json",
                "INVALID_BACKUP",
                400,
            )

        restored = []

        for name in _BACKUP_FILES:
            src = tmp_dir / name
            if src.exists():
                dest = _state_dir / name
                shutil.copy2(str(src), str(dest))
                restored.append(name)

        ssl_src = tmp_dir / "ssl"
        ssl_keys_missing = False
        if ssl_src.exists() and ssl_src.is_dir():
            ssl_dest = _state_dir / "ssl"
            ssl_dest.mkdir(parents=True, exist_ok=True)
            for item in ssl_src.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(ssl_src)
                    dest_file = ssl_dest / rel
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(item), str(dest_file))
                    restored.append(f"ssl/{rel}")
            # Lock down restored SSL directory and key permissions
            _harden_ssl_dir(ssl_dest)
        # Check if the target ssl dir has key files that weren't in the backup
        ssl_dest_check = _state_dir / "ssl"
        if ssl_dest_check.exists() and ssl_dest_check.is_dir():
            for item in ssl_dest_check.rglob("*"):
                if item.is_file() and item.suffix.lower() in _BACKUP_SSL_EXCLUDE:
                    ssl_keys_missing = True
                    break
        if ssl_keys_missing:
            _log.warning(
                "SSL private key files (.key/.p12/.pfx/.pem) are excluded from "
                "backups for security (V2-04). Re-generate or copy keys manually "
                "after restore."
            )

        detail = "Backup restored. Server restart required for changes to take effect."
        if ssl_keys_missing:
            detail += (
                " Note: SSL private key files were excluded from this backup for "
                "security. Re-generate or copy keys manually."
            )

        return JSONResponse({
            "status": "ok",
            "restored_files": restored,
            "restart_required": True,
            "ssl_keys_excluded": ssl_keys_missing,
            "detail": detail,
        })

    except (tarfile.TarError, OSError) as e:
        _log.error(f"Restore failed: {e}")
        return _error("Backup restore failed", "RESTORE_FAILED")
    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(str(tmp_dir), ignore_errors=True)


# ---------------------------------------------------------------------------
# Security page data
# ---------------------------------------------------------------------------

_security_audit_sync_state: dict[str, int | None] = {
    "mtime_ns": None,
    "size": None,
}


def _workspace_root() -> Path:
    """Return the configured Apex workspace path."""
    return env.get_runtime_workspace_root()


def _security_audit_log_path() -> Path:
    return _workspace_root() / "logs" / "agent_audit.jsonl"


def _format_relative_time(iso_ts: str | None) -> str:
    """Format an ISO timestamp relative to now."""
    if not iso_ts:
        return "never"
    dt = _parse_iso(iso_ts)
    if dt is None:
        return "unknown"
    now = datetime.now(timezone.utc)
    delta = max(0, int((now - dt).total_seconds()))
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def _safe_eval_python_expr(node: ast.AST, names: dict[str, Any]) -> Any:
    """Evaluate a narrow literal subset from guardrail source files."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_safe_eval_python_expr(item, names) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_safe_eval_python_expr(item, names) for item in node.elts)
    if isinstance(node, ast.Set):
        return {_safe_eval_python_expr(item, names) for item in node.elts}
    if isinstance(node, ast.Dict):
        return {
            _safe_eval_python_expr(key, names): _safe_eval_python_expr(value, names)
            for key, value in zip(node.keys, node.values, strict=False)
        }
    if isinstance(node, ast.Name):
        if node.id in names:
            return names[node.id]
        raise ValueError(f"unsupported name: {node.id}")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _safe_eval_python_expr(node.left, names)
        right = _safe_eval_python_expr(node.right, names)
        return left + right
    if isinstance(node, ast.Attribute):
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr == "sep"
        ):
            return os.sep
        raise ValueError("unsupported attribute")
    if isinstance(node, ast.Call):
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "expanduser"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "path"
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "os"
            and len(node.args) == 1
            and not node.keywords
        ):
            arg = _safe_eval_python_expr(node.args[0], names)
            return os.path.expanduser(str(arg))
        raise ValueError("unsupported call")
    raise ValueError(f"unsupported AST node: {type(node).__name__}")


def _load_python_assignments(path: Path) -> dict[str, Any]:
    """Parse simple top-level assignments without executing the source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: dict[str, Any] = {}
    for node in tree.body:
        target_name = None
        value_node: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            target_name = node.target.id
            value_node = node.value
        if not target_name or value_node is None:
            continue
        try:
            names[target_name] = _safe_eval_python_expr(value_node, names)
        except ValueError:
            continue
    return names


def _count_collection_items(path: Path, name: str) -> int:
    """Count literal collection entries for a top-level assignment."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        target_name = None
        value_node: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            target_name = node.target.id
            value_node = node.value
        if target_name != name or value_node is None:
            continue
        if isinstance(value_node, (ast.List, ast.Tuple, ast.Set)):
            return len(value_node.elts)
        raise ValueError(f"{name} is not a collection literal")
    raise ValueError(f"{name} not found")


def _load_guardrail_summary() -> dict[str, Any]:
    """Read current guardrail constants from the workspace source of truth."""
    workspace = _workspace_root()
    core_path = workspace / "scripts" / "guardrails" / "guardrail_core.py"
    secrets_path = workspace / "scripts" / "guardrails" / "secret_patterns.py"
    try:
        core = _load_python_assignments(core_path)
        secret_pattern_count = _count_collection_items(secrets_path, "SECRET_PATTERNS")
    except Exception as exc:
        _log.error(f"SECURITY_GUARDRAILS_LOAD_FAILED: {exc}")
        return {
            "protected_count": 0,
            "sandbox_rule_count": 0,
            "secret_pattern_count": 0,
        }

    protected_count = sum((
        len(core.get("PROTECTED_EXACT", set())),
        len(core.get("PROTECTED_ABSOLUTE", set())),
        len(core.get("PROTECTED_SUFFIXES", ())),
        len(core.get("PROTECTED_SUBSTRINGS", ())),
    ))
    sandbox_rule_count = sum((
        len(core.get("SANDBOX_ALLOW", [])),
        len(core.get("SANDBOX_BLOCK", [])),
    ))
    return {
        "protected_count": protected_count,
        "sandbox_rule_count": sandbox_rule_count,
        "secret_pattern_count": secret_pattern_count,
    }


def _ensure_security_audit_table(conn: sqlite3.Connection) -> None:
    """Create the mirrored security audit table if it does not exist yet."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS security_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT NOT NULL UNIQUE,
            timestamp TEXT NOT NULL,
            session_id TEXT,
            actor TEXT,
            tool_name TEXT,
            original_tool_name TEXT,
            target TEXT,
            status TEXT NOT NULL,
            summary TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_security_audit_ts "
        "ON security_audit_log(timestamp DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_security_audit_status "
        "ON security_audit_log(status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_security_audit_actor "
        "ON security_audit_log(actor)"
    )


def _sync_security_audit_log() -> dict[str, Any]:
    """Mirror the JSONL agent audit trail into SQLite for querying."""
    if _db_path is None:
        raise RuntimeError("Dashboard not initialized")

    audit_path = _security_audit_log_path()
    if not audit_path.exists():
        return {
            "status": "missing",
            "path": str(audit_path),
            "imported": 0,
            "total": 0,
            "last_entry_at": None,
        }

    stat = audit_path.stat()
    unchanged = (
        _security_audit_sync_state.get("mtime_ns") == stat.st_mtime_ns
        and _security_audit_sync_state.get("size") == stat.st_size
    )

    conn = sqlite3.connect(str(_db_path))
    try:
        _ensure_security_audit_table(conn)
        imported = 0
        if not unchanged:
            with audit_path.open("r", encoding="utf-8", errors="replace") as handle:
                for raw_line in handle:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        payload = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue

                    raw_json = json.dumps(
                        payload, sort_keys=True, separators=(",", ":"), default=str
                    )
                    event_key = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
                    before = conn.total_changes
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO security_audit_log (
                            event_key, timestamp, session_id, actor, tool_name,
                            original_tool_name, target, status, summary, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_key,
                            str(payload.get("timestamp", "")),
                            str(payload.get("session_id", "")),
                            str(payload.get("actor", "")),
                            str(payload.get("tool_name", "")),
                            str(payload.get("original_tool_name", "")),
                            str(payload.get("target", "")),
                            str(payload.get("status", "")),
                            str(payload.get("summary", "")),
                            raw_json,
                        ),
                    )
                    if conn.total_changes > before:
                        imported += 1
            conn.commit()
            _security_audit_sync_state["mtime_ns"] = stat.st_mtime_ns
            _security_audit_sync_state["size"] = stat.st_size

        total = conn.execute(
            "SELECT COUNT(*) FROM security_audit_log"
        ).fetchone()[0]
        last_entry_at = conn.execute(
            "SELECT MAX(timestamp) FROM security_audit_log"
        ).fetchone()[0]
        return {
            "status": "ok",
            "path": str(audit_path),
            "imported": imported,
            "total": total,
            "last_entry_at": last_entry_at,
        }
    finally:
        conn.close()


@dashboard_app.get("/api/security/posture")
async def api_security_posture():
    """Aggregate the live data needed for the security posture tab."""
    if _config is None:
        return _not_initialized()

    try:
        tls = _get_tls_status_data()
    except RuntimeError:
        return _not_initialized()
    except FileNotFoundError:
        tls = {"status": "critical", "certificates": {}, "warnings": ["SSL directory not found"]}

    try:
        audit_sync = _sync_security_audit_log()
    except RuntimeError:
        return _not_initialized()

    guardrails = _load_guardrail_summary()
    server_cert = tls.get("certificates", {}).get("server", {})
    server_days = int(server_cert.get("days_remaining", -1) or -1)
    mtls_status = server_cert.get("status", "error")
    if mtls_status == "ok":
        mtls_level = "ok"
    elif mtls_status in {"expiring_soon", "missing", "error"}:
        mtls_level = "warning"
    else:
        mtls_level = "critical"

    rate_limits: dict[str, tuple[int, int]] = {}
    try:
        import apex as _lc

        rate_limits = dict(getattr(_lc, "_RATE_LIMITS", {}))
    except Exception:
        pass

    total_audit = int(audit_sync.get("total", 0) or 0)
    last_audit_at = audit_sync.get("last_entry_at")
    warning_count = 0
    items = [
        {
            "key": "mtls",
            "label": "mTLS",
            "status": mtls_level,
            "detail": (
                f"CERT_REQUIRED · server cert expires in {server_days} days"
                if server_days >= 0
                else "CERT_REQUIRED · certificate status unavailable"
            ),
        },
        {
            "key": "csrf",
            "label": "CSRF",
            "status": "ok",
            "detail": "Admin mutations require X-Requested-With",
        },
        {
            "key": "guardrails",
            "label": "Guardrails",
            "status": "ok" if guardrails["protected_count"] > 0 else "warning",
            "detail": (
                f"{guardrails['protected_count']} protected patterns · "
                f"{guardrails['sandbox_rule_count']} sandbox rules"
            ),
        },
        {
            "key": "rate-limiting",
            "label": "Rate Limiting",
            "status": "ok" if rate_limits else "warning",
            "detail": (
                f"Active on {len(rate_limits)} endpoints"
                if rate_limits
                else "No global expensive-endpoint limits configured"
            ),
        },
        {
            "key": "audit-log",
            "label": "Audit Log",
            "status": "ok" if total_audit > 0 else "warning",
            "detail": (
                f"{total_audit:,} entries · last {_format_relative_time(str(last_audit_at))}"
                if total_audit > 0
                else "No audit entries mirrored yet"
            ),
        },
        {
            "key": "headers",
            "label": "Headers",
            "status": "warning",
            "detail": "HSTS · X-Frame-Options · nosniff · CSP pending",
        },
    ]
    warning_count = sum(1 for item in items if item["status"] != "ok")

    banner = None
    if 0 <= server_days < 14:
        banner = {
            "level": "critical",
            "message": f"Server certificate expires in {server_days} days.",
            "action_label": "View audit log",
            "action_tab": "audit",
        }

    return JSONResponse({
        "status": "ok",
        "warning_count": warning_count,
        "banner": banner,
        "server": {
            "running": True,
            "pid": os.getpid(),
            "uptime_human": _format_uptime(time.time() - _start_time),
        },
        "items": items,
        "summary": {
            "tls_warnings": tls.get("warnings", []),
            "rate_limit_count": len(rate_limits),
            "guardrails": guardrails,
            "audit_total": total_audit,
            "audit_last_entry_at": last_audit_at,
        },
    })


@dashboard_app.get("/api/security/audit")
async def api_security_audit(
    status: str = "all",
    search: str = "",
    page: int = 1,
    page_size: int = 25,
):
    """Return paginated audit events for the security page."""
    if _db_path is None:
        return _not_initialized()

    page = max(1, page)
    page_size = max(1, min(100, page_size))
    search = (search or "").strip().lower()

    try:
        sync_info = _sync_security_audit_log()
    except RuntimeError:
        return _not_initialized()

    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    try:
        _ensure_security_audit_table(conn)

        clauses: list[str] = []
        params: list[Any] = []
        if status == "blocked":
            clauses.append("status = ?")
            params.append("blocked")
        elif status == "allowed":
            clauses.append("status = ?")
            params.append("allowed")
        elif status == "whitelisted":
            clauses.append("status = ?")
            params.append("allowed_via_whitelist")

        if search:
            like = f"%{search}%"
            clauses.append(
                "("
                "lower(actor) LIKE ? OR lower(tool_name) LIKE ? OR "
                "lower(target) LIKE ? OR lower(summary) LIKE ? OR "
                "lower(session_id) LIKE ?"
                ")"
            )
            params.extend([like, like, like, like, like])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        total = conn.execute(
            f"SELECT COUNT(*) FROM security_audit_log {where_sql}",
            params,
        ).fetchone()[0]
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""
            SELECT timestamp, session_id, actor, tool_name, original_tool_name,
                   target, status, summary
            FROM security_audit_log
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        ).fetchall()
        grouped = conn.execute(
            "SELECT status, COUNT(*) AS count FROM security_audit_log GROUP BY status"
        ).fetchall()
        status_counts = {row["status"]: row["count"] for row in grouped}

        entries = []
        for row in rows:
            entries.append({
                "timestamp": row["timestamp"],
                "session_id": row["session_id"],
                "actor": row["actor"],
                "tool_name": row["tool_name"],
                "original_tool_name": row["original_tool_name"],
                "target": row["target"],
                "status": row["status"],
                "summary": row["summary"],
            })

        return JSONResponse({
            "status": "ok",
            "filter": status,
            "search": search,
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": max(1, math.ceil(total / page_size)) if total else 1,
            "entries": entries,
            "status_counts": {
                "allowed": int(status_counts.get("allowed", 0) or 0),
                "blocked": int(status_counts.get("blocked", 0) or 0),
                "whitelisted": int(status_counts.get("allowed_via_whitelist", 0) or 0),
            },
            "meta": {
                "log_path": sync_info.get("path"),
                "last_entry_at": sync_info.get("last_entry_at"),
                "last_entry_relative": _format_relative_time(
                    str(sync_info.get("last_entry_at") or "")
                ),
                "server_log_level": logging.getLevelName(
                    logging.getLogger().getEffectiveLevel()
                ),
                "mirrored_into_db": True,
            },
        })
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Catch-all for unknown API routes
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Memory scoring observability
# ---------------------------------------------------------------------------

_MEM_CAT_WEIGHT = {"correction": 1.0, "decision": 0.7, "task": 0.5, "context": 0.3}
_MEM_MAX_TOKEN_BUDGET = 80


_MIN_INJECTION_SCORE = 0.10  # matches context.py threshold


def _score_with_breakdown(memories: list[dict], user_message: str = "") -> list[dict]:
    """Score memories and return per-dimension breakdown for observability.

    Mirrors the production scorer in context.py but collects each component
    separately so the debug endpoint can expose why each memory ranked where it did.
    """
    now = datetime.now(timezone.utc)
    user_words = set(user_message.lower().split()) if user_message else set()

    for mem in memories:
        bd: dict[str, float] = {}
        created = _parse_iso(mem["created_at"])
        last_acc = _parse_iso(mem.get("last_accessed_at", ""))

        age_hours = max(0, (now - created).total_seconds() / 3600)
        bd["recency"] = round(0.12 * math.exp(-0.693 * age_hours / (7 * 24)), 4)

        acc = mem.get("access_count", 0)
        bd["frequency"] = round(0.10 * min(1.0, math.log1p(acc) / math.log1p(50)), 4)

        bd["category_weight"] = round(0.12 * _MEM_CAT_WEIGHT.get(mem.get("category", ""), 0.3), 4)

        if user_words:
            mem_words = set(mem["content"].lower().split())
            overlap = len(user_words & mem_words)
            bd["task_proximity"] = round(0.25 * min(1.0, overlap / max(3, len(user_words) * 0.3)), 4)
        else:
            bd["task_proximity"] = 0.0

        if mem.get("last_accessed_at"):
            stale_days = max(0, (now - last_acc).total_seconds() / 86400)
            bd["staleness_decay"] = round(0.08 * math.exp(-0.693 * stale_days / 14), 4)
        else:
            bd["staleness_decay"] = 0.02

        viol = mem.get("violation_count", 0)
        if mem.get("category") == "correction" and viol > 0:
            bd["violation_boost"] = round(0.10 * min(1.0, viol / 5), 4)
        elif mem.get("category") == "correction":
            bd["violation_boost"] = 0.05
        else:
            bd["violation_boost"] = 0.0

        tc = mem.get("token_count", 0) or len(mem["content"].split())
        if tc > _MEM_MAX_TOKEN_BUDGET:
            bd["token_roi"] = round(0.03 * max(0, 1 - (tc - _MEM_MAX_TOKEN_BUDGET) / 200), 4)
        else:
            bd["token_roi"] = 0.03

        bd["superseded_penalty"] = 0.0
        mem["_breakdown"] = bd
        mem["_score"] = round(sum(bd.values()), 4)
        mem["_superseded"] = False

    # Superseded post-pass
    word_sets = [(set(m["content"].lower().split()), m) for m in memories]
    for i, (ws_i, mem_i) in enumerate(word_sets):
        for j, (ws_j, mem_j) in enumerate(word_sets):
            if i >= j or not ws_i or not ws_j:
                continue
            overlap = len(ws_i & ws_j) / min(len(ws_i), len(ws_j))
            if overlap >= 0.6:
                older = mem_i if mem_i["created_at"] < mem_j["created_at"] else mem_j
                older["_breakdown"]["superseded_penalty"] = -0.05
                older["_score"] = round(max(0, older["_score"] - 0.05), 4)
                older["_superseded"] = True

    memories.sort(key=lambda m: m["_score"], reverse=True)
    return memories


@dashboard_app.get("/api/memory-scores/{profile_id}")
async def api_memory_scores(profile_id: str, request: Request):
    """Debug: score all memories for a profile and return full breakdown."""
    params = request.query_params
    message = str(params.get("message", ""))[:500]
    try:
        limit = min(200, max(1, int(params.get("limit", "80"))))
    except (ValueError, TypeError):
        limit = 80

    injection_limit = 30
    all_memories = _get_persona_memories(profile_id, limit=limit)
    scored = _score_with_breakdown(all_memories, user_message=message)

    candidates = []
    for i, mem in enumerate(scored):
        would_inject = (i < injection_limit
                        and mem["_score"] >= _MIN_INJECTION_SCORE
                        and not mem.get("_superseded"))
        candidates.append({
            "rank": i + 1,
            "injected": would_inject,
            "superseded": bool(mem.get("_superseded")),
            "below_threshold": mem["_score"] < _MIN_INJECTION_SCORE,
            "id": mem["id"],
            "category": mem.get("category", ""),
            "content": mem["content"],
            "created_at": mem.get("created_at", ""),
            "access_count": mem.get("access_count", 0),
            "last_accessed_at": mem.get("last_accessed_at", ""),
            "violation_count": mem.get("violation_count", 0),
            "token_count": mem.get("token_count", 0),
            "score": mem["_score"],
            "breakdown": mem["_breakdown"],
        })

    return JSONResponse({
        "profile_id": profile_id,
        "message": message,
        "total_candidates": len(scored),
        "injection_limit": injection_limit,
        "min_score": _MIN_INJECTION_SCORE,
        "injected_count": sum(1 for c in candidates if c["injected"]),
        "candidates": candidates,
    })


# ─── Plan M Screener Reports ────────────────────────────────────────────────

_PLAN_M_RESULTS_DIR = Path(
    os.environ.get(
        "PLAN_M_RESULTS_DIR",
        os.path.expanduser("~/.openclaw/workspace/plan_m/results/current"),
    )
)

_PLAN_M_REPORTS = {
    "long": "plan_m_long_report.html",
    "short": "plan_m_short_report.html",
}


@dashboard_app.get("/plan-m", response_class=HTMLResponse)
async def plan_m_index():
    """Plan M screener index — links to long/short reports + JSON status."""
    reports = []
    for label, fname in _PLAN_M_REPORTS.items():
        fpath = _PLAN_M_RESULTS_DIR / fname
        exists = fpath.is_file()
        mtime = ""
        if exists:
            import datetime as _dt
            mtime = _dt.datetime.fromtimestamp(fpath.stat().st_mtime).strftime(
                "%Y-%m-%d %H:%M"
            )
        reports.append((label, fname, exists, mtime))

    # Read screen_results.json for market status
    results_json = _PLAN_M_RESULTS_DIR / "plan_m_screen_results.json"
    market_status = ""
    if results_json.is_file():
        try:
            import json as _json
            data = _json.loads(results_json.read_text())
            mkt = data.get("market", {})
            ap = mkt.get("all_pass", False)
            fg = mkt.get("fg_today", 0)
            close = mkt.get("close", 0)
            date = mkt.get("date", "")
            status_color = "#27ae60" if ap else "#e74c3c"
            status_text = "GO" if ap else "NO-GO"
            market_status = (
                f'<div style="margin:12px 0;padding:10px 16px;background:#16213e;'
                f'border-left:4px solid {status_color};border-radius:4px;">'
                f'<span style="color:{status_color};font-weight:700;font-size:16px;">'
                f'{status_text}</span>'
                f' &nbsp; SPY ${close:.2f} &nbsp; F&amp;G={fg:.0f} &nbsp; '
                f'<span style="color:#888;">({date})</span></div>'
            )
        except Exception:
            pass

    rows = ""
    for label, fname, exists, mtime in reports:
        if exists:
            rows += (
                f'<tr><td><a href="/admin/plan-m/{label}" '
                f'style="color:#64b5f6;text-decoration:none;font-weight:600;">'
                f'{label.title()}</a></td>'
                f'<td style="color:#888;">{mtime}</td></tr>'
            )
        else:
            rows += (
                f'<tr><td style="color:#555;">{label.title()}</td>'
                f'<td style="color:#555;">not generated</td></tr>'
            )

    return HTMLResponse(
        f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Plan M Screener</title>
<style>
  body {{ background:#1a1a2e; color:#eee; font-family:-apple-system,'SF Mono',monospace; margin:20px; }}
  h1 {{ color:#27ae60; font-size:22px; }}
  table {{ border-collapse:collapse; margin-top:12px; }}
  td {{ padding:8px 16px; border-bottom:1px solid #262640; }}
  a:hover {{ text-decoration:underline !important; }}
  .back {{ color:#888; font-size:13px; margin-top:20px; }}
  .back a {{ color:#64b5f6; text-decoration:none; }}
</style></head><body>
<h1>Plan M Screener</h1>
{market_status}
<table>{rows}</table>
<div style="margin-top:16px;">
  <a href="/admin/api/plan-m/results" style="color:#888;font-size:13px;text-decoration:none;">
    Raw JSON &rarr;</a>
</div>
<div class="back"><a href="/admin/">&larr; Dashboard</a></div>
</body></html>"""
    )


@dashboard_app.get("/plan-m/{report_type}", response_class=HTMLResponse)
async def plan_m_report(report_type: str):
    """Serve a Plan M report HTML (long or short)."""
    fname = _PLAN_M_REPORTS.get(report_type)
    if not fname:
        return HTMLResponse(
            "<h1>Not found</h1><p>Valid reports: long, short</p>", status_code=404
        )
    fpath = _PLAN_M_RESULTS_DIR / fname
    if not fpath.is_file():
        return HTMLResponse(
            f"<html><body style='background:#1a1a2e;color:#eee;font-family:system-ui;'>"
            f"<h1>Plan M {report_type.title()} Report</h1>"
            f"<p style='color:#e74c3c;'>Report not yet generated.</p>"
            f"<p style='color:#888;'>Run the screener to generate: "
            f"<code>python3 plan_m_{report_type}_screener.py --force</code></p>"
            f"<p><a href='/admin/plan-m' style='color:#64b5f6;'>Back</a></p>"
            f"</body></html>",
            status_code=200,
        )
    html = fpath.read_text()
    # Inject a back-link at the top of the report body
    back_link = (
        '<div style="margin-bottom:10px;">'
        '<a href="/admin/plan-m" style="color:#888;font-size:13px;'
        'text-decoration:none;font-family:system-ui;">&larr; Plan M Index</a>'
        '</div>'
    )
    html = html.replace("<body>", f"<body>{back_link}", 1)
    return HTMLResponse(html)


@dashboard_app.get("/api/plan-m/results")
async def api_plan_m_results():
    """Return the latest Plan M screen results JSON."""
    fpath = _PLAN_M_RESULTS_DIR / "plan_m_screen_results.json"
    if not fpath.is_file():
        return _error("No screen results found", "NOT_FOUND", status=404)
    import json as _json
    try:
        data = _json.loads(fpath.read_text())
        return JSONResponse(data)
    except Exception as exc:
        return _error(str(exc), "PARSE_ERROR", status=500)


# ---------------------------------------------------------------------------
# Memory Admin — Subconscious Memory System
# ---------------------------------------------------------------------------

def _subconscious_dir() -> Path | None:
    """Resolve .subconscious state directory from workspace paths."""
    for p in env.get_runtime_workspace_paths_list():
        sub = Path(p) / ".subconscious"
        if sub.is_dir():
            return sub
    root = _workspace_root()
    sub = root / ".subconscious"
    return sub if sub.is_dir() else None


def _read_subconscious_json(filename: str) -> dict | list | None:
    """Read a JSON file from .subconscious/ with error handling."""
    sub = _subconscious_dir()
    if not sub:
        return None
    path = sub / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _write_subconscious_json(filename: str, data: Any) -> bool:
    """Atomic write to .subconscious/ with file locking."""
    sub = _subconscious_dir()
    if not sub:
        return False
    path = sub / filename
    lock_path = sub / ".lock"
    lock_path.touch(exist_ok=True)
    import fcntl
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(sub), suffix=".tmp")
        try:
            os.write(tmp_fd, json.dumps(data, indent=2).encode())
        finally:
            os.close(tmp_fd)
        os.replace(tmp_path, str(path))
        return True
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except Exception:
            pass
        fd.close()


def _migrate_guidance_item(item: dict) -> dict:
    """Add Type 1/Type 2 fields if missing (transparent migration)."""
    if "pathway" not in item:
        t = item.get("type", "")
        if t in ("invariant", "correction"):
            item["pathway"] = "type1"
        else:
            item["pathway"] = "type2"
    if "injection_count" not in item:
        item["injection_count"] = 0
    if "promotion_score" not in item:
        item["promotion_score"] = 0.0
    return item


@dashboard_app.get("/api/memory/status")
async def api_memory_status():
    """Aggregated memory system health status."""
    sub = _subconscious_dir()

    # Feature flags
    type1_enabled = getattr(env, "ENABLE_TYPE1_GUIDANCE", False)
    unified_enabled = getattr(env, "ENABLE_UNIFIED_MEMORY", False)
    metacog_enabled = getattr(env, "ENABLE_METACOGNITION", False)

    # Guidance counts
    guidance = _read_subconscious_json("guidance.json") or {}
    items = guidance.get("items", [])
    items = [_migrate_guidance_item(it) for it in items]
    type1_count = sum(1 for it in items if it.get("pathway") == "type1")
    type2_count = sum(1 for it in items if it.get("pathway") == "type2")
    total_chars = sum(len(it.get("text", "")) for it in items)

    # Contradiction count
    contradictions = _read_subconscious_json("pending_review.json") or []
    if isinstance(contradictions, dict):
        contradictions = contradictions.get("items", [])
    pending_count = sum(
        1 for c in contradictions if c.get("status", "pending") == "pending"
    )

    # Metacognition index
    metacog_docs = 0
    metacog_size = 0
    metacog_last_built = None
    if sub:
        meta_path = sub / "metacognition" / "metacognition_meta.json"
        vec_path = sub / "metacognition" / "metacognition_vectors.npy"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                metacog_docs = len(meta) if isinstance(meta, list) else 0
                metacog_last_built = datetime.fromtimestamp(
                    meta_path.stat().st_mtime, tz=timezone.utc
                ).isoformat()
            except Exception:
                pass
        if vec_path.exists():
            try:
                metacog_size = vec_path.stat().st_size
            except OSError:
                pass

    # Feedback stats
    feedback_evals = 0
    if sub:
        fb_index = sub / "whisper_feedback" / "index.json"
        if fb_index.exists():
            try:
                fb = json.loads(fb_index.read_text())
                feedback_evals = fb.get("total_evaluations", 0)
            except Exception:
                pass

    # Last extraction / consolidation timestamps
    last_extraction = None
    last_consolidation = None
    if sub:
        guidance_path = sub / "guidance.json"
        if guidance_path.exists():
            try:
                last_extraction = datetime.fromtimestamp(
                    guidance_path.stat().st_mtime, tz=timezone.utc
                ).isoformat()
            except OSError:
                pass
        autodream_log = sub / "autodream.log"
        if autodream_log.exists():
            try:
                last_consolidation = datetime.fromtimestamp(
                    autodream_log.stat().st_mtime, tz=timezone.utc
                ).isoformat()
            except OSError:
                pass

    return JSONResponse({
        "status": "ok",
        "type1_enabled": type1_enabled,
        "unified_enabled": unified_enabled,
        "metacog_enabled": metacog_enabled,
        "guidance_count": len(items),
        "type1_count": type1_count,
        "type2_count": type2_count,
        "total_chars": total_chars,
        "contradiction_count": pending_count,
        "metacog_doc_count": metacog_docs,
        "metacog_size_bytes": metacog_size,
        "metacog_last_built": metacog_last_built,
        "feedback_evaluations": feedback_evals,
        "last_extraction": last_extraction,
        "last_consolidation": last_consolidation,
        "initialized": sub is not None,
    })


@dashboard_app.get("/api/memory/guidance")
async def api_memory_guidance():
    """List all guidance items with full metadata."""
    guidance = _read_subconscious_json("guidance.json") or {}
    items = guidance.get("items", [])
    items = [_migrate_guidance_item(it) for it in items]
    total_chars = sum(len(it.get("text", "")) for it in items)

    return JSONResponse({
        "status": "ok",
        "items": items,
        "count": len(items),
        "total_chars": total_chars,
    })


@dashboard_app.delete("/api/memory/guidance/{index}")
async def api_memory_guidance_delete(index: int):
    """Delete a guidance item by index."""
    sub = _subconscious_dir()
    if not sub:
        return _error("Memory system not initialized", "NOT_INITIALIZED", 503)

    guidance = _read_subconscious_json("guidance.json")
    if not guidance or not isinstance(guidance, dict):
        return _error("No guidance data", "NOT_FOUND", 404)

    items = guidance.get("items", [])
    if index < 0 or index >= len(items):
        return _error(
            f"Index {index} out of range (0-{len(items)-1})",
            "OUT_OF_RANGE",
            status=400,
        )

    removed = items.pop(index)
    guidance["items"] = items

    if _write_subconscious_json("guidance.json", guidance):
        return JSONResponse({
            "status": "ok",
            "removed": removed,
            "remaining": len(items),
        })
    return _error("Failed to write guidance", "WRITE_ERROR")


@dashboard_app.put("/api/memory/guidance/{index}")
async def api_memory_guidance_update(index: int, request: Request):
    """Update a guidance item's editable fields."""
    sub = _subconscious_dir()
    if not sub:
        return _error("Memory system not initialized", "NOT_INITIALIZED", 503)

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON", "INVALID_JSON", status=400)

    guidance = _read_subconscious_json("guidance.json")
    if not guidance or not isinstance(guidance, dict):
        return _error("No guidance data", "NOT_FOUND", 404)

    items = guidance.get("items", [])
    if index < 0 or index >= len(items):
        return _error(
            f"Index {index} out of range (0-{len(items)-1})",
            "OUT_OF_RANGE",
            status=400,
        )

    item = items[index]
    # Editable fields
    for field in ("text", "confidence", "pathway", "type"):
        if field in body:
            item[field] = body[field]
    items[index] = item
    guidance["items"] = items

    if _write_subconscious_json("guidance.json", guidance):
        return JSONResponse({"status": "ok", "item": item})
    return _error("Failed to write guidance", "WRITE_ERROR")


@dashboard_app.get("/api/memory/contradictions")
async def api_memory_contradictions():
    """List pending contradictions."""
    contradictions = _read_subconscious_json("pending_review.json") or []
    if isinstance(contradictions, dict):
        contradictions = contradictions.get("items", [])

    pending = [c for c in contradictions if c.get("status", "pending") == "pending"]
    return JSONResponse({
        "status": "ok",
        "contradictions": contradictions,
        "count": len(contradictions),
        "pending_count": len(pending),
    })


@dashboard_app.post("/api/memory/contradictions/{index}/resolve")
async def api_memory_contradiction_resolve(index: int, request: Request):
    """Resolve a contradiction: keep_a, keep_b, keep_both, dismiss."""
    sub = _subconscious_dir()
    if not sub:
        return _error("Memory system not initialized", "NOT_INITIALIZED", 503)

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON", "INVALID_JSON", status=400)

    action = body.get("action", "")
    if action not in ("keep_a", "keep_b", "keep_both", "dismiss"):
        return _error(
            "Invalid action. Must be: keep_a, keep_b, keep_both, dismiss",
            "INVALID_ACTION",
            status=400,
        )

    contradictions = _read_subconscious_json("pending_review.json") or []
    if isinstance(contradictions, dict):
        contradictions = contradictions.get("items", [])

    if index < 0 or index >= len(contradictions):
        return _error(
            f"Index {index} out of range",
            "OUT_OF_RANGE",
            status=400,
        )

    contradictions[index]["status"] = "resolved"
    contradictions[index]["resolution"] = action

    if _write_subconscious_json("pending_review.json", contradictions):
        return JSONResponse({
            "status": "ok",
            "resolution": action,
            "remaining_pending": sum(
                1 for c in contradictions
                if c.get("status", "pending") == "pending"
            ),
        })
    return _error("Failed to write contradictions", "WRITE_ERROR")


@dashboard_app.get("/api/memory/metacognition")
async def api_memory_metacognition():
    """Metacognition index status and summary."""
    sub = _subconscious_dir()
    if not sub:
        return JSONResponse({
            "status": "ok",
            "doc_count": 0,
            "categories": {},
            "index_size_bytes": 0,
            "last_built": None,
            "initialized": False,
        })

    meta_path = sub / "metacognition" / "metacognition_meta.json"
    vec_path = sub / "metacognition" / "metacognition_vectors.npy"

    doc_count = 0
    categories: dict[str, int] = {}
    index_size = 0
    last_built = None

    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            if isinstance(meta, list):
                doc_count = len(meta)
                for doc in meta:
                    cat = doc.get("category", "unknown")
                    categories[cat] = categories.get(cat, 0) + 1
            last_built = datetime.fromtimestamp(
                meta_path.stat().st_mtime, tz=timezone.utc
            ).isoformat()
        except Exception:
            pass

    if vec_path.exists():
        try:
            index_size = vec_path.stat().st_size
        except OSError:
            pass

    return JSONResponse({
        "status": "ok",
        "doc_count": doc_count,
        "categories": categories,
        "index_size_bytes": index_size,
        "last_built": last_built,
        "initialized": meta_path.exists(),
    })


@dashboard_app.post("/api/memory/metacognition/search")
async def api_memory_metacognition_search(request: Request):
    """Test metacognition retrieval for a query."""
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON", "INVALID_JSON", status=400)

    query = body.get("query", "").strip()
    if not query:
        return _error("Missing 'query' field", "BAD_REQUEST", status=400)

    try:
        from metacognition import test_retrieval
        result = await asyncio.to_thread(test_retrieval, query, verbose=True)
        return JSONResponse({"status": "ok", **result})
    except ImportError:
        return _error("Metacognition module not available", "NOT_AVAILABLE", 503)
    except Exception as e:
        _log.error(f"Metacognition search error: {e}")
        return _error(f"Search failed: {e}", "SEARCH_ERROR")


@dashboard_app.get("/api/memory/feedback")
async def api_memory_feedback():
    """Whisper feedback stats."""
    sub = _subconscious_dir()
    if not sub:
        return JSONResponse({
            "status": "ok",
            "items": [],
            "total_evaluations": 0,
            "initialized": False,
        })

    fb_index_path = sub / "whisper_feedback" / "index.json"
    if not fb_index_path.exists():
        return JSONResponse({
            "status": "ok",
            "items": [],
            "total_evaluations": 0,
            "initialized": True,
        })

    try:
        fb = json.loads(fb_index_path.read_text())
        items_raw = fb.get("items", {})
        total = fb.get("total_evaluations", 0)

        items = []
        for hash_key, info in items_raw.items():
            items.append({
                "hash": hash_key,
                "injection_count": info.get("injection_count", 0),
                "useful_count": info.get("useful_count", 0),
                "hit_rate": round(info.get("hit_rate", 0.0), 3),
                "last_evaluated": info.get("last_evaluated", ""),
                "text_preview": info.get("text_preview", "")[:120],
            })

        items.sort(key=lambda x: x["injection_count"], reverse=True)
        return JSONResponse({
            "status": "ok",
            "items": items,
            "total_evaluations": total,
            "initialized": True,
        })
    except Exception as e:
        _log.error(f"Feedback read error: {e}")
        return _error(f"Failed to read feedback: {e}", "READ_ERROR")


@dashboard_app.post("/api/memory/operations/{action}")
async def api_memory_operations(action: str):
    """Trigger memory operations: rebuild_index, run_consolidation, promotion_dryrun."""
    valid_actions = ("rebuild_index", "run_consolidation", "promotion_dryrun")
    if action not in valid_actions:
        return _error(
            f"Invalid action. Must be one of: {', '.join(valid_actions)}",
            "INVALID_ACTION",
            status=400,
        )

    # Find scripts directory
    scripts_dir: Path | None = None
    for p in env.get_runtime_workspace_paths_list():
        candidate = Path(p) / "scripts" / "subconscious"
        if candidate.is_dir():
            scripts_dir = candidate
            break
    if not scripts_dir:
        # Also check inside the apex repo
        apex_root = env.APEX_ROOT
        candidate = apex_root / "scripts" / "subconscious"
        if candidate.is_dir():
            scripts_dir = candidate

    if not scripts_dir:
        return _error(
            "Subconscious scripts directory not found",
            "NOT_FOUND",
            status=404,
        )

    script_map = {
        "rebuild_index": ("build_index.py", ["build", "--force"], 300),
        "run_consolidation": ("autodream.py", ["--dry-run"], 120),
        "promotion_dryrun": (None, [], 0),  # handled inline
    }

    if action == "promotion_dryrun":
        # Read feedback index and find promotion candidates
        sub = _subconscious_dir()
        if not sub:
            return JSONResponse({
                "status": "ok",
                "action": action,
                "output": "No subconscious directory found.",
                "candidates": [],
            })

        fb_path = sub / "whisper_feedback" / "index.json"
        if not fb_path.exists():
            return JSONResponse({
                "status": "ok",
                "action": action,
                "output": "No feedback index. Need more sessions for data.",
                "candidates": [],
            })

        try:
            fb = json.loads(fb_path.read_text())
            items = fb.get("items", {})
            candidates = []
            for hash_key, info in items.items():
                inj = info.get("injection_count", 0)
                hit = info.get("hit_rate", 0.0)
                if inj >= 20 and hit >= 0.60:
                    candidates.append({
                        "hash": hash_key,
                        "injection_count": inj,
                        "hit_rate": round(hit, 3),
                        "text_preview": info.get("text_preview", "")[:200],
                    })

            output = (
                f"Found {len(candidates)} promotion candidate(s) "
                f"(min injections: 20, min hit rate: 60%)"
            )
            return JSONResponse({
                "status": "ok",
                "action": action,
                "output": output,
                "candidates": candidates,
            })
        except Exception as e:
            return _error(f"Failed to analyze: {e}", "ANALYSIS_ERROR")

    # Run script as subprocess
    script_name, args, timeout = script_map[action]
    script_path = scripts_dir / script_name
    if not script_path.exists():
        return _error(
            f"Script not found: {script_name}",
            "SCRIPT_NOT_FOUND",
            status=404,
        )

    def _run_script():
        result = subprocess.run(
            [sys.executable, str(script_path)] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(scripts_dir),
        )
        return result.stdout + result.stderr

    try:
        output = await asyncio.to_thread(_run_script)
        return JSONResponse({
            "status": "ok",
            "action": action,
            "output": output[-4000:] if len(output) > 4000 else output,
        })
    except subprocess.TimeoutExpired:
        return _error(
            f"Operation timed out after {timeout}s",
            "TIMEOUT",
            status=504,
        )
    except Exception as e:
        _log.error(f"Memory operation {action} failed: {e}")
        return _error(f"Operation failed: {e}", "OPERATION_ERROR")


# GET /api/memory/backends — discover available embedding/model backends
@dashboard_app.get("/api/memory/backends")
async def api_memory_backends():
    """Return available backends and models for memory config dropdowns."""
    # --- Gemini ---
    gemini_available = False
    env_text = ""
    try:
        env_text = ENV_PATH.read_text()
    except FileNotFoundError:
        pass
    for line in env_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("GOOGLE_API_KEY=") and len(stripped) > 16:
            gemini_available = True
            break
    if not gemini_available and os.environ.get("GOOGLE_API_KEY"):
        gemini_available = True

    # --- Ollama ---
    ollama_url = "http://localhost:11434"
    if _config:
        ollama_url = _config.get("models", "ollama_url") or ollama_url
    ollama_info = _ping_ollama(ollama_url)
    ollama_available = ollama_info.get("status") == "reachable"
    ollama_models = ollama_info.get("models", [])

    # Resolve the specific embedding model names
    gemini_embed_model = "gemini-embedding-2-preview"
    ollama_embed_model = os.environ.get("APEX_OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # Build embedding backend choices (only available ones)
    embedding_choices = []
    if gemini_available:
        embedding_choices.append({
            "value": "gemini",
            "label": f"Gemini — {gemini_embed_model}",
            "available": True,
        })
    else:
        embedding_choices.append({
            "value": "gemini",
            "label": f"Gemini — not configured (needs GOOGLE_API_KEY)",
            "available": False,
        })
    if ollama_available:
        # Check if the embedding model is actually pulled
        embed_installed = ollama_embed_model in ollama_models or f"{ollama_embed_model}:latest" in ollama_models
        suffix = "" if embed_installed else " (not installed)"
        embedding_choices.append({
            "value": "ollama",
            "label": f"Ollama — {ollama_embed_model}{suffix}",
            "available": True,
        })
    else:
        embedding_choices.append({
            "value": "ollama",
            "label": f"Ollama — not reachable",
            "available": False,
        })

    return JSONResponse({
        "gemini_available": gemini_available,
        "ollama_available": ollama_available,
        "ollama_url": ollama_url,
        "ollama_models": ollama_models,
        "embedding_choices": embedding_choices,
    })


# ---------------------------------------------------------------------------
# Memory extraction schedule — crontab management
# ---------------------------------------------------------------------------

# Canonical pipeline jobs. The "pattern" matches existing crontab lines.
# "script" + "args" are used to CREATE new entries when none exist.
# Scripts are resolved relative to the subconscious scripts directory.
_MEMORY_PIPELINE_JOBS = [
    {
        "key": "db_snapshot",
        "label": "DB Snapshot",
        "description": "Safe backup of database before mining",
        "pattern": "db_snapshot.sh",
        "script": "db_snapshot.sh",
        "args": [],
        "default_hour": 22, "default_minute": 50,
    },
    {
        "key": "chatmine",
        "label": "Chatmine (extraction)",
        "description": "Extract knowledge from conversation transcripts",
        "pattern": "run_chatmine.sh",
        "script": "run_chatmine.sh",
        "args": [],
        "default_hour": 23, "default_minute": 0,
    },
    {
        "key": "batch_digest",
        "label": "Batch Digest",
        "description": "Catch-all session digestion into guidance",
        "pattern": "batch_digest.py",
        "script": "batch_digest.py",
        "args": ["--days", "3"],
        "default_hour": 2, "default_minute": 30,
    },
    {
        "key": "autodream",
        "label": "Autodream (consolidation)",
        "description": "Nightly memory consolidation and pruning",
        "pattern": "run_autodream.sh",
        "script": "run_autodream.sh",
        "args": [],
        "default_hour": 3, "default_minute": 0,
    },
]


def _find_scripts_dir() -> Path | None:
    """Find the subconscious scripts directory."""
    for p in env.get_runtime_workspace_paths_list():
        candidate = Path(p) / "scripts" / "subconscious"
        if candidate.is_dir():
            return candidate
    candidate = env.APEX_ROOT / "scripts" / "subconscious"
    if candidate.is_dir():
        return candidate
    return None


def _read_crontab() -> str:
    """Read current user crontab, returning empty string on error."""
    try:
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, timeout=5,
        )
        return result.stdout if result.returncode == 0 else ""
    except Exception:
        return ""


def _parse_memory_schedule() -> tuple[list[dict], str]:
    """Parse crontab and build schedule status for each pipeline job."""
    raw = _read_crontab()
    scripts_dir = _find_scripts_dir()

    jobs = []
    for spec in _MEMORY_PIPELINE_JOBS:
        # Check if the script actually exists in this install
        script_exists = False
        if scripts_dir:
            script_exists = (scripts_dir / spec["script"]).exists()

        # Find ALL crontab lines matching this job's pattern (may be multiple)
        entries = []
        for line in raw.splitlines():
            stripped = line.strip()
            # Skip pure comment lines (prose descriptions mentioning scripts)
            if stripped.startswith("#"):
                # Only match if the comment contains an actual cron schedule
                # (i.e., uncommented form starts with a number)
                bare = stripped.lstrip("#").strip()
                if not bare or not bare[0].isdigit():
                    continue
            else:
                bare = stripped
            if spec["pattern"] in bare:
                is_active = not stripped.startswith("#")
                parts = bare.split(None, 5)
                if len(parts) >= 6:
                    # Extract variant suffix from command (e.g., "prod", "dev")
                    cmd = parts[5]
                    variant = ""
                    for token in cmd.split():
                        if token in ("prod", "dev", "claude", "codex"):
                            variant = token
                    entries.append({
                        "enabled": is_active,
                        "hour": parts[1],
                        "minute": parts[0],
                        "variant": variant,
                        "cron_line": bare,
                    })

        if entries:
            # Group into one job per variant
            for entry in entries:
                suffix = f" ({entry['variant']})" if entry["variant"] else ""
                jobs.append({
                    "key": spec["key"] + ("_" + entry["variant"] if entry["variant"] else ""),
                    "label": spec["label"] + suffix,
                    "description": spec["description"],
                    "enabled": entry["enabled"],
                    "hour": entry["hour"],
                    "minute": entry["minute"],
                    "installed": True,
                    "script_exists": script_exists,
                    "cron_line": entry["cron_line"],
                })
        else:
            # No crontab entry — show as not installed (available to create)
            jobs.append({
                "key": spec["key"],
                "label": spec["label"],
                "description": spec["description"],
                "enabled": False,
                "hour": str(spec["default_hour"]),
                "minute": str(spec["default_minute"]),
                "installed": False,
                "script_exists": script_exists,
                "cron_line": "",
            })

    return jobs, raw


@dashboard_app.get("/api/memory/schedule")
async def api_memory_schedule():
    """Return current extraction schedule from crontab."""
    jobs, _ = _parse_memory_schedule()
    return JSONResponse({"jobs": jobs})


@dashboard_app.put("/api/memory/schedule")
async def api_memory_schedule_update(request: Request):
    """Update extraction schedule in crontab."""
    body = await request.json()
    updates = body.get("jobs", {})
    if not updates:
        return _error("No updates provided", "EMPTY_UPDATE", status=400)

    raw = _read_crontab()
    scripts_dir = _find_scripts_dir()
    lines = raw.splitlines()
    new_lines = []
    handled_keys: set[str] = set()

    # Phase 1: Update existing lines
    for line in lines:
        stripped = line.strip()
        bare = stripped.lstrip("#").strip()

        matched_spec = None
        matched_key = None
        for spec in _MEMORY_PIPELINE_JOBS:
            if spec["pattern"] in bare:
                # Determine variant
                variant = ""
                for token in bare.split():
                    if token in ("prod", "dev", "claude", "codex"):
                        variant = token
                matched_spec = spec
                matched_key = spec["key"] + ("_" + variant if variant else "")
                break

        if matched_spec and matched_key in updates:
            update = updates[matched_key]
            handled_keys.add(matched_key)
            parts = bare.split(None, 5)
            if len(parts) >= 6:
                new_min = str(update.get("minute", parts[0]))
                new_hour = str(update.get("hour", parts[1]))
                new_cron = f"{new_min} {new_hour} {parts[2]} {parts[3]} {parts[4]} {parts[5]}"
                if update.get("enabled", True):
                    new_lines.append(new_cron)
                else:
                    new_lines.append(f"# {new_cron}")
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Phase 2: Create new entries for jobs that don't exist yet
    for key, update in updates.items():
        if key in handled_keys:
            continue
        if not update.get("enabled", False):
            continue
        # Find the matching spec
        base_key = key.split("_")[0] if "_" in key else key
        spec = next((s for s in _MEMORY_PIPELINE_JOBS if s["key"] == base_key), None)
        if not spec or not scripts_dir:
            continue
        script_path = scripts_dir / spec["script"]
        if not script_path.exists():
            continue
        hour = str(update.get("hour", spec["default_hour"]))
        minute = str(update.get("minute", spec["default_minute"]))
        if spec["script"].endswith(".py"):
            cmd = f"{sys.executable} {script_path}"
            if spec["args"]:
                cmd += " " + " ".join(spec["args"])
        else:
            cmd = f"/bin/bash {script_path}"
            if spec["args"]:
                cmd += " " + " ".join(spec["args"])
        new_lines.append("")
        new_lines.append(f"# Apex memory — {spec['label']}")
        new_lines.append(f"{minute} {hour} * * * {cmd}")

    new_crontab = "\n".join(new_lines)
    if not new_crontab.endswith("\n"):
        new_crontab += "\n"

    try:
        result = subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return _error(
                f"crontab update failed: {result.stderr}",
                "CRONTAB_ERROR",
            )
    except Exception as e:
        return _error(f"Failed to update crontab: {e}", "CRONTAB_ERROR")

    jobs, _ = _parse_memory_schedule()
    return JSONResponse({"status": "ok", "jobs": jobs})


# PUT /api/config/memory — route through standard config updater
@dashboard_app.put("/api/config/memory")
async def api_config_update_memory(request: Request):
    """Update memory configuration."""
    return await _update_config_section("memory", request)


# ---------------------------------------------------------------------------
# Catch-all — must remain last
# ---------------------------------------------------------------------------

@dashboard_app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def api_not_found(path: str):
    """Return a structured error for unknown API paths."""
    return _error(
        f"Unknown endpoint: /admin/api/{path}",
        "NOT_FOUND",
        status=404,
    )
