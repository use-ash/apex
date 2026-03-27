# Apex — Issues Resolved

Running tracker of bugs, misconfigurations, and edge cases fixed during development.
Each entry becomes a configuration note, test case, or FAQ item for the OSS release.

Format: `[component] title` — what broke, why, how it was fixed.

---

## Server / Core

### #1 — [server] WebSocket 403 after restart
**When:** 2026-03-24 &bull; **Component:** auth
**Symptom:** All WebSocket connections rejected after server restart.
**Root cause:** Session signing key used `secrets.token_hex()` — regenerated every restart, invalidating all cookies.
**Fix:** Replaced cookie/session auth entirely with mTLS (CERT_OPTIONAL + VPN).
**OSS note:** First-run setup must generate stable signing key or use mTLS. Document the auth model.

### #2 — [server] SDK streaming fails on image uploads
**When:** 2026-03-24 &bull; **Component:** sdk-integration
**Symptom:** Image uploads hang, then `'async for' requires __aiter__` error.
**Root cause:** `query()` expects `str | AsyncIterable[dict]`, but image content blocks were passed as a plain list.
**Fix:** Wrap content blocks in an async generator. Each yielded dict must be a full message `{"type": "user", "message": {...}}`.
**OSS note:** Document SDK input contract. Add type check / helpful error if user passes a list.

### #3 — [server] Stale SDK session hangs indefinitely
**When:** 2026-03-24 &bull; **Component:** sdk-integration
**Symptom:** `client.query()` hangs forever when resuming an expired session.
**Root cause:** SDK resumes with stale `claude_session_id` from DB; CLI process just hangs.
**Fix:** `asyncio.wait_for()` with 30s timeout on `query()`, 300s on `_stream_response()`. On timeout, clear session ID and create fresh.
**OSS note:** Must document session lifecycle. Add health check / TTL for stored session IDs.

### #4 — [server] Tool events lost on phone disconnect
**When:** 2026-03-24 &bull; **Component:** persistence
**Symptom:** After phone lock/unlock, tool blocks and thinking sections missing from history.
**Root cause:** `WebSocketDisconnect` during `_stream_response()` caused early return before `_save_message()`.
**Fix:** Wrapped `stream_end` send in try/except; `_save_message()` executes regardless of WS state.
**OSS note:** Streaming save must be disconnect-resilient. Test with network interrupts.

### #5 — [server] Messages buffered instead of streaming
**When:** 2026-03-24 &bull; **Component:** streaming
**Symptom:** During tool-use chains, nothing appears until entire response completes.
**Root cause:** Response collected into list first before iterating.
**Fix:** Stream directly via `async for msg in response:` — send each event to WS immediately.
**OSS note:** Default behavior must be true streaming. Never buffer-then-send.

### #6 — [server] mTLS blocks WebSocket in browsers
**When:** 2026-03-24 &bull; **Component:** tls
**Symptom:** Page loads but WS never connects. No JS errors.
**Root cause:** Browsers don't send client certs on WebSocket upgrade (known limitation).
**Fix:** Changed to `CERT_OPTIONAL`. VPN provides the access control boundary.
**OSS note:** Document that mTLS CERT_REQUIRED is incompatible with browser WebSocket. Recommend CERT_OPTIONAL + network-level access control.

### #7 — [server] Compaction fires Stop hook → false death alerts
**When:** 2026-03-26 &bull; **Component:** hooks
**Symptom:** Telegram alerts for session crashes that were actually compaction events.
**Root cause:** Claude Code fires Stop hook on compaction (context window trim), not just session end.
**Fix:** Added `pgrep` + parent-process checks in `postmortem.py` — if session still alive, log as `compaction` instead of crash.
**OSS note:** Any hook-based monitoring must distinguish compaction from termination.

### #8 — [server] Codex sessions trigger false crash alerts
**When:** 2026-03-27 &bull; **Component:** hooks
**Symptom:** 3 false "abnormal termination" Telegram alerts in 10 minutes — all from Codex sessions.
**Root cause:** Codex adapter passed Codex transcripts (different format: `event_msg`, `response_item`) through Claude-format `analyze_transcript()`. No `stop_reason` field → classified as abnormal.
**Fix:** Added `_is_codex_clean_exit()` in `postmortem_adapter.py` — checks for `task_complete` event in transcript tail. Clean exits logged as `codex_exit` without alerting.
**OSS note:** Multi-agent postmortem must be format-aware. Each agent backend needs its own clean-exit detection.

## iOS Client

### #9 — [ios] File input doesn't trigger on Mobile Safari
**When:** 2026-03-24 &bull; **Component:** ui
**Symptom:** Tapping attach button does nothing on iOS.
**Root cause:** iOS Safari doesn't reliably trigger `fileInput.click()` from button onclick when input is `display:none`.
**Fix:** Wrapped file input in `<label class="btn-compose">` — label acts as native click proxy.
**OSS note:** Never use JS `.click()` for file inputs on iOS. Use label wrapping.

### #10 — [ios] Formatting lost on history reload
**When:** 2026-03-24 &bull; **Component:** rendering
**Symptom:** Live streaming shows markdown; reloaded history is plain text.
**Root cause:** History reload used `escHtml()` instead of `renderMarkdown()`.
**Fix:** History reload creates `.bubble` element, sets `textContent`, then calls `renderMarkdown()`.
**OSS note:** All content paths (live + history) must go through the same renderer.

### #11 — [ios] Service worker breaks self-signed cert
**When:** 2026-03-24 &bull; **Component:** pwa
**Symptom:** `FetchEvent.respondWith` error: `TypeError: Load failed`.
**Root cause:** Service worker intercepted and re-fetched all requests; re-fetch fails with self-signed cert.
**Fix:** Replaced with no-op service worker.
**OSS note:** Don't register a service worker when using self-signed certs. Or scope it to skip API routes.

## Infrastructure

### #12 — [infra] Session recovery loses context on server restart
**When:** 2026-03-26 &bull; **Component:** continuity
**Symptom:** After server restart, resumed sessions have no memory of prior conversation.
**Root cause:** Recovery briefing relied on Apex compaction summaries which weren't persisted.
**Fix:** Structured recovery system: `session_memory_context.md` + `/ss` digest + bridge agent.
**OSS note:** Document session persistence model. Users need to understand what survives a restart.

### #14 — [infra] build_session_context.py crashes — KeyError: 'lines'
**When:** 2026-03-27 &bull; **Component:** continuity
**Symptom:** `session_memory_context.md` never generated; Codex/Claude sessions start with no semantic memory.
**Root cause:** When OpenClaw was replaced with Gemini embedding search, `run_memory_search()` was updated to return `{"score", "ref"}` only. Downstream code (`first_line_of_content()`, auto-load content) still expected a `"lines"` key from the old `parse_results()` format.
**Fix:** `run_memory_search()` now reads file content into `lines` at search time so all downstream consumers get the data they need.
**OSS note:** Memory bootstrap pipeline must be tested end-to-end after swapping search backends. Integration test: run `build_session_context.py --print-only` and verify non-empty output.

### #15 — [infra] Bottom research agent burning Grok API credits on web search
**When:** 2026-03-27 &bull; **Component:** cron / cost
**Symptom:** Large xAI API cost spike at 6:23 AM daily — tall purple "Web searches" bar on usage dashboard.
**Root cause:** `bottom_research_agent.py` called `run_grok.sh --search` for every Phase 3+ candidate (17 symbols), each triggering xAI SDK `web_search()` + `x_search()` native tools.
**Fix:** Replaced Grok API with local pipeline: yfinance fetches earnings dates, news, sector/analyst data; Ollama `qwen3.5:35b-a3b` generates verdicts. Auto-AVOID rule skips LLM for earnings within 10 days. Streaming API used because Qwen 3.5 thinking mode consumes non-streaming token budgets silently.
**OSS note:** Expensive API calls for structured research can often be replaced by free data APIs + local models. Document the yfinance + Ollama pattern as a reference architecture for cost-sensitive deployments.

### #13 — [infra] Model health dots show red despite valid keys
**When:** 2026-03-27 &bull; **Component:** dashboard
**Symptom:** Dashboard health indicators red even though API keys are configured.
**Root cause:** Health check tested API reachability (actual HTTP call), not just key presence.
**Fix:** Confirmed this is correct behavior — red means the API is actually unreachable, not misconfigured.
**OSS note:** Document that health dots test live connectivity, not just configuration.
