LocalChat v2 follow-up fixes applied in `scripts/localchat.py`.

Changes:
- Extended the `resumeConnection()` wait-for-open window from 5s to 15s and added a timeout debug log so slow cold reconnects after iOS page eviction do not give up early.
- Added connection timing in `connect()` with `ws opened in Xms` logging for TLS/WebSocket handshake diagnosis.
- Kept the existing fresh-boot restore path and made it explicit in `onopen` by logging the `sessionStorage.streamingChatId` state before reattaching to the active stream.
- Hardened the `pageshow` handler so bfcache restores always trigger resume logic and non-bfcache `pageshow` also forces reconnect when the WebSocket is already dead.

Verification:
- `python3 -m py_compile scripts/localchat.py` passed.

Relevant lines:
- `scripts/localchat.py:1386`
- `scripts/localchat.py:1455`
- `scripts/localchat.py:2389`
