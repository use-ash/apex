# LocalChat Mobile Reconnection — Debug Report V2

**Date:** 2026-03-24
**File:** `scripts/localchat.py` (~2444 lines after Codex v1 fixes)
**Platform:** iOS Safari PWA over WireGuard VPN + mTLS
**Prereq:** Read `debug_localchat.md` for full architecture and Bugs 1-6.

## V1 Fix Results (Codex pass 1)

Codex applied fixes for Bugs 1-6. Live testing results:

| Test | Result |
|------|--------|
| 5s lock/unlock (idle) | **PASS** — auto-reconnects, green dot, correct chat, no manual refresh |
| 15s lock/unlock (idle) | **PASS** — same as above |
| 30s lock/unlock (idle) | **FAIL** — must hit refresh button manually to restore session |
| Mid-stream lock (observed) | **Partial** — stop button stuck red, content from before lock missing |

**Bugs 1-3 are improved but not fully resolved for longer lock durations (≥30s).**
Bugs 4-6 (markdown formatting, PWA refresh, mTLS badge) were addressed by Codex.

## New Bug: 30-Second Lock Failure (HIGH)

### Symptom

Locking the phone for ≥30 seconds requires a manual tap of the refresh button (↻) to restore the session. The 5s and 15s tests pass cleanly.

### Root Cause: iOS Page Eviction

After ~20-25 seconds of background suspension, iOS **evicts the page from memory** entirely. This changes the reconnection mechanism:

| Lock Duration | iOS Behavior | Recovery Path |
|---|---|---|
| 5-15s | Page suspended in memory, JS frozen | `visibilitychange` fires on unlock → `resumeConnection()` → works |
| 20-30s+ | Page evicted from memory | Full reload OR bfcache restore via `pageshow` → different code path |

### Three Compounding Failure Mechanisms

#### Mechanism 1: 5-Second Polling Timeout (Primary)

In `resumeConnection()` (~line 1407):
```javascript
const waitForOpen = setInterval(() => {
  if (waitDone) return;
  if (ws && ws.readyState === WebSocket.OPEN) {
    waitDone = true;
    clearInterval(waitForOpen);
    attachToStream(ws, resumeChat, {...});
  }
}, 100);
setTimeout(() => {
  waitDone = true;
  clearInterval(waitForOpen);
}, 5000);  // Gives up after 5 seconds
```

After a page eviction, the cold TLS/WebSocket handshake over VPN can take longer than 5 seconds. The polling loop gives up before the connection is established. `attachToStream()` is never called.

**Fix:** Extend timeout from 5s to 15s:
```javascript
setTimeout(() => {
  waitDone = true;
  clearInterval(waitForOpen);
}, 15000);  // was 5000
```

#### Mechanism 2: `visibilitychange` Never Fires After Eviction

When iOS evicts the page, `visibilitychange` doesn't fire on restore. Instead:
- **Full reload:** Page starts fresh from `connect()` at boot — no `resumeConnection()` called
- **bfcache restore:** `pageshow` event fires with `e.persisted = true`

The `pageshow` handler (~line 2384) does call `resumeConnection('pageshow')`, but if the page was fully reloaded (not bfcache), no resume logic runs — it's just a fresh boot with no awareness that a stream was active.

**Fix:** On fresh boot, check `sessionStorage.streamingChatId` and send `attach` if set. This already exists in the `onopen` handler (~line 1311) but verify it works after a full reload:
```javascript
// In onopen, after ensureInitialized:
const streamingChatId = sessionStorage.getItem('streamingChatId');
if (streamingChatId && streamingChatId === currentChat) {
  socket.send(JSON.stringify({action: 'attach', chat_id: currentChat}));
}
```

#### Mechanism 3: `onclose` Reconnect Skipped When Hidden

The v1 fix correctly skips the reconnect timer when the page is hidden:
```javascript
if (document.visibilityState === 'visible') {
  reconnectTimer = setTimeout(connect, 3000);
} else {
  dbg(' ws closed while hidden; waiting for visibilitychange');
}
```

But if the page is evicted, `visibilitychange` never fires to pick up the slack. The page reloads cold with no pending reconnect.

**Fix:** Detect page eviction explicitly in `pageshow`:
```javascript
window.addEventListener('pageshow', (e) => {
  if (e.persisted && (!ws || ws.readyState !== WebSocket.OPEN)) {
    dbg('pageshow: bfcache but WS dead, forcing reconnect');
    resumeConnection('pageshow');
  } else if (e.persisted) {
    resumeConnection('pageshow');
  }
});
```

### Additional Fix: Connection Timing Logs

Add timing to `connect()` to diagnose slow TLS handshakes:
```javascript
function connect() {
  const connectStart = Date.now();
  const socket = new WebSocket(ws_url);
  socket.onopen = async () => {
    dbg(`ws opened in ${Date.now() - connectStart}ms`);
    // ...
  };
}
```

This will tell us if the 5s timeout is genuinely too short or if there's a deeper TLS issue.

## Fix Priority (V2)

1. **Extend polling timeout to 15s** — simplest fix, highest impact for 30s lock case
2. **Verify `onopen` attach logic works on full reload** — may already work, needs testing
3. **Harden `pageshow` handler** — detect dead WS and force reconnect
4. **Add connection timing logs** — diagnostic, helps tune the timeout

## Updated Test Plan

After V2 fixes:
1. ~~5s lock/unlock~~ — PASS (v1)
2. ~~15s lock/unlock~~ — PASS (v1)
3. **30s lock/unlock (idle)** — should auto-reconnect without manual refresh
4. **45s lock/unlock (idle)** — push the boundary, verify bfcache vs full reload
5. **60s lock/unlock (idle)** — extreme case, likely full reload
6. **30s lock mid-stream** — lock while streaming, unlock, stream content should appear
7. Check Safari console (Mac) for `ws opened in Xms` timing after each test
8. Verify `sessionStorage.streamingChatId` is properly cleared in all paths

## Bug 7: Voice Button Removal Incomplete — JS Crash (HIGH)

**Symptom:** Red error banner across top of screen on iOS:
```
JS Error: TypeError: null is not an object (evaluating 'btn.classList') (line 788)
```

**Root cause:** Codex removed the voice button HTML element (`#voiceBtn`) and some voice code, but left behind `updateVoiceBtn()` and related functions that reference the removed element. `updateVoiceBtn()` is called from multiple places (`onopen`, `onclose`, `stream_end`, etc.) and crashes every time.

**Affected code (line ~1862):**
```javascript
function updateVoiceBtn() {
  const btn = document.getElementById('voiceBtn');
  btn.classList.toggle('recording', recording);  // CRASH — btn is null
  btn.classList.toggle('transcribing', transcribing);
  btn.disabled = streaming;
  btn.title = ...;
  btn.innerHTML = ...;
}
```

**Also still present (~line 1856):**
```javascript
function stopVoiceStream() {
  if (!mediaStream) return;
  mediaStream.getTracks().forEach(track => track.stop());
  mediaStream = null;
}
```

**Fix — two options:**

**Option A (minimal, safe):** Add null guard to `updateVoiceBtn()`:
```javascript
function updateVoiceBtn() {
  const btn = document.getElementById('voiceBtn');
  if (!btn) return;
  // ... rest unchanged
}
```

**Option B (thorough, recommended):** Remove ALL remaining voice code since the button is gone. Search for and remove:
- `updateVoiceBtn()` function and all call sites
- `stopVoiceStream()` function
- `recording`, `transcribing`, `mediaStream`, `mediaRecorder` variables
- `startRecording()`, `stopRecording()` functions (if present)
- Voice-related CSS (`.recording`, `.transcribing` classes)
- The `/api/transcribe` endpoint on the server side (if voice is permanently removed)
- Any `navigator.mediaDevices` references

**Call sites that invoke `updateVoiceBtn()` — each will crash:**
- `socket.onopen` (~line 1303)
- `socket.onclose` (~line 1329)
- `stream_end` handler (~line 1449)
- `stream_reattached` handler (~line 1462)
- `attach_ok` handler (~line 1478)
- Boot initialization (~line 2193)

**Priority:** HIGH — this crashes on every page load and every WS reconnect. It's the most visible bug right now.

## File References

All changes in `scripts/localchat.py`:
- `resumeConnection()`: ~line 1407 (polling timeout)
- `pageshow` handler: ~line 2384
- `connect()` + `onopen`: ~line 1288 (attach on fresh boot)
- `onclose`: ~line 1500 (hidden page skip)
- `updateVoiceBtn()`: ~line 1862 (voice crash)
- Voice code to remove: search `voice`, `recording`, `transcribing`, `mediaStream`, `whisper`
