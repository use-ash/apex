---
name: Apex OSS extraction plan
description: Plan to open-source Apex as a standalone single-file Claude chat server
type: project
---

Apex (`server/apex.py`) is a candidate for OSS release as a standalone self-hosted Claude chat interface.

**What it is:** Single-file Python chat server (~1600 lines) with inline HTML/CSS/JS. Zero build step. Runs Claude via the Agent SDK with streaming, persistent sessions, file uploads, and TLS.

**Why OSS:** Nothing like it exists — existing options are full SaaS or bare API wrappers. Demand spiked after Computer Use announcement drove interest in self-hosted Claude interfaces.

**Extraction checklist:**
- Strip hardcoded workspace path (`/Users/dana/.openclaw/workspace`)
- Make password setup a first-run flow (not env var)
- Remove OpenClaw-specific hooks/references
- Make model configurable via env var (already done: `APEX_MODEL`)
- Add proper README with screenshots
- License: MIT
- Repo: `use-ash/apex` or standalone

**Could also serve as:** ASH customer service chat (swap system prompt, scope tools, add per-tenant isolation). The transport layer, auth, and streaming are production-grade.

## Security Roadmap ("SecureClaw")

Apex should differentiate from OpenClaw by being security-first. Every shortcut now becomes tech debt for the paid tier. The goal: users trust Apex with their API keys and conversations.

### Already implemented (2026-03-27)
- **mTLS** — client certificate required for all connections (dashboard + chat)
- **Password-masked credential input** — `type="password"`, `autocomplete="off"`
- **Key format validation** — prefix checks (`sk-ant-`, `xai-`), min/max length, control char rejection
- **Rate limiting** — 5s cooldown per provider on credential updates
- **Audit logging** — all credential changes logged with masked key + remote IP
- **Atomic .env writes** — temp file + rename, no partial state on crash
- **Whitespace stripping** — catches paste artifacts before saving
- **Input sanitization** — newline/null/control character rejection on all credential values

### Next: OSS release hardening
- **Encrypted-at-rest secrets** — macOS Keychain / Linux keyring / Windows DPAPI instead of plaintext .env
- **RBAC** — admin vs viewer roles (admin can change config/credentials, viewer is chat-only)
- **Session-based auth on top of mTLS** — for multi-user deployments
- **CSRF tokens** — on all state-changing endpoints (currently mTLS is the gate)
- **Content Security Policy** — restrict inline scripts/styles for XSS defense
- **Secrets redaction in logs** — scan all log output for API key patterns before writing

### Paid tier additions
- **Per-tenant isolation** — separate DB, workspace, and credential store per tenant
- **SSO/OIDC integration** — enterprise auth (Okta, Google Workspace, Azure AD)
- **Audit trail API** — queryable history of all admin actions
- **Key rotation workflows** — scheduled rotation with zero-downtime cutover
- **Compliance reporting** — SOC 2 / GDPR evidence generation from audit logs

**Why:** Dana identified this as both an OSS opportunity and a reference implementation for the ASH proxy architecture. OpenClaw's reputation for lax security is a cautionary tale — Apex should be the "SecureClaw" alternative.

**How to apply:** When the time comes, extract into a clean repo. Don't rush — get the SDK image upload bug fixed first and test the hooks integration end-to-end.
