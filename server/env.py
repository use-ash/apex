"""Canonical environment variable registry for the Apex server.

All os.environ reads live here. Every other module imports constants
from this file instead of calling os.environ directly. This is the
single source of truth for env-var names and their default values.

Priority at runtime (when config.py Admin portal is in use):
  config.json  >  env var  >  default below

Note: a small number of variables are not yet surfaced in the Admin
portal schema (SSL paths, APNs, xAI management keys, Codex CLI). These
are env-only and documented here for discoverability.

Known default divergence (pre-existing, do not silently fix):
  APEX_HOST — apex.py startup default: 127.0.0.1
               config.py schema default: 0.0.0.0
  Uvicorn binds to the value of HOST below. The Admin portal reflects
  config.py's default. Fix requires coordinated change in both files.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

HOST: str = os.environ.get("APEX_HOST", "127.0.0.1")
PORT: int = int(os.environ.get("APEX_PORT", "8300"))
LOG_LEVEL: str = os.environ.get("APEX_LOG_LEVEL", "info")
DEBUG: bool = os.environ.get("APEX_DEBUG", "").lower() in {"1", "true", "yes"}

# TLS / mTLS — env-only (not in Admin portal schema)
SSL_CERT: str = os.environ.get("APEX_SSL_CERT", "")
SSL_KEY: str = os.environ.get("APEX_SSL_KEY", "")
SSL_CA: str = os.environ.get("APEX_SSL_CA", "")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# APEX_ROOT resolves to the repo root (parent of server/).
APEX_ROOT: Path = Path(
    os.environ.get("APEX_ROOT", str(Path(__file__).resolve().parent.parent))
)
# APEX_WORKSPACE can be a single path or colon-separated list.
# WORKSPACE is always the primary (first) path — used for APEX.md, skills, etc.
# WORKSPACE_PATHS is the full colon-separated string for safety.py multi-root checks.
_ws_raw: str = os.environ.get("APEX_WORKSPACE", os.getcwd())
WORKSPACE: Path = Path(_ws_raw.split(":")[0].strip() or os.getcwd())
WORKSPACE_PATHS: str = _ws_raw
MCP_EXTRA_ROOTS_RAW: str = os.environ.get("APEX_MCP_EXTRA_ROOTS", "")

def _normalize_workspace_roots(raw: str | None) -> list[str]:
    roots: list[str] = []
    text = str(raw or "").replace("\r\n", "\n").replace("\r", "\n")
    for line in text.split("\n"):
        for chunk in line.split(":"):
            item = chunk.strip()
            if item and item not in roots:
                roots.append(item)
    return roots


def get_runtime_workspace_paths_list() -> list[str]:
    """Return workspace roots from config.json first, env fallback second."""
    config_path = APEX_ROOT / "state" / "config.json"
    try:
        if config_path.exists():
            data = json.loads(config_path.read_text())
            raw = (
                data.get("workspace", {}).get("path", "")
                if isinstance(data, dict) else ""
            )
            roots = _normalize_workspace_roots(str(raw))
            if roots:
                return roots
    except Exception:
        pass
    roots = _normalize_workspace_roots(WORKSPACE_PATHS)
    return roots or [str(WORKSPACE)]


def get_runtime_mcp_roots_list() -> list[str]:
    roots = list(get_runtime_workspace_paths_list())
    for extra in _normalize_workspace_roots(MCP_EXTRA_ROOTS_RAW):
        if extra not in roots:
            roots.append(extra)
    return roots or [str(WORKSPACE)]


def get_runtime_workspace_paths() -> str:
    return ":".join(get_runtime_workspace_paths_list())


def get_runtime_workspace_root() -> Path:
    roots = get_runtime_workspace_paths_list()
    return Path(roots[0] if roots else str(WORKSPACE))


def rewrite_mcp_servers_for_workspace(
    servers: dict[str, dict],
    workspace_paths: str | list[str] | None = None,
) -> dict[str, dict]:
    """Rewrite filesystem MCP roots to the configured workspace roots."""
    if isinstance(workspace_paths, str):
        roots = _normalize_workspace_roots(workspace_paths)
    elif isinstance(workspace_paths, list):
        roots = [str(root).strip() for root in workspace_paths if str(root).strip()]
    else:
        roots = get_runtime_workspace_paths_list()
    roots = roots or [str(WORKSPACE)]
    mcp_roots = list(roots)
    for extra in _normalize_workspace_roots(MCP_EXTRA_ROOTS_RAW):
        if extra not in mcp_roots:
            mcp_roots.append(extra)

    rewritten: dict[str, dict] = {}
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            rewritten[name] = cfg
            continue
        command = str(cfg.get("command") or "")
        args = list(cfg.get("args") or [])

        # npx -y @modelcontextprotocol/server-filesystem <roots...>
        if command == "npx" and "@modelcontextprotocol/server-filesystem" in args:
            idx = args.index("@modelcontextprotocol/server-filesystem")
            new_cfg = dict(cfg)
            new_cfg["args"] = args[: idx + 1] + mcp_roots
            rewritten[name] = new_cfg
            continue

        # docker run ... mcp/filesystem <roots...>
        if command == "docker":
            image_idx = next(
                (i for i, arg in enumerate(args) if "mcp/filesystem" in str(arg)),
                -1,
            )
            if image_idx >= 0:
                prefix = args[:image_idx]
                cleaned_prefix: list[str] = []
                i = 0
                while i < len(prefix):
                    if prefix[i] == "-v" and (i + 1) < len(prefix):
                        i += 2
                        continue
                    cleaned_prefix.append(prefix[i])
                    i += 1
                mounts: list[str] = []
                for root in roots:
                    mounts.extend(["-v", f"{root}:{root}"])
                for root in mcp_roots:
                    if root in roots:
                        continue
                    mounts.extend(["-v", f"{root}:{root}"])
                new_cfg = dict(cfg)
                new_cfg["args"] = cleaned_prefix + mounts + [args[image_idx]] + mcp_roots
                rewritten[name] = new_cfg
                continue

        rewritten[name] = cfg

    return rewritten

# ---------------------------------------------------------------------------
# Models & SDK
# ---------------------------------------------------------------------------

MODEL: str = os.environ.get("APEX_MODEL", "claude-sonnet-4-6")
PERMISSION_MODE: str = os.environ.get("APEX_PERMISSION_MODE", "acceptEdits")
SDK_QUERY_TIMEOUT: int = int(os.environ.get("APEX_SDK_QUERY_TIMEOUT", "30"))
SDK_STREAM_TIMEOUT: int = int(os.environ.get("APEX_SDK_STREAM_TIMEOUT", "900"))
MAX_TOOL_ITERATIONS: int = int(os.environ.get("APEX_MAX_TOOL_ITERATIONS", "50"))
COMPACTION_THRESHOLD: int = int(os.environ.get("APEX_COMPACTION_THRESHOLD", "100000"))
COMPACTION_MODEL: str = os.environ.get(
    "APEX_COMPACTION_MODEL", "grok-4-1-fast-non-reasoning"
)
COMPACTION_OLLAMA_FALLBACK: str = os.environ.get(
    "APEX_COMPACTION_OLLAMA_FALLBACK", "gemma3:27b"
)

# Ollama / MLX base URLs — env-only (also in Admin portal schema)
OLLAMA_URL: str = os.environ.get("APEX_OLLAMA_URL", "http://localhost:11434")
MLX_URL: str = os.environ.get("APEX_MLX_URL", "http://localhost:8400")

# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------

ENABLE_SKILL_DISPATCH: bool = (
    os.environ.get("APEX_ENABLE_SKILL_DISPATCH", "true").lower()
    in {"1", "true", "yes"}
)
ENABLE_SUBCONSCIOUS_WHISPER: bool = (
    os.environ.get("APEX_ENABLE_WHISPER", "").lower() in {"1", "true", "yes"}
)
GROUPS_ENABLED: bool = (
    os.environ.get("APEX_GROUPS_ENABLED", "").lower() in {"1", "true", "yes"}
)

# Dev mode — auto-True when running on a non-production port.
# In dev mode, premium modules load from plaintext .py instead of encrypted .enc.
DEV_MODE: bool = (
    os.environ.get("APEX_DEV_MODE", "").lower() in {"1", "true", "yes"}
    or PORT != 8300
)
ALLOW_LOCAL_TOOLS: bool = (
    os.environ.get("APEX_ALLOW_LOCAL_TOOLS", "").lower() in {"1", "true", "yes"}
)

# ---------------------------------------------------------------------------
# Secrets (raw strings — never log, never repr without masking)
# ---------------------------------------------------------------------------

ALERT_TOKEN: str = os.environ.get("APEX_ALERT_TOKEN", "")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
XAI_API_KEY: str = os.environ.get("XAI_API_KEY", "")

# Codex CLI binary — env-only
CODEX_CLI: str = os.environ.get("CODEX_CLI_PATH", "codex")

# xAI management (model listing) — env-only
XAI_MANAGEMENT_KEY: str = os.environ.get("XAI_MANAGEMENT_KEY", "")
XAI_TEAM_ID: str = os.environ.get("XAI_TEAM_ID", "")

# ---------------------------------------------------------------------------
# APNs — env-only
# ---------------------------------------------------------------------------

APNS_KEY_ID: str = os.environ.get("APEX_APNS_KEY_ID", "")
APNS_TEAM_ID: str = os.environ.get("APEX_APNS_TEAM_ID", "")
APNS_KEY_PATH: str = os.environ.get("APEX_APNS_KEY_PATH", "")
APNS_BUNDLE_ID: str = os.environ.get("APEX_APNS_BUNDLE_ID", "com.apex.app.apexchat")
APNS_USE_SANDBOX: bool = (
    os.environ.get("APEX_APNS_SANDBOX", "1").lower() in {"1", "true", "yes"}
)

# ---------------------------------------------------------------------------
# Uploads / Whisper
# ---------------------------------------------------------------------------

WHISPER_BIN: str = os.environ.get(
    "APEX_WHISPER_BIN", shutil.which("whisper") or "whisper"
)

# ---------------------------------------------------------------------------
# Storage names — override to run multiple instances side by side
# ---------------------------------------------------------------------------

DB_NAME: str = os.environ.get("APEX_DB_NAME", "apex.db")
LOG_NAME: str = os.environ.get("APEX_LOG_NAME", "apex.log")

# ---------------------------------------------------------------------------
# Alert client
# ---------------------------------------------------------------------------

# URL of the Apex server used by the alert client helper.
# Default to this process's port so dev/prod instances do not cross-post alerts.
SERVER_URL: str = os.environ.get("APEX_SERVER", f"https://localhost:{PORT}")

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.environ.get("TELEGRAM_CHAT_ID", "")

# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------

# Path to the .env file loaded at startup (env-only — dashboard reads this for
# the credential editor, and it varies per deployment).
ENV_FILE: Path = Path(
    os.environ.get("APEX_ENV_FILE", str(Path.home() / ".apex" / ".env"))
)

# Optional bearer token for defense-in-depth on /admin routes (mTLS is primary).
ADMIN_TOKEN: str = os.environ.get("APEX_ADMIN_TOKEN", "")

# mTLS mode: "required" (default) or "optional" (dev/Playwright — accepts but
# does not demand client certificates).
MTLS_MODE: str = os.environ.get("APEX_MTLS_MODE", "required").lower()

# ---------------------------------------------------------------------------
# Licensing
# ---------------------------------------------------------------------------

LICENSE_SERVER_URL: str = os.environ.get(
    "APEX_LICENSE_SERVER",
    "https://ash-licensing-service-990524419393.us-central1.run.app/api/v1/license/refresh",
)
