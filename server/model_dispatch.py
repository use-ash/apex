"""Model backend routing — Ollama, MLX, Claude, Grok, Codex.

Layer 1: depends only on log.py (Layer 0).
"""
from __future__ import annotations

import json
import urllib.request

import env
from log import log

# ---------------------------------------------------------------------------
# Remote / local base URLs
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = env.OLLAMA_URL
MLX_BASE_URL = env.MLX_URL

# ---------------------------------------------------------------------------
# Model context window sizes (input tokens)
# ---------------------------------------------------------------------------
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus-4-6": 1_000_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "grok-4": 2_000_000,
    "grok-4-fast": 2_000_000,
    "mlx:mlx-community/Qwen3.5-35B-A3B-4bit": 128_000,
    "codex:gpt-5.4": 272_000,
    "codex:gpt-5.4-mini": 272_000,
    "codex:o3": 200_000,
    "codex:o4-mini": 200_000,
    "codex:gpt-5.3-codex": 272_000,
    "codex:gpt-5.2": 272_000,
    "codex:gpt-5.1-codex-max": 272_000,
}
MODEL_CONTEXT_DEFAULT = 128_000  # fallback for local/unknown models

# ---------------------------------------------------------------------------
# Remote model catalogue (drives the model picker UI)
# ---------------------------------------------------------------------------
REMOTE_MODEL_OPTIONS = [
    {"id": "claude-opus-4-6",       "displayName": "Claude Opus 4.6",  "provider": "anthropic", "local": False},
    {"id": "claude-sonnet-4-6",     "displayName": "Claude Sonnet 4.6","provider": "anthropic", "local": False},
    {"id": "claude-haiku-4-5-20251001", "displayName": "Claude Haiku 4.5", "provider": "anthropic", "local": False},
    {"id": "grok-4",                "displayName": "Grok 4",           "provider": "xai",       "local": False},
    {"id": "grok-4-fast",           "displayName": "Grok 4 Fast",      "provider": "xai",       "local": False},
    {"id": "codex:gpt-5.4",         "displayName": "GPT-5.4",          "provider": "openai",    "local": False},
    {"id": "codex:gpt-5.4-mini",    "displayName": "GPT-5.4 Mini",     "provider": "openai",    "local": False},
    {"id": "codex:o3",              "displayName": "o3 (API key)",      "provider": "openai",    "local": False},
    {"id": "codex:o4-mini",         "displayName": "o4-mini (API key)", "provider": "openai",    "local": False},
    {"id": "codex:gpt-5.3-codex",   "displayName": "GPT-5.3",          "provider": "openai",    "local": False},
    {"id": "codex:gpt-5.2",         "displayName": "GPT-5.2",          "provider": "openai",    "local": False},
    {"id": "codex:gpt-5.1-codex-max","displayName": "GPT-5.1 Max",     "provider": "openai",    "local": False},
]


# ---------------------------------------------------------------------------
# Backend routing
# ---------------------------------------------------------------------------

def _is_local_model(model: str) -> bool:
    """True if the model should be routed through Ollama instead of Claude SDK."""
    return not model.startswith("claude-")


def _get_model_backend(model: str) -> str:
    """Determine which backend to use for a model."""
    if model.startswith("codex:"):
        return "codex"
    elif model.startswith("claude-"):
        return "claude"
    elif model.startswith("grok-"):
        return "xai"
    elif model.startswith("mlx:"):
        return "mlx"
    else:
        return "ollama"


def _get_ollama_models() -> list[dict]:
    """Query Ollama for available local models."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            size_gb = round(m.get("size", 0) / 1e9, 1)
            models.append({"id": name, "displayName": name, "sizeGb": size_gb, "local": True})
        return models
    except Exception as e:
        log(f"ollama model list failed: {e}")
        return []


def _get_mlx_models() -> list[dict]:
    """Query MLX server for available models."""
    try:
        req = urllib.request.Request(
            f"{MLX_BASE_URL}/v1/models",
            headers={"User-Agent": "Apex/1.0"},
        )
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        models = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            models.append({
                "id": f"mlx:{mid}",
                "displayName": mid.split("/")[-1] if "/" in mid else mid,
                "sizeGb": 0,
                "local": True,
            })
        return models
    except Exception as e:
        log(f"mlx model list failed: {e}")
        return []


def get_available_model_ids() -> set[str]:
    """Return the live allowlist of valid model identifiers."""
    ids = {item["id"] for item in REMOTE_MODEL_OPTIONS if item.get("id")}
    ids.add(env.MODEL)
    for loader in (_get_ollama_models, _get_mlx_models):
        try:
            ids.update(model.get("id", "") for model in loader() if model.get("id"))
        except Exception as e:
            log(f"model allowlist refresh failed: {e}")
    return {mid for mid in ids if mid}
