#!/usr/bin/env python3
"""MCP server that exposes macOS GUI automation to the Claude SDK.

Tools: screenshot, click, type_text, press_key, scroll, wait, get_frontmost,
activate_target_app.

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


def _target_pid() -> int | None:
    """Return the PID of the first running instance of APEX_CU_TARGET_BUNDLE, else None."""
    target = _target_bundle()
    if not target:
        return None
    try:
        AppKit = _get_appkit()
        apps = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(target)
        if apps and len(apps) > 0:
            return int(apps[0].processIdentifier())
    except Exception as e:
        _log_stderr(f"target_pid lookup failed: {e}")
    return None


def _post_unicode_to_pid(pid: int, text: str, interval: float = 0.012) -> int:
    """Post each char as keydown+keyup CGEvents scoped to `pid`, carrying the
    unicode code point via CGEventKeyboardSetUnicodeString.

    Focus-independent: keystrokes land in the target process regardless of
    which app is frontmost. Validated April 16 2026 via /tmp/cgevent_smoke.py
    — "HELLO FROM CGEVENT" delivered to TextEdit while Finder was frontmost.

    Checks the pause flag between characters and bails out early if the user
    pauses mid-type. Returns the number of characters actually posted.
    """
    Quartz = _get_quartz()
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    posted = 0
    for ch in text:
        # Respect pause flag between chars — the primary reason we don't use
        # pyautogui.typewrite here. File stat is cheap (<1ms) and lets the
        # user interrupt an in-flight type_text at any character boundary.
        if _is_paused():
            break
        for is_down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(src, 0, is_down)
            Quartz.CGEventKeyboardSetUnicodeString(ev, 1, ch)
            Quartz.CGEventPostToPid(pid, ev)
        posted += 1
        if interval > 0:
            time.sleep(interval)
    return posted


def _wait_for_target(timeout: float = 30.0, interval: float = 0.1) -> bool:
    """Poll frontmost up to `timeout` seconds waiting for target to match.

    Returns True as soon as frontmost bundle-id equals APEX_CU_TARGET_BUNDLE,
    False on timeout. If no target is configured, returns True immediately
    (the gate is open). Also respects the pause flag — if user pauses while
    we're waiting, returns False right away.

    This lets the user click out of the target app (e.g. to watch the agent
    from the Apex window) without corrupting an in-progress write action.
    The tool blocks until the user clicks back in, up to `timeout`.
    """
    target = _target_bundle()
    if not target:
        return True
    deadline = time.monotonic() + max(0.0, timeout)
    while time.monotonic() < deadline:
        if _is_paused():
            return False
        _name, bid = _frontmost_bundle()
        if bid == target:
            return True
        time.sleep(interval)
    _name, bid = _frontmost_bundle()
    return bid == target


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
    if not _wait_for_target(timeout=10.0):
        _, bid = _frontmost_bundle()
        _flog(logging.INFO, "click", f"refused: target mismatch {bid}")
        return {
            "ok": False,
            "reason": f"frontmost is {bid}, target is {_target_bundle()}. Refusing.",
            "frontmost": bid,
        }

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
    """Type text scoped to the target app's PID via CGEventPostToPid.

    Focus-independent: keystrokes are posted directly to the target
    process, so they land in the target regardless of which app is
    frontmost. If the user clicks out (e.g. into Apex to watch the agent
    work), typing continues uninterrupted in the target app. No chunking,
    no wait-for-frontmost, no pyautogui-follows-focus hazard.

    Mechanism: for each character, create a CGEventKeyboardEvent with
    virtual keycode 0, call CGEventKeyboardSetUnicodeString(ev, 1, ch)
    to stamp the actual unicode code point onto the event, then
    CGEventPostToPid(pid, ev). The target app sees it as a normal
    keystroke at its current keyboard focus inside its window.

    Fallbacks:
      * APEX_CU_TARGET_BUNDLE not set  → pyautogui.typewrite (legacy).
      * Target app not running         → refuse with hint to call
                                         activate_target_app first.

    Validated end-to-end April 16 2026 (/tmp/cgevent_smoke.py). Replaces
    the pyautogui.typewrite path that leaked keystrokes into whichever
    app the user clicked into mid-type (the bug reported April 16).
    """
    paused = _pause_check()
    if paused:
        _flog(logging.INFO, "type_text", "refused: paused")
        return paused

    text = str(args.get("text", ""))
    if not text:
        _flog(logging.INFO, "type_text", "ok chars=0 (empty)")
        return {"ok": True, "chars": 0}

    target = _target_bundle()
    if not target:
        # No target configured — fall back to legacy pyautogui path (follows focus).
        try:
            pyautogui = _get_pyautogui()
            pyautogui.typewrite(text, interval=0.01)
        except Exception as e:
            err = _permission_error("type_text", e)
            _flog(logging.ERROR, "type_text", err["reason"])
            return err
        _flog(logging.INFO, "type_text",
              f"ok (no target, pyautogui) chars={len(text)}")
        return {"ok": True, "chars": len(text), "method": "pyautogui"}

    pid = _target_pid()
    if pid is None:
        msg = (
            f"target app {target} is not running; call activate_target_app "
            f"first, then retry type_text."
        )
        _flog(logging.INFO, "type_text", f"refused: {msg}")
        return {"ok": False, "reason": msg}

    try:
        posted = _post_unicode_to_pid(pid, text)
    except Exception as e:
        err = _permission_error("type_text", e)
        _flog(logging.ERROR, "type_text", err["reason"])
        return err

    # Partial write if user hit pause mid-type. Report honestly so the agent
    # knows the full string didn't land and can decide whether to retry after
    # unpause, resume with the suffix, or ask the user.
    requested = len(text)
    paused_mid = posted < requested
    if paused_mid:
        _flog(logging.INFO, "type_text",
              f"paused mid-type pid={pid} target={target} "
              f"posted={posted}/{requested} remaining={text[posted:]!r}")
        return {
            "ok": False,
            "reason": "paused by user mid-type",
            "chars": posted,
            "requested": requested,
            "remaining": text[posted:],
            "method": "cgevent-post-to-pid",
            "pid": pid,
            "target": target,
        }

    _flog(logging.INFO, "type_text",
          f"ok pid={pid} target={target} chars={posted} method=cgevent-post-to-pid")
    return {
        "ok": True,
        "chars": posted,
        "method": "cgevent-post-to-pid",
        "pid": pid,
        "target": target,
    }


def _tool_press_key(args: dict) -> dict:
    paused = _pause_check()
    if paused:
        _flog(logging.INFO, "press_key", "refused: paused")
        return paused
    # Brief wait on mismatch so "click out to watch, click back in" doesn't
    # require the agent to re-fire.
    if not _wait_for_target(timeout=10.0):
        _, bid = _frontmost_bundle()
        _flog(logging.INFO, "press_key", f"refused: target mismatch {bid}")
        return {
            "ok": False,
            "reason": f"frontmost is {bid}, target is {_target_bundle()}. Refusing.",
            "frontmost": bid,
        }

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
    if not _wait_for_target(timeout=10.0):
        _, bid = _frontmost_bundle()
        _flog(logging.INFO, "scroll", f"refused: target mismatch {bid}")
        return {
            "ok": False,
            "reason": f"frontmost is {bid}, target is {_target_bundle()}. Refusing.",
            "frontmost": bid,
        }

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


def _tool_activate_target_app(_args: dict) -> dict:
    """Launch (if needed) and bring the configured target bundle-ID frontmost.

    Security: only activates the app whose bundle-ID is in APEX_CU_TARGET_BUNDLE.
    This is the single permitted way for the agent to break the chicken-and-egg
    where every write tool requires target-app frontmost but the agent had no
    way to bring it forward. The target is chat-scoped and set by the user via
    POST /api/chats/{id}/computer_use/enable; the agent cannot change it.

    Strategy (handles macOS Sonoma+ focus-stealing prevention):
      1. AppleScript `activate` + `reopen` (Dock-click equivalent: creates a
         window if none exist; required for apps like TextEdit that start
         without a visible document).
      2. If still not frontmost, NSRunningApplication.activateWithOptions_
         with NSApplicationActivateIgnoringOtherApps.
      3. If still not frontmost, send Cmd+Tab via the CGEvent path as a last
         resort (only works after step 2 registers the app as user-reachable).
    """
    target = (os.environ.get("APEX_CU_TARGET_BUNDLE") or "").strip()
    if not target:
        return {"ok": False, "reason": "APEX_CU_TARGET_BUNDLE not set; target-app gate is open but nothing to activate"}
    if _is_paused():
        return {"ok": False, "reason": "paused by user"}
    # macOS Mojave+ blocks cross-process focus steal via NSRunningApplication
    # .activateWithOptions:. AppleScript's `tell app id "..." to activate` has
    # the privileged path. Bundle ID is sanitized via a character whitelist so
    # it cannot break out of the double-quoted AppleScript literal.
    import re as _re
    import subprocess as _sp
    if not _re.match(r"^[A-Za-z0-9._-]+$", target):
        return {"ok": False, "reason": f"target bundle-ID {target!r} contains unsafe characters; refusing"}

    def _check_frontmost() -> bool:
        _, bid = _frontmost_bundle()
        return bid == target

    def _poll_frontmost(tries: int = 10, interval: float = 0.15) -> bool:
        for _ in range(tries):
            time.sleep(interval)
            if _check_frontmost():
                return True
        return False

    try:
        AppKit = _get_appkit()
        running = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(target)
        was_running = running is not None and len(running) > 0
        steps_tried: list[str] = []

        # --- Step 1: AppleScript activate + reopen (Dock-click equivalent) ---
        # `reopen` tells the app to show a default window if none exist.
        # Most document-based apps support it (TextEdit, Finder, Preview, etc).
        # The `try` inside AppleScript swallows NotHandled errors for apps that
        # don't implement reopen so `activate` still fires.
        script = (
            f'tell application id "{target}"\n'
            f'  activate\n'
            f'  try\n'
            f'    reopen\n'
            f'  end try\n'
            f'end tell'
        )
        proc = _sp.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True, text=True, timeout=8,
        )
        steps_tried.append("applescript")
        if proc.returncode != 0:
            err = (proc.stderr or "").strip()[:200]
            _flog(logging.WARNING, "activate_target_app", f"osascript failed rc={proc.returncode} err={err}")
            return {"ok": False, "reason": f"osascript activate failed for {target}: {err}. Check the bundle-ID is correct and the app is installed."}

        if _poll_frontmost():
            _flog(logging.INFO, "activate_target_app", f"ok via applescript target={target} was_running={was_running}")
            return {"ok": True, "bundle_id": target, "was_running": was_running, "now_frontmost": True, "method": "applescript"}

        # --- Step 2: NSRunningApplication activateWithOptions ignoring others ---
        # Re-fetch running apps because step 1 may have just launched the app.
        running2 = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(target)
        if running2 is not None and len(running2) > 0:
            # NSApplicationActivateIgnoringOtherApps = 1 << 1 = 2
            # NSApplicationActivateAllWindows        = 1 << 0 = 1
            opts = 2 | 1
            for app_ref in running2:
                try:
                    app_ref.activateWithOptions_(opts)
                except Exception as e:
                    _log_stderr(f"activateWithOptions exception: {e}")
            steps_tried.append("activateWithOptions")
            if _poll_frontmost():
                _flog(logging.INFO, "activate_target_app", f"ok via activateWithOptions target={target}")
                return {"ok": True, "bundle_id": target, "was_running": was_running, "now_frontmost": True, "method": "activateWithOptions"}

        # --- Step 3: AppleScript via System Events (click Dock tile) ---
        # If the app is running but still not frontmost, it likely has no
        # visible window and reopen was a no-op. Try System Events to click
        # the Dock tile, which is the single most reliable macOS surface-app
        # primitive. Requires Accessibility permission (already granted for
        # this tool to do anything useful).
        dock_script = (
            f'tell application id "{target}" to activate\n'
            f'delay 0.2\n'
            f'tell application "System Events"\n'
            f'  tell process "Dock"\n'
            f'    try\n'
            f'      set appName to name of first application process whose bundle identifier is "{target}"\n'
            f'      click UI element appName of list 1\n'
            f'    end try\n'
            f'  end tell\n'
            f'end tell'
        )
        proc3 = _sp.run(
            ["/usr/bin/osascript", "-e", dock_script],
            capture_output=True, text=True, timeout=8,
        )
        steps_tried.append("dock-click")
        if proc3.returncode == 0 and _poll_frontmost(tries=15, interval=0.2):
            _flog(logging.INFO, "activate_target_app", f"ok via dock-click target={target}")
            return {"ok": True, "bundle_id": target, "was_running": was_running, "now_frontmost": True, "method": "dock-click"}

        _, bid = _frontmost_bundle()
        _flog(logging.WARNING, "activate_target_app", f"all steps failed tried={steps_tried} frontmost={bid} target={target}")
        return {
            "ok": False,
            "bundle_id": target,
            "was_running": was_running,
            "now_frontmost": False,
            "methods_tried": steps_tried,
            "reason": (
                f"launched/activated {target} via {', '.join(steps_tried)} but frontmost is still {bid}. "
                f"The app may have no visible window and not support `reopen`. "
                f"Ask the user to Cmd+Tab to the app or click its Dock icon, then retry."
            ),
        }
    except Exception as e:
        _flog(logging.ERROR, "activate_target_app", f"exception: {e}")
        return {"ok": False, "reason": f"activate_target_app failed: {e}"}


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
            "Type a string into the configured target app. Uses CGEventPostToPid "
            "scoped to the target process, so keystrokes land in the target "
            "regardless of which app is frontmost — the user can click around "
            "without corrupting the stream. Requires the target app to be "
            "running; call activate_target_app first if get_frontmost shows a "
            "different app or the target isn't launched. Respects the pause "
            "flag. Returns {ok, chars, method, pid, target}."
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
    {
        "name": "activate_target_app",
        "description": (
            "Launch (if not running) and bring the configured target app frontmost "
            "so that write tools (click/type_text/press_key/scroll) will be allowed. "
            "Only activates the bundle-ID the user set for this chat via the enable "
            "endpoint — cannot switch to arbitrary apps. Call this FIRST if "
            "get_frontmost shows a different app, then verify with get_frontmost or "
            "proceed directly to screenshot. Returns {ok, bundle_id, was_running, "
            "now_frontmost}."
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
    "activate_target_app": _tool_activate_target_app,
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
