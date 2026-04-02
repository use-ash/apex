"""Template generators for APEX.md, memory index, and memory files.

Produces the configuration files that define an Apex workspace: the main
APEX.md agent instructions file and the structured memory system.
All output is scrubbed for secrets before returning.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from setup.scanner import ConventionInfo, DocInfo, ProjectInfo, scrub_text

# ---------------------------------------------------------------------------
# Personality mappings
# ---------------------------------------------------------------------------

WORK_STYLES: dict[str, str] = {
    "direct": (
        "Communicate directly and concisely. Lead with the answer, "
        "not the reasoning."
    ),
    "thorough": (
        "Be thorough and detailed. Explain your reasoning and cover "
        "edge cases."
    ),
    "conversational": (
        "Be conversational and collaborative. Think out loud, invite input."
    ),
}

EXPERTISE_LEVELS: dict[str, str] = {
    "peer": (
        "Assume the user is an experienced developer. Skip basics, "
        "don't over-explain."
    ),
    "mentor": (
        "Explain concepts when relevant, but don't be condescending."
    ),
    "beginner": (
        "Explain everything clearly. Suggest resources. Be patient "
        "with questions."
    ),
}

PERSONALITIES: dict[str, str] = {
    "professional": (
        "Be focused and efficient. Minimal small talk. Get things done."
    ),
    "collaborative": (
        "Be an engaged partner. Ask good questions. Push back when "
        "something seems wrong."
    ),
    "casual": (
        "Be relaxed and informal. Like a smart coworker at a whiteboard."
    ),
}


# ---------------------------------------------------------------------------
# APEX.md generator
# ---------------------------------------------------------------------------

def generate_apex_md(
    personality: dict,
    projects: list[ProjectInfo],
    conventions: list[ConventionInfo],
    docs: list[DocInfo],
    workspace: Path,
    custom_rules: list[str],
    permission_mode: str = "suggest",
) -> str:
    """Build the APEX.md content from wizard inputs.

    All output is scrubbed for secrets before returning.

    Parameters
    ----------
    personality : dict
        Keys: work_style, expertise, personality, custom_rules.
    projects : list[ProjectInfo]
        Detected projects to document.
    conventions : list[ConventionInfo]
        Detected coding conventions.
    docs : list[DocInfo]
        Documentation files to reference.
    workspace : Path
        Root workspace directory.
    custom_rules : list[str]
        Additional user-specified rules.
    permission_mode : str
        Current permission level (e.g. "suggest", "auto-edit", "full-auto").
    """
    sections: list[str] = []

    # --- Identity ---
    work_style_text = WORK_STYLES.get(
        personality.get("work_style", "direct"), WORK_STYLES["direct"]
    )
    expertise_text = EXPERTISE_LEVELS.get(
        personality.get("expertise", "peer"), EXPERTISE_LEVELS["peer"]
    )
    personality_text = PERSONALITIES.get(
        personality.get("personality", "professional"),
        PERSONALITIES["professional"],
    )

    identity_lines = [
        "# Apex",
        "",
        "## Identity",
        "You are an AI assistant working in the user's workspace.",
        work_style_text,
        expertise_text,
        personality_text,
    ]

    # Custom personality rules
    p_rules = personality.get("custom_rules", [])
    if p_rules:
        identity_lines.append("")
        for rule in p_rules:
            identity_lines.append(f"- {rule}")

    sections.append("\n".join(identity_lines))

    # --- Permissions ---
    permissions = dedent(f"""\
        ## Permissions
        Current mode: {permission_mode}
        - In "suggest" mode: describe what you would do and ask for approval.
        - In "auto-edit" mode: make file edits freely, but ask before destructive ops.
        - In "full-auto" mode: execute tasks end-to-end, report results.
        - If a task would benefit from a higher permission level, suggest upgrading.""")
    sections.append(permissions)

    # --- Workspace ---
    sections.append(f"## Workspace\nWorking directory: `{workspace}`")

    # --- Projects ---
    if projects:
        proj_lines = ["## Projects"]
        for proj in projects:
            proj_lines.append(f"### {proj.name} ({proj.project_type})")
            proj_lines.append(f"- Config: `{proj.config_path}`")
            if proj.entry_points:
                eps = ", ".join(f"`{ep}`" for ep in proj.entry_points)
                proj_lines.append(f"- Entry points: {eps}")
            if proj.dependencies:
                dep_str = ", ".join(proj.dependencies[:20])
                if len(proj.dependencies) > 20:
                    dep_str += f" (+{len(proj.dependencies) - 20} more)"
                proj_lines.append(f"- Dependencies: {dep_str}")
            if proj.python_version:
                proj_lines.append(f"- Python: {proj.python_version}")
            if proj.test_runner:
                proj_lines.append(f"- Test runner: {proj.test_runner}")
            proj_lines.append("")
        sections.append("\n".join(proj_lines))

    # --- Conventions ---
    if conventions:
        conv_lines = ["## Conventions"]
        for conv in conventions:
            conv_lines.append(f"### {conv.source}")
            for key, val in conv.conventions.items():
                conv_lines.append(f"- {key}: {val}")
            conv_lines.append("")
        sections.append("\n".join(conv_lines))

    # --- Key Documentation ---
    if docs:
        doc_lines = ["## Key Documentation"]
        for doc in docs:
            rel_path = doc.path
            try:
                rel_path = doc.path.relative_to(workspace)
            except ValueError:
                pass
            doc_lines.append(f"- `{rel_path}` — {doc.title}")
        sections.append("\n".join(doc_lines))

    # --- Rules ---
    rules_lines = ["## Rules"]
    if custom_rules:
        for rule in custom_rules:
            rules_lines.append(f"- {rule}")
    # Auto-detected rules
    rules_lines.append("- Always confirm before deleting files or running destructive commands.")
    rules_lines.append("- Respect .gitignore patterns when creating new files.")
    rules_lines.append("- Use the project's existing code style and conventions.")
    sections.append("\n".join(rules_lines))

    content = "\n\n".join(sections) + "\n"
    return scrub_text(content)


# ---------------------------------------------------------------------------
# Memory index generator
# ---------------------------------------------------------------------------

def generate_memory_index(
    projects: list[ProjectInfo],
    docs: list[DocInfo],
) -> str:
    """Generate memory/MEMORY.md content — a categorized index.

    Parameters
    ----------
    projects : list[ProjectInfo]
        Projects to index as memory files.
    docs : list[DocInfo]
        Documentation files to index.
    """
    lines = ["# Memory Index", ""]

    if projects:
        lines.append("## Projects")
        for proj in projects:
            safe_name = proj.name.replace(" ", "_").lower()
            desc = f"{proj.project_type} project"
            if proj.test_runner:
                desc += f", tests via {proj.test_runner}"
            lines.append(f"- [{proj.name}](memory/{safe_name}.md) — {desc}")
        lines.append("")

    if docs:
        lines.append("## Documentation")
        for doc in docs:
            safe_name = doc.path.stem.replace(" ", "_").lower()
            lines.append(
                f"- [{doc.title}](memory/{safe_name}.md) — "
                f"{_size_label(doc.size_bytes)}"
            )
        lines.append("")

    content = "\n".join(lines) + "\n"
    return scrub_text(content)


# ---------------------------------------------------------------------------
# Individual memory file generator
# ---------------------------------------------------------------------------

def generate_memory_file(
    name: str,
    description: str,
    content_summary: str,
) -> str:
    """Generate a single memory file with YAML frontmatter.

    Parameters
    ----------
    name : str
        The memory entry name.
    description : str
        One-line description.
    content_summary : str
        Summary text for the memory file body.
    """
    safe_summary = scrub_text(content_summary)
    lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
        "type: project",
        "---",
        "",
        safe_summary,
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _size_label(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
