"""Alert ingestion, APNs push notifications, and device registration.

Layer 4: imports from db/state/log plus explicit streaming and guardrail
helpers. No runtime back-reference to apex.py.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import time
import uuid
from pathlib import Path

import env

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from db import (
    _db_lock, _get_db, _now,
    _create_alert, _get_alerts, _get_alert, _ack_alert,
    _get_all_device_tokens, _remove_device_token,
)
from log import log
from memory_extract import _add_whitelist_entry
from streaming import _broadcast_alert, _safe_ws_send_json
from state import _alert_waiters, _chat_ws, _ws_chat

alerts_router = APIRouter()

# ---------------------------------------------------------------------------
# Config (env — same source as apex.py)
# ---------------------------------------------------------------------------
APNS_KEY_ID = env.APNS_KEY_ID
APNS_TEAM_ID = env.APNS_TEAM_ID
APNS_KEY_PATH = env.APNS_KEY_PATH
APNS_BUNDLE_ID = env.APNS_BUNDLE_ID
APNS_USE_SANDBOX = env.APNS_USE_SANDBOX

_apns_key_data: str | None = None


# ---------------------------------------------------------------------------
# APNs helpers
# ---------------------------------------------------------------------------

def _load_apns_key() -> str | None:
    """Load the APNs .p8 key file. Cached after first read."""
    global _apns_key_data
    if _apns_key_data is not None:
        return _apns_key_data
    p = APNS_KEY_PATH
    if not p:
        apns_dir = Path.home() / ".apex" / "apns"
        candidates = list(apns_dir.glob("AuthKey_*.p8")) if apns_dir.exists() else []
        if candidates:
            p = str(candidates[0])
    if not p or not Path(p).exists():
        return None
    _apns_key_data = Path(p).read_text().strip()
    return _apns_key_data


def _make_apns_jwt() -> str | None:
    """Create a short-lived JWT for APNs authentication."""
    key_data = _load_apns_key()
    if not key_data or not APNS_KEY_ID or not APNS_TEAM_ID:
        return None
    try:
        import jwt  # PyJWT
        now = int(time.time())
        payload = {"iss": APNS_TEAM_ID, "iat": now}
        return jwt.encode(payload, key_data, algorithm="ES256", headers={"kid": APNS_KEY_ID})
    except ImportError:
        log("APNs: PyJWT not installed — pip install PyJWT")
        return None
    except Exception as exc:
        log(f"APNs JWT error: {exc}")
        return None


async def _send_push_notification(device_token: str, title: str, body: str,
                                   subtitle: str = "", thread_id: str = "",
                                   category: str = "ALERT", extra: dict | None = None) -> bool:
    """Send a push notification to a single device via APNs HTTP/2."""
    token = _make_apns_jwt()
    if not token:
        return False
    host = "api.sandbox.push.apple.com" if APNS_USE_SANDBOX else "api.push.apple.com"
    url = f"https://{host}/3/device/{device_token}"
    alert_dict: dict = {"title": title, "body": body[:200]}
    if subtitle:
        alert_dict["subtitle"] = subtitle
    aps: dict = {
        "alert": alert_dict,
        "sound": "default",
        "category": category,
    }
    if thread_id:
        aps["thread-id"] = thread_id
    payload = {"aps": aps}
    if extra:
        payload.update(extra)
    data = json.dumps(payload).encode()
    headers = {
        "authorization": f"bearer {token}",
        "apns-topic": APNS_BUNDLE_ID,
        "apns-push-type": "alert",
        "apns-priority": "10",
        "content-type": "application/json",
    }
    try:
        import httpx
        async with httpx.AsyncClient(http2=True) as client:
            resp = await client.post(url, content=data, headers=headers, timeout=10)
            if resp.status_code == 200:
                return True
            log(f"APNs error: {resp.status_code} {resp.text[:100]}")
            if resp.status_code == 410:
                _remove_device_token(device_token)
            return False
    except ImportError:
        log("APNs: httpx not installed — pip install httpx[http2]")
        return False
    except Exception as exc:
        log(f"APNs send error: {exc}")
        return False


async def _push_to_all_devices(title: str, body: str, subtitle: str = "",
                                thread_id: str = "", extra: dict | None = None) -> int:
    """Send push notification to all registered devices. Returns count sent."""
    tokens = _get_all_device_tokens()
    if not tokens:
        return 0
    sent = 0
    for tok in tokens:
        if await _send_push_notification(tok, title, body, subtitle=subtitle,
                                          thread_id=thread_id, extra=extra):
            sent += 1
    return sent


# ---------------------------------------------------------------------------
# Alert routes
# ---------------------------------------------------------------------------

@alerts_router.post("/api/alerts")
async def api_create_alert(request: Request):
    """Webhook: ingest an alert. Auth: bearer token."""
    alert_token = env.ALERT_TOKEN
    if not alert_token:
        return JSONResponse({"error": "Alert token not configured"}, status_code=503)
    auth = request.headers.get("authorization", "")
    expected = f"Bearer {alert_token}"
    if not hmac.compare_digest(auth.encode(), expected.encode()):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = await request.json()
    source = str(data.get("source", "unknown"))
    severity = str(data.get("severity", "info"))
    if severity not in ("info", "warning", "critical"):
        severity = "info"
    title = str(data.get("title", ""))
    body = str(data.get("body", ""))
    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        metadata = None
    if not title:
        return JSONResponse({"error": "title is required"}, status_code=400)
    alert = _create_alert(source, severity, title, body, metadata=metadata)

    # Broadcast to all WS clients
    await _broadcast_alert(alert)

    # Wake long-poll waiters
    for evt in _alert_waiters:
        evt.set()

    # Push notification — skip if any client is actively connected via WebSocket
    has_active_session = any(bool(ws_set) for ws_set in _chat_ws.values())
    if not has_active_session:
        push_body = title if title else body
        push_extra_body = body[:100] if body and title else ""
        if push_extra_body:
            push_body = f"{push_body} — {push_extra_body}"
        asyncio.create_task(_push_to_all_devices(
            title="ApexChat",
            subtitle=f"[{severity.upper()}] {source}",
            body=push_body[:200],
            thread_id=f"alerts-{source}",
            extra={"alert_id": alert["id"], "source": source,
                   "chat_id": metadata.get("chat_id", "") if metadata else ""},
        ))
    log(f"alert: id={alert['id']} src={source} sev={severity} title={title[:50]}")
    return JSONResponse(alert, status_code=201)


@alerts_router.get("/api/alerts")
async def api_get_alerts(since: str | None = None, unacked: bool = False,
                          category: str | None = None):
    return JSONResponse(_get_alerts(since=since, unacked_only=unacked, category=category))


@alerts_router.get("/api/alerts/wait")
async def api_wait_alert(since: str | None = None, timeout: int = 25):
    """Long-poll: block until a new alert arrives or timeout (max 30s)."""
    timeout = min(timeout, 30)
    alerts = _get_alerts(since=since, unacked_only=True, limit=20)
    if alerts:
        return JSONResponse(alerts)
    event = asyncio.Event()
    _alert_waiters.append(event)
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        try:
            _alert_waiters.remove(event)
        except ValueError:
            pass
    alerts = _get_alerts(since=since, unacked_only=True, limit=20)
    return JSONResponse(alerts)


@alerts_router.post("/api/alerts/{alert_id}/ack")
async def api_ack_alert(alert_id: str):
    _ack_alert(alert_id)
    payload = {"type": "alert_acked", "alert_id": alert_id}
    all_ws: set = set()
    for ws_set in _chat_ws.values():
        all_ws.update(ws_set)
    for ws in list(all_ws):
        await _safe_ws_send_json(ws, payload, chat_id=_ws_chat.get(ws, ""))
    return JSONResponse({"ok": True})


@alerts_router.delete("/api/alerts/{alert_id}")
async def api_delete_alert(alert_id: str):
    with _db_lock:
        conn = _get_db()
        cur = conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        conn.commit()
        deleted = cur.rowcount > 0
        conn.close()
    if not deleted:
        return JSONResponse({"error": "Alert not found"}, status_code=404)
    log(f"alert deleted: id={alert_id}")
    return JSONResponse({"ok": True})


@alerts_router.delete("/api/alerts")
async def api_delete_all_alerts():
    with _db_lock:
        conn = _get_db()
        cur = conn.execute("DELETE FROM alerts")
        conn.commit()
        count = cur.rowcount
        conn.close()
    log(f"alerts cleared: {count} deleted")
    return JSONResponse({"ok": True, "deleted": count})


@alerts_router.post("/api/alerts/{alert_id}/allow")
async def api_allow_alert(alert_id: str):
    """Whitelist a guardrail-blocked action for retry (1hr TTL)."""
    alert = _get_alert(alert_id)
    if not alert:
        return JSONResponse({"error": "Alert not found"}, status_code=404)
    if alert["source"] != "guardrail":
        return JSONResponse({"error": "Only guardrail alerts can be whitelisted"}, status_code=400)
    meta = alert.get("metadata", {})
    tool = meta.get("tool", "")
    target = meta.get("target", "")
    if not tool:
        return JSONResponse({"error": "Alert metadata missing tool info"}, status_code=400)
    entry = _add_whitelist_entry(tool, target, alert_id)
    _ack_alert(alert_id)
    log(f"guardrail allow: alert={alert_id} tool={tool} target={target[:60]} expires={entry['expires_at']}")
    return JSONResponse({"ok": True, "expires_at": entry["expires_at"]})


# ---------------------------------------------------------------------------
# Device registration
# ---------------------------------------------------------------------------

@alerts_router.post("/api/devices")
async def api_register_device(request: Request):
    """Register a device for push notifications."""
    data = await request.json()
    token = str(data.get("token", "")).strip()
    platform = str(data.get("platform", "ios")).strip()
    label = str(data.get("label", "")).strip()[:100]
    if not token or len(token) < 20:
        return JSONResponse({"error": "Invalid device token"}, status_code=400)
    now = _now()
    with _db_lock:
        conn = _get_db()
        existing = conn.execute("SELECT id FROM device_tokens WHERE token = ?", (token,)).fetchone()
        if existing:
            conn.execute("UPDATE device_tokens SET last_seen = ?, label = ? WHERE token = ?",
                         (now, label, token))
        else:
            did = uuid.uuid4().hex[:8]
            conn.execute(
                "INSERT INTO device_tokens (id, token, platform, label, created_at, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                (did, token, platform, label, now, now),
            )
        conn.commit()
        conn.close()
    log(f"device registered: platform={platform} token={token[:12]}...")
    return JSONResponse({"ok": True}, status_code=201)
