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
    GET    /api/tls/sans              — Current SAN list from ext.cnf
    PUT    /api/tls/sans              — Update SANs in ext.cnf
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
from fastapi.responses import HTMLResponse, JSONResponse, Response

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

    # Check for existing cert with same CN
    if (_ssl_dir / f"{cn}.crt").exists():
        return _error(
            f"Client certificate '{cn}' already exists",
            "CN_EXISTS",
            status=409,
        )

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
         "-passout", "pass:localchat"],
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
                return _error(
                    f"openssl failed: {result.stderr.strip()}",
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
    base = str(request.base_url).rstrip("/")
    download_url = f"{base}/admin/api/tls/clients/{cn}/p12"

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

        html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>QR — {cn}</title>"
            "<style>body{{background:#111;color:#eee;font-family:system-ui;"
            "display:flex;flex-direction:column;align-items:center;padding:2em}}"
            "svg{{background:white;padding:1em;border-radius:8px;max-width:300px}}"
            "a{{color:#6cf;word-break:break-all}}</style></head><body>"
            f"<h2>Client cert: {cn}</h2>"
            f"{svg_str}"
            f"<p style='margin-top:1em'>Or copy: <a href='{download_url}'>"
            f"{download_url}</a></p>"
            f"<p>Install password: <code>localchat</code></p>"
            "</body></html>"
        )
        return HTMLResponse(html)

    except ImportError:
        # Fallback: URL card without QR
        html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>Download — {cn}</title>"
            "<style>body{background:#111;color:#eee;font-family:system-ui;"
            "display:flex;flex-direction:column;align-items:center;padding:2em}"
            ".card{background:#222;padding:2em;border-radius:12px;max-width:500px;"
            "text-align:center;border:1px solid #444}"
            "a{color:#6cf;font-size:1.1em;word-break:break-all}"
            "code{background:#333;padding:2px 8px;border-radius:4px}</style></head>"
            "<body><div class='card'>"
            f"<h2>Client cert: {cn}</h2>"
            f"<p>Download URL:</p>"
            f"<p><a href='{download_url}'>{download_url}</a></p>"
            f"<p style='margin-top:1em'>Install password: <code>localchat</code></p>"
            "<p style='color:#888;font-size:0.85em;margin-top:1em'>"
            "QR code unavailable — install <code>qrcode</code> package for SVG QR.</p>"
            "</div></body></html>"
        )
        return HTMLResponse(html)


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
                return _error(
                    f"openssl failed: {result.stderr.strip()}",
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
