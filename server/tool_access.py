"""Shared tool-access policy for SDK and tool-loop backends."""
from __future__ import annotations

from typing import Iterable

from local_model.safety import ensure_workspace_path, validate_command

SDK_TOOL_NAME_MAP = {
    "Bash": "bash",
    "Read": "read_file",
    "Write": "write_file",
    "Edit": "write_file",
    "MultiEdit": "write_file",
    "NotebookEdit": "write_file",
    "LS": "list_files",
    "Glob": "list_files",
    "Grep": "search_files",
    "WebFetch": "fetch__fetch",
    "WebSearch": "fetch__fetch",
}

STANDARD_LOCAL_TOOLS = frozenset({"read_file", "list_files", "search_files"})
BUILTIN_LOCAL_TOOLS = frozenset(
    {"bash", "read_file", "write_file", "list_files", "search_files"}
)
LEVEL2_ALLOWED_MCP_PREFIXES = ("playwright__", "fetch__")
LEVEL2_ALLOWED_MCP_EXACT = frozenset(
    {
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
    }
)


def canonical_tool_name(tool_name: str) -> str:
    return SDK_TOOL_NAME_MAP.get(tool_name, tool_name or "")


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


def _allow_level2_mcp_tool(name: str) -> bool:
    if name in LEVEL2_ALLOWED_MCP_EXACT:
        return True
    return any(name.startswith(prefix) for prefix in LEVEL2_ALLOWED_MCP_PREFIXES)


def tool_allowed_for_level(name: str, level: int) -> bool:
    canonical = canonical_tool_name(name)
    if level <= 0:
        return False
    if level >= 4:
        return True
    if canonical in BUILTIN_LOCAL_TOOLS:
        return level >= 2 or canonical in STANDARD_LOCAL_TOOLS
    if canonical.startswith("filesystem__"):
        return level >= 3 or _allow_level2_mcp_tool(canonical)
    if canonical.startswith("playwright__") or canonical.startswith("fetch__"):
        return level >= 2
    if canonical.startswith("memory__"):
        return level >= 3
    return level >= 3


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
) -> tuple[bool, str]:
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
            return False, command_err
        return True, ""

    if canonical in {"read_file", "list_files", "search_files"}:
        path_keys = ("path", "file_path")
        allow_write = False
    elif canonical == "write_file":
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

    if path_keys:
        for key in path_keys:
            raw_path = str((tool_input or {}).get(key) or "").strip()
            if not raw_path:
                continue
            _, err = ensure_workspace_path(
                raw_path,
                workspace_paths,
                allow_write=allow_write,
                permission_level=level,
            )
            if err:
                return False, err
    return True, ""
