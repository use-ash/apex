# Apex Troubleshooting Log

## Session: 2026-03-24

### Issue 1: WebSocket 403 after server restart
**Symptom:** `ws auth failed` spam, WebSocket rejects all connections after restart.
**Root cause:** `SESSION_SIGNING_KEY` was `secrets.token_hex(32)` — regenerated on every restart, invalidating all existing cookies.
**Fix 1:** Changed to deterministic key derived from password + file inode. **Failed** — inode changes when file is rewritten by editors.
**Fix 2:** Changed to `hashlib.sha256((PASSWORD + "apex-stable-salt").encode()).hexdigest()`. **Still failed** — old cookies from before the key change remain in browser.
**Fix 3:** Changed cookie to `httponly=False` so JS can read it dynamically via `document.cookie`. Added `getToken()` function. **Partially worked** — but embedded `{{WS_TOKEN}}` in HTML still used on initial load.
**Fix 4:** Added `wsAuthFailCount` — after 3 WS auth failures, redirect to `/login`. **Didn't help** because the redirect itself was cached.
**Final resolution:** Replaced entire auth system with mTLS (see Issue 6).

### Issue 2: SDK streaming — `'async for' requires __aiter__, got list`
**Symptom:** Image uploads hang, then error. SDK `receive_response()` returns a list instead of an async iterator.
**Root cause (initial theory):** Resumed sessions return lists. **Wrong** — it happens on fresh sessions too.
**Root cause (actual):** `query()` accepts `str | AsyncIterable[dict]`. We were passing a plain Python list of content blocks for image uploads. The SDK's `async for msg in prompt` fails because list isn't async-iterable.
**Fix:** Wrap content blocks in an async generator:
```python
async def _make_stream(blocks):
    yield {"type": "user", "message": {"role": "user", "content": blocks}}
```
**Important:** The yielded dict must be a full message `{"type": "user", "message": {...}}`, NOT bare content blocks. The SDK's `query()` writes each yielded item directly to the transport as a JSON line.

**Additional fix:** Async generators are single-use. On retry, must create a fresh generator from the saved blocks list (`_saved_blocks`).

### Issue 3: Stale SDK session hang
**Symptom:** SDK `client.query()` hangs indefinitely when resuming a session that no longer exists on the server.
**Root cause:** `_get_or_create_client()` uses the `claude_session_id` from the DB to resume. If that session expired or was from a different server restart, the CLI just hangs.
**Fix:** Added `asyncio.wait_for()` with 30s timeout on `query()` and 300s on `_stream_response()`. On failure, clears `claude_session_id` from DB and creates a fresh session.

### Issue 4: Mobile Safari file input not triggering
**Symptom:** Tapping the attach button (📎) does nothing on iOS Safari.
**Root cause:** iOS Safari doesn't reliably trigger `fileInput.click()` from a button's onclick handler when the input uses `display:none`.
**Fix:** Wrapped the file input inside a `<label class="btn-compose">` element. The label acts as a native click proxy for the enclosed input. Removed the JS `.click()` handler — label handles it natively.

### Issue 5: Service worker fetch errors with self-signed cert
**Symptom:** `FetchEvent.respondWith received an error: TypeError: Load failed`
**Root cause:** The service worker intercepted all fetch requests and re-fetched them. With a self-signed cert, the re-fetch fails.
**Fix:** Changed service worker to a no-op: `"// no-op service worker"`. iOS keyboard dictation handles voice input natively.

### Issue 6: mTLS — browser doesn't send client cert for WebSocket
**Symptom:** After switching to mTLS (`ssl_cert_reqs=ssl.CERT_REQUIRED`), the HTML page loads (GET / returns 200) but WebSocket never connects. No `/ws` requests in server logs. Zero JS errors.
**Root cause:** Browsers don't send client certificates on WebSocket upgrade requests when using `wss://`. The TLS handshake for the WebSocket connection fails silently because the browser doesn't present the cert. This is a known browser limitation — confirmed by testing: `websockets.connect()` from Python with explicit cert works, but browsers don't.
**Fix:** Changed to `ssl_cert_reqs=ssl.CERT_OPTIONAL`. The server still accepts client certs and verifies them against the CA, but doesn't reject connections without one. Network-level access control (WireGuard VPN) provides the security boundary instead.

### Issue 7: No debug output in tmux
**Symptom:** Server runs but no debug-level HTTP/WebSocket logging in the tmux pane.
**Root cause:** `uvicorn.run()` was changed to use `log_level=os.environ.get("APEX_LOG_LEVEL", "info")` which defaults to `info`. The launch script doesn't set the env var.
**Fix:** To get debug output, add `export APEX_LOG_LEVEL=debug` to `launch_apex.sh` or run manually with that env var.

### Issue 8: Tool events and thinking not persisted to DB
**Symptom:** After phone lock/unlock, chat history loads but tool blocks and thinking sections are missing.
**Root cause:** When the phone disconnects mid-stream (`WebSocketDisconnect`), `_stream_response()` returns early with partially populated `result_info`. The save path (`_save_message()`) after it tries to send `stream_end` which also fails.
**Fix:** Wrapped `stream_end` send in try/except. The `_save_message()` call now executes regardless of WebSocket state, saving whatever was accumulated before disconnect.

### Issue 9: Formatting lost on reload
**Symptom:** Live streaming shows markdown formatting. After reload from DB history, formatting is plain text.
**Root cause:** History reload used `escHtml(m.content)` instead of calling `renderMarkdown()`.
**Fix:** Changed history reload to create a `.bubble` element, set `textContent`, then call `renderMarkdown(bubble)`. Also enhanced `renderMarkdown()` to support headers, bullet lists, numbered lists, bold, italic, and code blocks with proper extraction/protection.

### Issue 10: Messages buffered instead of streaming
**Symptom:** During tool-use chains, the phone shows nothing until the entire response completes.
**Root cause:** `_stream_response()` collected ALL messages into a list first (`msgs = []; async for m in response: msgs.append(m)`) before iterating.
**Fix:** Changed to stream directly: normalize the response to an async iterator, then `async for msg in response:` processes and sends each event to the WebSocket immediately.

## Architecture Decisions

### Auth evolution
1. **Password + cookie + session** (original) → broken on restarts
2. **Deterministic signing key** → broken when key derivation inputs change
3. **httponly=False + JS cookie reading** → stale embedded tokens
4. **mTLS CERT_REQUIRED** → browsers don't send certs for WebSocket
5. **mTLS CERT_OPTIONAL** → current. VPN is the access control.

### SDK quirks (claude-agent-sdk)
- `query()` signature: `str | AsyncIterable[dict]`. Lists are NOT AsyncIterable.
- Each yielded dict must be a complete message: `{"type": "user", "message": {"role": "user", "content": [blocks]}}`
- `receive_response()` returns `AsyncIterator` per type hints, but may return a list at runtime
- Resumed sessions can hang indefinitely if the session ID is stale
- The SDK spawns a CLI process: `claude --output-format stream-json --input-format stream-json`
- Each process uses ~360MB RAM idle

### TLS certificate chain
```
state/ssl/
├── ca.crt + ca.key          — Apex Local CA (root, 5yr)
├── apex.crt + .key          — Server cert (SANs: your-vpn-ip, your-lan-ip, 127.0.0.1)
├── client.crt + .key        — Client cert (CN=apex-client, clientAuth EKU)
├── client.p12               — PKCS#12 bundle for iOS (password: apex)
└── ext.cnf                  — Extension config for cert generation
```
