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
    from env import WORKSPACE  # type: ignore[import]
except ImportError:
    import os
    WORKSPACE = Path(os.environ.get("APEX_WORKSPACE", os.getcwd()))


def _read_safe(path: Path, max_chars: int = 0) -> str:
    """Read a file, return empty string on failure."""
    try:
        text = path.read_text()
        return text[:max_chars] if max_chars else text
    except Exception:
        return ""


def build_system_prompt(model: str) -> str:
    """Build a condensed system prompt for a local model."""
    if model.startswith("grok-"):
        parts = ["You are Grok, made by xAI. You are running as a channel in the Apex server."]
        parts.append("You are NOT Claude, NOT a local model. You are Grok.")
    else:
        parts = [f"You are a local AI assistant running {model} via Ollama."]
        parts.append("You are NOT Claude, NOT made by Anthropic.")
    # Build dynamic tool list (built-in + MCP)
    tool_names = ["bash", "read_file", "write_file", "list_files", "search_files"]
    try:
        from local_model.mcp_bridge import get_mcp_tool_schemas
        mcp_tools = get_mcp_tool_schemas()
        for t in mcp_tools:
            tool_names.append(t["function"]["name"])
    except Exception:
        pass
    parts.append(f"You have tools: {', '.join(tool_names)}. Use them to answer questions and complete tasks.")
    parts.append("")

    # Workspace context
    ws = str(WORKSPACE)
    python_exe = sys.executable or "python3"
    parts.append("## Workspace")
    parts.append(f"- Root: {ws}")
    parts.append(f"- Python: {python_exe}")
    parts.append("")

    # Inject APEX.md (or CLAUDE.md fallback) summary if available
    apex_md = WORKSPACE / "APEX.md"
    claude_md = WORKSPACE / "CLAUDE.md"
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
    if project_md.exists():
        parts.append(f"- Start with: read_file('{project_md}') for full project context")
    parts.append("")

    # Available scripts (if workspace has skills or tools)
    skills_dir = WORKSPACE / "skills"
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
        script = WORKSPACE / name
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
    memory_md = WORKSPACE / "memory" / "MEMORY.md"
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
