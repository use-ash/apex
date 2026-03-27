---
name: Apex mobile access and mTLS auth
description: Apex mobile setup over VPN with mTLS client cert auth, SDK streaming fixes, and troubleshooting log
type: project
---

Apex (`server/apex.py`) serves over HTTPS with mTLS client certificate auth. Full troubleshooting log at `docs/TROUBLESHOOTING.md`.

**Auth: mTLS (CERT_OPTIONAL)**
- Password auth fully stripped. No cookies, no sessions, no tokens.
- `ssl_cert_reqs=ssl.CERT_OPTIONAL` — browsers don't send client certs for WebSocket upgrades, so CERT_REQUIRED breaks WebSocket. VPN is the security boundary.
- Client cert: `state/ssl/client.p12` (AirDrop to phone, password: `apex`)
- CA: `state/ssl/ca.crt` (OpenClaw Local CA)
- Server cert SANs: 10.8.0.2 (VPN), 192.168.86.214 (LAN), 127.0.0.1

**SDK quirks (must-know):**
- `query()` accepts `str | AsyncIterable[dict]` — plain lists break it
- Yielded dicts must be full messages: `{"type": "user", "message": {"role": "user", "content": [blocks]}}`
- Async generators are single-use — create fresh on retry
- Stale session resume hangs — 30s timeout + clear session ID on failure
- Each SDK process ~360MB RAM

**Launch:** `./server/launch_apex.sh` (generates client cert on first run)

**Why:** Dana wants mobile Claude access over WireGuard VPN. Also a reference impl for ASH customer service chat.

**How to apply:** Read `docs/TROUBLESHOOTING.md` before touching auth or SDK code. 10 issues documented with root causes and fixes.
