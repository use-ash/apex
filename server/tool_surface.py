"""Unified Apex MCP tool surface (PR1a: pure extract, no intentional behavior change).

Source of truth for catalog load + inject helpers previously inlined in
``streaming.py``. Projectors for Grok/Codex and level matrices land in later
PRs; this module must preserve Claude SDK + tool-loop load semantics.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import env
from env import APEX_ROOT
from log import log

# ---------------------------------------------------------------------------
# Catalog load
# ---------------------------------------------------------------------------


def load_enabled_mcp_servers(*, strip_enabled_key: bool = True) -> dict[str, dict]:
    """Load enabled MCP servers from ``state/mcp_servers.json``.

    Args:
        strip_enabled_key: Claude SDK path historically strips the ``enabled``
            key from each server dict. The tool-loop bridge historically keeps
            it. Pass the matching flag so call sites stay byte-compatible.
    """
    mcp_path = APEX_ROOT / "state" / "mcp_servers.json"
    if not mcp_path.exists():
        return {}
    try:
        data = json.loads(mcp_path.read_text())
        servers = data.get("mcpServers", {})
        if not isinstance(servers, dict):
            return {}
        out: dict[str, dict] = {}
        for name, cfg in servers.items():
            if not isinstance(cfg, dict) or not cfg.get("enabled", True):
                continue
            if strip_enabled_key:
                out[name] = {k: v for k, v in cfg.items() if k != "enabled"}
            else:
                out[name] = cfg
        return env.rewrite_mcp_servers_for_workspace(out)
    except (json.JSONDecodeError, OSError) as e:
        log(f"MCP config load failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Inject helpers (conditions locked to pre-extract streaming.py behavior)
# ---------------------------------------------------------------------------


def inject_execute_code_mcp(
    servers: dict,
    *,
    chat_id: str | None = None,
    workspace: str | None = None,
    permission_level: int = 2,
) -> dict:
    """Auto-inject the execute_code MCP server if Jupyter is installed."""
    if "execute_code" in servers:
        return servers  # user already configured it manually
    try:
        import jupyter_client  # noqa: F401
    except ImportError:
        return servers  # no Jupyter — skip
    mcp_script = APEX_ROOT / "server" / "local_model" / "mcp_execute_code.py"
    if not mcp_script.exists():
        return servers
    mcp_env = {"APEX_PERMISSION_LEVEL": str(permission_level)}
    if chat_id:
        mcp_env["APEX_CHAT_ID"] = chat_id
    if workspace:
        mcp_env["APEX_WORKSPACE"] = workspace
    servers = dict(servers)  # don't mutate caller's dict
    servers["execute_code"] = {
        "command": sys.executable,
        "args": [str(mcp_script)],
        "env": mcp_env,
    }
    return servers


def inject_claim_store_mcp(servers: dict, *, chat_id: str | None = None) -> dict:
    """Propagate Apex chat_id to claim_store MCP via APEX_CHAT_ID env.

    Idempotent and narrow: no-op when claim_store isn't configured or chat_id
    is None. Mutates only env['APEX_CHAT_ID'] — preserves other env vars.
    """
    if not chat_id or "claim_store" not in servers:
        return servers
    servers = dict(servers)
    spec = dict(servers["claim_store"])
    env_map = dict(spec.get("env") or {})
    env_map["APEX_CHAT_ID"] = chat_id
    spec["env"] = env_map
    servers["claim_store"] = spec
    return servers


def inject_computer_use_mcp(
    servers: dict,
    *,
    chat_id: str | None = None,
    permission_level: int = 2,
    computer_use_target: str | None = None,
) -> dict:
    """Auto-inject computer_use MCP for macOS GUI automation when configured."""
    if sys.platform != "darwin":
        return servers
    if not (isinstance(computer_use_target, str) and computer_use_target.strip()):
        return servers
    if "computer_use" in servers:
        return servers
    mcp_script = APEX_ROOT / "server" / "local_model" / "mcp_computer_use.py"
    if not mcp_script.exists():
        return servers
    mcp_env = {
        "APEX_CU_TARGET_BUNDLE": computer_use_target.strip(),
        "APEX_CU_CHAT_ID": chat_id or "",
        "APEX_CU_STATE_DIR": str(APEX_ROOT / "state" / "computer_use"),
        "APEX_PERMISSION_LEVEL": str(permission_level),
    }
    servers = dict(servers)
    servers["computer_use"] = {
        "command": sys.executable,
        "args": [str(mcp_script)],
        "env": mcp_env,
    }
    return servers


def inject_interceptor_mcp(
    servers: dict,
    *,
    chat_id: str | None = None,
    interceptor_enabled: bool = False,
) -> dict:
    """Auto-inject Interceptor (browser-agent) MCP when chat has opted in."""
    if not interceptor_enabled:
        return servers
    if sys.platform != "darwin":
        return servers
    if "interceptor" in servers:
        return servers
    mcp_script = APEX_ROOT / "server" / "local_model" / "mcp_interceptor.py"
    if not mcp_script.exists():
        return servers
    bin_path = os.environ.get("APEX_INTERCEPTOR_BIN") or str(
        (APEX_ROOT.parent.parent / ".interceptor" / "bin" / "interceptor").resolve()
        if False
        else os.path.expanduser("~/.interceptor/bin/interceptor")
    )
    if not os.path.exists(bin_path):
        log(f"interceptor MCP skipped: binary missing at {bin_path}")
        return servers
    mcp_env = {
        "APEX_INT_CHAT_ID": chat_id or "",
        "APEX_INT_STATE_DIR": str(APEX_ROOT / "state" / "interceptor"),
        "APEX_INTERCEPTOR_BIN": bin_path,
    }
    servers = dict(servers)
    servers["interceptor"] = {
        "command": sys.executable,
        "args": [str(mcp_script)],
        "env": mcp_env,
    }
    return servers


def inject_guide_tools_mcp(servers: dict) -> dict:
    """Auto-inject guide config tools MCP server (caller decides when)."""
    if "guide_tools" in servers:
        return servers
    mcp_script = APEX_ROOT / "server" / "local_model" / "mcp_guide_tools.py"
    if not mcp_script.exists():
        return servers
    servers = dict(servers)
    servers["guide_tools"] = {
        "command": sys.executable,
        "args": [str(mcp_script)],
        "env": {"APEX_ROOT": str(APEX_ROOT)},
    }
    return servers


def project_claude(servers: dict[str, Any]) -> dict[str, dict]:
    """Claude SDK projector: pass-through of already-stripped server specs.

    PR1a: identical to assigning opts.mcp_servers = servers after injects.
    """
    return dict(servers)
