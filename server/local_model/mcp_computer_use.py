#!/usr/bin/env python3
"""MCP server that exposes macOS GUI automation to the Claude SDK.

Tools: screenshot, click, type_text, press_key, scroll, wait, get_frontmost.

Protocol: newline-delimited JSON-RPC over stdin/stdout (MCP stdio transport),
matching mcp_execute_code.py exactly.

Target-app enforcement: if APEX_CU_TARGET_BUNDLE is set, every write action
(click/type_text/press_key/scroll) verifies NSWorkspace.frontmostApplication()
bundleIdentifier matches. If not, returns {ok: false, reason: "..."} without
raising.

Pause flag: file at {APEX_CU_STATE_DIR}/pause/{APEX_CU_CHAT_ID}. If present,
write actions return {ok: false, reason: "paused by user"}.

Run standalone:  python3 mcp_computer_use.py
Registered via:  streaming.py _inject_computer_use_mcp() (auto-configured)
"""
import base64
import io
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# stderr diagnostic logging (visible in Claude Code debug output)
# ---------------------------------------------------------------------------

def _log_stderr(msg: str) -> None:
    print(f"[mcp-computer-use] {msg}", file=sys.stderr, flush=True)


# Add server dir to path for consistency with mcp_execute_code.py
_server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


# ---------------------------------------------------------------------------
# Config from env (re-read on each call where noted, not import time)
# ---------------------------------------------------------------------------

_PYTHON_PATH_HINT = "/Users/dana/.openclaw/apex/.venv/bin/python3.14"


def _state_dir() -> str:
    return os.environ.get("APEX_CU_STATE_DIR", "/tmp/apex_computer_use")


def _chat_id() -> str:
    return os.environ.get("APEX_CU_CHAT_ID", "default")


def _target_bundle() -> str:
    """Read target bundle id at call time so it can change between chats."""
    return (os.environ.get("APEX_CU_TARGET_BUNDLE") or "").strip()


def _pause_flag_path() -> str:
    return os.path.join(_state_dir(), "pause", _chat_id())


def _screenshots_dir() -> str:
    return os.path.join(_state_dir(), "screenshots", _chat_id())


# ---------------------------------------------------------------------------
# File logging
# ---------------------------------------------------------------------------

_file_logger: logging.Logger | None = None


def _get_file_logger() -> logging.Logger:
    global _file_logger
    if _file_logger is not None:
        return _file_logger
    lg = logging.getLogger("apex.mcp_computer_use")
    lg.setLevel(logging.INFO)
    lg.propagate = False
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        log_path = os.path.join(_state_dir(), "mcp_computer_use.log")
        h = logging.FileHandler(log_path)
        h.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] chat=%(chat_id)s %(message)s"
        ))
        lg.addHandler(h)
    except Exception as e:
        _log_stderr(f"file logger setup failed: {e}")
    _file_logger = lg
    return lg


def _flog(level: int, tool: str, msg: str) -> None:
    try:
        lg = _get_file_logger()
        lg.log(level, f"tool={tool} {msg}", extra={"chat_id": _chat_id()})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Lazy imports for pyautogui / pyobjc / PIL — fail soft with clear messages
# ---------------------------------------------------------------------------

_pyautogui = None
_Quartz = None
_AppKit = None
_PIL_Image = None


def _get_pyautogui():
    global _pyautogui
    if _pyautogui is not None:
        return _pyautogui
    import pyautogui  # type: ignore
    pyautogui.FAILSAFE = False
    _pyautogui = pyautogui
    return _pyautogui


def _get_quartz():
    global _Quartz
    if _Quartz is not None:
        return _Quartz
    import Quartz  # type: ignore
    _Quartz = Quartz
    return _Quartz


def _get_appkit():
    global _AppKit
    if _AppKit is not None:
        return _AppKit
    import AppKit  # type: ignore
    _AppKit = AppKit
    return _AppKit


def _get_pil():
    global _PIL_Image
    if _PIL_Image is not None:
        return _PIL_Image
    from PIL import Image  # type: ignore
    _PIL_Image = Image
    return _PIL_Image


# ---------------------------------------------------------------------------
# Helpers: frontmost app, pause, target-app check
# ---------------------------------------------------------------------------

def _frontmost_bundle() -> tuple[str | None, str | None]:
    """Return (app_name, bundle_id) of the frontmost app, or (None, None)."""
    try:
        AppKit = _get_appkit()
        ws = AppKit.NSWorkspace.sharedWorkspace()
        app = ws.frontmostApplication()
        if app is None:
            return (None, None)
        name = app.localizedName()
        bid = app.bundleIdentifier()
        return (str(name) if name else None, str(bid) if bid else None)
    except Exception as e:
        _log_stderr(f"frontmost lookup failed: {e}")
        return (None, None)


def _frontmost_window_title(pid: int | None) -> str | None:
    """Best-effort window title via Quartz CGWindowListCopyWindowInfo."""
    if pid is None:
        return None
    try:
        Quartz = _get_quartz()
        opts = (Quartz.kCGWindowListOptionOnScreenOnly |
                Quartz.kCGWindowListExcludeDesktopElements)
        windows = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID)
        for w in windows or []:
            try:
                if int(w.get("kCGWindowOwnerPID", -1)) == int(pid):
                    name = w.get("kCGWindowName") or ""
                    if name:
                        return str(name)
            except Exception:
                continue
        return None
    except Exception:
        return None


def _is_paused() -> bool:
    try:
        return os.path.exists(_pause_flag_path())
    except Exception:
        return False


def _target_app_check() -> dict | None:
    """Return None if allowed; else a refusal dict."""
    target = _target_bundle()
    if not target:
        return None
    _name, bid = _frontmost_bundle()
    if bid != target:
        return {
            "ok": False,
            "reason": f"frontmost is {bid}, target is {target}. Refusing.",
            "frontmost": bid,
        }
    return None


def _pause_check() -> dict | None:
    if _is_paused():
        return {"ok": False, "reason": "paused by user"}
    return None


def _permission_error(action: str, exc: Exception) -> dict:
    return {
        "ok": False,
        "reason": (
            f"macOS Accessibility permission not granted to Python interpreter. "
            f"System Settings > Privacy & Security > Accessibility — add "
            f"{_PYTHON_PATH_HINT}  (underlying error on {action}: "
            f"{type(exc).__name__}: {exc})"
        ),
    }


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _tool_screenshot(args: dict) -> list[dict]:
    """Always-allowed. Returns [image block, text block]."""
    region = args.get("region") if isinstance(args, dict) else None
    try:
        Quartz = _get_quartz()
        PIL_Image = _get_pil()
    except Exception as e:
        msg = f"screenshot deps missing: {type(e).__name__}: {e}"
        _flog(logging.ERROR, "screenshot", msg)
        return [{"type": "text", "text": msg}]

    try:
        if region and all(k in region for k in ("x", "y", "w", "h")):
            rect = Quartz.CGRectMake(
                float(region["x"]), float(region["y"]),
                float(region["w"]), float(region["h"]),
            )
        else:
            rect = Quartz.CGRectInfinite

        image_ref = Quartz.CGWindowListCreateImage(
            rect,
            Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
            Quartz.kCGWindowImageDefault,
        )
        if image_ref is None:
            msg = (
                "Screen capture returned no image. This usually means macOS "
                "Screen Recording permission is not granted to the Python "
                f"interpreter. System Settings > Privacy & Security > Screen "
                f"Recording — add {_PYTHON_PATH_HINT}"
            )
            _flog(logging.ERROR, "screenshot", "no image returned")
            return [{"type": "text", "text": msg}]

        width = int(Quartz.CGImageGetWidth(image_ref))
        height = int(Quartz.CGImageGetHeight(image_ref))
        bytes_per_row = int(Quartz.CGImageGetBytesPerRow(image_ref))
        data_provider = Quartz.CGImageGetDataProvider(image_ref)
        raw = Quartz.CGDataProviderCopyData(data_provider)
        # raw is a CFData; convert to bytes
        buf = bytes(raw)

        # CGImage on macOS is typically BGRA; PIL "RGBA" from raw then convert
        img = PIL_Image.frombuffer(
            "RGBA", (width, height), buf, "raw", "BGRA", bytes_per_row, 1
        )

        # Downscale so max edge <= 1568
        MAX_EDGE = 1568
        w, h = img.size
        if max(w, h) > MAX_EDGE:
            scale = MAX_EDGE / float(max(w, h))
            new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            img = img.resize(new_size, PIL_Image.LANCZOS)

        # Encode PNG
        out = io.BytesIO()
        img.convert("RGB").save(out, format="PNG", optimize=True)
        png_bytes = out.getvalue()
        b64 = base64.b64encode(png_bytes).decode("ascii")

        # Persist to disk
        ss_dir = _screenshots_dir()
        os.makedirs(ss_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
        path = os.path.join(ss_dir, f"{ts}.png")
        try:
            with open(path, "wb") as f:
                f.write(png_bytes)
        except Exception as e:
            _flog(logging.WARNING, "screenshot", f"persist failed: {e}")
            path = "(not saved)"

        final_w, final_h = img.size
        _flog(logging.INFO, "screenshot",
              f"ok path={path} size={final_w}x{final_h} bytes={len(png_bytes)}")

        return [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": b64,
                },
            },
            {
                "type": "text",
                "text": f"saved to {path}, {final_w}x{final_h}",
            },
        ]
    except Exception as e:
        msg = f"screenshot failed: {type(e).__name__}: {e}"
        _flog(logging.ERROR, "screenshot", msg)
        return [{"type": "text", "text": msg}]


def _tool_click(args: dict) -> dict:
    paused = _pause_check()
    if paused:
        _flog(logging.INFO, "click", "refused: paused")
        return paused
    refusal = _target_app_check()
    if refusal:
        _flog(logging.INFO, "click", f"refused: target mismatch {refusal['frontmost']}")
        return refusal

    x = int(args.get("x", 0))
    y = int(args.get("y", 0))
    button = str(args.get("button", "left"))
    double = bool(args.get("double", False))

    try:
        pyautogui = _get_pyautogui()
        pyautogui.click(x=x, y=y, button=button, clicks=2 if double else 1)
    except Exception as e:
        err = _permission_error("click", e)
        _flog(logging.ERROR, "click", err["reason"])
        return err

    _name, bid = _frontmost_bundle()
    _flog(logging.INFO, "click",
          f"ok x={x} y={y} button={button} double={double} frontmost={bid}")
    return {"ok": True, "frontmost": bid, "x": x, "y": y}


def _tool_type_text(args: dict) -> dict:
    paused = _pause_check()
    if paused:
        _flog(logging.INFO, "type_text", "refused: paused")
        return paused
    refusal = _target_app_check()
    if refusal:
        _flog(logging.INFO, "type_text", f"refused: target mismatch {refusal['frontmost']}")
        return refusal

    text = str(args.get("text", ""))
    try:
        pyautogui = _get_pyautogui()
        pyautogui.typewrite(text, interval=0.01)
    except Exception as e:
        err = _permission_error("type_text", e)
        _flog(logging.ERROR, "type_text", err["reason"])
        return err

    _flog(logging.INFO, "type_text", f"ok chars={len(text)}")
    return {"ok": True, "chars": len(text)}


def _tool_press_key(args: dict) -> dict:
    paused = _pause_check()
    if paused:
        _flog(logging.INFO, "press_key", "refused: paused")
        return paused
    refusal = _target_app_check()
    if refusal:
        _flog(logging.INFO, "press_key", f"refused: target mismatch {refusal['frontmost']}")
        return refusal

    key = str(args.get("key", "")).strip()
    if not key:
        return {"ok": False, "reason": "key is empty"}

    try:
        pyautogui = _get_pyautogui()
        if "+" in key:
            parts = [p.strip() for p in key.split("+") if p.strip()]
            pyautogui.hotkey(*parts)
        else:
            pyautogui.press(key)
    except Exception as e:
        err = _permission_error("press_key", e)
        _flog(logging.ERROR, "press_key", err["reason"])
        return err

    _flog(logging.INFO, "press_key", f"ok key={key}")
    return {"ok": True, "key": key}


def _tool_scroll(args: dict) -> dict:
    paused = _pause_check()
    if paused:
        _flog(logging.INFO, "scroll", "refused: paused")
        return paused
    refusal = _target_app_check()
    if refusal:
        _flog(logging.INFO, "scroll", f"refused: target mismatch {refusal['frontmost']}")
        return refusal

    x = int(args.get("x", 0))
    y = int(args.get("y", 0))
    direction = str(args.get("direction", "down"))
    amount = int(args.get("amount", 3))

    try:
        pyautogui = _get_pyautogui()
        pyautogui.moveTo(x, y)
        pyautogui.scroll(amount if direction == "up" else -amount)
    except Exception as e:
        err = _permission_error("scroll", e)
        _flog(logging.ERROR, "scroll", err["reason"])
        return err

    _flog(logging.INFO, "scroll",
          f"ok x={x} y={y} direction={direction} amount={amount}")
    return {"ok": True}


def _tool_wait(args: dict) -> dict:
    try:
        secs = float(args.get("seconds", 0))
    except (TypeError, ValueError):
        secs = 0.0
    secs = max(0.0, min(secs, 30.0))
    time.sleep(secs)
    _flog(logging.INFO, "wait", f"ok waited={secs}")
    return {"ok": True, "waited": secs}


def _tool_get_frontmost(_args: dict) -> dict:
    name, bid = _frontmost_bundle()
    title: str | None = None
    try:
        AppKit = _get_appkit()
        ws = AppKit.NSWorkspace.sharedWorkspace()
        app = ws.frontmostApplication()
        pid = int(app.processIdentifier()) if app is not None else None
        title = _frontmost_window_title(pid)
    except Exception as e:
        _log_stderr(f"get_frontmost window title failed: {e}")
    _flog(logging.INFO, "get_frontmost", f"ok app={name} bid={bid}")
    return {
        "app": name,
        "bundle_id": bid,
        "window_title": title,
    }


# ---------------------------------------------------------------------------
# Tool schemas (MCP tools/list)
# ---------------------------------------------------------------------------

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "screenshot",
        "description": (
            "Capture the macOS screen (or a region). Returns a downscaled PNG "
            "(max edge 1568px) as a base64 image block plus a text block with "
            "the saved file path and dimensions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "w": {"type": "integer"},
                        "h": {"type": "integer"},
                    },
                    "required": ["x", "y", "w", "h"],
                },
            },
        },
    },
    {
        "name": "click",
        "description": (
            "Click at absolute screen coordinates. Respects APEX_CU_TARGET_BUNDLE "
            "and the pause flag. Returns {ok, frontmost, x, y}."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "button": {"type": "string", "enum": ["left", "right", "middle"]},
                "double": {"type": "boolean"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "type_text",
        "description": (
            "Type a string at current keyboard focus. Respects target-app check "
            "and pause flag. Returns {ok, chars}."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "press_key",
        "description": (
            "Press a key or key combo (e.g. 'return', 'escape', 'cmd+space', "
            "'cmd+shift+4'). Respects target-app check and pause flag."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
            },
            "required": ["key"],
        },
    },
    {
        "name": "scroll",
        "description": (
            "Move to (x, y) and scroll up/down by amount. Respects target-app "
            "check and pause flag."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "direction": {"type": "string", "enum": ["up", "down"]},
                "amount": {"type": "integer"},
            },
            "required": ["x", "y", "direction", "amount"],
        },
    },
    {
        "name": "wait",
        "description": "Sleep for up to 30 seconds. Returns {ok, waited}.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "number"},
            },
            "required": ["seconds"],
        },
    },
    {
        "name": "get_frontmost",
        "description": (
            "Return the frontmost macOS application: {app, bundle_id, "
            "window_title}. Always allowed."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


_DISPATCH = {
    "screenshot": _tool_screenshot,       # returns list[block]
    "click": _tool_click,                 # returns dict
    "type_text": _tool_type_text,
    "press_key": _tool_press_key,
    "scroll": _tool_scroll,
    "wait": _tool_wait,
    "get_frontmost": _tool_get_frontmost,
}


def _result_to_content(tool_name: str, result: Any) -> tuple[list[dict], bool]:
    """Convert a tool result into MCP content blocks + isError flag."""
    if tool_name == "screenshot" and isinstance(result, list):
        # Already in MCP content-block form
        is_err = any(
            b.get("type") == "text" and b.get("text", "").startswith(
                ("screenshot failed", "Screen capture", "screenshot deps")
            )
            for b in result
        )
        return result, is_err

    # Dict result — return one text block with pretty JSON
    if isinstance(result, dict):
        is_err = not bool(result.get("ok", True))
        return [{"type": "text", "text": json.dumps(result)}], is_err

    return [{"type": "text", "text": str(result)}], False


# ---------------------------------------------------------------------------
# JSON-RPC handler
# ---------------------------------------------------------------------------

def _handle_request(request: dict) -> dict | None:
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        _log_stderr(f"initialize (id={req_id})")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "apex-computer-use",
                    "version": "1.0.0",
                },
            },
        }

    if method == "notifications/initialized":
        _log_stderr("notifications/initialized received")
        return None

    if method == "tools/list":
        _log_stderr(f"tools/list (id={req_id})")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": _TOOLS},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        _log_stderr(f"tools/call: {tool_name} (id={req_id})")

        handler = _DISPATCH.get(tool_name)
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    "isError": True,
                },
            }

        try:
            result = handler(args)
        except Exception as e:
            msg = f"{tool_name} raised: {type(e).__name__}: {e}"
            _log_stderr(msg)
            _flog(logging.ERROR, tool_name, msg)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": msg}],
                    "isError": True,
                },
            }

        content, is_err = _result_to_content(tool_name, result)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": content, "isError": is_err},
        }

    if req_id is not None:
        _log_stderr(f"unknown method: {method} (id={req_id})")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    _log_stderr(f"unknown notification: {method}")
    return None


# ---------------------------------------------------------------------------
# Main stdio loop
# ---------------------------------------------------------------------------

def main() -> None:
    _log_stderr(f"starting (pid={os.getpid()}, python={sys.executable})")
    _log_stderr(
        f"env: APEX_CU_CHAT_ID={_chat_id()}, "
        f"APEX_CU_TARGET_BUNDLE={_target_bundle() or '(unset)'}, "
        f"APEX_CU_STATE_DIR={_state_dir()}"
    )

    # Warm up file logger early so any init issues surface
    _get_file_logger()
    _flog(logging.INFO, "__init__",
          f"server started target={_target_bundle() or '(unset)'}")

    _log_stderr("ready, reading stdin")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            _log_stderr(f"JSON parse error: {e} — line: {line[:200]}")
            continue
        response = _handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

    _log_stderr("stdin closed, exiting")


if __name__ == "__main__":
    main()
