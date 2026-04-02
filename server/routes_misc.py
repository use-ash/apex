"""Misc routes: index page, PWA, health, embedding status, features, license.

Layer 4: most config re-derived from env plus explicit licensing access.
No runtime back-reference to apex.py.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import subprocess
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

import env
from chat_html import CHAT_HTML
from db import _get_chats
from license import get_license_manager
from log import log
from state import _clients

misc_router = APIRouter()

# ---------------------------------------------------------------------------
# Config (re-derived from env or computed once at import)
# ---------------------------------------------------------------------------
PORT = env.PORT
MODEL = env.MODEL
ENABLE_SUBCONSCIOUS_WHISPER = env.ENABLE_SUBCONSCIOUS_WHISPER
GROUPS_ENABLED = env.GROUPS_ENABLED
_WORKSPACE = env.WORKSPACE

_license_mgr = get_license_manager()


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return ""


def _read_version() -> str:
    try:
        v = Path(__file__).resolve().parent.parent / "VERSION"
        return v.read_text().strip() if v.exists() else "0.0.0"
    except Exception:
        return "0.0.0"


APP_VERSION = _read_version()
APP_BRANCH = _git_output("branch", "--show-current") or "unknown"
APP_COMMIT = _git_output("rev-parse", "--short", "HEAD") or "unknown"
APP_BUILD = f"v{APP_VERSION} • {APP_BRANCH} • {APP_COMMIT}"


# ---------------------------------------------------------------------------
# Index / PWA
# ---------------------------------------------------------------------------

@misc_router.get("/", response_class=HTMLResponse)
async def index():
    title_suffix = " (Dev)" if PORT != 8300 else ""
    nonce = secrets.token_hex(16)
    html = (
        CHAT_HTML
        .replace("{{TITLE_SUFFIX}}", title_suffix)
        .replace("{{MODE_CLASS}}", "mtls")
        .replace("{{MODE_LABEL}}", "mTLS")
        .replace("{{CSP_NONCE}}", nonce)
    )
    html = html.encode("utf-8", errors="replace").decode("utf-8")
    csp = (
        f"default-src 'self'; "
        f"script-src 'nonce-{nonce}'; "
        f"style-src 'self' 'unsafe-inline'; "
        f"img-src 'self' data: blob:; "
        f"connect-src 'self' wss: ws:; "
        f"font-src 'self'; "
        f"object-src 'none'; "
        f"base-uri 'self'; "
        f"frame-ancestors 'none';"
    )
    return HTMLResponse(html, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Content-Security-Policy": csp,
    })


@misc_router.get("/manifest.json")
async def manifest():
    return JSONResponse({
        "name": "Apex",
        "short_name": "Apex",
        "description": "Self-hosted AI platform — multi-model chat, persistent memory, extensible skills",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0F172A",
        "theme_color": "#0F172A",
        "icons": [
            {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"},
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        ],
    })


@misc_router.get("/icon.svg")
async def icon_svg():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">
<defs>
<linearGradient id="hs"><stop stop-color="#38bdf8" stop-opacity="0.6"/><stop offset="1" stop-color="#818cf8" stop-opacity="0.6"/></linearGradient>
<linearGradient id="l1" x1="0" y1="1" x2="1" y2="0"><stop stop-color="#2dd4bf"/><stop offset="1" stop-color="#38bdf8"/></linearGradient>
<linearGradient id="l3" x1="1" y1="1" x2="0" y2="0"><stop stop-color="#818cf8"/><stop offset="1" stop-color="#38bdf8"/></linearGradient>
<linearGradient id="cb"><stop stop-color="#2dd4bf"/><stop offset="0.5" stop-color="#38bdf8"/><stop offset="1" stop-color="#818cf8"/></linearGradient>
<radialGradient id="nc" cx="0.45" cy="0.4"><stop stop-color="#7dd3fc"/><stop offset="0.5" stop-color="#38bdf8"/><stop offset="1" stop-color="#818cf8"/></radialGradient>
</defs>
<rect width="192" height="192" rx="40" fill="#0a0e17"/>
<path d="M96 22 L158 54 L158 118 L96 166 L34 118 L34 54 Z" stroke="url(#hs)" stroke-width="2.5" fill="none" opacity="0.5"/>
<line x1="50" y1="124" x2="96" y2="58" stroke="url(#l1)" stroke-width="2" opacity="0.6"/>
<line x1="96" y1="148" x2="96" y2="58" stroke="#38bdf8" stroke-width="2" opacity="0.6"/>
<line x1="142" y1="124" x2="96" y2="58" stroke="url(#l3)" stroke-width="2" opacity="0.6"/>
<line x1="50" y1="124" x2="142" y2="124" stroke="url(#cb)" stroke-width="1.5" opacity="0.3"/>
<circle cx="96" cy="58" r="14" fill="url(#nc)"/>
<circle cx="96" cy="58" r="5.5" fill="#0a0e17"/>
<circle cx="96" cy="58" r="2.5" fill="#e2e8f0"/>
<circle cx="50" cy="124" r="5" fill="#2dd4bf" opacity="0.85"/>
<circle cx="96" cy="148" r="5" fill="#38bdf8" opacity="0.85"/>
<circle cx="142" cy="124" r="5" fill="#818cf8" opacity="0.85"/>
</svg>'''
    return Response(content=svg, media_type="image/svg+xml")


@misc_router.get("/icon-192.png")
async def icon_png():
    """Serve 192x192 PNG icon for PWA manifest."""
    icon_path = Path(__file__).parent.parent / "docs" / "images" / "icon-192.png"
    if icon_path.exists():
        return Response(content=icon_path.read_bytes(), media_type="image/png")
    return Response(status_code=404)


@misc_router.get("/sw.js")
async def service_worker():
    sw = "// no-op service worker — avoids fetch errors with self-signed certs"
    return Response(content=sw, media_type="application/javascript")


# ---------------------------------------------------------------------------
# Health + embedding
# ---------------------------------------------------------------------------

@misc_router.get("/api/health")
@misc_router.get("/health")
async def health():
    return JSONResponse({
        "ok": True,
        "clients": len(_clients),
        "chats": len(_get_chats()),
        "model": MODEL,
        "whisper": ENABLE_SUBCONSCIOUS_WHISPER,
        "version": APP_VERSION,
        "branch": APP_BRANCH,
        "commit": APP_COMMIT,
        "build": APP_BUILD,
    })


@misc_router.get("/api/embedding/status")
async def api_embedding_status():
    """Return embedding index status."""
    try:
        idx_dir = _WORKSPACE / "state" / "embeddings"
        result = {}
        for name, meta_file in [("memory", "memory_meta.json"), ("transcripts", "transcript_meta.json")]:
            meta_path = idx_dir / meta_file
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                result[name] = {"files": len(meta)}
            else:
                result[name] = {"files": 0}
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@misc_router.post("/api/embedding/reindex")
async def api_embedding_reindex(request: Request):
    """Trigger a full embedding reindex (memory + transcripts).

    Body (optional): {"force": true}  — force re-embed even if unchanged.
    """
    csrf = request.headers.get("x-requested-with", "")
    if csrf != "XMLHttpRequest":
        return JSONResponse({"error": "CSRF check failed"}, status_code=403)
    data = {}
    try:
        data = await request.json()
    except Exception:
        pass
    force = bool(data.get("force", False))
    try:
        import importlib
        mod = importlib.import_module("memory_search")
        importlib.reload(mod)
        stats = await asyncio.to_thread(mod.index_all, force=force)
        return JSONResponse({"status": "ok", "stats": stats})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Features + license
# ---------------------------------------------------------------------------

@misc_router.get("/api/features")
async def api_features():
    lic = _license_mgr.status()
    premium = lic["premium_active"]
    return JSONResponse({
        "groups_enabled": GROUPS_ENABLED or premium,
        "tier": lic["tier"],
        "trial_active": lic["trial_active"],
        "trial_days_remaining": lic["trial_days_remaining"],
        "features": {
            "groups": GROUPS_ENABLED or lic["features"].get("groups", False),
            "orchestration": lic["features"].get("orchestration", False),
            "agent_profiles": lic["features"].get("agent_profiles", False),
        },
        "activate_url": "https://buy.stripe.com/dRmcN40Ag8Qucptc2UcQU04",
    })


@misc_router.get("/api/license/status")
async def api_license_status():
    """Return current license tier, trial state, and feature flags."""
    return JSONResponse(_license_mgr.status())


@misc_router.post("/api/license/activate")
async def api_license_activate(request: Request):
    """Activate a signed license. Body: raw license JSON or {"license": ..., "feature_key": ...}."""
    try:
        body = await request.body()
        if not body:
            return JSONResponse({"success": False, "error": "Empty body"}, status_code=400)
        raw = body.decode("utf-8")

        # Accept either raw license JSON or a wrapper with feature_key
        feature_key = ""
        try:
            wrapper = __import__("json").loads(raw)
            if isinstance(wrapper, dict) and "license" in wrapper:
                license_data = wrapper["license"]
                feature_key = wrapper.get("feature_key", "")
                raw = __import__("json").dumps(license_data) if isinstance(license_data, dict) else str(license_data)
        except Exception:
            pass  # not a wrapper — treat raw as license JSON

        result = _license_mgr.activate(raw, feature_key=feature_key)
        if result["success"]:
            log(f"License activated: tier={result['tier']} expires={result.get('expires')} feature_key={'yes' if feature_key else 'no'}")
        else:
            log(f"License activation failed: {result['error']}")
        status_code = 200 if result["success"] else 400
        return JSONResponse(result, status_code=status_code)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@misc_router.post("/api/license/deactivate")
async def api_license_deactivate():
    """Remove active license. Reverts to trial or free tier."""
    result = _license_mgr.deactivate()
    if result["success"]:
        log(f"License deactivated, reverted to tier={result['tier']}")
    return JSONResponse(result)
