"""Background task registry for Apex.

Layer 2: depends on state (Layer 0), log (Layer 0).
Nothing above Layer 2 imports this module directly — callers use the
public accessor functions below. No direct state._tasks access outside
this module.

Tasks run as asyncio coroutines. Status is in-memory only — tasks do
not survive a server restart. Callers receive a TaskRecord immediately;
progress is available via routes_tasks.py endpoints or SSE live-tail.

Architectural constraints (per Architect sign-off):
  - chat_id is a required first-class field on every TaskRecord
  - All state access goes through accessor functions, not state._tasks
  - _watch_bg_skill migration is out of scope for this module
"""
from __future__ import annotations

import asyncio
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Coroutine

import state
from log import log

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

TERMINAL_STATUSES = frozenset({STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED})

# Maximum output lines kept per task — avoids unbounded memory growth on
# long-running tasks that emit many lines.
_MAX_OUTPUT_LINES = 500


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TaskRecord:
    task_id: str
    name: str
    chat_id: str                                    # first-class; used for filtering
    status: str = STATUS_PENDING
    created_at: str = field(default_factory=lambda: _now())
    started_at: str | None = None
    finished_at: str | None = None
    meta: dict = field(default_factory=dict)        # caller-supplied context
    result: str | None = None                       # final output on success
    error: str | None = None                        # exception message on failure
    output: deque = field(
        default_factory=lambda: deque(maxlen=_MAX_OUTPUT_LINES)
    )
    # Internal handle — excluded from serialization by routes layer
    _asyncio_task: object = field(default=None, repr=False)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Public accessors — the only permitted interface to state._tasks
# ---------------------------------------------------------------------------

def get_task(task_id: str) -> TaskRecord | None:
    """Return the TaskRecord for task_id, or None if unknown."""
    return state._tasks.get(task_id)


def list_tasks(
    status: str | None = None,
    chat_id: str | None = None,
    limit: int = 50,
) -> list[TaskRecord]:
    """Return tasks newest-first, optionally filtered by status and/or chat_id."""
    tasks: list[TaskRecord] = list(state._tasks.values())
    if status:
        tasks = [t for t in tasks if t.status == status]
    if chat_id:
        tasks = [t for t in tasks if t.chat_id == chat_id]
    # ISO timestamps sort lexicographically — no datetime parsing needed
    tasks.sort(key=lambda t: t.created_at, reverse=True)
    return tasks[:limit]


def append_output(task_id: str, line: str) -> None:
    """Append a line to task output and wake any SSE waiters."""
    record = state._tasks.get(task_id)
    if record is None:
        return
    record.output.append(line)
    _notify_waiters(task_id)


def cancel_task(task_id: str) -> bool:
    """Request cancellation of a pending or running task.

    Returns True if cancellation was requested, False if the task was
    already terminal or unknown.
    """
    record = state._tasks.get(task_id)
    if record is None:
        return False
    if record.status in TERMINAL_STATUSES:
        return False
    asyncio_task = record._asyncio_task
    if asyncio_task is not None:
        asyncio_task.cancel()
    # Status is set immediately so callers see CANCELLED right away;
    # _run_task will also set it when CancelledError propagates.
    record.status = STATUS_CANCELLED
    record.finished_at = _now()
    _notify_waiters(task_id)
    return True


# ---------------------------------------------------------------------------
# Task creation
# ---------------------------------------------------------------------------

def create_task(
    name: str,
    chat_id: str,
    coro: Coroutine,
    meta: dict | None = None,
) -> TaskRecord:
    """Register and immediately schedule a background coroutine.

    Returns a TaskRecord with a stable task_id before the coroutine
    starts running. Coroutines should write progress via
    append_output(task_id, line).

    Args:
        name:    Human-readable label (e.g. "codex: refactor auth.py").
        chat_id: The chat that originated the task — required for filtering.
        coro:    An unawaited coroutine object.
        meta:    Optional caller context stored verbatim on the record.
    """
    task_id = str(uuid.uuid4())
    record = TaskRecord(
        task_id=task_id,
        name=name,
        chat_id=chat_id,
        meta=meta or {},
    )
    state._tasks[task_id] = record
    asyncio_task = asyncio.create_task(
        _run_task(record, coro),
        name=f"apex-task-{task_id[:8]}",
    )
    record._asyncio_task = asyncio_task
    log(f"[tasks] created task={task_id[:8]} name={name!r} chat={chat_id}")
    return record


# ---------------------------------------------------------------------------
# Internal runner
# ---------------------------------------------------------------------------

async def _run_task(record: TaskRecord, coro: Coroutine) -> None:
    """Wrap a coroutine with lifecycle bookkeeping. Never raises."""
    record.status = STATUS_RUNNING
    record.started_at = _now()
    try:
        result = await coro
        record.result = str(result) if result is not None else ""
        record.status = STATUS_DONE
        log(f"[tasks] done task={record.task_id[:8]} name={record.name!r}")
    except asyncio.CancelledError:
        # Status may already be CANCELLED (set by cancel_task); that's fine.
        record.status = STATUS_CANCELLED
        log(f"[tasks] cancelled task={record.task_id[:8]}")
    except Exception as exc:
        record.status = STATUS_FAILED
        record.error = str(exc)
        log(f"[tasks] failed task={record.task_id[:8]} error={exc!r}")
    finally:
        record.finished_at = _now()
        _notify_waiters(record.task_id)


def _notify_waiters(task_id: str) -> None:
    """Set all registered SSE events so live-tail clients unblock."""
    for event in state._task_output_waiters.get(task_id, []):
        event.set()


def register_waiter(task_id: str, event: asyncio.Event) -> None:
    """Register an asyncio.Event to be notified on task output or completion."""
    state._task_output_waiters.setdefault(task_id, []).append(event)


def deregister_waiter(task_id: str, event: asyncio.Event) -> None:
    """Remove a previously registered SSE waiter event."""
    waiters = state._task_output_waiters.get(task_id)
    if waiters is None:
        return
    try:
        waiters.remove(event)
    except ValueError:
        pass
