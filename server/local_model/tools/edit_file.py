"""Diff-based file editing tool — search-and-replace on exact text spans."""
import os
from ..safety import ensure_workspace_path, MAX_FILE_WRITE_BYTES


def execute(args: dict, workspace: str | None = None, *, permission_level: int = 2) -> str:
    """Edit a file by replacing an exact text span with new text."""
    file_path = args.get("file_path", "").strip()
    old_text = args.get("old_text", "")
    new_text = args.get("new_text", "")

    if not file_path:
        return "Error: file_path is required"
    if not old_text:
        return "Error: old_text is required"
    if old_text == new_text:
        return "Error: old_text and new_text are identical"

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

    # Read current content
    try:
        with open(file_path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        return f"Error: file not found: {file_path}"
    except Exception as e:
        return f"Error reading file: {type(e).__name__}: {e}"

    # Count occurrences
    count = content.count(old_text)
    if count == 0:
        # Provide helpful context — show a snippet of the file
        lines = content.split("\n")
        preview = "\n".join(lines[:20])
        hint = f" (file has {len(lines)} lines)"
        if len(old_text) < 200:
            return (
                f"Error: old_text not found in {file_path}{hint}. "
                f"Check for whitespace/indentation differences.\n"
                f"First 20 lines:\n{preview}"
            )
        return f"Error: old_text not found in {file_path}{hint}. Check for whitespace/indentation differences."

    if count > 1:
        return (
            f"Error: old_text matches {count} locations in {file_path}. "
            f"Include more surrounding context to make the match unique."
        )

    # Perform replacement
    new_content = content.replace(old_text, new_text, 1)

    if len(new_content.encode("utf-8")) > MAX_FILE_WRITE_BYTES:
        return f"Error: resulting file would exceed {MAX_FILE_WRITE_BYTES // (1024*1024)}MB limit"

    try:
        with open(file_path, "w") as f:
            f.write(new_content)
    except Exception as e:
        return f"Error writing file: {type(e).__name__}: {e}"

    # Build a confirmation showing what changed
    old_lines = old_text.count("\n") + 1
    new_lines = new_text.count("\n") + 1
    size = os.path.getsize(file_path)
    return (
        f"Edited {file_path} ({size} bytes): "
        f"replaced {old_lines} line(s) with {new_lines} line(s)"
    )
