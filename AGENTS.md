# Agent Workflow Rules

These rules apply to all agents working in this repo. No exceptions.

---

## Rule 1 — Sync-First

Before touching any file or starting any task, verify your local branch matches origin.

```bash
git fetch origin
git status
```

If local `dev` does not match `origin/dev`, resolve the divergence before proceeding. Do not start work on a stale HEAD.

---

## Rule 2 — Atomic Push-Verify

Every commit must be immediately followed by a push and a confirmation that `origin/dev` shows the new hash. A commit is not done until it is on remote.

```bash
git commit -m "your message"
git push origin dev
git log origin/dev --oneline -1
```

Post the resulting hash in the group channel. That hash is the proof of completion.

---

## Rule 3 — Show the Hash

No commit is considered done based on a chat claim alone. The agent must post the verified `origin/dev` HEAD hash in the channel after every push.

Operations will spot-check. If the hash does not appear on `origin/dev`, the work is not done — regardless of what was reported.

---

## Summary

| Step | Command | Required |
|------|---------|----------|
| Before work | `git fetch origin && git status` | Always |
| After commit | `git push origin dev` | Always |
| Proof of done | Post `origin/dev` HEAD hash in channel | Always |

Skipping any of these three steps is the root cause of every branch divergence incident this sprint.

---

## Rule 4 — Group Channel Handoffs

When working in a group channel, the final message of any completed task **must @mention the next agent explicitly.**

- If handing off to a specific agent: `@Developer — your turn. [brief context]`
- If handing back to orchestrator: `@Operations — done. [one-line summary]`
- If you don't know who's next: `@Operations` and let them route it.

No silent completions. A task with no @mention handoff is a dropped baton — the next step won't start and the workflow stalls.

This rule exists because agents do not monitor the channel passively. They only act when addressed.

---

## Rule 5 — Edit Safety

Before editing any file, re-read it. Do not trust memory of file contents — compaction silently destroys prior reads in long sessions. In a session longer than ~10 exchanges, treat every file as unseen until re-read.

Files over 500 lines must be read in chunks (`offset` + `limit`). The read tool caps at 2000 lines and silently truncates. Key server files that require chunking: `apex.py`, `ws_handler.py`, `agent_sdk.py`, `routes_chat.py`, `db.py`.

Never report a task complete based solely on the edit tool confirming the write. The write succeeds even if the code is broken. After any change, verify before reporting done:

```bash
# Python server files
python3 -m py_compile server/<file>.py

# Swift iOS files (run from apexchat-ios repo)
xcodebuild -scheme ApexChat -sdk iphoneos26.4 -destination "generic/platform=iOS" build
```

---

## Rule 6 — Grep Is Not Semantic Search

Grep matches text, not meaning. When renaming a function, route, or config key, run separate passes for:
- Direct calls and imports
- String literals containing the name (route paths, log messages, config keys)
- Test files and fixtures

One pass is never enough. A missed string reference in a route or config key causes silent runtime failures that don't surface until a request hits the broken path.

---

## Rule 7 — Scope of Done

The default brevity bias ("simplest fix", "don't refactor beyond what was asked") applies to isolated changes. Override it when:
- The pattern being fixed is inconsistent with the rest of the file
- The architecture will cause the same bug to recur
- The change touches a security boundary (auth, token validation, rate limiting, path handling)

In these cases: fix the root cause, note what you changed and why, and say so in the commit message.

---

## Rule 8 — WIP Design Documents

All work-in-progress design documents, feature plans, and architecture proposals live in `docs/wip/`. This directory is gitignored — nothing in it ships to GitHub.

Before starting any project or feature work, check `docs/wip/` for an existing design doc. If one exists, read it and use it as your reference for scope, decisions, and open questions. Do not duplicate or contradict decisions made in a WIP doc without flagging the conflict.

When creating a new design doc, place it in `docs/wip/` with a descriptive name (e.g. `PERMISSION_LEVELS_PLAN.md`, `MCP_BRIDGE_DESIGN.md`). Reference it in your channel when handing off work.
