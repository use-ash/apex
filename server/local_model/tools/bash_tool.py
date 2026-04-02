"""Bash command execution tool."""
import subprocess
from ..safety import (
    prepare_command, truncate_output,
    DEFAULT_COMMAND_TIMEOUT, MAX_COMMAND_TIMEOUT,
    _primary_workspace,
)


def execute(args: dict, workspace: str | None = None) -> str:
    """Execute a bash command and return output."""
    command = args.get("command", "").strip()
    if not command:
        return "Error: no command provided"

    argv, err = prepare_command(command, workspace)
    if err:
        return err

    try:
        timeout = min(int(args.get("timeout", DEFAULT_COMMAND_TIMEOUT)), MAX_COMMAND_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEFAULT_COMMAND_TIMEOUT

    try:
        result = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=_primary_workspace(workspace),
        )
        output = result.stdout
        if result.stderr:
            output += ("\n" if output else "") + result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return truncate_output(output) if output else "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout} seconds"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
