# Apex Development Conventions

How we develop, release, and scale Apex across OSS, premium, and iOS.

---

## 1. Repository Structure

**GitHub Org:** `apex-ai`

| Repo | Visibility | Purpose |
|------|-----------|---------|
| `apex` | Public | OSS server + setup wizard + skills + plugin API |
| `apex-premium` | Private | Premium Python package (multi-agent, SSO, RBAC) |
| `apex-ios` | Private | iOS app (SwiftUI) |
| `apex-docs` | Public | Documentation site (MkDocs) |
| `.github` | Public | Org-wide: profile README, SECURITY.md, issue templates, shared workflows |

OSS (`apex`) is the canonical upstream. Premium is a separate package that plugs in. iOS is standalone. No forks — premium never diverges from OSS core.

---

## 2. Plugin Architecture

Premium features live in a separate private Python package. Zero premium code in the OSS repo.

### Design decision: Simple register() — no pluggy

We evaluated pluggy (Datasette/pytest pattern) vs a simple `register(app, ctx)` function. **Simple wins for v1.** We have one plugin (apex-premium), not a community ecosystem. Pluggy adds implicit magic, harder stack traces, and an unnecessary dependency. Revisit when/if 5+ community plugins exist.

### How it works

OSS server at startup:
```python
# In apex.py lifespan
from apex.plugin_api import PluginContext

def load_premium_plugin(app, db_metadata, workspace_path):
    try:
        import apex_premium
        ctx = PluginContext(app, db_metadata, workspace_path)
        apex_premium.register(app, ctx)
    except ImportError:
        pass  # OSS-only mode
```

Premium package:
```python
# apex_premium/__init__.py
from apex.plugin_api import PluginContext
from fastapi import FastAPI

def register(app: FastAPI, ctx: PluginContext) -> None:
    ctx.add_middleware(...)                    # SSO, RBAC
    ctx.register_db_models(...)               # agent_profiles, etc.
    ctx.register_websocket_handlers(...)      # multi-agent routing
    ctx.register_ui_component("sidebar", ...) # premium UI
    app.include_router(premium_router)        # premium routes
```

### Plugin Contract

OSS exports `apex/plugin_api.py` — the stable contract premium depends on:

```python
from __future__ import annotations
from collections.abc import Callable
from typing import Any, Protocol
from fastapi import FastAPI
from sqlalchemy import MetaData

__version__ = "1.0"  # Independent from server version

class PluginContext:
    """Read-only context passed to premium. No raw DB/env access."""

    def __init__(self, app: FastAPI, db_metadata: MetaData, workspace_path: str):
        self.app = app
        self._db_metadata = db_metadata
        self.workspace_path = workspace_path
        self._ws_handlers: list[Callable] = []
        self._ui_components: dict[str, Any] = {}

    def register_db_models(self, metadata: MetaData) -> None:
        """Add premium tables (agent_profiles, channel_memberships, etc.)."""
        for table in metadata.tables.values():
            self._db_metadata.tables[table.name] = table

    def register_alembic_migrations(self, migration_dir: str) -> None:
        """Point to premium's migration folder. OSS runs them on startup."""
        pass  # implemented in main app

    def register_websocket_handlers(self, handler: Callable) -> None:
        """Register callbacks for WS message routing / multi-agent."""
        self._ws_handlers.append(handler)

    def add_middleware(self, middleware_class: type, **kwargs: Any) -> None:
        """Add auth, SSO, RBAC, audit middleware."""
        self.app.add_middleware(middleware_class, **kwargs)

    def extend_config_schema(self, section_name: str, pydantic_model: type) -> None:
        """Add premium config section with validation."""
        pass  # implemented in config loader

    def register_ui_component(self, location: str, component: Any) -> None:
        """Inject UI elements (menu items, dashboard panels, etc.)."""
        self._ui_components[location] = component


class Plugin(Protocol):
    """Premium must export this exact function."""
    @staticmethod
    def register(app: FastAPI, ctx: PluginContext) -> None: ...
```

### Extension Points (v1)

| Hook | Purpose | How premium uses it |
|------|---------|---------------------|
| `app.include_router()` | Routes | Premium API endpoints |
| `ctx.add_middleware()` | Middleware | SSO, RBAC, rate limiting |
| `ctx.register_db_models()` | Schema | agent_profiles, channel_memberships |
| `ctx.register_websocket_handlers()` | WS events | Multi-agent message routing |
| `ctx.extend_config_schema()` | Config | Premium config sections |
| `ctx.register_ui_component()` | UI injection | Dashboard panels, menu items |
| `ctx.register_alembic_migrations()` | DB migrations | Premium table migrations |

### Rules
- Plugin API versioned independently (`plugin_api.__version__`)
- Breaking changes: deprecate in 1 minor, remove in next major
- Premium matrix-tested against last 3 OSS versions
- `PluginContext` is read-only — plugins don't get raw DB sessions or env vars
- All plugin actions logged via audit middleware

---

## 3. Distribution

| Package | Method | Auth |
|---------|--------|------|
| OSS `apex` | PyPI (public) | None |
| Premium `apex-premium` | `pip install git+https://$TOKEN@github.com/apex-ai/apex-premium.git` | GitHub PAT |
| iOS | App Store / TestFlight | Apple subscription |

**Future:** GitHub Packages for premium when team grows. Air-gapped customers: provide signed wheels.

**Package integrity:** All wheels Sigstore-signed via `pypa/gh-action-pypi-publish`. Customers verify: `pip install sigstore; sigstore verify dist/*.whl`.

---

## 4. Versioning

**SemVer** (MAJOR.MINOR.PATCH) — signals breaking changes, critical for plugin contract stability.

| Component | Version example | Notes |
|-----------|----------------|-------|
| OSS server | `1.2.3` | Patch=bugfix, Minor=feature, Major=breaking |
| Plugin API | `1.0` | Independent. Increments only on contract changes. |
| Premium | `1.2.3` | Follows OSS. Minor can add premium-only features. |
| iOS | `1.2.3` | Independent from server versioning. |

### Release cadence

| Channel | Frequency | Details |
|---------|-----------|---------|
| OSS `apex` | Monthly (1st Friday) or on-demand | Patch releases anytime for critical fixes |
| Premium | Within 1 week of OSS release | Matrix-tested against OSS first |
| iOS | Bi-monthly tags → TestFlight | App Store quarterly |
| Docs | On merge to main | Auto-deploy |

### Breaking changes
1. Mark deprecated in code + docs (e.g., `@deprecated` decorator)
2. 2 minor releases (~2 months) warning period
3. Remove in next major version

### Automation
- `release-please` on main merges → auto-generates changelog PR + tag
- Premium: manual tag after OSS release passes CI
- `dependabot.yml` for weekly dependency update PRs

---

## 5. CI/CD (GitHub Actions)

### OSS repo (`apex`)

**On PR:**
- Ruff lint + format check
- pytest (Python 3.11 + 3.12 matrix)
- Plugin contract verification (`tests/plugin_contract.py`)

**On tag `v*`:**
- Full test suite
- Build wheel
- Sigstore sign
- Publish to PyPI
- Create GitHub Release with changelog

**On push to main:**
- Deploy docs (if `apex-docs` is separate, trigger via workflow dispatch)

### Premium repo (`apex-premium`)

**On PR:**
- Install OSS from `apex-ai/apex@main`
- Install premium
- pytest premium tests
- Matrix test against last 3 OSS tags

**On tag `v*`:**
- Build wheel
- Sigstore sign
- Push to GitHub Packages (private)

### iOS repo (`apex-ios`)

**On push to main:**
- SwiftLint
- Xcode build + test (iOS Simulator)

**On tag `v*`:**
- Fastlane → TestFlight
- Signing via App Store Connect API key (in GitHub Secrets)
- No manual certs in repo

---

## 6. Security Governance ("SecureClaw")

### SECURITY.md (org-wide, in `.github` repo)

```markdown
# Security Policy

## Supported Versions
| Version | Supported |
|---------|-----------|
| >= 1.0.x | Yes |
| < 1.0.x | No |

## Reporting a Vulnerability
- Email: security@apex-ai.org (private — never file public issues)
- Include: description, reproduction steps, impact assessment, affected versions
- Timeline: ACK within 48 hours, fix target within 7 days, public disclosure after patch (90 day max)

## Scope
- Apex server (apex.py)
- Plugin API (apex.plugin_api)
- Setup wizard (setup/)
- iOS app

## Out of Scope
- Third-party AI model behavior (Claude, Grok, etc.)
- User-created skills and plugins
- Self-hosted infrastructure configuration
```

### Practices
- **Vulnerability disclosure:** Private email → GitHub Security Advisory → coordinated patch
- **Community PRs:** Branch protection requires tests + 1 approval. Security-sensitive changes get manual audit.
- **Audits:** Annual third-party security audit (budget ~$5K). Publish report.
- **Bug bounties:** Not initially (overhead > payouts for solo). Revisit at 1000+ stars.
- **Dependencies:** Dependabot weekly PRs. Pin all production deps.
- **Premium integrity:** Sigstore signing on all wheels. Customers can verify provenance.

### Plugin security boundary
- `PluginContext` is a read-only proxy — no raw DB, no env vars, no filesystem outside workspace
- All plugin route calls logged in audit trail
- Plugins cannot register pre-startup hooks (prevents boot-time attacks)
- Rate limiting on premium routes

---

## 7. Scaling Plan

### Solo (now → 1000 stars)
- BDFL governance — you own all decisions
- Monthly releases, on-demand patches
- Community via GitHub Issues + Discussions
- No bounties, no foundation

### Small team (2-5 people)
- Hire marketer/community manager first (Plausible model)
- Core team with write access to premium repo
- CODEOWNERS file for review routing
- Weekly async standup (GitHub Project board)

### Growth (5+ / company)
- Consider foundation if >$10M ARR
- Launch Weeks (Supabase model) for community engagement
- Dedicated security team member
- Bug bounty program
- Enterprise SLAs

---

## 8. Development Workflow

### Local development setup

Clone both repos side by side:
```
~/apex-dev/
├── apex/           # git clone from apex-ai/apex
└── apex-premium/   # git clone from apex-ai/apex-premium
```

Link premium to local OSS for live development:
```bash
cd ~/apex-dev/apex-premium
uv add --editable ../apex
```

This adds to `apex-premium/pyproject.toml`:
```toml
[tool.uv.sources]
apex = { path = "../apex", editable = true }
```

Now `uv sync` in either repo works independently. Changes in `apex/` are instantly visible in premium.

### Day-to-day
1. Work on OSS features in `apex` repo (public)
2. Work on premium features in `apex-premium` repo (private)
3. Your personal server runs OSS + premium installed locally
4. Test changes locally before pushing

### Adding an OSS feature
1. Branch from `apex/main`
2. Implement + test
3. PR → CI (ruff, pytest, contract check)
4. Merge → `release-please` auto-generates changelog
5. Monthly tag → release

### Adding a premium feature
1. Branch from `apex-premium/main`
2. Implement using `apex.plugin_api` imports
3. PR → CI (matrix test against last 3 OSS versions)
4. Merge → manual tag after next OSS release

### Hotfix
1. Branch from latest tag
2. Fix + test
3. PR → merge → immediate patch tag (e.g., `v1.2.4`)
4. Premium follows within 24 hours if affected

---

## 9. File Naming Conventions

| File | Purpose |
|------|---------|
| `APEX.md` | Project instructions (replaces CLAUDE.md, model-agnostic) |
| `MEMORY.md` | Memory index file |
| `memory/*.md` | Individual memory files |
| `skills/*/SKILL.md` | Skill definitions |
| `state/config.json` | Server runtime config |
| `state/apex.db` | SQLite database |
| `state/ssl/` | TLS certificates |
| `state/embeddings/` | Vector index |
| `state/discovery_prompts.json` | Agent-guided discovery prompts |

---

---

## 10. 90-Day Launch Plan (~20 hrs/week)

### Weeks 1-2: Foundation & Repos
- Create `apex-ai` GitHub org + repos (apex, apex-premium, apex-ios, .github, apex-docs)
- Decompose current server into clean OSS version
- Implement `plugin_api.py` + `load_premium_plugin()`
- Set up shared `.github` workflows (ruff, pytest, Sigstore)
- Write SECURITY.md + threat model doc
- **Milestone:** `uv sync` works in both repos, premium registers cleanly

### Weeks 3-4: Core Features + Premium Skeleton
- Implement the 7 extension points in PluginContext
- Build minimum viable premium (1-2 premium-only routes + DB tables)
- Add `/api/version` endpoint for iOS compatibility
- Local dev workflow documented in READMEs
- **Milestone:** End-to-end server runs with/without premium

### Weeks 5-8: iOS MVP + TestFlight
- Build SwiftUI iOS app (connect, chat, mTLS cert import)
- Server version check + graceful degradation
- Server-side "Download client cert" endpoint + docs
- Submit to TestFlight (internal 100 + external beta link)
- **Milestone:** First TestFlight build live with 5-10 friends testing

### Weeks 9-12: Polish, Release & Community
- Week 9: OSS release v1.0.0 to PyPI + blog post
- Week 10: Premium release (private) + self-hosting docs
- Week 11: OpenSSF Scorecard + Best Practices badges + first Security Transparency Report
- Week 12: Community seeding (r/selfhosted, r/LocalLLaMA, Show HN, Discord server)
- **Milestone:** Public OSS repo live, 50+ TestFlight users, first community PRs

---

*Last updated: 2026-03-27. Review quarterly.*
