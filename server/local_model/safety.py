"""Safety constraints for local model tool execution."""
import os
import shlex
import tempfile
from pathlib import Path

from env import APEX_ROOT

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
LEVEL3_ALLOWED_SHELL_META_SNIPPETS = ("&&", "||", "|", ";", "\n")
LEVEL3_BLOCKED_SHELL_META_SNIPPETS = ("`", "$(", "${", ">", "<", "\r", "\x00")
LEVEL3_ALLOWED_SHELL_OPERATORS = frozenset({"&&", "||", "|", ";"})

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
PROTECTED_PATHS = {
    os.path.realpath(str(APEX_ROOT / "state" / "apex.db")),
    os.path.realpath(str(APEX_ROOT / "state" / "config.json")),
    os.path.realpath(str(APEX_ROOT / "ssl")),
    os.path.realpath(str(APEX_ROOT / "state" / "ssl")),
    os.path.realpath(str(APEX_ROOT / "server")),
}
LIVE_APEX_DB_PATHS = tuple(
    os.path.realpath(str(APEX_ROOT / "state" / name))
    for name in ("apex.db", "apex.db-wal", "apex.db-shm", "apex.db-journal")
)
ADMIN_TEMP_ROOTS = tuple(
    dict.fromkeys(
        os.path.realpath(path)
        for path in (
            tempfile.gettempdir(),
            "/tmp",
            "/private/tmp",
        )
    )
)


def _is_env_path(path: str) -> bool:
    base = os.path.basename(path)
    return base == ".env" or base.startswith(".env.")


def _live_db_path_error(path: str) -> str | None:
    for blocked in LIVE_APEX_DB_PATHS:
        if path == blocked:
            return f"Error: access to live Apex database is blocked: {path}"
    return None


def _protected_path_error(path: str) -> str | None:
    live_db_err = _live_db_path_error(path)
    if live_db_err:
        return live_db_err
    for protected in PROTECTED_PATHS:
        if path == protected or path.startswith(protected + os.sep):
            return f"Error: access to protected path is blocked: {path}"
    if _is_env_path(path):
        return f"Error: access to protected path is blocked: {path}"
    return None


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
    protected = _protected_path_error(path)
    if protected:
        return True
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
        protected = _protected_path_error(resolved)
        if protected:
            return protected
        if _is_sensitive_path(resolved):
            return f"Error: access to sensitive path is blocked: {arg}"
    return None


def _validate_write_capable_arg_paths(args: list[str], workspace: str | None) -> str | None:
    primary = _primary_workspace(workspace)
    for arg in args:
        if not _looks_like_path(arg):
            continue
        resolved = _resolve_candidate_path(arg, primary)
        err = validate_path(resolved, allow_write=True)
        if err:
            return err
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


def _tokenize_shell_command(command: str) -> list[str]:
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars="|&;<>")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _validate_live_db_command_paths(command: str, workspace: str | None) -> str | None:
    primary = _primary_workspace(workspace)
    normalized_command = command.replace('"', " ").replace("'", " ")
    for blocked in LIVE_APEX_DB_PATHS:
        if blocked in normalized_command:
            return _live_db_path_error(blocked)
    try:
        tokens = _tokenize_shell_command(command)
    except ValueError:
        return None

    for token in tokens:
        if token in {"|", "||", "&&", ";", "<", ">", "<<", ">>", "&"}:
            continue
        candidates = [token.strip()]
        if "=" in token and not token.startswith("="):
            _, _, rhs = token.partition("=")
            if rhs:
                candidates.append(rhs.strip())
        for candidate in candidates:
            if not _looks_like_path(candidate):
                continue
            resolved = _resolve_candidate_path(candidate, primary)
            err = _live_db_path_error(resolved)
            if err:
                return err
    return None


def _normalize_command_text(command: str) -> str:
    try:
        return " ".join(shlex.split(command, posix=True))
    except ValueError:
        return " ".join(command.strip().split())


def _command_matches_allowed_prefix(command: str, allowed_commands: list[str] | None) -> bool:
    normalized = _normalize_command_text(command)
    for entry in allowed_commands or []:
        prefix = _normalize_command_text(entry)
        if not prefix:
            continue
        if normalized == prefix or normalized.startswith(prefix + " "):
            return True
    return False


def _contains_disallowed_shell_syntax(
    command: str,
    *,
    permission_level: int,
    allowed_commands: list[str] | None = None,
) -> bool:
    if permission_level >= 3 and any(
        snippet in command for snippet in LEVEL3_ALLOWED_SHELL_META_SNIPPETS
    ):
        return any(snippet in command for snippet in LEVEL3_BLOCKED_SHELL_META_SNIPPETS)
    if permission_level >= 3 and _command_matches_allowed_prefix(command, allowed_commands):
        return any(snippet in command for snippet in LEVEL3_BLOCKED_SHELL_META_SNIPPETS)
    return any(snippet in command for snippet in SHELL_META_SNIPPETS)


def _path_is_within_root(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def _workspace_roots(workspace: str | None) -> list[str]:
    return [
        os.path.realpath(os.path.expanduser(root))
        for root in (workspace or "").split(":")
        if root.strip()
    ]


def _path_is_within_admin_roots(path: str, workspace: str | None) -> bool:
    roots = _workspace_roots(workspace)
    inside_workspace = any(_path_is_within_root(path, root) for root in roots)
    inside_tmp = any(_path_is_within_root(path, root) for root in ADMIN_TEMP_ROOTS)
    return inside_workspace or inside_tmp


def _validate_allowlisted_command_segment(
    segment: str,
    workspace: str | None,
    allowed_commands: list[str] | None,
) -> str | None:
    if not _command_matches_allowed_prefix(segment, allowed_commands):
        try:
            argv = shlex.split(segment, posix=True)
        except ValueError as e:
            return f"Error: invalid command syntax: {e}"
        exe = argv[0] if argv else ""
        return f"Error: command is not allowed: {exe}"

    try:
        argv = shlex.split(segment, posix=True)
    except ValueError as e:
        return f"Error: invalid command syntax: {e}"

    if not argv:
        return "Error: invalid command syntax"

    exe = argv[0]
    base = os.path.basename(exe)
    if base in READ_ONLY_COMMANDS:
        return _validate_read_only_command(argv, workspace)
    if base == "git":
        git_err = _validate_git_command(argv, workspace)
        if not git_err:
            return None
        return _validate_write_capable_arg_paths(argv[1:], workspace)
    if exe in PYTHON_COMMANDS or base in PYTHON_COMMANDS:
        py_err = _validate_python_command(argv, workspace)
        if not py_err:
            return None
        return _validate_write_capable_arg_paths(argv[1:], workspace)
    return _validate_write_capable_arg_paths(argv[1:], workspace)


def _split_level3_shell_segments(command: str) -> tuple[list[str] | None, str | None]:
    try:
        lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars="|&;")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError as e:
        return None, f"Error: invalid command syntax: {e}"

    segments: list[str] = []
    current: list[str] = []
    for token in tokens:
        if token in LEVEL3_ALLOWED_SHELL_OPERATORS:
            if not current:
                return None, "Error: invalid command syntax"
            segments.append(shlex.join(current))
            current = []
            continue
        if token == "&":
            return None, "Error: shell syntax is not allowed"
        current.append(token)

    if not current:
        return None, "Error: invalid command syntax"
    segments.append(shlex.join(current))
    return segments, None


def _validate_level3_shell_command(
    command: str,
    workspace: str | None,
    allowed_commands: list[str] | None,
) -> str | None:
    segments, err = _split_level3_shell_segments(command)
    if err:
        return err
    for segment in segments or []:
        err = _validate_allowlisted_command_segment(segment, workspace, allowed_commands)
        if err:
            return err
    return None


def prepare_command(
    command: str,
    workspace: str | None = None,
    *,
    permission_level: int = 2,
    allowed_commands: list[str] | None = None,
) -> tuple[list[str] | None, str | None]:
    """Parse and validate a bash-tool command, returning argv on success."""
    cmd = command.strip()
    if not cmd:
        return None, "Error: no command provided"
    if permission_level <= 0:
        return None, "Error: tools are disabled for this persona"
    live_db_err = _validate_live_db_command_paths(cmd, workspace)
    if live_db_err:
        return None, live_db_err
    if permission_level >= 4:
        return ["/bin/sh", "-lc", cmd], None
    if _contains_disallowed_shell_syntax(
        cmd,
        permission_level=permission_level,
        allowed_commands=allowed_commands,
    ):
        return None, "Error: shell syntax is not allowed"
    if (
        permission_level >= 3
        and any(snippet in cmd for snippet in LEVEL3_ALLOWED_SHELL_META_SNIPPETS)
    ):
        err = _validate_level3_shell_command(cmd, workspace, allowed_commands)
        if err:
            return None, err
        return ["/bin/sh", "-lc", cmd], None

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
        git_err = _validate_git_command(argv, workspace)
        if not git_err:
            return argv, None
        if permission_level >= 3 and _command_matches_allowed_prefix(cmd, allowed_commands):
            return argv, _validate_write_capable_arg_paths(argv[1:], workspace)
        return None, git_err
    if exe in PYTHON_COMMANDS or base in PYTHON_COMMANDS:
        py_err = _validate_python_command(argv, workspace)
        if not py_err:
            return argv, None
        if permission_level >= 3 and _command_matches_allowed_prefix(cmd, allowed_commands):
            return argv, _validate_write_capable_arg_paths(argv[1:], workspace)
        return argv, py_err
    if permission_level >= 3 and _command_matches_allowed_prefix(cmd, allowed_commands):
        return argv, _validate_write_capable_arg_paths(argv[1:], workspace)
    return None, f"Error: command is not allowed: {exe}"


def validate_command(
    command: str,
    workspace: str | None = None,
    *,
    permission_level: int = 2,
    allowed_commands: list[str] | None = None,
) -> str | None:
    """Returns error string if command is blocked, None if OK."""
    _, err = prepare_command(
        command,
        workspace,
        permission_level=permission_level,
        allowed_commands=allowed_commands,
    )
    return err


def ensure_workspace_path(
    path: str,
    workspace: str | None,
    *,
    allow_write: bool = False,
    permission_level: int = 2,
) -> tuple[str | None, str | None]:
    """Resolve a path and enforce that it stays within one of the workspace roots.

    ``workspace`` may contain multiple colon-separated directories (like PATH).
    The first entry is the primary workspace used to resolve relative paths.
    A path is allowed if it falls under *any* of the listed roots.
    """
    if permission_level >= 4:
        resolved = _resolve_candidate_path(path, _primary_workspace(workspace))
        err = validate_path(resolved, allow_write=allow_write, permission_level=permission_level)
        if err:
            return None, err
        return resolved, None

    if permission_level >= 3:
        resolved = _resolve_candidate_path(path, _primary_workspace(workspace))
        if not _path_is_within_admin_roots(resolved, workspace):
            detail = "write path is outside allowed admin paths" if allow_write else "path is outside allowed admin paths"
            return None, f"Error: {detail}: {path}"
        err = validate_path(resolved, allow_write=allow_write, permission_level=permission_level)
        if err:
            return None, err
        return resolved, None

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

    err = validate_path(resolved, allow_write=allow_write, permission_level=permission_level)
    if err:
        return None, err
    return resolved, None


def validate_path(path: str, allow_write: bool = False, *, permission_level: int = 2) -> str | None:
    """Returns error string if path is blocked, None if OK."""
    resolved = os.path.realpath(os.path.expanduser(path))
    live_db_err = _live_db_path_error(resolved)
    if live_db_err:
        return live_db_err
    if permission_level >= 4:
        return None
    protected = _protected_path_error(resolved)
    if protected:
        return protected
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
