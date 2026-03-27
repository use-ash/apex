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
            "env": "LOCALCHAT_HOST",
            "description": "Listen address",
        },
        "port": {
            "type": "int",
            "default": 8300,
            "env": "LOCALCHAT_PORT",
            "description": "Listen port",
        },
        "debug": {
            "type": "bool",
            "default": False,
            "env": "LOCALCHAT_DEBUG",
            "description": "Enable verbose debug logging",
        },
    },
    "models": {
        "default_model": {
            "type": "str",
            "default": "claude-sonnet-4-6",
            "env": "LOCALCHAT_MODEL",
            "description": "Default AI model",
            "choices": [
                "claude-opus-4-6",
                "claude-sonnet-4-6",
                "claude-haiku-4-5-20251001",
                "grok-4",
                "grok-4-fast",
            ],
        },
        "permission_mode": {
            "type": "str",
            "default": "acceptEdits",
            "env": "LOCALCHAT_PERMISSION_MODE",
            "description": "Claude SDK permission mode",
            "choices": ["acceptEdits", "bypassPermissions", "plan"],
        },
        "ollama_url": {
            "type": "str",
            "default": "http://localhost:11434",
            "env": "LOCALCHAT_OLLAMA_URL",
            "description": "Ollama API base URL",
        },
        "compaction_threshold": {
            "type": "int",
            "default": 100_000,
            "env": "LOCALCHAT_COMPACTION_THRESHOLD",
            "description": "Input tokens before auto-compaction",
            "min": 10_000,
            "max": 2_000_000,
        },
        "compaction_model": {
            "type": "str",
            "default": "gemma3:27b",
            "env": "LOCALCHAT_COMPACTION_MODEL",
            "description": "Ollama model for compaction summaries",
        },
        "max_turns": {
            "type": "int",
            "default": 50,
            "description": "Max SDK turns per query",
            "min": 1,
            "max": 200,
        },
    },
    "workspace": {
        "path": {
            "type": "str",
            "default": "",
            "env": "LOCALCHAT_WORKSPACE",
            "description": "Agent workspace directory",
        },
        "enable_whisper": {
            "type": "bool",
            "default": False,
            "env": "LOCALCHAT_ENABLE_WHISPER",
            "description": "Enable audio transcription via Whisper",
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
            "description": "Whether LOCALCHAT_ALERT_TOKEN is set",
        },
        "xai_configured": {
            "type": "bool",
            "default": False,
            "readonly": True,
            "description": "Whether XAI_API_KEY is set",
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
                if any(ord(c) < 32 and c not in (' ', '\t') for c in value):
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
            return bool(os.environ.get("LOCALCHAT_ALERT_TOKEN"))
        if key == "xai_configured":
            return bool(os.environ.get("XAI_API_KEY"))
        return False
