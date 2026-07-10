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


# ---------------------------------------------------------------------------
# Level × server admission matrix (PR1b) — dual-track (SDK vs CLI)
# ---------------------------------------------------------------------------
#
# Design ref: docs/UNIFIED_TOOL_SURFACE_DESIGN.md §"Level × server admission
# matrix (dual-track — locked for P1+)". Rationale: Claude SDK gates
# individual tool CALLS at runtime via tool_access_decision + PreToolUse
# hooks; CLI backends run under --always-approve and have no equivalent
# mid-call gate, so admission must be stricter for CLI at the same level.
#
# Track A (SDK):  claude, tool_loop
# Track B (CLI):  xai/grok, codex

CORE_PACK_SERVERS: frozenset[str] = frozenset({"filesystem", "fetch", "memory"})

CLI_DEFAULT_DENY_SERVERS: frozenset[str] = frozenset(
    {"computer_use", "interceptor"}
)

_BACKEND_TRACKS: dict[str, str] = {
    "claude": "sdk",
    "tool_loop": "sdk",
    "xai": "cli",
    "grok": "cli",  # alias for xai
    "codex": "cli",
}


def backend_track(backend: str) -> str:
    """Map backend id to admission track. Unknown → sdk (conservative)."""
    return _BACKEND_TRACKS.get(backend, "sdk")


def _extras_include_claim_store(extras: frozenset[str] | None) -> bool:
    if not extras:
        return False
    for t in extras:
        if not isinstance(t, str):
            continue
        if t == "claim_store" or t.startswith("claim_store"):
            return True
    return False


def admit_server(
    server_name: str,
    *,
    level: int,
    backend: str,
    pack: str = "full",
    extras: frozenset[str] | None = None,
    in_catalog: bool = True,
    allow_cli_dangerous: bool = False,
) -> tuple[bool, str]:
    """Pure admission decision for a single MCP server.

    Returns (admit, reason). Reason is empty on admit; a short human-readable
    string on deny (for log/debug). See design doc for the full matrix.

    Args:
      server_name: The MCP server key (filesystem, fetch, execute_code, ...).
      level: Apex permission level (0=guide-only ... 4=full).
      backend: Apex backend id — claude, tool_loop, xai/grok, codex.
      pack: "core" (filesystem+fetch+memory) or "full" (everything except D).
      extras: extra_allowed_tools set (drives claim_store + guide_tools gates).
      in_catalog: Server is present in mcp_servers.json / injected.
      allow_cli_dangerous: Override CLI_DEFAULT_DENY_SERVERS (computer_use,
        interceptor). Never true in normal chats.
    """
    if not in_catalog:
        return False, "not in catalog"

    track = backend_track(backend)

    # L0 guide-only: only guide_tools admitted, and only via extras.
    if level <= 0:
        if server_name == "guide_tools" and extras:
            return True, ""
        return False, "L0 admits only guide_tools+extras"

    # claim_store — same rule both tracks (pure function in design §admit_claim_store)
    if server_name == "claim_store":
        if _extras_include_claim_store(extras):
            return True, ""
        if level >= 3 and pack == "full":
            return True, ""
        return False, f"claim_store needs extras or L3+ full (level={level}, pack={pack})"

    # guide_tools — extras-only regardless of track/level
    if server_name == "guide_tools":
        if extras:
            return True, ""
        return False, "guide_tools requires extras"

    if track == "sdk":
        # Track A — SDK / tool_loop
        if server_name == "filesystem":
            return (True, "") if level >= 1 else (False, "filesystem L1+")
        if server_name in {"fetch", "memory"}:
            return (True, "") if level >= 2 else (False, f"{server_name} L2+")
        if server_name == "execute_code":
            # L2+ on SDK; Claude L2 already permits via DEFAULT_LEVEL2_TOOL_PATTERNS.
            return (True, "") if level >= 2 else (False, "execute_code L2+")
        if server_name in {"computer_use", "interceptor"}:
            # Inject already filtered by target/enabled + darwin; matrix
            # permits at L2+ once conditions met.
            return (True, "") if level >= 2 else (False, f"{server_name} L2+")
        # F = full-pack-only servers (playwright, tradingview, gdrive,
        # google-drive, code-review-graph, ...).
        if level >= 2:
            if pack == "full":
                return True, ""
            return False, f"{server_name} requires full pack"
        return False, f"{server_name} L2+"

    # Track B — CLI (xai/grok, codex)
    if server_name in CLI_DEFAULT_DENY_SERVERS and not allow_cli_dangerous:
        return False, f"{server_name} in CLI default deny"
    if server_name == "filesystem":
        # L1: admitted (writes fine-denied via grok_mcp_deny_rules_for_level).
        return (True, "") if level >= 1 else (False, "filesystem L1+")
    if server_name in {"fetch", "memory"}:
        return (True, "") if level >= 2 else (False, f"{server_name} L2+")
    if server_name == "execute_code":
        # L3+ only on CLI — prevents arbitrary code exec under --always-approve.
        return (True, "") if level >= 3 else (False, "execute_code CLI L3+")
    if level >= 2:
        if pack == "full":
            return True, ""
        return False, f"{server_name} requires full pack"
    return False, f"{server_name} L2+"


def servers_for_level(
    server_names,
    *,
    level: int,
    backend: str,
    pack: str = "full",
    extras: frozenset[str] | None = None,
    allow_cli_dangerous: bool = False,
) -> tuple[frozenset[str], list[tuple[str, str]]]:
    """Filter a collection of server names through the admission matrix.

    Returns (admitted_names, denied_with_reasons). Deny reasons are stable
    strings suitable for logging or the ResolvedToolSurface.debug payload.
    """
    admitted: set[str] = set()
    denied: list[tuple[str, str]] = []
    for name in server_names:
        ok, reason = admit_server(
            name,
            level=level,
            backend=backend,
            pack=pack,
            extras=extras,
            in_catalog=True,
            allow_cli_dangerous=allow_cli_dangerous,
        )
        if ok:
            admitted.add(name)
        else:
            denied.append((name, reason))
    return frozenset(admitted), denied


# ---------------------------------------------------------------------------
# Turn-level resolvers (PR1c) — one-stop load+inject for a specific chat turn
# ---------------------------------------------------------------------------


def resolve_for_grok(
    chat_id: str | None,
    *,
    workspace: str,
    permission_level: int = 2,
    computer_use_target: str | None = None,
    interceptor_enabled: bool = False,
    extra_allowed_tools: frozenset[str] | None = None,
    pack: str = "full",
) -> dict[str, dict]:
    """Load + inject the Apex MCP catalog for a Grok CLI turn.

    Mirrors the sequence in ``streaming._build_sdk_options`` so Grok gets the
    same server set Claude would. Caller passes the result to
    ``project_grok(servers)`` to render the temp GROK_HOME.

    Args mirror ``streaming.py`` call sites; safe defaults so ``_run_grok_chat``
    can call this without extra plumbing on day one.
    """
    servers = load_enabled_mcp_servers(strip_enabled_key=True)
    servers = inject_execute_code_mcp(
        servers,
        chat_id=chat_id,
        workspace=workspace,
        permission_level=permission_level,
    )
    servers = inject_claim_store_mcp(servers, chat_id=chat_id)
    servers = inject_computer_use_mcp(
        servers,
        chat_id=chat_id,
        permission_level=permission_level,
        computer_use_target=computer_use_target,
    )
    servers = inject_interceptor_mcp(
        servers,
        chat_id=chat_id,
        interceptor_enabled=interceptor_enabled,
    )
    if extra_allowed_tools:
        servers = inject_guide_tools_mcp(servers)
    # PR1b: apply Track B (CLI) admission matrix. Denies computer_use /
    # interceptor / execute_code at L2 on CLI (would run under --always-approve
    # with no runtime gate), gates claim_store to extras or L3+ full pack.
    admitted, denied = servers_for_level(
        servers.keys(),
        level=permission_level,
        backend="xai",
        pack=pack,
        extras=extra_allowed_tools,
    )
    if denied:
        log(
            "grok tool_surface denied "
            f"(L{permission_level}/pack={pack}): {denied}"
        )
    return {k: v for k, v in servers.items() if k in admitted}


# ---------------------------------------------------------------------------
# Grok CLI projector (PR1b) — locked to PR0 spike results 2026-07-09
# ---------------------------------------------------------------------------

# Filesystem write tools requiring --deny at L1 (verified in PR0 §3).
_GROK_FILESYSTEM_WRITE_TOOLS = (
    "filesystem__write_file",
    "filesystem__edit_file",
    "filesystem__create_directory",
    "filesystem__move_file",
)

# Grok CLI permission rules use CLAUDE CODE category names (Bash, Edit,
# Write, etc.), not the internal tool names (run_terminal_command, etc.).
# Verified 2026-07-09: `--deny 'Bash'` denies run_terminal_command via
# "Denied by permission policy: deny rule on bash". `--disallowed-tools`
# does NOT gate builtins — must use `--deny` with rule syntax.
#
# Rule categories:
#   Bash    — shell (run_terminal_command)
#   Edit    — search_replace, edit_file variants
#   Write   — write, write_file, create_file
#   Read    — file reads (always safe; never deny)
#   Grep    — content search (always safe; never deny)
#   WebFetch, WebSearch — web ops

_GROK_DENY_WRITE_RULES = ("Bash", "Edit", "Write")
_GROK_DENY_WEB_RULES = ("WebFetch",)


def grok_deny_rules_for_level(level: int) -> list[str]:
    """Return grok CLI --deny rules to pass for the given Apex permission
    level. Each returned string is a rule ready for `--deny <rule>`.

    Matches Claude SDK level semantics so a chat switched between Claude
    and Grok has the same effective capability:
      L0 (guide-only):  Bash, Edit, Write + WebFetch
      L1 (read-only):   Bash, Edit, Write
      L2 (default):     Bash, Edit, Write  (Claude L2 has no bash either)
      L3 (elevated):    no builtin denies
      L4 (full):        no builtin denies
    """
    if level >= 3:
        return []
    if level <= 0:
        return list(_GROK_DENY_WRITE_RULES) + list(_GROK_DENY_WEB_RULES)
    return list(_GROK_DENY_WRITE_RULES)


def grok_mcp_deny_rules_for_level(level: int) -> list[str]:
    """Return grok CLI --deny MCPTool(...) rules for the given level.

    L1 (read-only): fine-deny filesystem MCP write tools per PR0 §3
      (write_file, edit_file, create_directory, move_file). Server itself
      is still attached so reads work — CLI has no runtime gate, so writes
      must be blocked at admission.

    L0: filesystem is denied at server admission (see servers_for_level),
      so no per-tool rule needed here.

    L2+: filesystem writes are allowed. Matches Claude L2 which relies on
      the SDK's runtime gate; Grok has no runtime gate but the level
      threshold is chosen to match Claude L2's effective write capability.
    """
    if level == 1:
        return [f"MCPTool({name})" for name in _GROK_FILESYSTEM_WRITE_TOOLS]
    return []


def _serialize_toml_value(value: Any) -> str:
    """Minimal TOML value serializer for MCP server blocks.

    Handles str, int, bool, list[str], dict[str, str] — the shapes Apex's
    MCP server specs actually use. Not a general TOML serializer.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)  # JSON string escaping is TOML-compatible
    if isinstance(value, list):
        return "[" + ", ".join(_serialize_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        parts = [f"{k} = {_serialize_toml_value(v)}" for k, v in value.items()]
        return "{ " + ", ".join(parts) + " }"
    return json.dumps(str(value))


def _render_grok_mcp_block(name: str, spec: dict) -> str:
    """Render a single [mcp_servers.<name>] TOML block from an Apex spec."""
    lines = [f'[mcp_servers."{name}"]']
    for key in ("command", "args", "env", "cwd"):
        if key in spec:
            lines.append(f"{key} = {_serialize_toml_value(spec[key])}")
    # Default startup timeout for npx-launched servers (spec §4.d)
    if spec.get("command", "").endswith("npx"):
        lines.append("startup_timeout_sec = 60")
    return "\n".join(lines) + "\n"


def _strip_mcp_server_sections(toml_text: str) -> str:
    """Remove existing [mcp_servers.*] blocks from a TOML file's text.

    Naive block-based scanner — Grok's own config.toml is line-oriented and
    doesn't nest mcp_servers under other tables, so this holds. If the CLI
    starts nesting we'll need a real TOML parser.
    """
    out_lines: list[str] = []
    skipping = False
    for line in toml_text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[mcp_servers.") or stripped == "[mcp_servers]":
            skipping = True
            continue
        if skipping and stripped.startswith("[") and stripped.endswith("]"):
            # New non-mcp_servers section starts — resume copying.
            skipping = False
        if not skipping:
            out_lines.append(line)
    return "".join(out_lines)


def _force_compat_mcps_off(toml_text: str) -> str:
    """Ensure `[compat.claude]` and `[compat.cursor]` both have `mcps = false`.

    - If the section exists, rewrite any `mcps = ...` inside it to `false`
      (and add the line if missing before the next section).
    - If the section is absent, append a fresh `[section]\\nmcps = false`.

    Naive line scanner — matches the same TOML shape assumptions as
    _strip_mcp_server_sections.
    """
    lines = toml_text.splitlines(keepends=True)
    tail_nl = "\n" if lines and not lines[-1].endswith("\n") else ""
    if tail_nl:
        lines.append(tail_nl)

    def _rewrite(section_header: str) -> None:
        in_section = False
        wrote_mcps = False
        idx = 0
        while idx < len(lines):
            stripped = lines[idx].strip()
            if stripped == section_header:
                in_section = True
                idx += 1
                continue
            if in_section:
                if stripped.startswith("[") and stripped.endswith("]"):
                    # Section ended; if we never saw `mcps = ...`, inject before this line.
                    if not wrote_mcps:
                        lines.insert(idx, "mcps = false\n")
                        idx += 1
                        wrote_mcps = True
                    in_section = False
                    continue
                if stripped.startswith("mcps"):
                    lines[idx] = "mcps = false\n"
                    wrote_mcps = True
            idx += 1
        # Section was the last one in the file and had no mcps line.
        if in_section and not wrote_mcps:
            lines.append("mcps = false\n")

    for section in ("[compat.claude]", "[compat.cursor]"):
        section_present = any(l.strip() == section for l in lines)
        if section_present:
            _rewrite(section)
        else:
            lines.append(f"\n{section}\nmcps = false\n")

    return "".join(lines)


def _grok_home_symlink_layout(real_home: Path, temp_home: Path) -> None:
    """Symlink required + defensive-default entries from real_home into temp_home.

    Locked layout (PR0 §1):
      - REQUIRED: `auth.json`, `sessions/`
      - DEFENSIVE DEFAULT: every other real_home entry EXCEPT `config.toml`
      - `config.toml` is copied+merged separately by caller

    Never copies auth material — symlinks so CLI reads real files. Skips
    entries that don't exist in real_home. Any symlink target that doesn't
    exist is silently omitted so PR1b won't fail on a partial real home.
    """
    if not real_home.exists():
        # Real home doesn't exist yet — CLI will bootstrap it on next real
        # `grok login`; temp home just gets no symlinks. This is a corner
        # case for first-time users; not an error.
        return
    for entry in real_home.iterdir():
        if entry.name == "config.toml":
            continue
        target = temp_home / entry.name
        if target.exists() or target.is_symlink():
            continue
        try:
            os.symlink(entry, target)
        except OSError as e:
            log(f"grok temp home symlink skipped {entry.name}: {e}")


def project_grok(
    servers: dict[str, dict],
    *,
    real_grok_home: Path | None = None,
    cli_deny_tools: tuple[str, ...] = (),
) -> tuple[Path, dict[str, str], list[str]]:
    """Materialize a temp GROK_HOME with Apex MCP servers merged in.

    Returns:
      (temp_home, env_overrides, extra_cli_args)
      - temp_home: Path to a fresh mkdtemp'd home. Caller MUST pass to
        cleanup_projected_home() in a finally block.
      - env_overrides: dict to merge into subprocess env. Sets GROK_HOME +
        compat kill switches.
      - extra_cli_args: list of --deny MCPTool(...) argv fragments for the
        write-tool denylist. Concatenate into the grok CLI command.

    Args:
      servers: Apex-resolved MCP server dict (post-injects, post-filter).
      real_grok_home: Override for the durable ~/.grok. Defaults to
        ``Path.home() / ".grok"`` — **never** process env ``GROK_HOME``.
        (Env may already point at a prior Apex temp home; chaining those
        broke sessions/ tool-history capture — 2026-07-09.)
      cli_deny_tools: Wire names to append via --deny MCPTool(<name>).
        PR1b: default empty; deny rules are driven by
        ``grok_mcp_deny_rules_for_level`` in the caller so denies match
        the chat's permission level (writes denied only at L1).

    Design ref: docs/UNIFIED_TOOL_SURFACE_DESIGN.md §"Grok / backend xai —
    hard algorithm". PR0 spike results: docs/PR0_TOOL_SURFACE_SPIKES.md.
    """
    import tempfile
    import shutil

    if real_grok_home is None:
        # Durable user home only. Do NOT read os.environ["GROK_HOME"] — the
        # Apex server process may still hold a previous turn's temp path.
        real_grok_home = Path.home() / ".grok"
    real_grok_home = real_grok_home.expanduser().resolve()
    # Guard against accidental temp-home chaining if a caller passes garbage.
    if "apex-grok-home-" in real_grok_home.name:
        log(
            f"project_grok: refusing temp real_grok_home={real_grok_home}, "
            "falling back to ~/.grok"
        )
        real_grok_home = (Path.home() / ".grok").resolve()

    temp_home = Path(tempfile.mkdtemp(prefix="apex-grok-home-"))
    temp_home.chmod(0o700)

    # 1. Symlink required + defensive-default entries (excludes config.toml).
    _grok_home_symlink_layout(real_grok_home, temp_home)

    # 2. Copy + merge config.toml — strip existing MCP blocks, append Apex ones,
    #    force compat kill switches.
    real_config = real_grok_home / "config.toml"
    base_toml = real_config.read_text() if real_config.exists() else ""
    merged = _strip_mcp_server_sections(base_toml)
    if merged and not merged.endswith("\n"):
        merged += "\n"

    # Ensure compat kill switches — force off both Claude & Cursor MCP merges
    # so project .mcp.json etc. don't leak in. Rewrites existing `mcps = true`
    # to `false` inside [compat.claude] / [compat.cursor] blocks (Grok's review
    # 2026-07-09: earlier "append only if missing" logic failed to force
    # `false` when user had explicitly set `true`).
    merged = _force_compat_mcps_off(merged)

    for name, spec in servers.items():
        merged += "\n" + _render_grok_mcp_block(name, spec)

    (temp_home / "config.toml").write_text(merged)

    # 3. Env overrides — never mutate os.environ; caller merges into subprocess env.
    env_overrides = {
        "GROK_HOME": str(temp_home),
        "GROK_CLAUDE_MCPS_ENABLED": "0",
        "GROK_CURSOR_MCPS_ENABLED": "0",
    }

    # 4. --deny MCPTool(<tool>) argv fragments for write denies.
    extra_cli_args: list[str] = []
    for tool in cli_deny_tools:
        extra_cli_args.extend(["--deny", f"MCPTool({tool})"])

    return temp_home, env_overrides, extra_cli_args


def cleanup_projected_home(path: Path | None) -> None:
    """Best-effort rmtree of a temp home only. NEVER touches real ~/.grok/~/.codex.

    Safety: path must be under $TMPDIR / /tmp / /var/folders (macOS mkdtemp)
    and must have the apex-grok-home- or apex-codex-home- prefix. Guards
    against accidentally being pointed at a real home.
    """
    if path is None:
        return
    import tempfile
    import shutil as _shutil
    try:
        resolved = path.resolve()
        # Must be under system tempdir.
        tmp_root = Path(tempfile.gettempdir()).resolve()
        if not str(resolved).startswith(str(tmp_root)):
            log(f"cleanup_projected_home refused: {resolved} not under {tmp_root}")
            return
        # Must have expected prefix.
        if not (
            resolved.name.startswith("apex-grok-home-")
            or resolved.name.startswith("apex-codex-home-")
        ):
            log(f"cleanup_projected_home refused: {resolved} lacks apex prefix")
            return
        _shutil.rmtree(resolved, ignore_errors=True)
    except (OSError, ValueError) as e:
        log(f"cleanup_projected_home error: {e}")
