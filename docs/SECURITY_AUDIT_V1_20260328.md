# Apex Security Audit — 2026-03-28
> **Historical document.** This audit was performed against the pre-refactor monolith (`server/apex.py`, ~11K lines). The codebase has since been split into 26 modules. Line numbers referenced below no longer correspond to current file locations — findings remain relevant but should be mapped to the new module structure before remediation.

**Audited by:** Codex (live dev instance, `:8301`) + static analysis of `server/apex.py`
**Audit type:** Code review + runtime probe
**Branch audited:** `dev` (uncommitted working-tree edits applied)
**Status:** OPEN — remediation not yet applied to any finding below

---

## Executive Summary

The server is **not secure by default.** mTLS is configured but not enforced — any client without a certificate can connect and call every API route. Combined with zero authentication on 40+ routes and no rate limiting, the server is fully open to unauthenticated access from any host on the local network.

**These findings must be addressed before any distribution milestone (TestFlight, OSS release, App Store).**

---

## Finding Index

| ID | Severity | Title |
|----|----------|-------|
| S-01 | 🔴 CRITICAL | mTLS configured as OPTIONAL, not REQUIRED |
| S-02 | 🔴 CRITICAL | Auth middleware covers only one route out of 40+ |
| S-03 | 🔴 CRITICAL | 40+ routes fully unauthenticated |
| S-04 | 🔴 CRITICAL | WebSocket endpoint bypasses cert middleware entirely |
| S-05 | 🔴 CRITICAL | Origin check allows requests with no Origin header |
| S-06 | 🟠 HIGH | API keys stored as module-level globals |
| S-07 | 🟠 HIGH | OpenAI key passed into subprocess environment |
| S-08 | 🟠 HIGH | No rate limiting on any endpoint |
| S-09 | 🟠 HIGH | File upload validated by extension only (no magic number check) |
| S-10 | 🟡 MEDIUM | Path traversal risk in upload pipeline |
| S-11 | 🟡 MEDIUM | Dynamic SQL string formatting pattern present |
| S-12 | 🟡 MEDIUM | Error details and stderr disclosed to clients |
| S-13 | 🟡 MEDIUM | SSL cert files not validated before server start |
| S-14 | 🟡 MEDIUM | Subprocess paths not validated against symlink attacks |
| S-15 | 🟡 MEDIUM | No CORS middleware configured |
| S-16 | 🔵 LOW | Missing security response headers on all routes |
| S-17 | 🔵 LOW | Bearer token comparison vulnerable to timing attacks |
| S-18 | 🔵 LOW | Temp directory prefix leaks process identity |
| S-19 | 🔵 LOW | Server binds `0.0.0.0` by default |
| S-20 | 🔵 LOW | No audit logging for sensitive operations |
| S-21 | 🔵 LOW | SSL private keys may be tracked in git history |

---

## Findings — Detailed

---

### S-01 · 🔴 CRITICAL — mTLS configured as OPTIONAL, not REQUIRED

**File:** `server/apex.py:9111`

**Evidence:**
```python
uvicorn.run(
    app, host=HOST, port=PORT, log_level=log_lvl,
    ssl_certfile=SSL_CERT,
    ssl_keyfile=SSL_KEY,
    ssl_ca_certs=SSL_CA,
    ssl_cert_reqs=ssl.CERT_OPTIONAL,   # <-- clients do NOT need a valid cert
)
```

**Impact:** Clients can complete TLS handshakes without presenting a certificate. The server establishes a connection and passes the request through to the app layer. Combined with S-02 and S-03, this means any unauthenticated host on the LAN can reach every endpoint.

**Confirmed at runtime:** Codex hit the running dev instance without a client cert and received valid API responses.

**Remediation plan:**
1. Change `ssl_cert_reqs=ssl.CERT_OPTIONAL` → `ssl_cert_reqs=ssl.CERT_REQUIRED`
2. Add a pre-flight cert validation check at startup that verifies `SSL_CERT`, `SSL_KEY`, and `SSL_CA` all exist and are readable before `uvicorn.run()` is called — fail fast with a clear error if any are missing
3. Add a README note and setup script step ensuring the iOS app's `client.p12` is provisioned before first run
4. **Breaking change note:** This will immediately break any client (iOS app, CLI scripts, curl tests) that does not present the client cert. Coordinate rollout with iOS cert provisioning step.

---

### S-02 · 🔴 CRITICAL — Auth middleware covers only one route out of 40+

**File:** `server/apex.py:2450–2459`

**Evidence:**
```python
@app.middleware("http")
async def verify_client_cert(request: Request, call_next):
    path = request.url.path
    # Bearer token auth for alert creation (POST /api/alerts only)
    if path == "/api/alerts" and request.method == "POST" and ALERT_TOKEN:
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {ALERT_TOKEN}":
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return await call_next(request)   # everything else: pass through unconditionally
```

**Impact:** The middleware name implies cert verification but performs none. Only the alerts POST is gated; all other routes receive `call_next` unconditionally.

**Remediation plan:**
1. **Option A (preferred — defense in depth):** After fixing S-01, add cert presence check in this middleware for all non-public routes:
   ```python
   cert = request.scope.get("ssl_object")
   if cert is None or cert.getpeercert() is None:
       return JSONResponse({"error": "Client certificate required"}, status_code=401)
   ```
2. **Option B (simpler, relies on TLS layer):** Enforce CERT_REQUIRED at TLS level (S-01 fix) and remove the middleware, trusting the TLS handshake. Add an allowlist of public routes (e.g., `/health`) that bypass the cert check.
3. Document which routes (if any) are intentionally public and why — likely only `/health`.
4. Rename the middleware to accurately reflect its function after changes.

---

### S-03 · 🔴 CRITICAL — 40+ routes fully unauthenticated

**File:** `server/apex.py` (multiple)

**Routes accessible without any authentication:**

| Route | Method | Sensitivity |
|-------|--------|-------------|
| `/api/chats` | GET | Lists all chat metadata |
| `/api/chats` | POST | Creates new chats |
| `/api/chats/{id}` | PATCH / DELETE | Modifies or deletes chats |
| `/api/chats/{id}/messages` | GET | Reads all message history |
| `/api/chats/{id}/context` | GET | Reads context window state |
| `/api/chats/{id}/members` | GET / POST / DELETE / PATCH | Group membership control |
| `/api/profiles` | GET / POST | Lists or creates agent profiles |
| `/api/profiles/{id}` | GET / PUT / DELETE | Reads/modifies/deletes profiles |
| `/api/upload` | POST | Uploads files to server disk |
| `/api/transcribe` | POST | Whisper transcription |
| `/api/alerts` | GET / DELETE / POST ack | Read and manage alerts |
| `/api/alerts/wait` | GET | Long-poll stream |
| `/api/models/local` | GET | Exposes local model inventory |
| `/api/usage` | GET | Exposes API cost data |
| `/api/usage/grok` | GET | Exposes xAI spend |
| `/api/usage/codex` | GET | Exposes Claude Code spend |
| `/api/persona-templates` | GET | Reads persona templates |
| `/api/persona-templates/install` | POST | Installs persona templates |
| `/api/features` | GET | Exposes feature flag state |
| `/health` | GET | (acceptable as public) |

**Impact:** Any host that can reach the server port (including any device on the same LAN) can read all conversations, delete chats, create profiles, install personas, and trigger file uploads.

**Remediation plan:**
1. Fixing S-01 and S-02 together closes this gap for properly configured deployments.
2. Add an explicit allowlist of intentionally public routes (e.g., `["/health"]`) in a constant at the top of the file.
3. For OSS release, document that all endpoints require mTLS — add to README security section.
4. Consider a "local-only" mode flag (`APEX_LOCAL_ONLY=true`) that binds to `127.0.0.1` and skips cert checks, for developers who want to test without certs. This becomes the dev default; mTLS becomes the prod default.

---

### S-04 · 🔴 CRITICAL — WebSocket endpoint bypasses cert middleware entirely

**File:** `server/apex.py:3944–3950`

**Evidence:**
```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if not _websocket_origin_allowed(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()   # no cert check, just origin header check
```

**Impact:** HTTP middleware runs before WebSocket upgrade but `ssl_object` peer cert is not checked. The WebSocket accepts and streams full chat completions to any connecting client that passes the origin check (which S-05 shows is also weak).

**Remediation plan:**
1. After the origin check, extract and validate the peer cert from `websocket.scope`:
   ```python
   ssl_obj = websocket.scope.get("ssl_object")
   if ssl_obj is None or ssl_obj.getpeercert() is None:
       await websocket.close(code=1008)
       return
   ```
2. Alternatively, validate a session token passed as a WebSocket query parameter (token generated only after a successful mTLS HTTP handshake).
3. Add a test that connects to `/ws` without a client cert and asserts `1008` close code.

---

### S-05 · 🔴 CRITICAL — Origin check allows requests with no Origin header

**File:** `server/apex.py:1487–1496`

**Evidence:**
```python
def _websocket_origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return True   # <-- no origin = always allowed
    ...
```

**Impact:** Any WebSocket client that omits the `Origin` header (e.g., `websocat`, `wscat`, curl-upgraded, or any non-browser client) bypasses the only defense on the WebSocket endpoint.

**Remediation plan:**
1. Flip the default — require an Origin header to be present:
   ```python
   if not origin:
       return False   # require origin
   ```
2. Maintain an explicit allowlist of permitted origins (e.g., `https://<server-host>`, `apex://` for iOS in-app WebViews).
3. Note: Fixing S-01/S-04 makes this less critical, but defense-in-depth still applies.

---

### S-06 · 🟠 HIGH — API keys stored as module-level globals

**File:** `server/apex.py:87–101`

**Evidence:**
```python
XAI_API_KEY       = os.environ.get("XAI_API_KEY", "")
XAI_MANAGEMENT_KEY = os.environ.get("XAI_MANAGEMENT_KEY", "")
ALERT_TOKEN       = os.environ.get("APEX_ALERT_TOKEN", "")
OPENAI_API_KEY    = os.environ.get("OPENAI_API_KEY", "")
```

**Impact:** Module-level globals are visible to any code in the process, any exception traceback that prints `globals()`, and any debug endpoint or profiling tool that enumerates the module namespace. If a future `/debug` or `/admin` route is added carelessly, these are immediately exposed.

**Remediation plan:**
1. Wrap secrets in a `SecretsStore` class that provides accessor methods but does not expose raw strings in `__repr__` or `__str__`:
   ```python
   class _Secret:
       def __init__(self, value): self._v = value
       def get(self): return self._v
       def __repr__(self): return "<Secret:[redacted]>"
   ```
2. Fail fast at startup if required keys are empty — do not silently operate in a degraded state.
3. Add a `/api/health` response that confirms keys are *present* (boolean) but never returns their values.
4. Never log key values, even at DEBUG level.

---

### S-07 · 🟠 HIGH — OpenAI key passed into subprocess environment

**File:** `server/apex.py:3279`

**Evidence:**
```python
env={**os.environ, "OPENAI_API_KEY": OPENAI_API_KEY},
```

**Impact:** On Linux, subprocess environment variables are readable via `/proc/[pid]/environ` by any process running as the same user. On macOS the risk is lower but subprocess error messages can leak env contents.

**Remediation plan:**
1. Pass the key only via stdin or a named pipe rather than the environment:
   ```python
   # write key to a temp file with mode 0600, pass path via env
   ```
2. If the subprocess must use the env var (e.g., OpenAI SDK reads it automatically), ensure the child process is short-lived and the PID is not exposed to other users.
3. Audit all other `subprocess` calls for similar patterns.

---

### S-08 · 🟠 HIGH — No rate limiting on any endpoint

**File:** `server/apex.py` (global — no rate limiting present)

**Impact:** All endpoints are unbounded. Specific risks:
- `/api/upload` — disk fill attack (no per-client upload quota)
- `/api/chats` POST — can create thousands of chats
- `/api/alerts` POST — alert spam
- `/ws` — unlimited concurrent WebSocket connections
- `/api/transcribe` — repeated expensive Whisper invocations

**Remediation plan:**
1. Add `slowapi` (Starlette-compatible rate limiter) as a dependency.
2. Apply per-IP limits on the highest-risk endpoints first:
   - `/api/upload`: 10 requests/min, max 50 MB/day per IP
   - `/api/transcribe`: 5 requests/min
   - `/api/chats` POST: 20 requests/min
   - `/api/alerts` POST: 30 requests/min
3. Add a global request-size cap via middleware (reject bodies > N MB before processing).
4. Add WebSocket connection limit (max N concurrent connections per IP).

---

### S-09 · 🟠 HIGH — File upload validated by extension only

**File:** `server/apex.py:3851–3870`

**Evidence:**
```python
ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
is_image = ext in IMAGE_TYPES
is_text  = ext in TEXT_TYPES
if not is_image and not is_text:
    return JSONResponse({"error": f"Unsupported file type: .{ext}"}, status_code=400)
```

**Impact:** An attacker can rename `malicious.php` → `malicious.jpg` and upload it. If the server ever serves static files from the upload directory, this becomes code execution. Even without execution, SSRF or HTML injection can occur via uploaded SVG files.

**Remediation plan:**
1. Add `python-magic` (libmagic bindings) to `requirements.txt`.
2. After writing the file, verify magic bytes match the declared extension — reject mismatches.
3. For SVG specifically: either reject entirely or sanitize with `bleach`/`defusedxml` before storage.
4. Set `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff` on all file-serving routes.
5. Store uploads outside the web root (they already appear to be in a workspace directory — confirm they are not served via a static file route).

---

### S-10 · 🟡 MEDIUM — Path traversal risk in upload pipeline

**File:** `server/apex.py:1354–1355`

**Evidence:**
```python
def _normalize_filename(filename: str | None, fallback: str = "upload") -> str:
    safe = Path(filename or fallback).name.replace("\x00", "").strip()
    return safe or fallback
```

**Impact:** `Path(...).name` strips directory components, which is correct. However, the validation that the written file stays within the intended parent directory happens *after* the write (or not at all). Null-byte stripping is present but other bypasses (unicode normalization, encoded slashes) are not guarded.

**Remediation plan:**
1. After constructing the final path, assert `final_path.resolve().parent == upload_dir.resolve()` before writing.
2. Add a unit test with path traversal payloads: `../../etc/passwd`, `%2e%2e%2fetc`, `\x00malicious`.
3. Use `secrets.token_hex(8)` as the stored filename, keep original name only in the DB metadata row — eliminates traversal class entirely.

---

### S-11 · 🟡 MEDIUM — Dynamic SQL string formatting pattern present

**File:** `server/apex.py:2735`

**Evidence:**
```python
conn.execute(f"DELETE FROM chats WHERE id IN ({placeholders})", ids)
```
where `placeholders` is built via `",".join("?" * len(ids))`.

**Impact:** The current usage is safe — `placeholders` contains only `?` characters and `ids` are bound as parameters. However, the f-string pattern is easy to misuse in future edits. A developer could accidentally interpolate a user-controlled value into `placeholders`.

**Remediation plan:**
1. No immediate change required — confirm all usages of this pattern use only `?` in the interpolated part.
2. Add a linting rule (e.g., `semgrep` rule) that flags `f"...SQL...{variable}"` patterns and requires review.
3. Add a comment at each usage site: `# safe: placeholders contains only '?' chars`.

---

### S-12 · 🟡 MEDIUM — Error details and stderr disclosed to clients

**File:** `server/apex.py` — multiple locations

**Evidence:**
- Line ~294: API error body forwarded to client
- Line ~3926: Whisper subprocess stderr returned in response
- DEBUG mode logs chat IDs, model names, token counts to stdout

**Impact:** Stack traces, internal paths, model names, and error bodies from upstream APIs can be used for reconnaissance. Whisper stderr can contain temp file paths and system info.

**Remediation plan:**
1. Catch all upstream API errors and return a generic `{"error": "upstream_error", "code": <http_status>}` — log the full error server-side only.
2. Remove subprocess stderr from API responses — return a generic transcription failure message.
3. Ensure DEBUG log level is never enabled in production (`LOG_LEVEL=WARNING` default in `launch_apex.sh`).
4. Add a startup warning if `LOG_LEVEL=DEBUG` is set.

---

### S-13 · 🟡 MEDIUM — SSL cert files not validated before server start

**File:** `server/apex.py:9090–9111`

**Impact:** If cert files are missing or corrupt, uvicorn may fail with an unhelpful error or fall back to plaintext HTTP silently (behavior depends on version).

**Remediation plan:**
1. Add a pre-flight check function:
   ```python
   def _validate_ssl_paths():
       for path, label in [(SSL_CERT, "SSL_CERT"), (SSL_KEY, "SSL_KEY"), (SSL_CA, "SSL_CA")]:
           if not Path(path).exists():
               raise SystemExit(f"[FATAL] {label} not found: {path}")
   ```
2. Call this before `uvicorn.run()` when SSL is configured.
3. Add a check that the cert and key are a matching pair.

---

### S-14 · 🟡 MEDIUM — Subprocess paths not validated against symlink attacks

**File:** `server/apex.py:3272–3280, 3907–3913, 833–835`

**Impact:** If `WORKSPACE` or any user-controlled path is used as a subprocess argument and an attacker can control a symlink in that path, they can redirect file reads/writes.

**Remediation plan:**
1. Resolve all paths with `.resolve()` before passing to subprocesses.
2. Assert that resolved paths are within the expected workspace root.
3. Add `follow_symlinks=False` where applicable on `os.stat` / `shutil` calls.

---

### S-15 · 🟡 MEDIUM — No CORS middleware configured

**File:** `server/apex.py` (global)

**Impact:** Without explicit CORS headers, browsers will use their own default policy. If a future web dashboard or third-party client uses cross-origin fetch, requests may fail silently or (if CORS is added carelessly later) be over-permissive.

**Remediation plan:**
1. Add `CORSMiddleware` from `starlette.middleware.cors`:
   ```python
   from starlette.middleware.cors import CORSMiddleware
   app.add_middleware(
       CORSMiddleware,
       allow_origins=ALLOWED_ORIGINS,   # explicit allowlist, not "*"
       allow_credentials=True,
       allow_methods=["GET","POST","PATCH","DELETE"],
       allow_headers=["Authorization","Content-Type"],
   )
   ```
2. Define `ALLOWED_ORIGINS` from an env var — default to `[]` (deny all cross-origin).
3. Do not use `allow_origins=["*"]` — this bypasses all origin protection.

---

### S-16 · 🔵 LOW — Missing security response headers

**File:** `server/apex.py:4542` (HTML route) and all JSON routes

**Missing headers:**

| Header | Required Value | Why |
|--------|---------------|-----|
| `X-Content-Type-Options` | `nosniff` | Prevents MIME sniffing of uploaded files |
| `X-Frame-Options` | `DENY` | Prevents clickjacking |
| `Content-Security-Policy` | Strict policy | Prevents XSS in dashboard HTML |
| `Strict-Transport-Security` | `max-age=31536000` | Forces HTTPS after first visit |
| `Referrer-Policy` | `no-referrer` | Prevents URL leakage |

**Remediation plan:**
1. Add a response middleware that injects these headers on all responses:
   ```python
   @app.middleware("http")
   async def security_headers(request, call_next):
       response = await call_next(request)
       response.headers["X-Content-Type-Options"] = "nosniff"
       response.headers["X-Frame-Options"] = "DENY"
       response.headers["Referrer-Policy"] = "no-referrer"
       if request.url.scheme == "https":
           response.headers["Strict-Transport-Security"] = "max-age=31536000"
       return response
   ```
2. Add a strict CSP to the dashboard HTML response separately.

---

### S-17 · 🔵 LOW — Bearer token comparison vulnerable to timing attacks

**File:** `server/apex.py:2456–2457`

**Evidence:**
```python
if auth != f"Bearer {ALERT_TOKEN}":
```

**Impact:** String `!=` comparison is not constant-time. In theory, an attacker could measure response time differences to brute-force the token character by character. Practical risk is low given network jitter, but is an easy fix.

**Remediation plan:**
1. Replace with `hmac.compare_digest`:
   ```python
   import hmac
   expected = f"Bearer {ALERT_TOKEN}"
   if not hmac.compare_digest(auth.encode(), expected.encode()):
   ```
2. Add a minimum token length validation at startup (e.g., `len(ALERT_TOKEN) >= 32`).

---

### S-18 · 🔵 LOW — Temp directory prefix leaks process identity

**File:** `server/apex.py:3902`

**Evidence:**
```python
with tempfile.TemporaryDirectory(prefix="apex-whisper-") as tmp_dir:
```

**Impact:** The `apex-whisper-` prefix makes it trivial for another process on the same machine to discover that a transcription is in progress and attempt to read the temp file during the window it exists.

**Remediation plan:**
1. Remove the `prefix` argument — Python's default generates a random name.
2. Ensure `TemporaryDirectory` cleanup runs even on exception (the `with` block already handles this — confirm no code paths break out of it).

---

### S-19 · 🔵 LOW — Server binds `0.0.0.0` by default

**File:** `server/apex.py:87`

**Evidence:**
```python
HOST = os.environ.get("APEX_HOST", "0.0.0.0")
```

**Impact:** Exposes the server on all network interfaces. Combined with weak auth (S-01–S-05), this is the delivery mechanism for most critical findings. Even after fixing auth, listening on all interfaces is a broader attack surface than necessary.

**Remediation plan:**
1. Change the default to `127.0.0.1` for local development:
   ```python
   HOST = os.environ.get("APEX_HOST", "127.0.0.1")
   ```
2. Require `APEX_HOST=0.0.0.0` to be set explicitly for network-accessible deployments.
3. Add a startup log line: `[apex] Listening on {HOST}:{PORT}` so the operator knows what interface is active.
4. Update `launch_apex.sh` to explicitly set `APEX_HOST` for the known deployment topology.

---

### S-20 · 🔵 LOW — No audit logging for sensitive operations

**File:** `server/apex.py` (global)

**Missing audit events:**
- Profile created / updated / deleted
- Chat deleted
- File uploaded (filename, size, uploader IP)
- Alert created / acknowledged / deleted
- Authentication failure (rejected cert or bad token)
- Server startup (who, when, which config)

**Remediation plan:**
1. Create an `audit_log(event, detail, request)` helper that writes to a separate `audit.log` file (not `stdout`).
2. Wire it to the 8–10 highest-sensitivity operations listed above.
3. Include: timestamp (ISO 8601), client IP, route, HTTP method, result code, and a short event label.
4. Ensure audit log is not truncated on server restart (append mode, log rotation).

---

### S-21 · 🔵 LOW — SSL private keys may be tracked in git history

**File:** `state/ssl/` directory

**Evidence:** Directory contains `apex.crt`, `apex.key`, `ca.crt`, `ca.key`, `client.crt`, `client.key`, `client.p12`.

**Impact:** If any of these were ever committed to git, the private keys are in history and must be considered compromised regardless of current `.gitignore` state.

**Remediation plan:**
1. Run `git log --all --full-history -- state/ssl/` to determine if any key files were ever committed.
2. If yes: rotate all certificates immediately. Use `git filter-repo` to scrub history before any OSS release.
3. Add `state/ssl/` to `.gitignore` if not already present.
4. For OSS distribution: provide a `scripts/gen-certs.sh` that generates fresh certs per installation — do not ship any certs in the repo.

---

## Remediation Priority Order

**Do these first — they close the full-open access window:**

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| P0 | S-01 — Change CERT_OPTIONAL → CERT_REQUIRED | 1 line | Closes unauthenticated LAN access |
| P0 | S-02 — Enforce cert in middleware for all routes | ~20 lines | Adds app-layer defense in depth |
| P0 | S-04 — Add cert check to WebSocket handler | ~10 lines | Closes WS bypass |
| P0 | S-05 — Flip origin check default to deny | 1 line | Closes no-origin bypass |
| P1 | S-08 — Add rate limiting (slowapi) | ~50 lines | Closes DoS/spam vectors |
| P1 | S-09 — Add magic-byte file validation | ~30 lines + dep | Closes upload abuse |
| P1 | S-16 — Add security response headers middleware | ~15 lines | Low effort, high value |
| P2 | S-06 — Wrap secrets in opaque class | ~30 lines | Reduces secret exposure surface |
| P2 | S-07 — Stop passing API key in subprocess env | ~10 lines | Reduces key leakage |
| P2 | S-12 — Sanitize error responses | ~20 lines | Stops info disclosure |
| P2 | S-17 — Switch to `hmac.compare_digest` | 2 lines | Easy win |
| P2 | S-19 — Default bind to 127.0.0.1 | 1 line | Reduces exposure surface |
| P3 | S-10, S-13, S-14, S-15, S-18, S-20, S-21 | Moderate | Defense-in-depth / OSS readiness |

---

## OSS / Distribution Gate

These findings block OSS release and TestFlight distribution until resolved:

- [ ] S-01 resolved and verified with a cert-less connection test (should receive TLS error, not API response)
- [ ] S-04 resolved and verified with `wscat` without client cert (should receive `1008`)
- [ ] S-08 rate limiting in place on upload and transcribe endpoints
- [ ] S-09 magic-byte validation in place
- [ ] S-21 git history checked; if keys were committed, new certs generated before any public push
- [ ] All `state/ssl/` private keys confirmed absent from git history or repo `.gitignore` confirmed

---

*Audit prepared by Codex · Reviewed by Operations · 2026-03-28*
