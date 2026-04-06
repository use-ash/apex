"""Jupyter kernel-backed code execution tool for local models.

Provides a stateful Python execution environment — variables, imports,
and function definitions persist between calls within the same kernel.
Kernels are keyed by (workspace, chat_id) for per-chat isolation.
Cell history is saved to disk and replayed on kernel restart to restore state.

Requires: jupyter_client, ipykernel (optional deps in requirements.txt).
"""

import atexit
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty

from jupyter_client import KernelManager
from jupyter_client.blocking import BlockingKernelClient

from ..safety import truncate_output, MAX_OUTPUT_CHARS, _primary_workspace

log = logging.getLogger("apex.execute_code")

# ── Config ────────────────────────────────────────────────────────────

DEFAULT_TIMEOUT = 30       # seconds per cell execution
MAX_TIMEOUT = 120          # hard cap on user-requested timeout
IDLE_SHUTDOWN_SECS = 600   # kill kernels idle > 10 minutes
REAPER_INTERVAL = 60       # check for idle kernels every 60s
KERNEL_STARTUP_TIMEOUT = 30  # seconds to wait for kernel ready
REPLAY_TIMEOUT = 10        # seconds per cell during replay (shorter — skip slow cells)
MAX_HISTORY_CELLS = 200    # cap history to prevent unbounded replay

# Where cell history lives on disk
_STATE_DIR: Path | None = None


def _get_state_dir() -> Path:
    """Lazily resolve the state directory for kernel cell history."""
    global _STATE_DIR
    if _STATE_DIR is None:
        # state/ is next to the server directory
        server_dir = Path(__file__).resolve().parent.parent.parent
        _STATE_DIR = server_dir / "state" / "kernels"
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
    return _STATE_DIR


# ── Cell history persistence ─────────────────────────────────────────

def _history_path(kernel_key: str) -> Path:
    """Path to cell history file for a kernel key."""
    # Sanitize key for filesystem (replace / and other bad chars)
    safe_key = kernel_key.replace("/", "_").replace("\\", "_").replace(":", "_")
    return _get_state_dir() / f"{safe_key}.jsonl"


def _save_cell(kernel_key: str, code: str, success: bool):
    """Append a cell to the history file. Only saves successful cells."""
    if not success:
        return
    path = _history_path(kernel_key)
    try:
        with open(path, "a") as f:
            f.write(json.dumps({"code": code, "ts": time.time()}) + "\n")
    except Exception as e:
        log.warning("Failed to save cell history: %s", e)


def _load_history(kernel_key: str) -> list[str]:
    """Load cell history from disk. Returns list of code strings."""
    path = _history_path(kernel_key)
    if not path.exists():
        return []
    cells = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    cells.append(entry["code"])
                except (json.JSONDecodeError, KeyError):
                    continue
    except Exception as e:
        log.warning("Failed to load cell history: %s", e)
    return cells[-MAX_HISTORY_CELLS:]  # keep last N


def _clear_history(kernel_key: str):
    """Remove cell history file."""
    path = _history_path(kernel_key)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


# ── Kernel lifecycle ──────────────────────────────────────────────────

@dataclass
class KernelContext:
    """Wraps a running Jupyter kernel with metadata."""
    km: KernelManager
    kc: BlockingKernelClient
    kernel_key: str
    last_used: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)
    cell_count: int = 0


_kernels: dict[str, KernelContext] = {}
_global_lock = threading.Lock()
_reaper_started = False


def _make_kernel_key(workspace: str | None, chat_id: str | None) -> str:
    """Build a kernel key from workspace + chat_id."""
    ws = _primary_workspace(workspace) or "__default__"
    if chat_id:
        return f"{ws}::{chat_id}"
    return ws


def _start_kernel(kernel_key: str, workspace_key: str | None = None) -> KernelContext:
    """Start a new Jupyter kernel."""
    km = KernelManager(kernel_name="python3")

    # Resolve workspace directory for cwd
    ws_dir = workspace_key or kernel_key.split("::")[0]
    env = os.environ.copy()
    if ws_dir and ws_dir != "__default__" and os.path.isdir(ws_dir):
        km.cwd = ws_dir
        env["APEX_WORKSPACE"] = ws_dir

    km.start_kernel(env=env)

    kc = km.blocking_client()
    kc.start_channels()
    kc.wait_for_ready(timeout=KERNEL_STARTUP_TIMEOUT)

    # Inject preamble — set cwd and basic imports
    preamble = "import os, sys\n"
    if ws_dir and ws_dir != "__default__" and os.path.isdir(ws_dir):
        preamble += f"os.chdir({ws_dir!r})\n"

    msg_id = kc.execute(preamble, silent=True)
    _drain_iopub(kc, msg_id, timeout=10)

    ctx = KernelContext(km=km, kc=kc, kernel_key=kernel_key)
    try:
        pid = km.provisioner.pid if hasattr(km, 'provisioner') else "unknown"
    except Exception:
        pid = "unknown"
    log.info("Started Jupyter kernel for %s (pid=%s)", kernel_key, pid)
    return ctx


def _replay_history(ctx: KernelContext):
    """Replay saved cell history into a fresh kernel to restore state.

    Runs each cell silently — output is discarded. Cells that error are
    skipped (the user will see errors when they re-run interactively).
    """
    cells = _load_history(ctx.kernel_key)
    if not cells:
        return

    log.info("Replaying %d cells for %s", len(cells), ctx.kernel_key)
    replayed = 0
    for code in cells:
        try:
            msg_id = ctx.kc.execute(code, silent=True)
            outputs = _drain_iopub(ctx.kc, msg_id, timeout=REPLAY_TIMEOUT)
            replayed += 1
        except Exception as e:
            log.warning("Replay cell failed for %s: %s", ctx.kernel_key, e)
            # Continue — skip failed cells

    ctx.cell_count = replayed
    log.info("Replayed %d/%d cells for %s", replayed, len(cells), ctx.kernel_key)


def _get_or_create_kernel(workspace: str | None, chat_id: str | None = None) -> KernelContext:
    """Get existing kernel for (workspace, chat_id) or create a new one."""
    global _reaper_started
    kernel_key = _make_kernel_key(workspace, chat_id)

    with _global_lock:
        ctx = _kernels.get(kernel_key)
        if ctx is not None:
            if ctx.km.is_alive():
                ctx.last_used = time.monotonic()
                return ctx
            else:
                log.warning("Kernel for %s found dead, restarting", kernel_key)
                _cleanup_kernel(ctx)
                del _kernels[kernel_key]

        # Create new kernel (hold lock to prevent double-create)
        ws_key = _primary_workspace(workspace) or "__default__"
        ctx = _start_kernel(kernel_key, workspace_key=ws_key)

        # Replay history to restore state from a previous session
        _replay_history(ctx)

        _kernels[kernel_key] = ctx

        # Start reaper thread on first kernel creation
        if not _reaper_started:
            t = threading.Thread(target=_idle_reaper, daemon=True, name="kernel-reaper")
            t.start()
            _reaper_started = True

        return ctx


def _cleanup_kernel(ctx: KernelContext):
    """Shut down a single kernel context."""
    try:
        ctx.kc.stop_channels()
    except Exception:
        pass
    try:
        if ctx.km.is_alive():
            ctx.km.shutdown_kernel(now=True)
    except Exception as e:
        log.warning("Error shutting down kernel: %s", e)


def shutdown_all_kernels():
    """Shut down all running kernels. Called on server teardown."""
    with _global_lock:
        for key, ctx in list(_kernels.items()):
            log.info("Shutting down kernel for %s", key)
            _cleanup_kernel(ctx)
        _kernels.clear()


def _idle_reaper():
    """Background thread that kills idle kernels."""
    while True:
        time.sleep(REAPER_INTERVAL)
        now = time.monotonic()
        with _global_lock:
            expired = [
                key for key, ctx in _kernels.items()
                if now - ctx.last_used > IDLE_SHUTDOWN_SECS
            ]
            for key in expired:
                ctx = _kernels.pop(key)
                log.info("Reaping idle kernel for %s (idle %.0fs)", key, now - ctx.last_used)
                _cleanup_kernel(ctx)


atexit.register(shutdown_all_kernels)


# ── Execution ─────────────────────────────────────────────────────────

def _drain_iopub(kc: BlockingKernelClient, msg_id: str, timeout: int = DEFAULT_TIMEOUT) -> list[str]:
    """Collect IOPub messages for a given msg_id until kernel goes idle.

    Returns list of output strings (stdout, stderr, error tracebacks, results).
    """
    outputs: list[str] = []
    deadline = time.monotonic() + timeout

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            outputs.append("\n[execution timed out]")
            break

        try:
            msg = kc.get_iopub_msg(timeout=min(remaining, 5.0))
        except Empty:
            continue

        # Only process messages belonging to our execution
        parent_id = msg.get("parent_header", {}).get("msg_id")
        if parent_id != msg_id:
            continue

        msg_type = msg["header"]["msg_type"]
        content = msg.get("content", {})

        if msg_type == "status" and content.get("execution_state") == "idle":
            break
        elif msg_type == "stream":
            outputs.append(content.get("text", ""))
        elif msg_type == "error":
            # Format traceback without ANSI escape codes
            import re
            tb = content.get("traceback", [])
            clean_tb = [re.sub(r"\x1b\[[0-9;]*m", "", line) for line in tb]
            outputs.append("\n".join(clean_tb))
        elif msg_type == "execute_result":
            data = content.get("data", {})
            text = data.get("text/plain", "")
            if text:
                outputs.append(text)
        elif msg_type == "display_data":
            data = content.get("data", {})
            text = data.get("text/plain", "")
            if text:
                outputs.append(text)

    return outputs


def _is_error_output(outputs: list[str]) -> bool:
    """Check if any output looks like an error traceback."""
    combined = "".join(outputs)
    return "Traceback" in combined or "Error:" in combined


def execute(
    args: dict,
    workspace: str | None = None,
    *,
    permission_level: int = 2,
    chat_id: str | None = None,
) -> str:
    """Execute Python code in a stateful Jupyter kernel.

    Follows the standard local model tool executor signature.
    chat_id is used for per-chat kernel isolation.
    """
    code = args.get("code", "").strip()
    if not code:
        return "Error: no code provided"

    # Parse timeout
    try:
        timeout = min(int(args.get("timeout", DEFAULT_TIMEOUT)), MAX_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT

    # Get or create kernel (per-chat isolation)
    try:
        ctx = _get_or_create_kernel(workspace, chat_id=chat_id)
    except Exception as e:
        return f"Error starting Jupyter kernel: {type(e).__name__}: {e}"

    # Execute under the kernel's lock to prevent interleaved IOPub collection
    with ctx.lock:
        ctx.last_used = time.monotonic()
        try:
            msg_id = ctx.kc.execute(code)
            outputs = _drain_iopub(ctx.kc, msg_id, timeout=timeout)
        except Exception as e:
            return f"Error executing code: {type(e).__name__}: {e}"

    result = "".join(outputs).strip()
    success = not _is_error_output(outputs)

    # Persist cell to history (only successful cells, for replay on restart)
    _save_cell(ctx.kernel_key, code, success=success)
    ctx.cell_count += 1

    if not result:
        return "(no output)"

    return truncate_output(result)
