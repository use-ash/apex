---
name: project_apex
description: Apex — local web chat for Claude Code over WireGuard. v1.2 shipped with persistent sessions, attachments, voice notes, PWA.
type: project
---

## Apex

Local web chat for Claude Code. Zero third-party data flow. Phone → WireGuard → Mac.

**Status:** v1.2 committed (`b70abe2`). Working from browser. Other session working on TLS + mobile fixes.

**File:** `server/apex.py` (single file, ~1700 lines)

**Architecture:** FastAPI + WebSocket + Claude Agent SDK (`ClaudeSDKClient`) for persistent multi-turn sessions. SQLite for chat/message storage. Embedded HTML/CSS/JS.

**Features shipped:**
- Persistent sessions via SDK (no subprocess respawning per turn)
- bcrypt auth + signed session cookies
- Streaming responses with thinking/tool blocks (collapsible)
- File attachments (images as base64 to Claude, text files by path)
- Voice notes (MediaRecorder → local Whisper transcription)
- Chat history with auto-titling
- PWA manifest (Add to Home Screen on iOS)
- Configurable model (default Sonnet, APEX_MODEL env var)
- Binds to 0.0.0.0 (WireGuard accessible)

**Known issues being addressed in other session:**
- TLS with local CA for HTTPS
- SDK streaming bugs
- Image upload format
- iOS Safari cookie fixes (httponly removed, dynamic WS_TOKEN)
- Session invalidation on restart (signing key stability)

**Env vars:** APEX_AUTH (required), APEX_HOST, APEX_PORT, APEX_MODEL, APEX_TRUSTED (legacy: LOCALCHAT_* also accepted)

**JS syntax lesson:** Embedded JS inside Python strings breaks when using nested quotes in innerHTML. Use `&quot;` for HTML attributes inside template literals. Always extract JS and run `node --check` before deploying.
