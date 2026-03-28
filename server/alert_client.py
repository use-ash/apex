"""Apex alert client — drop-in for trading scripts.

Usage:
    from alert_client import send_apex_alert
    send_apex_alert("plan_h", "critical", "SPY signal detected", body="CALL @ $542.30")
"""

import json, os, ssl, urllib.request

_SERVER = os.environ.get("APEX_SERVER", "https://10.8.0.2:8300")
_TOKEN = os.environ.get("APEX_ALERT_TOKEN", "")


def send_apex_alert(
    source: str, severity: str, title: str, body: str = "",
    *, metadata: dict | None = None, timeout: int = 5
) -> bool:
    """Post alert to Apex. Returns True on success."""
    if not _TOKEN:
        return False
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    payload = {"source": source, "severity": severity, "title": title, "body": body}
    if metadata:
        payload["metadata"] = metadata
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{_SERVER}/api/alerts",
        data=data,
        headers={
            "Authorization": f"Bearer {_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=timeout, context=ctx)
        return True
    except Exception:
        return False
