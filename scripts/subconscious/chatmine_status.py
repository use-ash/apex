#!/opt/homebrew/bin/python3
"""chatMine Status — quick overview of chatmine health and output.

Usage:
    python3 scripts/subconscious/chatmine_status.py          # compact summary
    python3 scripts/subconscious/chatmine_status.py -v        # verbose (recent log lines)
    python3 scripts/subconscious/chatmine_status.py --json    # machine-readable
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sqlite3
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────

WORKSPACE = Path("/Users/dana/.openclaw/workspace")
CHATMINE_DIR = WORKSPACE / ".subconscious" / "chatmine"
LOGS_DIR = WORKSPACE / "logs"
LOCK_DIR = Path("/tmp/chatmine_locks")
APEX_DB = Path(os.environ.get("APEX_DB", "/Users/dana/.openclaw/apex/state/apex.db"))

MODES = {
    "prod":   {"log": "chatmine.log",        "label": "Apex (prod)"},
    "dev":    {"log": "chatmine_dev.log",     "label": "Apex (dev)"},
    "claude": {"log": "chatmine_claude.log",  "label": "Claude Code"},
    "codex":  {"log": "chatmine_codex.log",   "label": "Codex"},
}

# ── Helpers ───────────────────────────────────────────────────────────

def _dim(s: str) -> str:
    return f"\033[2m{s}\033[0m"

def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"

def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"

def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"

def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"

def _cyan(s: str) -> str:
    return f"\033[36m{s}\033[0m"


def _ago(dt: datetime.datetime) -> str:
    """Human-readable time-ago string."""
    delta = datetime.datetime.now() - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def _parse_log_entry(line: str) -> dict | None:
    """Parse a cron log line like 'Mon Apr  6 05:00:00 PDT 2026: chatmine-prod starting'."""
    # Match: <date>: <label> <action> [optional details]
    m = re.match(
        r'^(.+?\d{4}):\s+(chatmine-\w+)\s+(starting|finished|skipped)(.*)',
        line.strip()
    )
    if not m:
        return None
    try:
        dt = datetime.datetime.strptime(m.group(1).strip(), "%a %b %d %H:%M:%S %Z %Y")
    except ValueError:
        # Try without timezone
        try:
            raw = re.sub(r'\s+[A-Z]{3,4}\s+', ' ', m.group(1).strip())
            dt = datetime.datetime.strptime(raw, "%a %b %d %H:%M:%S %Y")
        except ValueError:
            return None
    return {
        "time": dt,
        "label": m.group(2),
        "action": m.group(3),
        "detail": m.group(4).strip(),
    }


def _last_entries(log_path: Path, n: int = 20) -> list[dict]:
    """Get last N parseable entries from a log file."""
    if not log_path.exists():
        return []
    entries = []
    with open(log_path) as f:
        for line in f:
            parsed = _parse_log_entry(line)
            if parsed:
                entries.append(parsed)
    return entries[-n:]


def _cron_enabled() -> dict[str, bool]:
    """Check which chatmine cron jobs are enabled."""
    result = {}
    try:
        crontab = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception:
        return {m: False for m in MODES}

    for mode in MODES:
        # Look for uncommented run_chatmine.sh lines
        pattern = re.compile(rf'^[^#].*run_chatmine\.sh\s+{mode}', re.MULTILINE)
        result[mode] = bool(pattern.search(crontab))
    return result


def _lock_status() -> dict:
    """Check for active lock files."""
    locks = {}
    global_lock = LOCK_DIR / "chatmine_global.lock"
    if global_lock.exists():
        try:
            pid = int(global_lock.read_text().strip())
            alive = subprocess.run(
                ["kill", "-0", str(pid)], capture_output=True
            ).returncode == 0
            locks["global"] = {"pid": pid, "alive": alive}
        except (ValueError, OSError):
            locks["global"] = {"pid": None, "alive": False}

    for mode in MODES:
        lock = LOCK_DIR / f"chatmine_{mode}.lock"
        if lock.exists():
            try:
                pid = int(lock.read_text().strip())
                alive = subprocess.run(
                    ["kill", "-0", str(pid)], capture_output=True
                ).returncode == 0
                locks[mode] = {"pid": pid, "alive": alive}
            except (ValueError, OSError):
                locks[mode] = {"pid": None, "alive": False}
    return locks


def _output_stats() -> dict:
    """Count summaries and total knowledge items per category."""
    stats = {"apex": 0, "claude": 0, "codex": 0, "total_items": 0}

    if not CHATMINE_DIR.exists():
        return stats

    # Apex chats (direct subdirs that aren't claude/codex)
    for d in CHATMINE_DIR.iterdir():
        if d.is_dir() and d.name not in ("claude", "codex"):
            if (d / "summary.md").exists():
                stats["apex"] += 1

    # Claude sessions
    claude_dir = CHATMINE_DIR / "claude"
    if claude_dir.exists():
        for d in claude_dir.iterdir():
            if d.is_dir() and (d / "summary.md").exists():
                stats["claude"] += 1

    # Codex sessions
    codex_dir = CHATMINE_DIR / "codex"
    if codex_dir.exists():
        for d in codex_dir.iterdir():
            if d.is_dir() and (d / "summary.md").exists():
                stats["codex"] += 1

    # Total knowledge items (count headings in summaries)
    for summary in CHATMINE_DIR.rglob("summary.md"):
        try:
            text = summary.read_text()
            stats["total_items"] += text.count("\n- ")
        except OSError:
            pass

    return stats


def _disk_usage() -> str:
    """Total disk usage of chatmine output."""
    if not CHATMINE_DIR.exists():
        return "0"
    try:
        result = subprocess.run(
            ["du", "-sh", str(CHATMINE_DIR)],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.split()[0] if result.stdout else "?"
    except Exception:
        return "?"


def _last_run_info(mode: str) -> dict:
    """Get info about the most recent run for a mode."""
    log_path = LOGS_DIR / MODES[mode]["log"]
    entries = _last_entries(log_path)
    if not entries:
        return {"status": "no_data", "last_run": None, "last_finish": None}

    # Find last start and last finish
    last_start = None
    last_finish = None
    last_skip = None
    for e in reversed(entries):
        if e["action"] == "starting" and not last_start:
            last_start = e
        elif e["action"] == "finished" and not last_finish:
            last_finish = e
        elif e["action"] == "skipped" and not last_skip:
            last_skip = e
        if last_start and last_finish:
            break

    info = {"last_run": last_start, "last_finish": last_finish, "last_skip": last_skip}

    if last_start and last_finish and last_finish["time"] > last_start["time"]:
        duration = last_finish["time"] - last_start["time"]
        info["status"] = "ok"
        info["duration"] = str(duration).split(".")[0]
        info["exit"] = last_finish["detail"]
    elif last_start and (not last_finish or last_start["time"] > last_finish["time"]):
        info["status"] = "running"
    else:
        info["status"] = "ok"

    return info


# ── Display ───────────────────────────────────────────────────────────

def print_status(verbose: bool = False):
    cron = _cron_enabled()
    locks = _lock_status()
    stats = _output_stats()
    disk = _disk_usage()

    print()
    print(_bold("  chatMine Status"))
    print(_dim("  ─" * 25))

    # Cron status
    all_disabled = not any(cron.values())
    if all_disabled:
        print(f"  Cron:    {_yellow('ALL DISABLED')}")
    else:
        enabled = [m for m, v in cron.items() if v]
        disabled = [m for m, v in cron.items() if not v]
        print(f"  Cron:    {_green(', '.join(enabled))} enabled", end="")
        if disabled:
            print(f"  {_dim('(' + ', '.join(disabled) + ' off)')}", end="")
        print()

    # Lock status
    if locks:
        alive = {k: v for k, v in locks.items() if v.get("alive")}
        stale = {k: v for k, v in locks.items() if not v.get("alive")}
        if alive:
            pids = ", ".join(f"{k} (PID {v['pid']})" for k, v in alive.items())
            print(f"  Running: {_cyan(pids)}")
        if stale:
            names = ", ".join(stale.keys())
            print(f"  Stale:   {_red(names + ' — stale lock files')}")
    else:
        print(f"  Running: {_dim('none')}")

    print()

    # Per-mode last run
    print(_bold("  Last Runs"))
    print(_dim("  ─" * 25))
    for mode, meta in MODES.items():
        info = _last_run_info(mode)
        label = f"{meta['label']:16s}"
        cron_tag = _green("●") if cron.get(mode) else _red("○")

        if info["status"] == "no_data":
            print(f"  {cron_tag} {label} {_dim('no log data')}")
        elif info["status"] == "running":
            started = info["last_run"]["time"]
            print(f"  {cron_tag} {label} {_cyan('▶ running')}  started {_ago(started)}")
        else:
            finished = info["last_finish"]["time"] if info["last_finish"] else None
            if finished:
                exit_info = info.get("exit", "")
                dur = info.get("duration", "?")
                ok = "exit=0" in exit_info
                status = _green(f"✓ {dur}") if ok else _red(f"✗ {exit_info}")
                print(f"  {cron_tag} {label} {status}  {_dim(_ago(finished))}")
            else:
                print(f"  {cron_tag} {label} {_dim('unknown')}")

        # Show skip rate in verbose mode
        if verbose and info.get("last_skip"):
            skip_time = info["last_skip"]["time"]
            detail = info["last_skip"].get("detail", "")
            print(f"       {_dim(f'last skip: {_ago(skip_time)} — {detail}')}")

    print()

    # Output stats
    print(_bold("  Knowledge Base"))
    print(_dim("  ─" * 25))
    print(f"  Apex chats:      {stats['apex']} summaries")
    print(f"  Claude sessions: {stats['claude']} summaries")
    print(f"  Codex sessions:  {stats['codex']} summaries")
    print(f"  Total items:     ~{stats['total_items']:,}")
    print(f"  Disk usage:      {disk}")
    print()

    if verbose:
        print(_bold("  Recent Log Tail"))
        print(_dim("  ─" * 25))
        for mode, meta in MODES.items():
            log_path = LOGS_DIR / meta["log"]
            if log_path.exists():
                print(f"  {_cyan(meta['label'])}:")
                try:
                    lines = log_path.read_text().strip().split("\n")[-6:]
                    for line in lines:
                        print(f"    {_dim(line)}")
                except OSError:
                    print(f"    {_dim('(read error)')}")
                print()


def print_json():
    cron = _cron_enabled()
    locks = _lock_status()
    stats = _output_stats()
    disk = _disk_usage()

    data = {
        "timestamp": datetime.datetime.now().isoformat(),
        "cron": cron,
        "locks": {k: {"pid": v["pid"], "alive": v["alive"]} for k, v in locks.items()},
        "last_runs": {},
        "output": {
            "apex_summaries": stats["apex"],
            "claude_summaries": stats["claude"],
            "codex_summaries": stats["codex"],
            "total_items": stats["total_items"],
            "disk_usage": disk,
        },
    }

    for mode in MODES:
        info = _last_run_info(mode)
        run_data = {"status": info["status"]}
        if info.get("last_finish"):
            run_data["last_finish"] = info["last_finish"]["time"].isoformat()
        if info.get("duration"):
            run_data["duration"] = info["duration"]
        data["last_runs"][mode] = run_data

    print(json.dumps(data, indent=2))


# ── Main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="chatMine status monitor")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show recent log lines")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.json:
        print_json()
    else:
        print_status(verbose=args.verbose)
