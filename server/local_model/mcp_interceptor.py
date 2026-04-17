#!/usr/bin/env python3
"""MCP server that exposes Interceptor (github.com/Hacker-Valley-Media/Interceptor)
to Claude SDK sessions via the Apex MCP plumbing.

Interceptor is a Chrome extension + Bun daemon + macOS Swift bridge that lets
agents drive the user's authenticated browser without CDP. We wrap the
`interceptor` CLI (stdio, `--json` flag, returns structured results) behind
MCP tool calls so Apex chats can use it like any other tool.

Patterned on mcp_execute_code.py + mcp_computer_use.py.

Safety model (per-chat):
  - Read-only tools (status/read/find/tree/net_log) require no special flag.
  - Write tools (open/act/click/type/keys/scroll/navigate/eval/monitor_*)
    require ``interceptor_enabled = 1`` on the chat row (enforced upstream
    by the streaming injection — we only get spawned if the chat opted in).
  - Pause flag file at ``state/interceptor/pause/{chat_id}`` halts all write
    tools (returns {ok: false, reason: "paused"}). Polled per call.
  - Output cap: every CLI stdout is truncated to ``_MAX_OUTPUT_BYTES`` before
    going back to the model — keeps a misbehaving page from flooding context.

Run standalone: ``python3 mcp_interceptor.py``
Registered via: ``streaming.py:_inject_interceptor_mcp()`` (auto-configured).
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants / env
# ---------------------------------------------------------------------------

_INTERCEPTOR_BIN = os.environ.get("APEX_INTERCEPTOR_BIN") or str(
    Path.home() / ".interceptor" / "bin" / "interceptor"
)
_CHAT_ID = os.environ.get("APEX_INT_CHAT_ID") or ""
_STATE_DIR = Path(
    os.environ.get("APEX_INT_STATE_DIR")
    or str(Path.home() / ".openclaw" / "apex" / "state" / "interceptor")
)
_PAUSE_DIR = _STATE_DIR / "pause"

_MAX_OUTPUT_BYTES = 96 * 1024  # ~100KB cap on raw CLI stdout per call
_DEFAULT_TIMEOUT = 30  # seconds; interceptor itself has 15s call timeout


def _log(msg: str) -> None:
    print(f"[mcp-interceptor] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Pause flag (same pattern as computer_use)
# ---------------------------------------------------------------------------

def _is_paused() -> bool:
    if not _CHAT_ID:
        return False
    return (_PAUSE_DIR / _CHAT_ID).exists()


# ---------------------------------------------------------------------------
# CLI invocation
# ---------------------------------------------------------------------------

def _run_cli(argv: list[str], *, timeout: float = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Run ``interceptor <argv...> --json`` and return a normalized dict.

    Returns keys: ok (bool), stdout (str), stderr (str), exit_code (int),
    parsed (Any | None — JSON-decoded stdout when possible).
    """
    if not os.path.exists(_INTERCEPTOR_BIN):
        return {
            "ok": False,
            "reason": (
                f"interceptor binary not found at {_INTERCEPTOR_BIN}. "
                "Install from https://github.com/Hacker-Valley-Media/Interceptor "
                "releases (DMG) or set APEX_INTERCEPTOR_BIN."
            ),
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "parsed": None,
        }

    # Always force JSON output when supported. All documented commands accept
    # --json; if the CLI ever rejects it we still capture stderr.
    if "--json" not in argv:
        argv = argv + ["--json"]

    cmd = [_INTERCEPTOR_BIN, *argv]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "reason": f"timeout after {timeout}s: {' '.join(argv[:3])}...",
            "stdout": (e.stdout or "")[:_MAX_OUTPUT_BYTES],
            "stderr": (e.stderr or "")[:_MAX_OUTPUT_BYTES],
            "exit_code": -1,
            "parsed": None,
        }
    except OSError as e:
        return {
            "ok": False,
            "reason": f"exec failed: {e}",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "parsed": None,
        }

    stdout = (proc.stdout or "")[:_MAX_OUTPUT_BYTES]
    stderr = (proc.stderr or "")[:_MAX_OUTPUT_BYTES]

    parsed: Any | None = None
    if stdout.strip():
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = None  # many commands return raw text; that's fine

    ok = proc.returncode == 0
    out: dict[str, Any] = {
        "ok": ok,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": proc.returncode,
        "parsed": parsed,
    }
    if not ok and "reason" not in out:
        # First non-empty line of stderr or stdout gives a usable summary.
        first = next(
            (ln.strip() for ln in (stderr + "\n" + stdout).splitlines() if ln.strip()),
            f"exit={proc.returncode}",
        )
        out["reason"] = first
    return out


# ---------------------------------------------------------------------------
# Tool definitions (declared as JSON Schema; handled by name in _dispatch)
# ---------------------------------------------------------------------------

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "interceptor_status",
        "description": (
            "Check the Interceptor daemon health (is it running, socket path, PID). "
            "Use before the first browser action to confirm the CLI is reachable. "
            "Does NOT require the Chrome extension."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "browser_open",
        "description": (
            "Open a URL in the active browser tab and return its accessibility tree + a "
            "short text summary. Reuses the user's existing authenticated Chrome session "
            "(cookies, logins preserved). Prefer this over navigate+read for first-visit flows."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "full_text": {"type": "boolean", "description": "Return full page text instead of 2000-char summary."},
                "tree_only": {"type": "boolean"},
                "text_only": {"type": "boolean"},
                "timeout_ms": {"type": "integer", "description": "Wait-stable timeout (default 5000)."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_read",
        "description": (
            "Read the current page's accessibility tree + visible text. "
            "Optionally scope to a single element by semantic ref (e.g. 'e5')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Optional element ref like 'e5'."},
                "tree_only": {"type": "boolean"},
                "text_only": {"type": "boolean"},
            },
        },
    },
    {
        "name": "browser_tree",
        "description": "Return the semantic accessibility tree only. Good for cheap state snapshots.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {"type": "string", "enum": ["interactive", "all"]},
                "depth": {"type": "integer"},
                "max_chars": {"type": "integer"},
            },
        },
    },
    {
        "name": "browser_find",
        "description": "Find elements on the current page by name/text, optionally filtered by ARIA role.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "role": {"type": "string", "description": "ARIA role (button, link, textbox, etc.)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "browser_click",
        "description": "Click an element by semantic ref (e.g. 'e5') or index.",
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
    },
    {
        "name": "browser_type",
        "description": "Type text into an element by ref. Clears the field first unless append=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "text": {"type": "string"},
                "append": {"type": "boolean"},
            },
            "required": ["ref", "text"],
        },
    },
    {
        "name": "browser_keys",
        "description": "Send a keyboard shortcut (e.g. 'Control+A', 'Enter', 'Escape').",
        "inputSchema": {
            "type": "object",
            "properties": {"combo": {"type": "string"}},
            "required": ["combo"],
        },
    },
    {
        "name": "browser_navigate",
        "description": "Navigate the active tab to a URL (no extra wait or read).",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "browser_scroll",
        "description": "Scroll the page up/down/top/bottom.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down", "top", "bottom"]},
            },
            "required": ["direction"],
        },
    },
    {
        "name": "browser_screenshot",
        "description": "Capture a viewport screenshot and return a data URL. Use format=png for lossless.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["png", "jpeg"]},
                "quality": {"type": "integer", "description": "JPEG quality 0-100."},
                "full_page": {"type": "boolean"},
            },
        },
    },
    {
        "name": "browser_net_log",
        "description": (
            "Passively captured fetch/XHR traffic on the current tab. Always-on, no CDP. "
            "Filter by URL substring; limit defaults to 100."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "browser_eval",
        "description": (
            "Run JavaScript in the page. Default is isolated-world (no page globals); set main=true "
            "to run in the page's main world (access to page variables)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "main": {"type": "boolean"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "browser_wait",
        "description": "Wait N milliseconds. Use sparingly; prefer wait_stable for DOM settling.",
        "inputSchema": {
            "type": "object",
            "properties": {"ms": {"type": "integer"}},
            "required": ["ms"],
        },
    },
    {
        "name": "browser_wait_stable",
        "description": "Wait for DOM stability (200ms debounce default).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ms": {"type": "integer"},
                "timeout": {"type": "integer"},
            },
        },
    },
    {
        "name": "browser_monitor_start",
        "description": (
            "Start a workflow recording session on the active tab. User demonstrates the "
            "task; `browser_monitor_stop` ends it; `browser_monitor_export` emits a replay script."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"instruction": {"type": "string"}},
        },
    },
    {
        "name": "browser_monitor_stop",
        "description": "End the current recording session and return its summary.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "browser_monitor_export",
        "description": (
            "Export a recorded session. Default returns pretty-printed event log; plan=true "
            "emits a replayable 'interceptor ...' script."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "plan": {"type": "boolean"},
                "json_raw": {"type": "boolean"},
            },
            "required": ["session_id"],
        },
    },
]

# Tools that mutate browser state — gated by pause flag.
_WRITE_TOOLS = frozenset({
    "browser_open", "browser_click", "browser_type", "browser_keys",
    "browser_navigate", "browser_scroll", "browser_eval",
    "browser_monitor_start", "browser_monitor_stop",
})


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def _dispatch(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    if tool in _WRITE_TOOLS and _is_paused():
        return {"ok": False, "reason": "paused by user (flag file present)"}

    if tool == "interceptor_status":
        return _run_cli(["status"])

    if tool == "browser_open":
        url = str(args.get("url") or "").strip()
        if not url:
            return {"ok": False, "reason": "url required"}
        argv = ["open", url]
        if args.get("full_text"):
            argv.append("--full")
        if args.get("tree_only"):
            argv.append("--tree-only")
        if args.get("text_only"):
            argv.append("--text-only")
        if isinstance(args.get("timeout_ms"), int):
            argv += ["--timeout", str(args["timeout_ms"])]
        return _run_cli(argv)

    if tool == "browser_read":
        argv = ["read"]
        if args.get("ref"):
            argv.append(str(args["ref"]))
        if args.get("tree_only"):
            argv.append("--tree-only")
        if args.get("text_only"):
            argv.append("--text-only")
        return _run_cli(argv)

    if tool == "browser_tree":
        argv = ["tree"]
        if args.get("filter") in ("interactive", "all"):
            argv += ["--filter", args["filter"]]
        if isinstance(args.get("depth"), int):
            argv += ["--depth", str(args["depth"])]
        if isinstance(args.get("max_chars"), int):
            argv += ["--max-chars", str(args["max_chars"])]
        return _run_cli(argv)

    if tool == "browser_find":
        query = str(args.get("query") or "").strip()
        if not query:
            return {"ok": False, "reason": "query required"}
        argv = ["find", query]
        if args.get("role"):
            argv += ["--role", str(args["role"])]
        return _run_cli(argv)

    if tool == "browser_click":
        ref = str(args.get("ref") or "").strip()
        if not ref:
            return {"ok": False, "reason": "ref required"}
        return _run_cli(["click", ref])

    if tool == "browser_type":
        ref = str(args.get("ref") or "").strip()
        text = str(args.get("text") or "")
        if not ref:
            return {"ok": False, "reason": "ref required"}
        argv = ["type", ref, text]
        if args.get("append"):
            argv.append("--append")
        return _run_cli(argv)

    if tool == "browser_keys":
        combo = str(args.get("combo") or "").strip()
        if not combo:
            return {"ok": False, "reason": "combo required"}
        return _run_cli(["keys", combo])

    if tool == "browser_navigate":
        url = str(args.get("url") or "").strip()
        if not url:
            return {"ok": False, "reason": "url required"}
        return _run_cli(["navigate", url])

    if tool == "browser_scroll":
        direction = str(args.get("direction") or "down").strip()
        if direction not in ("up", "down", "top", "bottom"):
            return {"ok": False, "reason": "direction must be up|down|top|bottom"}
        return _run_cli(["scroll", direction])

    if tool == "browser_screenshot":
        argv = ["screenshot"]
        fmt = args.get("format")
        if fmt in ("png", "jpeg"):
            argv += ["--format", fmt]
        if isinstance(args.get("quality"), int):
            argv += ["--quality", str(args["quality"])]
        if args.get("full_page"):
            argv.append("--full")
        return _run_cli(argv, timeout=45)

    if tool == "browser_net_log":
        argv = ["net", "log"]
        if args.get("filter"):
            argv += ["--filter", str(args["filter"])]
        if isinstance(args.get("limit"), int):
            argv += ["--limit", str(args["limit"])]
        return _run_cli(argv)

    if tool == "browser_eval":
        code = str(args.get("code") or "")
        if not code:
            return {"ok": False, "reason": "code required"}
        argv = ["eval", code]
        if args.get("main"):
            argv.append("--main")
        return _run_cli(argv)

    if tool == "browser_wait":
        ms = int(args.get("ms") or 0)
        if ms <= 0:
            return {"ok": False, "reason": "ms must be a positive int"}
        return _run_cli(["wait", str(ms)], timeout=max(10, ms / 1000 + 5))

    if tool == "browser_wait_stable":
        argv = ["wait-stable"]
        if isinstance(args.get("ms"), int):
            argv += ["--ms", str(args["ms"])]
        if isinstance(args.get("timeout"), int):
            argv += ["--timeout", str(args["timeout"])]
        return _run_cli(argv, timeout=30)

    if tool == "browser_monitor_start":
        argv = ["monitor", "start"]
        instruction = args.get("instruction")
        if instruction:
            argv += ["--instruction", str(instruction)]
        return _run_cli(argv)

    if tool == "browser_monitor_stop":
        return _run_cli(["monitor", "stop"])

    if tool == "browser_monitor_export":
        session_id = str(args.get("session_id") or "").strip()
        if not session_id:
            return {"ok": False, "reason": "session_id required"}
        argv = ["monitor", "export", session_id]
        if args.get("plan"):
            argv.append("--plan")
        if args.get("json_raw"):
            argv.append("--json")  # raw JSONL mode (already appended by _run_cli; harmless dup)
        return _run_cli(argv)

    return {"ok": False, "reason": f"unknown tool: {tool}"}


# ---------------------------------------------------------------------------
# JSON-RPC plumbing (identical shape to mcp_execute_code.py)
# ---------------------------------------------------------------------------

def _handle_request(request: dict) -> dict | None:
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {}) or {}

    if method == "initialize":
        _log(f"initialize (id={req_id})")
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "apex-interceptor", "version": "0.1.0"},
            },
        }

    if method == "notifications/initialized":
        _log("notifications/initialized received")
        return None

    if method == "tools/list":
        _log(f"tools/list (id={req_id})")
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": _TOOLS}}

    if method == "tools/call":
        tool = params.get("name", "")
        args = params.get("arguments", {}) or {}
        if not isinstance(args, dict):
            args = {}
        t0 = time.time()
        try:
            result = _dispatch(tool, args)
        except Exception as e:  # noqa: BLE001
            _log(f"dispatch error: {type(e).__name__}: {e}")
            result = {"ok": False, "reason": f"{type(e).__name__}: {e}"}
        dt_ms = int((time.time() - t0) * 1000)
        _log(f"tools/call {tool} ok={result.get('ok')} dt={dt_ms}ms")
        text_payload = json.dumps(result, indent=2, default=str)
        if len(text_payload) > _MAX_OUTPUT_BYTES:
            text_payload = text_payload[:_MAX_OUTPUT_BYTES] + "\n...[truncated]"
        is_error = not bool(result.get("ok", True))
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "content": [{"type": "text", "text": text_payload}],
                "isError": is_error,
            },
        }

    if req_id is not None:
        _log(f"unknown method: {method}")
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def main() -> None:
    _log(f"starting pid={os.getpid()} bin={_INTERCEPTOR_BIN} chat={_CHAT_ID}")
    try:
        _PAUSE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        _log(f"pause dir setup failed (non-fatal): {e}")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            _log(f"JSON parse error: {e} — line: {line[:200]}")
            continue
        response = _handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

    _log("stdin closed, exiting")


if __name__ == "__main__":
    main()
