# Changelog

All notable changes to Apex are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Fixed
- **B-25: Stop button stuck after agent thinks** — After an agent (e.g. Operations) finished thinking and responding, the Stop button stayed visually active and a follow-up triggered a false "agent is busy" red error. Root cause: the `result` event handler did not clear the stream's active/busy state — it was left to `stream_end`, which arrives after server-side post-processing (save, compact, agent routing). Fix: call `_finalizeStream` + `updateSendBtn` immediately on `result` so the UI reflects completion as soon as the response is shown. `stream_end` remains handled and is idempotent.

---

## [0.1.7] — 2026-03-29

Generic OSS-ready persona templates + profile editor.

### Added
- **Profile editor modal** — click the ⚙️ gear icon on any persona card in the channel picker to edit name, avatar, role description, model, and system prompt. Model dropdown includes all cloud providers (Claude, Grok, GPT) plus any local Ollama models detected on the machine. Changes apply immediately to future messages in channels using that profile.
- **Delete profile** — profiles can be deleted from the edit modal (with confirmation).

### Changed
- **Persona templates rewritten for OSS** — replaced 7 Apex-specific personas with 6 generic, product-agnostic templates suitable for any self-hosted user: Architect, Writer, Planner, Assistant, Developer, Designer. New IDs (`writer`, `planner`, `assistant`, `developer`) so existing installs keep their customized profiles untouched via `INSERT OR IGNORE`. Local `Assistant` persona defaults to `ollama/llama3.1:8b` for zero-cost quick tasks.

### Removed
- **Dana-specific personas** — Marketing (Apex CMO), Operations (Apex COO), Kodi (hardcoded qwen3.5:27b), Codex (codex:gpt-5.4), QA (Apex test engineer) removed from templates. Existing database entries are unaffected.

### Docs
- **GETTING_STARTED.md** — Step 6 rewritten for new generic personas + profile editor UI instructions.
- **PERSONAS.md** — Full rewrite: generic persona reference with API examples, model selection guide, and customization instructions.
- **docs/personas/** — Replaced 5 Dana-specific persona files (marketing, operations, kodi, codex, architect) with 6 generic ones (architect, writer, planner, developer, designer, assistant).
- **Remaining CLAUDE.md references** — Fixed in OSS_PLAN.md, README_OSS.md, FREE_TIER_OVERVIEW.md to say APEX.md. Dashboard API key renamed from `claude_md_exists` to `project_md_exists`.

---

## [0.1.6] — 2026-03-29

Agent personas auto-seed on new installs.

### Fixed
- **New users see empty profile picker** — `seed_default_profiles` now defaults to `true` in both the setup wizard config and the server. New installs get the 6 built-in agent personas (Architect, Marketing, Operations, Kodi, Codex, Designer) on first server start. Existing installs that upgrade also get them seeded on next restart. Uses `INSERT OR IGNORE` so existing customized profiles are never overwritten. Set `seed_default_profiles: false` in config.json to disable.

---

## [0.1.5] — 2026-03-29

Clickable installer for new users.

### Added
- **`Install Apex.command`** — double-click in Finder to launch setup. Opens Terminal with a branded banner, checks for Python 3.10+, creates venv, installs deps, and hands off to the interactive wizard
- **`install.sh`** — cross-platform bootstrap script (macOS + Linux). Detects platform, finds Python, handles venv creation errors with platform-specific guidance (e.g. `sudo apt install python3-venv` on Debian)
- Terminal window stays open on errors so users can read the message
- Passes through all flags (`--fast`, `--add-knowledge`, etc.)

---

## [0.1.4] — 2026-03-29

Fix server startup health check and first-run browser experience.

### Fixed
- **Server health check failed on mTLS** — `_wait_for_server()` now presents the client certificate during the TLS handshake; previously the bare HTTPS connection was rejected by `CERT_REQUIRED` before reaching `/health`, causing a false "did not respond within 30 seconds" warning
- **Browser opens before user knows about .p12** — connection info and certificate install instructions are now shown *before* the browser opens, with platform-specific steps (macOS, Linux, iOS, Android)

---

## [0.1.3] — 2026-03-29

Setup wizard hardening — secret scrubbing + model recommendations.

### Security
- **Expanded GitHub token scrubber** — now catches fine-grained PATs (`github_pat_`), App installation tokens (`ghs_`), user-to-server tokens (`ghu_`), and refresh tokens (`ghr_`) in addition to classic PATs

### Changed
- **Model recommendations show alternatives** — users now see smaller/faster models alongside the top-tier recommendation, so a 64GB Mac user can still pick gemma3:27b for speed

---

## [0.1.2] — 2026-03-29

Setup wizard audit — fixes for new user onboarding.

### Fixed
- **P0: `.p12` password lost after setup** — password now persisted to progress file so returning users can retrieve it from "Launch server" menu
- **P0: Ollama model pull dead on Apple Silicon** — `recommend_models()` now includes `ollama_name` on all platforms; pull prompt fires correctly on Macs
- **P0: Double colon in secret prompts** — removed trailing `: ` from API key prompts that collided with `prompt_secret()` formatting
- **P1: Duplicate "Step 7" in bootstrap** — config write step renumbered to Step 8
- **P1: Bare `print()` in install helpers** — `install_claude()`, `install_codex()`, and health summary table now use UI system (`print_success`/`print_error`/`print_warning`)
- **P1: No Python version guard** — setup.py now exits cleanly with a message on Python < 3.10
- **Import crash in `setup/models.py`** — added short aliases (`header`, `info`, `success`, `warn`, `ask_yes_no`, `ask_input`) to `setup/ui.py` for backward compatibility

---

## [0.1.1] — 2026-03-28

Security hardening pass (Codex audit V2) + iOS group UX.

### Security
- **HTTP middleware fails closed** — returns 401 when mTLS is configured but no peer cert is found (V2-01)
- **WebSocket fails closed** — closes with 1008 before accept() when no peer cert (V2-02)
- **DOM XSS cleanup** — all innerHTML user-data (avatar, name) escaped via `escHtml()` across 5 locations (V2-03)
- **Backups exclude private keys** — `.key`, `.p12`, `.pfx`, `.pem` files excluded from standard backups; restore warns about missing key material (V2-04)

### Added
- **iOS: Quote-reply routing** — quoting an agent message auto-routes to that agent with @mention
- **iOS: Active agent bar** — shows current responding agent with avatar during streaming
- **iOS: Always-on send button** — send available during concurrent agent responses
- **iOS: @mention picker** — tap @ to select agent from group roster
- **Codex security audit docs** — V1 + V2 audit reports tracked in repo

### Changed
- Startup banner now reads version from `VERSION` file (`Apex v0.1.1`)

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
