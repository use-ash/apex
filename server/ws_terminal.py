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
    # Set/cleared on each WS attach. Old read task self-exits when this changes.
    active_ws: object = None


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
            # Self-exit if a newer WS replaced us (only one reader per PTY at a time)
            if sess.active_ws is not ws:
                break
            await ws.send_bytes(data)
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
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>
*{{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}}
html,body{{background:#0d0d0d;overflow:hidden;height:100%}}
/* Terminal canvas — fills space above the input bar */
#t{{
  position:fixed;
  top:env(safe-area-inset-top,0px);
  left:0;right:0;
  bottom:var(--bar-h,88px);
  overflow:hidden;
}}
.xterm{{height:100%!important}}
.xterm-viewport{{overflow-y:auto!important}}
/* Input bar — fixed above keyboard, slides with visualViewport */
#bar{{
  position:fixed;
  left:0;right:0;
  bottom:0;
  background:#111827;
  border-top:1px solid rgba(255,255,255,0.08);
  padding-bottom:env(safe-area-inset-bottom,0px);
  z-index:10;
}}
/* Shortcut key row */
#keys{{
  display:flex;
  overflow-x:auto;
  -webkit-overflow-scrolling:touch;
  gap:6px;
  padding:6px 8px 4px;
  scrollbar-width:none;
}}
#keys::-webkit-scrollbar{{display:none}}
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
}}
#inp{{
  flex:1;
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
  <div id="keys">
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
    <button data-k="13">Enter</button>
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

  // Set bar height CSS var BEFORE opening terminal so #t has correct dimensions
  function setBarH(andFit){{
    var h = document.getElementById('bar').offsetHeight || 88;
    document.documentElement.style.setProperty('--bar-h', h+'px');
    document.getElementById('t').style.bottom = h+'px';
    if(andFit){{ try{{fit.fit();}}catch(e){{}} }}
  }}
  setBarH(false);

  term.open(document.getElementById('t'));

  // After DOM paints, fit and send initial resize
  requestAnimationFrame(function(){{
    requestAnimationFrame(function(){{
      setBarH(true);
      if(ws&&ws.readyState===1)
        ws.send(JSON.stringify({{type:'resize',cols:term.cols,rows:term.rows}}));
    }});
  }});

  new ResizeObserver(function(){{ setBarH(true); }}).observe(document.getElementById('bar'));

  // Track keyboard: slide bar up with visualViewport
  if(window.visualViewport){{
    window.visualViewport.addEventListener('resize', function(){{
      var kbH = Math.max(0, window.innerHeight - window.visualViewport.height);
      document.getElementById('bar').style.bottom = kbH+'px';
      document.getElementById('t').style.bottom = (kbH + document.getElementById('bar').offsetHeight)+'px';
      try{{fit.fit();}}catch(e){{}}
      term.scrollToBottom();
      if(ws&&ws.readyState===1)
        ws.send(JSON.stringify({{type:'resize',cols:term.cols,rows:term.rows}}));
    }});
  }}

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
      ws.send(JSON.stringify({{type:'resize',cols:term.cols,rows:term.rows}}));
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
  document.querySelectorAll('#keys button').forEach(function(btn){{
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
    else:
        # Existing session — kick the prior WS reader off this PTY and
        # request a tmux redraw so the new client sees current pane state.
        prior_ws = sess.active_ws
        if prior_ws is not None and prior_ws is not websocket:
            with contextlib.suppress(Exception):
                await prior_ws.close(code=4001, reason="superseded")
            log(f"terminal: superseded prior WS for chat={chat_id[:8]}")
        if tmux_session:
            with contextlib.suppress(Exception):
                refresh = await asyncio.create_subprocess_exec(
                    "tmux", "refresh-client", "-t", tmux_session,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(refresh.wait(), timeout=2)

    sess.active_ws = websocket
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
