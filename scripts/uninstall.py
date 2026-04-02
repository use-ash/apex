#!/usr/bin/env python3
"""apex uninstall — Remove Apex server installation with selective cleanup.

Usage:
    python3 scripts/uninstall.py           # interactive, preserves user data
    python3 scripts/uninstall.py --purge   # also removes memory/transcripts
    python3 scripts/uninstall.py --yes     # non-interactive (use with care)

Exit codes:
    0  Success
    1  Cancelled by user
    2  Error during removal
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

APEX_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = APEX_ROOT / "state"

# --- Items always removed ---
REMOVE_ALWAYS = [
    # Config and DB
    STATE_DIR / "config.json",
    STATE_DIR / "apex.db",
    STATE_DIR / "apex.db-shm",
    STATE_DIR / "apex.db-wal",
    STATE_DIR / "apex.log",
    STATE_DIR / "localchat.db",
    STATE_DIR / "localchat.db-shm",
    STATE_DIR / "localchat.db-wal",
    STATE_DIR / "localchat.log",
    # License + instance ID
    STATE_DIR / "license.json",
    STATE_DIR / ".instance_id",
    # TLS certificates
    STATE_DIR / "ssl",
    STATE_DIR / "ssl_backup_encrypted",
    # Uploads
    STATE_DIR / "uploads",
    # Streams (temp files)
    STATE_DIR / "streams",
    # Push device tokens DB
    STATE_DIR / "devices.db",
    # Venv (if created by install.sh)
    APEX_ROOT / ".venv",
    APEX_ROOT / "server" / "__pycache__",
]

# --- Items removed only with --purge ---
REMOVE_PURGE = [
    STATE_DIR / "backups",
]

LAUNCHD_LABEL = "com.apex.server"
LAUNCHD_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def _confirm(prompt: str) -> bool:
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
        return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def _remove(path: Path) -> tuple[bool, str]:
    """Remove file or directory. Returns (success, message)."""
    if not path.exists() and not path.is_symlink():
        return True, f"  [ ] {path.relative_to(APEX_ROOT)} — not found"
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True, f"  [x] {path.relative_to(APEX_ROOT)}"
    except Exception as exc:
        return False, f"  [!] {path.relative_to(APEX_ROOT)} — {exc}"


def _stop_server() -> None:
    """Try to stop a running Apex server gracefully."""
    # LaunchD
    if LAUNCHD_PLIST.exists():
        subprocess.run(
            ["launchctl", "unload", str(LAUNCHD_PLIST)],
            check=False, capture_output=True
        )
        return

    # pkill as fallback
    subprocess.run(
        ["pkill", "-f", "apex.py"],
        check=False, capture_output=True
    )


def _remove_launchd() -> None:
    if LAUNCHD_PLIST.exists():
        try:
            LAUNCHD_PLIST.unlink()
            print(f"  [x] LaunchAgent: {LAUNCHD_PLIST}")
        except Exception as exc:
            print(f"  [!] LaunchAgent: {exc}")
    else:
        print("  [ ] LaunchAgent — not found")


def main() -> int:
    parser = argparse.ArgumentParser(description="Uninstall Apex server")
    parser.add_argument("--purge", action="store_true",
                        help="Also remove backups and user data")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Non-interactive — skip confirmation prompt")
    args = parser.parse_args()

    print()
    print("Apex Uninstall")
    print("=" * 40)
    print()

    remove_list = REMOVE_ALWAYS[:]
    if args.purge:
        remove_list += REMOVE_PURGE

    existing = [p for p in remove_list if p.exists() or p.is_symlink()]

    print("The following will be REMOVED:")
    for p in remove_list:
        exists = p.exists() or p.is_symlink()
        marker = "[x]" if exists else "[ ]"
        try:
            rel = p.relative_to(APEX_ROOT)
        except ValueError:
            rel = p
        print(f"  {marker} {rel}")

    if LAUNCHD_PLIST.exists():
        print(f"  [x] LaunchAgent: {LAUNCHD_PLIST}")
    else:
        print("  [ ] LaunchAgent — not found")

    print()
    if not args.purge:
        print("The following will be PRESERVED:")
        for p in REMOVE_PURGE:
            try:
                rel = p.relative_to(APEX_ROOT)
            except ValueError:
                rel = p
            print(f"  [ ] {rel}")
        print()
        print("  To also remove preserved data, re-run with: --purge")
        print()

    if not existing and not LAUNCHD_PLIST.exists():
        print("Nothing to remove. Apex does not appear to be installed.")
        return 0

    if not args.yes:
        if not _confirm("Proceed?"):
            print("\nCancelled.")
            return 1

    print()
    print("Stopping server…")
    _stop_server()

    print("Removing files…")
    errors = []
    for path in remove_list:
        ok, msg = _remove(path)
        print(msg)
        if not ok:
            errors.append(msg)

    _remove_launchd()

    print()
    if errors:
        print(f"Completed with {len(errors)} error(s). Apex may be partially removed.")
        for e in errors:
            print(f"  {e}")
        return 2

    print("Apex removed successfully.")
    print()
    print("Note: The Apex repo directory itself was NOT deleted.")
    print(f"  To fully remove: rm -rf {APEX_ROOT}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
