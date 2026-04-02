# Apex Security Audit — 2026-04-01

Scope: Setup wizard, mTLS, public routes, API key storage, chat UI (XSS), persona guidance feature.
Method: 5 parallel automated scans covering routes_setup.py, setup_html.py, chat_html.py, apex.py/mtls.py, env.py/config.py/agent_sdk.py.

---

## CRITICAL (2)

### C-1: Setup POST endpoints accessible after setup completes, no mTLS required

**Files:** `apex.py` (`_PUBLIC_ROUTES`), `routes_setup.py`

Setup POST endpoints (`/api/setup/models`, `/api/setup/workspace`, `/api/setup/knowledge`, `/api/setup/complete`) are in `_PUBLIC_ROUTES` (mTLS-exempt) and have no guard checking whether setup is already complete. After setup finishes, any network client can:

- Overwrite API keys (`ANTHROPIC_API_KEY`, `XAI_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`) via POST `/api/setup/models`
- Change the workspace path via POST `/api/setup/workspace`
- Trigger filesystem scanning via POST `/api/setup/knowledge`

Only protection is `X-Requested-With: XMLHttpRequest` CSRF header, which is trivially spoofable by any attacker with network access.

**Fix:** Add `phase_completed("setup_complete")` guard to all setup POST handlers, return 403 after setup is done.

---

### C-2: `has_verified_peer_cert()` always returns `True` — mTLS middleware is a no-op

**File:** `mtls.py:25`

The function unconditionally returns `True`. Enforcement relies entirely on `ssl.CERT_REQUIRED` at the TLS layer. If Apex is ever deployed behind a TLS-terminating reverse proxy (Cloudflare, nginx, Caddy), mTLS silently vanishes — all routes become publicly accessible with zero authentication.

The code comments acknowledge this: "Assumes direct-TLS; behind a TLS-terminating proxy this would return True without actual client certificate verification."

**Fix:** Detect proxy headers (`X-Forwarded-For`) and fail closed, or extract actual peer cert from the connection. Add a startup warning if proxy deployment is detected.

---

## HIGH (3)

### H-1: XSS in OAuth status display — `innerHTML` with unsanitized server data

**File:** `setup_html.py:1043-1050`

`checkOAuthStatus()` renders `r.email`, `r.subscription`, and `r.error` from API responses directly into `innerHTML` without escaping. A crafted email value like `<img src=x onerror=alert(1)>` would execute.

**Fix:** Use `textContent` or wrap dynamic values in `escHtml()` before `innerHTML` assignment.

---

### H-2: XSS in history scan — filesystem paths rendered via `innerHTML`

**File:** `setup_html.py:1168-1178`

`scanHistory()` renders `s.path`, `s.name`, `s.count`, `s.size_mb` from the `/api/setup/history/scan` response directly into `innerHTML`. Filesystem paths with HTML metacharacters would be interpreted as markup.

**Fix:** Escape all dynamic values before insertion, or build DOM elements with `textContent`.

---

### H-3: Private keys stored unencrypted on disk

**Files:** `state/ssl/ca.key`, `state/ssl/apex.key`

Both CA and server private keys are plaintext PEM. The `ssl_keystore.py` module has full encryption support and `migrate_plaintext_keys()` exists but was never executed. File permissions are correct (0600) but unencrypted keys are vulnerable to backup leakage or disk imaging.

**Fix:** Run `migrate_plaintext_keys()` to encrypt at rest.

---

## MEDIUM (8)

### M-1: Workspace path traversal via symlinks

**File:** `routes_setup.py:425`

Path validation uses `".." in workspace_path` (substring check) but doesn't resolve symlinks. A symlink pointing outside the expected root could allow scanning arbitrary directories.

**Fix:** Use `Path(workspace_path).resolve()` and verify the resolved path is under an acceptable root.

---

### M-2: Race conditions on `.env` and progress file writes

**Files:** `dashboard.py` (`_update_env_var`), `setup/progress.py` (`mark_phase_completed`)

Both do read-modify-write on files without locking. Concurrent requests could clobber each other's changes.

**Fix:** Add `threading.Lock` around the read-modify-write cycles.

---

### M-3: Exception messages leak internal paths to client

**Files:** `routes_setup.py:230-235, 251-252, 357, 398`

`str(exc)` is returned directly in API error responses. These could leak filesystem paths, module import errors, or stack trace fragments.

**Fix:** Return generic error messages to the client; log the full exception server-side only.

---

### M-4: `log()` not imported in `routes_setup.py` — NameError swallows validation errors

**File:** `routes_setup.py:308`

`log(f"setup: key validation error for {field}: {exc}")` will raise `NameError` (function not imported), which is caught by the outer `except Exception` block, causing the validation error to be silently swallowed and the invalid key to be saved anyway.

**Fix:** Add `from log import log` to the imports.

---

### M-5: No Content-Security-Policy on setup page

**File:** `setup_html.py`

No CSP header or `<meta>` tag. Adding a policy would limit the blast radius of XSS findings H-1 and H-2.

**Fix:** Add `<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'">`.

---

### M-6: Token prefix (12 chars) logged to disk

**File:** `agent_sdk.py:436, 466, 475`

Multiple log statements include the first 12 characters of API keys/tokens, plus last 4 on line 475. Combined prefix + suffix narrows key identification.

**Fix:** Log only the last 4 characters, or reduce prefix to 6 chars max.

---

### M-7: `os.environ` mutations not thread-safe across async handlers

**Files:** `agent_sdk.py`, `dashboard.py`

`os.environ` is modified from multiple async code paths (OAuth refresh, credential updates, token startup). The read-check-write pattern is not atomic.

**Fix:** Wrap `os.environ` mutations in a shared lock.

---

### M-8: Orphaned `client_new.key` (valid private key) on disk

**File:** `state/ssl/client_new.key`, `client_new.crt` (0 bytes), `client_new.csr`

Failed or abandoned certificate generation left a valid 2048-bit private key on disk alongside an empty cert file.

**Fix:** Securely delete the orphaned `client_new.*` files.

---

## LOW (6)

### L-1: `_is_oauth_token()` uses weak heuristic

**File:** `agent_sdk.py:145`

`"oat" in token[:15]` could misclassify a crafted API key containing "oat" in its prefix. Combined with L-2, this creates a bypass path.

**Fix:** Use `token.startswith("sk-ant-oat")` instead of substring search.

---

### L-2: OAuth tokens never validated (always returns True)

**File:** `agent_sdk.py:102-115`

Known limitation — Anthropic REST API doesn't support OAuth token validation. Any string matching the OAuth heuristic is accepted.

**Fix:** Document as known limitation. Consider adding `_validate_oauth_expiry()` as a secondary gate.

---

### L-3: `data-profile-id` uses `escHtml()` instead of `escAttr()` in attribute context

**File:** `chat_html.py:2739, 4276`

Not exploitable (double-quoted attributes, `escHtml` escapes `"`), but inconsistent with how `data-alert-id` uses `escAttr()`.

**Fix:** Use `escAttr()` for all `data-*` attribute values.

---

### L-4: CSRF is header-only (no per-session token)

**Files:** `routes_setup.py`, `dashboard.py`

`X-Requested-With: XMLHttpRequest` is a CORS-based CSRF defense. Adequate behind mTLS but weaker than a per-session nonce.

**Fix:** Consider adding a session-bound CSRF token if mTLS is ever removed.

---

### L-5: Alert token returned in rotation response

**File:** `dashboard.py:2483-2486`

By design (only time client can see it). Mitigated by admin auth + CSRF + mTLS.

**Fix:** No action needed unless mTLS is removed.

---

### L-6: `_htmlToText()` uses innerHTML on detached element

**File:** `chat_html.py:1760-1763`

Safe today (input is pre-escaped), but the pattern is dangerous if future callers pass raw server data.

**Fix:** Replace with regex strip or use `textContent` of the source element directly.

---

## Positive Findings

- `escHtml()` consistently used across `chat_html.py` for all profile/message rendering
- New persona guidance card is fully static HTML — no injection vectors
- `hmac.compare_digest` used for all token comparisons (no timing attacks)
- No API keys stored in SQLite, localStorage, or API responses
- File permissions correct (0600) on all sensitive files
- WebSocket message handling properly sanitizes all data
- All subprocess calls use array form (no shell injection)
- `showErr()` uses `textContent` (safe)
- Field-level validation errors use `textContent` (safe)
- Config secrets properly separated (boolean flags only, never raw values)

---

## Recommended Fix Order

1. **C-1** — Gate setup POST endpoints after completion (highest impact, simplest fix)
2. **M-4** — Import `log` in routes_setup.py (bug causing silent failures)
3. **H-1 + H-2** — Escape innerHTML in setup_html.py (2 XSS vectors)
4. **C-2** — Harden `has_verified_peer_cert()` for proxy deployments
5. **M-2** — Add file write locks
6. **H-3 + M-8** — Encrypt keys at rest + delete orphaned key files
7. **M-3** — Sanitize error messages returned to client
8. Everything else (LOW items, CSP, token logging reduction)
