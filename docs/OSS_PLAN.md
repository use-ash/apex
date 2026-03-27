---
name: Apex OSS + Monetization Plan
description: Free server (OSS) + paid iOS app subscription + enterprise tier
type: project
---

# Apex: Product Tiers

## Monetization Model

**Server = Free (OSS, MIT license).** iOS app = Paid subscription.

The server is the adoption engine — developers set it up, see it's real, trust it with their keys. The iOS app is the daily-driver convenience that turns users into subscribers. Enterprise features serve organizations.

| Tier | What | Price |
|------|------|-------|
| **Free** | Self-hosted server + webapp | $0 (bring your own API keys) |
| **Apex Pro** | iOS app subscription | ~$4.99/mo or $39.99/yr |
| **Enterprise** | Multi-tenant, SSO, compliance | Custom pricing |

---

## Free Tier — Self-Hosted Server (OSS)

Everything a single user needs to run a fully-featured AI agent platform on their own hardware. Zero third-party data flow — all conversations stay on their machine.

### Multi-Model Unified Chat
Users bring their own API keys and get a single interface across all models:

- **Claude** (Anthropic) — Full Agent SDK integration with persistent sessions, tool use (Read/Write/Edit/Grep/Glob/Bash), 1M context. Models: Opus 4.6, Sonnet 4.6, Haiku 4.5. Uses your existing Claude subscription (Pro/Max/Code) via Agent SDK — no separate API key.
- **Grok** (xAI) — xAI API with web search, X/Twitter search, 2M context. Models: grok-4, grok-4-fast. Requires xAI API key (pay-per-use — the only model needing a separate API key).
- **Codex** (OpenAI) — Codex CLI wrapper for code tasks. Models: gpt-5.4, gpt-5.3, o3, o4-mini. Uses your existing ChatGPT subscription (Plus/Pro) via Codex CLI — no separate API key.
- **Local models** (Ollama / MLX) — Zero-cost inference on Mac. Qwen 3.5, Gemma 3, any Ollama-compatible model. 128K context. Tool-calling loop included. No account needed.

Per-chat model routing: each conversation can target a different backend independently. Run Claude, Grok, and a local model simultaneously in separate channels.

### Skills System (18+ skills)
Server-side skill dispatch — type a slash command, the server handles execution:

- `/recall` — Full-text search across all conversation transcripts (170+ sessions)
- `/embedding` — Semantic search via Gemini Embedding 2 (3072-dim vectors, hybrid BM25 + cosine)
- `/codex` — Delegate tasks to OpenAI Codex as a parallel agent (background execution)
- `/grok` — Live web research via xAI (web search, X search, thinking levels)
- `/ask-claude` — Query Claude Code locally with full workspace context
- `/evaluate-repo` — Sandbox and assess any GitHub repo (cloned to /tmp, never workspace)
- `/youtube` — Fetch and analyze YouTube transcripts
- `/first-principles` — 4-layer deep analysis (strip assumptions, Feynman test, self-challenge, zero-base)
- `/stop-slop` — Rewrite AI-sounding prose to sound human
- `/improve` — Analyze skill metrics and propose improvements with structured diffs
- `/delegate` — Dispatch tasks to Codex as parallel background agents
- Plus `/x-post`, `/scrapling`, `/check-logs`, `/portfolio-manager`, and more

### Memory, Whisper & Continuity System (Subconscious)
The system that makes the AI feel like it knows you across sessions:

- **Persistent memory** — CLAUDE.md (project instructions) + MEMORY.md (accumulated knowledge) auto-injected into every session. The AI reads your rules and remembers your preferences.
- **Embedding index** — All memory files and conversation transcripts indexed with Gemini Embedding 2. Semantic search finds relevant context even when you don't use exact keywords.
- **Whisper injection** — On each message, the server searches the embedding index for memories relevant to what you're currently discussing and silently injects them into the prompt. The AI "remembers" without you having to ask.
- **Session recovery** — When a session compacts (context limit) or the server restarts, the system generates a structured recovery briefing (what was being discussed, what was decided, what's pending) and injects it into the next message. Conversations survive restarts.
- **Recent exchange context** — For fresh sessions, the last 2 Q&A pairs from the database are injected so the AI has immediate conversational continuity.
- **Transcript export** — All conversations are exported to searchable JSONL transcripts for the embedding system and `/recall`.

This is what makes Apex different from a bare API wrapper — the AI maintains context across sessions, across models, across restarts.

### Unified Experience Across Models
The continuity system works for ALL backends, not just Claude:

- **Claude** gets CLAUDE.md + MEMORY.md + skills + whisper via the Agent SDK system prompt
- **Grok** gets the same context injected into its prompt, plus its own identity and web search capabilities
- **Local models** (Ollama/MLX) get context injection + the custom tool-calling loop for file operations
- **Codex** gets workspace context when delegated tasks

Every model sees the same memory, the same project instructions, the same conversation history. Switching between Claude and Grok feels seamless — they both know what you were working on.

### Admin Dashboard (61 REST endpoints)
Full web-based server management at `/admin`:

- **Health monitoring** — Server status, database stats, TLS cert validity, model provider reachability (green/red dots per provider)
- **Configuration** — Server settings, default model, compaction thresholds, timeouts
- **Credentials** — Set/update API keys with masked input, format validation, rate limiting, audit logging
- **TLS certificates** — Generate CA, server certs, client certs (.p12), QR codes for mobile provisioning
- **Workspace** — Edit CLAUDE.md, manage memory files, enable/disable skills, manage guardrail whitelists
- **Sessions** — List active sessions, view context usage, force compaction, kill sessions
- **Logs** — Tail logs with search/level filter, SSE live streaming
- **Database** — VACUUM, backup/restore (tarball export)

### Alert System
Multi-channel alert delivery:

- **In-app** — Real-time WebSocket delivery with badge counters, long-poll support
- **Telegram** — Bot delivery for mobile notifications when away from the app
- **Database** — Persistent alert history with ack/unack tracking
- Trading scripts (or any external system) can POST alerts via authenticated REST endpoint

### Security (SecureClaw)
Production-grade from day one:

- **mTLS** — Client certificate required for all connections (no passwords to steal)
- **Credential management** — Password-masked input, format validation, rate limiting, audit logging, atomic writes
- **Input sanitization** — Newline/null/control character rejection on all values
- **Secrets never in DB** — Credentials stored in .env only, never in SQLite

### What Free Users Need
- A machine to run the server (Mac, Linux, or any Python 3.14+ host)
- Claude subscription (Pro/Max/Code) — uses existing sub, no separate API key
- ChatGPT subscription (Plus/Pro) — uses existing sub via Codex CLI, no separate API key
- xAI API key for Grok — the only model requiring a separate pay-per-use key
- Google API key for embeddings (free tier covers personal use)
- Optional: Ollama or MLX for zero-cost local inference (no account needed)
- Optional: Telegram bot token for mobile alerts

---

## Apex Pro — iOS App Subscription (~$4.99/mo or $39.99/yr)

The iOS app that turns Apex into a mobile-first AI agent platform. Connects to your self-hosted server via mTLS.

### What subscribers get:
- **Native SwiftUI app** — Not a PWA. Real iOS app with background survival, push notifications, gesture navigation
- **mTLS authentication** — Certificate-pinned to your server's CA. No passwords.
- **Multi-channel chat** — Create separate channels for Claude, Grok, local models, and alerts
- **Real-time streaming** — Watch responses stream in real-time over WebSocket
- **File & image uploads** — Send files, images, and voice memos directly from iOS
- **Voice transcription** — Whisper-powered voice-to-text for hands-free prompts
- **Alert inbox** — Push notifications for trading alerts, system events, health checks
- **Background connectivity** — BGTask keepalive so alerts arrive even when the app is suspended
- **Connection profiles** — Switch between WiFi and VPN server addresses with one tap
- **Offline resilience** — Message history cached locally, auto-reconnect on network change

### Why it's worth paying for:
- Active maintenance against iOS updates, SDK changes, new Claude/Grok features
- App Store distribution (signed, reviewed, auto-updated)
- The server is where the intelligence lives — the app is how you access it from anywhere

---

## Enterprise Tier (Custom Pricing)

For organizations deploying Apex as internal AI infrastructure:

- **Per-tenant isolation** — Separate database, workspace, and credential store per user/team
- **SSO/OIDC** — Okta, Google Workspace, Azure AD integration
- **RBAC** — Admin vs viewer roles (admin manages config/credentials, viewer is chat-only)
- **Audit trail API** — Queryable history of all admin actions
- **Key rotation workflows** — Scheduled rotation with zero-downtime cutover
- **Compliance reporting** — SOC 2 / GDPR evidence generation from audit logs
- **SLA guarantees** — Uptime commitments, priority support

---

## Extraction Checklist (for OSS release)

- [ ] Strip hardcoded workspace path (`/Users/dana/.openclaw/workspace`)
- [ ] Make password setup a first-run flow (not env var)
- [ ] Remove OpenClaw-specific hooks/references
- [ ] Remove trading-specific skills (portfolio-manager, etc.)
- [ ] Add setup wizard (server URL, API keys, cert generation)
- [ ] Encrypted-at-rest secrets (Keychain / keyring / DPAPI)
- [ ] CSRF tokens on state-changing endpoints
- [ ] Content Security Policy headers
- [ ] Secrets redaction in log output
- [ ] Proper README with screenshots + quickstart
- [ ] License: MIT
- [ ] Repo: `use-ash/apex` or standalone
- [ ] iOS app: separate private repo, App Store distribution only

**Why:** Apex is both an OSS opportunity and a reference implementation for the ASH proxy architecture. OpenClaw's reputation for lax security is a cautionary tale — Apex is the "SecureClaw" alternative. The free server builds the community; the iOS subscription builds the business.
