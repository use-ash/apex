# Apex — Agent Contribution Rules

## OSS vs Private

This is the public OSS repo. Before committing, ask: would this commit
be safe and useful for every Apex user, on any machine, with no prior
context about Dana's setup?

If no → it belongs in `apex-private`, not here.

Red flags that mean "private":
- Hardcoded paths under `/Users/`, `/private/tmp/`, or any home directory
- Bypass mechanisms (`CERT_OPTIONAL`, token-based auth shortcuts, `?_token=`)
- Playwright-specific env vars or Docker cert mounts
- Personal deployment assumptions (specific hostnames, port numbers)
- Scripts named `launch_dana.sh`, `restart_apex_*.sh`, `.enable_codex_access.sh`

These never land on public `main`.

## Development Branch Rule

All server feature work happens on `dev`, not `main`. `main` is production.

```
main  = production (port 8300)   ← merge target only
dev   = feature work (port 8301) ← develop here
```

Workflow: `dev` → test on :8301 → merge to `main` → operator restarts prod.

## Upstreaming Private Patches

If a private patch in `apex-private/patches/` turns out to be generally
useful, generalize it and upstream as a proper OSS feature. Never ship
private shortcuts as OSS defaults.
