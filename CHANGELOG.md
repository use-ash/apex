# Changelog

All notable changes to Apex are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [0.1.0] — 2026-03-28

First OSS-ready release.

### Added
- **Setup wizard** (`setup.py`) — interactive 4-phase onboarding: certs, models, knowledge, launch
- **Network access step** in setup wizard — users choose localhost-only or LAN/VPN access with security warnings
- **Generic launcher** (`server/launch.sh`) — .env autodiscovery, first-run detection, SSL defaults
- **Persona templates** — 6 opt-in agent personas (Architect, Marketing, Operations, Kodi, Codex, Designer) installable via API
- **Config-based overrides** — alert categories, category titles, and personas survive upgrades via `state/config.json` and database
- **`local_model` package** bundled in repo — Ollama/xAI tool loop, no external dependency needed
- **Admin dashboard** — 61 REST endpoints, embedded SPA at `/admin`
- **Alert system** — WebSocket + Telegram + REST delivery, configurable categories
- **Groups & threads** — multi-agent channels with @mention routing, gated behind `APEX_GROUPS_ENABLED`
- **V3 pill UI** — tool pills, thinking pills, side panel, hybrid streaming/history rendering
- **Multi-stream task management** — concurrent agent responses in group channels
- **Session recovery** — structured briefings on restart/compaction/crash
- **Embedding system** — Gemini Embedding 2 semantic search, whisper injection
- **GETTING_STARTED.md** — 700-line walkthrough for non-technical users
- **CONTRIBUTING.md** — PR guidelines, dev setup, contribution areas
- **UPGRADE_GUIDE.md** — what survives upgrades, how to upgrade
- **Docker test suite** — 33 fresh-install checks + 7 security tests
- **Elastic License 2.0** (ELv2)

### Security
- **mTLS enforced** — `CERT_REQUIRED` at TLS level (was `CERT_OPTIONAL`)
- **Auth middleware** on all HTTP routes (defense-in-depth), only `/health` is public
- **WebSocket cert check** — peer cert validated before accepting connections
- **Origin header required** on WebSocket connections (no-origin = denied)
- **Security response headers** — `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Strict-Transport-Security`
- **Timing-safe token comparison** — `hmac.compare_digest` for bearer token auth
- **Default bind to localhost** — `127.0.0.1` by default, network access requires explicit `APEX_HOST=0.0.0.0`

### Changed
- Project instructions renamed from `CLAUDE.md` to `APEX.md` (backward-compat fallback preserved)
- Dashboard API routes renamed from `/api/workspace/claude-md` to `/api/workspace/project-md`
- All `LOCALCHAT_*` env var fallbacks removed — `APEX_*` only
- Default personas are opt-in templates, not auto-seeded (controlled by `seed_default_profiles` in config.json)
- Browser tab shows "ApexChat (Dev)" when running on non-default port

### Removed
- Trader persona from default seeds (trading-specific, users can create their own)
- Trading alert categories from code defaults (configurable via `config.json`)
- Hardcoded Dana-specific paths, secrets, IPs, persona references
- `/opt/homebrew` paths — all use `sys.executable` / `shutil.which`
- Screenshots directory from git history (67MB purged via `git filter-repo`)
