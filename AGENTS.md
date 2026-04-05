# Agent Workflow Rules

These rules apply to all agents working in this repo. No exceptions.

**Read `REPO_CONVENTIONS.md` first** — it defines the three-repo layout (drm-collab origin, use-ash upstream, apex-private), the development flow, and what goes where. Everything below assumes you understand that layout.

---

## Rule 0 — Repo Routing

Before any git operation, confirm which remote you are targeting:

- `origin` = `drm-collab/apex` (private). Push dev work and merged main here freely.
- `upstream` = `use-ash/apex` (public OSS). **Never push here.** Dana pushes upstream only after prod validation.

```bash
git remote -v   # confirm before any push
```

If you are about to run `git push upstream`, stop and route it through Dana.

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

**Security audit findings, vulnerability reports, and pen test results must always go in `docs/wip/`, never in tracked files.** Publishing security findings to the public repo exposes attack surface details to adversaries. This applies to any document that describes a vulnerability, a fix for a vulnerability, or the security posture of the system. No exceptions.

---

## Rule 9 — Design Before You Build

Before implementing anything that touches more than 2 files, stop and answer these questions:

1. **Can this use existing infrastructure?** Don't create a new module, backend type, or abstraction when an existing one can be extended with a few lines. Adding a field to an existing JSON config is almost always better than a new config system.
2. **Am I adding a new code path?** Every new code path (new backend, new dispatch branch, new tool type) is permanent maintenance. Extend an existing path unless there's a clear reason it can't work.
3. **If I removed half the plan, would it still solve the problem?** If yes, remove that half. Ship the minimum that works. The rest can be added later if actually needed.
4. **Where do the checks live?** Resolve state once, thread it through. Don't create a central module that gets called from 5 different files — that's 5 places to forget to call it.

If the design requires a new file, justify it in the design doc. "It felt cleaner" is not a justification. "The existing file is 2000 lines and this is an independent concern" is.

Post your design in the group channel for review before starting implementation. Another agent's job is to find what can be removed, not what should be added.

---

## Rule 10 — Prefer Simple Commands

Tool permissions in Apex are intentionally conservative. Agents should prefer the simplest command or tool call that accomplishes the task.

Default habits:
- Prefer dedicated tools over Bash when possible:
  - `Read`, `Grep`, `Glob`, `Edit`, `Write`, `playwright`, `fetch`
- Prefer one direct command over chained shell logic
- Prefer multiple small commands over one dense one-liner
- Prefer explicit paths and explicit flags over shell tricks

Avoid unless absolutely necessary:
- command substitution like `$(...)`
- heredocs for commit messages or inline file generation
- long fallback chains with mixed redirects
- probing protected paths such as `state/ssl`, live DB files, or secrets to “see if access works”

Recommended patterns:

```bash
# Good
git add server/apex.py
git commit -m "Fix dev mTLS handling"

# Bad
git add ... && git commit -m "$(cat <<'EOF'
long generated message
EOF
)"
```

```bash
# Good
ls /Users/dana/.openclaw/apex/docs/wip

# Bad
ls ~/.openclaw/apex/docs/wip 2>/dev/null || ls ~/.openclaw/apex/docs
```

```text
# Good
Use Read on the file directly.

# Bad
Use Bash with cat, pipes, redirects, and grep if a direct Read/Grep tool exists.
```

If a command fails on permissions:
1. simplify it
2. remove shell syntax
3. switch to a direct tool
4. only then escalate or ask for broader access

Less clever is better. Apex agents should optimize for reliability under policy, not shell virtuosity.
