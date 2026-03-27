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

**Why:** Dana identified this as both an OSS opportunity and a reference implementation for the ASH proxy architecture.

**How to apply:** When the time comes, extract into a clean repo. Don't rush — get the SDK image upload bug fixed first and test the hooks integration end-to-end.
