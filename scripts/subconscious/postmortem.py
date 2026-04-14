#!/opt/homebrew/bin/python3
"""Session postmortem — analyzes session transcripts and logs death metadata.

Used in two ways:
1. Called from Stop/StopFailure hooks to auto-log every session exit
2. Run standalone: python3 postmortem.py <session_id_or_jsonl_path>

Writes to:
- .subconscious/session_deaths.jsonl  (append-only audit log)
- Dual-sends Telegram + LocalChat alert on abnormal terminations
"""

import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "trading_plans", "production", "lib"))

import config
from trading_utils import send_alert

# Import secret scrubber from guardrail_core
try:
    _guardrail_path = os.path.join(os.path.dirname(__file__), "..", "guardrails")
    sys.path.insert(0, os.path.realpath(_guardrail_path))
    from guardrail_core import scrub_secrets
except ImportError:
    import re as _re
    _fallback_pats = [
        _re.compile(r"sk-(?:ant-|proj-)?[a-zA-Z0-9_-]{20,}"),
        _re.compile(r"xai-[a-zA-Z0-9_-]{20,}"),
        _re.compile(r"AIza[a-zA-Z0-9_-]{20,}"),
        _re.compile(r"AKIA[A-Z0-9]{16}"),
    ]
    def scrub_secrets(text):
        if not text or not isinstance(text, str):
            return text
        for p in _fallback_pats:
            text = p.sub("[REDACTED]", text)
        return text

# ── Constants ────────────────────────────────────────────────────────────

DEATHS_LOG = os.path.join(config.STATE_DIR, "session_deaths.jsonl")
CHARS_PER_TOKEN = 4  # rough heuristic

# Claude Code session transcripts live here
CC_PROJECT_DIR = os.path.expanduser(
    "~/.claude/projects/-Users-dana--openclaw-workspace"
)

# ── Alert helpers ────────────────────────────────────────────────────────


def _load_env():
    """Load .env into os.environ (best-effort)."""
    env_path = os.path.expanduser("~/.openclaw/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


# ── Transcript analysis ─────────────────────────────────────────────────


def analyze_transcript(path: str) -> dict:
    """Parse a session JSONL and return a postmortem report."""
    report = {
        "transcript_path": path,
        "file_size_bytes": 0,
        "total_lines": 0,
        "total_chars": 0,
        "estimated_tokens": 0,
        "message_counts": {},
        "tool_calls": 0,
        "last_message_type": None,
        "last_stop_reason": None,
        "last_tool_name": None,
        "last_tool_target": None,
        "verdict": "unknown",
    }

    if not os.path.exists(path):
        report["verdict"] = "file_not_found"
        return report

    report["file_size_bytes"] = os.path.getsize(path)

    total_chars = 0
    msg_counts: dict[str, int] = {}
    tool_calls = 0
    last_type = None
    last_stop = None
    last_tool_name = None
    last_tool_target = None
    line_count = 0
    session_id_from_file = None

    try:
        with open(path) as f:
            for line in f:
                line_count += 1
                line = line.strip()
                if not line:
                    continue
                total_chars += len(line)
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Track which session this line belongs to — reset counters on session change
                entry_session = entry.get("sessionId", "")
                if entry_session and entry_session != session_id_from_file:
                    if session_id_from_file is not None:
                        # New session in same file — reset counters (compaction happened)
                        total_chars = len(line)
                        msg_counts = {}
                        tool_calls = 0
                        last_type = None
                        last_stop = None
                        last_tool_name = None
                        last_tool_target = None
                        line_count = 1
                    session_id_from_file = entry_session

                msg_type = entry.get("type", "unknown")
                msg_counts[msg_type] = msg_counts.get(msg_type, 0) + 1
                last_type = msg_type

                # Track stop_reason on assistant messages
                message = entry.get("message", {})
                if isinstance(message, dict):
                    sr = message.get("stop_reason")
                    if sr is not None:
                        last_stop = sr
                    for block in message.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_calls += 1
                            last_tool_name = block.get("name")
                            inp = block.get("input", {})
                            last_tool_target = (
                                inp.get("file_path")
                                or inp.get("command", "")[:120]
                                or inp.get("pattern", "")
                                or None
                            )

    except Exception as exc:
        report["error"] = str(exc)

    report["total_lines"] = line_count
    report["total_chars"] = total_chars
    report["estimated_tokens"] = total_chars // CHARS_PER_TOKEN
    report["message_counts"] = msg_counts
    report["tool_calls"] = tool_calls
    report["last_message_type"] = last_type
    report["last_stop_reason"] = last_stop
    report["last_tool_name"] = last_tool_name
    report["last_tool_target"] = scrub_secrets(last_tool_target)

    # ── Verdict ──────────────────────────────────────────────────────
    if last_stop == "end_turn":
        report["verdict"] = "clean_exit"
    elif last_stop == "tool_use" or last_stop is None:
        # Died mid-generation or mid-tool-use
        if report["estimated_tokens"] < 5_000 and tool_calls == 0:
            # Session barely started — likely a recovery retry kill, not a real crash
            report["verdict"] = "startup_retry"
        elif report["estimated_tokens"] > 120_000:
            report["verdict"] = "probable_context_overflow"
        elif report["file_size_bytes"] > 800_000:
            report["verdict"] = "probable_context_overflow"
        else:
            report["verdict"] = "abnormal_termination"
    elif last_stop == "max_tokens":
        report["verdict"] = "max_tokens_hit"
    else:
        report["verdict"] = "unknown"

    return report


# ── Log & alert ──────────────────────────────────────────────────────────


def log_death(session_id: str, report: dict, event: str = "Stop") -> None:
    """Append to session_deaths.jsonl and alert on abnormal exits."""
    config.ensure_dirs()

    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "session_id": session_id,
        "event": event,
        "verdict": report["verdict"],
        "file_size_bytes": report["file_size_bytes"],
        "estimated_tokens": report["estimated_tokens"],
        "total_lines": report["total_lines"],
        "tool_calls": report["tool_calls"],
        "last_message_type": report["last_message_type"],
        "last_stop_reason": report["last_stop_reason"],
        "last_tool_name": report["last_tool_name"],
        "last_tool_target": report["last_tool_target"],
        "message_counts": report["message_counts"],
    }

    # Append to deaths log
    with open(DEATHS_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Alert on abnormal exits — but skip if session is still running (compaction, not death)
    if report["verdict"] in ("probable_context_overflow", "abnormal_termination",
                              "max_tokens_hit"):
        import subprocess
        still_alive = False
        try:
            # Check 1: pgrep for session_id in command args (works for --resume sessions)
            ps = subprocess.run(["pgrep", "-f", session_id], capture_output=True, timeout=5)
            if ps.returncode == 0 and ps.stdout.strip():
                still_alive = True
        except Exception:
            pass
        if not still_alive:
            try:
                # Check 2: is our parent process still a claude process?
                # Hooks are spawned by Claude — if parent is still claude, session is alive
                ppid = os.getppid()
                ps = subprocess.run(
                    ["ps", "-p", str(ppid), "-o", "comm="],
                    capture_output=True, text=True, timeout=5,
                )
                parent_cmd = ps.stdout.strip()
                if "claude" in parent_cmd.lower() or "node" in parent_cmd.lower():
                    still_alive = True
            except Exception:
                pass
        if still_alive:
            entry["verdict"] = "compaction"
            entry["note"] = "session still running, hook fired on compaction"
            # Re-write the last line with corrected verdict
            with open(DEATHS_LOG, "a") as f:
                f.write(json.dumps(entry) + "\n")
            return
        _alert_abnormal(session_id, report, event)


def _get_terminal_label(session_id: str) -> str:
    """Try to identify which terminal/tmux window this session is running in."""
    import subprocess
    try:
        # Find the process and its controlling terminal
        ps = subprocess.run(
            ["ps", "-p", session_id, "-o", "tty="],
            capture_output=True, text=True, timeout=5,
        )
        tty = ps.stdout.strip()
        if tty and tty != "??":
            # Try to get tmux pane title for this tty
            tmux = subprocess.run(
                ["tmux", "list-panes", "-a", "-F", "#{pane_tty} #{window_name}"],
                capture_output=True, text=True, timeout=5,
            )
            for line in tmux.stdout.strip().split("\n"):
                parts = line.split(" ", 1)
                if len(parts) == 2 and parts[0].endswith(tty.replace("s", "tty")):
                    return parts[1]
            return tty
    except Exception:
        pass
    return ""


def _alert_abnormal(session_id: str, report: dict, event: str) -> None:
    """Dual-send alert for abnormal session death."""
    short_id = session_id[:8]
    verdict = report["verdict"].replace("_", " ")
    est_tok = f"{report['estimated_tokens'] // 1000}K"
    last_doing = ""
    if report["last_tool_name"]:
        target = report["last_tool_target"] or ""
        if target and "/" in target:
            target = target.split("/")[-1]  # just filename
        last_doing = f"Last: {report['last_tool_name']}"
        if target:
            last_doing += f" → {target}"

    # Try to identify terminal
    terminal = _get_terminal_label(short_id)
    terminal_str = f" [{terminal}]" if terminal else ""

    # Telegram message
    tg_msg = (
        f"⚠️ Session {short_id}{terminal_str} died: {verdict}\n"
        f"~{est_tok} tokens, {report['tool_calls']} tool calls\n"
        f"{last_doing}"
    ).strip()
    send_alert(
        tg_msg,
        source="system",
        severity="critical",
        title="Session Crash Postmortem",
    )


# ── Hook entry point ────────────────────────────────────────────────────


def run_from_hook():
    """Called from Stop/StopFailure hooks. Reads payload from stdin."""
    import select
    ready, _, _ = select.select([sys.stdin], [], [], 0.2)
    if not ready:
        return
    raw = sys.stdin.read()
    if not raw.strip():
        return

    payload = json.loads(raw)
    session_id = payload.get("session_id", "")
    transcript_path = payload.get("transcript_path", "")
    event = payload.get("type", "Stop")

    if not session_id:
        return

    # If no transcript path, try to find it
    if not transcript_path:
        candidate = os.path.join(CC_PROJECT_DIR, f"{session_id}.jsonl")
        if os.path.exists(candidate):
            transcript_path = candidate

    if not transcript_path or not os.path.exists(transcript_path):
        # Can't analyze without a transcript — log minimal entry
        config.ensure_dirs()
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "session_id": session_id,
            "event": event,
            "verdict": "no_transcript",
        }
        with open(DEATHS_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return

    report = analyze_transcript(transcript_path)
    log_death(session_id, report, event)


# ── Standalone CLI ───────────────────────────────────────────────────────


def main_cli():
    """Run postmortem from command line on a session ID or JSONL path."""
    if len(sys.argv) < 2:
        print("Usage: postmortem.py <session_id | path_to.jsonl>")
        sys.exit(1)

    target = sys.argv[1]
    _load_env()

    # Is it a file path?
    if os.path.exists(target):
        path = target
        session_id = Path(target).stem
    else:
        # Treat as session ID — look for the JSONL
        session_id = target
        path = os.path.join(CC_PROJECT_DIR, f"{session_id}.jsonl")
        if not os.path.exists(path):
            print(f"Transcript not found: {path}")
            sys.exit(1)

    report = analyze_transcript(path)

    # Pretty-print
    print(f"Session:    {session_id}")
    print(f"File size:  {report['file_size_bytes']:,} bytes")
    print(f"Lines:      {report['total_lines']:,}")
    print(f"Est tokens: {report['estimated_tokens']:,}")
    print(f"Messages:   {json.dumps(report['message_counts'])}")
    print(f"Tool calls: {report['tool_calls']}")
    print(f"Last type:  {report['last_message_type']}")
    print(f"Last stop:  {report['last_stop_reason']}")
    print(f"Last tool:  {report['last_tool_name']}")
    print(f"Last target:{report['last_tool_target']}")
    print(f"Verdict:    {report['verdict']}")

    # Also log it if --log flag passed
    if "--log" in sys.argv:
        log_death(session_id, report, "manual_postmortem")
        print(f"\nLogged to {DEATHS_LOG}")

    # Also alert if --alert flag passed
    if "--alert" in sys.argv and report["verdict"] != "clean_exit":
        _alert_abnormal(session_id, report, "manual_postmortem")
        print("Alert sent.")


if __name__ == "__main__":
    main_cli()
