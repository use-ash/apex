"""Interactive Claude OAuth re-auth for the phone/browser.

Wraps `claude auth login --claudeai` on a PTY, scrapes the authorize URL,
accepts the pasted code into the SAME process (PKCE is bound to it), then
reloads Keychain credentials.

One live session at a time. mTLS required — do not mount on setup_router.
"""
from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
import pty
import re
import signal
import struct
import termios
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
# Request is used by submit (JSON body). start/status/cancel take no body.

from log import log

claude_login_router = APIRouter()

_SESSION_TTL_S = 180
_SUBMIT_WAIT_S = 45
_BUF_CAP = 512 * 1024
_URL_MAX = 32_768
_CODE_MAX = 256

_ANSI_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_OSC8_RE = re.compile(r"\x1b\]8;;(https://[^\x07\x1b]+)\x07|\x1b\]8;;(https://[^\x07\x1b]+)\x1b\\")
_URL_RE = re.compile(
    r"https://(?:(?:platform\.)?claude\.(?:com|ai)|claude\.com|claude\.ai)"
    r"/[^\s<>'\"\\]+",
    re.IGNORECASE,
)
_PASTE_RE = re.compile(r"Paste code here if prompted", re.IGNORECASE)
_OK_RE = re.compile(
    r"logged in(?: as)?|successfully (?:logged in|authenticated)|authentication complete",
    re.IGNORECASE,
)
_FAIL_RE = re.compile(
    r"login failed|invalid code|oauth error|authorization failed|not authenticated",
    re.IGNORECASE,
)


def strip_ansi(text: str) -> str:
    text = _OSC_RE.sub("", text)
    return _ANSI_RE.sub("", text)


def _collapse_wrapped_urls(text: str) -> str:
    """Join hard-wrapped authorize URLs (terminals wrap at ~80 cols)."""
    out = text
    for _ in range(40):
        nxt = re.sub(r"(https://[^\s]+)\r?\n([^\s])", r"\1\2", out)
        if nxt == out:
            break
        out = nxt
    return out


def extract_oauth_url(raw: str) -> Optional[str]:
    """Return the Claude authorize URL from PTY output, or None."""
    for m in _OSC8_RE.finditer(raw):
        url = (m.group(1) or m.group(2) or "").strip()
        if "oauth" in url.lower() and len(url) <= _URL_MAX:
            return url
    text = _collapse_wrapped_urls(strip_ansi(raw).replace("\r", "\n"))
    matches = [m.group(0).rstrip(").,]>\"'") for m in _URL_RE.finditer(text)]
    oauth = [u for u in matches if "oauth" in u.lower()]
    pick = (oauth or matches)
    if not pick:
        return None
    url = pick[-1]
    if len(url) > _URL_MAX:
        return None
    if not url.startswith("https://"):
        return None
    return url


def parse_login_output(raw: str) -> dict:
    """Classify a PTY buffer. Pure — used by the reader and by tests."""
    url = extract_oauth_url(raw)
    text = strip_ansi(raw)
    awaiting = bool(_PASTE_RE.search(text)) or bool(url)
    ok = bool(_OK_RE.search(text))
    fail_m = _FAIL_RE.search(text)
    error = fail_m.group(0) if fail_m and not ok else None
    return {
        "url": url,
        "awaiting_code": awaiting and not ok,
        "ok": ok,
        "error": error,
    }


def sanitize_code(code: str) -> str:
    cleaned = (code or "").strip()
    if not cleaned or len(cleaned) > _CODE_MAX:
        raise ValueError("invalid code")
    if any(c in cleaned for c in "\r\n\x00"):
        raise ValueError("invalid code")
    return cleaned


def _find_claude() -> str:
    import shutil
    path = shutil.which("claude")
    if path:
        return path
    for candidate in (
        Path.home() / ".local" / "bin" / "claude",
        Path("/opt/homebrew/bin") / "claude",
        Path("/usr/local/bin") / "claude",
    ):
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError("Claude Code CLI not installed")


def _set_pty_size(fd: int, cols: int, rows: int) -> None:
    with contextlib.suppress(OSError):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def _pty_preexec(slave_path: str):
    def _preexec() -> None:
        os.setsid()
        fd = os.open(slave_path, os.O_RDWR)
        os.dup2(fd, 0)
        os.dup2(fd, 1)
        os.dup2(fd, 2)
        if fd > 2:
            os.close(fd)
    return _preexec


@dataclass
class _LoginSession:
    id: str
    master_fd: int
    proc: asyncio.subprocess.Process
    buf: str = ""
    url: Optional[str] = None
    status: str = "starting"  # starting | awaiting_code | submitting | ok | error
    error: str = ""
    created_at: float = field(default_factory=time.time)
    reader_task: object = None


_lock = asyncio.Lock()
_session: Optional[_LoginSession] = None


def _public(sess: Optional[_LoginSession]) -> dict:
    if sess is None:
        return {"status": "idle"}
    age = time.time() - sess.created_at
    expired = age > _SESSION_TTL_S and sess.status not in ("ok", "error")
    status = "error" if expired else sess.status
    error = "login timed out" if expired else sess.error
    return {
        "status": status,
        "session_id": sess.id,
        "url": sess.url,
        "error": error,
        "age_s": int(age),
    }


async def _pty_read(sess: _LoginSession) -> None:
    loop = asyncio.get_running_loop()
    try:
        while True:
            data = await loop.run_in_executor(None, os.read, sess.master_fd, 4096)
            if not data:
                break
            chunk = data.decode("utf-8", errors="replace")
            sess.buf = (sess.buf + chunk)[-_BUF_CAP:]
            parsed = parse_login_output(sess.buf)
            if parsed["url"] and not sess.url:
                sess.url = parsed["url"]
                log(f"claude-login: scraped authorize URL ({len(sess.url)} chars)")
            if sess.status in ("starting", "submitting"):
                if parsed["ok"]:
                    sess.status = "ok"
                    log("claude-login: CLI reported success")
                    break
                if parsed["error"] and sess.status == "submitting":
                    sess.status = "error"
                    sess.error = parsed["error"]
                    break
                if parsed["awaiting_code"] and sess.status == "starting":
                    sess.status = "awaiting_code"
        if sess.status not in ("ok", "error", "awaiting_code"):
            code = sess.proc.returncode
            if code == 0:
                sess.status = "ok"
            elif sess.status == "starting" and not sess.url:
                sess.status = "error"
                sess.error = "login process exited before publishing a URL"
    except OSError:
        if sess.status not in ("ok", "error"):
            sess.status = "error"
            sess.error = "login PTY closed"
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log(f"claude-login: reader failed: {exc}")
        if sess.status not in ("ok", "error"):
            sess.status = "error"
            sess.error = "login reader failed"


async def _kill_session(sess: Optional[_LoginSession]) -> None:
    if sess is None:
        return
    if sess.reader_task is not None:
        sess.reader_task.cancel()
    with contextlib.suppress(OSError):
        os.close(sess.master_fd)
    if sess.reader_task is not None:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await sess.reader_task
    with contextlib.suppress(OSError, ProcessLookupError):
        os.killpg(os.getpgid(sess.proc.pid), signal.SIGTERM)
    with contextlib.suppress(asyncio.TimeoutError, Exception):
        await asyncio.wait_for(sess.proc.wait(), timeout=5)


def _login_env() -> dict:
    env = {
        "HOME": os.environ.get("HOME", "/"),
        "USER": os.environ.get("USER", ""),
        "LOGNAME": os.environ.get("LOGNAME", ""),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "SHELL": os.environ.get("SHELL", "/bin/bash"),
        "TERM": "xterm-256color",
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        # Don't open a Mac browser — the operator is on the phone.
        "BROWSER": "/usr/bin/true",
        "NO_COLOR": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    # OAuth tokens in ANTHROPIC_API_KEY break the CLI login flow.
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key and not api_key.startswith("sk-ant-oat"):
        env["ANTHROPIC_API_KEY"] = api_key
    return env


async def _spawn_login() -> _LoginSession:
    cli = _find_claude()
    master_fd, slave_fd = pty.openpty()
    _set_pty_size(master_fd, 120, 32)
    proc = await asyncio.create_subprocess_exec(
        cli, "auth", "login", "--claudeai",
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        preexec_fn=_pty_preexec(os.ttyname(slave_fd)),
        close_fds=True,
        env=_login_env(),
    )
    os.close(slave_fd)
    sess = _LoginSession(
        id=uuid.uuid4().hex[:16],
        master_fd=master_fd,
        proc=proc,
    )
    sess.reader_task = asyncio.create_task(_pty_read(sess))
    log(f"claude-login: spawned pid={proc.pid} session={sess.id}")
    return sess


async def _reload_oauth() -> dict:
    try:
        from agent_sdk import reload_oauth_after_login
        return await asyncio.to_thread(reload_oauth_after_login)
    except Exception as exc:
        log(f"claude-login: keychain reload failed: {exc}")
        return {"token_found": False, "error": str(exc)}


@claude_login_router.get("/api/claude-login/status")
async def api_claude_login_status():
    global _session
    async with _lock:
        sess = _session
        if sess and (time.time() - sess.created_at) > _SESSION_TTL_S and sess.status not in ("ok", "error"):
            await _kill_session(sess)
            _session = None
            return JSONResponse({"status": "idle", "error": "login timed out"})
        return JSONResponse(_public(sess))


@claude_login_router.post("/api/claude-login/start")
async def api_claude_login_start():
    global _session
    async with _lock:
        sess = _session
        now = time.time()
        if sess and sess.status in ("starting", "awaiting_code") and (now - sess.created_at) < _SESSION_TTL_S:
            return JSONResponse(_public(sess))
        if sess and sess.status == "submitting":
            return JSONResponse({"status": "submitting", "error": "login already submitting"}, status_code=409)
        if sess:
            await _kill_session(sess)
            _session = None
        try:
            sess = await _spawn_login()
        except FileNotFoundError:
            return JSONResponse(
                {"status": "error", "error": "Claude Code CLI not installed"},
                status_code=500,
            )
        except Exception as exc:
            log(f"claude-login: spawn failed: {exc}")
            return JSONResponse({"status": "error", "error": "failed to start login"}, status_code=500)
        _session = sess
    # Give the TUI a moment to print the URL before the first response.
    for _ in range(20):
        await asyncio.sleep(0.15)
        if sess.url or sess.status in ("awaiting_code", "ok", "error"):
            break
    return JSONResponse(_public(sess))


@claude_login_router.post("/api/claude-login/submit")
async def api_claude_login_submit(request: Request):
    global _session
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "error": "invalid json"}, status_code=400)
    try:
        code = sanitize_code(str(body.get("code") or ""))
    except ValueError:
        return JSONResponse({"status": "error", "error": "invalid code"}, status_code=400)
    session_id = str(body.get("session_id") or "").strip()

    async with _lock:
        sess = _session
        if sess is None or (session_id and sess.id != session_id):
            return JSONResponse({"status": "idle", "error": "no active login"}, status_code=404)
        if sess.status not in ("awaiting_code", "starting"):
            return JSONResponse(_public(sess), status_code=409)
        if not sess.url and sess.status == "starting":
            return JSONResponse(_public(sess), status_code=409)
        sess.status = "submitting"
        try:
            os.write(sess.master_fd, (code + "\r").encode("utf-8"))
        except OSError:
            sess.status = "error"
            sess.error = "login PTY write failed"
            return JSONResponse(_public(sess), status_code=500)
        log(f"claude-login: submitted code len={len(code)} session={sess.id}")

    deadline = time.time() + _SUBMIT_WAIT_S
    while time.time() < deadline:
        if sess.status in ("ok", "error"):
            break
        await asyncio.sleep(0.2)

    if sess.status == "ok":
        reload = await _reload_oauth()
        payload = _public(sess)
        payload["token_found"] = bool(reload.get("token_found"))
        return JSONResponse(payload)

    if sess.status == "submitting":
        sess.status = "error"
        sess.error = "timed out waiting for login to complete"
    return JSONResponse(_public(sess), status_code=400)


@claude_login_router.post("/api/claude-login/cancel")
async def api_claude_login_cancel():
    global _session
    async with _lock:
        sess = _session
        _session = None
        await _kill_session(sess)
    log("claude-login: cancelled")
    return JSONResponse({"status": "idle"})
