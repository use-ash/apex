# Apex Security Audit V2 — 2026-03-28
> **Historical document.** This audit was performed against the pre-refactor monolith (`server/apex.py`, ~11K lines). The codebase has since been split into 26 modules. Line numbers referenced below no longer correspond to current file locations.

**Audited by:** Codex
**Scope:** `server/apex.py`, `server/dashboard.py`, `server/dashboard_html.py` + runtime probe of dev server on `https://127.0.0.1:8301`
**Branch:** `dev`
**Status:** Partial hardening applied; critical anonymous-access issue fixed, but important follow-up work remains.

---

## Executive Summary

The security posture is **materially better than V1**.

The most dangerous prior issue — **anonymous access to API/admin because mTLS was optional** — is now fixed in the current direct dev deployment:
- `ssl_cert_reqs` is now `ssl.CERT_REQUIRED` in `server/apex.py:9180-9185`
- default bind is now `127.0.0.1` in `server/apex.py:88`
- missing WebSocket `Origin` is now rejected in `server/apex.py:1497-1506`
- basic hardening headers were added in `server/apex.py:2502-2511`
- alert token comparison now uses `hmac.compare_digest` in `server/apex.py:2473-2479`
- the mention-popup inline-handler injection bug was fixed in `server/apex.py:8364-8377`

### Runtime validation
Fresh no-cert probe against the restarted dev server:
- `curl -sk https://127.0.0.1:8301/api/features` → connection reset (`rc=56`)
- `curl -sk https://127.0.0.1:8301/admin/` → connection reset (`rc=56`)
- `curl -vk https://127.0.0.1:8301/api/features` shows TLS `Request CERT` during handshake, then the request is rejected without a client cert

So the server is **no longer anonymously reachable by default**.

## Overall verdict
- **Critical anonymous exposure:** fixed
- **Current direct dev deployment:** much safer
- **Still open:** defense-in-depth auth gaps, authenticated XSS surfaces, overpowered backup/restore handling, lack of rate limiting, CSP blockers, and some secret/error-handling hardening

---

## Validated Fixes Since V1

### F-01 · mTLS now required at transport layer
- **File:** `server/apex.py:9180-9185`
- **Validation:** TLS handshake now requests a client certificate and resets no-cert requests.
- **Outcome:** prior unauthenticated API/admin access is closed in the current direct deployment.

### F-02 · Localhost-by-default bind
- **File:** `server/apex.py:88`
- **Outcome:** reduces accidental LAN exposure during development.

### F-03 · WebSocket missing-Origin bypass fixed
- **File:** `server/apex.py:1497-1506`
- **Outcome:** non-browser clients no longer bypass the only browser-style origin check by omitting `Origin`.

### F-04 · Basic browser hardening headers added
- **File:** `server/apex.py:2502-2511`
- **Headers present:**
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: no-referrer`
  - `Strict-Transport-Security` on HTTPS requests

### F-05 · Timing-safe alert token comparison
- **File:** `server/apex.py:2473-2479`
- **Outcome:** token comparison no longer uses simple string equality.

### F-06 · Mention popup inline-handler injection fixed
- **File:** `server/apex.py:8364-8377`
- **Outcome:** that specific DOM/JS injection path is closed.

---

## Open Findings — Remaining Work

| ID | Severity | Title |
|----|----------|-------|
| V2-01 | 🟠 HIGH | HTTP cert middleware still does not fail closed |
| V2-02 | 🟠 HIGH | WebSocket cert check still does not enforce before `accept()` |
| V2-03 | 🟠 HIGH | Remaining authenticated DOM XSS via user-controlled `innerHTML` |
| V2-04 | 🟠 HIGH | Backups still include full `state/ssl/` contents |
| V2-05 | 🟡 MEDIUM | Dashboard still has no independent admin auth boundary |
| V2-06 | 🟡 MEDIUM | No general rate limiting / abuse controls |
| V2-07 | 🟡 MEDIUM | Upload/transcribe validation is still weak and upload leaks server path |
| V2-08 | 🟡 MEDIUM | Whisper stderr/stdout details still returned to clients |
| V2-09 | 🟡 MEDIUM | Secrets remain module globals; OpenAI key still passed via subprocess env |
| V2-10 | 🟡 MEDIUM | Strong CSP still blocked by widespread inline handlers |
| V2-11 | 🟡 MEDIUM | TLS startup checks only verify env vars are non-empty, not file readability |
| V2-12 | 🔵 LOW | Dynamic SQL composition patterns remain; safe today, brittle for future changes |
| V2-13 | 🔵 LOW / OPERATIONAL | `/health` cannot be publicly probed without a client cert under current design |

---

## Detailed Findings

### V2-01 · 🟠 HIGH — HTTP cert middleware still does not fail closed
**File:** `server/apex.py:2464-2499`

**Evidence:**
```python
@app.middleware("http")
async def verify_client_cert(request: Request, call_next):
    ...
    if SSL_CERT and SSL_CA and peer_cert is None:
        transport = request.scope.get("transport")
        if transport and hasattr(transport, "get_extra_info"):
            peer_cert = transport.get_extra_info("peercert")
    ...
    return await call_next(request)
```

**What changed:** the code now inspects transport TLS metadata.

**What is still missing:** if no peer certificate is found, it **still falls through** to `call_next()`.

**Why this matters:**
In the current direct uvicorn deployment, TLS `CERT_REQUIRED` is doing the real protection. But this middleware is explicitly described as defense-in-depth for proxy/misconfiguration scenarios, and it currently **does not actually reject** such requests.

**Risk:**
- safe enough in current direct deployment
- unsafe if Apex is ever placed behind TLS termination, a reverse proxy, or a future misconfigured ingress

**Remediation plan:**
1. Fail closed when TLS is configured but no peer cert is present:
   ```python
   if SSL_CERT and SSL_CA and peer_cert is None:
       return JSONResponse({"error": "Client certificate required"}, status_code=401)
   ```
2. Keep a tiny explicit allowlist only for intentionally public routes.
3. Add a regression test that simulates missing `peercert` in scope/transport and expects `401`.

---

### V2-02 · 🟠 HIGH — WebSocket cert check still does not enforce before `accept()`
**File:** `server/apex.py:3996-4011`

**Evidence:**
```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if SSL_CERT and SSL_CA:
        transport = websocket.scope.get("transport")
        peer_cert = None
        if transport and hasattr(transport, "get_extra_info"):
            peer_cert = transport.get_extra_info("peercert")
        # With CERT_REQUIRED, TLS layer blocks cert-less connections.
        # This is defense-in-depth for proxy/misconfiguration scenarios.

    if not _websocket_origin_allowed(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
```

**Issue:** it reads `peer_cert` but never rejects on `None`.

**Why this matters:**
Same story as HTTP: current direct deployment is protected by TLS, but the WebSocket route does not independently fail closed.

**Remediation plan:**
1. Close before `accept()` when no peer cert is present:
   ```python
   if SSL_CERT and SSL_CA and peer_cert is None:
       await websocket.close(code=1008)
       return
   ```
2. Add a WS regression test for no-cert and bad-origin cases.
3. If a proxy deployment is ever supported, require a signed session token or verified upstream identity header in addition to mTLS.

---

### V2-03 · 🟠 HIGH — Remaining authenticated DOM XSS via user-controlled `innerHTML`
**Files:**
- `server/apex.py:5504-5515` — ask-next chips
- `server/apex.py:5544-5549` — stop menu
- `server/apex.py:8814-8822` — new channel profile cards
- `server/apex.py:8936-8943` — new group profile cards
- `server/apex.py:9042-9054` — profile dropdown

**Representative evidence:**
```javascript
btn.innerHTML = `<span class="chip-emoji">${member.avatar || ''}</span> ${member.name}`;
```
```javascript
btn.innerHTML = `<span class="stop-dot"></span>${stream.avatar || ''} Stop ${stream.name || 'agent'}...`;
```
```javascript
card.innerHTML = `<div class="profile-avatar">${p.avatar || '💬'}</div> ...`
```
```javascript
item.innerHTML = `<span class="pd-avatar">${p.avatar || '💬'}</span><span class="pd-name">${escHtml(p.name)}</span>` + ...
```

**Impact:**
Profile names / avatars are user-controlled data. Even though mTLS now narrows access, these are still **real authenticated-client XSS sinks**.

**Notes:**
- `escHtml(...)` helps for text nodes, but several avatar/name placements are still raw HTML.
- This is especially important for OSS or multi-user/shared environments.

**Remediation plan:**
1. Replace each user-data `innerHTML` assignment with DOM construction and `textContent`.
2. Treat emoji/avatar as text, not HTML.
3. Use `addEventListener` instead of inline `onclick` when touching these components.
4. Add a regression test/profile fixture with values like:
   - `"<img src=x onerror=alert(1)>"`
   - `"'\"><svg onload=alert(1)>"`
   and verify literal rendering only.

---

### V2-04 · 🟠 HIGH — Backups still include full `state/ssl/` contents
**Files:**
- backup create: `server/dashboard.py:3065-3096`
- backup restore: `server/dashboard.py:3185-3253`

**Evidence:**
```python
ssl_dir = _state_dir / "ssl"
if ssl_dir.exists() and ssl_dir.is_dir():
    for item in ssl_dir.rglob("*"):
        if item.is_file():
            arcname = f"ssl/{item.relative_to(ssl_dir)}"
            tar.add(str(item), arcname=arcname)
```

and restore copies it back wholesale:
```python
for item in ssl_src.rglob("*"):
    if item.is_file():
        ...
        shutil.copy2(str(item), str(dest_file))
```

**Impact:**
If `state/ssl/` contains CA private key, server private key, or client issuance material, a backup download is effectively a **key-exfiltration surface**.

**Current risk level:** reduced from V1 because access is now mTLS-gated, but this remains one of the highest-value authenticated admin actions.

**Remediation plan:**
1. Exclude private key material from ordinary backups.
2. Split backup modes:
   - **state backup**: DB/config/uploads only
   - **disaster-recovery backup**: explicit, heavily warned, maybe local-only, maybe encrypted
3. At minimum exclude:
   - CA private key
   - server private key
   - client key material
4. Add a manifest to backups stating what was included.
5. Require explicit confirmation for restore of any TLS material.

---

### V2-05 · 🟡 MEDIUM — Dashboard still has no independent admin auth boundary
**Files:**
- mount: `server/apex.py:2456-2457`
- dashboard middleware: `server/dashboard.py:169-178`
- powerful admin endpoints: e.g. `server/dashboard.py:602`, `679`, `872`, `984`, `1354`, `1846`, `2223`, `2893`, `3065`, `3185`

**Evidence:**
```python
@dashboard_app.middleware("http")
async def csrf_protection(request: Request, call_next):
    if request.method in ("PUT", "POST", "DELETE"):
        if request.headers.get("x-requested-with") != "XMLHttpRequest":
            return JSONResponse(..., status_code=403)
```

**Issue:**
`X-Requested-With` is not authentication. Today the real boundary is parent-app mTLS.

**Why this matters:**
If TLS is ever terminated upstream, misconfigured, or a trusted client cert is compromised, the dashboard has no second layer like admin session auth, operator token, or explicit certificate subject allowlist.

**Remediation plan:**
1. Add a real admin auth layer for `/admin`, such as:
   - admin session cookie after cert-auth bootstrap, or
   - separate admin bearer token, or
   - certificate CN/OU allowlist for admin endpoints
2. Keep CSRF only if you move to cookie/session auth.
3. Consider mounting dashboard behind a separate admin-only ingress or localhost-only binding.

---

### V2-06 · 🟡 MEDIUM — No general rate limiting / abuse controls
**Files:**
- `server/apex.py` — no app-wide limiter found
- upload: `server/apex.py:3903-3938`
- transcribe: `server/apex.py:3943-3991`
- websocket: `server/apex.py:3996+`

**Current state:**
- file size limits exist
- backup endpoint has its own cooldown in dashboard
- there is still no per-client or per-route request limiting

**Impact:**
Authenticated clients can still:
- spam `/api/upload`
- repeatedly invoke Whisper
- open excessive WebSocket sessions
- churn chats/profiles/alerts

**Remediation plan:**
1. Add per-cert / per-IP quotas for:
   - `/api/upload`
   - `/api/transcribe`
   - `/ws`
   - chat/profile creation
2. Add concurrent-job caps for Whisper and long-running tool streams.
3. Log and surface rate-limit rejects in admin diagnostics.

---

### V2-07 · 🟡 MEDIUM — Upload/transcribe validation is still weak and upload leaks server path
**Files:**
- `_normalize_filename`: `server/apex.py:1364-1366`
- upload route: `server/apex.py:3903-3938`
- transcribe route: `server/apex.py:3943-3991`

**Evidence:**
Upload acceptance is still extension-based:
```python
ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
is_image = ext in IMAGE_TYPES
is_text = ext in TEXT_TYPES
```

And response leaks local filesystem path:
```python
"path": str(path),
```

**Impact:**
- weak content validation
- clients can upload content that does not match extension
- absolute filesystem path disclosure (`state/uploads/...`) is unnecessary information leakage
- transcription accepts arbitrary extension names and passes content to Whisper tooling

**Remediation plan:**
1. Validate image/audio types by content signature / MIME sniffing, not only extension.
2. Return an opaque file ID and download URL instead of absolute server path.
3. Restrict transcription to a known set of actual audio formats.
4. Consider malware scanning / structured parsing if uploads broaden over time.

---

### V2-08 · 🟡 MEDIUM — Whisper stderr/stdout details still returned to clients
**File:** `server/apex.py:3977-3991`

**Evidence:**
```python
if proc.returncode not in (0, None):
    detail = stderr.decode()[:200]
    log(f"whisper failed: {detail}")
    return JSONResponse({"error": "Transcription failed", "detail": detail}, status_code=500)
...
detail = stderr.decode()[:200] or stdout.decode()[:200]
return JSONResponse({"error": "Transcription failed", "detail": detail}, status_code=500)
```

**Impact:**
Leaks subprocess/internal error detail to clients.

**Remediation plan:**
1. Keep full detail in server logs only.
2. Return generic client-facing errors such as:
   - `{"error": "Transcription failed"}`
3. Optionally include a correlation ID for debugging.

---

### V2-09 · 🟡 MEDIUM — Secrets remain module globals; OpenAI key still passed via subprocess env
**Files:**
- globals: `server/apex.py:98-102`
- subprocess env pass-through: `server/apex.py:3323-3332`

**Evidence:**
```python
ALERT_TOKEN = os.environ.get("APEX_ALERT_TOKEN", "")
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
XAI_MANAGEMENT_KEY = os.environ.get("XAI_MANAGEMENT_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
```
```python
env={**os.environ, "OPENAI_API_KEY": OPENAI_API_KEY},
```

**Impact:**
- secrets remain easy to access from in-process debugging/introspection
- child process environment carries API key

**Remediation plan:**
1. Centralize secrets access behind a small wrapper that redacts `repr`/logs.
2. Avoid re-exporting secrets to subprocess env if there is a safer supported mechanism.
3. If env must be used, keep subprocess short-lived and never log full env.
4. Add log redaction for known key formats.

---

### V2-10 · 🟡 MEDIUM — Strong CSP still blocked by widespread inline handlers
**Files:**
- main UI inline handlers: `server/apex.py:5266-5288`, `5353`, `5378`, `5885`, `6459`, `6909-6973`, `7043-7045`
- dashboard inline handlers: `server/dashboard_html.py:1216`, `1234`, `1249`, `1316`, `1452`, `1545`, `1820`, `2515`, `2582`, `2774`, and many more
- no CSP header present in `server/apex.py:2502-2511`

**Impact:**
You added basic security headers, but a meaningful CSP is still blocked by inline `onclick`/templated handlers across both apps.

**Remediation plan:**
1. Replace inline event handlers with `addEventListener`.
2. Remove `onclick="..."` from HTML templates and `innerHTML`-generated fragments.
3. After refactor, add CSP in report-only mode first.
4. Then tighten to an enforcing CSP.

---

### V2-11 · 🟡 MEDIUM — TLS startup checks only verify env vars are non-empty, not file readability
**File:** `server/apex.py:9161-9168`

**Evidence:**
```python
if not (SSL_CERT and SSL_KEY and SSL_CA):
    ...
    sys.exit(1)
```

**Issue:**
The process checks only that env vars are set, not that the referenced files exist, are readable, and correspond to the expected types.

**Impact:**
- operationally brittle startup
- misleading “secure” startup path if wrong files are configured
- harder diagnostics for cert provisioning issues

**Remediation plan:**
1. Before `uvicorn.run`, validate that each path exists and is readable.
2. Emit clear startup errors naming the missing/unreadable file.
3. Optionally verify that CA/cert/key are parseable before serving.

---

### V2-12 · 🔵 LOW — Dynamic SQL composition patterns remain; safe today, brittle for future changes
**Files:**
- chat update: `server/apex.py:1590-1596`
- profile update: `server/apex.py:3051-3057`
- migration helper: `server/apex.py:1271-1273`

**Evidence:**
```python
sets = ", ".join(f"{k} = ?" for k in kwargs)
conn.execute(f"UPDATE chats SET {sets}, updated_at = ? WHERE id = ?", vals)
```
```python
cur = conn.execute(f"UPDATE agent_profiles SET {', '.join(fields)} WHERE id = ?", values)
```

**Assessment:**
These appear to rely on internally constrained field names today, so this is not an immediate exploit based on current call paths. Still, dynamic SQL string construction is a fragile pattern.

**Remediation plan:**
1. Enforce explicit field allowlists right next to each builder.
2. Avoid composing SQL identifiers from caller-provided strings unless strictly validated.
3. Add tests that reject unexpected field names.

---

### V2-13 · 🔵 LOW / OPERATIONAL — `/health` cannot be publicly probed without a client cert under current design
**Files:**
- allowlist: `server/apex.py:2460-2471`
- TLS requirement: `server/apex.py:9180-9185`
- runtime validation: no-cert `curl -sk https://127.0.0.1:8301/health` returned no HTTP response

**Issue:**
`/health` is allowlisted at the app layer, but transport-level `CERT_REQUIRED` blocks cert-less probes before the request reaches the app.

**Impact:**
- public/unauthenticated health checks will fail
- load balancers or uptime monitors need a client cert or a separate health surface

**Remediation options:**
1. Keep as-is and require health probes to use a client cert.
2. Or expose a truly public health endpoint on a separate localhost/reverse-proxy port.
3. Or terminate TLS upstream and enforce app-layer cert/session logic carefully — but only if you also fix V2-01/V2-02 first.

---

## Priority Remediation Plan

### P1 — Do next
1. **V2-01:** make HTTP middleware fail closed on missing peer cert
2. **V2-02:** make WebSocket handler close before `accept()` when peer cert is missing
3. **V2-03:** finish remaining DOM XSS cleanup in `server/apex.py`
4. **V2-04:** remove private TLS material from standard backup/restore flows

### P2 — Next hardening pass
5. **V2-05:** add real admin auth boundary for `/admin`
6. **V2-06:** add rate limiting / concurrency caps
7. **V2-07:** strengthen upload/audio validation and stop returning absolute paths
8. **V2-08:** stop returning raw Whisper stderr/stdout to clients
9. **V2-09:** reduce secret exposure and subprocess env leakage

### P3 — Security-first polish
10. **V2-10:** remove inline handlers and introduce CSP in report-only mode, then enforce
11. **V2-11:** add robust TLS file preflight checks
12. **V2-12:** clean up dynamic SQL patterns
13. **V2-13:** decide intended health-check model and document it

---

## Final Assessment

**Good news:** the most severe issue from V1 is fixed. The current direct dev instance is **not anonymously exposed** the way it was before.

**But:** this is not yet a complete hardening pass.

If Apex wants to lean into a **security-first / SecureClaw** posture, the next tranche of work should focus on:
- true fail-closed defense in depth for HTTP + WebSocket
- eliminating remaining authenticated XSS sinks
- separating routine backups from TLS private material
- adding admin auth/rate limiting/CSP groundwork

**Current state:**
> No longer critically open, but still needs one more serious security hardening pass before claiming strong default security.
