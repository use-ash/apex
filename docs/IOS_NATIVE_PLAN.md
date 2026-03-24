# LocalChat Swift — Native iOS Client Plan

**Status:** Planning
**Created:** 2026-03-24
**Problem:** iOS Safari PWA kills WebSocket after ~30s lock. Native app survives via URLSessionWebSocketTask + background modes.
**Approach:** Client-side only. Zero server changes. SwiftUI app speaks the existing LocalChat WebSocket + REST protocol.

---

## Why Native Beats PWA on iOS

| Scenario | PWA (Safari) | Native (SwiftUI) |
|---|---|---|
| 5–15s lock | JS frozen, resumes | App suspended, socket alive |
| 30s lock | Page evicted, WS dead | App suspended, WS alive (BGTask keepalive) |
| 60s+ lock | Full reload, sessionStorage may be gone | App wakes via BGTask, reconnects in <1s |
| Mid-stream lock | Buffer replay (if reconnect works) | Never disconnects, stream continues |
| Notification on complete | Not possible | Push via local notification when `result` arrives while backgrounded |

The native app eliminates the entire class of reconnection bugs. The server already has the protocol right — it's the client that can't stay alive.

---

## Architecture

```
┌─────────────────────────────────┐
│  SwiftUI App                    │
│                                 │
│  ┌───────────┐  ┌────────────┐  │
│  │ ChatView  │  │ SidebarView│  │
│  │ (messages)│  │ (chat list)│  │
│  └─────┬─────┘  └─────┬──────┘  │
│        │               │         │
│  ┌─────▼───────────────▼──────┐  │
│  │     ChatViewModel          │  │
│  │  - messages: [Message]     │  │
│  │  - streaming: Bool         │  │
│  │  - currentChatId: String?  │  │
│  └─────────────┬──────────────┘  │
│                │                 │
│  ┌─────────────▼──────────────┐  │
│  │     ConnectionManager      │  │
│  │  - URLSessionWebSocketTask │  │
│  │  - mTLS via SecIdentity    │  │
│  │  - auto-reconnect          │  │
│  │  - ping/pong heartbeat     │  │
│  └─────────────┬──────────────┘  │
│                │                 │
│  ┌─────────────▼──────────────┐  │
│  │     APIClient (REST)       │  │
│  │  - GET /api/chats          │  │
│  │  - POST /api/chats         │  │
│  │  - GET /api/chats/:id/msgs │  │
│  │  - POST /api/upload        │  │
│  │  - POST /api/transcribe    │  │
│  └────────────────────────────┘  │
└─────────────────────────────────┘
         │ wss://macstudio:8300/ws
         ▼
┌─────────────────────────────────┐
│  LocalChat Server (unchanged)   │
│  FastAPI + Claude Agent SDK     │
└─────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Connection & Chat List (MVP Boot)

**Goal:** App connects over mTLS, shows chat list, can select a chat and see history.

**Files:**
```
LocalChat/
├── LocalChatApp.swift              # @main, app lifecycle
├── Models/
│   ├── Chat.swift                  # Chat model (id, title, created_at, updated_at)
│   └── Message.swift               # Message model (id, role, content, tool_events, thinking, cost, tokens)
├── Network/
│   ├── ConnectionManager.swift     # WebSocket lifecycle, mTLS, reconnect
│   ├── APIClient.swift             # REST endpoints (chats, messages, upload)
│   └── TLSConfig.swift             # Load .p12 → SecIdentity, pin local CA
├── Views/
│   ├── SidebarView.swift           # Chat list + new chat button
│   └── ChatView.swift              # Message history (read-only this phase)
└── Info.plist                      # NSAppTransportSecurity exception for local CA
```

**Key implementation details:**

1. **mTLS Setup (`TLSConfig.swift`)**
   - Bundle `client.p12` and `ca.pem` in app
   - Load via `SecPKCS12Import` → extract `SecIdentity`
   - Custom `URLSessionDelegate` that provides client cert on challenge
   - Pin server cert against bundled CA (reject anything else)

2. **WebSocket (`ConnectionManager.swift`)**
   - `URLSessionWebSocketTask` (not Starscream — native handles TLS better)
   - Receive loop: recursive `.receive()` call pattern
   - Parse JSON → enum `ServerEvent` (all 9 types)
   - Auto-reconnect on `.close` / `.viabilityChanged` with exponential backoff (1s, 2s, 4s, max 15s)
   - Ping every 10s via `{"action": "ping"}`, expect pong within 15s

3. **REST (`APIClient.swift`)**
   - Shared `URLSession` with same mTLS delegate
   - Base URL from `UserDefaults` (default `https://macstudio.local:8300`)
   - All calls are async/await
   - JSON decoding with `ISO8601DateFormatter`

4. **Chat List (`SidebarView.swift`)**
   - Pull on launch: `GET /api/chats`
   - Tap → set `currentChatId`, load messages: `GET /api/chats/{id}/messages`
   - "New Chat" button → `POST /api/chats`, select it

**Acceptance:** App boots on iPhone over VPN, shows chat list, tap loads history with rendered messages.

---

### Phase 2: Send & Stream (Core UX)

**Goal:** Send messages, see Claude's streaming response with text + thinking + tool blocks.

**Files (new/modified):**
```
├── Models/
│   └── ServerEvent.swift           # Enum for all WS event types
├── ViewModels/
│   └── ChatViewModel.swift         # State machine: idle → sending → streaming → complete
├── Views/
│   ├── ChatView.swift              # + compose bar, streaming bubble, auto-scroll
│   ├── MessageBubble.swift         # User/assistant bubbles with markdown
│   ├── ThinkingBlock.swift         # Collapsible thinking content
│   ├── ToolBlock.swift             # Collapsible tool_use + tool_result
│   └── ComposeBar.swift            # Text input + send button + attachment
```

**Key implementation details:**

1. **State Machine (`ChatViewModel`)**
   ```
   idle ──send──▶ sending ──stream_start──▶ streaming ──result──▶ complete ──▶ idle
                     │                          │
                     ▼                          ▼
                   error                      stop (interrupt)
   ```
   - `send`: WS `{"action":"send", "chat_id":..., "prompt":...}`
   - During `streaming`: accumulate `text` chunks, `thinking` chunks, `tool_use`/`tool_result` events
   - On `result`: finalize message, save cost/tokens, render markdown
   - On `stream_end`: clear streaming state

2. **Message Model (in-memory during stream)**
   - Assistant message built incrementally:
     - `content: String` — accumulated text chunks
     - `thinkingBlocks: [ThinkingBlock]` — each thinking event appends
     - `toolEvents: [ToolEvent]` — tool_use creates, tool_result fills
   - On `result`, snapshot to final `Message` and add to array

3. **Markdown Rendering**
   - Use `AttributedString(markdown:)` (iOS 15+) for basic markdown
   - Code blocks: monospace font with background
   - If richer rendering needed later: swap in `swift-markdown-ui` package

4. **Compose Bar**
   - Text field + Send button (disabled during streaming)
   - Stop button appears during streaming → sends `{"action":"stop"}`
   - Keyboard avoidance via `.scrollDismissesKeyboard(.interactively)`

**Acceptance:** Full conversation flow. Send message, see streaming response with thinking/tool blocks, cost footer shown.

---

### Phase 3: Background Survival (The Whole Point)

**Goal:** App maintains connection through lock/unlock cycles. Never lose a stream.

**Files (new/modified):**
```
├── Network/
│   ├── ConnectionManager.swift     # + BGTaskScheduler, NWPathMonitor
│   └── BackgroundManager.swift     # Background task registration & scheduling
├── LocalChatApp.swift              # + scenePhase handling, BGTask registration
```

**Key implementation details:**

1. **Scene Phase Handling**
   ```swift
   @Environment(\.scenePhase) var scenePhase

   .onChange(of: scenePhase) { phase in
       switch phase {
       case .active:
           // Verify WS is alive, reconnect if needed
           connectionManager.ensureConnected()
           // If was streaming, auto-attach
           if let chatId = streamingChatId {
               connectionManager.send(.attach(chatId: chatId))
           }
       case .inactive:
           // Transitioning — no action
           break
       case .background:
           // Schedule BGAppRefreshTask to wake before kill
           BackgroundManager.scheduleKeepAlive()
       }
   }
   ```

2. **Background Task Keepalive (`BackgroundManager.swift`)**
   - Register `BGAppRefreshTaskRequest` with `earliestBeginDate` = 25 seconds
   - When woken: ping WebSocket, schedule next keepalive
   - This keeps the app in "recently active" state, iOS is less aggressive about killing it
   - **Not guaranteed** but buys significant extra time vs PWA (minutes vs seconds)

3. **NWPathMonitor (Network Change Detection)**
   ```swift
   let monitor = NWPathMonitor()
   monitor.pathUpdateHandler = { path in
       if path.status == .satisfied && !self.isConnected {
           self.reconnect()
       }
   }
   ```
   - Catches VPN reconnection (WireGuard comes back after lock)
   - Catches WiFi → cellular transitions

4. **Reconnect-on-Wake Flow**
   ```
   App wakes → scenePhase .active
     ├── WS alive? → ping, continue
     └── WS dead? → reconnect (15s timeout for TLS over VPN)
           ├── Was streaming? → attach, get buffer replay
           └── Not streaming? → attach_ok, reload from DB
   ```

5. **Local Notifications**
   - If `result` event arrives while `scenePhase == .background`:
     ```swift
     let notification = UNMutableNotificationContent()
     notification.title = "Claude"
     notification.body = "Response ready"  // or first 100 chars
     ```
   - User taps notification → opens app to that chat

**Acceptance:** Lock phone for 30s, 60s, 2 min during active stream. Unlock → stream continues or has completed with notification. No manual refresh ever needed.

---

### Phase 4: Attachments & Voice

**Goal:** Feature parity with PWA for file sharing and voice input.

**Files (new/modified):**
```
├── Views/
│   ├── ComposeBar.swift            # + attachment picker, voice button
│   ├── ImagePicker.swift           # PHPickerViewController wrapper
│   └── VoiceRecorder.swift         # AVAudioRecorder → webm/mp4 → /api/transcribe
```

**Key implementation details:**

1. **Image Attachments**
   - `PHPickerViewController` for photo selection
   - Upload via `POST /api/upload` (multipart form data)
   - Show thumbnail in compose bar before send
   - Include attachment IDs in `send` action

2. **File Attachments**
   - `UIDocumentPickerViewController` for file selection
   - Same upload flow, supported types match server whitelist

3. **Voice Input**
   - `AVAudioRecorder` → record to m4a (AAC)
   - Upload to `POST /api/transcribe`
   - Insert transcribed text into compose bar
   - Show recording indicator with waveform

**Acceptance:** Can send photos and files. Can record voice and get transcription inserted.

---

### Phase 5: Polish

**Goal:** Production-quality UX.

- **Chat management:** Swipe to delete, rename chats
- **Search:** Search across chat messages (local SQLite cache or server-side)
- **Settings screen:** Server URL, export/import .p12, connection status indicator
- **Haptics:** Subtle haptic on send, on stream complete
- **Appearance:** Dark/light mode, dynamic type support
- **iPad:** Split view (sidebar always visible)
- **Share extension:** Share text/images/URLs directly to LocalChat

---

## Protocol Reference (Quick Card)

### WebSocket Messages: Client → Server

| Action | Payload | When |
|---|---|---|
| `ping` | `{}` | Every 10s |
| `attach` | `{chat_id}` | On connect/reconnect if have active chat |
| `send` | `{chat_id, prompt, attachments?}` | User sends message |
| `stop` | `{chat_id}` | User taps stop |

### WebSocket Messages: Server → Client

| Type | Key Fields | Client Action |
|---|---|---|
| `pong` | — | Reset ping timer |
| `stream_start` | `chat_id` | Set streaming=true, show cursor |
| `text` | `text` | Append to message bubble |
| `thinking` | `text` | Append to thinking block |
| `tool_use` | `id, name, input` | Show tool block |
| `tool_result` | `tool_use_id, content, is_error` | Fill tool result |
| `result` | `cost_usd, tokens_in, tokens_out, session_id` | Finalize message, show cost |
| `stream_end` | `chat_id` | Clear streaming state |
| `stream_reattached` | `chat_id` | Buffer replay done, stream continues |
| `attach_ok` | `chat_id` | No active stream, reload from DB |
| `stream_complete_reload` | `chat_id` | Stream finished while away, reload |
| `chat_updated` | `chat_id, title` | Update sidebar title |
| `error` | `message` | Show error toast |
| `system` | `subtype, model` | Store model info |

### REST Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/chats` | List chats |
| POST | `/api/chats` | Create chat |
| GET | `/api/chats/{id}/messages` | Chat history |
| POST | `/api/upload` | Upload attachment |
| POST | `/api/transcribe` | Voice → text |
| GET | `/health` | Server status |

---

## Estimated Effort

| Phase | Effort | Depends On |
|---|---|---|
| Phase 1: Connection & Chat List | 2–3 sessions | — |
| Phase 2: Send & Stream | 2–3 sessions | Phase 1 |
| Phase 3: Background Survival | 1–2 sessions | Phase 2 |
| Phase 4: Attachments & Voice | 1–2 sessions | Phase 2 |
| Phase 5: Polish | Ongoing | Phase 1–4 |

**Total to usable MVP (Phases 1–3): ~6–8 sessions**

Phase 3 is the payoff — once that works, the lock/unlock problem is solved permanently.

---

## Open Questions

1. **Xcode project location:** `~/Developer/LocalChat/` or inside openclaw workspace?
2. **Cert bundling vs runtime import:** Bundle .p12 in app (simpler) or let user import via Files (more flexible for rotation)?
3. **Local message cache:** Mirror server DB in local CoreData/SwiftData for offline viewing? Or always fetch from server (simpler, we're always on VPN anyway)?
4. **Minimum iOS version:** iOS 16 (SwiftUI improvements, NavigationSplitView) or iOS 17 (Observable macro)?
