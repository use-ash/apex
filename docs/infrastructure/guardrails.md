# Guardrails

Apex runs AI models that can read files, execute commands, and modify your system. Guardrails are the safety layer that controls what those models are allowed to do.

Every tool call goes through the guardrail system before it executes. If a call looks dangerous, it gets blocked and you get an alert.

---

## How It Works

When an AI model tries to use a tool (write a file, run a bash command, read a file), the guardrail checks three things:

1. **Is the file protected?** Some files should never be modified by an AI model.
2. **Is it inside the sandbox?** Tool calls are restricted to your workspace and temp directories.
3. **Is the command safe?** Bash commands are scanned for patterns that could bypass file protections.

If a check fails, the call is blocked, an audit log entry is written, and you get an alert (in-app and optionally via Telegram).

---

## Protected Files

These files are always blocked from AI modification:

| Category | Examples |
|----------|---------|
| **Credentials** | `.env`, `.env.local`, `.key`, `.pem`, `.secret`, `credentials.json` |
| **SSH** | Anything under `~/.ssh/` |
| **Secrets directories** | Any path containing `/secrets/` |

You can add your own protected files through the admin dashboard under **Guardrails > Whitelist**.

---

## Sandbox

AI tool calls are restricted to allowed directories:

**Allowed:**

- Your configured workspace (set during setup)
- `/tmp/` and `/private/tmp/`
- `~/.claude/` (Claude Code data)

**Blocked:**

- `~/.ssh/`
- `/etc/`, `/usr/`, `/bin/`, `/sbin/`
- `/System/`, `/Library/`
- System directories that should never be modified by AI

If a model tries to write outside the sandbox, the call is blocked immediately.

---

## Bash Command Scanning

Bash commands get extra scrutiny because they can bypass file-level protections. The guardrail detects these patterns:

- **Output redirection** (`>`, `>>`, `tee`)
- **File operations** (`cp`, `mv`, `sed -i`)
- **Heredocs** (`cat << EOF > file`)
- **Encoded payloads** (`base64 -d | bash`)
- **Variable interpolation** that targets protected paths

If a bash command would write to a protected file or escape the sandbox, it is blocked.

---

## Whitelist (Temporary Exemptions)

Sometimes you need the AI to do something the guardrail would normally block. The whitelist system lets you grant time-limited exemptions:

- Exemptions are scoped to a specific **tool + target** combination
- Each exemption has an **expiration time**
- Expired exemptions are automatically ignored

Manage the whitelist from the admin dashboard: **Settings > Guardrails**.

---

## Audit Log

Every tool call is logged to `agent_audit.jsonl` with:

- Timestamp
- Tool name and arguments
- Whether it was allowed, blocked, or allowed via whitelist
- The session and actor that made the call
- Reason for blocking (if blocked)

The audit log is append-only. It is never modified or deleted by the AI.

---

## Alerts

When a guardrail blocks a dangerous action, you get notified:

- **In-app alert** — appears in the Apex alerts panel (bell icon)
- **Telegram** — if configured, sends to your alert channel
- **iOS push notification** — if the mobile app is set up

Alerts are throttled to prevent flooding (5-minute window per unique alert type).

---

## Secret Scrubbing

Before any tool output is logged or displayed, the guardrail scrubs known API key patterns:

- Anthropic (`sk-ant-*`)
- OpenAI (`sk-proj-*`, `sk-*`)
- xAI (`xai-*`)
- Google (`AIza*`)
- AWS (`AKIA*`)
- GitHub (`ghp_*`, `ghu_*`)
- Generic key/token/secret patterns

Scrubbed values are replaced with `[REDACTED]` in the audit log.

---

## Authentication & Access Control

Apex uses mutual TLS (mTLS) as its primary access control:

- **Client certificate required** — every connection must present a valid certificate signed by the Apex CA
- **No passwords to guess** — there is no username/password login. If you don't have the certificate, the TLS handshake fails before any HTTP request reaches the server
- **API key validation** — during setup, all API keys are validated against their provider before being saved. Invalid keys are rejected with a clear error message
- **OAuth auto-recovery** — if your Claude subscription token expires, Apex automatically refreshes it from your macOS Keychain on the next request. No manual re-authentication needed (as long as you have a GUI terminal session open)

### Setup Validation

The setup wizard validates credentials at entry time:

| Provider | Validation Method |
|----------|------------------|
| Claude (OAuth) | `claude auth status` CLI check — verifies login, email, subscription |
| Claude (API key) | REST API call to Anthropic |
| Grok (xAI) | `GET /v1/models` — verifies key is active |
| Google | `GET /v1beta/models` — verifies key is active |
| OpenAI | `GET /v1/models` — verifies key is active |

Invalid keys are not saved. The setup wizard shows a per-field error and blocks advancement until the key is corrected or removed.

---

## For Developers

The guardrail system is implemented in two layers:

1. **`guardrail_core.py`** — shared logic for all backends (file protection, sandbox, bash scanning, whitelisting, alerting, audit logging)
2. **Backend adapters** — thin wrappers that call `guardrail_core` before executing tool calls:
    - Claude Code: via CLI hooks (`PreToolUse`, `PostToolUse`)
    - Local models (Ollama): via `local_model/guardrails.py`
    - Grok: via the skill wrapper

All backends share the same protection rules, audit log format, and alert pipeline.
