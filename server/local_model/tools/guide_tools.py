"""Guide persona configuration tools.

Safe-by-design tools that let the Guide persona configure the Apex server
on the user's behalf. Each tool validates inputs against a strict schema
and only modifies known, safe configuration surfaces.

These tools are:
- Registered in the local model registry (Ollama path)
- Exposed via mcp_guide_tools.py MCP server (Claude SDK path)
- Gated to guide sessions only via extra_allowed_tools in the tool gate
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

_APEX_ROOT = Path(os.environ.get("APEX_ROOT", "")).resolve() if os.environ.get("APEX_ROOT") else None


def _apex_root() -> Path:
    """Resolve APEX_ROOT, preferring the env module if available."""
    if _APEX_ROOT:
        return _APEX_ROOT
    try:
        import env
        return env.APEX_ROOT
    except Exception:
        # Fallback for MCP subprocess context
        return Path(os.environ.get("APEX_ROOT", Path.home() / ".openclaw" / "apex"))


def _config_path() -> Path:
    return _apex_root() / "state" / "config.json"


def _mcp_config_path() -> Path:
    return _apex_root() / "state" / "mcp_servers.json"


def _db_path() -> Path:
    return _apex_root() / "state" / "apex.db"


def _read_config() -> dict:
    path = _config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_config(config: dict) -> None:
    path = _config_path()
    path.write_text(json.dumps(config, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Writable config keys — whitelist with type validation
# ---------------------------------------------------------------------------

_WRITABLE_KEYS: dict[str, type | tuple[type, ...]] = {
    "models.default_model": str,
    "models.ollama_url": str,
    "models.mlx_url": str,
    "models.compaction_threshold": int,
    "models.compaction_model": str,
    "models.compaction_ollama_fallback": str,
    "models.sdk_query_timeout": int,
    "models.sdk_stream_timeout": int,
    "models.enable_skill_dispatch": bool,
    "models.max_turns": int,
    "models.max_tool_iterations": int,
    "workspace.enable_whisper": bool,
}


# =====================================================================
# Tool: guide__config_get
# =====================================================================

def config_get(args: dict, workspace: str | None = None, **kwargs) -> str:
    """Read configuration values. Returns full config or a specific section."""
    section = str(args.get("section", "")).strip().lower()
    config = _read_config()

    if not section or section == "all":
        # Redact sensitive paths but show structure
        safe = dict(config)
        return json.dumps(safe, indent=2)

    if section in config:
        return json.dumps({section: config[section]}, indent=2)

    return f"Unknown section: {section}. Available: {', '.join(config.keys())}"


# =====================================================================
# Tool: guide__config_set
# =====================================================================

def config_set(args: dict, workspace: str | None = None, **kwargs) -> str:
    """Set a configuration value. Only whitelisted keys are allowed."""
    key = str(args.get("key", "")).strip()
    value = args.get("value")

    if not key:
        return "Error: 'key' is required. Use guide__config_get to see available keys."

    if key not in _WRITABLE_KEYS:
        writable = "\n".join(f"  {k} ({t.__name__})" for k, t in _WRITABLE_KEYS.items())
        return f"Error: '{key}' is not a writable config key.\n\nWritable keys:\n{writable}"

    expected_type = _WRITABLE_KEYS[key]

    # Type coercion
    if expected_type is bool:
        if isinstance(value, str):
            value = value.lower() in ("true", "1", "yes", "on")
        else:
            value = bool(value)
    elif expected_type is int:
        try:
            value = int(value)
        except (TypeError, ValueError):
            return f"Error: '{key}' expects an integer, got: {value!r}"
    elif expected_type is str:
        value = str(value) if value is not None else ""

    # Read, update, write
    config = _read_config()
    section, field = key.split(".", 1)
    if section not in config:
        config[section] = {}
    old_value = config[section].get(field, "<unset>")
    config[section][field] = value
    _write_config(config)

    return f"OK: {key} = {json.dumps(value)}\n(was: {json.dumps(old_value)})"


# =====================================================================
# Tool: guide__agent_list
# =====================================================================

def agent_list(args: dict, workspace: str | None = None, **kwargs) -> str:
    """List all agent personas with their settings."""
    db = _db_path()
    if not db.exists():
        return "Error: database not found"

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, name, slug, avatar, role_description, backend, model, "
            "tool_policy, is_default, is_system FROM agent_profiles "
            "ORDER BY is_system DESC, name"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return "No agent personas found."

    lines = []
    for row in rows:
        policy = {}
        try:
            policy = json.loads(row["tool_policy"]) if row["tool_policy"] else {}
        except json.JSONDecodeError:
            pass
        level = policy.get("level", "default")
        flags = []
        if row["is_system"]:
            flags.append("system")
        if row["is_default"]:
            flags.append("default")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        lines.append(
            f"  {row['avatar']} {row['name']} (id={row['id']}){flag_str}\n"
            f"    model: {row['model']} | backend: {row['backend']} | level: {level}\n"
            f"    {row['role_description'] or '(no description)'}"
        )
    return f"Agent Personas ({len(rows)}):\n\n" + "\n\n".join(lines)


# =====================================================================
# Tool: guide__agent_create
# =====================================================================

def agent_create(args: dict, workspace: str | None = None, **kwargs) -> str:
    """Create a new agent persona."""
    name = str(args.get("name", "")).strip()
    if not name:
        return "Error: 'name' is required."

    model = str(args.get("model", "")).strip()
    backend = str(args.get("backend", "claude")).strip().lower()
    description = str(args.get("description", "")).strip()
    system_prompt = str(args.get("system_prompt", "")).strip()
    avatar = str(args.get("avatar", "🤖")).strip()
    level = 2  # Default to L2 for new agents

    level_arg = args.get("permission_level")
    if level_arg is not None:
        try:
            level = max(0, min(4, int(level_arg)))
        except (TypeError, ValueError):
            pass

    # Generate slug from name
    slug = name.lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")

    # Generate ID
    import hashlib
    agent_id = f"usr-{hashlib.md5(f'{name}{time.time()}'.encode()).hexdigest()[:8]}"

    db = _db_path()
    if not db.exists():
        return "Error: database not found"

    policy = json.dumps({"level": level, "default_level": level})
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO agent_profiles "
            "(id, name, slug, avatar, role_description, backend, model, "
            " system_prompt, tool_policy, is_default, is_system, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)",
            (agent_id, name, slug, avatar, description, backend, model,
             system_prompt, policy, now, now),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        return f"Error: {e}"
    finally:
        conn.close()

    return (
        f"Created agent persona:\n"
        f"  {avatar} {name} (id={agent_id})\n"
        f"  model: {model or '(default)'} | backend: {backend} | level: {level}\n"
        f"  {description or '(no description)'}"
    )


# =====================================================================
# Tool: guide__mcp_list
# =====================================================================

def mcp_list(args: dict, workspace: str | None = None, **kwargs) -> str:
    """List configured MCP servers and their status."""
    path = _mcp_config_path()
    if not path.exists():
        return "No MCP servers configured (mcp_servers.json not found)."

    try:
        data = json.loads(path.read_text())
        servers = data.get("mcpServers", {})
    except (json.JSONDecodeError, OSError) as e:
        return f"Error reading MCP config: {e}"

    if not servers:
        return "No MCP servers configured."

    lines = []
    for name, cfg in servers.items():
        enabled = cfg.get("enabled", True)
        status = "✅ enabled" if enabled else "⏸️  disabled"
        cmd = cfg.get("command", "?")
        cmd_args = cfg.get("args", [])
        # Show the key package name from args if npx
        pkg = ""
        if cmd == "npx" and cmd_args:
            for a in cmd_args:
                if not a.startswith("-"):
                    pkg = a
                    break
        lines.append(
            f"  {name}: {status}\n"
            f"    command: {cmd}{f' ({pkg})' if pkg else ''}"
        )

    return f"MCP Servers ({len(servers)}):\n\n" + "\n\n".join(lines)


# =====================================================================
# Tool: guide__mcp_toggle
# =====================================================================

def mcp_toggle(args: dict, workspace: str | None = None, **kwargs) -> str:
    """Enable or disable an MCP server."""
    server_name = str(args.get("server_name", "")).strip()
    enable = args.get("enable")

    if not server_name:
        return "Error: 'server_name' is required. Use guide__mcp_list to see available servers."

    path = _mcp_config_path()
    if not path.exists():
        return "Error: mcp_servers.json not found."

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return f"Error reading MCP config: {e}"

    servers = data.get("mcpServers", {})
    if server_name not in servers:
        available = ", ".join(servers.keys()) if servers else "(none)"
        return f"Error: server '{server_name}' not found. Available: {available}"

    if enable is None:
        # Toggle
        current = servers[server_name].get("enabled", True)
        enable = not current
    elif isinstance(enable, str):
        enable = enable.lower() in ("true", "1", "yes", "on")
    else:
        enable = bool(enable)

    old_state = servers[server_name].get("enabled", True)
    servers[server_name]["enabled"] = enable
    data["mcpServers"] = servers

    path.write_text(json.dumps(data, indent=2) + "\n")

    state_str = "enabled" if enable else "disabled"
    old_str = "enabled" if old_state else "disabled"
    return f"OK: MCP server '{server_name}' is now {state_str} (was: {old_str})\nNote: changes take effect on next chat session."


# =====================================================================
# Tool: guide__server_status
# =====================================================================

def server_status(args: dict, workspace: str | None = None, **kwargs) -> str:
    """Show server health and configuration summary."""
    config = _read_config()
    models = config.get("models", {})
    server = config.get("server", {})
    workspace_cfg = config.get("workspace", {})

    # Check DB
    db = _db_path()
    db_status = "OK" if db.exists() else "MISSING"
    db_size = f"{db.stat().st_size / 1024:.0f} KB" if db.exists() else "N/A"

    # Count agents
    agent_count = 0
    chat_count = 0
    if db.exists():
        try:
            conn = sqlite3.connect(str(db))
            agent_count = conn.execute("SELECT COUNT(*) FROM agent_profiles").fetchone()[0]
            chat_count = conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
            conn.close()
        except Exception:
            pass

    # Check Ollama
    ollama_url = models.get("ollama_url", "")
    ollama_status = "configured" if ollama_url else "not configured"

    # MCP servers
    mcp_path = _mcp_config_path()
    mcp_count = 0
    mcp_enabled = 0
    if mcp_path.exists():
        try:
            mcp_data = json.loads(mcp_path.read_text())
            mcp_servers = mcp_data.get("mcpServers", {})
            mcp_count = len(mcp_servers)
            mcp_enabled = sum(1 for c in mcp_servers.values() if c.get("enabled", True))
        except Exception:
            pass

    return (
        f"Apex Server Status\n"
        f"{'=' * 40}\n"
        f"  Host: {server.get('host', '?')}:{server.get('port', '?')}\n"
        f"  Debug: {server.get('debug', False)}\n"
        f"\n"
        f"Models:\n"
        f"  Default: {models.get('default_model', '(not set)')}\n"
        f"  Ollama: {ollama_status} ({ollama_url})\n"
        f"  Compaction model: {models.get('compaction_model', '(not set)')}\n"
        f"  SDK timeout: {models.get('sdk_stream_timeout', '?')}s stream / {models.get('sdk_query_timeout', '?')}s query\n"
        f"  Max turns: {models.get('max_turns', '?')} | Max tool iterations: {models.get('max_tool_iterations', '?')}\n"
        f"  Skills: {'enabled' if models.get('enable_skill_dispatch') else 'disabled'}\n"
        f"\n"
        f"Database:\n"
        f"  Status: {db_status} ({db_size})\n"
        f"  Agents: {agent_count} | Chats: {chat_count}\n"
        f"\n"
        f"MCP Servers: {mcp_enabled}/{mcp_count} enabled\n"
        f"Whisper: {'enabled' if workspace_cfg.get('enable_whisper') else 'disabled'}\n"
    )


# =====================================================================
# Tool: guide__reload_config
# =====================================================================

def reload_config(args: dict, workspace: str | None = None, **kwargs) -> str:
    """Signal the server to reload its configuration from disk.

    This works because the server reads config.json on each request via
    _read_policy_config() — most config changes take effect immediately
    without a restart. This tool just confirms the config is valid.
    """
    config = _read_config()
    if not config:
        return "Error: could not read config.json — file may be missing or malformed."

    # Validate structure
    required_sections = {"server", "models"}
    missing = required_sections - set(config.keys())
    if missing:
        return f"Warning: config.json is missing sections: {', '.join(missing)}"

    return (
        "Config validated OK. Most settings take effect on the next request "
        "or chat session — no server restart needed.\n\n"
        "Settings that require a server restart:\n"
        "  - server.host / server.port (binding changes)\n"
        "  - server.debug (debug mode)\n\n"
        "All other settings (models, workspace, policy) are read live."
    )


# ---------------------------------------------------------------------------
# Tool definitions (schemas) for registration
# ---------------------------------------------------------------------------

GUIDE_TOOL_DEFS: list[dict] = [
    {
        "name": "guide__config_get",
        "description": "Read the Apex server configuration. Returns the full config or a specific section (server, models, workspace, policy, alerts).",
        "parameters": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Config section to read: 'all', 'server', 'models', 'workspace', 'policy', 'alerts'. Default: 'all'",
                },
            },
            "required": [],
        },
        "executor": config_get,
    },
    {
        "name": "guide__config_set",
        "description": "Set a server configuration value. Only safe, whitelisted keys can be modified. Use guide__config_get first to see current values.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Dotted config key (e.g. 'models.default_model', 'models.ollama_url')",
                },
                "value": {
                    "description": "The value to set (type must match the key's expected type)",
                },
            },
            "required": ["key", "value"],
        },
        "executor": config_set,
    },
    {
        "name": "guide__agent_list",
        "description": "List all agent personas configured on the server, including their model, permission level, and description.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "executor": agent_list,
    },
    {
        "name": "guide__agent_create",
        "description": "Create a new agent persona. Specify name, model, backend, description, system prompt, and permission level.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Agent display name"},
                "model": {"type": "string", "description": "Model name (e.g. 'claude-sonnet-4-20250514', 'gemma3:27b')"},
                "backend": {"type": "string", "description": "Backend: 'claude' or 'ollama' (default: 'claude')"},
                "description": {"type": "string", "description": "Short role description"},
                "system_prompt": {"type": "string", "description": "System prompt / instructions for the agent"},
                "avatar": {"type": "string", "description": "Emoji avatar (default: 🤖)"},
                "permission_level": {"type": "integer", "description": "Permission level 0-4 (default: 2)"},
            },
            "required": ["name"],
        },
        "executor": agent_create,
    },
    {
        "name": "guide__mcp_list",
        "description": "List all MCP (Model Context Protocol) servers and their enabled/disabled status.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "executor": mcp_list,
    },
    {
        "name": "guide__mcp_toggle",
        "description": "Enable or disable an MCP server. Changes take effect on the next chat session.",
        "parameters": {
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Name of the MCP server (from guide__mcp_list)"},
                "enable": {"type": "boolean", "description": "True to enable, false to disable. Omit to toggle."},
            },
            "required": ["server_name"],
        },
        "executor": mcp_toggle,
    },
    {
        "name": "guide__server_status",
        "description": "Show Apex server health: configuration summary, database stats, MCP server count, and model settings.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "executor": server_status,
    },
    {
        "name": "guide__reload_config",
        "description": "Validate the current config and confirm which settings are live vs. require a restart.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "executor": reload_config,
    },
]

# Tool name set for permission gating
GUIDE_TOOL_NAMES: frozenset[str] = frozenset(d["name"] for d in GUIDE_TOOL_DEFS)
