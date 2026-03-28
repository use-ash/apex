"""File writing tool."""
import os
from ..safety import validate_path, MAX_FILE_WRITE_BYTES


def execute(args: dict, workspace: str | None = None) -> str:
    """Write content to a file."""
    file_path = args.get("file_path", "").strip()
    content = args.get("content", "")

    if not file_path:
        return "Error: file_path is required"

    # Resolve relative paths against workspace
    if not os.path.isabs(file_path) and workspace:
        file_path = os.path.join(workspace, file_path)

    err = validate_path(file_path, allow_write=True)
    if err:
        return err

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
