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
    # Set/cleared on each WS attach. The reader forwards to whatever is current.
    active_ws: object = None
    # One reader owns the PTY for the session's whole life. Per-WS readers raced:
    # a superseded reader stayed parked in os.read, woke on the next chunk, and
    # dropped it on the floor — so a reconnecting client saw a blank screen.
    reader_task: object = None


_sessions: dict[str, _Session] = {}
_resize_tokens: dict[str, tuple[float, float]] = {}  # chat_id -> (tokens, last_refill)


def _set_pty_size(fd: int, cols: int, rows: int) -> None:
    with contextlib.suppress(OSError):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def _make_pty_preexec(slave_path: str):
    """Build a preexec_fn that gives the child the PTY as its *controlling*
    terminal.

    The kernel only delivers SIGWINCH to the foreground process group of a
    controlling terminal. setsid() alone leaves the child with none, so every
    TIOCSWINSZ from _set_pty_size was silently ignored and the session stayed
    at its 80x24 spawn size no matter what the client reported — the terminal
    rendered into the top-left corner of the viewport.

    The slave is opened by name rather than reusing fd 0: under the event
    loop, fd 0 is not the PTY when preexec_fn runs (isatty() is False there),
    so a TIOCSCTTY on it fails with ENODEV. Opening the slave while we are a
    session leader with no controlling terminal claims it as the controlling
    terminal, and re-duping it onto 0/1/2 guarantees the child's standard
    streams are the terminal regardless of what it was handed.
    """
    def _preexec() -> None:
        os.setsid()
        fd = os.open(slave_path, os.O_RDWR)
        os.dup2(fd, 0)
        os.dup2(fd, 1)
        os.dup2(fd, 2)
        if fd > 2:
            os.close(fd)
    return _preexec


_TMUX_CONF = os.path.join(os.path.dirname(__file__), "tmux.conf")


def _tmux_base() -> list[str]:
    """tmux command prefix with our config if present."""
    if os.path.exists(_TMUX_CONF):
        return ["tmux", "-f", _TMUX_CONF]
    return ["tmux"]


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
    _set_pty_size(master_fd, 80, 24)
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
            *_tmux_base(), "has-session", "-t", tmux_session,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await chk.wait()
        if chk.returncode != 0:
            mk = await asyncio.create_subprocess_exec(
                *_tmux_base(), "new-session", "-d", "-s", tmux_session,
                env=safe_env,
            )
            await mk.wait()
        # -d detaches any other client on this session. A tmux window has a
        # single size shared by every attached client, so a second client always
        # forces one of them to render wrong: the window follows the smallest
        # client (or the most recent, per window-size), and a stale client that
        # never detached pins everyone to its size indefinitely — an 80x24
        # leftover clamps a 160-column browser to 80 columns forever.
        # Detaching on attach makes the connecting client the only client, so it
        # always gets its true dimensions, and evicts leaked clients for free.
        cmd = [*_tmux_base(), "attach-session", "-d", "-t", tmux_session]
    else:
        cmd = [os.environ.get("SHELL", "/bin/bash"), "-l"]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        preexec_fn=_make_pty_preexec(os.ttyname(slave_fd)),
        close_fds=True,
        env=safe_env,
    )
    os.close(slave_fd)
    return master_fd, proc


async def _cleanup(chat_id: str) -> None:
    sess = _sessions.pop(chat_id, None)
    if not sess:
        return
    sess.active_ws = None
    if sess.reader_task is not None:
        sess.reader_task.cancel()
    # Closing the master also breaks the executor thread out of its blocking
    # os.read, which cancel() alone cannot do.
    with contextlib.suppress(OSError):
        os.close(sess.master_fd)
    if sess.reader_task is not None:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await sess.reader_task
    with contextlib.suppress(OSError, ProcessLookupError):
        os.killpg(os.getpgid(sess.proc.pid), signal.SIGHUP)
    with contextlib.suppress(asyncio.TimeoutError, Exception):
        await asyncio.wait_for(sess.proc.wait(), timeout=5)
    _resize_tokens.pop(chat_id, None)
    log(f"terminal: cleaned up chat={chat_id[:8]}")


async def _pty_read(sess: _Session) -> None:
    """Forward PTY output for the life of the session.

    Exactly one of these runs per session. It must not be tied to a single
    WebSocket: os.read runs in an executor thread that cannot be cancelled, so
    a per-WS reader outlives its socket, wakes on the next chunk, and discards
    it. With two readers parked on the same fd after a reconnect, whichever won
    the wake-up decided whether the new client saw the screen — which is why a
    refreshed page was blank until the next keystroke produced more output.

    Sending to a stale socket is harmless; the send fails and we keep going, so
    the next client still gets everything after it.
    """
    loop = asyncio.get_running_loop()
    try:
        while True:
            data = await loop.run_in_executor(None, os.read, sess.master_fd, 4096)
            if not data:
                break
            sess.last_activity = time.time()
            ws = sess.active_ws
            if ws is None:
                # Nothing attached (e.g. mid page-refresh). Discard rather than
                # buffer: what arrives here is tmux teardown — clear-screen and
                # mode resets — and replaying it to the next client would blank
                # the screen it just painted. The attach-time repaint below is
                # what makes the new client whole.
                continue
            try:
                await ws.send_bytes(data)
            except Exception:
                # Client went away mid-write; keep draining for the next one.
                continue
    except (OSError, RuntimeError):
        pass


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------

_TERMINAL_VIEW_HTML = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,interactive-widget=resizes-content">
<style>
*{{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}}
html,body{{background:#0d0d0d;overflow:hidden}}
/* Flex column: terminal grows, bar stays its natural size at bottom.
   Using 100dvh + interactive-widget=resizes-content so the layout
   viewport shrinks when the iOS keyboard appears — no JS choreography needed. */
body{{
  height:100dvh;
  display:flex;
  flex-direction:column;
  padding-top:env(safe-area-inset-top,0px);
}}
#t{{
  flex:1 1 0;
  min-height:0;
  overflow:hidden;
}}
.xterm{{height:100%!important;width:100%!important}}
.xterm-viewport{{overflow-y:auto!important}}
#bar{{
  flex-shrink:0;
  background:#111827;
  border-top:1px solid rgba(255,255,255,0.08);
  padding-bottom:env(safe-area-inset-bottom,0px);
}}
/* Shortcut key row. The dismiss button sits OUTSIDE the scrolling strip: it
   used to be the last of sixteen buttons inside #keys, so on a phone it was
   scrolled out of sight and an accidentally-raised keyboard had no visible
   way out. It must stay pinned and reachable at all times. */
#keys-row{{
  display:flex;
  align-items:center;
  gap:6px;
  padding:6px 8px 4px;
  min-width:0;
}}
#keys{{
  display:flex;
  flex:1 1 auto;
  min-width:0;
  overflow-x:auto;
  -webkit-overflow-scrolling:touch;
  gap:6px;
  scrollbar-width:none;
}}
#keys::-webkit-scrollbar{{display:none}}
#kb-dismiss{{
  flex-shrink:0;
  padding:5px 10px;
  background:#1f2937;
  color:#d1d5db;
  border:1px solid rgba(255,255,255,0.1);
  border-radius:6px;
  font-size:12px;
  font-family:'SF Mono',monospace;
  cursor:pointer;
  white-space:nowrap;
}}
#kb-dismiss:active{{background:#374151}}
#keys button{{
  flex-shrink:0;
  padding:5px 10px;
  background:#1f2937;
  color:#d1d5db;
  border:1px solid rgba(255,255,255,0.1);
  border-radius:6px;
  font-size:12px;
  font-family:'SF Mono',monospace;
  cursor:pointer;
  white-space:nowrap;
}}
#keys button:active{{background:#374151}}
/* Text input row */
#inp-row{{
  display:flex;
  align-items:center;
  gap:6px;
  padding:4px 8px 6px;
  width:100%;
  box-sizing:border-box;
}}
#inp{{
  flex:1 1 0;
  min-width:0;
  padding:8px 12px;
  background:#0f0f1a;
  color:#e5e7eb;
  border:1px solid rgba(255,255,255,0.12);
  border-radius:8px;
  font-family:'SF Mono','Fira Code',monospace;
  font-size:14px;
  outline:none;
  -webkit-appearance:none;
}}
#inp::placeholder{{color:#4b5563}}
#send{{
  padding:8px 14px;
  background:#7c3aed;
  color:#fff;
  border:none;
  border-radius:8px;
  font-size:13px;
  font-weight:600;
  cursor:pointer;
  white-space:nowrap;
}}
#send:active{{opacity:.8}}
/* Status row */
#status{{
  display:flex;
  align-items:center;
  gap:6px;
  padding:4px 12px 2px;
  font-size:11px;
  color:#9ca3af;
  font-family:'SF Mono',monospace;
}}
#dot{{
  width:8px;height:8px;border-radius:50%;
  background:#f59e0b;
  flex-shrink:0;
}}
#dot.ok{{background:#22c55e}}
#dot.err{{background:#ef4444}}
</style>
<link rel="stylesheet" href="/static/xterm.css">
</head>
<body>
<div id="t"></div>

<!-- Input bar: shortcut row + text input -->
<div id="bar">
  <div id="status"><span id="dot"></span><span id="status-txt">connecting…</span></div>
  <div id="keys-row">
  <div id="keys">
    <button data-k="13">Enter</button>
    <button data-k="3">Ctrl-C</button>
    <button data-k="4">Ctrl-D</button>
    <button data-k="26">Ctrl-Z</button>
    <button data-k="27">Esc</button>
    <button data-k="9">Tab</button>
    <button data-k="arrow-up">↑</button>
    <button data-k="arrow-down">↓</button>
    <button data-k="arrow-left">←</button>
    <button data-k="arrow-right">→</button>
    <button data-k="1">Ctrl-A</button>
    <button data-k="5">Ctrl-E</button>
    <button data-k="11">Ctrl-K</button>
    <button data-k="21">Ctrl-U</button>
    <button data-k="12">Ctrl-L</button>
  </div>
  <button id="kb-dismiss" type="button" title="Hide keyboard">⌨ ▼</button>
  </div>
  <form id="inp-row" onsubmit="event.preventDefault();sendInp();return false;">
    <input id="inp" type="text" placeholder="command…"
      autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"
      inputmode="text"
      enterkeyhint="send"
    >
    <button id="send" type="submit">Send</button>
  </form>
</div>

<script src="/static/xterm.js"></script>
<script src="/static/xterm-addon-fit.js"></script>
<script src="/static/apex-term-links.js"></script>
<script>
(function(){{
  var chatId = {chat_id_json};
  var tmuxSession = {tmux_json};

  var term = new Terminal({{
    cursorBlink:true, fontSize:13,
    fontFamily:"'SF Mono','Fira Code',monospace",
    theme:{{background:'#0d0d0d',foreground:'#e5e7eb',cursor:'#22c55e',
            selectionBackground:'rgba(124,58,237,0.35)'}},
    scrollback:5000, allowTransparency:false,
    disableStdin:true,
  }});
  var fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  function linkToast(msg){{
    var d = document.createElement('div');
    d.textContent = msg;
    d.style.cssText = 'position:fixed;left:50%;bottom:24px;transform:translateX(-50%);'
      + 'background:#7c3aed;color:#fff;padding:8px 14px;border-radius:8px;'
      + 'font:13px -apple-system,sans-serif;z-index:9999;max-width:80vw;text-align:center';
    document.body.appendChild(d);
    setTimeout(function(){{ d.remove(); }}, 2600);
  }}
  // The iOS app installs an `apexOpenURL` message handler that hands the URL
  // to Safari. Plain browsers have no bridge, so fall back to window.open and
  // then the clipboard.
  function openLink(uri){{
    try {{
      var bridge = window.webkit && window.webkit.messageHandlers
        && window.webkit.messageHandlers.apexOpenURL;
      if (bridge) {{ bridge.postMessage(uri); return; }}
    }} catch (e) {{}}
    var w = null;
    try {{ w = window.open(uri, '_blank', 'noopener,noreferrer'); }} catch (e) {{}}
    if (w) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(uri)
        .then(function(){{ linkToast('Link copied — paste into Safari'); }})
        .catch(function(){{ linkToast('Copy failed'); }});
    }} else {{
      linkToast('Copy unavailable');
    }}
  }}
  if (typeof installApexTermLinks !== 'undefined')
    installApexTermLinks(term, openLink);
  term.open(document.getElementById('t'));

  // Debounced fit + WS resize on viewport changes.
  // Body is a flex column — keyboard appearance shrinks layout viewport
  // (interactive-widget=resizes-content), body shrinks, ResizeObserver fires,
  // we fit() once after 150ms of quiescence.
  var _rt = null, _lc = 0, _lr = 0;
  function refit(){{
    if(_rt) clearTimeout(_rt);
    _rt = setTimeout(function(){{
      try {{ fit.fit(); }} catch(e) {{}}
      if(ws && ws.readyState === 1 && (term.cols !== _lc || term.rows !== _lr)){{
        _lc = term.cols; _lr = term.rows;
        ws.send(JSON.stringify({{type:'resize', cols:_lc, rows:_lr}}));
      }}
    }}, 150);
  }}

  // Initial fit after paint settles
  requestAnimationFrame(function(){{
    requestAnimationFrame(function(){{
      try {{ fit.fit(); }} catch(e) {{}}
      _lc = term.cols; _lr = term.rows;
      if(ws && ws.readyState === 1)
        ws.send(JSON.stringify({{type:'resize', cols:_lc, rows:_lr}}));
    }});
  }});

  new ResizeObserver(refit).observe(document.body);

  // WebSocket
  var proto = location.protocol==='https:'?'wss:':'ws:';
  var sessParam = tmuxSession?'&tmux_session='+encodeURIComponent(tmuxSession):'';
  var url = proto+'//'+location.host+'/ws/terminal?chat_id='+encodeURIComponent(chatId)+sessParam;
  var ws, attempt=0;

  function setStatus(state, txt){{
    var dot = document.getElementById('dot');
    var t = document.getElementById('status-txt');
    dot.className = state;  // '' (amber) | 'ok' | 'err'
    t.textContent = txt;
  }}

  function connect(){{
    setStatus('', attempt ? 'reconnecting ('+attempt+'/5)…' : 'connecting…');
    ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';
    ws.onopen = function(){{
      attempt=0;
      setStatus('ok', tmuxSession ? 'connected · tmux:'+tmuxSession : 'connected · shell');
      // Send a resize using whatever dimensions are CURRENT (post-fit).
      // refit() also runs on mount, but ws.onopen may race ahead of it;
      // sending here ensures the PTY learns our size before tmux refresh.
      try {{ fit.fit(); }} catch(e) {{}}
      _lc = term.cols; _lr = term.rows;
      ws.send(JSON.stringify({{type:'resize',cols:_lc,rows:_lr}}));
    }};
    ws.onmessage = function(e){{
      if(e.data instanceof ArrayBuffer){{ term.write(new Uint8Array(e.data)); term.scrollToBottom(); }}
      else{{
        try{{
          var c=JSON.parse(e.data);
          if(c.type==='exit'||c.type==='timeout'){{
            term.writeln('\\r\\n\\x1b[33m[session ended]\\x1b[0m');
            setStatus('err', c.type==='timeout' ? 'idle timeout' : 'exit '+(c.code||0));
          }}
        }}catch(ex){{}}
      }}
    }};
    ws.onclose=function(){{
      if(attempt<5){{
        attempt++;
        setStatus('', 'disconnected · retry '+attempt);
        setTimeout(connect,Math.min(8000,500*Math.pow(2,attempt)));
      }} else {{
        setStatus('err', 'connection lost');
      }}
    }};
    ws.onerror=function(){{}};
  }}
  connect();

  // Send raw bytes to PTY
  function send(str){{
    if(ws&&ws.readyState===WebSocket.OPEN){{
      ws.send(new TextEncoder().encode(str).buffer);
      return true;
    }}
    return false;
  }}

  // Map data-k values to actual byte sequences (built at runtime so escapes are clean)
  var KEY_MAP = {{
    'arrow-up':    '\\x1b[A',
    'arrow-down':  '\\x1b[B',
    'arrow-left':  '\\x1b[D',
    'arrow-right': '\\x1b[C',
  }};

  // Wire up shortcut buttons
  document.querySelectorAll('#keys button[data-k]').forEach(function(btn){{
    btn.addEventListener('click', function(ev){{
      ev.preventDefault();
      var k = btn.getAttribute('data-k');
      var seq;
      if(KEY_MAP[k]){{ seq = KEY_MAP[k]; }}
      else {{ seq = String.fromCharCode(parseInt(k,10)); }}
      send(seq);
      // Bring input back into focus so user can keep typing
      document.getElementById('inp').focus();
    }});
  }});

  // Keyboard-dismiss button — blurs the input, which retracts the iOS keyboard
  document.getElementById('kb-dismiss').addEventListener('click', function(ev){{
    ev.preventDefault();
    document.getElementById('inp').blur();
    document.activeElement && document.activeElement.blur && document.activeElement.blur();
  }});

  // Send text field contents + newline
  window.sendInp=function(){{
    var inp=document.getElementById('inp');
    var val=inp.value;
    if(!val) return;
    if(send(val+'\\r')){{
      inp.value='';
    }}
  }};

  // Heartbeat
  setInterval(function(){{
    if(ws&&ws.readyState===WebSocket.OPEN)
      ws.send(JSON.stringify({{type:'ping'}}));
  }},30000);
}})();
</script>
</body>
</html>"""


@terminal_router.get("/terminal-view/{chat_id}")
async def terminal_view(chat_id: str):
    """Standalone xterm.js page for embedding in iOS WKWebView."""
    import json as _json
    from db import _get_chat_settings
    settings = _get_chat_settings(chat_id)
    tmux = settings.get("tmux_session") or ""
    html = _TERMINAL_VIEW_HTML.format(
        chat_id_json=_json.dumps(chat_id),
        tmux_json=_json.dumps(tmux) if tmux else "null",
    )
    from fastapi.responses import HTMLResponse as _HR
    return _HR(html, headers={"Cache-Control": "no-store"})


@terminal_router.get("/api/terminal/sessions")
async def list_sessions():
    """List running tmux session names."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *_tmux_base(), "list-sessions", "-F", "#{session_name}",
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
        # One reader for the session's whole life, started before any client is
        # attached so no output is missed between spawn and the first attach.
        sess.reader_task = asyncio.create_task(_pty_read(sess))
        log(f"terminal: spawned chat={chat_id[:8]} tmux={tmux_session or 'shell'} pid={proc.pid}")
    else:
        # Existing session — the reader keeps running and simply retargets to
        # the new socket once active_ws is reassigned below.
        # The tmux refresh is deferred until the first resize message lands
        # so tmux redraws at the new client's actual cols/rows, not the old.
        prior_ws = sess.active_ws
        # Retarget the reader BEFORE closing the old socket. Closing awaits, and
        # any output arriving in that window would otherwise be handed to a
        # socket that is going away and lost — the tail of the race that made a
        # refreshed page come up blank.
        sess.active_ws = websocket
        if prior_ws is not None and prior_ws is not websocket:
            with contextlib.suppress(Exception):
                await prior_ws.close(code=4001, reason="superseded")
            log(f"terminal: superseded prior WS for chat={chat_id[:8]}")

    sess.active_ws = websocket
    needs_tmux_refresh = tmux_session is not None and sess.proc.returncode is None
    first_resize = True  # bypass rate limiter for critical initial sizing

    async def _tmux_repaint(force: bool = False):
        """Force tmux to redraw for the client that just attached.

        Output produced while nothing was attached is dropped (see _pty_read),
        so a fresh client can only be made whole by a repaint. The resize path
        calls this as soon as dimensions are known; the settle pass below calls
        it with force so a repaint also lands *after* the reconnect has fully
        quiesced, covering anything missed in between.
        """
        nonlocal needs_tmux_refresh
        if not (needs_tmux_refresh or force):
            return
        needs_tmux_refresh = False
        with contextlib.suppress(Exception):
            refresh = await asyncio.create_subprocess_exec(
                *_tmux_base(), "refresh-client", "-t", tmux_session,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(refresh.wait(), timeout=2)

    async def _repaint_fallback():
        # Unconditional settle pass. Two reasons it must not be skipped when the
        # resize path already repainted: a client that never sends a resize
        # would otherwise never be repainted at all, and a repaint triggered at
        # resize time lands before the reconnect has settled, so output produced
        # just after it can still be missed. Repainting once more here makes the
        # visible screen correct regardless of what was dropped in between.
        await asyncio.sleep(0.75)
        await _tmux_repaint(force=True)

    repaint_task = asyncio.create_task(_repaint_fallback())

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
                    if t == "resize" and (_allow_resize(chat_id) or first_resize):
                        first_resize = False
                        cols = max(1, min(1000, int(ctrl.get("cols", 80))))
                        rows = max(1, min(500, int(ctrl.get("rows", 24))))
                        _set_pty_size(sess.master_fd, cols, rows)
                        if needs_tmux_refresh:
                            await asyncio.sleep(0.08)  # let ioctl propagate before refresh
                            await _tmux_repaint()
                    elif t == "ping":
                        await websocket.send_text('{"type":"pong"}')
    except Exception:
        pass
    finally:
        idle_task.cancel()
        repaint_task.cancel()
        # The reader is owned by the session, not this socket — leave it running
        # so output produced between disconnect and reconnect is still drained
        # and cannot be delivered to a dead socket by a second reader.
        if sess.active_ws is websocket:
            sess.active_ws = None
        if sess.proc.returncode is not None:
            code = sess.proc.returncode
            await _cleanup(chat_id)
            with contextlib.suppress(Exception):
                await websocket.send_text(json.dumps({"type": "exit", "code": code}))
        # else: PTY still alive — keep for reconnect
