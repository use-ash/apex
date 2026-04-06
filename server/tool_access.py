"""Shared tool-access policy for SDK and tool-loop backends."""
from __future__ import annotations

import json
from typing import Iterable

import env
from local_model.safety import ensure_workspace_path, validate_command
from log import log

SDK_TOOL_NAME_MAP = {
    "Bash": "bash",
    "Read": "read_file",
    "Write": "write_file",
    "Edit": "edit_file",
    "MultiEdit": "write_file",
    "NotebookEdit": "write_file",
    "LS": "list_files",
    "Glob": "list_files",
    "Grep": "search_files",
    "WebFetch": "fetch__fetch",
    "WebSearch": "fetch__fetch",
    "ToolSearch": "tool_search",
    "Skill": "skill",
    "Agent": "agent",
}

STANDARD_LOCAL_TOOLS = frozenset({"read_file", "list_files", "search_files"})
BUILTIN_LOCAL_TOOLS = frozenset(
    {"bash", "read_file", "write_file", "edit_file", "list_files", "search_files",
     "execute_code"}
)
DEFAULT_LEVEL2_TOOL_PATTERNS = (
    "bash",
    "read_file",
    "write_file",
    "edit_file",
    "list_files",
    "search_files",
    "fetch__*",
    "playwright__*",
    "filesystem__read_file",
    "filesystem__read_text_file",
    "filesystem__read_media_file",
    "filesystem__read_multiple_files",
    "filesystem__list_directory",
    "filesystem__list_directory_with_sizes",
    "filesystem__directory_tree",
    "filesystem__search_files",
    "filesystem__get_file_info",
    "filesystem__list_allowed_directories",
)

TOOL_POLICY_CATALOG = {
    "bash": {
        "name": "Shell Command",
        "description": "Run tightly restricted shell commands using the level's command rules.",
        "category": "built-in",
        "group": "shell",
    },
    "read_file": {
        "name": "Read File",
        "description": "Read a single file from allowed workspace roots.",
        "category": "built-in",
        "group": "read",
    },
    "write_file": {
        "name": "Write File",
        "description": "Create or overwrite entire files in allowed writable roots for the current level.",
        "category": "built-in",
        "group": "write",
    },
    "edit_file": {
        "name": "Edit File",
        "description": "Surgically edit a file by replacing a specific text span — more precise than write_file.",
        "category": "built-in",
        "group": "write",
    },
    "list_files": {
        "name": "List Files",
        "description": "List directories and discover files inside allowed roots.",
        "category": "built-in",
        "group": "read",
    },
    "search_files": {
        "name": "Search Files",
        "description": "Search file contents inside allowed workspace roots.",
        "category": "built-in",
        "group": "read",
    },
    "execute_code": {
        "name": "Execute Code",
        "description": "Run Python in a stateful Jupyter kernel. Level 3+ only.",
        "category": "built-in",
        "group": "execute",
    },
    "fetch__*": {
        "name": "Fetch MCP",
        "description": "Fetch web content through the MCP fetch server.",
        "category": "mcp",
        "group": "network",
    },
    "playwright__*": {
        "name": "Playwright MCP",
        "description": "Drive a browser for live UI validation and testing.",
        "category": "mcp",
        "group": "browser",
    },
    "filesystem__read_file": {
        "name": "Filesystem: Read File",
        "description": "Read a file through the filesystem MCP server.",
        "category": "mcp",
        "group": "read",
    },
    "filesystem__read_text_file": {
        "name": "Filesystem: Read Text File",
        "description": "Read text content through the filesystem MCP server.",
        "category": "mcp",
        "group": "read",
    },
    "filesystem__read_media_file": {
        "name": "Filesystem: Read Media File",
        "description": "Read image or media data through the filesystem MCP server.",
        "category": "mcp",
        "group": "read",
    },
    "filesystem__read_multiple_files": {
        "name": "Filesystem: Read Multiple Files",
        "description": "Read a batch of files from allowed directories.",
        "category": "mcp",
        "group": "read",
    },
    "filesystem__list_directory": {
        "name": "Filesystem: List Directory",
        "description": "List one directory through the filesystem MCP server.",
        "category": "mcp",
        "group": "read",
    },
    "filesystem__list_directory_with_sizes": {
        "name": "Filesystem: List Directory With Sizes",
        "description": "List a directory with file size metadata.",
        "category": "mcp",
        "group": "read",
    },
    "filesystem__directory_tree": {
        "name": "Filesystem: Directory Tree",
        "description": "Inspect a directory tree through the filesystem MCP server.",
        "category": "mcp",
        "group": "read",
    },
    "filesystem__search_files": {
        "name": "Filesystem: Search Files",
        "description": "Search files by pattern through the filesystem MCP server.",
        "category": "mcp",
        "group": "read",
    },
    "filesystem__get_file_info": {
        "name": "Filesystem: File Info",
        "description": "Read metadata for a file or directory.",
        "category": "mcp",
        "group": "read",
    },
    "filesystem__list_allowed_directories": {
        "name": "Filesystem: Allowed Directories",
        "description": "Show the current filesystem MCP root directories.",
        "category": "mcp",
        "group": "read",
    },
    "filesystem__write_file": {
        "name": "Filesystem: Write File",
        "description": "Write a file through the filesystem MCP server.",
        "category": "mcp",
        "group": "write",
    },
    "filesystem__edit_file": {
        "name": "Filesystem: Edit File",
        "description": "Edit an existing file through the filesystem MCP server.",
        "category": "mcp",
        "group": "write",
    },
    "filesystem__create_directory": {
        "name": "Filesystem: Create Directory",
        "description": "Create a directory through the filesystem MCP server.",
        "category": "mcp",
        "group": "write",
    },
    "filesystem__move_file": {
        "name": "Filesystem: Move File",
        "description": "Move or rename a file through the filesystem MCP server.",
        "category": "mcp",
        "group": "write",
    },
    "memory__*": {
        "name": "Memory MCP",
        "description": "Read or mutate the shared structured memory graph.",
        "category": "mcp",
        "group": "memory",
    },
    "tool_search": {
        "name": "Tool Search",
        "description": "Search available tools and capabilities before choosing a next action.",
        "category": "sdk",
        "group": "coordination",
    },
    "skill": {
        "name": "Skill",
        "description": "Invoke a registered skill workflow inside Apex.",
        "category": "sdk",
        "group": "coordination",
    },
    "agent": {
        "name": "Agent",
        "description": "Delegate work to another agent as part of a collaborative workflow.",
        "category": "sdk",
        "group": "coordination",
    },
}


def canonical_tool_name(tool_name: str) -> str:
    canonical = SDK_TOOL_NAME_MAP.get(tool_name, tool_name or "")
    while canonical.startswith("mcp__"):
        canonical = canonical[len("mcp__") :]
    return canonical


def _iter_mcp_tool_names() -> list[str]:
    try:
        from local_model.mcp_bridge import get_mcp_tool_schemas

        names: list[str] = []
        for schema in get_mcp_tool_schemas():
            name = str(schema.get("function", {}).get("name") or "").strip()
            if name:
                names.append(name)
        return names
    except Exception:
        return []


def _normalize_tool_patterns(raw: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for item in raw:
        value = canonical_tool_name(str(item).strip())
        if not value:
            continue
        if value not in TOOL_POLICY_CATALOG:
            continue
        if value not in seen:
            seen.append(value)
    return seen


def _read_policy_config() -> dict:
    config_path = env.APEX_ROOT / "state" / "config.json"
    try:
        if config_path.exists():
            data = json.loads(config_path.read_text())
            if isinstance(data, dict):
                return data.get("policy", {}) or {}
    except Exception:
        pass
    return {}


def get_workspace_tool_patterns() -> list[str]:
    policy = _read_policy_config()
    raw = policy.get("workspace_tools", "")
    if isinstance(raw, list):
        patterns = _normalize_tool_patterns(raw)
        return patterns or list(DEFAULT_LEVEL2_TOOL_PATTERNS)
    text = str(raw or "").replace("\r\n", "\n").replace("\r", "\n")
    items: list[str] = []
    for line in text.split("\n"):
        for chunk in line.split(","):
            item = chunk.strip()
            if item:
                items.append(item)
    patterns = _normalize_tool_patterns(items)
    return patterns or list(DEFAULT_LEVEL2_TOOL_PATTERNS)


def tool_matches_pattern(tool_name: str, pattern: str) -> bool:
    canonical = canonical_tool_name(tool_name)
    normalized = canonical_tool_name(pattern)
    if normalized.endswith("*"):
        return canonical.startswith(normalized[:-1])
    return canonical == normalized


def _tool_is_catalogued(tool_name: str) -> bool:
    canonical = canonical_tool_name(tool_name)
    return any(tool_matches_pattern(canonical, pattern) for pattern in TOOL_POLICY_CATALOG)


def _iter_tool_input_paths(tool_input: dict, keys: tuple[str, ...]) -> list[str]:
    if not isinstance(tool_input, dict):
        return []

    paths: list[str] = []
    for key in keys:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(value.strip())
            continue
        if isinstance(value, list):
            paths.extend(str(item).strip() for item in value if str(item).strip())
    return paths


def _is_dangerous_policy_error(message: str) -> bool:
    text = message or ""
    return (
        "access to live Apex database is blocked" in text
        or "access to blocked path is denied by system policy" in text
        or "command is denied by system policy" in text
    )


def _summarize_dangerous_intent(tool_name: str, tool_input: dict) -> str:
    canonical = canonical_tool_name(tool_name)
    if canonical == "bash":
        command = str((tool_input or {}).get("command") or "").strip()
        return command[:240]

    paths = _iter_tool_input_paths(
        tool_input,
        ("path", "file_path", "new_path", "old_path", "paths", "notebook_path"),
    )
    if paths:
        joined = ", ".join(paths[:4])
        if len(paths) > 4:
            joined += ", ..."
        return joined[:240]

    try:
        return json.dumps(tool_input, sort_keys=True)[:240]
    except Exception:
        return str(tool_input)[:240]


def _log_dangerous_tool_intent(
    tool_name: str,
    tool_input: dict,
    *,
    level: int,
    message: str,
    audit_context: dict | None = None,
) -> None:
    if not _is_dangerous_policy_error(message):
        return
    summary = _summarize_dangerous_intent(tool_name, tool_input)
    context = {
        str(k): str(v)
        for k, v in (audit_context or {}).items()
        if v not in (None, "")
    }
    context_text = " ".join(f"{k}={context[k]!r}" for k in sorted(context))
    log(
        "dangerous tool intent blocked: "
        f"level={level} tool={canonical_tool_name(tool_name)} "
        f"{context_text + ' ' if context_text else ''}"
        f"detail={summary!r} reason={message}"
    )


def get_tool_catalog() -> list[dict[str, str | bool]]:
    workspace_set = set(get_workspace_tool_patterns())
    items: list[dict[str, str | bool]] = []
    for tool_id, meta in TOOL_POLICY_CATALOG.items():
        items.append(
            {
                "id": tool_id,
                "name": str(meta["name"]),
                "description": str(meta["description"]),
                "category": str(meta["category"]),
                "group": str(meta.get("group") or meta["category"]),
                "workspace_default": tool_id in DEFAULT_LEVEL2_TOOL_PATTERNS,
                "workspace_enabled": tool_id in workspace_set,
            }
        )
    items.sort(key=lambda item: (str(item["category"]), str(item["name"])))
    return items


def tool_allowed_for_level(name: str, level: int) -> bool:
    canonical = canonical_tool_name(name)
    if level <= 0:
        return False
    if level >= 4:
        return True
    if level == 1:
        return canonical in STANDARD_LOCAL_TOOLS
    if level == 2:
        return any(tool_matches_pattern(canonical, pattern) for pattern in get_workspace_tool_patterns())
    return _tool_is_catalogued(canonical)


def allowed_tool_names_for_level(level: int) -> set[str] | None:
    if level <= 0:
        return set()
    if level >= 4:
        return None

    allowed = {
        name for name in BUILTIN_LOCAL_TOOLS
        if tool_allowed_for_level(name, level)
    }
    allowed.update(
        name for name in _iter_mcp_tool_names()
        if tool_allowed_for_level(name, level)
    )
    return allowed


def tool_access_decision(
    tool_name: str,
    tool_input: dict,
    *,
    level: int,
    allowed_commands: list[str] | None,
    workspace_paths: str,
    audit_context: dict | None = None,
) -> tuple[bool, str]:
    def _deny(message: str) -> tuple[bool, str]:
        _log_dangerous_tool_intent(
            tool_name,
            tool_input,
            level=level,
            message=message,
            audit_context=audit_context,
        )
        return False, message

    if level <= 0:
        return False, "This agent is Restricted and cannot use tools or access files."

    canonical = canonical_tool_name(tool_name)
    if not tool_allowed_for_level(canonical, level):
        if level == 1:
            return False, "This action requires Elevated or Admin permissions."
        return False, f"Error: tool is not allowed at this permission level: {tool_name}"

    if canonical == "bash":
        command = str((tool_input or {}).get("command") or "").strip()
        command_err = validate_command(
            command,
            workspace_paths.split(":")[0].strip() or None,
            permission_level=level,
            allowed_commands=allowed_commands,
        )
        if command_err:
            return _deny(command_err)
        return True, ""

    if canonical in {"read_file", "list_files", "search_files"}:
        path_keys = ("path", "file_path")
        allow_write = False
    elif canonical in {"write_file", "edit_file"}:
        path_keys = ("path", "file_path", "new_path", "old_path", "notebook_path")
        allow_write = True
    else:
        path_keys = ()
        allow_write = False

    if canonical.startswith("filesystem__"):
        if canonical in {
            "filesystem__write_file",
            "filesystem__edit_file",
            "filesystem__create_directory",
            "filesystem__move_file",
        }:
            allow_write = True
            path_keys = ("path", "file_path", "new_path", "old_path")
        elif canonical != "filesystem__list_allowed_directories":
            path_keys = ("path", "file_path")

    if canonical == "filesystem__read_multiple_files":
        path_keys = ("paths",)

    if path_keys:
        for raw_path in _iter_tool_input_paths(tool_input, path_keys):
            _, err = ensure_workspace_path(
                raw_path,
                workspace_paths,
                allow_write=allow_write,
                permission_level=level,
            )
            if err:
                return _deny(err)
    return True, ""
