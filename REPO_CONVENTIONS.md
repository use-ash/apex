# Apex Repo Conventions

## Three-Repo Layout

```
drm-collab/apex   (origin)    — private development home. All work lands here first.
use-ash/apex      (upstream)  — public OSS release. Only receives deliberate pushes from origin/main after prod validation.
use-ash/apex-private          — private ops overlay (scripts, launchers, patches). Never merges into either apex repo.
```

Local paths:
```
~/.openclaw/apex/       — working clone (origin = drm-collab, upstream = use-ash)
~/.apex-prod/           — git worktree of the above, checked out at main, runs prod on port 8300
~/.openclaw/apex-private/ — private ops repo, never touched by OSS agents
```

---

## Development Flow

```
feature work on dev
       ↓
git push origin dev          (drm-collab/apex — private)
       ↓
merge dev → main locally
       ↓
git push origin main         (drm-collab/apex — private)
       ↓
Dana restarts prod from ~/.apex-prod/ and validates
       ↓
git push upstream main       (use-ash/apex — public OSS) ← ONLY after prod confirmation
```

**Nothing touches `upstream` (use-ash/apex) until Dana has confirmed it in prod.**

---

## Remote Commands

| Intent | Command |
|--------|---------|
| Push feature work | `git push origin dev` |
| Promote to private main | `git push origin main` |
| Release to public OSS | `git push upstream main` ← Dana only |
| Pull latest OSS changes | `git fetch upstream && git merge upstream/main` |

---

## What Goes Where

| Code type | Destination |
|-----------|-------------|
| Server features, bug fixes, OSS-safe config | `drm-collab/apex` dev → main → upstream when ready |
| Restart scripts, cert shortcuts, personal paths | `apex-private/scripts/` only |
| Dev/prod launchers | `apex-private/launchers/` only |
| Playwright Docker, bearer bypasses | `apex-private/patches/` only |

**Red flags that mean private, not OSS:**
- Any hardcoded path under `/Users/`, `/private/tmp/`, or home directories
- Bypass mechanisms (`CERT_OPTIONAL`, `?_token=`, bearer shortcuts)
- Machine-specific env vars or port assumptions
- Scripts named `launch_dana.sh`, `restart_apex_*.sh`, `.enable_codex_access.sh`

---

## Branch Rules

- `main` — production-confirmed code. Merges to upstream when Dana approves.
- `dev` — all feature work. Never commit directly to main.
- Worktree `~/.apex-prod/` runs `main`. Do not develop in the worktree.

---

## Agents: What You Can and Cannot Do

| Action | Allowed |
|--------|---------|
| `git push origin dev` | Yes |
| `git push origin main` | Yes, after merge from dev |
| `git push upstream main` | No — Dana only |
| `git push upstream *` | No — Dana only |
| Edit files in `~/.openclaw/apex/` | Yes |
| Edit files in `~/.apex-prod/` | Yes (same repo, worktree) |
| Edit files in `~/.openclaw/apex-private/` | Yes |
| Commit private-ops code to apex | Never |
