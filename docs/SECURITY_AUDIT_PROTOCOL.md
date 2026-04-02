# Apex Security Audit Protocol

_Last updated: 2026-03-28_

Purpose: run full-project security audits without touching production, corrupting SQLite, or creating unsafe concurrency.

---

## Non-Negotiable Rules

1. **Never use production for security audits**
   - Never target `main`
   - Never target port `8300`
   - Never read, write, migrate, vacuum, restore, or fuzz `state/apex.db`
   - Never restart production

2. **Apex development and testing must happen on `dev`**
   - Branch: `dev`
   - Server: port `8301`
   - DB: `state/apex_dev.db`

3. **No direct live-DB testing**
   - Before any DB-touching test, create a timestamped backup/copy first
   - Prefer testing against a disposable DB copy in `/tmp/`
   - Never run destructive audit actions against the live dev DB unless explicitly required and backed up

4. **No parallel audit agents**
   - No multi-agent fanout
   - No concurrent sub-agents
   - No scanners or scripts that open many concurrent DB writers/readers
   - Run audit steps serially

5. **Read-only first**
   - Static audit before dynamic audit
   - Config/infra review before runtime probing
   - Dynamic testing only after preflight checks pass

6. **No destructive admin endpoints during audits unless explicitly needed**
   - Avoid live use of:
     - `/admin/api/db/vacuum`
     - `/admin/api/db/export`
     - `/admin/api/db/messages`
     - `/admin/api/backup/restore`
     - backup/restore flows against active DBs

---

## Required Preflight Checklist

Before starting any security audit, verify all of the following:

- [ ] Current repo branch is `dev`
- [ ] Target server is dev only (`:8301`)
- [ ] No production paths, ports, or DB files are referenced
- [ ] No sub-agents or parallel workers will be launched
- [ ] Dev DB backup exists
- [ ] If dynamic DB testing is needed, a disposable `/tmp/` DB copy exists
- [ ] Audit starts with static review, not runtime mutation

---

## Safe Audit Workflow

### Phase 0 — Safety Setup
- Confirm branch = `dev`
- Confirm target port = `8301`
- Identify DB path(s)
- Create backup of `state/apex_dev.db`
- Create disposable working copy in `/tmp/` if DB interaction is needed
- Confirm zero concurrent audit workers

### Phase 1 — Static Code Audit
Review only; no runtime mutation.

Focus areas:
- auth / authorization
- mTLS enforcement
- websocket auth/origin checks
- secret handling
- hardcoded credentials
- file uploads / attachments / transcription
- path traversal
- SSRF / unsafe fetches
- subprocess usage
- shell injection
- SQL injection / dynamic SQL
- XSS / unsafe `innerHTML`
- CSRF / CORS / security headers
- backup / restore safety
- admin endpoints with destructive power
- iOS certificate and token handling
- logging of secrets / PII
- dependency and operational security risks

### Phase 2 — Config / Infra Review
Mostly read-only.

Inspect:
- launch scripts
- env loading
- dev vs prod separation
- dashboard/admin controls
- backup scripts
- SQLite access patterns
- cron / maintenance / alerting
- any scripts that can accidentally point at prod

### Phase 3 — Controlled Dynamic Testing
Only after Phases 0–2.

Rules:
- dev only
- serial execution only
- low request rate
- one test stream at a time
- avoid destructive routes against live DB
- prefer disposable DB copies when mutation is required

Test classes:
- auth bypass
- IDOR / cross-chat access
- invalid input handling
- upload validation
- profile/chat/admin permission boundaries
- websocket rejection cases
- rate-limit presence / abuse resistance

### Phase 4 — Reporting
Every audit report should include:
- severity
- exploitability
- exact file path + line number
- safe reproduction notes
- remediation recommendation
- whether fix is safe now or needs approval

---

## SQLite Safety Rules

SQLite is sensitive to concurrency and destructive maintenance operations.

During audits:
- Do not run many parallel requests against one live SQLite DB
- Do not run `VACUUM`, restore, or destructive cleanup against the active DB during broad audits
- Do not point automated scanners at the live DB admin endpoints
- Prefer copied DB files in `/tmp/` for inspection or mutation tests
- If tests require import-time DB initialization, force test env vars before importing server modules

---

## Apex-Specific Guardrails

- `main` = production, frozen for development
- `dev` = all Apex feature work and all audit work
- `server/launch_dev.sh` uses `APEX_DB_NAME=apex_dev.db`
- Tests must override env vars before importing `server/apex.py`
- Never let inherited shell env point tests at production state

---

## Explicitly Forbidden Audit Behavior

- Running 8 sub-agents at once
- Touching `state/apex.db`
- Running audits on port `8300`
- Restarting production
- Fuzzing live production or live dev DB-admin endpoints aggressively
- Restoring a backup over an active DB during an audit
- Assuming dev/prod separation without checking env vars first

---

## Minimal Audit Kickoff Template

Use this at the start of every Apex security audit:

1. Verify branch is `dev`
2. Verify target is `:8301`
3. Verify DB is `state/apex_dev.db`
4. Create backup of dev DB
5. Create disposable `/tmp/` DB copy if needed
6. Confirm zero parallel agents
7. Run static audit
8. Run config/infra review
9. Present findings before destructive or mutation-heavy runtime checks

---

## Definition of Safe-to-Start

An Apex security audit is safe to start only if:
- branch is `dev`
- production is untouched
- there is a backup/copy plan for DB interaction
- no parallel sub-agents are used
- the audit begins read-only
