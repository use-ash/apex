"""Terminal WebSocket handler + REST routes for Apex.

WS  /ws/terminal?chat_id=<id>[&tmux_session=<name>]
GET /api/terminal/sessions  — list live tmux sessions
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import os
import pty
import re
import signal
import struct
import termios
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, WebSocket
from mtls import has_verified_peer_cert, mtls_required
from log import log
import env

SSL_CERT = env.SSL_CERT
SSL_CA = env.SSL_CA

terminal_router = APIRouter()

_TMUX_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")
_MAX_TERMINALS = 5
_IDLE_TIMEOUT = 1800  # 30 min


@dataclass
class _Session:
    master_fd: int
    proc: asyncio.subprocess.Process
    chat_id: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)


_sessions: dict[str, _Session] = {}
_resize_tokens: dict[str, tuple[float, float]] = {}  # chat_id -> (tokens, last_refill)


def _set_pty_size(fd: int, cols: int, rows: int) -> None:
    with contextlib.suppress(OSError):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def _allow_resize(chat_id: str) -> bool:
    now = time.monotonic()
    tokens, last = _resize_tokens.get(chat_id, (4.0, now))
    tokens = min(4.0, tokens + (now - last) * 2.0)
    if tokens < 1:
        _resize_tokens[chat_id] = (tokens, now)
        return False
    _resize_tokens[chat_id] = (tokens - 1, now)
    return True


async def _spawn(tmux_session: Optional[str]) -> tuple[int, asyncio.subprocess.Process]:
    master_fd, slave_fd = pty.openpty()
    _set_pty_size(master_fd, 220, 50)
    safe_env = {
        "HOME": os.environ.get("HOME", "/"),
        "USER": os.environ.get("USER", ""),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "SHELL": os.environ.get("SHELL", "/bin/bash"),
        "TERM": "xterm-256color",
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", ""),
    }
    if tmux_session:
        # Create session if it doesn't exist, then attach
        chk = await asyncio.create_subprocess_exec(
            "tmux", "has-session", "-t", tmux_session,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await chk.wait()
        if chk.returncode != 0:
            mk = await asyncio.create_subprocess_exec(
                "tmux", "new-session", "-d", "-s", tmux_session,
                env=safe_env,
            )
            await mk.wait()
        cmd = ["tmux", "attach-session", "-t", tmux_session]
    else:
        cmd = [os.environ.get("SHELL", "/bin/bash"), "-l"]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        preexec_fn=os.setsid,
        close_fds=True,
        env=safe_env,
    )
    os.close(slave_fd)
    return master_fd, proc


async def _cleanup(chat_id: str) -> None:
    sess = _sessions.pop(chat_id, None)
    if not sess:
        return
    with contextlib.suppress(OSError):
        os.close(sess.master_fd)
    with contextlib.suppress(OSError, ProcessLookupError):
        os.killpg(os.getpgid(sess.proc.pid), signal.SIGHUP)
    with contextlib.suppress(asyncio.TimeoutError, Exception):
        await asyncio.wait_for(sess.proc.wait(), timeout=5)
    _resize_tokens.pop(chat_id, None)
    log(f"terminal: cleaned up chat={chat_id[:8]}")


async def _pty_read(master_fd: int, ws: WebSocket, sess: _Session) -> None:
    loop = asyncio.get_running_loop()
    try:
        while True:
            data = await loop.run_in_executor(None, os.read, master_fd, 4096)
            if not data:
                break
            sess.last_activity = time.time()
            await ws.send_bytes(data)
    except (OSError, RuntimeError):
        pass


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------

@terminal_router.get("/api/terminal/sessions")
async def list_sessions():
    """List running tmux session names."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "tmux", "list-sessions", "-F", "#{session_name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        names = [s for s in (l.strip() for l in stdout.decode().splitlines())
                 if s and _TMUX_NAME_RE.match(s)]
    except (asyncio.TimeoutError, FileNotFoundError, OSError):
        names = []
    return {"sessions": names}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@terminal_router.websocket("/ws/terminal")
async def ws_terminal(websocket: WebSocket):
    if mtls_required(SSL_CERT, SSL_CA) and not has_verified_peer_cert(websocket.scope):
        await websocket.close(code=1008)
        return

    params = websocket.query_params
    chat_id = params.get("chat_id", "").strip()
    tmux_session = params.get("tmux_session", "").strip() or None

    if not chat_id:
        await websocket.close(code=4000, reason="chat_id required")
        return
    if tmux_session and not _TMUX_NAME_RE.match(tmux_session):
        await websocket.close(code=4000, reason="invalid tmux session name")
        return
    if chat_id not in _sessions and len(_sessions) >= _MAX_TERMINALS:
        await websocket.close(code=4029, reason="terminal limit reached")
        return

    await websocket.accept()

    sess = _sessions.get(chat_id)
    if sess is None:
        try:
            master_fd, proc = await _spawn(tmux_session)
        except Exception as exc:
            with contextlib.suppress(Exception):
                await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
            await websocket.close()
            return
        sess = _Session(master_fd=master_fd, proc=proc, chat_id=chat_id)
        _sessions[chat_id] = sess
        log(f"terminal: spawned chat={chat_id[:8]} tmux={tmux_session or 'shell'} pid={proc.pid}")

    read_task = asyncio.create_task(_pty_read(sess.master_fd, websocket, sess))

    async def _idle_watch():
        while True:
            await asyncio.sleep(60)
            if time.time() - sess.last_activity > _IDLE_TIMEOUT:
                with contextlib.suppress(Exception):
                    await websocket.send_text('{"type":"timeout"}')
                break

    idle_task = asyncio.create_task(_idle_watch())

    try:
        while True:
            msg = await websocket.receive()
            raw_bytes = msg.get("bytes")
            raw_text = msg.get("text")
            if raw_bytes:
                sess.last_activity = time.time()
                with contextlib.suppress(OSError):
                    os.write(sess.master_fd, raw_bytes)
            elif raw_text:
                with contextlib.suppress(Exception):
                    ctrl = json.loads(raw_text)
                    t = ctrl.get("type", "")
                    if t == "resize" and _allow_resize(chat_id):
                        cols = max(1, min(1000, int(ctrl.get("cols", 80))))
                        rows = max(1, min(500, int(ctrl.get("rows", 24))))
                        _set_pty_size(sess.master_fd, cols, rows)
                    elif t == "ping":
                        await websocket.send_text('{"type":"pong"}')
    except Exception:
        pass
    finally:
        read_task.cancel()
        idle_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await read_task
        if sess.proc.returncode is not None:
            code = sess.proc.returncode
            await _cleanup(chat_id)
            with contextlib.suppress(Exception):
                await websocket.send_text(json.dumps({"type": "exit", "code": code}))
        # else: PTY still alive — keep for reconnect
