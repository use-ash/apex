#!/usr/bin/env python3
"""Apex — Local web chat for Claude Code.

Zero third-party data flow. FastAPI + WebSocket + Claude Agent SDK.
All conversation data stays on this machine. Persistent sessions — no
subprocess respawning per turn. Auth via mTLS (client certificate).

Usage:
    python3 apex.py
    # or via setup wizard: python3 setup_apex.py

Env vars:
    APEX_SSL_CERT            — server certificate
    APEX_SSL_KEY             — server private key
    APEX_SSL_CA              — CA cert for client verification (mTLS)
    APEX_HOST                — bind address (default: 0.0.0.0)
    APEX_PORT                — port (default: 8300)
    APEX_MODEL               — Claude model (default: claude-sonnet-4-6)
    APEX_WORKSPACE           — working directory for Claude SDK (default: cwd)
    APEX_PERMISSION_MODE     — SDK permission mode (default: acceptEdits)
    APEX_DEBUG               — enable verbose debug logging (default: false)
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import os
import ssl
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, RedirectResponse
    import uvicorn
except ImportError:
    print("pip install fastapi uvicorn python-multipart", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Internal module imports
# ---------------------------------------------------------------------------
from config import Config as ApexConfig
from dashboard import dashboard_app, init_dashboard
from license import get_license_manager
from log import log, LOG_PATH, LOG_MAX
from db import (
    DB_PATH, _get_db, _init_db, _seed_default_profiles, seed_system_personas,
    _get_recent_messages_text, _get_recently_active_chats,
)
from state import (
    _recovery_pending,
    _session_context_sent,
    _clients, _rate_buckets, _db_lock,
)

# Phase 1+2 extracted route modules
from routes_misc import misc_router
from routes_profiles import profiles_router
from routes_alerts import alerts_router
from routes_models import models_router
from routes_upload import upload_router
from routes_chat import chat_router
from routes_tasks import tasks_router
from routes_setup import setup_router

# Phase 3+4 extracted modules
from streaming import _disconnect_client
from context import _generate_recovery_context, _store_recovery_context
import context as _context_mod
from ws_handler import ws_router
import ws_handler as _ws_handler_mod
import env
from premium_loader import PremiumLoader
from mtls import has_verified_peer_cert, mtls_required

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HOST = env.HOST
PORT = env.PORT
SSL_CERT = env.SSL_CERT
SSL_KEY = env.SSL_KEY
SSL_CA = env.SSL_CA
APEX_ROOT = env.APEX_ROOT
WORKSPACE = env.WORKSPACE


def _read_version() -> str:
    version_file = APEX_ROOT / "VERSION"
    try:
        version = version_file.read_text().strip()
        return version or "dev"
    except Exception:
        return "dev"


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(APEX_ROOT), *args],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return ""


APP_VERSION = _read_version()
APP_BRANCH = _git_output("branch", "--show-current") or "unknown"
APP_COMMIT = _git_output("rev-parse", "--short", "HEAD") or "unknown"
APP_BUILD = f"v{APP_VERSION} • {APP_BRANCH} • {APP_COMMIT}"

MODEL = env.MODEL
PERMISSION_MODE = env.PERMISSION_MODE
DEBUG = env.DEBUG


class _Secret(str):
    """String subclass that redacts its value in repr/logging."""
    def __repr__(self) -> str:
        return "'***'" if self else "''"
    def __str_for_log__(self) -> str:
        return "***" if self else ""


GROUPS_ENABLED = env.GROUPS_ENABLED
ENABLE_SKILL_DISPATCH = env.ENABLE_SKILL_DISPATCH

# --- Licensing ---
_license_mgr = get_license_manager()

# Migration: rename localchat.db → apex.db
_old_db = DB_PATH.parent / "localchat.db"
if not DB_PATH.exists() and _old_db.exists():
    _old_db.rename(DB_PATH)

# Migration: rename localchat.log → apex.log
_old_log = LOG_PATH.parent / "localchat.log"
if not LOG_PATH.exists() and _old_log.exists():
    _old_log.rename(LOG_PATH)

UPLOAD_DIR = APEX_ROOT / "state" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
os.chmod(UPLOAD_DIR, 0o700)

SDK_QUERY_TIMEOUT = env.SDK_QUERY_TIMEOUT

# ---------------------------------------------------------------------------
# Premium module loading — must happen before app.include_router() so
# dynamically registered routes are picked up by FastAPI.
# ---------------------------------------------------------------------------
_premium_loader = PremiumLoader(
    server_dir=APEX_ROOT / "server",
    state_dir=APEX_ROOT / "state",
)
_premium = _premium_loader.load_all()
if _premium.get("routes_chat_premium"):
    _premium["routes_chat_premium"].register_premium_chat_routes(chat_router)
if _premium.get("context_premium"):
    _context_mod._premium = _premium["context_premium"]
if _premium.get("ws_handler_premium"):
    _ws_handler_mod._ws_premium = _premium["ws_handler_premium"]


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    _seed_default_profiles()
    seed_system_personas()
    _apex_config = ApexConfig(APEX_ROOT / "state")
    init_dashboard(
        state_dir=APEX_ROOT / "state",
        db_path=DB_PATH,
        ssl_dir=APEX_ROOT / "state" / "ssl",
    )
    log(f"Apex starting on {HOST}:{PORT} [mTLS]")

    # Validate Anthropic token early — catches revoked tokens before first chat
    try:
        from agent_sdk import validate_token_on_startup
        await asyncio.to_thread(validate_token_on_startup)
    except Exception as e:
        log(f"OAuth startup validation failed (non-fatal): {e}")

    async def _startup_recovery():
        """Lazy recovery — only recover the most recently active chat at boot."""
        try:
            active_chats = _get_recently_active_chats(hours=24)
            if not active_chats:
                return
            with _db_lock:
                conn = _get_db()
                row = conn.execute(
                    "SELECT m.chat_id FROM messages m "
                    "JOIN chats c ON m.chat_id = c.id "
                    "WHERE c.type = 'chat' "
                    "ORDER BY m.created_at DESC LIMIT 1"
                ).fetchone()
                conn.close()
            if not row:
                return
            cid = row[0]
            t0 = datetime.now()
            log(f"startup recovery: recovering most recent chat={cid[:8]} (skipping {len(active_chats)-1} others until opened)")
            _recovery_pending[cid] = asyncio.Event()
            try:
                transcript = _get_recent_messages_text(cid, 30)
                if transcript.strip():
                    recovery = await asyncio.to_thread(_generate_recovery_context, transcript)
                    # Always store — even empty summary triggers transcript tail injection
                    _store_recovery_context(cid, recovery or "", skip_targeting=True)
                    _session_context_sent.discard(cid)
                    log(f"startup recovery: chat={cid[:8]} len={len(recovery or '')}")
            except Exception as e:
                log(f"startup recovery error chat={cid[:8]}: {e}")
            finally:
                evt = _recovery_pending.pop(cid, None)
                if evt:
                    evt.set()
            elapsed = (datetime.now() - t0).total_seconds()
            log(f"startup recovery: done (1 chat in {elapsed:.1f}s)")
        except Exception as e:
            log(f"startup recovery failed (non-fatal): {e}")
            for evt in _recovery_pending.values():
                evt.set()
            _recovery_pending.clear()
        # Export Apex transcripts to .jsonl for unified search
        try:
            embed_path = str(WORKSPACE / "skills" / "embedding")
            if embed_path not in sys.path:
                sys.path.insert(0, embed_path)
            import importlib
            export_mod = importlib.import_module("apex_export")
            importlib.reload(export_mod)
            export_stats = await asyncio.to_thread(export_mod.export_apex_transcripts, since_hours=72)
            log(f"apex transcript export: {export_stats}")
        except Exception as e:
            log(f"apex transcript export failed (non-fatal): {e}")
        # Reindex embeddings (incremental — only changed files)
        try:
            mod = importlib.import_module("memory_search")
            importlib.reload(mod)
            stats = await asyncio.to_thread(mod.index_all, force=False)
            log(f"embedding reindex: memory={stats.get('memory', {})} transcripts={stats.get('transcripts', {})}")
        except Exception as e:
            log(f"embedding reindex failed (non-fatal): {e}")
    asyncio.create_task(_startup_recovery())
    asyncio.create_task(_license_mgr.run_check_in_loop())
    try:
        yield
    finally:
        for chat_id in list(_clients):
            await _disconnect_client(chat_id)


app = FastAPI(title="Apex", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/admin", dashboard_app)
app.include_router(setup_router)   # setup wizard (mTLS-exempt)
app.include_router(misc_router)
app.include_router(profiles_router)
app.include_router(alerts_router)
app.include_router(models_router)
app.include_router(upload_router)
app.include_router(chat_router)
app.include_router(tasks_router)
app.include_router(ws_router)


# Routes that don't require client certificate.
# License activate/deactivate are secured by Ed25519 signature on the
# license payload itself — mTLS not required, and exempting them lets
# users activate before importing their client cert.
# Setup routes are exempt because the user has not installed their client
# certificate yet when they first visit /setup.
_PUBLIC_ROUTES = frozenset({
    "/health",
    "/api/license/activate",
    "/api/license/deactivate",
    "/setup",
    "/api/setup/status",
    "/api/setup/models",
    "/api/setup/workspace",
    "/api/setup/knowledge",
    "/api/setup/complete",
})

# Routes allowed during first-run (setup not yet complete). Everything else
# redirects to /setup until the wizard finishes.
_SETUP_PASSTHROUGH = _PUBLIC_ROUTES | frozenset({"/health", "/favicon.ico"})


@app.middleware("http")
async def setup_redirect(request: Request, call_next):
    """Redirect to /setup if first-run wizard has not been completed."""
    path = request.url.path
    if path in _SETUP_PASSTHROUGH or path.startswith("/api/setup/"):
        return await call_next(request)
    # routes_setup.py has already inserted APEX_ROOT into sys.path
    try:
        from setup.progress import phase_completed as _phase_completed
        if not _phase_completed(APEX_ROOT / "state", "setup_complete"):
            return RedirectResponse("/setup", status_code=302)
    except Exception:
        pass  # if progress file unreadable, proceed normally
    return await call_next(request)


@app.middleware("http")
async def verify_client_cert(request: Request, call_next):
    """Enforce mTLS on all routes except public ones. Bearer token for /api/alerts POST."""
    path = request.url.path

    if path in _PUBLIC_ROUTES:
        return await call_next(request)

    current_alert_token = env.ALERT_TOKEN
    if path == "/api/alerts" and request.method == "POST" and current_alert_token:
        auth = request.headers.get("authorization", "")
        expected = f"Bearer {current_alert_token}"
        if not hmac.compare_digest(auth.encode(), expected.encode()):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)

    if mtls_required(SSL_CERT, SSL_CA) and not has_verified_peer_cert(request.scope):
        return JSONResponse({"error": "Client certificate required"}, status_code=401)

    return await call_next(request)


# Premium routes gated behind Pro/Trial license.
# Each entry: path_prefix -> True (always gated) | callable(request) -> bool
_PREMIUM_GATES: list[tuple[str, object]] = [
    ("/api/chats",          lambda r: r.method == "POST" and
                                      (r.query_params.get("type") == "group" or
                                       r.headers.get("x-chat-type") == "group")),
    ("/api/chats/",         lambda r: r.url.path.split("/")[3:4] == ["members"]),
    ("/api/profiles",       lambda r: r.method == "POST"),
]


@app.middleware("http")
async def license_gate(request: Request, call_next):
    """Block premium routes when trial has expired and no valid license."""
    if _license_mgr.is_premium_active():
        return await call_next(request)
    path = request.url.path
    for prefix, check in _PREMIUM_GATES:
        if path.startswith(prefix):
            blocked = check(request) if callable(check) else check
            if blocked:
                return JSONResponse({
                    "error": "premium_required",
                    "message": "This feature requires Apex Pro. Your trial has expired.",
                    "activate_url": "https://useash.dev/activate",
                }, status_code=403)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """S-16: Add security response headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# V2-06: Lightweight per-client rate limiting
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/upload": (30, 60),
    "/api/transcribe": (10, 60),
}


def _rate_limit_check(client_ip: str, path: str) -> bool:
    """Return True if the request should be allowed, False if rate-limited."""
    limit = _RATE_LIMITS.get(path)
    if not limit:
        return True
    max_req, window = limit
    key = f"{client_ip}:{path}"
    now = time.time()
    bucket = _rate_buckets.get(key, [])
    bucket = [t for t in bucket if now - t < window]
    if len(bucket) >= max_req:
        _rate_buckets[key] = bucket
        return False
    bucket.append(now)
    _rate_buckets[key] = bucket
    return True


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """V2-06: Rate limit expensive endpoints per client IP."""
    path = request.url.path
    if path in _RATE_LIMITS:
        client_ip = request.client.host if request.client else "unknown"
        if not _rate_limit_check(client_ip, path):
            return JSONResponse(
                {"error": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
    return await call_next(request)


# WebSocket handler is in ws_handler.py, included via ws_router above.


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not (SSL_CERT and SSL_KEY and SSL_CA):
        print("\n  Apex requires TLS certificates to run securely.", file=sys.stderr)
        print("  Run the setup wizard first:\n", file=sys.stderr)
        print("    python3 setup.py\n", file=sys.stderr)
        print("  Or for a quick start:\n", file=sys.stderr)
        print("    python3 setup.py --fast\n", file=sys.stderr)
        sys.exit(1)

    # V2-11: Verify TLS files exist and are readable
    for label, fpath in [("SSL_CERT", SSL_CERT), ("SSL_KEY", SSL_KEY), ("SSL_CA", SSL_CA)]:
        p = Path(fpath)
        if not p.exists():
            print(f"\n  Error: {label} file not found: {fpath}", file=sys.stderr)
            sys.exit(1)
        if not os.access(fpath, os.R_OK):
            print(f"\n  Error: {label} file not readable: {fpath}", file=sys.stderr)
            sys.exit(1)

    # --- Decrypt encrypted server key for uvicorn ---
    import atexit
    _apex_root_str = str(APEX_ROOT)
    if _apex_root_str not in sys.path:
        sys.path.insert(0, _apex_root_str)

    _ssl_key_path = SSL_KEY
    _decrypted_tmp = None
    try:
        from setup.ssl_keystore import (
            retrieve_passphrase as _retrieve_pw,
            decrypt_key_to_tempfile as _decrypt_tmp,
            is_key_encrypted as _is_enc,
            shred_file as _shred,
        )
        if _is_enc(Path(SSL_KEY)):
            _pw = _retrieve_pw()
            if _pw:
                _decrypted_tmp = _decrypt_tmp(Path(SSL_KEY), _pw)
                _ssl_key_path = str(_decrypted_tmp)
            else:
                print("  Warning: server key is encrypted but no passphrase found.", file=sys.stderr)
                print("  Run: python3 setup.py --encrypt-keys", file=sys.stderr)
                sys.exit(1)
    except ImportError:
        pass

    def _cleanup_decrypted_key():
        if _decrypted_tmp is not None:
            try:
                _shred(_decrypted_tmp)
            except Exception:
                pass
    atexit.register(_cleanup_decrypted_key)

    print(f"\n  Apex {APP_BUILD}")
    print(f"  https://{HOST}:{PORT}")
    print(f"  Model: {MODEL}")
    print(f"  Auth: mTLS (client certificate)")
    print(f"  CA: {SSL_CA}")
    print()

    log_lvl = env.LOG_LEVEL
    uvicorn.run(
        app, host=HOST, port=PORT, log_level=log_lvl,
        ssl_certfile=SSL_CERT,
        ssl_keyfile=_ssl_key_path,
        ssl_ca_certs=SSL_CA,
        ssl_cert_reqs=ssl.CERT_REQUIRED,
    )
