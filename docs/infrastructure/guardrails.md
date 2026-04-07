# Guardrails

Apex runs AI models that can read files, execute commands, and modify your system. Guardrails control what those models are allowed to do.

Every tool call goes through the guardrail system before it executes. If a call is not permitted at the current permission level, it gets blocked.

---

## Permission Levels

Each chat can be assigned a permission level that controls what tools the AI can use. Higher levels unlock more capabilities.

| Level | Name | What It Can Do | What It Cannot Do |
|-------|------|----------------|-------------------|
| **L0** | Restricted | Nothing — all tools blocked | Everything |
| **L1** | Standard | Read files, list directories, search files | Write files, run commands, use browser, execute code |
| **L2** | Workspace | Everything in L1, plus: write/edit files, run sandboxed Python (Jupyter), restricted shell commands, browse the web (Playwright, Fetch), use MCP filesystem tools (read-only) | Run arbitrary shell commands, use subprocess/os.system from code, write via MCP filesystem, access system directories |
| **L3** | Elevated | Everything in L2, plus: full shell access (allowlisted commands), run scripts, write via MCP filesystem | System-level commands not on the allowlist, paths outside workspace |
| **L4+** | Admin | Unrestricted tool access | Nothing is blocked |

**Default for new chats:** L2 (Workspace).

Levels are set per-chat in the chat settings panel. Changing the level takes effect immediately — no restart needed.

---

## Sandboxed Code Execution (L2)

At L2, the `execute_code` tool runs Python in a stateful Jupyter kernel. An AST-level sandbox blocks dangerous operations before execution:

- **Blocked imports:** `subprocess`, `shutil`, `signal`, `ctypes`, `importlib`
- **Blocked calls:** `os.system()`, `os.popen()`, `os.exec*()`, `shutil.rmtree()`
- **Blocked builtins:** `exec()`, `eval()`, `compile()`, `__import__()`

At L3+, these restrictions are lifted.

Each chat gets its own isolated kernel — state does not leak between chats.

---

## Shell Command Restrictions

Bash commands are validated differently at each level:

| Level | Allowed |
|-------|---------|
| **L1** | No shell access |
| **L2** | Version checks only (`python3 --version`, `git --version`, `py_compile`) |
| **L3** | Allowlisted commands (git, curl, ls, find, grep, python3, node, npm, etc.) within workspace paths. Stderr redirects permitted. |
| **L4+** | Unrestricted |

At all levels, commands targeting protected paths or system directories are blocked.

---

## File Protection

### Protected Files

These files are always blocked from AI modification:

| Category | Examples |
|----------|---------|
| **Credentials** | `.env`, `.env.local`, `.key`, `.pem`, `.secret`, `credentials.json` |
| **SSH** | Anything under `~/.ssh/` |
| **Secrets directories** | Any path containing `/secrets/` |

### Sandbox Boundaries

Tool calls are restricted to allowed directories:

**Allowed:** Your configured workspace, `/tmp/`, `~/.claude/`

**Blocked:** `~/.ssh/`, `/etc/`, `/usr/`, `/bin/`, `/sbin/`, `/System/`, `/Library/`

---

## Bash Command Scanning

Bash commands get extra scrutiny because they can bypass file-level protections:

- **Output redirection** (`>`, `>>`, `tee`)
- **File operations** (`cp`, `mv`, `sed -i`)
- **Heredocs** (`cat << EOF > file`)
- **Encoded payloads** (`base64 -d | bash`)
- **Variable interpolation** that targets protected paths

If a command would write to a protected file or escape the sandbox, it is blocked.

---

## Tool Policy Dashboard

The admin dashboard (**Settings > Guardrails**) lets you customize which tools are available at L2:

- Toggle individual tools on/off
- Tools are grouped by category: built-in, MCP, SDK
- New tools added in updates are auto-merged into your saved config
- Whitelist time-limited exemptions for specific tool + target combinations

---

## Audit Log

Every tool call is logged to `agent_audit.jsonl` with:

- Timestamp, tool name, and arguments
- Whether it was allowed, blocked, or allowed via whitelist
- The session and actor that made the call
- Reason for blocking (if blocked)

The audit log is append-only. It is never modified or deleted by the AI.

---

## Alerts

When a guardrail blocks a dangerous action, you get notified:

- **In-app alert** — appears in the Apex alerts panel
- **Telegram** — if configured, sends to your alert channel
- **iOS push notification** — if the mobile app is set up

Alerts are throttled to prevent flooding (5-minute window per unique alert type).

---

## Secret Scrubbing

Before any tool output is logged or displayed, the guardrail scrubs known API key patterns:

- Anthropic (`sk-ant-*`), OpenAI (`sk-proj-*`), xAI (`xai-*`), Google (`AIza*`), AWS (`AKIA*`), GitHub (`ghp_*`, `ghu_*`)
- Generic key/token/secret patterns

Scrubbed values are replaced with `[REDACTED]` in the audit log.

---

## Authentication

Apex uses mutual TLS (mTLS) as its primary access control:

- **Client certificate required** — every connection must present a valid certificate signed by the Apex CA
- **No passwords** — if you don't have the certificate, the TLS handshake fails before any HTTP request reaches the server
- **API key validation** — during setup, all provider keys are validated before being saved
- **OAuth auto-recovery** — expired Claude tokens are refreshed automatically from macOS Keychain

---

## Architecture

The guardrail system has two layers:

1. **`tool_access.py`** — permission levels, tool gating, path validation, command validation
2. **`guardrail_core.py`** — file protection, sandbox boundaries, bash scanning, whitelisting, alerting, audit logging

All backends (Claude SDK, local models, Grok) share the same protection rules and audit pipeline.
