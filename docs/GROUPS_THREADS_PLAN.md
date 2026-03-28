# Apex Groups, Threads & Designer Persona — Implementation Plan

**Status:** Approved direction, ready for Architect review and phased execution
**Date:** 2026-03-27
**Author:** Dana + Claude (planning session)

## Context

Evolve Apex from flat 1:1 chats into a hierarchy: **Channels** (1:1, exists today), **Groups** (multi-agent with orchestrator + contributors), and **Threads** (lightweight one-offs). Also adding a **Designer** persona focused on UX/customer experience.

The existing `MULTI_AGENT_CHANNELS_DESIGN.md` covers multi-agent routing in detail — this plan adapts those ideas into buildable phases.

### Dana's Vision

- **Channels** — individual 1:1 conversations with a persona or model (what exists today, renamed from "chats")
- **Groups** — collections of agents working toward a shared goal. Has an orchestrator persona + individual contributor personas. Goal may be abstract, requiring planning. Agents interact with each other through the group.
- **Threads** — lightweight one-off interactions. Go in, respond, done. No ongoing task management.
- **Designer persona** — the missing voice advocating for the end user. UX, beauty, human perspective. Evaluates from the customer's point of view.

### Current Architecture (as of 2026-03-27)

**Database tables:** `chats` (id, title, model, type, category, profile_id), `messages` (id, chat_id, role, content, tool_events, thinking, cost), `agent_profiles` (id, name, slug, avatar, role_description, backend, model, system_prompt, tool_policy, is_default), `alerts`

**API:** `/api/chats` (CRUD), `/api/profiles` (CRUD + detail), `/ws` (WebSocket with actions: ping, attach, send, stop, set_model, set_chat_model)

**Existing personas (6):** Architect, Codex, Marketing, Operations, Trader, Kodi

**Existing skill dispatch:** `/recall` (context injection), `/codex` (background process), `/grok` (background process) — proves hidden delegation pattern works

**Naming inconsistency:** iOS says "Channels" everywhere, webapp says "Chats", API/DB uses `chats`

---

## Phase 0: Naming Unification (30 min, Codex-eligible)

Webapp says "Chats" — change to "Channels" to match iOS.

**Server (`apex.py`):**
- Sidebar header: `<h2>Chats</h2>` → `<h2>Channels</h2>` (~line 4422)
- New button: `+ New Chat` → `+ New Channel` (~line 4425)
- Default title: `"New Chat"` → `"New Channel"` in `api_new_chat` (~line 2224)

**iOS (`AppState.swift`):**
- Fallback title `"New Chat"` → `"New Channel"` (~line 439)

**NOT changing:** API paths (`/api/chats`), DB table name (`chats`), internal JS function names, WebSocket event types. Too risky for a cosmetic rename — defer to a major version bump if ever.

---

## Phase 1: Designer Persona (15 min, Codex-eligible)

Add 7th built-in profile to `_seed_default_profiles()` in `apex.py`:

| Field | Value |
|-------|-------|
| id | `designer` |
| name | Designer |
| slug | `designer` |
| avatar | 🎨 |
| role_description | Head of Design — UX, beauty, customer experience |
| backend | claude |
| model | claude-opus-4-6 |

**System prompt core principles:**
- Takes the human perspective — as if a real user is behind a phone or keyboard
- Beauty is not decoration. It communicates quality and trust.
- Every tap, swipe, and transition should feel intentional.
- If a feature needs explanation, the design failed.
- Accessibility is not optional. Mobile-first.
- When reviewing any feature: What does the user see first? What do they expect? What actually happens? How does it feel? What would make it delightful?

**Scope:** UX flows, visual design, interaction design, design system, customer journey, onboarding, accessibility, design critique.
**NOT scope:** Code implementation (→ Codex/Architect), marketing copy (→ Marketing), budgets (→ Operations), trading (→ Trader).

`INSERT OR IGNORE` means existing installs get it on next restart automatically. No migration needed.

---

## Phase 2: Threads (2-3 hrs, split Codex/Claude)

Lightweight one-off interactions. Threads are channels with `type = 'thread'` — **no new tables needed**.

### Server (`apex.py`)
- Accept `type: "thread"` in POST /api/chats
- Default title: `"Quick thread"`
- Add `DELETE /api/threads/stale?older_than_days=7` cleanup endpoint
- Auto-title from first user message (first 50 chars)

### Webapp (`apex.py` HTML/JS)
- Partition sidebar into sections: **Channels**, **Threads** (last 10, collapsible), **Alerts**
- Add "Quick Thread" button in new-channel overlay (top, before profiles)
- Thread items get lighter styling + bolt/thread icon instead of bubble

### iOS
- `ChannelListView.swift`: Filter `appState.chats` into sections by type
- `NewChannelView.swift`: Add "Quick Thread" button at top
- `AppState.swift`: Add `createThread()` method

### Key decision
Threads share 100% of existing infrastructure. Same messages table, same WebSocket, same streaming. The only difference is UX treatment (separate section, auto-prune, lighter styling).

---

## Phase 3: Groups Foundation (4-6 hrs, split Codex/Claude)

Data model for multi-agent groups. **No orchestration logic yet** — just the container and membership model.

### DB migrations (`apex.py`)

```sql
CREATE TABLE IF NOT EXISTS channel_agent_memberships (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    agent_profile_id TEXT NOT NULL REFERENCES agent_profiles(id),
    routing_mode TEXT NOT NULL DEFAULT 'mentioned',
    is_primary INTEGER NOT NULL DEFAULT 0,
    display_order INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(channel_id, agent_profile_id)
);
```

Extend messages table:
```sql
ALTER TABLE messages ADD COLUMN speaker_id TEXT DEFAULT '';
ALTER TABLE messages ADD COLUMN speaker_name TEXT DEFAULT '';
ALTER TABLE messages ADD COLUMN speaker_avatar TEXT DEFAULT '';
ALTER TABLE messages ADD COLUMN visibility TEXT DEFAULT 'public';
ALTER TABLE messages ADD COLUMN group_turn_id TEXT DEFAULT '';
```

### Server API
- POST /api/chats with `type: "group"` + `members` array:
  ```json
  {
    "type": "group",
    "title": "Build Room",
    "members": [
      {"profile_id": "architect", "routing_mode": "primary"},
      {"profile_id": "codex", "routing_mode": "mentioned"},
      {"profile_id": "designer", "routing_mode": "mentioned"}
    ]
  }
  ```
- GET/POST/DELETE/PATCH `/api/chats/{id}/members` — member CRUD
- `_get_chats()` returns `member_count`, `primary_profile_name` for groups
- **Premium gate:** `APEX_GROUPS_ENABLED` env var (default `"false"`)

### iOS
- `Chat.swift`: Add `memberCount`, `primaryProfileName`, `primaryProfileAvatar`
- `Message.swift`: Add `speakerId`, `speakerName`, `speakerAvatar`
- `MessageBubble.swift`: Speaker identity header when `speakerName` is set
- New `NewGroupView.swift`: Member picker, primary agent selection, group title

### Webapp
- Group icon + member count in sidebar
- Speaker identity header above assistant bubbles
- "New Group" button in new-channel overlay (premium-gated)

---

## Phase 4: Group Orchestration

### Phase 4a: @Mention Routing (3-4 hrs)

When user sends `@Codex fix the scrolling bug` in a group channel:

1. Server parses `@Name` from message text against group members
2. Routes to mentioned agent's model/backend/system_prompt
3. Response includes `speaker_id`/`speaker_name`/`speaker_avatar`
4. No mentions = route to primary agent

**Composer UX:** Typing `@` triggers member autocomplete dropdown (both webapp and iOS).

**Routing modes** (from MULTI_AGENT_CHANNELS_DESIGN.md):
- `primary` — default responder, receives all turns
- `mentioned` — only responds when `@`-tagged
- `rule_based` — responds when channel rules match (Phase 4c, future)
- `delegate_only` — only primary can invoke
- `silent_context` — reads but never replies

### Phase 4b: Hidden Delegation (6-8 hrs, Claude only)

The primary agent can internally invoke other agents and synthesize responses.

- Primary agent gets a `delegate(agent, task)` tool in group channels
- Server intercepts the tool call, routes to delegate's model with their system prompt + task
- Delegate response returned as tool result for primary to synthesize
- Delegate's raw response stored as `visibility='internal'`
- Internal messages hidden by default, `?include_internal=true` to reveal

**Implementation:** Uses existing skill dispatch pattern (proven with `/codex`, `/grok`). The delegation flow:
1. Primary calls `delegate(agent="codex", task="...")`
2. Server intercepts tool call
3. Spawns API call to delegate's model with delegate's system prompt
4. Returns result as tool result in primary's stream
5. Primary synthesizes and responds publicly

---

## Sequencing

| Phase | Effort | Codex? | Dependencies |
|-------|--------|--------|-------------|
| 0: Naming | 30 min | Yes | None |
| 1: Designer | 15 min | Yes | None |
| 2: Threads | 2-3 hrs | Partial | Phase 0 |
| 3: Groups | 4-6 hrs | Partial | Phase 1 |
| 4a: Mentions | 3-4 hrs | Partial | Phase 3 |
| 4b: Delegation | 6-8 hrs | No | Phase 4a |

**Phases 0+1 can ship together immediately.** Phase 2 is independent. Phase 3+ is premium-only.

---

## Verification

- Phase 0: Webapp sidebar shows "Channels", new channel default title is "New Channel"
- Phase 1: `GET /api/profiles` returns 7 profiles including Designer
- Phase 2: Create thread via API, verify it appears in Threads section, verify stale cleanup
- Phase 3: Create group with 3 members, verify member list, verify speaker headers in messages
- Phase 4a: Send `@Codex do X` in group, verify Codex responds (not primary)
- Phase 4b: Send plain message in group, verify primary delegates and synthesizes

## Critical Files

- `server/apex.py` — every phase (DB schema, API, HTML/JS, profile seeds)
- `ios/ApexChat/ApexChat/Models/Chat.swift` — Phase 2, 3
- `ios/ApexChat/ApexChat/Models/Message.swift` — Phase 3
- `ios/ApexChat/ApexChat/Views/ChannelListView.swift` — Phase 2, 3
- `ios/ApexChat/ApexChat/Views/MessageBubble.swift` — Phase 3
- `ios/ApexChat/ApexChat/Views/NewChannelView.swift` — Phase 2, 3
- `ios/ApexChat/ApexChat/ViewModels/AppState.swift` — Phase 0, 2, 3
- `docs/MULTI_AGENT_CHANNELS_DESIGN.md` — reference (already exists, detailed routing design)

## Related Documents

- `docs/MULTI_AGENT_CHANNELS_DESIGN.md` — comprehensive routing, premium gating, UX rules
- `docs/CHANNEL_SETTINGS_SPEC.md` — per-channel settings dropdown (implemented)
- `docs/personas/*.md` — individual persona system prompts
