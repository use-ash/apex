"""Task registry HTTP surface.

Layer 4: imports from tasks (Layer 2), log (Layer 0), state (Layer 0).

Endpoints:
  GET    /api/tasks                 — list tasks (filterable by status, chat_id)
  GET    /api/tasks/{id}            — full record + last 500 output lines
  DELETE /api/tasks/{id}            — cancel a pending/running task
  GET    /api/tasks/{id}/output     — SSE live-tail of output lines

Tasks are created internally (e.g. by skills.py via tasks.create_task).
There is no POST endpoint — callers don't create tasks over HTTP.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse

from log import log
from tasks import (
    STATUS_CANCELLED,
    TERMINAL_STATUSES,
    cancel_task,
    deregister_waiter,
    get_task,
    list_tasks,
    register_waiter,
)

tasks_router = APIRouter()


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _record_to_dict(record, *, include_output: bool = False) -> dict:
    d = {
        "task_id": record.task_id,
        "name": record.name,
        "chat_id": record.chat_id,
        "status": record.status,
        "created_at": record.created_at,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "meta": record.meta,
        "result": record.result,
        "error": record.error,
    }
    if include_output:
        d["output"] = list(record.output)
    return d


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@tasks_router.get("/api/tasks")
async def api_list_tasks(
    status: str | None = None,
    chat_id: str | None = None,
    limit: int = 50,
):
    """List tasks, newest first. Supports ?status= and ?chat_id= filters."""
    tasks = list_tasks(status=status, chat_id=chat_id, limit=min(limit, 200))
    return JSONResponse({"tasks": [_record_to_dict(t) for t in tasks]})


@tasks_router.get("/api/tasks/{task_id}")
async def api_get_task(task_id: str):
    """Return a single task record including full output buffer."""
    record = get_task(task_id)
    if record is None:
        return JSONResponse({"error": "task not found"}, status_code=404)
    return JSONResponse(_record_to_dict(record, include_output=True))


@tasks_router.delete("/api/tasks/{task_id}")
async def api_cancel_task(task_id: str):
    """Cancel a pending or running task."""
    record = get_task(task_id)
    if record is None:
        return JSONResponse({"error": "task not found"}, status_code=404)
    if record.status in TERMINAL_STATUSES:
        return JSONResponse(
            {"error": f"task already {record.status}"}, status_code=409
        )
    cancel_task(task_id)
    return JSONResponse({"ok": True, "task_id": task_id, "status": STATUS_CANCELLED})


@tasks_router.get("/api/tasks/{task_id}/output")
async def api_task_output_stream(task_id: str):
    """SSE live-tail of task output lines.

    Streams data: {"line": "..."} events as output is appended.
    Sends a final data: {"status": "...", "done": true} when the task
    reaches a terminal state, then closes the connection.

    Clients that connect after the task is already done receive the
    buffered output and the terminal event in a single response.
    """
    record = get_task(task_id)
    if record is None:
        return JSONResponse({"error": "task not found"}, status_code=404)

    async def event_stream():
        sent = 0
        while True:
            # Drain any lines accumulated since last wake
            lines = list(record.output)
            for line in lines[sent:]:
                yield f"data: {json.dumps({'line': line})}\n\n"
                sent += 1

            # Terminal — send final status event and stop
            if record.status in TERMINAL_STATUSES:
                yield f"data: {json.dumps({'status': record.status, 'done': True})}\n\n"
                break

            # Register as a waiter, block until new output or completion
            event = asyncio.Event()
            register_waiter(task_id, event)
            try:
                await asyncio.wait_for(event.wait(), timeout=25.0)
            except asyncio.TimeoutError:
                pass
            finally:
                deregister_waiter(task_id, event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering for proxied setups
        },
    )
