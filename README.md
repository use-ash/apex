# Apex

Private Claude chat interface — native iOS client (ApexChat) + Python server. Runs over WireGuard VPN with mTLS client certificate auth.

## Structure

```
apex/
├── server/           # FastAPI + WebSocket + Claude Agent SDK
│   ├── apex.py       # Single-file server (port 8300)
│   └── launch_apex.sh
├── ios/              # SwiftUI native client (ApexChat)
├── production/       # Deployment configs, cron, systemd
├── docs/             # Design docs, debug logs, plans
└── state/            # Runtime data (not committed)
    ├── apex.db       # SQLite chat database
    ├── ssl/          # mTLS certs (ca, server, client)
    └── uploads/      # Temporary file uploads
```

## Quick Start

```bash
# Server
cd server && bash launch_apex.sh

# State directory must exist with SSL certs
# See docs/TROUBLESHOOTING.md for cert generation
```

## Architecture

- **Server:** FastAPI, persistent Claude SDK sessions, SQLite, WebSocket streaming
- **iOS Client (ApexChat):** SwiftUI, URLSessionWebSocketTask, mTLS, background survival
- **Auth:** mTLS client certificates over WireGuard VPN
- **Protocol:** JSON over WebSocket (see docs/IOS_NATIVE_PLAN.md for full spec)
