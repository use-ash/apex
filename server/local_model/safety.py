"""Safety constraints for local model tool execution."""
import json
import os
import re
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
LEVEL3_FIND_EXEC_SENTINEL = "__APEX_FIND_EXEC_SEMI__"

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

LEVEL3_WRITE_GIT_SUBCOMMANDS = {
    "add",
    "commit",
}

LEVEL3_ALLOWED_GIT_ADD_FLAGS = {
    "-A",
    "--all",
    "-u",
    "--update",
    "-N",
    "--intent-to-add",
    "--",
}

LEVEL3_ALLOWED_GIT_COMMIT_FLAGS = {
    "-a",
    "--all",
    "-m",
    "--message",
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
DEFAULT_LEVEL3_ALLOWED_COMMANDS = frozenset(
    {
        "awk",
        "basename",
        "bun",
        "cat",
        "cd",
        "chmod",
        "comm",
        "cp",
        "curl",
        "cut",
        "date",
        "df",
        "diff",
        "dirname",
        "du",
        "echo",
        "env",
        "file",
        "find",
        "git",
        "grep",
        "head",
        "jq",
        "kill",
        "ln",
        "ls",
        "lsof",
        "make",
        "mkdir",
        "mv",
        "npm",
        "npx",
        "open",
        "pgrep",
        "pip",
        "pip3",
        "pkill",
        "pnpm",
        "printenv",
        "ps",
        "pwd",
        "pytest",
        "python",
        "python3",
        "realpath",
        "rg",
        "rm",
        "sed",
        "sort",
        "sqlite3",
        "stat",
        "tail",
        "tar",
        "touch",
        "tr",
        "uniq",
        "unzip",
        "uv",
        "uvx",
        "wc",
        "which",
        "xargs",
        "yarn",
        "zip",
    }
)
PROTECTED_PATHS = {
    os.path.realpath(str(APEX_ROOT / "state" / "apex.db")),
    os.path.realpath(str(APEX_ROOT / "state" / "config.json")),
    os.path.realpath(str(APEX_ROOT / "ssl")),
    os.path.realpath(str(APEX_ROOT / "state" / "ssl")),
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
LEVEL3_SAFE_STDERR_REDIRECT_RE = re.compile(r"(?<!\\)(?<!\S)2\s*>>?\s*/dev/null\b")


def _is_env_path(path: str) -> bool:
    base = os.path.basename(path)
    return base == ".env" or base.startswith(".env.")


def _live_db_path_error(path: str) -> str | None:
    for blocked in LIVE_APEX_DB_PATHS:
        if path == blocked:
            return f"Error: access to live Apex database is blocked: {path}"
    return None


def _read_policy_config() -> dict:
    config_path = APEX_ROOT / "state" / "config.json"
    try:
        if config_path.exists():
            data = json.loads(config_path.read_text())
            if isinstance(data, dict):
                return data.get("policy", {}) or {}
    except Exception:
        pass
    return {}


def _parse_multiline_policy_list(raw: object) -> list[str]:
    text = str(raw or "").replace("\r\n", "\n").replace("\r", "\n")
    values: list[str] = []
    for line in text.split("\n"):
        item = line.strip()
        if item and item not in values:
            values.append(item)
    return values


def get_policy_never_allowed_commands() -> list[str]:
    return _parse_multiline_policy_list(_read_policy_config().get("never_allowed_commands", ""))


def get_policy_blocked_path_prefixes() -> list[str]:
    raw = _parse_multiline_policy_list(_read_policy_config().get("blocked_path_prefixes", ""))
    normalized: list[str] = []
    for item in raw:
        resolved = os.path.realpath(os.path.expanduser(item))
        if resolved not in normalized:
            normalized.append(resolved)
    return normalized


def _protected_path_error(path: str) -> str | None:
    live_db_err = _live_db_path_error(path)
    if live_db_err:
        return live_db_err
    for blocked_prefix in get_policy_blocked_path_prefixes():
        if path == blocked_prefix or path.startswith(blocked_prefix + os.sep):
            return f"Error: access to blocked path is denied by system policy: {path}"
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
        blocked_args = {"-delete", "-execdir", "-ok", "-okdir", "-fprintf", "-fprint", "-fls"}
        for arg in argv[1:]:
            if arg in blocked_args:
                return f"Error: find argument is blocked: {arg}"
        if "-exec" in argv[1:]:
            exec_positions = [idx for idx, arg in enumerate(argv) if arg == "-exec"]
            if len(exec_positions) != 1:
                return "Error: find argument is blocked: -exec"
            exec_idx = exec_positions[0]
            try:
                term_idx = argv.index(";", exec_idx + 1)
            except ValueError:
                return "Error: find argument is blocked: -exec"
            exec_cmd = argv[exec_idx + 1 : term_idx]
            if not exec_cmd or exec_cmd[0] != "grep" or exec_cmd[-1] != "{}":
                return "Error: find argument is blocked: -exec"
            allowed_grep_flags = {
                "-l",
                "-i",
                "-n",
                "-E",
                "-F",
                "-e",
                "--line-number",
                "--files-with-matches",
                "--ignore-case",
                "--extended-regexp",
                "--fixed-strings",
            }
            for token in exec_cmd[1:-1]:
                if token.startswith("-") and token not in allowed_grep_flags:
                    return "Error: find argument is blocked: -exec"
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
        if subcommand == "add":
            path_args: list[str] = []
            for token in argv[i + 1 :]:
                if token in LEVEL3_ALLOWED_GIT_ADD_FLAGS:
                    continue
                if token.startswith("-"):
                    return f"Error: git add flag is not allowed: {token}"
                path_args.append(token)
            return _validate_write_capable_arg_paths(path_args, workspace)

        if subcommand == "commit":
            args = argv[i + 1 :]
            if not args:
                return "Error: git commit requires -m/--message"
            saw_message = False
            idx = 0
            while idx < len(args):
                token = args[idx]
                if token in {"-a", "--all"}:
                    idx += 1
                    continue
                if token in {"-m", "--message"}:
                    if idx + 1 >= len(args):
                        return "Error: git commit requires a message"
                    saw_message = True
                    idx += 2
                    continue
                return f"Error: git commit flag is not allowed: {token}"
            if not saw_message:
                return "Error: git commit requires -m/--message"
            return None

        return f"Error: git subcommand is not allowed: {subcommand}"

    return _validate_arg_paths(argv[i + 1 :], workspace)


def _validate_python_command(argv: list[str], workspace: str | None) -> str | None:
    if len(argv) == 2 and argv[1] in {"-V", "--version"}:
        return None
    if len(argv) >= 4 and argv[1] == "-m" and argv[2] == "py_compile":
        return _validate_arg_paths(argv[3:], workspace)
    if len(argv) >= 2:
        script = argv[1]
        if not script.startswith("-") and script.endswith(".py"):
            resolved, err = ensure_workspace_path(
                script,
                workspace,
                permission_level=3,
            )
            if err:
                return err
            return _validate_arg_paths(argv[2:], workspace)
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
    for blocked_prefix in get_policy_blocked_path_prefixes():
        if blocked_prefix in normalized_command:
            return f"Error: access to blocked path is denied by system policy: {blocked_prefix}"
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
            blocked = _protected_path_error(resolved)
            if blocked and "system policy" in blocked:
                return blocked
    return None


def _normalize_command_text(command: str) -> str:
    try:
        return " ".join(shlex.split(command, posix=True))
    except ValueError:
        return " ".join(command.strip().split())


def _strip_level3_safe_stderr_redirects(command: str) -> str:
    return LEVEL3_SAFE_STDERR_REDIRECT_RE.sub("", command)


def _normalize_level3_command_for_shell_split(command: str) -> str:
    return _strip_level3_safe_stderr_redirects(command).replace(r"\;", LEVEL3_FIND_EXEC_SENTINEL)


def _restore_level3_command_tokens(command: str) -> str:
    return command.replace(LEVEL3_FIND_EXEC_SENTINEL, ";")


def _effective_allowed_commands(
    permission_level: int,
    allowed_commands: list[str] | None,
) -> list[str]:
    cleaned = [str(entry).strip() for entry in (allowed_commands or []) if str(entry).strip()]
    if cleaned:
        return cleaned
    if permission_level >= 3:
        return sorted(DEFAULT_LEVEL3_ALLOWED_COMMANDS)
    return cleaned


def _command_matches_allowed_prefix(command: str, allowed_commands: list[str] | None) -> bool:
    normalized = _normalize_command_text(command)
    for entry in allowed_commands or []:
        prefix = _normalize_command_text(entry)
        if not prefix:
            continue
        if normalized == prefix or normalized.startswith(prefix + " "):
            return True
    return False


def _command_matches_blocked_prefix(command: str, blocked_commands: list[str] | None) -> str | None:
    normalized = _normalize_command_text(command)
    for entry in blocked_commands or []:
        prefix = _normalize_command_text(entry)
        if not prefix:
            continue
        if normalized == prefix or normalized.startswith(prefix + " "):
            return entry
    return None


def _contains_disallowed_shell_syntax(
    command: str,
    *,
    permission_level: int,
    allowed_commands: list[str] | None = None,
) -> bool:
    if permission_level >= 3:
        command = _strip_level3_safe_stderr_redirects(command)
    effective_allowed = _effective_allowed_commands(permission_level, allowed_commands)
    if permission_level >= 3 and any(
        snippet in command for snippet in LEVEL3_ALLOWED_SHELL_META_SNIPPETS
    ):
        return any(snippet in command for snippet in LEVEL3_BLOCKED_SHELL_META_SNIPPETS)
    if permission_level >= 3 and _command_matches_allowed_prefix(command, effective_allowed):
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
    segment = _restore_level3_command_tokens(segment)
    effective_allowed = _effective_allowed_commands(3, allowed_commands)
    if not _command_matches_allowed_prefix(segment, effective_allowed):
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
        sanitized = _normalize_level3_command_for_shell_split(command)
        lexer = shlex.shlex(sanitized.replace("\n", " ; "), posix=True, punctuation_chars="|&;")
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


def _validate_system_blocked_command(command: str) -> str | None:
    blocked_commands = get_policy_never_allowed_commands()
    if not blocked_commands:
        return None
    segments, err = _split_level3_shell_segments(command)
    if err:
        normalized = _normalize_command_text(command)
        for entry in blocked_commands:
            prefix = _normalize_command_text(entry)
            if prefix and (normalized == prefix or normalized.startswith(prefix + " ")):
                return f"Error: command is denied by system policy: {entry}"
        return None
    for segment in segments or []:
        match = _command_matches_blocked_prefix(segment, blocked_commands)
        if match:
            return f"Error: command is denied by system policy: {match}"
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
    effective_allowed = _effective_allowed_commands(permission_level, allowed_commands)
    if permission_level <= 0:
        return None, "Error: tools are disabled for this persona"
    blocked_command_err = _validate_system_blocked_command(cmd)
    if blocked_command_err:
        return None, blocked_command_err
    live_db_err = _validate_live_db_command_paths(cmd, workspace)
    if live_db_err:
        return None, live_db_err
    if permission_level >= 4:
        return ["/bin/sh", "-lc", cmd], None
    if _contains_disallowed_shell_syntax(
        cmd,
        permission_level=permission_level,
        allowed_commands=effective_allowed,
    ):
        return None, "Error: shell syntax is not allowed"
    if (
        permission_level >= 3
        and any(snippet in cmd for snippet in LEVEL3_ALLOWED_SHELL_META_SNIPPETS)
    ):
        err = _validate_level3_shell_command(cmd, workspace, effective_allowed)
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
        if permission_level >= 3 and allowed_commands and _command_matches_allowed_prefix(cmd, allowed_commands):
            return argv, _validate_write_capable_arg_paths(argv[1:], workspace)
        return argv, git_err
    if exe in PYTHON_COMMANDS or base in PYTHON_COMMANDS:
        py_err = _validate_python_command(argv, workspace)
        if not py_err:
            return argv, None
        if permission_level >= 3 and allowed_commands and _command_matches_allowed_prefix(cmd, allowed_commands):
            return argv, _validate_write_capable_arg_paths(argv[1:], workspace)
        return argv, py_err
    if permission_level >= 3 and _command_matches_allowed_prefix(cmd, effective_allowed):
        return argv, _validate_write_capable_arg_paths(argv[1:], workspace)
    return None, f"Error: command '{exe}' is not permitted at permission level {permission_level}. Level 4 (Admin) allows unrestricted shell commands."


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
    for blocked_prefix in get_policy_blocked_path_prefixes():
        if resolved == blocked_prefix or resolved.startswith(blocked_prefix + os.sep):
            return f"Error: access to blocked path is denied by system policy: {resolved}"
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
