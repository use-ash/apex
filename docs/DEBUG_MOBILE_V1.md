# Apex Mobile Reconnection — Debug Report

**Date:** 2026-03-24
**File:** `server/apex.py` (single-file server, ~2260 lines)
**Platform:** iOS Safari PWA over WireGuard VPN + mTLS

## Context

Apex is a single-file FastAPI server embedding all HTML/JS/CSS inline. It streams Claude SDK responses over a WebSocket. On iOS, locking the phone kills the WebSocket and suspends all JavaScript. The goal is seamless resume: unlock the phone and pick up where you left off, including mid-stream responses.

## Architecture (Relevant Parts)

### Server-Side
- **`_chat_ws` registry** (line ~433): `dict[str, WebSocket]` — maps `chat_id` to current WebSocket. The `_stream_response()` function looks up the WS from this registry on every event emission via `_send()`, so if the client reconnects mid-stream, new events route to the new socket.
- **`_chat_locks`** (line ~432): `dict[str, asyncio.Lock]` — held while a stream is running. Used by the `attach` handler to detect if a stream is still active.
- **`attach` action** (line ~825): Client sends `{action: 'attach', chat_id: ...}` after reconnecting. Server registers the new WS, checks if the chat lock is held (stream active), and responds with either `stream_reattached` or `attach_ok`.
- **`_send()` closure** (line ~532): Nested function inside `_stream_response()`. Looks up `_chat_ws.get(chat_id)` on every call. If the WS is dead/missing, silently drops the event. **No buffering.**

### Client-Side
- **`onclose` handler** (line ~1322): Sets `streaming = false`, clears `currentBubble`, schedules `reconnectTimer = setTimeout(connect, 3000)`.
- **`visibilitychange` handler** (line ~2196): Fires when phone unlocks. Force-closes old WS, calls `connect()`, polls for OPEN state, then sends `attach`.
- **`sessionStorage`**: Stores `streamingChatId` (set on `stream_start`, cleared on `stream_end`) and `currentChatId` (set when chat is selected). Survives `onclose` clearing the JS `streaming` variable.
- **`resumeHandledExternally` flag** (line ~1286): Set by `visibilitychange` to prevent `onopen` from also calling `selectChat`.

## Bugs Found

### Bug 1: Manual refresh required after unlock (HIGH)

**Symptom:** After locking and unlocking the phone, the green dot comes back (WS reconnects) but the chat content is stale. User must tap the refresh button to see current state.

**Root cause — race condition between `onclose` and `visibilitychange`:**

When iOS kills the WebSocket:
1. `onclose` fires FIRST (while phone is still locking):
   - Sets `streaming = false`, `currentBubble = null`
   - Schedules `reconnectTimer = setTimeout(connect, 3000)`
   - JS is then **suspended** by iOS — the timer freezes

2. When phone unlocks, JS resumes and TWO things fire ~simultaneously:
   - The frozen `reconnectTimer` (3s elapsed during suspend) → calls `connect()`
   - `visibilitychange` event → closes old WS, calls `connect()` again

3. Both calls to `connect()` create new WebSocket objects. Each does `ws = socket`, so the second one wins. But `visibilitychange` handler's `setInterval` polling loop references `ws`, which is now the socket from the reconnectTimer's `connect()`, not its own.

4. The `visibilitychange` handler sets `resumeHandledExternally = true`, but the reconnectTimer's `connect()` → `onopen` runs first (before `visibilitychange` can set the flag), calling `selectChat()` with no stream awareness.

**Proposed fix:**
- In `visibilitychange`, clear the `reconnectTimer` BEFORE calling `connect()`:
  ```javascript
  clearTimeout(reconnectTimer);  // <-- kill the onclose timer
  if (ws) { try { ws.close(); } catch(e) {} }
  connect();
  ```
- Or better: don't reconnect in `onclose` at all when the page isn't visible:
  ```javascript
  socket.onclose = (e) => {
    ...
    if (document.visibilityState === 'visible') {
      reconnectTimer = setTimeout(connect, 3000);
    }
    // If hidden (phone locked), let visibilitychange handle reconnect
  };
  ```

### Bug 2: Stream content lost after lock/unlock (MEDIUM)

**Symptom:** User locks phone while Claude is streaming (thinking, tool use, text). After unlocking and refreshing, the streamed content is gone — only the user message appears, or a partial response.

**Root cause — events dropped with no buffer:**

The `_send()` function in `_stream_response()` looks up the WebSocket from `_chat_ws.get(chat_id)`. When the WS dies:
- `_safe_ws_send_json()` fails and `_send()` pops the dead WS from the registry
- Subsequent events find no WS (`_chat_ws.get(chat_id)` returns `None`) and silently return
- These events are **permanently lost** — no buffer, no replay

When the client reconnects and gets `stream_reattached`, it calls `selectChat()` which reloads from the DB. But the DB only stores the **final result** when the turn completes (after `ResultMessage`). Mid-stream content (thinking blocks, partial text, tool events) is only in memory during streaming.

**If the stream finishes while disconnected:** The result IS saved to DB. Client gets `attach_ok` → reloads from DB → sees complete response. This path works correctly.

**If the stream is still running when client reconnects:** Client gets `stream_reattached` → calls `selectChat()` (shows DB state, which has the user message but not the assistant response yet) → new streaming events create a fresh bubble for remaining content. **Events emitted while disconnected are lost.** User sees a gap.

**Proposed fix options:**
1. **Event buffer (recommended):** Server-side ring buffer per chat (last N events). On `stream_reattached`, replay buffered events before resuming live stream. Simple, bounded memory.
   ```python
   _stream_buffer: dict[str, list[dict]] = {}  # chat_id -> recent events

   async def _send(payload: dict) -> None:
       _stream_buffer.setdefault(chat_id, []).append(payload)
       if len(_stream_buffer[chat_id]) > 200:
           _stream_buffer[chat_id] = _stream_buffer[chat_id][-200:]
       ws = _chat_ws.get(chat_id)
       if not ws:
           return
       ...
   ```
   On `attach` when `stream_running`:
   ```python
   # Replay buffered events
   for event in _stream_buffer.get(attach_id, []):
       await websocket.send_json(event)
   await websocket.send_json({"type": "stream_reattached", "chat_id": attach_id})
   ```

2. **Accept the gap:** On reattach, just show "⏳ Response in progress..." and let remaining events flow in. Final result will be saved to DB. Less ideal UX but simpler.

### Bug 3: Stop button stuck in red/stop state (LOW — follows from Bug 1)

**Symptom:** After unlocking, the send button shows the red stop circle (streaming indicator) even though streaming may have finished.

**Root cause:** Follows from Bug 1. If the reconnect flow doesn't properly send `attach`, the client never receives `attach_ok` or `stream_end`, so:
- `sessionStorage.streamingChatId` is never cleared
- `streaming` stays truthy in the UI logic
- `updateSendBtn()` renders the stop button

**Fix:** Resolving Bug 1 fixes this. Additionally, add a safety timeout on the client:
```javascript
// Safety: if streaming flag is set but no events received in 30s, force clear
let streamWatchdog = null;
// In stream_reattached handler:
streamWatchdog = setTimeout(() => {
  if (streaming) {
    dbg('stream watchdog: no events in 30s, clearing streaming state');
    streaming = false;
    sessionStorage.removeItem('streamingChatId');
    currentBubble = null;
    updateSendBtn();
    if (currentChat) selectChat(currentChat).catch(() => {});
  }
}, 30000);
```

## What Already Works

- **`_chat_ws` registry pattern:** Correctly decouples the stream from a specific WS instance. If a new WS is registered mid-stream, subsequent events flow to it.
- **`sessionStorage` for streaming state:** Survives `onclose` clearing the JS variables. Correct approach.
- **`attach` server handler:** Properly checks lock state (not just old WS presence) to determine if stream is active.
- **`_send()` dynamic lookup:** Correct pattern — looks up WS per-event, not captured once.
- **Heartbeat/ping-pong:** 5s interval, 15s zombie detection. Works.
- **DB persistence of final results:** Complete responses are always saved. Only mid-stream content is at risk.

## Fix Priority

1. **Bug 1** (race condition) — Fix first. This is why manual refresh is needed.
2. **Bug 2** (event buffer) — Fix second. This recovers mid-stream content.
3. **Bug 3** (watchdog) — Defensive cleanup, add last.

## Test Plan

After fixes:
1. Open chat, send message, verify normal streaming works
2. Lock phone for 5s during idle → unlock → should auto-reconnect, show green dot, show correct chat (no refresh needed)
3. Send message, lock phone while Claude is streaming thinking → wait 15s → unlock → should see thinking content appear, stream resumes
4. Send message, lock phone, wait until stream would have finished (~30s) → unlock → should show complete response from DB
5. Chrome on Mac Studio open to same chat simultaneously — verify no interference
6. Repeat each test 3x to confirm no intermittent races

## Additional Issues (from CLI session troubleshooting)

### Bug 4: Markdown formatting lost on reload (MEDIUM)

**Symptom:** Live streaming shows formatted markdown (headers, code blocks, lists). After reload from DB history, formatting is plain text.

**Root cause:** The `renderMarkdown()` function is called during live streaming (on `stream_end`) but the history reload path may not call it consistently on all message bubbles.

**Fix:** Ensure every assistant message bubble in the history reload path calls `renderMarkdown(bubble)` after setting `textContent`.

### Bug 5: PWA has no native refresh mechanism (LOW)

**Symptom:** When opened as a PWA bookmark (Add to Home Screen), iOS provides no URL bar, no pull-to-refresh, no reload button. The only way to refresh is to close the app entirely and reopen.

**Status:** Partially fixed — a refresh button (↻) was added to the top bar, and `visibilitychange` + `pageshow` handlers were added. But pull-to-refresh may not trigger reliably if the messages div isn't at scroll position 0.

### Bug 6: mTLS status indicator stale (LOW)

**Symptom:** The mode badge shows "mTLS" in red after a disconnect, even though the connection is actually working. The badge reflects auth status from initial page load, not current connection state.

**Fix:** Update the mode badge color based on WebSocket connection state, not just initial auth mode.

## Implementation Notes

- All fixes are in `server/apex.py` — single file, inline JS/CSS/HTML
- Server runs under uvicorn with mTLS (`ssl_cert_reqs=ssl.CERT_OPTIONAL`)
- The `_send()` closure pattern is correct — keep it, just add the event buffer
- `sessionStorage` is correct for cross-disconnect state — keep it
- The `_chat_ws` registry pattern is correct — keep it, it already handles mid-stream reconnect
- Bug 1 fix is the highest leverage — it eliminates the need for manual refresh in most cases
- Bug 2 fix (event buffer) is the most complex but gives the best UX

## File References

All changes in `server/apex.py`:
- Server-side registry: lines 430-435
- `_stream_response` + `_send()`: lines 507-630
- `attach` handler: lines 825-845
- Client `connect()` + `onclose`: lines 1288-1351
- Client `handleEvent` stream handlers: lines 1444-1500
- Client `visibilitychange`: lines 2196-2236
