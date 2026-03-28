"""Apex alert client — drop-in for any script that needs to send alerts.

Usage:
    from alert_client import send_apex_alert
    send_apex_alert("my_app", "info", "Task completed", body="Backup finished successfully")
"""

import json, os, ssl, urllib.request

_SERVER = os.environ.get("APEX_SERVER", "https://localhost:8300")
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
