"""Knowledge ingestion for Apex onboarding wizard (Phase 3).

Orchestrates workspace scanning, personality questionnaire, template
generation, and file writing. All text is scrubbed for secrets before
being written to disk.

SECURITY: Atomic file writes (temp + rename). scrub_text() on everything.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from setup.scanner import ScanResult, scrub_text, scan_workspace
from setup.templates import (
    generate_apex_md,
    generate_memory_file,
    generate_memory_index,
)
from setup.ui import (
    print_error,
    print_header,
    print_info,
    print_step,
    print_success,
    print_table,
    print_warning,
    prompt_choice,
    prompt_text,
    prompt_yes_no,
)


# ---------------------------------------------------------------------------
# Personality questionnaire
# ---------------------------------------------------------------------------

def ask_personality() -> dict:
    """Interactive personality questionnaire.

    Returns
    -------
    dict
        Keys: work_style, expertise, personality, custom_rules (list[str]).
    """
    print_header("Agent Personality")

    # Work style
    work_style_idx = prompt_choice(
        "How should the agent communicate?",
        [
            "Direct — lead with the answer, concise",
            "Thorough — detailed, cover edge cases, explain reasoning",
            "Conversational — think out loud, invite input",
        ],
        default=1,
    )
    work_style = ["direct", "thorough", "conversational"][work_style_idx]

    # Expertise level
    expertise_idx = prompt_choice(
        "What's your experience level?",
        [
            "Peer — experienced developer, skip the basics",
            "Mentor — explain concepts when relevant",
            "Beginner — explain everything, suggest resources",
        ],
        default=1,
    )
    expertise = ["peer", "mentor", "beginner"][expertise_idx]

    # Personality
    personality_idx = prompt_choice(
        "What personality fits best?",
        [
            "Professional — focused, efficient, minimal small talk",
            "Collaborative — engaged partner, pushes back when needed",
            "Casual — relaxed, like a smart coworker at a whiteboard",
        ],
        default=2,
    )
    personality = ["professional", "collaborative", "casual"][personality_idx]

    # Custom rules
    custom_rules: list[str] = []
    print()
    print_info(
        "You can add custom rules the agent should always follow."
    )
    print_info(
        "Examples: 'Always use TypeScript', 'Prefer functional style'"
    )
    print_info("Enter one rule per line. Empty line to finish.")
    while True:
        rule = prompt_text("Rule (empty to finish)")
        if not rule:
            break
        custom_rules.append(rule)

    return {
        "work_style": work_style,
        "expertise": expertise,
        "personality": personality,
        "custom_rules": custom_rules,
    }


# ---------------------------------------------------------------------------
# Scan results presentation and selection
# ---------------------------------------------------------------------------

def present_scan_results(scan: ScanResult) -> dict:
    """Show scan results and let the user select what to include.

    Returns
    -------
    dict
        Keys: projects (list[ProjectInfo]), docs (list[DocInfo]),
        conventions (list[ConventionInfo]), ai_conversations (list[dict]).
    """
    print_header("Workspace Scan Results")

    selected: dict = {
        "projects": [],
        "docs": [],
        "conventions": [],
        "ai_conversations": [],
    }

    # --- Summary ---
    print_info(f"Total files scanned: {scan.total_files}")
    if scan.warnings:
        for w in scan.warnings:
            print_warning(w)
    print()

    # --- Repos ---
    if scan.repos:
        print_step(1, f"Git repositories ({len(scan.repos)} found)")
        for repo in scan.repos:
            langs = ", ".join(repo.languages) if repo.languages else "unknown"
            print_info(f"  {repo.name} — {langs}")
        print()

    # --- Projects ---
    if scan.projects:
        print_step(2, f"Projects ({len(scan.projects)} found)")
        rows: list[list[str]] = []
        for i, proj in enumerate(scan.projects, 1):
            deps_count = len(proj.dependencies)
            test = proj.test_runner or "none"
            rows.append([
                str(i), proj.name, proj.project_type,
                f"{deps_count} deps", test,
            ])
        print_table(
            ["#", "Name", "Type", "Dependencies", "Tests"],
            rows,
        )

        if prompt_yes_no("Include all projects?", default=True):
            selected["projects"] = list(scan.projects)
        else:
            # Let user pick by number
            print_info("Enter project numbers to include (comma-separated):")
            raw = prompt_text("Projects", default="all")
            if raw.lower() == "all":
                selected["projects"] = list(scan.projects)
            else:
                indices = _parse_number_list(raw, len(scan.projects))
                selected["projects"] = [scan.projects[i] for i in indices]
    print()

    # --- Documentation ---
    if scan.documentation:
        # Show top docs (cap display at 20 to avoid overwhelming)
        display_docs = scan.documentation[:20]
        remaining = len(scan.documentation) - len(display_docs)

        print_step(3, f"Documentation ({len(scan.documentation)} files found)")
        rows = []
        for i, doc in enumerate(display_docs, 1):
            size = _size_label(doc.size_bytes)
            rows.append([str(i), doc.title, size, f"P{doc.priority}"])
        print_table(["#", "Title", "Size", "Priority"], rows)
        if remaining > 0:
            print_info(f"  (+{remaining} more files not shown)")

        if prompt_yes_no("Include all documentation?", default=True):
            selected["docs"] = list(scan.documentation)
        else:
            print_info("Enter doc numbers to include (comma-separated):")
            raw = prompt_text("Docs", default="all")
            if raw.lower() == "all":
                selected["docs"] = list(scan.documentation)
            else:
                indices = _parse_number_list(raw, len(display_docs))
                selected["docs"] = [display_docs[i] for i in indices]
    print()

    # --- Conventions ---
    if scan.conventions:
        print_step(4, f"Conventions ({len(scan.conventions)} sources)")
        for conv in scan.conventions:
            items = ", ".join(f"{k}={v}" for k, v in conv.conventions.items())
            print_info(f"  {conv.source}: {items}")
        print()
        # Conventions are always included (they shape code quality)
        selected["conventions"] = list(scan.conventions)
        print_success("Conventions auto-included (they improve code quality)")
    print()

    # --- AI conversations ---
    if scan.ai_conversations:
        print_step(5, f"AI conversation history ({len(scan.ai_conversations)} sources)")
        for ai in scan.ai_conversations:
            print_info(f"  {ai['source']}: {ai['count']} files at {ai['path']}")
        print()
        if prompt_yes_no("Include AI conversation history for context?", default=False):
            selected["ai_conversations"] = list(scan.ai_conversations)
    print()

    return selected


# ---------------------------------------------------------------------------
# Knowledge generation
# ---------------------------------------------------------------------------

def generate_knowledge(
    scan: ScanResult,
    selected: dict,
    personality: dict,
    workspace: Path,
    permission_mode: str,
) -> dict:
    """Generate all knowledge files from scan results and personality.

    Returns
    -------
    dict
        Keys are relative file paths, values are file contents (str).
        Nothing is written to disk yet.
    """
    files: dict[str, str] = {}

    projects = selected.get("projects", [])
    docs = selected.get("docs", [])
    conventions = selected.get("conventions", [])
    custom_rules = personality.get("custom_rules", [])

    # --- APEX.md ---
    apex_md = generate_apex_md(
        personality=personality,
        projects=projects,
        conventions=conventions,
        docs=docs,
        workspace=workspace,
        custom_rules=custom_rules,
        permission_mode=permission_mode,
    )

    # Show preview
    print_header("APEX.md Preview")
    # Show first 60 lines
    preview_lines = apex_md.splitlines()[:60]
    for line in preview_lines:
        print(f"  {line}")
    if len(apex_md.splitlines()) > 60:
        print_info(f"  ... ({len(apex_md.splitlines()) - 60} more lines)")
    print()

    if not prompt_yes_no("Accept this APEX.md?", default=True):
        print_info("You can edit APEX.md manually after setup completes.")

    files["APEX.md"] = apex_md

    # --- Memory files for projects with substantial docs ---
    for proj in projects:
        safe_name = proj.name.replace(" ", "_").lower()
        description = f"{proj.project_type} project at {proj.path.name}"
        summary_parts: list[str] = [f"# {proj.name}", ""]
        summary_parts.append(f"**Type:** {proj.project_type}")
        summary_parts.append(f"**Path:** `{proj.path}`")
        if proj.config_path:
            summary_parts.append(f"**Config:** `{proj.config_path}`")
        if proj.entry_points:
            summary_parts.append("**Entry points:**")
            for ep in proj.entry_points:
                summary_parts.append(f"- `{ep}`")
        if proj.dependencies:
            dep_str = ", ".join(proj.dependencies[:30])
            summary_parts.append(f"**Dependencies:** {dep_str}")
        if proj.python_version:
            summary_parts.append(f"**Python:** {proj.python_version}")
        if proj.test_runner:
            summary_parts.append(f"**Tests:** {proj.test_runner}")

        content = generate_memory_file(
            name=proj.name,
            description=description,
            content_summary="\n".join(summary_parts),
        )
        files[f"memory/{safe_name}.md"] = content

    # --- MEMORY.md index ---
    memory_index = generate_memory_index(projects=projects, docs=docs)
    files["memory/MEMORY.md"] = memory_index

    return files


# ---------------------------------------------------------------------------
# File writing (atomic temp+rename, scrub everything)
# ---------------------------------------------------------------------------

def write_knowledge_files(
    apex_root: Path,
    workspace: Path,
    files: dict[str, str],
) -> None:
    """Write generated knowledge files to disk.

    - APEX.md is written to the workspace root.
    - memory/ files are written to workspace/memory/.
    - All content is scrubbed through scrub_text() before writing.
    - All writes use atomic temp+rename to avoid corruption.

    Parameters
    ----------
    apex_root : Path
        The Apex installation root (for reference, not written to).
    workspace : Path
        The user's workspace root.
    files : dict[str, str]
        Keys are relative paths, values are file contents.
    """
    for rel_path, content in files.items():
        target = workspace / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)

        # Scrub content one final time before writing
        safe_content = scrub_text(content)

        # Atomic write: temp file in same directory, then rename
        fd, tmp_path = tempfile.mkstemp(
            dir=str(target.parent),
            suffix=".tmp",
            prefix=f".{target.stem}_",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(safe_content)
            os.replace(tmp_path, str(target))
            print_success(f"Wrote {rel_path}")
        except Exception as exc:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            print_error(f"Failed to write {rel_path}: {exc}")
            raise


# ---------------------------------------------------------------------------
# Embedding index
# ---------------------------------------------------------------------------

def build_embedding_index(workspace: Path, apex_root: Path) -> dict:
    """Build semantic embedding index over memory files.

    Tries to import the embedding skill's memory_search module.
    If unavailable (no Google API key, missing deps), skips gracefully.

    Returns
    -------
    dict
        Stats dict, e.g. {"indexed": 5, "skipped": 0} or {"skipped": True}.
    """
    try:
        # Add the skills directory to the import path temporarily
        skills_dir = str(workspace / "skills" / "embedding")
        if skills_dir not in sys.path:
            sys.path.insert(0, skills_dir)

        from memory_search import index_memory  # type: ignore[import-untyped]

        print_info("Building semantic index over memory files...")
        stats = index_memory(force=True)
        if isinstance(stats, dict):
            indexed = stats.get("indexed", 0)
            print_success(f"Indexed {indexed} memory files")
            return stats
        return {"indexed": 0}
    except ImportError:
        print_warning(
            "Embedding system not available (missing dependencies). "
            "Skipping semantic index."
        )
        return {"skipped": True, "reason": "import_error"}
    except Exception as exc:
        print_warning(f"Embedding index failed: {exc}. Skipping.")
        return {"skipped": True, "reason": str(exc)}
    finally:
        # Clean up sys.path
        skills_dir = str(workspace / "skills" / "embedding")
        if skills_dir in sys.path:
            sys.path.remove(skills_dir)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_knowledge_ingestion(
    apex_root: Path,
    workspace: Path,
    permission_mode: str,
) -> dict:
    """Orchestrate Phase 3: Knowledge Ingestion.

    Steps:
    1. Show knowledge ingestion introduction.
    2. If user skips: generate minimal APEX.md, return.
    3. Run workspace scan.
    4. Present results, get user selections.
    5. Ask personality questions.
    6. Generate and write knowledge files.
    7. Build embedding index.
    8. Return summary dict.

    Parameters
    ----------
    apex_root : Path
        Apex installation directory.
    workspace : Path
        User's workspace to scan.
    permission_mode : str
        Current permission mode for APEX.md.

    Returns
    -------
    dict
        Summary with keys: files_written (int), embedding_stats (dict),
        skipped (bool).
    """
    print_header("Phase 3: Knowledge Ingestion")

    print_info(
        "Apex works best when it understands your workspace — projects, "
        "conventions, documentation, and your preferences."
    )
    print_info(
        "This step scans your workspace (read-only) and generates "
        "configuration files."
    )
    print()

    if not prompt_yes_no("Scan workspace and generate knowledge files?", default=True):
        # Minimal setup: just personality + workspace path
        print_info("Generating minimal configuration...")
        personality = ask_personality()
        minimal_apex = generate_apex_md(
            personality=personality,
            projects=[],
            conventions=[],
            docs=[],
            workspace=workspace,
            custom_rules=personality.get("custom_rules", []),
            permission_mode=permission_mode,
        )
        files = {"APEX.md": minimal_apex}
        write_knowledge_files(apex_root, workspace, files)
        return {
            "files_written": 1,
            "embedding_stats": {},
            "skipped": True,
        }

    # Step 1: Scan workspace
    print()
    print_step(1, "Scanning workspace...")
    scan = scan_workspace(workspace)
    print_success(
        f"Found {len(scan.projects)} projects, "
        f"{len(scan.documentation)} docs, "
        f"{len(scan.conventions)} convention sources, "
        f"{scan.total_files} total files"
    )

    # Step 2: Present results, get selections
    print()
    print_step(2, "Review scan results")
    selected = present_scan_results(scan)

    # Step 3: Ask personality questions
    print()
    print_step(3, "Configure agent personality")
    personality = ask_personality()

    # Step 4: Generate knowledge files
    print()
    print_step(4, "Generating knowledge files...")
    files = generate_knowledge(
        scan=scan,
        selected=selected,
        personality=personality,
        workspace=workspace,
        permission_mode=permission_mode,
    )

    # Step 5: Write files
    print()
    print_step(5, "Writing files...")
    write_knowledge_files(apex_root, workspace, files)

    # Step 6: Build embedding index
    print()
    print_step(6, "Building embedding index...")
    embedding_stats = build_embedding_index(workspace, apex_root)

    # Summary
    print()
    print_header("Knowledge Ingestion Complete")
    print_success(f"Generated {len(files)} files")
    if not embedding_stats.get("skipped"):
        indexed = embedding_stats.get("indexed", 0)
        print_success(f"Indexed {indexed} files for semantic search")
    else:
        print_info("Semantic search index skipped (can be built later)")

    return {
        "files_written": len(files),
        "embedding_stats": embedding_stats,
        "skipped": False,
    }


# ---------------------------------------------------------------------------
# Headless ingestion (for browser wizard)
# ---------------------------------------------------------------------------

def run_knowledge_ingestion_headless(
    apex_root: Path,
    workspace: Path,
    permission_mode: str,
    personality: dict | None = None,
) -> dict:
    """Non-interactive variant of run_knowledge_ingestion.

    Takes all decisions as parameters. Calls template generators directly,
    bypassing all interactive prompts (prompt_yes_no, prompt_choice, etc.).

    Returns
    -------
    dict
        Keys: files_written (int), embedding_stats (dict), skipped (bool).
    """
    if personality is None:
        personality = {
            "work_style": "direct",
            "expertise": "peer",
            "personality": "professional",
            "custom_rules": [],
        }

    scan = scan_workspace(workspace)

    projects = list(scan.projects)
    docs = list(scan.documentation)
    conventions = list(scan.conventions)
    custom_rules = personality.get("custom_rules", [])

    # Build files dict directly — skip interactive generate_knowledge()
    files: dict[str, str] = {}

    apex_md = generate_apex_md(
        personality=personality,
        projects=projects,
        conventions=conventions,
        docs=docs,
        workspace=workspace,
        custom_rules=custom_rules,
        permission_mode=permission_mode,
    )
    files["APEX.md"] = apex_md

    for proj in projects:
        safe_name = proj.name.replace(" ", "_").lower()
        description = f"{proj.project_type} project at {proj.path.name}"
        summary_parts: list[str] = [f"# {proj.name}", ""]
        summary_parts.append(f"**Type:** {proj.project_type}")
        summary_parts.append(f"**Path:** `{proj.path}`")
        if proj.config_path:
            summary_parts.append(f"**Config:** `{proj.config_path}`")
        if proj.entry_points:
            summary_parts.append("**Entry points:**")
            for ep in proj.entry_points:
                summary_parts.append(f"- `{ep}`")
        if proj.dependencies:
            dep_str = ", ".join(proj.dependencies[:30])
            summary_parts.append(f"**Dependencies:** {dep_str}")
        if proj.python_version:
            summary_parts.append(f"**Python:** {proj.python_version}")
        if proj.test_runner:
            summary_parts.append(f"**Tests:** {proj.test_runner}")
        content = generate_memory_file(
            name=proj.name,
            description=description,
            content_summary="\n".join(summary_parts),
        )
        files[f"memory/{safe_name}.md"] = content

    memory_index = generate_memory_index(projects=projects, docs=docs)
    files["memory/MEMORY.md"] = memory_index

    write_knowledge_files(apex_root, workspace, files)

    embedding_stats = build_embedding_index(workspace, apex_root)

    return {
        "files_written": len(files),
        "embedding_stats": embedding_stats,
        "skipped": False,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_number_list(raw: str, max_val: int) -> list[int]:
    """Parse a comma-separated list of 1-based numbers into 0-based indices.

    Invalid or out-of-range numbers are silently skipped.
    """
    indices: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        # Handle ranges like "1-3"
        if "-" in part:
            range_parts = part.split("-", 1)
            try:
                start = int(range_parts[0].strip())
                end = int(range_parts[1].strip())
                for n in range(start, end + 1):
                    if 1 <= n <= max_val:
                        indices.append(n - 1)
            except ValueError:
                continue
        else:
            try:
                n = int(part)
                if 1 <= n <= max_val:
                    indices.append(n - 1)
            except ValueError:
                continue
    return sorted(set(indices))


def _size_label(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
