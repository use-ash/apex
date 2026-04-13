"""File content search tool."""
import os
import subprocess
from ..safety import ensure_workspace_path, truncate_output, MAX_SEARCH_MATCHES

_WORKSPACE_WILDCARD_PATHS = {"*", "**", "./*", ".\\*", "**/*"}


def _workspace_roots(workspace: str | None) -> list[str]:
    roots: list[str] = []
    for raw in str(workspace or "").split(":"):
        root = raw.strip()
        if not root:
            continue
        resolved = os.path.realpath(os.path.expanduser(root))
        if resolved not in roots:
            roots.append(resolved)
    return roots


def _search_roots_for_args(args: dict, workspace: str | None, permission_level: int) -> tuple[list[str], str | None]:
    raw_path = str(args.get("path") or "").strip()
    roots = _workspace_roots(workspace)

    # Missing path in a multi-root workspace should search every configured root.
    if not raw_path:
        if roots:
            return roots, None
        search_path = workspace or "."
        resolved_path, err = ensure_workspace_path(search_path, workspace, permission_level=permission_level)
        return ([resolved_path] if resolved_path else []), err

    # Treat wildcard-like path aliases as "search the whole workspace set", not a literal file path.
    if raw_path in _WORKSPACE_WILDCARD_PATHS:
        if roots:
            return roots, None
        resolved_path, err = ensure_workspace_path(".", workspace, permission_level=permission_level)
        return ([resolved_path] if resolved_path else []), err

    resolved_path, err = ensure_workspace_path(raw_path, workspace, permission_level=permission_level)
    return ([resolved_path] if resolved_path else []), err


def execute(args: dict, workspace: str | None = None, *, permission_level: int = 2) -> str:
    """Search file contents for a pattern (grep-like)."""
    pattern = args.get("pattern", "").strip()
    if not pattern:
        return "Error: pattern is required"

    glob_filter = args.get("glob", "")
    search_roots, err = _search_roots_for_args(args, workspace, permission_level)
    if err:
        return err
    if not search_roots:
        return "Error: workspace is required for file tools"

    try:
        output_chunks: list[str] = []
        saw_match = False
        for root in search_roots:
            cmd = ["grep", "-rn", "--color=never"]
            if glob_filter:
                cmd.extend(["--include", glob_filter])
            cmd.extend(["-m", str(MAX_SEARCH_MATCHES), pattern, root])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.stderr and result.returncode not in (0, 1):
                return f"Error: {result.stderr.strip()}"
            if result.stdout:
                saw_match = True
                output_chunks.append(result.stdout.rstrip())

        if not saw_match:
            return "No matches found"
        output = "\n".join(chunk for chunk in output_chunks if chunk).strip()
        return truncate_output(output) if output else "No matches found"
    except subprocess.TimeoutExpired:
        return "Error: search timed out after 30 seconds"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
