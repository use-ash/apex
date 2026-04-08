# Apex

**Self-hosted AI agent platform. Multiple models. Persistent memory. Your machine, your data.**

Apex gives you a unified chat interface across Claude, Codex, Grok, and local models — with a memory system that makes the AI remember you across sessions, a skills engine you can extend, and an admin dashboard to manage it all. One Python server. Zero data leakage.

```bash
pip install fastapi uvicorn python-multipart claude-agent-sdk
python3 apex.py
```

Open `https://localhost:8300`. That's it.

---

## Why Apex?

Every hosted AI chat sends your data to someone else's servers. If you're working with proprietary code, sensitive documents, client data, or anything you wouldn't paste into a public website — that's a problem.

Apex keeps everything local. Your prompts, AI responses, files, and conversation history — all on your machine. The only external calls are to the AI providers you choose, using your own accounts.

But Apex isn't just a privacy wrapper. It's a platform:

- **Multi-model** — Use Claude, Codex, Grok, and local models through one interface
- **Memory** — The AI remembers your projects, preferences, and past conversations across sessions
- **Skills** — Extensible slash-command system for search, research, analysis, and automation
- **Self-hosted** — Runs on your hardware. You own the infrastructure.

---

## Models — Use Your Existing Subscriptions

Apex doesn't require separate API billing for most models. You connect your existing subscriptions.

### Claude (Anthropic)

Uses your existing Claude subscription (Pro / Max / Code) through the Agent SDK. No separate API key needed. Full tool ecosystem — Claude can read files, write code, run commands, search your codebase. Persistent sessions survive across messages. Up to 1M context with Opus 4.6.

**Models:** `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5`

### Codex (OpenAI)

Uses your existing ChatGPT subscription (Plus / Pro) through the Codex CLI. No separate API key needed. Supports one-shot tasks and multi-turn resume. Can run as a background agent for parallel work. Sandbox permissions control for network and disk access.

**Models:** `gpt-5.4`, `gpt-5.3`, `o3`, `o4-mini`

### Grok (xAI)

The one model that requires a separate API key (xAI doesn't offer a subscription product). Pay-per-use via the xAI API. 2M context window. Native web search and X/Twitter search built into the model. Configurable thinking levels.

**Models:** `grok-4`, `grok-4-fast`

### Local Models (Ollama / MLX)

Zero-cost inference on your own hardware. No API key, no account, no internet required. Full tool-calling loop included — local models can read files, run commands, and search code, just like Claude. MLX support for optimized Apple Silicon inference.

**Models:** Any Ollama-compatible model — Qwen, Gemma, Llama, Mistral, etc.

### Per-Chat Routing

Each conversation targets a specific model. Run Claude for deep coding tasks, Grok for web research, Codex for a background audit, and a local model for quick questions — all simultaneously in separate channels. Switch models per conversation, not per app.

---

## Memory System

This is what makes Apex different from a chat wrapper. The AI maintains context across sessions, across models, across restarts.

### Project Instructions (APEX.md)

Drop an `APEX.md` file in your workspace with project rules, coding conventions, architecture notes — whatever context the AI should always have. It's automatically injected into every session for every model. Define your rules once; every model follows them.

### Persistent Memory (MEMORY.md)

Accumulated knowledge that persists across sessions. The AI can read and update memory files as it learns about your project. Memory is indexed and searchable — the AI can recall facts from weeks ago.

### Semantic Search (Embedding Index)

All memory files and conversation transcripts are indexed with vector embeddings. The index updates incrementally — only changed files are re-embedded. Hybrid recall combines keyword matching with semantic similarity, so the AI finds relevant context even without exact keyword matches.

### Whisper Injection (Automatic Context Recall)

On each message, the server silently searches the embedding index for memories relevant to your current topic and injects them into the prompt. The AI "remembers" things you discussed in previous sessions without you asking. You might ask about a deployment and the AI already knows the server config, the last incident, and the fix you applied — because the whisper system found and injected those memories.

### Session Recovery

When a session hits the context limit and compacts, or when the server restarts, the system generates a structured recovery briefing: what was being discussed, what was decided, what's pending. The briefing is injected into the next message. Conversations survive restarts and crashes — no "I don't have context from our previous conversation."

### Cross-Model Continuity

The memory system works for ALL backends. Claude, Grok, Codex, and local models all receive the same project instructions, the same memories, the same whisper injections. Switch from Claude to Grok mid-project — Grok already knows what you were working on.

---

## Skills

Apex includes a slash-command skill system. Type a command, the server executes it, and the results are injected into the AI's context. Skills are discoverable, extensible, and self-improving.

### Built-In Skills

**Search & Memory**
- `/recall <topic>` — Full-text search across all conversation transcripts. Find what you discussed, when, and what was decided.
- `/embedding <query>` — Semantic search across memory and transcripts. Finds conceptually related content, not just keyword matches.

**Multi-Agent Delegation**
- `/codex <task>` — Delegate a task to OpenAI Codex as a parallel background agent. It runs independently and returns structured results.
- `/grok <question>` — Web research via xAI. Live web search, X/Twitter search, configurable thinking levels.
- `/ask-claude <question>` — Query Claude locally with full workspace context.
- `/delegate <task>` — Dispatch tasks to background agents in parallel with convergence checking.

**Analysis & Thinking**
- `/first-principles <topic>` — 4-layer deep analysis: strip assumptions to bedrock truth, Feynman test, self-challenge, zero-base rebuild.
- `/stop-slop <text>` — Score prose on 5 dimensions and rewrite AI-sounding text to sound human.
- `/improve <skill>` — Analyze a skill's usage metrics and feedback log, propose concrete improvements.

**Content & Research**
- `/evaluate-repo <url>` — Sandbox-assess any GitHub repo. Clones to /tmp, reads code, reports findings. Never touches your workspace.
- `/youtube <url>` — Fetch and analyze YouTube transcripts.
- `/check-logs` — Read and search application logs with level filtering.

### Build Your Own Skills

Skills are just directories with a `SKILL.md` file. Apex discovers them automatically — no registry, no configuration.

```
skills/my-skill/
├── SKILL.md          # Required — metadata + instructions
├── run.sh            # Optional — executable entry point
├── helper.py         # Optional — any supporting code
├── metrics.json      # Auto-generated — usage tracking
├── changelog.md      # Version history
└── feedback.log      # User corrections (append-only)
```

**Two types of skills:**

1. **Executable skills** — Have a `run.sh` or script. The server executes it and passes results to the AI. Use this for tools that call APIs, search databases, run analyses.

2. **Thinking skills** — No script. The AI reads the `SKILL.md` instructions and follows them directly. Use this for analysis frameworks, writing styles, review checklists.

**Minimal SKILL.md:**

```yaml
---
name: my-skill
description: "What this skill does (shown in /help)"
version: "1.0.0"
usage: /my-skill <args>
examples:
  - /my-skill analyze this code
  - /my-skill --verbose check deployment
metadata:
  {"apex":{"tags":["analysis"],"risk_tier":1}}
---

# My Skill — Title

## When to Use
Describe when the agent should invoke this skill.

## How to Execute
Step-by-step instructions or script invocation.
```

Drop it in `skills/`, restart the server, and it's live. The server automatically:
- Discovers it from the `SKILL.md` frontmatter
- Adds it to the skills catalog shown to the AI
- Tracks usage metrics (invocations, success rate, duration)
- Collects user feedback in `feedback.log`

**Self-improving skills:** The `/improve` meta-skill reads a skill's metrics and feedback log, then proposes concrete changes. Skills get better over time based on how you actually use them.

**Risk tiers** control what skills can do without approval:
| Tier | Behavior | Examples |
|------|----------|---------|
| 1 | Auto-approve | Read-only analysis, formatting, search |
| 2 | Notify | File modifications, new dependencies |
| 3 | Require approval | API calls, credential access, external writes |

---

## Admin Dashboard

Full web-based management portal at `/admin`. 61 REST API endpoints — usable by humans (web UI) and AI agents (JSON API).

**Health & Monitoring**
- Server status and uptime
- Per-provider model reachability (green/red dots for each AI provider)
- Database stats, TLS certificate status

**Configuration**
- Server settings, default model, timeouts
- Feature toggles (whisper, skills, compaction)
- Local model server URLs

**Credentials**
- Set/update API keys with masked input
- Format validation, rate limiting, audit logging
- Atomic writes — no partial state on crash

**TLS Certificates**
- Generate CA, server, and client certificates
- Download .p12 bundles and QR codes for mobile
- Certificate revocation

**Workspace**
- Edit project instructions (APEX.md) from the browser
- Manage memory files
- Enable/disable skills

**Sessions & Logs**
- View active sessions with token usage
- Force compaction, kill sessions
- Live log streaming (SSE)
- Database backup/restore

---

## Alert System

Multi-channel notifications for when the AI or your systems need to reach you:

- **In-app** — Real-time WebSocket delivery with badge counters
- **Telegram** — Bot delivery for mobile push notifications (optional)
- **REST API** — Any external script, cron job, or service can POST alerts into Apex
- **Persistent inbox** — All alerts stored with ack/unack tracking, searchable by category and severity

Alerts support custom categories, severity levels (info/warning/critical), and structured metadata. Use them for CI/CD notifications, monitoring alerts, scheduled reports, or anything else.

---

## Security

Apex is built security-first. Your AI conversations and API keys deserve production-grade protection.

- **mTLS** — Client certificate authentication for all connections. No passwords to steal.
- **Credential management** — Masked input, format validation, rate limiting, audit logging
- **Atomic writes** — Config and credential updates use temp file + rename. No partial state.
- **Input sanitization** — Control character, null byte, and injection rejection on all inputs
- **Secrets isolation** — Credentials stored in `.env` only, never in the database
- **TLS everywhere** — HTTPS for all connections, with built-in cert generation tools

---

## Architecture

```
server/
├── apex.py              — FastAPI entry point, router registration, startup
├── state.py             — shared in-memory state (Layer 0)
├── db.py                — SQLite: chats, messages, alerts, personas, devices
├── ws_handler.py        — WebSocket handler, multi-level session recovery
├── agent_sdk.py         — Claude Agent SDK query execution + auth recovery
├── streaming.py         — WS broadcast, alert fanout, SSE helpers
├── model_dispatch.py    — model routing (Claude / Grok / Ollama / MLX / Codex)
├── tasks.py             — background task registry (F-7)
├── skills.py            — server-side skill dispatch
├── memory_extract.py    — memory extraction + whitelist
├── routes_alerts.py     — alerts REST + APNs push notifications
├── routes_chat.py       — chat + message REST endpoints
├── routes_profiles.py   — persona management + model overrides
├── routes_tasks.py      — background task REST + SSE live-tail
├── routes_models.py     — model list + health endpoints
├── routes_upload.py     — file + image upload handling
├── routes_misc.py       — usage, health, config endpoints
├── dashboard.py         — admin dashboard routes
├── chat_html.py         — embedded chat UI (HTML/CSS/JS, no build step)
├── dashboard_html.py    — embedded admin UI
├── config.py            — environment config + feature flags
├── context.py           — session context helpers
├── backends.py          — model backend definitions
└── log.py               — structured logging (Layer 0)
```

No frameworks. No npm. No build step. The frontend is embedded Python — no separate build pipeline. Entry point is `apex.py`; each module has explicit layer dependencies so the codebase stays auditable as it grows.

---

## Configuration

All configuration via environment variables or the admin dashboard:

| Variable | Default | Description |
|----------|---------|-------------|
| `APEX_HOST` | `0.0.0.0` | Bind address |
| `APEX_PORT` | `8300` | Port |
| `APEX_MODEL` | `claude-sonnet-4-6` | Default model for new chats |
| `APEX_WORKSPACE` | current dir | Working directory for AI tools |
| `APEX_SSL_CERT` | — | TLS certificate (enables HTTPS) |
| `APEX_SSL_KEY` | — | TLS private key |
| `APEX_SSL_CA` | — | CA cert for mTLS client verification |
| `APEX_DEBUG` | `false` | Verbose logging |
| `APEX_ENABLE_WHISPER` | `false` | Enable memory whisper injection |
| `APEX_OLLAMA_URL` | `http://localhost:11434` | Ollama server address |
| `APEX_MLX_URL` | `http://localhost:8400` | MLX server address |
| `XAI_API_KEY` | — | xAI API key for Grok models |
| `GOOGLE_API_KEY` | — | Google API key for embedding index |

---

## Requirements

- Python 3.10+
- A Claude subscription (Pro/Max/Code) for Claude models — or —
- A ChatGPT subscription (Plus/Pro) for Codex models — or —
- Ollama or MLX for free local inference — or —
- An xAI API key for Grok models
- Use any combination. Mix and match per conversation.

**Optional:**
- Google API key for semantic search embeddings (free tier sufficient)
- Telegram bot token for mobile alert delivery
- Whisper binary for voice transcription

---

## Quick Start

### Claude Only

```bash
pip install fastapi uvicorn python-multipart claude-agent-sdk
python3 apex.py
```

Your Claude subscription is detected automatically via the Agent SDK.

### Claude + Local Models

```bash
# Install Ollama (https://ollama.ai)
ollama pull qwen3.5

# Start Apex
python3 apex.py
```

Create a Claude channel for heavy tasks and an Ollama channel for quick questions.

### With mTLS (Recommended for Network Access)

```bash
# The dashboard can generate certs for you, or bring your own:
APEX_SSL_CERT=cert.pem APEX_SSL_KEY=key.pem APEX_SSL_CA=ca.pem python3 apex.py
```

### Full Stack

```bash
export APEX_ENABLE_WHISPER=1
export XAI_API_KEY=xai-...
export GOOGLE_API_KEY=AIza...
python3 apex.py
```

All models active. Memory system with semantic search. Whisper injection. Full skill dispatch.

---

## iOS App

The iOS app is a **free download** on the App Store. It connects to your self-hosted server, but requires your server to have a valid license key.

- Native SwiftUI — not a PWA. Background survival, push notifications, gesture navigation.
- mTLS authentication — certificate-pinned to your server.
- Multi-channel chat with real-time streaming
- File, image, and voice uploads
- Alert inbox with push notifications
- Connection profiles for WiFi/VPN switching

The server and webapp are free forever. Everything is free through September 30, 2026 with no license required. After that, a license key ($29.99/mo, $249/yr, or $499 lifetime for the first 500) unlocks group channels, multi-agent orchestration, custom personas, and native app connectivity.

---

## Use Cases

**Software Development** — Claude reads your codebase, writes code, runs tests. Memory remembers your architecture decisions. Skills delegate code reviews to Codex in the background.

**Research & Writing** — Grok searches the web for current information. Claude analyzes and synthesizes. `/first-principles` strips topics to bedrock truth. `/stop-slop` cleans up AI prose.

**System Administration** — Claude manages configs, reads logs, runs diagnostics. Alerts notify you of issues. The dashboard gives you a control panel for everything.

**Personal Knowledge Base** — Every conversation is indexed and searchable. Memory accumulates over time. The AI gets better at helping you because it remembers what you've discussed before.

**Team Tooling** — Run an instance per developer. Each person's memory and project context stays isolated. Skills can be shared across instances via git.

---

## FAQ

**Is this a wrapper around the API?**
No. Claude runs through the Agent SDK with full tool access (read, write, bash, search). Codex runs through the CLI with sandbox permissions. Local models get a custom tool-calling loop. It's closer to Claude Code than to a simple chat interface.

**Can I use it on my phone?**
The webapp works in mobile browsers. The iOS app is a free download. Through September 30, 2026, it connects with no license required. After that, your server needs a valid license key ($29.99/mo, $249/yr, or $499 lifetime).

**Can multiple people use one server?**
The current architecture is single-user. Multi-user with RBAC is on the enterprise roadmap.

**How much does it cost to run?**
If you already pay for Claude and/or ChatGPT, Apex adds zero cost for those models. Local models (Ollama/MLX) are free. Only Grok requires a separate API key. Hosting is your own hardware.

**What if I only want local models?**
That works. Install Ollama, pull a model, start Apex. No API keys, no accounts, no internet needed for inference. You still get the full memory system, skills, and dashboard.

**Can I build my own skills?**
Yes. Drop a directory with a `SKILL.md` into `skills/` and restart. See the [Skills](#build-your-own-skills) section.

---

## License

MIT
