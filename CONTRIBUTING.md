# Contributing to Apex

Thanks for your interest in contributing to Apex. This document covers how to get involved.

## Code of Conduct

Be respectful, constructive, and professional. We're building something useful — keep discussions focused on that.

## How to Contribute

### Reporting Bugs

Open a GitHub issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your environment (OS, Python version, browser)

### Suggesting Features

Open a GitHub issue with the "feature" label. Describe the use case, not just the solution. We'll discuss before any implementation starts.

### Submitting Code

1. Fork the repo
2. Create a branch from `main` (`git checkout -b my-feature`)
3. Make your changes
4. Test locally — make sure the server starts and your change works
5. Commit with a clear message describing *why*, not just *what*
6. Open a PR against `main`

### PR Guidelines

- Keep PRs focused — one feature or fix per PR
- Include a description of what changed and why
- If it touches the UI, include a screenshot or screen recording
- Don't bundle unrelated cleanup with feature work

## Development Setup

```bash
git clone https://github.com/use-ash/apex.git
cd apex
pip install -r requirements.txt
python3 setup.py          # generates certs, configures API keys
bash server/launch.sh     # starts the server
```

The dev instance runs on port 8301:
```bash
bash server/launch_dev.sh
```

## Architecture

Apex is a single-file FastAPI server (`server/apex.py`) with supporting modules:

- `server/apex.py` — Core server: WebSocket streaming, model routing, skills, alerts
- `server/dashboard.py` — Admin dashboard API (61 endpoints)
- `server/dashboard_html.py` — Embedded SPA (no build step)
- `server/config.py` — Configuration manager
- `server/local_model/` — Ollama/local model tool loop
- `setup.py` + `setup/` — Interactive setup wizard

## What We're Looking For

- Bug fixes
- Documentation improvements
- New skills (slash commands)
- Dashboard UI improvements
- Cross-platform compatibility (Linux support, non-Homebrew paths)
- Security hardening

## What Needs Discussion First

- New model backend integrations
- Changes to the database schema
- Changes to the mTLS auth flow
- Anything that affects the iOS app contract

## License

By contributing, you agree that your contributions will be licensed under the Elastic License 2.0 (ELv2).
