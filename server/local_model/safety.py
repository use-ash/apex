"""Safety constraints for local model tool execution."""
import os

MAX_COMMAND_TIMEOUT = 120
DEFAULT_COMMAND_TIMEOUT = 30
MAX_OUTPUT_CHARS = 50_000
MAX_FILE_READ_LINES = 2000
MAX_FILE_WRITE_BYTES = 5 * 1024 * 1024  # 5MB
MAX_LIST_FILES = 500
MAX_SEARCH_MATCHES = 100

BLOCKED_COMMAND_PATTERNS = [
    "rm -rf /",
    "rm -fr /",
    "mkfs",
    "dd if=/dev/",
    "> /dev/sd",
    "> /dev/nvme",
    "chmod -R 777 /",
    ":(){ :|:& };:",  # fork bomb
    "shutdown",
    "reboot",
    "halt",
    "init 0",
    "init 6",
]

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


def validate_command(command: str) -> str | None:
    """Returns error string if command is blocked, None if OK."""
    cmd_lower = command.lower().strip()
    for pattern in BLOCKED_COMMAND_PATTERNS:
        if pattern.lower() in cmd_lower:
            return f"Error: blocked command pattern: {pattern}"
    return None


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
