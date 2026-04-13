"""Apex Server configuration manager.

Reads from state/config.json, merges with environment variables.
Config.json values take precedence over env vars when present.
Secrets stay in .env — config stores only boolean flags for them.
Atomic writes via temp file + rename.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Schema — every valid config key with type, default, env-var source
# ---------------------------------------------------------------------------

SCHEMA: dict[str, dict[str, dict[str, Any]]] = {
    "server": {
        "host": {
            "type": "str",
            "default": "0.0.0.0",
            "env": "APEX_HOST",
            "description": "Listen address",
        },
        "port": {
            "type": "int",
            "default": 8300,
            "env": "APEX_PORT",
            "description": "Listen port",
        },
        "debug": {
            "type": "bool",
            "default": False,
            "env": "APEX_DEBUG",
            "description": "Enable verbose debug logging",
        },
    },
    "models": {
        "default_model": {
            "type": "str",
            "default": "claude-sonnet-4-6",
            "env": "APEX_MODEL",
            "description": "Default AI model",
        },
        "permission_mode": {
            "type": "str",
            "default": "acceptEdits",
            "env": "APEX_PERMISSION_MODE",
            "description": "Claude SDK permission mode",
            "choices": ["acceptEdits", "bypassPermissions", "plan"],
        },
        "ollama_url": {
            "type": "str",
            "default": "http://localhost:11434",
            "env": "APEX_OLLAMA_URL",
            "description": "Ollama API base URL",
        },
        "mlx_url": {
            "type": "str",
            "default": "http://localhost:8400",
            "env": "APEX_MLX_URL",
            "description": "MLX model server base URL",
        },
        "compaction_threshold": {
            "type": "int",
            "default": 100_000,
            "env": "APEX_COMPACTION_THRESHOLD",
            "description": "Input tokens before auto-compaction",
            "min": 10_000,
            "max": 2_000_000,
        },
        "compaction_model": {
            "type": "str",
            "default": "grok-4-1-fast-non-reasoning",
            "env": "APEX_COMPACTION_MODEL",
            "description": "Primary model for recovery/compaction (xAI or Ollama)",
        },
        "compaction_ollama_fallback": {
            "type": "str",
            "default": "gemma3:27b",
            "env": "APEX_COMPACTION_OLLAMA_FALLBACK",
            "description": "Ollama fallback model if primary (xAI) fails",
        },
        "sdk_query_timeout": {
            "type": "int",
            "default": 30,
            "env": "APEX_SDK_QUERY_TIMEOUT",
            "description": "SDK query timeout (seconds)",
            "min": 5,
            "max": 120,
        },
        "sdk_stream_timeout": {
            "type": "int",
            "default": 300,
            "env": "APEX_SDK_STREAM_TIMEOUT",
            "description": "SDK streaming timeout (seconds)",
            "min": 30,
            "max": 900,
        },
        "enable_skill_dispatch": {
            "type": "bool",
            "default": True,
            "env": "APEX_ENABLE_SKILL_DISPATCH",
            "description": "Server-side /recall, /codex, /grok dispatch",
        },
        "max_turns": {
            "type": "int",
            "default": 50,
            "description": "Max SDK turns per query",
            "min": 1,
            "max": 200,
        },
        "max_tool_iterations": {
            "type": "int",
            "default": 50,
            "description": "Max tool-loop iterations for Ollama/xAI/Codex/MLX models",
            "min": 5,
            "max": 200,
            "env": "APEX_MAX_TOOL_ITERATIONS",
        },
    },
    "workspace": {
        "path": {
            "type": "str",
            "default": "",
            "env": "APEX_WORKSPACE",
            "description": "Agent workspace directories",
            "multiline": True,
            "placeholder": "/Users/you/project-a\n/Users/you/project-b",
        },
        "enable_whisper": {
            "type": "bool",
            "default": False,
            "env": "APEX_ENABLE_WHISPER",
            "description": "Enable audio transcription via Whisper",
        },
    },
    "history": {
        "transcript_dirs": {
            "type": "str",
            "default": "",
            "description": "Comma-separated paths to transcript directories for embedding",
        },
        "embedding_backend": {
            "type": "str",
            "default": "",
            "description": "Embedding backend: ollama, gemini, or empty (disabled)",
            "choices": ["", "ollama", "gemini"],
        },
        "sources_discovered": {
            "type": "str",
            "default": "",
            "description": "JSON-encoded sources found during setup (read-only reference)",
        },
    },
    "policy": {
        "workspace_tools": {
            "type": "str",
            "default": "",
            "description": "Normalized tool ids allowed at level 2 (Workspace + Browser), one per line",
            "multiline": True,
            "placeholder": "bash\nread_file\nwrite_file\nplaywright__*\nfetch__*",
        },
        "never_allowed_commands": {
            "type": "str",
            "default": "",
            "description": "Shell command prefixes blocked at every level, one per line",
            "multiline": True,
            "placeholder": "sqlite3\nrm -rf\nlaunchctl",
        },
        "blocked_path_prefixes": {
            "type": "str",
            "default": "",
            "description": "Path prefixes blocked at every level, one per line",
            "multiline": True,
            "placeholder": "/Users/you/project/state\n/Users/you/.ssh",
        },
    },
    "alerts": {
        "telegram_configured": {
            "type": "bool",
            "default": False,
            "readonly": True,
            "description": "Whether TELEGRAM_BOT_TOKEN is set",
        },
        "alert_token_configured": {
            "type": "bool",
            "default": False,
            "readonly": True,
            "description": "Whether APEX_ALERT_TOKEN is set",
        },
        "xai_configured": {
            "type": "bool",
            "default": False,
            "readonly": True,
            "description": "Whether XAI_API_KEY is set",
        },
        "openai_configured": {
            "type": "bool",
            "default": False,
            "readonly": True,
            "description": "Whether OPENAI_API_KEY is set",
        },
        "deepseek_configured": {
            "type": "bool",
            "default": False,
            "readonly": True,
            "description": "Whether DEEPSEEK_API_KEY is set",
        },
        "zhipu_configured": {
            "type": "bool",
            "default": False,
            "readonly": True,
            "description": "Whether ZHIPU_API_KEY is set",
        },
        "google_configured": {
            "type": "bool",
            "default": False,
            "readonly": True,
            "description": "Whether GOOGLE_API_KEY is set",
        },
    },
    "usage": {
        "budget_usd": {
            "type": "int",
            "default": 100,
            "description": "Monthly API budget target in USD",
            "min": 0,
            "max": 100000,
        },
        "alert_pct": {
            "type": "int",
            "default": 80,
            "description": "Budget alert threshold percentage",
            "min": 1,
            "max": 100,
        },
        "reset_day": {
            "type": "int",
            "default": 1,
            "description": "Calendar day of month when the usage budget resets",
            "min": 1,
            "max": 28,
        },
        "primary_user_label": {
            "type": "str",
            "default": "Dana",
            "description": "Display label for interactive usage in the admin usage report",
        },
    },
}

# Sections that require a server restart when changed
RESTART_REQUIRED_SECTIONS = {"server"}


# ---------------------------------------------------------------------------
# Config class
# ---------------------------------------------------------------------------

class Config:
    """Thread-safe configuration manager with file persistence."""

    def __init__(self, state_dir: Path | str) -> None:
        self._state_dir = Path(state_dir)
        self._path = self._state_dir / "config.json"
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = {}
        self.load()

    # -- persistence --------------------------------------------------------

    def load(self) -> None:
        """Load config.json, merging with env vars and schema defaults."""
        file_data: dict[str, dict[str, Any]] = {}
        if self._path.exists():
            try:
                file_data = json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                file_data = {}

        merged: dict[str, dict[str, Any]] = {}
        for section, keys in SCHEMA.items():
            merged[section] = {}
            for key, spec in keys.items():
                # Priority: config.json > env var > schema default
                if section in file_data and key in file_data[section]:
                    raw = file_data[section][key]
                elif spec.get("readonly"):
                    # Readonly fields are computed, not stored
                    raw = self._compute_readonly(key)
                elif "env" in spec and os.environ.get(spec["env"]):
                    raw = os.environ[spec["env"]]
                else:
                    raw = spec["default"]

                merged[section][key] = self._coerce(raw, spec)

        with self._lock:
            self._data = merged

    def save(self) -> None:
        """Persist config to state/config.json (atomic write).

        Readonly fields are excluded — they're computed at load time.
        """
        self._state_dir.mkdir(parents=True, exist_ok=True)
        # Strip readonly keys before saving
        saveable: dict[str, dict[str, Any]] = {}
        for section, keys in SCHEMA.items():
            saveable[section] = {}
            for key, spec in keys.items():
                if spec.get("readonly"):
                    continue
                saveable[section][key] = self._data.get(section, {}).get(key, spec["default"])

        fd, tmp = tempfile.mkstemp(
            dir=str(self._state_dir), suffix=".tmp", prefix="config_"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(saveable, f, indent=2)
                f.write("\n")
            os.replace(tmp, str(self._path))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # -- read/write ---------------------------------------------------------

    def get_all(self) -> dict[str, dict[str, Any]]:
        """Return full config with readonly fields recomputed."""
        with self._lock:
            out = json.loads(json.dumps(self._data))
        # Refresh readonly
        for section, keys in SCHEMA.items():
            for key, spec in keys.items():
                if spec.get("readonly"):
                    out.setdefault(section, {})[key] = self._compute_readonly(key)
        return out

    def get_section(self, section: str) -> dict[str, Any]:
        """Return a single config section."""
        all_cfg = self.get_all()
        if section not in SCHEMA:
            raise KeyError(f"Unknown section: {section}")
        return all_cfg.get(section, {})

    def get(self, section: str, key: str) -> Any:
        """Get a single config value."""
        return self.get_section(section).get(key)

    def update_section(
        self, section: str, updates: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        """Update a config section. Returns (new_values, restart_required).

        Raises ValueError on validation failure.
        """
        if section not in SCHEMA:
            raise KeyError(f"Unknown section: {section}")

        schema = SCHEMA[section]
        validated: dict[str, Any] = {}

        for key, value in updates.items():
            if key not in schema:
                raise ValueError(f"Unknown key: {section}.{key}")
            spec = schema[key]
            if spec.get("readonly"):
                raise ValueError(f"Key {section}.{key} is read-only")
            validated[key] = self._validate(key, value, spec)

        with self._lock:
            if section not in self._data:
                self._data[section] = {}
            self._data[section].update(validated)

        self.save()
        restart = section in RESTART_REQUIRED_SECTIONS
        return self.get_section(section), restart

    # -- schema introspection -----------------------------------------------

    @staticmethod
    def get_schema() -> dict[str, dict[str, dict[str, Any]]]:
        """Return the full schema for UI rendering."""
        return SCHEMA

    # -- validation helpers -------------------------------------------------

    @staticmethod
    def _coerce(raw: Any, spec: dict[str, Any]) -> Any:
        """Coerce raw value to the expected type."""
        target = spec["type"]
        try:
            if target == "int":
                return int(raw)
            if target == "bool":
                if isinstance(raw, str):
                    return raw.lower() in {"1", "true", "yes"}
                return bool(raw)
            return str(raw)
        except (ValueError, TypeError):
            return spec["default"]

    @staticmethod
    def _validate(key: str, value: Any, spec: dict[str, Any]) -> Any:
        """Validate and coerce a value against its spec. Raises ValueError."""
        target = spec["type"]
        try:
            if target == "int":
                value = int(value)
                if "min" in spec and value < spec["min"]:
                    raise ValueError(
                        f"{key}: must be >= {spec['min']}, got {value}"
                    )
                if "max" in spec and value > spec["max"]:
                    raise ValueError(
                        f"{key}: must be <= {spec['max']}, got {value}"
                    )
            elif target == "bool":
                if isinstance(value, str):
                    value = value.lower() in {"1", "true", "yes"}
                else:
                    value = bool(value)
            else:
                value = str(value)
                allowed_controls = {' ', '\t'}
                if spec.get("multiline"):
                    allowed_controls.update({'\n', '\r'})
                if any(ord(c) < 32 and c not in allowed_controls for c in value):
                    raise ValueError(f"{key}: contains control characters")
        except (ValueError, TypeError) as e:
            raise ValueError(f"{key}: invalid {target} value: {e}") from e

        if "choices" in spec and value not in spec["choices"]:
            raise ValueError(
                f"{key}: must be one of {spec['choices']}, got {value!r}"
            )

        # URL validation for ollama_url
        if key == "ollama_url" and isinstance(value, str):
            parsed = urlparse(value)
            if parsed.scheme not in ("http", "https"):
                raise ValueError(f"{key}: scheme must be http or https")
            if not parsed.hostname:
                raise ValueError(f"{key}: missing hostname")

        return value

    @staticmethod
    def _compute_readonly(key: str) -> bool:
        """Compute runtime-only values (secret presence flags)."""
        if key == "telegram_configured":
            return bool(os.environ.get("TELEGRAM_BOT_TOKEN"))
        if key == "alert_token_configured":
            return bool(os.environ.get("APEX_ALERT_TOKEN"))
        if key == "xai_configured":
            return bool(os.environ.get("XAI_API_KEY"))
        if key == "openai_configured":
            return bool(os.environ.get("OPENAI_API_KEY"))
        if key == "deepseek_configured":
            return bool(os.environ.get("DEEPSEEK_API_KEY"))
        if key == "zhipu_configured":
            return bool(os.environ.get("ZHIPU_API_KEY"))
        if key == "google_configured":
            return bool(os.environ.get("GOOGLE_API_KEY"))
        return False
