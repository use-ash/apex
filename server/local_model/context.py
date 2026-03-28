"""Build condensed system context for local models.

Reads CLAUDE.md and MEMORY.md from the workspace to produce a compact
system prompt that gives local models essential workspace knowledge
without overwhelming the context window. Target: ~2K tokens.
"""
import os
import sys
from pathlib import Path

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
    parts.append("You have tools: bash, read_file, write_file, list_files, search_files. Use them to answer questions and complete tasks.")
    parts.append("")

    # Workspace context
    ws = str(WORKSPACE)
    python_exe = sys.executable or "python3"
    parts.append("## Workspace")
    parts.append(f"- Root: {ws}")
    parts.append(f"- Python: {python_exe}")
    parts.append("")

    # Inject CLAUDE.md / APEX.md summary if available
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

    # Available scripts (if workspace has skills)
    skills_dir = WORKSPACE / "skills"
    if skills_dir.is_dir():
        parts.append("## Skills (use via bash tool)")
        recall_script = skills_dir / "recall" / "search_transcripts.py"
        if recall_script.exists():
            parts.append(f"- Recall past conversations: {python_exe} {recall_script} '<query>' --top 5")
        embedding_script = skills_dir / "embedding" / "memory_search.py"
        if embedding_script.exists():
            parts.append(f"- Semantic memory search: {python_exe} {embedding_script} search '<query>' --top 5")
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
