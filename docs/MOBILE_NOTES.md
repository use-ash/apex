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
- CA: `state/ssl/ca.crt` (Apex Local CA)
- Server cert SANs: your-vpn-ip (VPN), your-lan-ip (LAN), 127.0.0.1

**SDK quirks (must-know):**
- `query()` accepts `str | AsyncIterable[dict]` — plain lists break it
- Yielded dicts must be full messages: `{"type": "user", "message": {"role": "user", "content": [blocks]}}`
- Async generators are single-use — create fresh on retry
- Stale session resume hangs — 30s timeout + clear session ID on failure
- Each SDK process ~360MB RAM

**Launch:** `./server/launch_apex.sh` (generates client cert on first run)

**Why:** Mobile AI chat access over WireGuard VPN with full mTLS security.

**How to apply:** Read `docs/TROUBLESHOOTING.md` before touching auth or SDK code. 10 issues documented with root causes and fixes.

---

## iOS App — Single Repo Rule

**The iOS app lives in a separate repo: `apexchat-ios` (github.com/use-ash/apexchat-ios, `dev` branch).**

- `apex/ios/` has been **deleted** from this repo. Do not recreate it.
- All iOS Swift file edits must go to the `apexchat-ios` repo.
- Xcode builds from `apexchat-ios`. TestFlight archives from `apexchat-ios`.

**Why:** The two repos diverged. Features written to `apex/ios` while working in the apex server context never synced to `apexchat-ios`. Build 1.0(1) shipped to TestFlight missing ConnectionProfilesView, SubscriptionView, MessageBubble "Show more", and notification fixes as a result.

**Deployment target:** iOS 26.4 (prebuilt Swift modules only exist for 26.4 in Xcode 26.4).
