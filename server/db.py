"""Apex SQLite data access layer.

Pure CRUD operations — no business logic, no prompt building.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from state import _db_lock, _last_compacted_at
from compat import safe_chmod
from log import log
from env import APEX_ROOT, DB_NAME
from model_dispatch import _get_model_backend

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
DB_PATH = APEX_ROOT / "state" / DB_NAME

SYSTEM_PROFILE_ID = "_system"
SYSTEM_PROFILE_NAME = "Open"
SYSTEM_PROFILE_SLUG = "open"

_CHAT_UPDATE_FIELDS = frozenset({"title", "model", "profile_id", "claude_session_id", "category", "type"})
DEFAULT_TOOL_POLICY_LEVEL = 1
LEGACY_TOOL_POLICY_LEVEL = 2
MIN_TOOL_POLICY_LEVEL = 0
MAX_TOOL_POLICY_LEVEL = 4
_VALID_INVOKE_POLICIES = frozenset({"anyone", "owner_only"})

# ---------------------------------------------------------------------------
# Alert category mapping
# ---------------------------------------------------------------------------
_DEFAULT_ALERT_CATEGORIES = {
    "guardrail": "system",
    "watchdog": "system",
    "system": "system",
    "test": "test",
    "custom": "custom",
}


def _load_alert_category_map() -> dict[str, str]:
    merged = dict(_DEFAULT_ALERT_CATEGORIES)
    try:
        cfg_path = APEX_ROOT / "state" / "config.json"
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text())
            custom = data.get("alert_categories", {})
            if isinstance(custom, dict):
                merged.update(custom)
    except Exception:
        pass
    return merged


ALERT_CATEGORY_MAP = _load_alert_category_map()


def _alert_category(source: str) -> str:
    """Map an alert source to its category."""
    return ALERT_CATEGORY_MAP.get(source, "other")


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _coerce_tool_policy_level(
    value: object,
    *,
    default: int = DEFAULT_TOOL_POLICY_LEVEL,
) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return default
    return max(MIN_TOOL_POLICY_LEVEL, min(MAX_TOOL_POLICY_LEVEL, level))


def _normalize_tool_policy_timestamp(value: object) -> str | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _normalize_allowed_commands(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        command = " ".join(item.strip().split())
        if not command or command in seen:
            continue
        seen.add(command)
        normalized.append(command)
    return normalized


def _normalize_tool_policy(
    raw: str | dict | None,
    *,
    default_level: int = DEFAULT_TOOL_POLICY_LEVEL,
) -> dict:
    default_level = _coerce_tool_policy_level(default_level, default=DEFAULT_TOOL_POLICY_LEVEL)
    if isinstance(raw, dict):
        policy = dict(raw)
    elif raw in (None, ""):
        policy = {}
    else:
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            policy = {}
        else:
            policy = dict(parsed) if isinstance(parsed, dict) else {}
    level = _coerce_tool_policy_level(policy.get("level", default_level), default=default_level)
    normalized = {
        "level": level,
        "default_level": _coerce_tool_policy_level(policy.get("default_level", level), default=level),
        "elevated_until": _normalize_tool_policy_timestamp(policy.get("elevated_until")),
        "invoke_policy": str(policy.get("invoke_policy") or "anyone").strip().lower(),
        "allowed_commands": _normalize_allowed_commands(policy.get("allowed_commands")),
    }
    if normalized["invoke_policy"] not in _VALID_INVOKE_POLICIES:
        normalized["invoke_policy"] = "anyone"

    workspace = policy.get("workspace")
    if isinstance(workspace, str) and workspace.strip():
        normalized["workspace"] = workspace.strip()
    sandbox = policy.get("sandbox")
    if isinstance(sandbox, str) and sandbox.strip():
        normalized["sandbox"] = sandbox.strip()
    return normalized


def _normalize_tool_policy_text(
    raw: str | dict | None,
    *,
    default_level: int = DEFAULT_TOOL_POLICY_LEVEL,
) -> str:
    return json.dumps(
        _normalize_tool_policy(raw, default_level=default_level),
        separators=(",", ":"),
    )


def _tool_policy_level(raw: str | dict | None) -> int:
    return _normalize_tool_policy(raw)["level"]


def _migrate_tool_policy_levels(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT id, tool_policy FROM agent_profiles").fetchall()
    updates: list[tuple[str, str, str]] = []
    for profile_id, raw in rows:
        raw_text = raw or ""
        normalized = _normalize_tool_policy_text(raw_text, default_level=LEGACY_TOOL_POLICY_LEVEL)
        if raw_text != normalized:
            updates.append((normalized, _now(), profile_id))
    if updates:
        conn.executemany(
            "UPDATE agent_profiles SET tool_policy = ?, updated_at = ? WHERE id = ?",
            updates,
        )


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    safe_chmod(DB_PATH.parent, 0o700)
    conn = _get_db()
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
            attachments TEXT DEFAULT '[]',
            duration_ms INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            acked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        DROP TABLE IF EXISTS web_sessions;
        CREATE TABLE IF NOT EXISTS agent_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            avatar TEXT DEFAULT '',
            role_description TEXT DEFAULT '',
            backend TEXT DEFAULT '',
            model TEXT DEFAULT '',
            system_prompt TEXT NOT NULL DEFAULT '',
            system_prompt_override TEXT DEFAULT NULL,
            tool_policy TEXT DEFAULT '',
            is_default INTEGER DEFAULT 0,
            is_system INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    # Migration: add model and type columns if missing
    for col, default in [("model", "NULL"), ("type", "'chat'")]:
        try:
            conn.execute(f"ALTER TABLE chats ADD COLUMN {col} TEXT DEFAULT {default}")
        except Exception:
            pass
    # Migration: add metadata column to alerts if missing
    try:
        conn.execute("ALTER TABLE alerts ADD COLUMN metadata TEXT DEFAULT '{}'")
    except Exception:
        pass
    # Migration: add category column to chats (for alerts channel filtering)
    try:
        conn.execute("ALTER TABLE chats ADD COLUMN category TEXT DEFAULT NULL")
    except Exception:
        pass
    # Migration: add profile_id column to chats (for agent profiles)
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE chats ADD COLUMN profile_id TEXT DEFAULT ''")
    # Migration: add is_system column to agent_profiles (two-tier persona system)
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE agent_profiles ADD COLUMN is_system INTEGER NOT NULL DEFAULT 0")
    # Migration: add system_prompt_override column to agent_profiles
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE agent_profiles ADD COLUMN system_prompt_override TEXT DEFAULT NULL")
    _migrate_tool_policy_levels(conn)
    # Migration: channel_agent_memberships table (groups foundation)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS channel_agent_memberships (
            id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            agent_profile_id TEXT NOT NULL REFERENCES agent_profiles(id),
            routing_mode TEXT NOT NULL DEFAULT 'mentioned',
            is_primary INTEGER NOT NULL DEFAULT 0,
            display_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(channel_id, agent_profile_id)
        )
    """)
    # Migration: speaker identity columns on messages (groups)
    for col in ["speaker_id", "speaker_name", "speaker_avatar", "visibility", "group_turn_id"]:
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(f"ALTER TABLE messages ADD COLUMN {col} TEXT DEFAULT ''")
    # Migration: structured attachment refs on messages
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE messages ADD COLUMN attachments TEXT DEFAULT '[]'")
    # Migration: turn wall-clock duration
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE messages ADD COLUMN duration_ms INTEGER DEFAULT 0")
    # Migration: canceled flag for partial results saved on stop/compaction
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE messages ADD COLUMN canceled INTEGER DEFAULT 0")
    # Migration: add role column to channel_agent_memberships (owner/member)
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE channel_agent_memberships ADD COLUMN role TEXT DEFAULT 'member'")
    # Migration: add status column to channel_agent_memberships (soft-delete)
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE channel_agent_memberships ADD COLUMN status TEXT DEFAULT 'active'")
    # Migration: add settings JSON column to chats (group settings, premium flags, etc.)
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE chats ADD COLUMN settings TEXT DEFAULT '{}'")
    # Migration: persona_memories table (cross-group persistent memory for agents)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS persona_memories (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL REFERENCES agent_profiles(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'decision',
            source_chat_id TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    # Migration: scoring columns for persona_memories
    for col_sql in [
        "ALTER TABLE persona_memories ADD COLUMN access_count INTEGER DEFAULT 0",
        "ALTER TABLE persona_memories ADD COLUMN last_accessed_at TEXT DEFAULT ''",
        "ALTER TABLE persona_memories ADD COLUMN violation_count INTEGER DEFAULT 0",
        "ALTER TABLE persona_memories ADD COLUMN token_count INTEGER DEFAULT 0",
    ]:
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(col_sql)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_persona_memories_profile ON persona_memories(profile_id)")
    # Per-persona model overrides (runtime, cleared on restart if desired)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS persona_model_overrides (
            profile_id TEXT PRIMARY KEY REFERENCES agent_profiles(id) ON DELETE CASCADE,
            model TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
    """)
    # System-level key-value metadata (trial tracking, license state)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS apex_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    # APNs device tokens for push notifications
    conn.execute("""
        CREATE TABLE IF NOT EXISTS device_tokens (
            id TEXT PRIMARY KEY,
            token TEXT NOT NULL UNIQUE,
            platform TEXT DEFAULT 'ios',
            label TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            last_seen TEXT NOT NULL
        )
    """)
    # Migration: permission change audit log
    conn.execute("""
        CREATE TABLE IF NOT EXISTS permission_audit_log (
            id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            old_level INTEGER,
            new_level INTEGER,
            elevated_until TEXT DEFAULT NULL,
            changed_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_perm_audit_chat ON permission_audit_log(chat_id)")
    conn.commit()
    conn.close()


def _seed_default_profiles():
    """Seed system profile + optional persona templates from persona_templates.json."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT OR IGNORE INTO agent_profiles (id, name, slug, avatar, role_description, backend, model, system_prompt, tool_policy, is_default, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                SYSTEM_PROFILE_ID,
                SYSTEM_PROFILE_NAME,
                SYSTEM_PROFILE_SLUG,
                "\U0001f4ac",
                "Open model chat shared memory pool",
                "",
                "",
                "",
                _normalize_tool_policy_text("", default_level=LEGACY_TOOL_POLICY_LEVEL),
                0,
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()

    # Check if persona template seeding is enabled in config (default: true)
    try:
        cfg_path = APEX_ROOT / "state" / "config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text())
            if not cfg.get("seed_default_profiles", True):
                return
    except Exception:
        return

    # Load templates
    templates_path = Path(__file__).resolve().parent / "persona_templates.json"
    if not templates_path.exists():
        return
    try:
        profiles = json.loads(templates_path.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"Failed to load persona templates: {e}")
        return

    with _db_lock:
        conn = _get_db()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        inserted = 0
        for p in profiles:
            cur = conn.execute(
                "INSERT OR IGNORE INTO agent_profiles (id, name, slug, avatar, role_description, "
                "backend, model, system_prompt, tool_policy, is_default, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (p["id"], p["name"], p["slug"], p["avatar"], p["role_description"],
                 p["backend"], p["model"], p["system_prompt"],
                 _normalize_tool_policy_text("", default_level=LEGACY_TOOL_POLICY_LEVEL),
                 p.get("is_default", 0), now, now),
            )
            inserted += cur.rowcount
        conn.commit()
        conn.close()
        if inserted:
            log(f"Seeded {inserted} agent profiles from templates")


import hashlib as _hashlib
import base64 as _base64

# ---------------------------------------------------------------------------
# Encrypted system prompts — decrypted at runtime, never stored in plaintext
# ---------------------------------------------------------------------------

def _decrypt_guide_prompt() -> str:
    """Decrypt the Guide persona prompt from the encrypted blob on disk.

    Key derivation: PBKDF2-SHA256 with fixed passphrase + salt.
    The plaintext never exists in source code or on disk — only in memory.
    """
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    enc_path = Path(__file__).parent / "guide_prompt.enc"
    if not enc_path.exists():
        log("WARNING: guide_prompt.enc not found — Guide persona will have no prompt")
        return ""

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32,
        salt=b"apex-prompt-signing-2026", iterations=100_000,
    )
    key = _base64.urlsafe_b64encode(kdf.derive(b"apex.sys-guide.v1.canonical"))
    try:
        plaintext = Fernet(key).decrypt(enc_path.read_bytes()).decode("utf-8")
        return plaintext
    except Exception as e:
        log(f"WARNING: guide_prompt.enc decryption failed: {e}")
        return ""


_GUIDE_PROMPT = _decrypt_guide_prompt()

_GUIDE_PROMPT_REMOVED = "ENCRYPTED — see guide_prompt.enc"  # plaintext removed
# (old plaintext was here — 390 lines removed, now in guide_prompt.enc)

# Integrity digest — if the DB copy doesn't match, the server rejects it
# and falls back to this hardcoded canonical version.
_GUIDE_PROMPT_DIGEST = _hashlib.sha256(_GUIDE_PROMPT.encode("utf-8")).hexdigest()

# Map of system persona IDs to their canonical (signed) prompts.
# Used by verify_system_prompt() to detect DB tampering.
_SIGNED_PROMPTS: dict[str, tuple[str, str]] = {
    "sys-guide": (_GUIDE_PROMPT, _GUIDE_PROMPT_DIGEST),
}


def verify_system_prompt(profile_id: str, db_prompt: str) -> str:
    """Verify a system persona's prompt against its signed digest.

    Returns the canonical prompt if the DB copy has been tampered with,
    or the db_prompt if it matches. Logs a warning on mismatch.
    """
    if profile_id not in _SIGNED_PROMPTS:
        return db_prompt
    canonical, expected_digest = _SIGNED_PROMPTS[profile_id]
    actual_digest = _hashlib.sha256((db_prompt or "").encode("utf-8")).hexdigest()
    if actual_digest != expected_digest:
        log(f"SECURITY: system prompt integrity check FAILED for {profile_id} "
            f"(expected={expected_digest[:12]}… got={actual_digest[:12]}…) — using canonical prompt")
        return canonical
    return db_prompt


_SYSTEM_PERSONAS = [
    {
        "id": "sys-apex-assistant",
        "name": "Apex Assistant",
        "slug": "apex-assistant",
        "avatar": "\u2728",
        "role_description": "General-purpose assistant — questions, research, writing, analysis",
        "backend": "claude",
        "model": "claude-sonnet-4-6",
        "system_prompt": (
            "You are Apex Assistant, a helpful general-purpose AI assistant.\n\n"
            "You answer questions clearly and accurately, help with writing and research, "
            "analyze information, and assist with everyday tasks. You are direct, thoughtful, "
            "and honest about what you know and don't know.\n\n"
            "Communication style: Clear and concise. Match the user's register — "
            "casual for quick questions, thorough for complex ones. "
            "Always prioritize accuracy over speed."
        ),
        "tool_policy": "",
        "is_default": 1,
    },
    {
        "id": "sys-guide",
        "name": "Guide",
        "slug": "guide",
        "avatar": "\U0001f9ed",
        "role_description": "Apex platform expert — setup help, configuration, how things work",
        "backend": "claude",
        "model": "claude-haiku-4-5-20251001",
        "system_prompt": _GUIDE_PROMPT,
        "tool_policy": "",
        "is_default": 0,
    },
    {
        "id": "sys-code-expert",
        "name": "CodeExpert",
        "slug": "code-expert",
        "avatar": "\U0001f4bb",
        "role_description": "Technical specialist — code, debugging, architecture, engineering",
        "backend": "claude",
        "model": "claude-sonnet-4-6",
        "system_prompt": (
            "You are CodeExpert, a senior software engineer and technical specialist.\n\n"
            "You write production-quality code, debug issues methodically, design systems, "
            "and review implementations. You do not cut corners.\n\n"
            "Communication style: Lead with the solution, then explain your reasoning. "
            "Show full implementations — no pseudocode stubs. When you find a bug, report "
            "the exact file, line, expected vs actual behavior, and root cause. "
            "When requirements are ambiguous, ask before building the wrong thing.\n\n"
            "Principles:\n"
            "- Working code over clever code.\n"
            "- Test happy paths AND edge cases.\n"
            "- Name things clearly. Comments explain why, not what.\n"
            "- Understand root cause before patching symptoms.\n"
            "- Security is not optional.\n"
            "- Leave the codebase better than you found it."
        ),
        "tool_policy": "",
        "is_default": 0,
    },
]


def seed_system_personas() -> None:
    """Ensure system personas exist and have up-to-date prompt/avatar.

    Uses INSERT OR IGNORE to create new rows, then UPDATE to refresh
    system-controlled fields (name, avatar, role_description, system_prompt,
    backend, model, is_system) without overwriting user prompt overrides
    stored in system_prompt_override.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _db_lock:
        conn = _get_db()
        for p in _SYSTEM_PERSONAS:
            conn.execute(
                "INSERT OR IGNORE INTO agent_profiles "
                "(id, name, slug, avatar, role_description, backend, model, "
                "system_prompt, tool_policy, is_default, is_system, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (p["id"], p["name"], p["slug"], p["avatar"], p["role_description"],
                 p["backend"], p["model"], p["system_prompt"],
                 _normalize_tool_policy_text(p["tool_policy"], default_level=LEGACY_TOOL_POLICY_LEVEL),
                 p["is_default"], now, now),
            )
            conn.execute(
                "UPDATE agent_profiles SET "
                "name=?, avatar=?, role_description=?, backend=?, model=?, "
                "system_prompt=?, is_system=1, updated_at=? "
                "WHERE id=? AND (system_prompt_override IS NULL OR system_prompt_override = '')",
                (p["name"], p["avatar"], p["role_description"], p["backend"],
                 p["model"], p["system_prompt"], now, p["id"]),
            )
            # Always update model + backend + is_system (even if prompt is overridden)
            conn.execute(
                "UPDATE agent_profiles SET backend=?, model=?, is_system=1, updated_at=? WHERE id=?",
                (p["backend"], p["model"], now, p["id"]),
            )
        conn.commit()
        conn.close()
    log("System personas seeded/refreshed")


def _get_groups_using_persona(profile_id: str) -> list[str]:
    """Return list of group/channel titles that have this persona as a member."""
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT DISTINCT c.title FROM channel_agent_memberships m "
            "JOIN chats c ON m.channel_id = c.id "
            "WHERE m.agent_profile_id = ? AND COALESCE(m.status, 'active') = 'active' "
            "AND COALESCE(c.type, 'chat') = 'group'",
            (profile_id,),
        ).fetchall()
        conn.close()
    return [r[0] or "(untitled)" for r in rows]


def _is_known_profile_alias(candidate: str) -> bool:
    normalized = " ".join(str(candidate or "").split()).strip()
    if not normalized:
        return False
    folded = normalized.casefold()
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT id, name, slug FROM agent_profiles",
        ).fetchall()
        conn.close()
    for profile_id, name, slug in rows:
        aliases = [
            str(profile_id or "").strip(),
            str(name or "").strip(),
            str(slug or "").strip(),
        ]
        profile_text = str(profile_id or "").strip()
        slug_text = str(slug or "").strip()
        if profile_text:
            aliases.append(re.sub(r"[-_]+", " ", profile_text).strip())
        if slug_text:
            aliases.append(re.sub(r"[-_]+", " ", slug_text).strip())
        for alias in aliases:
            if alias and " ".join(alias.split()).casefold() == folded:
                return True
    return False


def _get_profile_tool_policy(profile_id: str | None) -> dict:
    if not profile_id:
        return _normalize_tool_policy(None)
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT tool_policy FROM agent_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        conn.close()
    return _normalize_tool_policy(row[0] if row else None)


def _get_chat_tool_policy(chat_id: str, profile_id: str | None = None) -> dict:
    if profile_id:
        return _get_profile_tool_policy(profile_id)
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT c.profile_id, c.settings, ap.tool_policy FROM chats c "
            "LEFT JOIN agent_profiles ap ON ap.id = c.profile_id "
            "WHERE c.id = ?",
            (chat_id,),
        ).fetchone()
        conn.close()
    if not row:
        return _normalize_tool_policy(None, default_level=LEGACY_TOOL_POLICY_LEVEL)
    profile_id = str(row[0] or "").strip()
    if not profile_id:
        settings_text = row[1] or ""
        try:
            settings = json.loads(settings_text) if settings_text else {}
        except (json.JSONDecodeError, TypeError):
            settings = {}
        return _normalize_tool_policy(settings.get("tool_policy"), default_level=LEGACY_TOOL_POLICY_LEVEL)
    return _normalize_tool_policy(row[2], default_level=DEFAULT_TOOL_POLICY_LEVEL)


def _set_chat_tool_policy(
    chat_id: str,
    raw: str | dict | None,
    *,
    default_level: int = LEGACY_TOOL_POLICY_LEVEL,
) -> dict:
    policy = _normalize_tool_policy(raw, default_level=default_level)
    settings = _get_chat_settings(chat_id)
    settings["tool_policy"] = policy
    with _db_lock:
        conn = _get_db()
        cur = conn.execute(
            "UPDATE chats SET settings = ?, updated_at = ? WHERE id = ?",
            (json.dumps(settings), _now(), chat_id),
        )
        conn.commit()
        conn.close()
    if cur.rowcount == 0:
        raise KeyError(chat_id)
    return policy


def _set_profile_tool_policy(
    profile_id: str,
    raw: str | dict | None,
    *,
    default_level: int = DEFAULT_TOOL_POLICY_LEVEL,
) -> dict:
    policy = _normalize_tool_policy(raw, default_level=default_level)
    with _db_lock:
        conn = _get_db()
        cur = conn.execute(
            "UPDATE agent_profiles SET tool_policy = ?, updated_at = ? WHERE id = ?",
            (json.dumps(policy, separators=(",", ":")), _now(), profile_id),
        )
        conn.commit()
        conn.close()
    if cur.rowcount == 0:
        raise KeyError(profile_id)
    return policy


# ---------------------------------------------------------------------------
# Token counting (compaction support)
# ---------------------------------------------------------------------------

def _get_cumulative_tokens_in(chat_id: str) -> int:
    """Sum tokens_in for messages in a chat since last compaction."""
    since = _last_compacted_at.get(chat_id)
    with _db_lock:
        conn = _get_db()
        if since:
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens_in), 0) FROM messages "
                "WHERE chat_id = ? AND created_at > ?",
                (chat_id, since),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens_in), 0) FROM messages WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        conn.close()
    return row[0] if row else 0


def _get_last_turn_tokens_in(chat_id: str) -> int:
    """Get the best estimate of current context fill for a Claude chat."""
    since = _last_compacted_at.get(chat_id)
    with _db_lock:
        conn = _get_db()
        if since:
            rows = conn.execute(
                "SELECT tokens_in FROM messages "
                "WHERE chat_id = ? AND role = 'assistant' AND tokens_in > 0 AND created_at > ? "
                "ORDER BY created_at DESC LIMIT 5",
                (chat_id, since),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT tokens_in FROM messages "
                "WHERE chat_id = ? AND role = 'assistant' AND tokens_in > 0 "
                "ORDER BY created_at DESC LIMIT 5",
                (chat_id,),
            ).fetchall()
        conn.close()
    return max((r[0] for r in rows), default=0)


def _estimate_tokens(chat_id: str, context_window: int = 0) -> int:
    """Estimate token count from message content (~4 chars per token)."""
    since = _last_compacted_at.get(chat_id)
    with _db_lock:
        conn = _get_db()
        if since:
            row = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(content)), 0) FROM messages "
                "WHERE chat_id = ? AND created_at > ?",
                (chat_id, since),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(content)), 0) FROM messages WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        conn.close()
    total_chars = row[0] if row else 0
    estimated = total_chars // 4
    if context_window > 0:
        return min(estimated, context_window)
    return estimated


def _get_recent_messages_text(chat_id: str, limit: int = 30) -> str:
    """Get recent message content for summarization (last N messages)."""
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        conn.close()
    rows.reverse()  # chronological order
    lines = []
    for role, content in rows:
        text = (content or "")[:500]
        lines.append(f"[{role}] {text}")
    return "\n".join(lines)


def _get_last_assistant_speaker(chat_id: str) -> str:
    """Return the speaker_id of the most recent assistant message, or ''."""
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT speaker_id FROM messages WHERE chat_id = ? AND role = 'assistant' "
            "AND speaker_id != '' ORDER BY created_at DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
        conn.close()
    return row[0] if row else ""


def _get_recently_active_chats(hours: int = 24) -> list[str]:
    """Return chat_ids (type='chat' only) with messages in the last N hours."""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT DISTINCT m.chat_id FROM messages m "
            "JOIN chats c ON m.chat_id = c.id "
            "WHERE c.type = 'chat' AND m.created_at > ?",
            (cutoff,),
        ).fetchall()
        conn.close()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Chat CRUD
# ---------------------------------------------------------------------------

def _create_chat(title: str = "New Channel", model: str | None = None, chat_type: str = "chat",
                  category: str | None = None, profile_id: str = "") -> str:
    cid = str(uuid.uuid4())[:8]
    now = _now()
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT INTO chats (id, title, model, type, category, profile_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, title, model, chat_type, category, profile_id, now, now),
        )
        conn.commit()
        conn.close()
    return cid


def _get_chats() -> list[dict]:
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT c.id, c.title, c.claude_session_id, c.created_at, c.updated_at, "
            "c.model, c.type, c.category, c.profile_id, ap.name, ap.avatar "
            "FROM chats c LEFT JOIN agent_profiles ap ON c.profile_id = ap.id "
            "ORDER BY c.updated_at DESC"
        ).fetchall()
        # Batch-fetch member counts + primary agent for groups
        group_ids = [r[0] for r in rows if (r[6] or "chat") == "group"]
        group_meta: dict[str, dict] = {}
        if group_ids:
            for gid in group_ids:
                members = conn.execute(
                    "SELECT m.agent_profile_id, m.is_primary, ap2.name, ap2.avatar "
                    "FROM channel_agent_memberships m "
                    "JOIN agent_profiles ap2 ON m.agent_profile_id = ap2.id "
                    "WHERE m.channel_id = ? AND COALESCE(m.status, 'active') = 'active'", (gid,)
                ).fetchall()
                primary = next((m for m in members if m[1]), None)
                group_meta[gid] = {
                    "member_count": len(members),
                    "primary_name": primary[2] if primary else "",
                    "primary_avatar": primary[3] if primary else "",
                }
        conn.close()
    result = []
    for r in rows:
        d = {"id": r[0], "title": r[1], "claude_session_id": r[2],
             "created_at": r[3], "updated_at": r[4], "model": r[5], "type": r[6], "category": r[7] or None,
             "profile_id": r[8] or "", "profile_name": r[9] or "", "profile_avatar": r[10] or ""}
        gm = group_meta.get(r[0])
        if gm:
            d["member_count"] = gm["member_count"]
            d["primary_profile_name"] = gm["primary_name"]
            d["primary_profile_avatar"] = gm["primary_avatar"]
            if not d["profile_name"] and gm["primary_name"]:
                d["profile_name"] = gm["primary_name"]
                d["profile_avatar"] = gm["primary_avatar"]
        result.append(d)
    return result


def _get_chat(chat_id: str) -> dict | None:
    with _db_lock:
        conn = _get_db()
        row = conn.execute("SELECT id, title, claude_session_id, created_at, updated_at, model, type, category, profile_id FROM chats WHERE id = ?",
                           (chat_id,)).fetchone()
        conn.close()
    if not row:
        return None
    return {"id": row[0], "title": row[1], "claude_session_id": row[2],
            "created_at": row[3], "updated_at": row[4], "model": row[5], "type": row[6], "category": row[7] or None,
            "profile_id": row[8] or ""}


def _update_chat(chat_id: str, **kwargs) -> None:
    bad = set(kwargs) - _CHAT_UPDATE_FIELDS
    if bad:
        raise ValueError(f"Disallowed chat update fields: {bad}")
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [_now(), chat_id]
    with _db_lock:
        conn = _get_db()
        conn.execute(f"UPDATE chats SET {sets}, updated_at = ? WHERE id = ?", vals)
        conn.commit()
        conn.close()


def _delete_chat(chat_id: str) -> bool:
    with _db_lock:
        conn = _get_db()
        # Delete messages first — FK constraint requires it
        conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        cur = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        if cur.rowcount:
            conn.commit()
            conn.close()
            return True
        conn.commit()
        conn.close()
        return False


# ---------------------------------------------------------------------------
# Group members
# ---------------------------------------------------------------------------

def _normalize_group_primary_locked(conn: sqlite3.Connection, channel_id: str,
                                  preferred_profile_id: str | None = None) -> str | None:
    """Enforce exactly one active primary for a group."""
    rows = conn.execute(
        "SELECT agent_profile_id, routing_mode, is_primary, display_order "
        "FROM channel_agent_memberships "
        "WHERE channel_id = ? AND COALESCE(status, 'active') = 'active' "
        "ORDER BY display_order, created_at, id",
        (channel_id,),
    ).fetchall()
    if not rows:
        return None

    active_ids = [r[0] for r in rows]
    if preferred_profile_id not in active_ids:
        preferred_profile_id = None

    primary_id = preferred_profile_id
    if not primary_id:
        for r in rows:
            if bool(r[2]) or (r[1] == 'primary'):
                primary_id = r[0]
                break
    if not primary_id:
        primary_id = rows[0][0]

    conn.execute(
        "UPDATE channel_agent_memberships "
        "SET routing_mode = CASE WHEN agent_profile_id = ? THEN 'primary' ELSE 'mentioned' END, "
        "    is_primary = CASE WHEN agent_profile_id = ? THEN 1 ELSE 0 END "
        "WHERE channel_id = ? AND COALESCE(status, 'active') = 'active'",
        (primary_id, primary_id, channel_id),
    )
    return primary_id


def _get_group_members(channel_id: str) -> list[dict]:
    with _db_lock:
        conn = _get_db()
        _normalize_group_primary_locked(conn, channel_id)
        conn.commit()
        rows = conn.execute(
            "SELECT m.id, m.agent_profile_id, m.routing_mode, m.is_primary, m.display_order, "
            "ap.name, ap.avatar, COALESCE(o.model, ap.model), m.role, m.status "
            "FROM channel_agent_memberships m "
            "JOIN agent_profiles ap ON m.agent_profile_id = ap.id "
            "LEFT JOIN persona_model_overrides o ON o.profile_id = ap.id "
            "WHERE m.channel_id = ? AND COALESCE(m.status, 'active') = 'active' "
            "ORDER BY m.is_primary DESC, m.display_order",
            (channel_id,),
        ).fetchall()
        conn.close()
    members = []
    for row in rows:
        effective_model = row[7] or ""
        members.append(
            {
                "id": row[0],
                "profile_id": row[1],
                "routing_mode": row[2],
                "is_primary": bool(row[3]),
                "display_order": row[4],
                "name": row[5],
                "avatar": row[6],
                "model": effective_model,
                "backend": _get_model_backend(effective_model) if effective_model else "",
                "role": row[8] or "member",
                "status": row[9] or "active",
            }
        )
    return members


def _get_chat_settings(chat_id: str) -> dict:
    """Get parsed settings dict for a chat. Returns empty dict if none."""
    with _db_lock:
        conn = _get_db()
        row = conn.execute("SELECT settings FROM chats WHERE id = ?", (chat_id,)).fetchone()
        conn.close()
    if not row or not row[0]:
        return {}
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return {}


def _update_chat_settings(chat_id: str, updates: dict) -> dict:
    """Merge updates into chat settings. Returns the full updated settings."""
    settings = _get_chat_settings(chat_id)
    settings.update(updates)
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "UPDATE chats SET settings = ?, updated_at = ? WHERE id = ?",
            (json.dumps(settings), _now(), chat_id),
        )
        conn.commit()
        conn.close()
    return settings


def _add_group_member(channel_id: str, profile_id: str, routing_mode: str = "mentioned",
                      is_primary: bool = False, display_order: int = 0) -> str:
    is_primary = bool(is_primary or routing_mode == "primary")
    routing_mode = "primary" if is_primary else "mentioned"
    with _db_lock:
        conn = _get_db()
        # Check for soft-deleted membership — reactivate if found
        existing = conn.execute(
            "SELECT id FROM channel_agent_memberships "
            "WHERE channel_id = ? AND agent_profile_id = ? AND status = 'inactive'",
            (channel_id, profile_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE channel_agent_memberships SET status = 'active', routing_mode = ?, "
                "is_primary = ?, display_order = ? WHERE id = ?",
                (routing_mode, int(is_primary), display_order, existing[0]),
            )
            if is_primary:
                _normalize_group_primary_locked(conn, channel_id, preferred_profile_id=profile_id)
            else:
                _normalize_group_primary_locked(conn, channel_id)
            conn.commit()
            conn.close()
            return existing[0]
        mid = str(uuid.uuid4())[:12]
        conn.execute(
            "INSERT INTO channel_agent_memberships (id, channel_id, agent_profile_id, routing_mode, "
            "is_primary, display_order, role, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'member', 'active', ?)",
            (mid, channel_id, profile_id, routing_mode, int(is_primary), display_order, _now()),
        )
        if is_primary:
            _normalize_group_primary_locked(conn, channel_id, preferred_profile_id=profile_id)
        else:
            _normalize_group_primary_locked(conn, channel_id)
        conn.commit()
        conn.close()
    return mid


def _update_group_member(channel_id: str, profile_id: str, routing_mode: str | None = None) -> bool:
    """Update an active member's routing mode (primary ↔ mentioned)."""
    if routing_mode not in ("primary", "mentioned", None):
        return False
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT id FROM channel_agent_memberships "
            "WHERE channel_id = ? AND agent_profile_id = ? AND COALESCE(status, 'active') = 'active'",
            (channel_id, profile_id),
        ).fetchone()
        if not row:
            conn.close()
            return False
        if routing_mode:
            is_primary = routing_mode == "primary"
            preferred = profile_id if is_primary else None
            _normalize_group_primary_locked(conn, channel_id, preferred_profile_id=preferred)
        conn.commit()
        conn.close()
    return True


def _remove_group_member(channel_id: str, profile_id: str) -> bool:
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT is_primary, routing_mode FROM channel_agent_memberships "
            "WHERE channel_id = ? AND agent_profile_id = ? AND COALESCE(status, 'active') = 'active'",
            (channel_id, profile_id),
        ).fetchone()
        if not row:
            conn.close()
            return False
        remaining = conn.execute(
            "SELECT COUNT(*) FROM channel_agent_memberships "
            "WHERE channel_id = ? AND agent_profile_id != ? AND COALESCE(status, 'active') = 'active'",
            (channel_id, profile_id),
        ).fetchone()[0]
        if remaining <= 0:
            conn.close()
            return False
        cur = conn.execute(
            "UPDATE channel_agent_memberships SET status = 'inactive' "
            "WHERE channel_id = ? AND agent_profile_id = ? AND COALESCE(status, 'active') = 'active'",
            (channel_id, profile_id),
        )
        if bool(row[0]) or row[1] == 'primary':
            _normalize_group_primary_locked(conn, channel_id)
        conn.commit()
        conn.close()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Persona memories
# ---------------------------------------------------------------------------

def _add_persona_memory(profile_id: str, content: str, category: str = "decision",
                        source_chat_id: str = "") -> str:
    """Store a memory entry for a persona. Memories persist across all groups."""
    mid = str(uuid.uuid4())[:12]
    token_count = max(1, len(content.split()) * 4 // 3)
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT INTO persona_memories (id, profile_id, content, category, source_chat_id, created_at, token_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mid, profile_id, content, category, source_chat_id, _now(), token_count),
        )
        conn.commit()
        conn.close()
    return mid


def _get_persona_memories(profile_id: str, limit: int = 50) -> list[dict]:
    """Retrieve recent memories for a persona, newest first."""
    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT id, content, category, source_chat_id, created_at, "
            "COALESCE(access_count, 0), COALESCE(last_accessed_at, ''), "
            "COALESCE(violation_count, 0), COALESCE(token_count, 0) "
            "FROM persona_memories WHERE profile_id = ? ORDER BY created_at DESC LIMIT ?",
            (profile_id, limit),
        ).fetchall()
        conn.close()
    return [{"id": r[0], "content": r[1], "category": r[2],
             "source_chat_id": r[3], "created_at": r[4],
             "access_count": r[5], "last_accessed_at": r[6],
             "violation_count": r[7], "token_count": r[8]} for r in rows]


def _get_persona_model_override(profile_id: str) -> str:
    """Return the active model override for a persona, or '' if none."""
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT model FROM persona_model_overrides WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        conn.close()
    return row[0] if row else ""


def _set_persona_model_override(profile_id: str, model: str) -> None:
    """Set or clear (model='') a model override for a persona."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _db_lock:
        conn = _get_db()
        if model:
            conn.execute(
                "INSERT INTO persona_model_overrides (profile_id, model, updated_at) "
                "VALUES (?, ?, ?) ON CONFLICT(profile_id) DO UPDATE SET model=excluded.model, updated_at=excluded.updated_at",
                (profile_id, model, now),
            )
        else:
            conn.execute(
                "DELETE FROM persona_model_overrides WHERE profile_id = ?",
                (profile_id,),
            )
        conn.commit()
        conn.close()


def _delete_persona_memory(memory_id: str) -> bool:
    with _db_lock:
        conn = _get_db()
        cur = conn.execute("DELETE FROM persona_memories WHERE id = ?", (memory_id,))
        conn.commit()
        conn.close()
    return cur.rowcount > 0


def _bump_memory_access(memory_ids: list[str]) -> None:
    """Increment access_count and update last_accessed_at for injected memories."""
    if not memory_ids:
        return
    now = _now()
    with _db_lock:
        conn = _get_db()
        conn.executemany(
            "UPDATE persona_memories SET access_count = access_count + 1, last_accessed_at = ? WHERE id = ?",
            [(now, mid) for mid in memory_ids],
        )
        conn.commit()
        conn.close()


def _bump_memory_violation(memory_id: str) -> None:
    """Increment violation_count for a correction memory."""
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "UPDATE persona_memories SET violation_count = violation_count + 1 WHERE id = ?",
            (memory_id,),
        )
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def _save_message(chat_id: str, role: str, content: str, tool_events: str = "[]",
                  thinking: str = "", cost_usd: float = 0, tokens_in: int = 0,
                  tokens_out: int = 0, speaker_id: str = "", speaker_name: str = "",
                  speaker_avatar: str = "", visibility: str = "public",
                  group_turn_id: str = "", attachments: str = "[]",
                  duration_ms: int = 0, canceled: bool = False) -> str:
    mid = str(uuid.uuid4())[:12]
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, tool_events, thinking, cost_usd, "
            "tokens_in, tokens_out, speaker_id, speaker_name, speaker_avatar, visibility, "
            "group_turn_id, attachments, duration_ms, canceled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, chat_id, role, content, tool_events, thinking, cost_usd, tokens_in, tokens_out,
             speaker_id, speaker_name, speaker_avatar, visibility, group_turn_id, attachments,
             duration_ms, int(canceled), _now()))
        conn.commit()
        conn.close()
    return mid


def _parse_message_attachments(raw: str | None) -> list[dict]:
    try:
        parsed = json.loads(raw or "[]")
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _get_latest_user_attachments(chat_id: str) -> list[dict]:
    """Return attachment refs from the most recent user message with attachments in this chat.

    Used to inject path references into secondary-agent prompts in group channels so
    non-primary agents know what was shared without receiving a full base64 payload.
    """
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT attachments FROM messages "
            "WHERE chat_id = ? AND role = 'user' "
            "AND attachments IS NOT NULL AND attachments != '[]' "
            "ORDER BY created_at DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
        conn.close()
    if not row:
        return []
    return _parse_message_attachments(row[0])


def _get_messages(
    chat_id: str,
    days: int | None = None,
    include_internal: bool = False,
    limit: int | None = None,
    before_id: str | None = None,
) -> dict:
    """Return {messages: [...], has_more: bool}.

    Pagination: pass limit + optional before_id (exclusive cursor).
    Messages are returned oldest-first within the page.
    has_more=True means older messages exist before this page.
    """
    vis_clause = "" if include_internal else " AND (visibility = 'public' OR visibility = '' OR visibility IS NULL)"
    cols = ("id, role, content, tool_events, thinking, cost_usd, tokens_in, tokens_out, "
            "created_at, speaker_id, speaker_name, speaker_avatar, visibility, group_turn_id, attachments, duration_ms, canceled")

    with _db_lock:
        conn = _get_db()

        # Build WHERE
        where_parts = ["chat_id = ?"]
        params: list = [chat_id]

        if days and days > 0:
            where_parts.append("created_at >= datetime('now', ?)")
            params.append(f"-{days} days")

        if before_id:
            # Fetch the created_at of the cursor message to paginate by time
            cur_row = conn.execute(
                "SELECT created_at FROM messages WHERE id = ?", (before_id,)
            ).fetchone()
            if cur_row:
                where_parts.append("created_at < ?")
                params.append(cur_row[0])

        where_parts_str = " AND ".join(where_parts)
        # Add visibility after other filters
        where = f"WHERE {where_parts_str}{vis_clause}"

        if limit and limit > 0:
            # Fetch limit+1 to detect has_more; fetch newest-first then reverse
            fetch_limit = min(limit + 1, 1000)
            rows = conn.execute(
                f"SELECT {cols} FROM messages {where} ORDER BY created_at DESC LIMIT ?",
                params + [fetch_limit],
            ).fetchall()
            has_more = len(rows) > limit
            rows = list(reversed(rows[:limit]))
        else:
            rows = conn.execute(
                f"SELECT {cols} FROM messages {where} ORDER BY created_at",
                params,
            ).fetchall()
            has_more = False

        conn.close()

    messages = [
        {"id": r[0], "role": r[1], "content": r[2], "tool_events": r[3],
         "thinking": r[4], "cost_usd": r[5], "tokens_in": r[6],
         "tokens_out": r[7], "created_at": r[8],
         "speaker_id": r[9] or "", "speaker_name": r[10] or "",
         "speaker_avatar": r[11] or "", "visibility": r[12] or "public",
         "group_turn_id": r[13] or "",
         "attachments": _parse_message_attachments(r[14]),
         "duration_ms": r[15] or 0,
         "canceled": bool(r[16]) if len(r) > 16 else False}
        for r in rows
    ]
    return {"messages": messages, "has_more": has_more}


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def _create_alert(source: str, severity: str, title: str, body: str, metadata: dict | None = None) -> dict:
    aid = uuid.uuid4().hex[:8]
    now = _now()
    raw_meta = metadata or {}
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT INTO alerts (id, source, severity, title, body, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (aid, source, severity, title, body, json.dumps(raw_meta), now),
        )
        conn.commit()
        conn.close()
    # Flatten values to strings — iOS decodes metadata as [String: String]
    str_meta = {str(k): json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                for k, v in raw_meta.items()}
    return {"id": aid, "source": source, "severity": severity, "title": title,
            "body": body, "acked": False, "metadata": str_meta, "created_at": now}


def _get_alerts(since: str | None = None, unacked_only: bool = False,
                category: str | None = None, limit: int = 100) -> list[dict]:
    # Map category to matching sources
    category_sources = None
    if category:
        category_sources = [src for src, cat in ALERT_CATEGORY_MAP.items() if cat == category]
    with _db_lock:
        conn = _get_db()
        query = "SELECT id, source, severity, title, body, acked, created_at, metadata FROM alerts"
        params: list = []
        conditions: list[str] = []
        if since:
            conditions.append("created_at > ?")
            params.append(since)
        if unacked_only:
            conditions.append("acked = 0")
        if category_sources is not None:
            placeholders = ", ".join("?" for _ in category_sources)
            conditions.append(f"source IN ({placeholders})")
            params.extend(category_sources)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
    results = []
    for r in rows:
        meta: dict[str, str] = {}
        try:
            raw = json.loads(r[7]) if r[7] else {}
            # Flatten all values to strings — iOS decodes as [String: String]
            meta = {str(k): json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                    for k, v in raw.items()}
        except Exception:
            pass
        results.append({"id": r[0], "source": r[1], "severity": r[2], "title": r[3],
                         "body": r[4], "acked": bool(r[5]), "created_at": r[6], "metadata": meta})
    return results


def _ack_alert(alert_id: str) -> bool:
    with _db_lock:
        conn = _get_db()
        cur = conn.execute("UPDATE alerts SET acked = 1 WHERE id = ? AND acked = 0", (alert_id,))
        conn.commit()
        changed = cur.rowcount > 0
        conn.close()
    return changed


def _get_alert(alert_id: str) -> dict | None:
    with _db_lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT id, source, severity, title, body, acked, created_at, metadata FROM alerts WHERE id = ?",
            (alert_id,),
        ).fetchone()
        conn.close()
    if not row:
        return None
    meta = {}
    try:
        meta = json.loads(row[7]) if row[7] else {}
    except Exception:
        pass
    return {"id": row[0], "source": row[1], "severity": row[2], "title": row[3],
            "body": row[4], "acked": bool(row[5]), "created_at": row[6], "metadata": meta}


def _get_alerts_channels() -> list[dict]:
    """Return alerts-type chats with their category filter."""
    with _db_lock:
        conn = _get_db()
        rows = conn.execute("SELECT id, category FROM chats WHERE type = 'alerts'").fetchall()
        conn.close()
    return [{"id": r[0], "category": r[1]} for r in rows]


# ---------------------------------------------------------------------------
# Device tokens (APNs)
# ---------------------------------------------------------------------------

def _get_all_device_tokens() -> list[str]:
    with _db_lock:
        conn = _get_db()
        rows = conn.execute("SELECT token FROM device_tokens").fetchall()
        conn.close()
    return [r[0] for r in rows]


def _remove_device_token(token: str) -> None:
    with _db_lock:
        conn = _get_db()
        conn.execute("DELETE FROM device_tokens WHERE token = ?", (token,))
        conn.commit()
        conn.close()
    log(f"APNs: removed expired token {token[:12]}...")


def _log_permission_change(
    chat_id: str,
    event_type: str,
    old_level: int | None,
    new_level: int | None,
    elevated_until: str | None = None,
) -> None:
    """Append a row to permission_audit_log. Non-blocking — errors are swallowed."""
    import uuid as _uuid
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row_id = str(_uuid.uuid4())
    try:
        with _db_lock:
            conn = _get_db()
            conn.execute(
                "INSERT INTO permission_audit_log (id, chat_id, event_type, old_level, new_level, elevated_until, changed_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (row_id, chat_id, event_type, old_level, new_level, elevated_until, now),
            )
            conn.commit()
            conn.close()
    except Exception as exc:
        log(f"permission_audit_log write failed: {exc}")
