"""File content search tool."""
import subprocess
from ..safety import ensure_workspace_path, truncate_output, MAX_SEARCH_MATCHES


def execute(args: dict, workspace: str | None = None, *, permission_level: int = 2) -> str:
    """Search file contents for a pattern (grep-like)."""
    pattern = args.get("pattern", "").strip()
    if not pattern:
        return "Error: pattern is required"

    search_path = args.get("path", workspace or ".")
    glob_filter = args.get("glob", "")
    resolved_path, err = ensure_workspace_path(search_path, workspace, permission_level=permission_level)
    if err:
        return err
    assert resolved_path is not None

    cmd = ["grep", "-rn", "--color=never"]
    if glob_filter:
        cmd.extend(["--include", glob_filter])
    cmd.extend(["-m", str(MAX_SEARCH_MATCHES), pattern, resolved_path])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=workspace,
        )
        output = result.stdout
        if not output and result.returncode == 1:
            return "No matches found"
        if result.stderr and result.returncode not in (0, 1):
            return f"Error: {result.stderr.strip()}"
        return truncate_output(output) if output else "No matches found"
    except subprocess.TimeoutExpired:
        return "Error: search timed out after 30 seconds"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
