"""Build condensed system context for local models.

Reads APEX.md and MEMORY.md from the workspace to produce a compact
system prompt that gives local models essential workspace knowledge
without overwhelming the context window. Target: ~2K tokens.
"""
import sys
from pathlib import Path

# Import WORKSPACE from the canonical env registry when running as part of the
# server package (server/ is in sys.path).  Fall back gracefully when this
# module is executed standalone (e.g. local tests).
try:
    import env as _env  # type: ignore[import]
except ImportError:
    import os
    _env = None


def _workspace_root() -> Path:
    if _env is not None:
        return _env.get_runtime_workspace_root()
    import os
    return Path(os.environ.get("APEX_WORKSPACE", os.getcwd()))


def _read_safe(path: Path, max_chars: int = 0) -> str:
    """Read a file, return empty string on failure."""
    try:
        text = path.read_text()
        return text[:max_chars] if max_chars else text
    except Exception:
        return ""


_LEVEL_NAMES = {0: "Restricted", 1: "Read-Only", 2: "Standard", 3: "Elevated", 4: "Admin"}
_LEVEL_DESCRIPTIONS = {
    0: "No tools available.",
    1: "Read-only file access only (read_file, list_files, search_files).",
    2: "Read/write files, bash (pre-approved commands only), filesystem read via MCP.",
    3: "All catalogued tools + extended bash allowlist (write/network commands included).",
    4: "Unrestricted shell — all commands permitted with no restrictions.",
}


def build_system_prompt(
    model: str,
    *,
    permission_level: int = 2,
    allowed_tool_names: set[str] | None = None,
) -> str:
    """Build a condensed system prompt for a local model."""
    if model.startswith("grok-"):
        parts = ["You are Grok, made by xAI. You are running as a channel in the Apex server."]
        parts.append("You are NOT Claude, NOT a local model. You are Grok.")
    else:
        parts = [f"You are a local AI assistant running {model} via Ollama."]
        parts.append("You are NOT Claude, NOT made by Anthropic.")

    # Collect tool names from registry (not hardcoded) + MCP
    try:
        from local_model.registry import TOOLS as _registered_tools
        all_tool_names = list(_registered_tools.keys())
    except Exception:
        all_tool_names = ["bash", "read_file", "write_file", "edit_file", "list_files", "search_files"]
    try:
        from local_model.mcp_bridge import get_mcp_tool_schemas
        mcp_tools = get_mcp_tool_schemas()
        for t in mcp_tools:
            all_tool_names.append(t["function"]["name"])
    except Exception:
        pass
    if allowed_tool_names is not None:
        tool_names = [n for n in all_tool_names if n in allowed_tool_names]
    else:
        tool_names = all_tool_names
    parts.append(f"You have tools: {', '.join(tool_names) if tool_names else 'none'}. Use them to answer questions and complete tasks.")
    if "execute_code" in tool_names:
        parts.append("IMPORTANT: For ALL Python code execution, you MUST use the execute_code tool — NEVER use bash to run Python. "
                     "execute_code runs a stateful Jupyter kernel where variables, imports, and definitions persist between calls. "
                     "This applies to any request involving Python code, scripts, calculations, or print statements.")
    parts.append("")

    # Permission level section — tells the model exactly what it can do this turn
    level_name = _LEVEL_NAMES.get(permission_level, str(permission_level))
    level_desc = _LEVEL_DESCRIPTIONS.get(permission_level, "")
    parts.append(f"## Permission Level: {permission_level} ({level_name})")
    parts.append(level_desc)
    if permission_level == 4:
        parts.append("You may run any shell command via the bash tool without restriction.")
    elif permission_level == 3:
        parts.append("Write tools and an extended bash allowlist are available. Output redirection (>) and backtick subshells are still blocked.")
    elif permission_level == 2:
        parts.append("Write tools (write_file, edit_file) are available. Bash is restricted to a pre-approved command set. MCP filesystem write tools require level 3.")
    elif permission_level == 1:
        parts.append("Only read-only tools are available. Do not attempt to write or run shell commands.")
    else:
        parts.append("No tools are available at this permission level.")
    parts.append("If a tool call fails due to permissions, explain this to the user and suggest upgrading the permission level in channel settings.")
    parts.append("")

    # Workspace context
    workspace = _workspace_root()
    ws = str(workspace)
    python_exe = sys.executable or "python3"
    parts.append("## Workspace")
    parts.append(f"- Root: {ws}")
    parts.append(f"- Python: {python_exe}")
    parts.append("")

    # Inject APEX.md (or CLAUDE.md fallback) summary if available
    apex_md = workspace / "APEX.md"
    claude_md = workspace / "CLAUDE.md"
    project_md = apex_md if apex_md.exists() else claude_md
    project_text = _read_safe(project_md, max_chars=3000)
    if project_text:
        parts.append("## Project Instructions (from {})".format(project_md.name))
        parts.append(project_text[:3000])
        parts.append("")

    # Efficient tool use guidance
    parts.append("## Tool Use Tips (conserve iterations)")
    parts.append("- Use read_file to read files directly by path — DON'T ls/find first")
    parts.append("- Use search_files with glob filter to narrow searches: search_files(pattern='def main', glob='*.py')")
    parts.append("- Use list_files only when you genuinely need to discover file names")
    parts.append("- Chain multiple reads in sequence rather than exploring directories")
    parts.append("- Use edit_file for surgical changes — provide old_text (exact match) and new_text. Don't rewrite entire files.")
    parts.append("- Prefer read_file/search_files/list_files over bash for file inspection. Avoid grep/cat/find via bash unless a direct tool cannot do the job.")
    parts.append("- Keep bash simple: one command at a time. Avoid heredocs, inline Python, complex chaining, and shell fallbacks unless absolutely necessary.")
    parts.append("- Uploaded files are real files under state/uploads. Do not treat /api/uploads/... as a literal filesystem path.")
    parts.append("- Private repo/process docs live in apex-private/ops-docs/REPO_CONVENTIONS.md, not apex/REPO_CONVENTIONS.md.")
    if project_md.exists():
        parts.append(f"- Start with: read_file('{project_md}') for full project context")
    parts.append("")

    # Available scripts (if workspace has skills or tools)
    skills_dir = workspace / "skills"
    skill_entries = []
    if skills_dir.is_dir():
        # Scan for Python scripts with docstrings in skills/
        for script in sorted(skills_dir.rglob("*.py")):
            if script.name.startswith("_") or "/lib/" in str(script):
                continue
            try:
                first_lines = script.read_text()[:800]
                # Extract docstring
                for marker in ('"""', "'''"):
                    start = first_lines.find(marker)
                    if start >= 0:
                        end = first_lines.find(marker, start + 3)
                        if end > start:
                            desc = first_lines[start + 3:end].strip().split("\n")[0]
                            skill_entries.append(f"- {script.name}: {desc} — `{python_exe} {script}`")
                            break
            except Exception:
                continue
    # Also check for standalone tool scripts in workspace root
    for name in ("fetch_x.py",):
        script = workspace / name
        if script.exists():
            try:
                first_lines = script.read_text()[:800]
                for marker in ('"""', "'''"):
                    start = first_lines.find(marker)
                    if start >= 0:
                        end = first_lines.find(marker, start + 3)
                        if end > start:
                            desc = first_lines[start + 3:end].strip().split("\n")[0]
                            skill_entries.append(f"- {name}: {desc} — `{python_exe} {script}`")
                            break
            except Exception:
                pass
    if skill_entries:
        parts.append("## Skills")
        parts.append("These are scripts you run using your `bash` tool. They are NOT standalone tools.")
        parts.append("Example: bash({\"command\": \"/opt/homebrew/bin/python3 /path/to/script.py 'argument'\"})")
        # Cap at 15 to avoid bloating context
        parts.extend(skill_entries[:15])
        parts.append("")

    # Safety rules
    parts.append("## Rules")
    parts.append("- NEVER modify production files without explicit confirmation")
    parts.append("- NEVER test against production data — copy to /tmp/ first")
    parts.append("")

    # Load active project list from MEMORY.md if available
    memory_md = workspace / "memory" / "MEMORY.md"
    memory_text = _read_safe(memory_md)
    if memory_text:
        next_idx = memory_text.find("## NEXT STEPS")
        if next_idx != -1:
            next_section = memory_text[next_idx:]
            lines = next_section.split("\n")
            parts.append("## Active TODO")
            for line in lines[1:]:
                line = line.strip()
                if line and line[0].isdigit() and "." in line[:4]:
                    if "~~" not in line:
                        parts.append(f"- {line[line.index('.')+2:]}")
                elif not line:
                    break
            parts.append("")

    return "\n".join(parts)
