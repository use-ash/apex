"""File writing tool."""
import os
from ..safety import ensure_workspace_path, MAX_FILE_WRITE_BYTES


def execute(args: dict, workspace: str | None = None, *, permission_level: int = 2) -> str:
    """Write content to a file."""
    file_path = args.get("file_path", "").strip()
    content = args.get("content", "")

    if not file_path:
        return "Error: file_path is required"

    resolved_path, err = ensure_workspace_path(
        file_path,
        workspace,
        allow_write=True,
        permission_level=permission_level,
    )
    if err:
        return err
    assert resolved_path is not None
    file_path = resolved_path

    if len(content.encode("utf-8")) > MAX_FILE_WRITE_BYTES:
        return f"Error: content exceeds {MAX_FILE_WRITE_BYTES // (1024*1024)}MB limit"

    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)
        size = os.path.getsize(file_path)
        return f"Wrote {size} bytes to {file_path}"
    except Exception as e:
        return f"Error writing file: {type(e).__name__}: {e}"
