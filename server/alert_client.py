"""Apex alert client — drop-in for any script that needs to send alerts.

Usage:
    from alert_client import send_apex_alert
    send_apex_alert("my_app", "info", "Task completed", body="Backup finished successfully")
"""

from __future__ import annotations

import json
from pathlib import Path
import ssl
import urllib.request

import env


def _build_ssl_context(server_url: str) -> ssl.SSLContext | None:
    """Build a verifying SSL context for HTTPS alert delivery."""
    if not server_url.lower().startswith("https://"):
        return None
    ca_path = env.SSL_CA.strip()
    if not ca_path:
        raise ValueError("APEX_SSL_CA is required for HTTPS alert delivery")
    ca_file = Path(ca_path).expanduser()
    if not ca_file.exists():
        raise FileNotFoundError(f"CA file not found: {ca_file}")
    return ssl.create_default_context(cafile=str(ca_file))


def send_apex_alert(
    source: str, severity: str, title: str, body: str = "",
    *, metadata: dict | None = None, timeout: int = 5
) -> bool:
    """Post alert to Apex. Returns True on success."""
    token = env.ALERT_TOKEN
    server_url = env.SERVER_URL
    if not token:
        return False
    payload = {"source": source, "severity": severity, "title": title, "body": body}
    if metadata:
        payload["metadata"] = metadata
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{server_url}/api/alerts",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        context = _build_ssl_context(server_url)
        if context is None:
            urllib.request.urlopen(req, timeout=timeout)
        else:
            urllib.request.urlopen(req, timeout=timeout, context=context)
        return True
    except Exception:
        return False
