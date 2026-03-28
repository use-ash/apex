"""File listing tool."""
import os
from pathlib import Path
from ..safety import MAX_LIST_FILES


def execute(args: dict, workspace: str | None = None) -> str:
    """List files matching a glob pattern."""
    pattern = args.get("pattern", "").strip()
    if not pattern:
        return "Error: pattern is required"

    search_path = args.get("path", workspace or os.getcwd())

    try:
        p = Path(search_path)
        if not p.exists():
            return f"Error: path not found: {search_path}"

        matches = sorted(
            p.glob(pattern),
            key=lambda f: f.stat().st_mtime if f.exists() else 0,
            reverse=True,
        )

        if not matches:
            return "No files found"

        total = len(matches)
        limited = matches[:MAX_LIST_FILES]
        result = "\n".join(str(f) for f in limited)
        if total > MAX_LIST_FILES:
            result += f"\n\n[showing {MAX_LIST_FILES} of {total} matches]"
        return result
    except Exception as e:
        return f"Error listing files: {type(e).__name__}: {e}"
