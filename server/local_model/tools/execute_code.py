"""Jupyter kernel-backed code execution tool for local models.

Provides a stateful Python execution environment — variables, imports,
and function definitions persist between calls within the same kernel.
Kernels are keyed by workspace path and auto-shutdown after idle timeout.

Requires: jupyter_client, ipykernel (optional deps in requirements.txt).
"""

import atexit
import logging
import os
import threading
import time
from dataclasses import dataclass, field
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


# ── Kernel lifecycle ──────────────────────────────────────────────────

@dataclass
class KernelContext:
    """Wraps a running Jupyter kernel with metadata."""
    km: KernelManager
    kc: BlockingKernelClient
    workspace_key: str
    last_used: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)


_kernels: dict[str, KernelContext] = {}
_global_lock = threading.Lock()
_reaper_started = False


def _start_kernel(workspace_key: str) -> KernelContext:
    """Start a new Jupyter kernel for the given workspace."""
    km = KernelManager(kernel_name="python3")

    # Set working directory for the kernel process
    env = os.environ.copy()
    if workspace_key and os.path.isdir(workspace_key):
        km.cwd = workspace_key
        env["APEX_WORKSPACE"] = workspace_key

    km.start_kernel(env=env)

    kc = km.blocking_client()
    kc.start_channels()
    kc.wait_for_ready(timeout=KERNEL_STARTUP_TIMEOUT)

    # Inject preamble — set cwd and basic imports
    preamble = "import os, sys\n"
    if workspace_key and os.path.isdir(workspace_key):
        preamble += f"os.chdir({workspace_key!r})\n"

    msg_id = kc.execute(preamble, silent=True)
    # Drain preamble output (don't care about results)
    _drain_iopub(kc, msg_id, timeout=10)

    ctx = KernelContext(km=km, kc=kc, workspace_key=workspace_key)
    try:
        pid = km.provisioner.pid if hasattr(km, 'provisioner') else "unknown"
    except Exception:
        pid = "unknown"
    log.info("Started Jupyter kernel for workspace %s (pid=%s)", workspace_key, pid)
    return ctx


def _get_or_create_kernel(workspace: str | None) -> KernelContext:
    """Get existing kernel for workspace or create a new one."""
    global _reaper_started
    workspace_key = _primary_workspace(workspace) or "__default__"

    with _global_lock:
        ctx = _kernels.get(workspace_key)
        if ctx is not None:
            # Verify kernel is still alive
            if ctx.km.is_alive():
                ctx.last_used = time.monotonic()
                return ctx
            else:
                # Dead kernel — clean up and recreate
                log.warning("Kernel for %s found dead, restarting", workspace_key)
                _cleanup_kernel(ctx)
                del _kernels[workspace_key]

        # Create new kernel (hold lock to prevent double-create)
        ctx = _start_kernel(workspace_key)
        _kernels[workspace_key] = ctx

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
            tb = content.get("traceback", [])
            import re
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


def execute(
    args: dict,
    workspace: str | None = None,
    *,
    permission_level: int = 2,
) -> str:
    """Execute Python code in a stateful Jupyter kernel.

    Follows the standard local model tool executor signature.
    """
    code = args.get("code", "").strip()
    if not code:
        return "Error: no code provided"

    # Parse timeout
    try:
        timeout = min(int(args.get("timeout", DEFAULT_TIMEOUT)), MAX_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT

    # Get or create kernel
    try:
        ctx = _get_or_create_kernel(workspace)
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

    if not result:
        return "(no output)"

    return truncate_output(result)
