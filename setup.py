#!/opt/homebrew/bin/python3
"""Apex Setup Wizard — main orchestrator.

Entry point for first-run onboarding and reconfiguration.

Usage:
    python3 setup.py              Full interactive wizard
    python3 setup.py --fast       Quick setup (certs only, skip knowledge)
    python3 setup.py --add-knowledge   Re-run knowledge ingestion (Phase 3)
    python3 setup.py --update-keys     Re-run model connection (Phase 2)
    python3 setup.py --regen-certs     Regenerate TLS certificates
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sqlite3
import subprocess
import ssl
import sys
import tempfile
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

APEX_ROOT = Path(__file__).resolve().parent
STATE_DIR = APEX_ROOT / "state"
SERVER_SCRIPT = APEX_ROOT / "server" / "apex.py"
DISCOVERY_PROMPTS_PATH = STATE_DIR / "discovery_prompts.json"
DB_PATH = STATE_DIR / "apex.db"

# Credential directory: ~/.apex on macOS, ~/.config/apex on Linux
if platform.system() == "Darwin":
    ENV_DIR = Path.home() / ".openclaw"
else:
    ENV_DIR = Path.home() / ".config" / "apex"


# ---------------------------------------------------------------------------
# Lazy imports from setup package (delay until needed for fast --help)
# ---------------------------------------------------------------------------

def _setup_imports():
    """Import setup package modules. Called after argument parsing."""
    global print_header, print_step, print_success, print_warning, print_error
    global print_info, print_table, prompt_choice, prompt_yes_no, prompt_text
    global load_progress, phase_completed, mark_phase_completed, save_progress
    global run_bootstrap, run_models_setup, run_knowledge_ingestion

    from setup.ui import (
        print_header,
        print_step,
        print_success,
        print_warning,
        print_error,
        print_info,
        print_table,
        prompt_choice,
        prompt_yes_no,
        prompt_text,
    )
    from setup.progress import (
        load_progress,
        phase_completed,
        mark_phase_completed,
        save_progress,
    )
    from setup.bootstrap import run_bootstrap
    from setup.models import run_models_setup
    from setup.ingest import run_knowledge_ingestion


# ---------------------------------------------------------------------------
# Discovery prompts
# ---------------------------------------------------------------------------

DISCOVERY_PROMPTS = {
    "version": 1,
    "shown": False,
    "categories": [
        {
            "name": "Get to know me",
            "prompts": [
                {
                    "label": "Import my ChatGPT history",
                    "prompt": (
                        "Help me import my ChatGPT conversation history. Walk me "
                        "through exporting from chat.openai.com and then parse the "
                        "export to learn about my interests, projects, and how I work."
                    ),
                },
                {
                    "label": "Import my Claude history",
                    "prompt": (
                        "Scan my Claude Code conversation history at ~/.claude/projects/ "
                        "and index the transcripts. Summarize what you learn about my "
                        "work patterns and create memory files."
                    ),
                },
                {
                    "label": "Import my Grok history",
                    "prompt": (
                        "Help me import my Grok/xAI conversation history. Walk me "
                        "through the export process and create memory files from "
                        "what you learn."
                    ),
                },
                {
                    "label": "Scan my notes",
                    "prompt": (
                        "I'd like you to scan a folder of my notes (Obsidian, Notion "
                        "export, Apple Notes, or plain markdown). Ask me where the "
                        "folder is, then read through it and create memory files about "
                        "my interests and knowledge."
                    ),
                },
                {
                    "label": "Learn from my emails",
                    "prompt": (
                        "I'd like you to learn about my work from my recent emails. "
                        "This is read-only \u2014 just to understand my projects and "
                        "contacts. Walk me through connecting safely."
                    ),
                },
                {
                    "label": "Learn about me from X/Twitter",
                    "prompt": (
                        "I'd like you to learn about me from my X/Twitter profile. "
                        "Ask me for my handle, then read my recent posts, likes, and "
                        "who I follow to understand my interests, expertise, and "
                        "communication style. Create a user profile memory file. "
                        "Note: this only reads PUBLIC profile data."
                    ),
                },
                {
                    "label": "Learn about me from GitHub",
                    "prompt": (
                        "Learn about me from my GitHub profile. Ask for my username, "
                        "then look at my repositories, starred repos, contribution "
                        "patterns, and languages to understand my technical interests "
                        "and expertise. Create a user profile memory file."
                    ),
                },
                {
                    "label": "Learn about me from LinkedIn",
                    "prompt": (
                        "I'd like you to learn about my professional background from "
                        "LinkedIn. Since LinkedIn doesn't have a public API, walk me "
                        "through exporting my profile as a PDF, then parse it to "
                        "understand my career history, skills, and industry focus. "
                        "Create a user profile memory file."
                    ),
                },
            ],
        },
        {
            "name": "Connect your tools",
            "prompts": [
                {
                    "label": "Set up calendar integration",
                    "prompt": (
                        "Help me connect my calendar (Google Calendar or Apple Calendar) "
                        "so you can be schedule-aware. Start with read-only access."
                    ),
                },
                {
                    "label": "Connect to GitHub",
                    "prompt": (
                        "Help me connect to my GitHub repositories so you can read "
                        "issues, PRs, and code. Walk me through setting up a personal "
                        "access token safely."
                    ),
                },
                {
                    "label": "Set up Slack notifications",
                    "prompt": (
                        "Help me set up Slack webhook integration for receiving alerts "
                        "and notifications from Apex."
                    ),
                },
                {
                    "label": "Connect project management",
                    "prompt": (
                        "Help me connect to my project management tool (Jira, Linear, "
                        "GitHub Issues, or Notion) for read-only access to tickets "
                        "and tasks."
                    ),
                },
            ],
        },
        {
            "name": "Customize your AI",
            "prompts": [
                {
                    "label": "Learn my coding style",
                    "prompt": (
                        "Analyze my recent git commits to learn my coding style, naming "
                        "conventions, and patterns. Run git log --author on my repos and "
                        "create a coding style memory."
                    ),
                },
                {
                    "label": "Learn my writing style",
                    "prompt": (
                        "I'll point you at some of my writing (docs, blog posts, emails). "
                        "Analyze my style and create a writing style memory so you can "
                        "match my voice."
                    ),
                },
                {
                    "label": "Set up daily briefing",
                    "prompt": (
                        "Help me set up an automated daily briefing that summarizes my "
                        "calendar, alerts, and project status each morning."
                    ),
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Discovery prompts writer
# ---------------------------------------------------------------------------

def _write_discovery_prompts() -> None:
    """Write discovery_prompts.json to state/ with atomic write."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(STATE_DIR), suffix=".tmp", prefix=".discovery_prompts_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(DISCOVERY_PROMPTS, f, indent=2)
            f.write("\n")
        os.replace(tmp, str(DISCOVERY_PROMPTS_PATH))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Welcome chat pre-seeding
# ---------------------------------------------------------------------------

def _preseed_welcome_chat(db_path: Path, ingested_summary: str) -> None:
    """Create a welcome chat with discovery prompts in the SQLite database.

    If the database or tables don't exist yet, creates the schema first.
    Skips silently if a welcome chat already exists.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        # Ensure tables exist (server may not have run yet)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT,
                claude_session_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL REFERENCES chats(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                tool_events TEXT DEFAULT '[]',
                thinking TEXT DEFAULT '',
                cost_usd REAL DEFAULT 0,
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
        """)

        # Add model and type columns if missing (matches server migration)
        for col, default in [("model", "NULL"), ("type", "'chat'")]:
            try:
                conn.execute(
                    f"ALTER TABLE chats ADD COLUMN {col} TEXT DEFAULT {default}"
                )
            except Exception:
                pass

        # Add category column if missing
        try:
            conn.execute(
                "ALTER TABLE chats ADD COLUMN category TEXT DEFAULT NULL"
            )
        except Exception:
            pass

        # Check if a welcome chat already exists
        row = conn.execute(
            "SELECT id FROM chats WHERE type = 'chat' AND title = 'Welcome to Apex' LIMIT 1"
        ).fetchone()
        if row:
            return  # already seeded

        # Generate IDs matching the existing format
        chat_id = str(uuid.uuid4())[:8] + str(uuid.uuid4())[9:13]
        msg_id = str(uuid.uuid4())[:8] + str(uuid.uuid4())[9:13]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        welcome_msg = (
            "Welcome to Apex. I have access to your workspace and know about "
            "your projects.\n\n"
            f"{ingested_summary}\n\n"
            "I can help you do more \u2014 try one of the suggestions below, "
            "or just start chatting."
        )

        conn.execute(
            "INSERT INTO chats (id, title, type, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (chat_id, "Welcome to Apex", "chat", now, now),
        )
        conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (msg_id, chat_id, "assistant", welcome_msg, now),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Server launch helpers
# ---------------------------------------------------------------------------

def _build_server_env(bootstrap_result: dict) -> dict[str, str]:
    """Build environment variables for the server subprocess."""
    env = os.environ.copy()
    ssl_dir = STATE_DIR / "ssl"

    env["APEX_ROOT"] = str(APEX_ROOT)
    env["APEX_SSL_CERT"] = str(ssl_dir / "apex.crt")
    env["APEX_SSL_KEY"] = str(ssl_dir / "apex.key")
    env["APEX_SSL_CA"] = str(ssl_dir / "ca.crt")

    # Pull workspace and permission mode from bootstrap result or config
    if bootstrap_result.get("workspace"):
        env["APEX_WORKSPACE"] = str(bootstrap_result["workspace"])
    if bootstrap_result.get("permission_mode"):
        env["APEX_PERMISSION_MODE"] = bootstrap_result["permission_mode"]

    # Load .env file for API keys
    env_file = ENV_DIR / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if key and key not in env:
                        env[key] = value
        except OSError:
            pass

    return env


def _read_config() -> dict:
    """Read state/config.json, return empty dict on failure."""
    config_path = STATE_DIR / "config.json"
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _get_port() -> int:
    """Get the configured server port."""
    config = _read_config()
    return config.get("server", {}).get("port", 8300)


def _wait_for_server(port: int, timeout: int = 30) -> bool:
    """Poll the server health endpoint until ready or timeout.

    Uses HTTPS with SSL verification disabled (self-signed certs).
    Returns True if the server responded successfully.
    """
    url = f"https://localhost:{port}/health"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = Request(url)
            with urlopen(req, timeout=3, context=ctx) as resp:
                if resp.status == 200:
                    return True
        except (URLError, OSError, ConnectionError):
            pass
        time.sleep(1)
    return False


def _launch_server(env: dict[str, str]) -> None:
    """Start the server as a subprocess, wait for readiness, open browser."""
    port = _get_port()
    ssl_dir = STATE_DIR / "ssl"

    print_info("Starting Apex server...")
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_SCRIPT)],
        env=env,
        stdout=subprocess.DEVNULL if not os.environ.get("APEX_DEBUG") else None,
        stderr=subprocess.DEVNULL if not os.environ.get("APEX_DEBUG") else None,
    )

    print_info(f"Waiting for server on port {port}...")
    if _wait_for_server(port):
        print_success(f"Server is ready.")
    else:
        print_warning("Server did not respond within 30 seconds.")
        print_info("It may still be starting. Check the logs if issues persist.")

    # Open browser
    url = f"https://localhost:{port}"
    try:
        webbrowser.open(url)
        print_success(f"Opened {url} in your browser.")
    except Exception:
        print_info(f"Open this URL in your browser: {url}")

    # Connection info
    print()
    print_header("Connection Info")
    print_table(
        ["Setting", "Value"],
        [
            ["URL", url],
            ["CA Certificate", str(ssl_dir / "ca.crt")],
            ["Client .p12", str(ssl_dir / "client.p12")],
            ["Server logs", str(STATE_DIR / "apex.log")],
        ],
    )

    p12_password = _get_p12_password()
    if p12_password:
        print_info(f".p12 install password: {p12_password}")
        print_info(
            "Install the .p12 on your device to connect from phones/tablets."
        )
    print()

    print_success("Press Ctrl+C to stop the server.")
    print()

    # Wait for the server process, forwarding KeyboardInterrupt
    try:
        proc.wait()
    except KeyboardInterrupt:
        print()
        print_info("Shutting down server...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print_success("Server stopped.")


def _get_p12_password() -> str:
    """Retrieve the .p12 password from setup progress, or empty string."""
    progress = load_progress(STATE_DIR)
    return progress.get("phases", {}).get("bootstrap", {}).get("p12_password", "")


# ---------------------------------------------------------------------------
# Ingestion summary builder
# ---------------------------------------------------------------------------

def _build_ingestion_summary(knowledge_result: dict) -> str:
    """Build a human-readable summary of what was ingested."""
    if not knowledge_result or knowledge_result.get("skipped"):
        return "I have basic access to your workspace. Run /add-knowledge to teach me more."

    parts: list[str] = []
    files = knowledge_result.get("files_written", 0)
    if files:
        parts.append(f"I scanned your workspace and generated {files} knowledge files.")

    embed = knowledge_result.get("embedding_stats", {})
    if embed and not embed.get("skipped"):
        indexed = embed.get("indexed", 0)
        if indexed:
            parts.append(f"Indexed {indexed} files for semantic search.")

    if not parts:
        return "Setup is complete. Start chatting to explore what I can do."

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Phase runners (used by menu and CLI flags)
# ---------------------------------------------------------------------------

def _run_phase_bootstrap(fast: bool = False) -> dict:
    """Run Phase 1: Bootstrap."""
    return run_bootstrap(APEX_ROOT)


def _run_phase_models() -> dict:
    """Run Phase 2: Model connections."""
    return run_models_setup(APEX_ROOT, ENV_DIR)


def _run_phase_knowledge() -> dict:
    """Run Phase 3: Knowledge ingestion."""
    config = _read_config()
    workspace = Path(
        config.get("workspace", {}).get("path", "")
        or os.environ.get("APEX_WORKSPACE", "")
        or str(Path.cwd())
    )
    permission_mode = (
        config.get("models", {}).get("permission_mode", "")
        or os.environ.get("APEX_PERMISSION_MODE", "acceptEdits")
    )
    return run_knowledge_ingestion(APEX_ROOT, workspace, permission_mode)


def _run_phase_launch(
    bootstrap_result: dict,
    knowledge_result: dict | None = None,
) -> None:
    """Run Phase 4: Write discovery prompts, pre-seed welcome chat, launch."""
    print_header("Phase 4: Launch")

    # Write discovery prompts
    print_step(1, "Writing discovery prompts")
    try:
        _write_discovery_prompts()
        print_success(f"Wrote {DISCOVERY_PROMPTS_PATH}")
    except Exception as exc:
        print_warning(f"Could not write discovery prompts: {exc}")

    # Pre-seed welcome chat
    print_step(2, "Creating welcome chat")
    summary_text = _build_ingestion_summary(knowledge_result)
    try:
        _preseed_welcome_chat(DB_PATH, summary_text)
        print_success("Welcome chat created.")
    except Exception as exc:
        print_warning(f"Could not create welcome chat: {exc}")

    # Mark setup complete
    print_step(3, "Finalizing setup")
    try:
        mark_phase_completed(STATE_DIR, "launch")
        mark_phase_completed(
            STATE_DIR,
            "setup_complete",
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )
        print_success("Setup marked as complete.")
    except Exception as exc:
        print_warning(f"Could not update progress: {exc}")

    # Launch server
    print()
    print_step(4, "Starting server")
    env = _build_server_env(bootstrap_result)
    _launch_server(env)


def _regen_certs() -> dict:
    """Regenerate certificates using the bootstrap cert generator."""
    from setup.bootstrap import detect_local_ips, generate_certificates

    print_header("Regenerate TLS Certificates")

    ip_entries = detect_local_ips()
    all_ips = [e["ip"] for e in ip_entries]

    if prompt_yes_no("Add additional IPs or hostnames?", default=False):
        extra = prompt_text(
            "Additional SANs (comma-separated)", required=False
        )
        if extra:
            import socket
            for part in extra.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    socket.inet_aton(part)
                    all_ips.append(part)
                except OSError:
                    pass

    dns_names = ["localhost"]
    if prompt_yes_no("Add a custom DNS name?", default=False):
        extra_dns = prompt_text("DNS names (comma-separated)", required=False)
        if extra_dns:
            for part in extra_dns.split(","):
                part = part.strip()
                if part and part not in dns_names:
                    dns_names.append(part)

    cert_info = generate_certificates(STATE_DIR, all_ips, dns_names)
    print()
    print_success("Certificates regenerated successfully.")
    return cert_info


# ---------------------------------------------------------------------------
# Returning-user menu
# ---------------------------------------------------------------------------

def _show_returning_menu() -> None:
    """Show the menu for users who have already completed setup."""
    progress = load_progress(STATE_DIR)
    completed_date = (
        progress.get("phases", {})
        .get("setup_complete", {})
        .get("date", "unknown")
    )

    print_header("Apex Setup")
    print_info(f"Previous setup detected (completed {completed_date}).")
    print()

    choice = prompt_choice(
        "What would you like to do?",
        [
            "Run full setup again",
            "Add more knowledge (re-scan workspace)",
            "Update API keys / model connections",
            "Regenerate certificates",
            "Launch server",
            "Exit",
        ],
        default=5,
    )

    if choice == 0:
        # Full setup
        _run_full_wizard()
    elif choice == 1:
        # Knowledge
        result = _run_phase_knowledge()
        if result and not result.get("skipped"):
            print_success("Knowledge ingestion complete.")
    elif choice == 2:
        # Models
        _run_phase_models()
    elif choice == 3:
        # Regen certs
        _regen_certs()
    elif choice == 4:
        # Launch
        bootstrap_result = _load_bootstrap_result()
        _run_phase_launch(bootstrap_result)
    elif choice == 5:
        print_info("Exiting.")
        return


def _load_bootstrap_result() -> dict:
    """Reconstruct a bootstrap result dict from config and progress."""
    config = _read_config()
    progress = load_progress(STATE_DIR)
    bootstrap = progress.get("phases", {}).get("bootstrap", {})

    return {
        "workspace": (
            config.get("workspace", {}).get("path", "")
            or bootstrap.get("workspace", "")
        ),
        "permission_mode": (
            config.get("models", {}).get("permission_mode", "")
            or bootstrap.get("permission_mode", "acceptEdits")
        ),
        "ips": bootstrap.get("ips", ["127.0.0.1"]),
        "dns_names": bootstrap.get("dns_names", ["localhost"]),
    }


# ---------------------------------------------------------------------------
# Full wizard
# ---------------------------------------------------------------------------

def _run_full_wizard(fast: bool = False) -> None:
    """Run the complete setup wizard (fast or full path)."""
    print_header("Apex Setup")

    if fast:
        path = "quick"
    else:
        print_info("  Quick start (fastest):")
        print_info("    Generates TLS certificates and launches the server.")
        print_info("    Time: ~30 seconds")
        print()
        print_info("  Full setup (recommended):")
        print_info(
            "    Configure models, scan your workspace, build AI knowledge."
        )
        print_info("    Time: ~5 minutes")
        print()

        raw = prompt_text("Choose [Q]uick / [F]ull", default="F").strip().upper()
        if raw.startswith("Q"):
            path = "quick"
        else:
            path = "full"

    # --- Phase 1: Bootstrap (always runs) ---
    bootstrap_result = _run_phase_bootstrap()
    if bootstrap_result.get("error"):
        print_error(
            "Bootstrap failed. Fix the issues above and try again."
        )
        if _offer_retry("Phase 1: Bootstrap"):
            bootstrap_result = _run_phase_bootstrap()
            if bootstrap_result.get("error"):
                print_error("Bootstrap failed again. Exiting.")
                sys.exit(1)
        else:
            sys.exit(1)

    if bootstrap_result.get("skipped"):
        # User declined re-run; load existing results
        bootstrap_result = _load_bootstrap_result()

    if path == "quick":
        # Fast path: skip Phases 2 and 3, go straight to launch
        _run_phase_launch(bootstrap_result)
        return

    # --- Phase 2: Models ---
    models_result = _run_phase_models()
    if models_result is None:
        print_warning("Model setup returned no results.")
    try:
        mark_phase_completed(STATE_DIR, "models")
    except Exception:
        pass

    # --- Phase 3: Knowledge ---
    knowledge_result = _run_phase_knowledge()
    try:
        mark_phase_completed(STATE_DIR, "knowledge")
    except Exception:
        pass

    # --- Phase 4: Launch ---
    _run_phase_launch(bootstrap_result, knowledge_result)


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _offer_retry(phase_name: str) -> bool:
    """Ask the user if they want to retry a failed phase."""
    print()
    return prompt_yes_no(f"Retry {phase_name}?", default=True)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apex Setup Wizard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 setup.py              Run the full interactive wizard\n"
            "  python3 setup.py --fast        Quick setup (certs + launch)\n"
            "  python3 setup.py --add-knowledge  Re-scan workspace\n"
            "  python3 setup.py --update-keys    Re-configure API keys\n"
            "  python3 setup.py --regen-certs    Regenerate TLS certificates\n"
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--fast",
        action="store_true",
        help="Quick setup: generate certificates and launch (skip knowledge)",
    )
    group.add_argument(
        "--add-knowledge",
        action="store_true",
        help="Re-run knowledge ingestion (Phase 3 only)",
    )
    group.add_argument(
        "--update-keys",
        action="store_true",
        help="Re-run model/API key configuration (Phase 2 only)",
    )
    group.add_argument(
        "--regen-certs",
        action="store_true",
        help="Regenerate TLS certificates",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry point with top-level error handling."""
    args = _parse_args()

    # Import setup package
    _setup_imports()

    # Dispatch based on flags
    if args.add_knowledge:
        result = _run_phase_knowledge()
        if result and not result.get("skipped"):
            print_success("Knowledge ingestion complete.")
        return

    if args.update_keys:
        _run_phase_models()
        return

    if args.regen_certs:
        _regen_certs()
        return

    # Check for previous setup
    if phase_completed(STATE_DIR, "setup_complete") and not args.fast:
        _show_returning_menu()
        return

    # First-time or --fast: run the wizard
    _run_full_wizard(fast=args.fast)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Setup cancelled.\n")
        sys.exit(130)
    except Exception as exc:
        debug = os.environ.get("APEX_DEBUG", "").lower() in {"1", "true", "yes"}
        if debug:
            import traceback
            traceback.print_exc()
        else:
            print(f"\n  Setup error: {exc}\n", file=sys.stderr)
            print(
                "  Set APEX_DEBUG=1 and run again for full traceback.\n",
                file=sys.stderr,
            )
        sys.exit(1)
