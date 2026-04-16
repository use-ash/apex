"""Subconscious memory system configuration.

Path resolution order:
  1. APEX_WORKSPACE env var (explicit override)
  2. Apex server config.json workspace.path (first entry if colon-separated)
  3. Relative to this file: ../../  (scripts/subconscious/ → workspace root)
"""

import json
import os
import re
from pathlib import Path


def _resolve_workspace() -> str:
    """Resolve workspace root without hardcoding any user path."""
    # 1. Explicit env override (highest priority)
    env = os.environ.get("APEX_WORKSPACE")
    if env and os.path.isdir(env):
        return env

    # 2. Read from Apex server config.json
    #    Look in known relative locations from this file
    this_dir = Path(__file__).resolve().parent  # scripts/subconscious/
    candidates = [
        this_dir.parents[2] / "apex" / "state" / "config.json",   # workspace/../apex/state/
        this_dir.parents[1] / "state" / "config.json",            # workspace/state/ (if scripts live in apex)
        Path.home() / ".apex" / "state" / "config.json",          # ~/.apex/state/
    ]
    for cfg_path in candidates:
        if cfg_path.exists():
            try:
                with open(cfg_path) as f:
                    cfg = json.load(f)
                ws_path = cfg.get("workspace", {}).get("path", "")
                if ws_path:
                    # config.json may have colon-separated multi-paths; take first
                    first = ws_path.split(":")[0].strip()
                    if os.path.isdir(first):
                        return first
            except (json.JSONDecodeError, OSError):
                continue

    # 3. Relative fallback: this file lives at <workspace>/scripts/subconscious/config.py
    fallback = str(this_dir.parents[1])
    if os.path.isdir(fallback):
        return fallback

    # Last resort (should never reach here in practice)
    return str(Path.home() / ".openclaw" / "workspace")


WORKSPACE = _resolve_workspace()
STATE_DIR = os.path.join(WORKSPACE, ".subconscious")
SESSIONS_DIR = os.path.join(STATE_DIR, "sessions")
DIGESTS_DIR = os.path.join(STATE_DIR, "digests")
GUIDANCE_FILE = os.path.join(STATE_DIR, "guidance.json")
LOCK_FILE = os.path.join(STATE_DIR, ".lock")

# ── Ollama ─────────────────────────────────────────────────────────
# gemma4:26b — Gemma 4 26B MoE (4B active), 17GB
# Fastest extraction model tested (12.1s total for both tasks).
# MUST use /api/chat endpoint — /api/generate leaks thinking tokens despite think=False.
# Must pass think=False + system message for clean JSON output.
OLLAMA_MODEL = "gemma4:26b"
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TIMEOUT = 120  # 60s was too tight for big prompts; chunks use their own timeout
OLLAMA_OPTIONS = {"num_predict": 1024, "temperature": 0.1, "repeat_penalty": 1.3}

# ── Guidance limits ────────────────────────────────────────────────
GUIDANCE_MAX_CHARS = 32000  # was 4000→20000→32000; 27 items = ~29K chars
GUIDANCE_MAX_AGE_DAYS = 7

# ── MemCollab invariants ──────────────────────────────────────────
INVARIANT_CONFIDENCE_THRESHOLD = 0.75
INVARIANT_TTL_DAYS = 30
INVARIANT_MAX_PER_SESSION = 3
OLLAMA_VALIDATION_MODEL = "gemma4:26b"
OLLAMA_VALIDATION_TIMEOUT = 30

# ── Type 1 / Type 2 pathway thresholds ─────────────────────────────
TYPE1_MAX_ITEMS = 10           # max invariants injected per turn
TYPE1_MAX_CHARS = 2000         # hard char budget for Type 1 block
TYPE2_MAX_CHARS = 4000         # hard char budget for Type 2 block
PROMOTION_MIN_INJECTIONS = 20  # minimum times injected before eligible
PROMOTION_MIN_HIT_RATE = 0.60  # minimum usefulness rate for promotion

# ── Contradiction detection ────────────────────────────────────────
CONTRADICTION_SIMILARITY_THRESHOLD = 0.45  # items about the same topic
PENDING_REVIEW_FILE = os.path.join(STATE_DIR, "pending_review.json")
OVERRIDES_FILE = os.path.join(STATE_DIR, "overrides.json")

# ── Secret patterns ────────────────────────────────────────────────
_SECRET_PATTERNS = [
    re.compile(r'(?<=[=\s:"\'])(?:[A-Za-z0-9+/]{40,}={0,2})'),
    re.compile(r'[Bb]earer\s+[A-Za-z0-9._\-]+'),
    re.compile(r'(?:api[_-]?key|token|secret|password)\s*[=:]\s*\S+', re.IGNORECASE),
]


def ensure_dirs() -> None:
    for d in (STATE_DIR, SESSIONS_DIR, DIGESTS_DIR):
        os.makedirs(d, exist_ok=True)

    gitignore = Path(WORKSPACE) / ".gitignore"
    marker = ".subconscious/"
    if gitignore.exists():
        content = gitignore.read_text()
        if marker not in content:
            with open(gitignore, "a") as f:
                f.write(f"\n{marker}\n")
    else:
        gitignore.write_text(f"{marker}\n")


def redact_secrets(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text
