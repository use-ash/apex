"""Apex Dashboard — FastAPI sub-app for server management.

Phase 1: Foundation + Health Dashboard.
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
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from config import Config, SCHEMA

# ---------------------------------------------------------------------------
# Module state — set by init_dashboard() at server startup
# ---------------------------------------------------------------------------

_start_time: float = time.time()

_state_dir: Path | None = None
_db_path: Path | None = None
_ssl_dir: Path | None = None
_config: Config | None = None


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
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)


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


# ---------------------------------------------------------------------------
# GET / — Dashboard HTML
# ---------------------------------------------------------------------------

@dashboard_app.get("/", response_class=HTMLResponse)
async def dashboard_index():
    """Serve the Apex Dashboard single-page app."""
    try:
        from dashboard_html import DASHBOARD_HTML
        return HTMLResponse(DASHBOARD_HTML)
    except ImportError:
        return HTMLResponse(
            "<html><body style='background:#111;color:#eee;font-family:system-ui;'>"
            "<h1>Apex Dashboard</h1>"
            "<p>dashboard_html.py not found. API endpoints are available at /admin/api/</p>"
            "</body></html>",
            status_code=200,
        )


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
        import localchat as _lc
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
        return _error(f"Database error: {e}", "DB_ERROR")


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

@dashboard_app.get("/api/status/tls")
async def api_status_tls():
    """TLS certificate expiry dates, days remaining, and warnings."""
    if _ssl_dir is None:
        return _not_initialized()

    if not _ssl_dir.exists():
        return _error("SSL directory not found", "SSL_DIR_NOT_FOUND", 404)

    certs = {
        "ca": _ssl_dir / "ca.crt",
        "server": _ssl_dir / "localchat.crt",
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

    return JSONResponse({
        "status": overall,
        "certificates": results,
        "warnings": warnings,
    })


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

    # Claude — check for API key
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        results["claude"] = {
            "status": "configured",
            "detail": "ANTHROPIC_API_KEY is set",
        }
    else:
        results["claude"] = {
            "status": "not_configured",
            "detail": "ANTHROPIC_API_KEY not found in environment",
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


def _ping_ollama(base_url: str) -> dict[str, Any]:
    """Ping Ollama /api/tags and return status + available models."""
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
        return {
            "status": "unreachable",
            "url": base_url,
            "detail": f"Connection failed: {e.reason}",
        }
    except Exception as e:
        return {
            "status": "unreachable",
            "url": base_url,
            "detail": str(e),
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
        return _error(f"Config read error: {e}", "CONFIG_READ_ERROR")


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
    """Update workspace configuration (path, whisper, etc)."""
    return await _update_config_section("workspace", request)


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
        return _error(str(e), "UNKNOWN_SECTION", status=400)
    except ValueError as e:
        return _error(str(e), "VALIDATION_ERROR", status=422)
    except Exception as e:
        return _error(f"Config update failed: {e}", "CONFIG_WRITE_ERROR")


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


# ---------------------------------------------------------------------------
# Catch-all for unknown API routes
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
