---
name: Apex Multi-Agent Channels Design
description: Premium design for group-style channels with multiple agents in one conversation
type: design
---

# Apex Multi-Agent Channels

## Summary

Add a premium Apex feature that lets one channel contain multiple agents, similar to a group chat, while avoiding the chaos of every agent replying to every message.

The core idea is:

- A channel can have multiple agent participants.
- One agent is the default speaker.
- Other agents speak only when mentioned, delegated to, or triggered by explicit rules.
- The UI makes agent identity obvious.
- The server enforces turn-taking conventions so the room stays readable.

This is **not** an OSS baseline feature. It should ship as an Apex premium capability.

---

## Why This Is Worth Building

The current Apex model is "one chat, one active agent/model." That is simple, but it forces the user to switch channels whenever they want a different kind of help.

Multi-agent channels unlock:

- `Claude + Codex` in one product/dev room
- `Claude + Grok + Codex` for synthesis + research + implementation
- specialist agent rooms like `Coordinator + Reviewer + Researcher`
- group-style workflows where one agent plans, another executes, another critiques

This can feel significantly more powerful than separate chats, but only if conventions are strict.

Without routing rules it becomes unusable.

---

## Product Positioning

### Tier placement

This should be a **premium-only** feature:

- **OSS / free server:** single-agent channels only
- **Apex Pro / premium:** multi-agent channels
- **Enterprise:** multi-agent channels plus org-level policy, templates, analytics, audit controls

### Why premium

Multi-agent channels are:

- a real differentiator versus generic self-hosted chat wrappers
- more expensive in compute, routing complexity, and UI complexity
- much easier to support if the install base is smaller and more intentional

This also keeps the OSS product clean and understandable.

---

## Design Principles

### 1. One room, not a free-for-all

A channel can contain many agents, but not all of them should answer by default.

### 2. Default to silence

Non-primary agents should be silent unless:

- explicitly mentioned
- delegated to by the primary agent
- activated by a channel rule

### 3. Identity must be obvious

Every assistant message in a multi-agent room must clearly show:

- agent name
- icon/avatar
- model/backend
- role label

### 4. The user should not manage orchestration manually every turn

Good multi-agent UX means:

- mentions when desired
- auto-routing when useful
- one coherent conversation, not constant channel switching

### 5. Delegation should compress noise

When possible, the primary agent should be able to delegate internally and then return a summarized answer, instead of forcing the user to read all internal chatter.

---

## Non-Goals

For the first version, do **not** build:

- simultaneous autonomous replies from multiple agents to the same user turn
- "agents arguing in public" as the default behavior
- enterprise multi-user collaboration
- arbitrary user-created model graphs
- fully autonomous agent societies

This feature should feel like a carefully managed group chat, not an experiment.

---

## User Experience

## Channel Types

Add a new channel mode:

- `single_agent`
- `multi_agent`
- existing `alerts`

For multi-agent channels, the channel header should show:

- channel name
- participant chips
- primary agent
- quick mention shortcuts

## Example channels

- `Apex Build Room`
  - Primary: Claude
  - Members: Codex, Grok
- `Trading Desk`
  - Primary: Claude
  - Members: Alerts, Research, Execution
- `Product Staff`
  - Primary: Coordinator
  - Members: Codex, Reviewer, Research

## Composer behavior

The composer should support:

- plain message to room
- `@agent` mention autocomplete
- optional "send to primary only" vs "allow routing" mode

Example:

- `@Codex fix the layout bug in SettingsView`
- `@Grok research the latest TestFlight APNs guidance`
- `compare both approaches and recommend one`

## Message rendering

Every assistant bubble in a multi-agent channel should show:

- avatar/icon
- display name, for example `Codex`
- subtitle, for example `GPT-5.4 • Builder`

Suggested order:

1. agent header
2. message body
3. optional tool/thinking disclosure

## Room conventions

Use explicit roles:

- **Primary**: default responder and coordinator
- **Specialist**: only responds when mentioned or triggered
- **Silent watcher**: receives context, never replies directly
- **Delegate-only**: can be invoked by primary agent but not directly by the user unless enabled

---

## Routing Model

This is the heart of the feature.

## MVP routing modes

Each agent membership in a channel gets one of these modes:

### `primary`

- default responder
- receives all turns
- allowed to respond directly

### `mentioned`

- only responds when explicitly tagged, like `@Codex`

### `rule_based`

- responds only when channel rules match
- example: code blocks -> Codex
- example: "research", "latest", URLs -> Grok

### `delegate_only`

- user cannot directly trigger unless allowed by settings
- primary agent can invoke it

### `silent_context`

- never responds directly
- gets channel context for future routed tasks

## Turn routing algorithm

For each user message:

1. Parse mentions.
2. If explicit mentions exist, route to only those agents.
3. If no mentions exist, choose the primary agent.
4. If rule-based agents match and channel policy allows fan-out, either:
   - let primary respond and internally delegate, or
   - surface a lightweight "also asking X" indicator.
5. Enforce response budget so only one visible answer appears unless the user explicitly requested multiple voices.

## Recommended default

For the first release:

- exactly one visible responder per turn by default
- multi-agent support mainly exists for mentions and delegation

This keeps channels readable.

---

## Server Architecture

## New concepts

Add these server-side abstractions:

- `agent_profile`
- `channel_membership`
- `routing_policy`
- `agent_invocation`
- `group_turn`

## Suggested data model

### `agent_profiles`

Represents a reusable agent persona/config.

Fields:

- `id`
- `name`
- `slug`
- `avatar`
- `role_description`
- `backend`
- `model`
- `system_prompt`
- `tool_policy`
- `visibility`
- `created_at`
- `updated_at`

### `channel_agent_memberships`

Join table between channel and agent profile.

Fields:

- `channel_id`
- `agent_profile_id`
- `routing_mode`
- `display_order`
- `is_primary`
- `can_user_mention`
- `can_agent_reply_publicly`
- `auto_trigger_rules_json`

### `messages`

Extend existing messages with:

- `speaker_type` = `user | assistant | system`
- `speaker_id`
- `speaker_name`
- `speaker_role`
- `group_turn_id`
- `invoked_by_message_id`
- `visibility` = `public | internal`

### `agent_invocations`

Useful for audit/debugging.

Fields:

- `id`
- `channel_id`
- `group_turn_id`
- `agent_profile_id`
- `trigger_type` = `mention | primary | rule | delegate`
- `status`
- `started_at`
- `completed_at`
- `error`

## Execution strategies

### Strategy A: public single-speaker with hidden delegation

Best MVP.

Flow:

1. user message enters room
2. primary agent receives it
3. primary may delegate to other agents internally
4. only the final synthesized response is public unless explicit mentions requested separate answers

Pros:

- low noise
- easy to understand
- feels polished

### Strategy B: public multi-speaker

Use only when user explicitly wants it.

Flow:

1. `@Claude` and `@Codex` both respond
2. both messages appear in the room

Pros:

- transparent
- good for compare/contrast

Cons:

- noisy
- more token cost
- easier to derail

Recommendation:

- build architecture for both
- ship Strategy A as the default

---

## UX Rules To Prevent Chaos

## Public reply budget

Per user turn:

- default max public assistant replies: `1`
- if explicit mentions > 1: allow up to mentioned count
- otherwise internal delegate results should stay hidden or summarized

## Mention rules

- `@Codex` means Codex is the public responder
- `@Claude @Codex` means both may reply
- no mention means primary only

## Inter-agent rules

Agents should never freely talk to each other in the public thread.

Allowed:

- primary delegates internally
- primary summarizes
- user explicitly asks for multiple opinions

Disallowed by default:

- spontaneous critique from non-mentioned agents
- open-ended agent debates

## Agent style conventions

Each agent profile should have:

- a short role description
- a speaking style
- a "when to stay quiet" rule

Example:

- `Codex`
  - role: implementation specialist
  - speak when: tagged for code, patching, debugging, repo analysis
  - stay quiet when: general planning unless asked

- `Grok`
  - role: web research specialist
  - speak when: tagged for current events, external docs, market/news context
  - stay quiet when: code implementation asks

- `Claude`
  - role: coordinator and synthesis lead
  - speak when: default
  - stay quiet when: another explicitly tagged specialist is meant to answer alone

---

## iOS and Web UI

## Channel creation

In channel creation/edit UI:

- channel type picker: `Single Agent` or `Multi-Agent`
- member selector
- choose primary agent
- assign routing modes
- optional rule templates

## Channel list

Multi-agent channels should show:

- stacked participant avatars or initials
- subtitle like `Claude + 2`

## Message list

Multi-agent message bubbles should include:

- colored identity chip
- agent name
- backend/model subtitle

## Mention UX

In composer:

- typing `@` opens member suggestions
- recently used agents appear first
- invalid mentions not allowed

## Settings / admin

Need an agent management UI:

- create/edit agent profile
- assign model/backend
- set prompt template
- set default role
- set whether it is premium-only or internal-only

---

## Premium Gating

## Feature gate

Add a server capability flag:

- `multi_agent_channels_enabled`

For premium builds/users:

- channel type selector shows `Multi-Agent`
- agent membership editor visible

For OSS:

- hide multi-agent channel creation
- existing codepaths remain single-agent only

## Upsell surfaces

Natural upsell points:

- when user tries to add a second agent to a channel
- when user taps "Create Multi-Agent Room"
- when user types `@Codex` in a non-premium environment

Messaging:

- "Multi-agent rooms are available in Apex Pro."

---

## Implementation Plan

## Phase 1: Design-safe foundation

- add `agent_profiles`
- add `channel_agent_memberships`
- extend message metadata with speaker identity
- add premium gating

No public multi-agent UI yet.

## Phase 2: Mention-based public multi-agent

- allow `@agent` mentions in one channel
- render multi-agent identity in bubbles
- exactly one or explicitly mentioned public speakers

This is the first user-facing release.

## Phase 3: Primary-agent delegation

- internal delegate flow
- primary summarizes delegate results
- add lightweight "consulted Codex" indicators

This is likely the most compelling long-term mode.

## Phase 4: Rule-based automation

- channel-level rules
- examples:
  - URLs -> research agent
  - code fence -> Codex
  - alert payload -> analyst

Only after routing behavior is already stable.

---

## Risks

## 1. Noise explosion

Mitigation:

- one visible responder by default
- explicit mentions only
- strong silent defaults

## 2. Token/cost blow-up

Mitigation:

- internal delegation summaries
- per-turn invocation budget
- allow agents to receive compressed context, not full transcript every time

## 3. User confusion

Mitigation:

- clear roles
- obvious identity badges
- predictable routing

## 4. Prompt leakage / policy conflicts

Mitigation:

- per-agent prompt isolation
- standardized room protocol
- no unrestricted public inter-agent chatter

---

## Recommended MVP

The strongest MVP is:

- premium-only multi-agent channels
- one primary agent per room
- explicit `@mention` support
- public reply budget of one by default
- internal delegation architecture prepared but not fully exposed yet

That gives Apex the "group chat with specialists" feeling without making the product noisy or fragile.

---

## Example Scenarios

## Example 1: Build room

Channel members:

- Claude = primary
- Codex = mentioned
- Grok = mentioned

User says:

- `@Codex fix the scrolling bug in SettingsView`

Result:

- only Codex responds publicly

User says:

- `What changed and is there any risk?`

Result:

- Claude responds publicly, possibly summarizing prior Codex work

## Example 2: Compare opinions

User says:

- `@Claude @Grok give me your takes on this launch strategy`

Result:

- both respond publicly, in order

## Example 3: Delegated synthesis

User says:

- `Investigate why this feature feels slow`

Result:

- Claude receives turn as primary
- Claude internally delegates code tracing to Codex
- Claude returns a single public summary with diagnosis and next steps

---

## Open Questions

- Should internal delegation traces be optionally visible to power users?
- Should multi-agent channels support per-room shared memory, or only reuse existing transcript context?
- Should agent profiles be global or workspace-scoped?
- Do we allow user-created custom agents in premium, or only curated built-ins first?
- Should iOS ship multi-agent UI at first release, or should web get it first?

---

## Recommendation

Build this.

But build it as a **disciplined premium orchestration feature**, not as unrestricted group chat.

If Apex ships multi-agent rooms with:

- a primary speaker
- mentions
- routing modes
- visible identities
- delegation-first conventions

then it becomes one of the most interesting parts of the product.

If it ships as "multiple bots can all talk whenever they want," it will feel chaotic and gimmicky.

The winning version is closer to:

- "a room with specialists and a coordinator"

than:

- "a chatroom full of bots."
