"""Guardrail integration for local model tool execution.

Bridges guardrail_core (in workspace/scripts/guardrails/) and
secret filtering into the local model tool loop.
"""

import sys
from pathlib import Path

# Import WORKSPACE from canonical env registry (server/ in sys.path at runtime).
# Fall back to os.environ when executed standalone.
try:
    from env import WORKSPACE as _WORKSPACE_PATH  # type: ignore[import]
    _WORKSPACE = str(_WORKSPACE_PATH)
except ImportError:
    import os
    _WORKSPACE = os.environ.get("APEX_WORKSPACE", os.getcwd())

_GUARDRAILS_DIR = str(Path(_WORKSPACE) / "scripts" / "guardrails")

try:
    if _GUARDRAILS_DIR not in sys.path:
        sys.path.insert(0, _GUARDRAILS_DIR)
    from guardrail_core import check_tool_call
    from output_secret_filter import mask_output
    _AVAILABLE = True
except ImportError as e:
    _AVAILABLE = False
    try:
        with open(str(Path(_WORKSPACE) / "logs" / "agent_audit_errors.log"), "a") as f:
            f.write(f"guardrails import failed: {e}\n")
    except Exception:
        pass


def pre_check(tool_name: str, tool_args: dict, model: str = "unknown") -> str | None:
    """Pre-execution guardrail check. Returns None if allowed, error string if blocked."""
    if not _AVAILABLE:
        return None
    status, audit = check_tool_call(
        tool_name=tool_name,
        tool_input=tool_args,
        session_id=f"local:{model}",
        actor=model,
    )
    if status == "blocked":
        return f"BLOCKED: {audit.get('summary', 'guardrail violation')}"
    return None


def filter_output(tool_name: str, output: str, model: str = "unknown") -> str:
    """Post-execution output filter. Redacts secrets from tool results."""
    if not _AVAILABLE:
        return output
    if tool_name in ("bash", "read_file", "search_files"):
        masked, count = mask_output(output, session_id=f"local:{model}")
        return masked
    return output
