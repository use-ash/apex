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
    GET    /api/workspace/claude-md                 — Read CLAUDE.md content
    PUT    /api/workspace/claude-md                 — Update CLAUDE.md (backup first)
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
import glob as _glob_mod
import html
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.responses import StreamingResponse

from config import Config, SCHEMA

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


@dashboard_app.middleware("http")
async def csrf_protection(request: Request, call_next):
    """Require X-Requested-With header on state-changing requests."""
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
        _log.warning(f"Config update unknown section: {e}")
        return _error("Unknown configuration section", "UNKNOWN_SECTION", status=400)
    except ValueError as e:
        _log.warning(f"Config validation error: {e}")
        return _error("Invalid configuration value", "VALIDATION_ERROR", status=422)
    except Exception as e:
        _log.error(f"Config update failed: {e}")
        return _error("Configuration update failed", "CONFIG_WRITE_ERROR")


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

    srv_path = _ssl_dir / "localchat.crt"
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
        if name in ("ca", "localchat"):
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
             "-CAkey", str(ca_key),
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

        # 5. Clean up CSR
        csr_path.unlink(missing_ok=True)

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

    key_path = _ssl_dir / "localchat.key"
    csr_path = _ssl_dir / "localchat.csr"
    crt_path = _ssl_dir / "localchat.crt"

    steps = [
        # 1. Generate new server key
        ["openssl", "genrsa", "-out", str(key_path), "2048"],
        # 2. Generate CSR
        ["openssl", "req", "-new",
         "-key", str(key_path),
         "-out", str(csr_path),
         "-subj", "/CN=localchat"],
        # 3. Sign with CA using ext.cnf for SANs
        ["openssl", "x509", "-req",
         "-in", str(csr_path),
         "-CA", str(ca_crt),
         "-CAkey", str(ca_key),
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

    # Clean up CSR
    csr_path.unlink(missing_ok=True)

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
    ['IP:10.8.0.2', 'DNS:localhost']."""
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
                # e.g. "IP.1 = 10.8.0.2" or "DNS.1 = localhost"
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

    # Validate each SAN entry
    san_re = re.compile(r"^(IP|DNS):.+$")
    for entry in raw_sans:
        if not isinstance(entry, str) or not san_re.match(entry):
            return _error(
                f"Invalid SAN entry: '{entry}' — must be 'IP:...' or 'DNS:...'",
                "INVALID_SAN_ENTRY",
                status=400,
            )

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
        "CN = localchat\n"
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

ENV_PATH = Path.home() / ".openclaw" / ".env"

_PROVIDER_KEY_MAP: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "telegram_bot": "TELEGRAM_BOT_TOKEN",
    "telegram_chat": "TELEGRAM_CHAT_ID",
}


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
        import localchat as _lc
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

    status = "configured" if (env_set or keychain_set) else "not_configured"

    resp: dict[str, Any] = {
        "status": status,
        "env_var_set": env_set,
        "keychain_set": keychain_set,
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
            "telegram_bot": _env_has_key("TELEGRAM_BOT_TOKEN"),
            "telegram_chat": _env_has_key("TELEGRAM_CHAT_ID"),
            "alert_token": _env_has_key("LOCALCHAT_ALERT_TOKEN"),
        },
    })


# ---------------------------------------------------------------------------
# PUT /api/credentials/{provider} — Set API key in .env
# ---------------------------------------------------------------------------

@dashboard_app.put("/api/credentials/{provider}")
async def api_credentials_update(provider: str, request: Request):
    """Set an API key/token in ~/.openclaw/.env (atomic write).

    Providers: anthropic, xai, telegram_bot, telegram_chat.
    Body: {"key": "sk-..."}
    """
    if provider not in _PROVIDER_KEY_MAP:
        return _error(
            f"Unknown provider: '{provider}'. "
            f"Valid: {', '.join(sorted(_PROVIDER_KEY_MAP))}",
            "UNKNOWN_PROVIDER",
            status=400,
        )

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON in request body", "INVALID_JSON", status=400)

    key_value = body.get("key", "") if isinstance(body, dict) else ""
    if not key_value or not isinstance(key_value, str):
        return _error("'key' field is required", "MISSING_KEY", status=400)

    env_var_name = _PROVIDER_KEY_MAP[provider]

    try:
        _update_env_var(env_var_name, key_value)
    except Exception as e:
        _log.error(f"Failed to update .env: {e}")
        return _error("Failed to update credentials file", "ENV_WRITE_ERROR")

    # Also update the current process environment
    os.environ[env_var_name] = key_value

    return JSONResponse({
        "status": "ok",
        "provider": provider,
        "env_var": env_var_name,
        "message": f"{env_var_name} updated in .env",
    })


# ---------------------------------------------------------------------------
# POST /api/credentials/alert-token/rotate — Generate new alert token
# ---------------------------------------------------------------------------

@dashboard_app.post("/api/credentials/alert-token/rotate")
async def api_credentials_alert_token_rotate():
    """Generate a new random alert token (32 bytes, base64url).

    Updates LOCALCHAT_ALERT_TOKEN in .env and the running config.
    Returns the new token (only time it is exposed).
    """
    import secrets
    import base64

    token_bytes = secrets.token_bytes(32)
    new_token = base64.urlsafe_b64encode(token_bytes).decode().rstrip("=")

    try:
        _update_env_var("LOCALCHAT_ALERT_TOKEN", new_token)
    except Exception as e:
        _log.error(f"Failed to update .env: {e}")
        return _error("Failed to update credentials file", "ENV_WRITE_ERROR")

    os.environ["LOCALCHAT_ALERT_TOKEN"] = new_token

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
    alert_token_set = _env_has_key("LOCALCHAT_ALERT_TOKEN")

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
    """Fire a test alert: insert into DB and send via Telegram.

    Returns the result of each channel.
    """
    results: dict[str, Any] = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Insert test alert into DB
    db_ok = False
    if _db_path and _db_path.exists():
        try:
            conn = sqlite3.connect(str(_db_path), check_same_thread=False)
            conn.execute(
                "INSERT INTO alerts (category, title, body, severity, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    "test",
                    "Test Alert",
                    f"Dashboard test alert fired at {now_iso}",
                    "info",
                    now_iso,
                ),
            )
            conn.commit()
            conn.close()
            db_ok = True
        except sqlite3.Error as e:
            _log.error(f"Test alert DB error: {e}")
            results["db"] = {"status": "error", "detail": "Database write failed"}

    if db_ok:
        results["db"] = {"status": "ok", "detail": "Test alert inserted"}
    elif "db" not in results:
        results["db"] = {"status": "error", "detail": "Database not available"}

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
                "text": f"🔔 Apex Dashboard Test Alert\n\n"
                        f"This is a test alert from the Apex Dashboard.\n"
                        f"Time: {now_iso}",
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

    # Overall
    all_ok = all(r.get("status") == "ok" for r in results.values())

    return JSONResponse({
        "status": "ok" if all_ok else "partial",
        "results": results,
        "fired_at": now_iso,
    })


# ===========================================================================
# Phase 4 — Workspace, Skills, Guardrails, Sessions
# ===========================================================================

WORKSPACE = Path(os.environ.get("LOCALCHAT_WORKSPACE", os.getcwd()))


# ---------------------------------------------------------------------------
# GET /api/workspace — Workspace summary
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/workspace")
async def api_workspace():
    """Workspace overview: path, CLAUDE.md exists, memory count, skills count."""
    claude_md = WORKSPACE / "CLAUDE.md"
    memory_dir = WORKSPACE / "memory"
    skills_dir = WORKSPACE / "skills"

    memory_count = len(list(memory_dir.glob("*.md"))) if memory_dir.is_dir() else 0
    skills_count = len(
        _glob_mod.glob(str(skills_dir / "*" / "SKILL.md"))
    ) if skills_dir.is_dir() else 0

    return JSONResponse({
        "workspace": str(WORKSPACE),
        "claude_md_exists": claude_md.exists(),
        "memory_file_count": memory_count,
        "skills_count": skills_count,
    })


# ---------------------------------------------------------------------------
# GET /api/workspace/claude-md — Read CLAUDE.md
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/workspace/claude-md")
async def api_workspace_claude_md_get():
    """Return the contents of CLAUDE.md."""
    claude_md = WORKSPACE / "CLAUDE.md"
    if not claude_md.exists():
        return _error("CLAUDE.md not found", "NOT_FOUND", status=404)
    try:
        content = claude_md.read_text(encoding="utf-8")
    except Exception as e:
        _log.error(f"Failed to read CLAUDE.md: {e}")
        return _error("Failed to read CLAUDE.md", "READ_ERROR")
    return JSONResponse({
        "content": content,
        "size_bytes": claude_md.stat().st_size,
    })


# ---------------------------------------------------------------------------
# PUT /api/workspace/claude-md — Update CLAUDE.md (backup first)
# ---------------------------------------------------------------------------

@dashboard_app.put("/api/workspace/claude-md")
async def api_workspace_claude_md_put(request: Request):
    """Write CLAUDE.md after backing up to CLAUDE.md.bak."""
    body = await request.json()
    content = body.get("content")
    if content is None:
        return _error("Missing 'content' field", "BAD_REQUEST", status=400)

    claude_md = WORKSPACE / "CLAUDE.md"
    bak = WORKSPACE / "CLAUDE.md.bak"

    try:
        if claude_md.exists():
            shutil.copy2(str(claude_md), str(bak))
        claude_md.write_text(content, encoding="utf-8")
    except Exception as e:
        _log.error(f"Failed to write CLAUDE.md: {e}")
        return _error("Failed to write CLAUDE.md", "WRITE_ERROR")

    return JSONResponse({
        "status": "ok",
        "message": "CLAUDE.md updated (backup saved to CLAUDE.md.bak)",
        "size_bytes": claude_md.stat().st_size,
    })


# ---------------------------------------------------------------------------
# GET /api/workspace/memory — List memory files
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/workspace/memory")
async def api_workspace_memory():
    """List all memory/*.md files with name, size, and modified time."""
    memory_dir = WORKSPACE / "memory"
    if not memory_dir.is_dir():
        return JSONResponse({"files": []})

    files = []
    for p in sorted(memory_dir.glob("*.md")):
        st = p.stat()
        files.append({
            "name": p.name,
            "size_bytes": st.st_size,
            "modified": datetime.fromtimestamp(
                st.st_mtime, tz=timezone.utc
            ).isoformat(),
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

    memory_dir = WORKSPACE / "memory"
    path = memory_dir / name
    # Prevent path traversal
    try:
        path.resolve().relative_to(memory_dir.resolve())
    except ValueError:
        return _error("Invalid memory file path", "PATH_TRAVERSAL", 400)

    if not path.exists():
        return _error(f"Memory file '{name}' not found", "NOT_FOUND", 404)

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

    memory_dir = WORKSPACE / "memory"
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
    """List installed skills by scanning skills/*/SKILL.md."""
    skills_dir = WORKSPACE / "skills"
    if not skills_dir.is_dir():
        return JSONResponse({"skills": [], "count": 0})

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
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        info = _parse_skill_frontmatter(skill_md)
        dir_name = skill_md.parent.name
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
        import localchat as lc
        result = await lc._maybe_compact_chat(chat_id)
    except AttributeError:
        return _error(
            "_maybe_compact_chat not available in localchat module",
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
        import localchat as lc
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
    r"^\[localchat\s+(\d{2}:\d{2}:\d{2})\]\s*(\w+)?\s*(.*)",
)


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
    """Parse a localchat log line into {timestamp, level, message}."""
    m = _LOG_LINE_RE.match(line)
    if m:
        return {
            "timestamp": m.group(1),
            "level": m.group(2) or "INFO",
            "message": m.group(3).strip(),
        }
    return {"timestamp": "", "level": "", "message": line}


# ---------------------------------------------------------------------------
# GET /api/logs — Read log lines
# ---------------------------------------------------------------------------

@dashboard_app.get("/api/logs")
async def api_logs(lines: int = 100, search: str = "", level: str = ""):
    """Read last N log lines with optional search/level filter."""
    if _state_dir is None:
        return _not_initialized()

    log_path = _state_dir / "localchat.log"
    if not log_path.exists():
        return JSONResponse({"lines": [], "total": 0, "file_exists": False})

    n = max(1, min(lines, 1000))
    raw_lines = _tail_lines(log_path, n)

    parsed = [_parse_log_line(l) for l in raw_lines if l.strip()]

    if level:
        level_upper = level.upper()
        parsed = [p for p in parsed if p["level"].upper() == level_upper]

    if search:
        try:
            pat = re.compile(search, re.IGNORECASE)
            parsed = [p for p in parsed if pat.search(p["message"])]
        except re.error:
            search_lower = search.lower()
            parsed = [p for p in parsed if search_lower in p["message"].lower()]

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

    log_path = _state_dir / "localchat.log"

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
    """Rotate: rename localchat.log -> localchat.log.1, create fresh log."""
    if _state_dir is None:
        return _not_initialized()

    log_path = _state_dir / "localchat.log"
    backup_path = _state_dir / "localchat.log.1"

    if not log_path.exists():
        return JSONResponse({"status": "ok", "detail": "No log file to rotate"})

    try:
        old_size = log_path.stat().st_size
        shutil.move(str(log_path), str(backup_path))
        log_path.touch()
        return JSONResponse({
            "status": "ok",
            "rotated_size": old_size,
            "detail": f"Rotated {old_size} bytes to localchat.log.1",
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

    days = max(1, days)

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

_BACKUP_FILES = ["localchat.db", "config.json", "guardrail_whitelist.json"]


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
                        if item.is_file():
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
        if not any(n in extracted_names for n in ("localchat.db", "config.json")):
            return _error(
                "Archive does not contain localchat.db or config.json",
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

        return JSONResponse({
            "status": "ok",
            "restored_files": restored,
            "restart_required": True,
            "detail": "Backup restored. Server restart required for changes to take effect.",
        })

    except (tarfile.TarError, OSError) as e:
        _log.error(f"Restore failed: {e}")
        return _error("Backup restore failed", "RESTORE_FAILED")
    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(str(tmp_dir), ignore_errors=True)


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
