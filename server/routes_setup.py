"""Browser-based setup wizard routes for Apex.

Mounted in apex.py. All /setup and /api/setup/* endpoints are mTLS-exempt
(user has not yet installed their client certificate at this point).

Security:
- All POST endpoints require X-Requested-With: XMLHttpRequest (CSRF guard)
- API keys written via _update_env_var() — same path as dashboard
- Workspace path validated: absolute, no '..', must exist
- Progress tracked in state/.setup_progress.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.responses import StreamingResponse

import env
from config import Config as _Config
from dashboard import _update_env_var, _env_has_key

# ---------------------------------------------------------------------------
# Ensure setup/ package (repo root) is importable from server context
# ---------------------------------------------------------------------------
_apex_root_str = str(env.APEX_ROOT)
if _apex_root_str not in sys.path:
    sys.path.insert(0, _apex_root_str)

from setup.progress import (  # noqa: E402
    load_progress,
    phase_completed,
    mark_phase_completed,
)
from setup.bootstrap import _seed_workspace  # noqa: E402

# ---------------------------------------------------------------------------
# Router + shared state
# ---------------------------------------------------------------------------
setup_router = APIRouter()

_STATE_DIR: Path = env.APEX_ROOT / "state"
_DB_PATH: Path = _STATE_DIR / "apex.db"
_DISCOVERY_PROMPTS_PATH: Path = _STATE_DIR / "discovery_prompts.json"

# Config instance (lazy — state dir may not exist at import time)
_config: _Config | None = None


def _get_config() -> _Config:
    global _config
    if _config is None:
        _config = _Config(_STATE_DIR)
    return _config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csrf_ok(request: Request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


async def _check_ollama() -> bool:
    import urllib.request
    try:
        def _try():
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)  # noqa: S310
        await asyncio.to_thread(_try)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# GET /setup — serve wizard or redirect if already complete
# ---------------------------------------------------------------------------
@setup_router.get("/setup", include_in_schema=False)
async def get_setup():
    if phase_completed(_STATE_DIR, "setup_complete"):
        return RedirectResponse("/", 302)
    from setup_html import SETUP_HTML  # imported lazily — lives next to this file
    return HTMLResponse(SETUP_HTML)


# ---------------------------------------------------------------------------
# GET /api/setup/status
# ---------------------------------------------------------------------------
@setup_router.get("/api/setup/status")
async def api_setup_status():
    progress = load_progress(_STATE_DIR)
    phases = progress.get("phases", {})

    # Step indices: 0=welcome 1=claude 2=models 3=workspace 4=history 5=knowledge 6=done
    _STEPS = ["welcome", "claude", "models", "workspace", "history", "knowledge", "done"]
    current_step = 0
    for i, step in enumerate(_STEPS):
        if phases.get(step, {}).get("completed"):
            current_step = i + 1
    current_step = min(current_step, len(_STEPS) - 1)

    ollama_running = await _check_ollama()

    try:
        workspace_cfg = _get_config().get_section("workspace")
    except Exception:
        workspace_cfg = {}

    return JSONResponse({
        "current_step": current_step,
        "phases": {k: bool(v.get("completed")) for k, v in phases.items()},
        "models": {
            "xai": _env_has_key("XAI_API_KEY"),
            "google": _env_has_key("GOOGLE_API_KEY"),
            "anthropic": _env_has_key("ANTHROPIC_API_KEY"),
            "claude_oauth": bool(os.environ.get("ANTHROPIC_API_KEY", ""))
                            and not _env_has_key("ANTHROPIC_API_KEY"),
            "deepseek": _env_has_key("DEEPSEEK_API_KEY"),
            "zhipu": _env_has_key("ZHIPU_API_KEY"),
            "ollama": ollama_running,
        },
        "workspace": {
            "path": workspace_cfg.get("path", ""),
            "permission_mode": workspace_cfg.get("permission_mode", "acceptEdits"),
        },
    })


# ---------------------------------------------------------------------------
# CLI auth checks (Claude + Codex)
# ---------------------------------------------------------------------------

def _find_cli(name: str) -> str:
    """Find a CLI binary by name, checking common install paths."""
    import shutil
    path = shutil.which(name)
    if path:
        return path
    # Common locations not always in PATH (e.g. server subprocesses)
    from pathlib import Path
    for candidate in [
        Path.home() / ".local" / "bin" / name,
        Path("/opt/homebrew/bin") / name,
        Path("/usr/local/bin") / name,
    ]:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(f"{name} not found")


def _check_claude_auth_status() -> dict:
    """Run `claude auth status` and return parsed JSON.

    Returns {"loggedIn": true/false, "email": ..., "subscriptionType": ...}
    Raises FileNotFoundError if claude CLI not installed.
    """
    import subprocess
    cli = _find_cli("claude")
    result = subprocess.run(
        [cli, "auth", "status"],
        capture_output=True, text=True, timeout=15,
    )
    # claude auth status returns exit 0 on success, non-zero on failure
    # but ALWAYS outputs JSON (even on failure)
    output = result.stdout.strip() or result.stderr.strip()
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"loggedIn": False, "error": output or "no output"}


def _check_codex_auth_status() -> dict:
    """Run `codex login status` and return structured result.

    Returns {"loggedIn": true/false, "provider": "ChatGPT"|...}
    Raises FileNotFoundError if codex CLI not installed.
    """
    import subprocess
    cli = _find_cli("codex")
    result = subprocess.run(
        [cli, "login", "status"],
        capture_output=True, text=True, timeout=15,
    )
    output = (result.stdout.strip() or result.stderr.strip()).lower()
    if "logged in" in output:
        # e.g. "Logged in using ChatGPT"
        provider = output.split("using")[-1].strip() if "using" in output else ""
        return {"loggedIn": True, "provider": provider}
    return {"loggedIn": False, "error": output}


# ---------------------------------------------------------------------------
# GET /api/setup/oauth-status — check OAuth token status
# ---------------------------------------------------------------------------

@setup_router.get("/api/setup/oauth-status")
async def api_auth_oauth_status():
    """Check Claude CLI auth status — end-to-end validation."""
    import asyncio as _aio

    try:
        status = await _aio.to_thread(_check_claude_auth_status)
        if status.get("loggedIn"):
            return JSONResponse({
                "token_found": True,
                "valid": True,
                "source": status.get("authMethod", "cli"),
                "email": status.get("email", ""),
                "subscription": status.get("subscriptionType", ""),
            })
        return JSONResponse({
            "token_found": False,
            "valid": False,
            "error": status.get("error", ""),
        })
    except FileNotFoundError:
        return JSONResponse({
            "token_found": False,
            "valid": False,
            "error": "Claude Code CLI not installed",
        })
    except Exception as exc:
        return JSONResponse({
            "token_found": False,
            "valid": False,
            "error": str(exc),
        })


# ---------------------------------------------------------------------------
# GET /api/setup/codex-status — check Codex CLI auth
# ---------------------------------------------------------------------------

@setup_router.get("/api/setup/codex-status")
async def api_codex_status():
    """Check Codex CLI login status."""
    import asyncio as _aio
    try:
        status = await _aio.to_thread(_check_codex_auth_status)
        return JSONResponse(status)
    except FileNotFoundError:
        return JSONResponse({"loggedIn": False, "error": "not_installed"})
    except Exception as exc:
        return JSONResponse({"loggedIn": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# POST /api/setup/models — save API keys
# ---------------------------------------------------------------------------
_KEY_MAP = {
    "xai_api_key": "XAI_API_KEY",
    "google_api_key": "GOOGLE_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "zhipu_api_key": "ZHIPU_API_KEY",
}


async def _validate_optional_key(field: str, value: str) -> str | None:
    """Validate an optional API key. Returns error string or None if valid."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if field == "xai_api_key":
                # xAI: list models (lightweight, no usage cost)
                r = await client.get(
                    "https://api.x.ai/v1/models",
                    headers={"Authorization": f"Bearer {value}"},
                )
                if r.status_code == 401:
                    return "Grok: Invalid API key. Check your key at x.ai."
                if r.status_code != 200:
                    return f"Grok: API returned {r.status_code}. Try again."

            elif field == "google_api_key":
                # Google: list models (free, no usage cost)
                r = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": value, "pageSize": "1"},
                )
                if r.status_code in (400, 403):
                    return "Google: Invalid API key. Check your key at aistudio.google.com."
                if r.status_code != 200:
                    return f"Google: API returned {r.status_code}. Try again."

            elif field == "openai_api_key":
                # OpenAI: list models (lightweight, no usage cost)
                r = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {value}"},
                )
                if r.status_code == 401:
                    return "OpenAI: Invalid API key. Check your key at platform.openai.com."
                if r.status_code != 200:
                    return f"OpenAI: API returned {r.status_code}. Try again."

            elif field == "deepseek_api_key":
                # DeepSeek: list models (OpenAI-compatible)
                r = await client.get(
                    "https://api.deepseek.com/models",
                    headers={"Authorization": f"Bearer {value}"},
                )
                if r.status_code == 401:
                    return "DeepSeek: Invalid API key. Check your key at platform.deepseek.com."
                if r.status_code != 200:
                    return f"DeepSeek: API returned {r.status_code}. Try again."

            elif field == "zhipu_api_key":
                # Zhipu/Z.ai: list models (OpenAI-compatible)
                r = await client.get(
                    "https://open.z.ai/api/paas/v4/models",
                    headers={"Authorization": f"Bearer {value}"},
                )
                if r.status_code == 401:
                    return "Zhipu: Invalid API key. Check your key at z.ai."
                if r.status_code != 200:
                    return f"Zhipu: API returned {r.status_code}. Try again."

    except httpx.TimeoutException:
        return f"{field}: Validation timed out. Check your internet connection."
    except Exception as exc:
        log(f"setup: key validation error for {field}: {exc}")
        # Don't block on transient network errors — save the key
        return None

    return None


@setup_router.post("/api/setup/models")
async def api_setup_models(request: Request):
    if not _csrf_ok(request):
        return JSONResponse({"error": "CSRF check failed"}, status_code=403)

    data = await request.json()
    saved: list[str] = []
    errors: list[str] = []
    is_step2 = bool(data.get("auth_method") or data.get("anthropic_api_key"))
    skipped_claude = data.get("skip_claude", False)

    # ── Step 2: Anthropic auth (optional — users can skip) ────────────
    auth_method = (data.get("auth_method") or "").strip()
    auth_valid = False

    if skipped_claude:
        # User chose to skip Claude — proceed without Anthropic auth
        auth_valid = True
        saved.append("skipped_claude")
        log("setup: Claude skipped by user — will use other models")

    elif auth_method == "oauth":
        # Subscription auth — use `claude auth status` for end-to-end validation
        try:
            import asyncio as _aio
            status = await _aio.to_thread(_check_claude_auth_status)
            if status.get("loggedIn"):
                # CLI confirms auth is valid. Don't set ANTHROPIC_API_KEY —
                # OAuth tokens break when set as env vars. The SDK subprocess
                # reads Keychain directly for OAuth auth.
                # Clear any stale OAuth token from env if present
                cur = os.environ.get("ANTHROPIC_API_KEY", "")
                if cur and "oat" in cur[:15]:
                    del os.environ["ANTHROPIC_API_KEY"]
                auth_valid = True
                saved.append("oauth")
                log(f"setup: OAuth validated via CLI "
                    f"(email={status.get('email')}, sub={status.get('subscriptionType')})")
            else:
                errors.append(
                    "Claude Code is not logged in. "
                    "Run 'claude auth login' in your terminal, then try again."
                )
        except FileNotFoundError:
            errors.append(
                "Claude Code CLI not found. "
                "Install it first: https://docs.anthropic.com/en/docs/claude-code"
            )
        except Exception as exc:
            errors.append(f"OAuth validation failed: {exc}")

    elif data.get("anthropic_api_key", "").strip():
        # API key auth — validate before saving
        api_key = data["anthropic_api_key"].strip()
        try:
            from agent_sdk import _validate_token
            import asyncio as _aio
            valid = await _aio.to_thread(_validate_token, api_key)
            if valid:
                _update_env_var("ANTHROPIC_API_KEY", api_key)
                auth_valid = True
                saved.append("anthropic_api_key")
            else:
                errors.append(
                    "API key rejected by Anthropic. "
                    "Check the key at console.anthropic.com and try again."
                )
        except OSError:
            # Windows: urllib SSL can throw Bad file descriptor — save anyway
            _update_env_var("ANTHROPIC_API_KEY", api_key)
            auth_valid = True
            saved.append("anthropic_api_key")
        except Exception as exc:
            errors.append(f"API key validation failed: {exc}")

    # If this is Step 2 and auth failed (and not skipped), block
    if is_step2 and not auth_valid:
        return JSONResponse(
            {"error": errors[0] if errors else "Authentication required",
             "errors": errors},
            status_code=400,
        )

    # ── Step 3: Optional model keys (validate before saving) ─────────
    for field, env_var in _KEY_MAP.items():
        if field == "anthropic_api_key":
            continue  # Already handled above
        value = (data.get(field) or "").strip()
        if value:
            err = await _validate_optional_key(field, value)
            if err:
                errors.append(err)
            else:
                try:
                    _update_env_var(env_var, value)
                    saved.append(field)
                except Exception as exc:
                    errors.append(f"{field}: {exc}")

    mark_phase_completed(_STATE_DIR, "claude")
    mark_phase_completed(_STATE_DIR, "models")
    return JSONResponse({"status": "ok", "saved": saved, "errors": errors})


# ---------------------------------------------------------------------------
# POST /api/setup/workspace — save workspace path + permission mode
# ---------------------------------------------------------------------------
_VALID_MODES = frozenset({"acceptEdits", "bypassPermissions", "plan"})


@setup_router.post("/api/setup/workspace")
async def api_setup_workspace(request: Request):
    if not _csrf_ok(request):
        return JSONResponse({"error": "CSRF check failed"}, status_code=403)

    data = await request.json()
    workspace_path = (data.get("workspace_path") or "").strip()
    permission_mode = (data.get("permission_mode") or "acceptEdits").strip()

    if permission_mode not in _VALID_MODES:
        return JSONResponse({"error": "Invalid permission mode"}, status_code=400)

    if workspace_path:
        if ".." in workspace_path:
            return JSONResponse({"error": "Invalid path (contains ..)"}, status_code=400)
        p = Path(workspace_path)
        if not p.is_absolute():
            return JSONResponse({"error": "Path must be absolute"}, status_code=400)
        if not p.exists():
            return JSONResponse({"error": "Path does not exist"}, status_code=400)

    try:
        cfg = _get_config()
        cfg.update_section("workspace", {"path": workspace_path})
        cfg.update_section("models", {"permission_mode": permission_mode})
        if workspace_path:
            _seed_workspace(Path(workspace_path))
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    mark_phase_completed(
        _STATE_DIR, "workspace",
        path=workspace_path, permission_mode=permission_mode,
    )
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# GET /api/setup/history/scan — discover AI conversation history
# ---------------------------------------------------------------------------

@setup_router.get("/api/setup/history/scan")
async def api_setup_history_scan():
    """Scan for Claude Code, Codex, and ChatGPT conversation histories."""
    from setup.scanner import _detect_ai_conversations

    progress = load_progress(_STATE_DIR)
    workspace_str = (
        progress.get("phases", {}).get("workspace", {}).get("path", "")
        or os.environ.get("APEX_WORKSPACE", "")
        or str(Path.home())
    )
    workspace = Path(workspace_str.split(":")[0].strip() or str(Path.home()))

    sources = await asyncio.to_thread(_detect_ai_conversations, workspace)
    ollama_running = await _check_ollama()
    google_key = _env_has_key("GOOGLE_API_KEY")

    return JSONResponse({
        "sources": sources,
        "embedding_options": {
            "ollama": ollama_running,
            "gemini": google_key,
        },
    })


# ---------------------------------------------------------------------------
# POST /api/setup/history — save history preferences + start indexing
# ---------------------------------------------------------------------------

@setup_router.post("/api/setup/history")
async def api_setup_history(request: Request):
    if not _csrf_ok(request):
        return JSONResponse({"error": "CSRF check failed"}, status_code=403)

    data = await request.json()
    selected_sources = data.get("sources", [])  # ["claude", "codex"]
    embedding_backend = data.get("embedding_backend")  # "ollama" | "gemini" | null

    # Build transcript_dirs from selected sources
    transcript_dirs: list[str] = []
    for src in selected_sources:
        if src == "claude":
            p = str(Path.home() / ".claude" / "projects")
            if Path(p).is_dir():
                transcript_dirs.append(p)
        elif src == "codex":
            p = str(Path.home() / ".codex" / "sessions")
            if Path(p).is_dir():
                transcript_dirs.append(p)

    # Save to config
    try:
        cfg = _get_config()
        cfg.update_section("history", {
            "transcript_dirs": ",".join(transcript_dirs),
            "embedding_backend": embedding_backend or "",
            "sources_discovered": json.dumps(selected_sources),
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    # If embedding requested, return SSE stream with indexing progress
    if embedding_backend and selected_sources:
        async def _sse():
            try:
                yield f"data: {json.dumps({'type': 'progress', 'step': 'Preparing...', 'pct': 5})}\\n\\n"

                # Pull Ollama model if needed
                if embedding_backend == "ollama":
                    yield f"data: {json.dumps({'type': 'progress', 'step': 'Checking nomic-embed-text model...', 'pct': 10})}\\n\\n"
                    try:
                        await asyncio.to_thread(_ensure_ollama_embed_model)
                    except Exception as exc:
                        yield f"data: {json.dumps({'type': 'error', 'message': f'Failed to pull embedding model: {exc}'})}\\n\\n"
                        return

                yield f"data: {json.dumps({'type': 'progress', 'step': 'Indexing transcripts...', 'pct': 20})}\\n\\n"

                result = await asyncio.to_thread(
                    _run_transcript_indexing,
                    transcript_dirs,
                    embedding_backend,
                )

                mark_phase_completed(
                    _STATE_DIR, "history",
                    sources=selected_sources,
                    embedding_backend=embedding_backend,
                    files_indexed=result.get("indexed", 0),
                )
                yield f"data: {json.dumps({'type': 'done', 'result': result})}\\n\\n"
            except asyncio.CancelledError:
                return
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\\n\\n"

        return StreamingResponse(
            _sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # No embedding — just mark complete and return
    mark_phase_completed(
        _STATE_DIR, "history",
        sources=selected_sources,
        embedding_backend=None,
        skipped_embedding=True,
    )
    return JSONResponse({"status": "ok", "skipped_embedding": True})


def _ensure_ollama_embed_model() -> None:
    """Pull nomic-embed-text if not already available in Ollama."""
    import urllib.request
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            data = json.loads(resp.read())
        models = [m.get("name", "") for m in data.get("models", [])]
        if any("nomic-embed-text" in m for m in models):
            return
    except Exception:
        pass
    # Pull the model
    payload = json.dumps({"name": "nomic-embed-text"}).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/pull",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310
        # Read to completion (Ollama streams progress)
        while resp.read(4096):
            pass


def _run_transcript_indexing(transcript_dirs: list[str], backend: str) -> dict:
    """Index transcripts using the specified embedding backend.

    Sets env vars so memory_search picks up the right config.
    """
    os.environ["APEX_TRANSCRIPT_DIRS"] = ",".join(transcript_dirs)
    os.environ["APEX_EMBEDDING_BACKEND"] = backend

    try:
        import importlib
        # Force reimport to pick up new env vars
        if "memory_search" in sys.modules:
            importlib.reload(sys.modules["memory_search"])
        from memory_search import index_transcripts
        return index_transcripts(force=True)
    except ImportError:
        return {"indexed": 0, "skipped": 0, "error": "memory_search module not available"}


# ---------------------------------------------------------------------------
# POST /api/setup/knowledge — SSE knowledge scan
# ---------------------------------------------------------------------------

@setup_router.post("/api/setup/knowledge")
async def api_setup_knowledge(request: Request):
    if not _csrf_ok(request):
        return JSONResponse({"error": "CSRF check failed"}, status_code=403)

    data = await request.json()
    scan = bool(data.get("scan", False))

    if not scan:
        mark_phase_completed(_STATE_DIR, "knowledge", skipped=True)
        return JSONResponse({"status": "ok", "skipped": True})

    async def _sse():
        try:
            progress = load_progress(_STATE_DIR)
            workspace_str = (
                progress.get("phases", {}).get("workspace", {}).get("path", "")
                or os.environ.get("APEX_WORKSPACE", "")
                or str(Path.home())
            )
            permission_mode = (
                progress.get("phases", {}).get("workspace", {}).get("permission_mode", "")
                or os.environ.get("APEX_PERMISSION_MODE", "acceptEdits")
            )
            workspace = Path(workspace_str.split(":")[0].strip() or str(Path.home()))

            yield f"data: {json.dumps({'type': 'progress', 'step': 'Scanning workspace...', 'pct': 10})}\n\n"

            result = await asyncio.to_thread(
                _run_headless_ingest,
                env.APEX_ROOT,
                workspace,
                permission_mode,
            )

            mark_phase_completed(
                _STATE_DIR, "knowledge",
                files_written=result.get("files_written", 0),
            )
            yield f"data: {json.dumps({'type': 'done', 'result': result})}\n\n"
        except asyncio.CancelledError:
            return
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _run_headless_ingest(apex_root: Path, workspace: Path, permission_mode: str) -> dict:
    from setup.ingest import run_knowledge_ingestion_headless
    return run_knowledge_ingestion_headless(apex_root, workspace, permission_mode)


# ---------------------------------------------------------------------------
# POST /api/setup/complete — finalize setup
# ---------------------------------------------------------------------------

# Discovery prompts payload (mirrors setup.py DISCOVERY_PROMPTS)
_DISCOVERY_PROMPTS: dict = {
    "version": 1,
    "shown": False,
    "categories": [
        {
            "name": "Get to know me",
            "prompts": [
                {
                    "label": "Import my ChatGPT history",
                    "prompt": (
                        "Help me import my ChatGPT conversation history. Walk me "
                        "through exporting from chat.openai.com and then parse the "
                        "export to learn about my interests, projects, and how I work."
                    ),
                },
                {
                    "label": "Import my Claude history",
                    "prompt": (
                        "Scan my Claude Code conversation history at ~/.claude/projects/ "
                        "and index the transcripts. Summarize what you learn about my "
                        "work patterns and create memory files."
                    ),
                },
                {
                    "label": "Learn from my GitHub",
                    "prompt": (
                        "Learn about me from my GitHub profile. Ask for my username, "
                        "then look at my repositories, starred repos, and languages "
                        "to understand my technical interests. Create a user profile memory."
                    ),
                },
            ],
        },
        {
            "name": "Connect your tools",
            "prompts": [
                {
                    "label": "Connect to GitHub",
                    "prompt": (
                        "Help me connect to my GitHub repositories so you can read "
                        "issues, PRs, and code. Walk me through setting up a personal "
                        "access token safely."
                    ),
                },
                {
                    "label": "Set up calendar integration",
                    "prompt": (
                        "Help me connect my calendar (Google Calendar or Apple Calendar) "
                        "so you can be schedule-aware. Start with read-only access."
                    ),
                },
            ],
        },
        {
            "name": "Customize your AI",
            "prompts": [
                {
                    "label": "Learn my coding style",
                    "prompt": (
                        "Analyze my recent git commits to learn my coding style, naming "
                        "conventions, and patterns. Create a coding style memory."
                    ),
                },
                {
                    "label": "Set up daily briefing",
                    "prompt": (
                        "Help me set up an automated daily briefing that summarizes my "
                        "calendar, alerts, and project status each morning."
                    ),
                },
            ],
        },
    ],
}


def _write_discovery_prompts() -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(_STATE_DIR), suffix=".tmp", prefix=".discovery_prompts_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_DISCOVERY_PROMPTS, f, indent=2)
            f.write("\n")
        os.replace(tmp, str(_DISCOVERY_PROMPTS_PATH))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _preseed_welcome_chat() -> None:
    """Create a 'Welcome to Apex' chat in the database. Skips if already present."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT,
                claude_session_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL REFERENCES chats(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                tool_events TEXT DEFAULT '[]',
                thinking TEXT DEFAULT '',
                cost_usd REAL DEFAULT 0,
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
        """)
        for col, default in [("model", "NULL"), ("type", "'chat'"), ("category", "NULL")]:
            try:
                conn.execute(f"ALTER TABLE chats ADD COLUMN {col} TEXT DEFAULT {default}")
            except Exception:
                pass

        # Add profile_id column if missing (for older DBs)
        try:
            conn.execute("ALTER TABLE chats ADD COLUMN profile_id TEXT DEFAULT ''")
        except Exception:
            pass

        row = conn.execute(
            "SELECT id FROM chats WHERE type = 'chat' AND title = 'Welcome to Apex' LIMIT 1"
        ).fetchone()
        if row:
            return

        chat_id = str(uuid.uuid4())[:8]
        msg_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        guide_id = "sys-guide"
        welcome_msg = (
            "Welcome to Apex! I'm Guide — your platform expert.\n\n"
            "I know every feature, setting, and API endpoint in Apex. "
            "Ask me anything:\n\n"
            "- **\"How do I add my Gemini API key?\"**\n"
            "- **\"What models are available?\"**\n"
            "- **\"How does the memory system work?\"**\n"
            "- **\"Set up Telegram alerts\"**\n"
            "- **\"Create a custom persona\"**\n\n"
            "I can walk you through configuration step by step, "
            "or explain how any part of the platform works. "
            "This channel is always here — come back anytime you have questions."
        )
        conn.execute(
            "INSERT INTO chats (id, title, type, profile_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, "Welcome to Apex", "chat", guide_id, now, now),
        )
        conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (msg_id, chat_id, "assistant", welcome_msg, now),
        )
        conn.commit()
    finally:
        conn.close()


@setup_router.post("/api/setup/complete")
async def api_setup_complete(request: Request):
    if not _csrf_ok(request):
        return JSONResponse({"error": "CSRF check failed"}, status_code=403)

    try:
        await asyncio.to_thread(_write_discovery_prompts)
    except Exception:
        pass

    try:
        await asyncio.to_thread(_preseed_welcome_chat)
    except Exception:
        pass

    mark_phase_completed(
        _STATE_DIR,
        "setup_complete",
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    return JSONResponse({"status": "ok"})
