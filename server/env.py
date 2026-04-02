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

# ---------------------------------------------------------------------------
# Models & SDK
# ---------------------------------------------------------------------------

MODEL: str = os.environ.get("APEX_MODEL", "claude-sonnet-4-6")
PERMISSION_MODE: str = os.environ.get("APEX_PERMISSION_MODE", "acceptEdits")
SDK_QUERY_TIMEOUT: int = int(os.environ.get("APEX_SDK_QUERY_TIMEOUT", "30"))
SDK_STREAM_TIMEOUT: int = int(os.environ.get("APEX_SDK_STREAM_TIMEOUT", "300"))
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

# ---------------------------------------------------------------------------
# Licensing
# ---------------------------------------------------------------------------

LICENSE_SERVER_URL: str = os.environ.get(
    "APEX_LICENSE_SERVER",
    "https://ash-licensing-service-990524419393.us-central1.run.app/api/v1/license/refresh",
)
