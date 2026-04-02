"""File reading tool."""
import os
from ..safety import ensure_workspace_path, MAX_FILE_READ_LINES


def execute(args: dict, workspace: str | None = None) -> str:
    """Read a file's contents with line numbers."""
    file_path = args.get("file_path", "").strip()
    if not file_path:
        return "Error: file_path is required"

    resolved_path, err = ensure_workspace_path(file_path, workspace)
    if err:
        return err
    assert resolved_path is not None
    file_path = resolved_path

    if not os.path.exists(file_path):
        return f"Error: file not found: {file_path}"

    if os.path.isdir(file_path):
        return f"Error: {file_path} is a directory, not a file"

    try:
        offset = max(1, int(args.get("offset", 1)))
    except (TypeError, ValueError):
        offset = 1
    try:
        limit = min(int(args.get("limit", 500)), MAX_FILE_READ_LINES)
    except (TypeError, ValueError):
        limit = 500

    try:
        with open(file_path, "r", errors="replace") as f:
            lines = f.readlines()

        total = len(lines)
        start_idx = offset - 1
        end_idx = min(start_idx + limit, total)

        if start_idx >= total:
            return f"Error: offset {offset} is beyond end of file ({total} lines)"

        result_lines = []
        for i in range(start_idx, end_idx):
            result_lines.append(f"{i + 1:>6}\t{lines[i].rstrip()}")

        result = "\n".join(result_lines)
        if end_idx < total:
            result += f"\n\n[showing lines {offset}-{end_idx} of {total}]"
        return result
    except Exception as e:
        return f"Error reading file: {type(e).__name__}: {e}"
