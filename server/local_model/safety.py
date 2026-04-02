"""Safety constraints for local model tool execution."""
import os
import shlex
from pathlib import Path

MAX_COMMAND_TIMEOUT = 120
DEFAULT_COMMAND_TIMEOUT = 30
MAX_OUTPUT_CHARS = 50_000
MAX_FILE_READ_LINES = 2000
MAX_FILE_WRITE_BYTES = 5 * 1024 * 1024  # 5MB
MAX_LIST_FILES = 500
MAX_SEARCH_MATCHES = 100

BLOCKED_WRITE_PATHS = [
    "/System",
    "/usr/bin",
    "/usr/sbin",
    "/usr/lib",
    "/bin",
    "/sbin",
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/Library/LaunchDaemons",
]

SENSITIVE_PATH_PREFIXES = tuple(
    os.path.realpath(str(path))
    for path in (
        Path.home() / ".ssh",
        Path.home() / ".aws",
        Path.home() / ".config" / "gh",
        Path.home() / ".gnupg",
    )
)

SENSITIVE_BASENAMES = {
    ".env",
    ".env.local",
    ".credentials.json",
    ".pypirc",
    ".npmrc",
    ".netrc",
    "id_rsa",
    "id_ed25519",
    "credentials",
    "config.json",
}

SHELL_META_SNIPPETS = ("`", "$(", "${", "&&", "||", "|", ";", ">", "<", "\n", "\r", "\x00")

READ_ONLY_GIT_SUBCOMMANDS = {
    "status",
    "diff",
    "show",
    "log",
    "branch",
    "rev-parse",
    "remote",
    "ls-files",
    "grep",
    "blame",
    "describe",
}

READ_ONLY_COMMANDS = {
    "pwd",
    "uname",
    "which",
    "echo",
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "sed",
    "grep",
    "rg",
    "find",
    "stat",
    "file",
}

PYTHON_COMMANDS = {"python", "python3", "/opt/homebrew/bin/python3"}


def _looks_like_path(arg: str) -> bool:
    if not arg or arg.startswith("-"):
        return False
    return (
        arg in {".", ".."}
        or arg.startswith(("~", "/", "."))
        or os.sep in arg
        or arg.endswith((".py", ".sh", ".json", ".toml", ".yaml", ".yml", ".env", ".txt", ".md"))
    )


def _resolve_candidate_path(arg: str, workspace: str | None) -> str:
    expanded = os.path.expanduser(arg)
    if os.path.isabs(expanded):
        return os.path.realpath(expanded)
    if workspace:
        return os.path.realpath(os.path.join(workspace, expanded))
    return os.path.realpath(expanded)


def _is_sensitive_path(path: str) -> bool:
    base = os.path.basename(path)
    if base in SENSITIVE_BASENAMES:
        return True
    for prefix in SENSITIVE_PATH_PREFIXES:
        if path == prefix or path.startswith(prefix + os.sep):
            return True
    return False


def _primary_workspace(workspace: str | None) -> str | None:
    """Return the first (primary) workspace root from a colon-separated list."""
    if not workspace:
        return None
    first = workspace.split(":")[0].strip()
    return first or None


def _validate_arg_paths(args: list[str], workspace: str | None) -> str | None:
    primary = _primary_workspace(workspace)
    for arg in args:
        if not _looks_like_path(arg):
            continue
        resolved = _resolve_candidate_path(arg, primary)
        if _is_sensitive_path(resolved):
            return f"Error: access to sensitive path is blocked: {arg}"
    return None


def _validate_read_only_command(argv: list[str], workspace: str | None) -> str | None:
    err = _validate_arg_paths(argv[1:], workspace)
    if err:
        return err

    exe = os.path.basename(argv[0])
    if exe == "find":
        blocked_args = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprintf", "-fprint", "-fls"}
        for arg in argv[1:]:
            if arg in blocked_args:
                return f"Error: find argument is blocked: {arg}"
    if exe == "sed":
        for arg in argv[1:]:
            if arg == "--in-place" or arg.startswith("-i"):
                return "Error: sed in-place editing is blocked"
    return None


def _validate_git_command(argv: list[str], workspace: str | None) -> str | None:
    if len(argv) < 2:
        return "Error: git subcommand is required"

    i = 1
    while i < len(argv) and argv[i] == "-C":
        if i + 1 >= len(argv):
            return "Error: git -C requires a path"
        err = _validate_arg_paths([argv[i + 1]], workspace)
        if err:
            return err
        i += 2

    if i >= len(argv):
        return "Error: git subcommand is required"

    subcommand = argv[i]
    if subcommand not in READ_ONLY_GIT_SUBCOMMANDS:
        return f"Error: git subcommand is not allowed: {subcommand}"

    return _validate_arg_paths(argv[i + 1 :], workspace)


def _validate_python_command(argv: list[str], workspace: str | None) -> str | None:
    if len(argv) == 2 and argv[1] in {"-V", "--version"}:
        return None
    if len(argv) >= 4 and argv[1] == "-m" and argv[2] == "py_compile":
        return _validate_arg_paths(argv[3:], workspace)
    return "Error: python is limited to version checks and -m py_compile"


def prepare_command(command: str, workspace: str | None = None) -> tuple[list[str] | None, str | None]:
    """Parse and validate a bash-tool command, returning argv on success."""
    cmd = command.strip()
    if not cmd:
        return None, "Error: no command provided"
    if any(snippet in cmd for snippet in SHELL_META_SNIPPETS):
        return None, "Error: shell syntax is not allowed"

    try:
        argv = shlex.split(cmd, posix=True)
    except ValueError as e:
        return None, f"Error: invalid command syntax: {e}"

    if not argv:
        return None, "Error: no command provided"

    exe = argv[0]
    base = os.path.basename(exe)
    if base in READ_ONLY_COMMANDS:
        return argv, _validate_read_only_command(argv, workspace)
    if base == "git":
        return argv, _validate_git_command(argv, workspace)
    if exe in PYTHON_COMMANDS or base in PYTHON_COMMANDS:
        return argv, _validate_python_command(argv, workspace)
    return None, f"Error: command is not allowed: {exe}"


def validate_command(command: str, workspace: str | None = None) -> str | None:
    """Returns error string if command is blocked, None if OK."""
    _, err = prepare_command(command, workspace)
    return err


def ensure_workspace_path(
    path: str,
    workspace: str | None,
    *,
    allow_write: bool = False,
) -> tuple[str | None, str | None]:
    """Resolve a path and enforce that it stays within one of the workspace roots.

    ``workspace`` may contain multiple colon-separated directories (like PATH).
    The first entry is the primary workspace used to resolve relative paths.
    A path is allowed if it falls under *any* of the listed roots.
    """
    if not workspace:
        return None, "Error: workspace is required for file tools"

    roots = [
        os.path.realpath(os.path.expanduser(r))
        for r in workspace.split(":") if r.strip()
    ]
    if not roots:
        return None, "Error: workspace is required for file tools"

    # Resolve relative paths against the primary (first) workspace root
    resolved = _resolve_candidate_path(path, roots[0])

    # Check if the resolved path falls under ANY allowed root
    inside = False
    for root in roots:
        try:
            if os.path.commonpath([resolved, root]) == root:
                inside = True
                break
        except ValueError:
            continue

    if not inside:
        return None, f"Error: path is outside workspace: {path}"

    err = validate_path(resolved, allow_write=allow_write)
    if err:
        return None, err
    return resolved, None


def validate_path(path: str, allow_write: bool = False) -> str | None:
    """Returns error string if path is blocked, None if OK."""
    resolved = os.path.realpath(os.path.expanduser(path))
    if allow_write:
        for blocked in BLOCKED_WRITE_PATHS:
            if resolved.startswith(blocked):
                return f"Error: write to {blocked} is blocked"
    return None


def truncate_output(output: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """Truncate output to max_chars, adding indicator if truncated."""
    if len(output) <= max_chars:
        return output
    return output[:max_chars] + f"\n\n[output truncated at {max_chars} chars]"
