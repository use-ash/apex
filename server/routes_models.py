"""Model listing and API usage meter routes.

Layer 4: imports from model_dispatch (Layer 1), log (Layer 0).
Credentials accessed directly from env — no circular deps.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import env
from log import log
from model_dispatch import (
    REMOTE_MODEL_OPTIONS,
    _get_ollama_models,
    _get_mlx_models,
)

import asyncio

models_router = APIRouter()

# ---------------------------------------------------------------------------
# xAI credentials (env — same source as apex.py, no sharing needed)
# ---------------------------------------------------------------------------
_XAI_MANAGEMENT_KEY = env.XAI_MANAGEMENT_KEY
_XAI_TEAM_ID = env.XAI_TEAM_ID

# ---------------------------------------------------------------------------
# Anthropic OAuth usage cache
# ---------------------------------------------------------------------------
_USAGE_CACHE: dict = {}
_USAGE_CACHE_TS: float = 0
_USAGE_CACHE_TTL = 300  # 5 minutes — avoid 429s from Anthropic
_USAGE_DISK_CACHE = Path.home() / ".claude" / ".usage_cache.json"
_PLAN_NAMES = {
    "default_claude_ai": "Pro",
    "default_claude_max_5x": "Max 5x",
    "default_claude_max_20x": "Max 20x",
}

# ---------------------------------------------------------------------------
# Grok usage cache
# ---------------------------------------------------------------------------
_GROK_USAGE_CACHE: dict = {}
_GROK_USAGE_CACHE_TS: float = 0

# ---------------------------------------------------------------------------
# Codex usage cache path
# ---------------------------------------------------------------------------
_CODEX_USAGE_CACHE_PATH = Path.home() / ".codex" / ".usage_cache.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_oauth_credentials() -> tuple[str | None, str]:
    creds_path = Path.home() / ".claude" / ".credentials.json"
    try:
        data = json.loads(creds_path.read_text())
        oauth = data.get("claudeAiOauth", {})
        token = oauth.get("accessToken")
        if token:
            tier = oauth.get("rateLimitTier", "")
            plan = _PLAN_NAMES.get(tier, tier.replace("default_claude_", "").replace("_", " ").title())
            return token, plan
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    if sys.platform == "darwin":
        try:
            import subprocess as _sp
            r = _sp.run(
                ["/usr/bin/security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                data = json.loads(r.stdout.strip())
                oauth = data.get("claudeAiOauth", {})
                token = oauth.get("accessToken")
                if token:
                    tier = oauth.get("rateLimitTier", "")
                    plan = _PLAN_NAMES.get(tier, tier.replace("default_claude_", "").replace("_", " ").title())
                    return token, plan
        except Exception:
            pass
    return None, ""


def _fetch_usage_data(token: str) -> dict | None:
    global _USAGE_CACHE, _USAGE_CACHE_TS
    now = time.time()
    if now - _USAGE_CACHE_TS < _USAGE_CACHE_TTL and _USAGE_CACHE:
        return _USAGE_CACHE
    stale_disk: dict | None = None
    try:
        disk = json.loads(_USAGE_DISK_CACHE.read_text())
        if now - disk.get("_ts", 0) < _USAGE_CACHE_TTL:
            _USAGE_CACHE = disk
            _USAGE_CACHE_TS = now
            return disk
        stale_disk = disk
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/api/oauth/usage",
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
                "Accept": "application/json",
                "User-Agent": "apex/1.0",
            },
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read(1_000_000))
        _USAGE_CACHE = data
        _USAGE_CACHE_TS = now
        try:
            data["_ts"] = now
            _USAGE_DISK_CACHE.write_text(json.dumps(data))
        except OSError:
            pass
        return data
    except Exception as e:
        log(f"usage API error: {type(e).__name__}: {e}")
        fallback = _USAGE_CACHE or stale_disk
        if fallback:
            _USAGE_CACHE = fallback
            _USAGE_CACHE_TS = now
            try:
                fallback["_ts"] = now
                _USAGE_DISK_CACHE.write_text(json.dumps(fallback))
            except OSError:
                pass
            return fallback
        return None


def _format_countdown(resets_at_str: str) -> str:
    if not resets_at_str:
        return "?"
    try:
        resets_at = datetime.fromisoformat(resets_at_str)
        secs = int((resets_at - datetime.now(timezone.utc)).total_seconds())
        if secs <= 0:
            return "now"
        h, m = secs // 3600, (secs % 3600) // 60
        return f"{h}h{m:02d}m" if h > 0 else f"{m}m"
    except (ValueError, TypeError):
        return "?"


def _fetch_grok_usage() -> dict | None:
    """Fetch xAI prepaid credit balance via Management API."""
    global _GROK_USAGE_CACHE, _GROK_USAGE_CACHE_TS
    if not _XAI_MANAGEMENT_KEY:
        return None
    now = time.time()
    if now - _GROK_USAGE_CACHE_TS < _USAGE_CACHE_TTL and _GROK_USAGE_CACHE:
        return _GROK_USAGE_CACHE

    try:
        headers = {
            "Authorization": f"Bearer {_XAI_MANAGEMENT_KEY}",
            "Accept": "application/json",
            "User-Agent": "Apex/1.0",
        }

        req = urllib.request.Request(
            f"https://management-api.x.ai/v1/billing/teams/{_XAI_TEAM_ID}/prepaid/balance",
            headers=headers,
        )
        resp = urllib.request.urlopen(req, timeout=10)
        bal_data = json.loads(resp.read(1_000_000))

        purchased_cents = 0
        ledger_spent_cents = 0
        for c in bal_data.get("changes", []):
            val = int(c.get("amount", {}).get("val", 0))
            if val < 0:
                purchased_cents += abs(val)
            else:
                ledger_spent_cents += val
        ledger_balance = purchased_cents - ledger_spent_cents

        current_month_cents = 0
        try:
            req2 = urllib.request.Request(
                f"https://management-api.x.ai/v1/billing/teams/{_XAI_TEAM_ID}/postpaid/invoice/preview",
                headers=headers,
            )
            resp2 = urllib.request.urlopen(req2, timeout=10)
            inv_data = json.loads(resp2.read(1_000_000))
            for line in inv_data.get("coreInvoice", {}).get("lines", []):
                current_month_cents += int(line.get("amount", "0"))
        except Exception:
            pass

        remaining_cents = ledger_balance - current_month_cents
        total_spent_cents = ledger_spent_cents + current_month_cents

        result = {
            "balance_usd": round(remaining_cents / 100.0, 2),
            "purchased_usd": round(purchased_cents / 100.0, 2),
            "spent_usd": round(total_spent_cents / 100.0, 2),
        }
        _GROK_USAGE_CACHE = result
        _GROK_USAGE_CACHE_TS = now
        return result
    except Exception as e:
        log(f"grok usage API error: {type(e).__name__}: {e}")
        if _GROK_USAGE_CACHE:
            _GROK_USAGE_CACHE_TS = now
            return _GROK_USAGE_CACHE
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@models_router.get("/api/models/local")
async def api_local_models():
    ollama, mlx = await asyncio.gather(
        asyncio.to_thread(_get_ollama_models),
        asyncio.to_thread(_get_mlx_models),
    )
    return JSONResponse(ollama + mlx)


@models_router.get("/api/available-models")
async def api_available_models():
    ollama, mlx = await asyncio.gather(
        asyncio.to_thread(_get_ollama_models),
        asyncio.to_thread(_get_mlx_models),
    )
    local_models = []
    for model in ollama + mlx:
        item = dict(model)
        item.setdefault("provider", "local")
        item["local"] = True
        local_models.append(item)
    return JSONResponse({"models": REMOTE_MODEL_OPTIONS + local_models})


@models_router.get("/api/usage")
async def api_usage():
    token, plan = _get_oauth_credentials()
    if not token:
        return JSONResponse({"error": "no credentials"}, status_code=401)
    usage = _fetch_usage_data(token)
    if not usage:
        return JSONResponse({"error": "fetch failed"}, status_code=502)

    five = usage.get("five_hour", {})
    seven = usage.get("seven_day", {})

    result = {
        "plan": plan,
        "session": {
            "utilization": round(five.get("utilization") or 0),
            "resets_at": five.get("resets_at", ""),
            "resets_in": _format_countdown(five.get("resets_at")),
        },
        "weekly": {
            "utilization": round(seven.get("utilization") or 0),
            "resets_at": seven.get("resets_at", ""),
            "resets_in": _format_countdown(seven.get("resets_at")),
        },
        "models": {},
    }

    for key, label in [("seven_day_opus", "opus"), ("seven_day_sonnet", "sonnet")]:
        model = usage.get(key)
        if model and model.get("utilization"):
            result["models"][label] = {
                "utilization": round(model["utilization"]),
                "resets_at": model.get("resets_at", ""),
                "resets_in": _format_countdown(model.get("resets_at")),
            }

    extra = usage.get("extra_usage", {})
    if extra and extra.get("is_enabled"):
        result["extra_credits"] = {
            "used": extra.get("used_credits", 0),
            "limit": extra.get("monthly_limit", 0),
            "remaining": extra.get("monthly_limit", 0) - extra.get("used_credits", 0),
        }

    return JSONResponse(result)


@models_router.get("/api/usage/grok")
async def api_usage_grok():
    if not _XAI_MANAGEMENT_KEY:
        return JSONResponse({"error": "no management key"}, status_code=401)
    usage = _fetch_grok_usage()
    if not usage:
        return JSONResponse({"error": "fetch failed"}, status_code=502)
    return JSONResponse(usage)


@models_router.get("/api/usage/codex")
async def api_usage_codex():
    """Return Codex/ChatGPT rate limit status from cached response headers."""
    try:
        data = json.loads(_CODEX_USAGE_CACHE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return JSONResponse({"error": "no usage data yet — send a message in a Codex chat first"}, status_code=404)

    ts = data.get("_ts", 0)
    stale = (time.time() - ts) > 1800

    primary_pct = float(data.get("x-codex-primary-used-percent", 0))
    secondary_pct = float(data.get("x-codex-secondary-used-percent", 0))
    primary_reset = int(data.get("x-codex-primary-reset-after-seconds", 0))
    secondary_reset = int(data.get("x-codex-secondary-reset-after-seconds", 0))
    plan = data.get("x-codex-plan-type", "unknown")

    def fmt_reset(secs: int) -> str:
        if secs <= 0:
            return "now"
        h, m = secs // 3600, (secs % 3600) // 60
        return f"{h}h{m:02d}m" if h > 0 else f"{m}m"

    return JSONResponse({
        "plan": plan.title() if plan else "Unknown",
        "session": {
            "utilization": round(primary_pct),
            "resets_in": fmt_reset(primary_reset),
        },
        "weekly": {
            "utilization": round(secondary_pct),
            "resets_in": fmt_reset(secondary_reset),
        },
        "stale": stale,
    })
