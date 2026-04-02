#!/usr/bin/env python3
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
# Python version guard
# ---------------------------------------------------------------------------
if sys.version_info < (3, 10):
    _ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"\n  ✗  Python 3.10+ is required, but you are running Python {_ver}.")
    print(f"     ({sys.executable})\n")
    if sys.platform == "darwin":
        print("  On macOS, run the installer instead — it handles Python automatically:\n")
        print("    Double-click  'Install Apex.command'  in Finder")
        print("    — or —")
        print("    ./install.sh\n")
        print("  To install a newer Python manually:")
        print("    brew install python@3.12   (requires Homebrew)")
        print("    https://www.python.org/downloads/\n")
    else:
        print("  Install Python 3.10+:")
        print("    Ubuntu/Debian:  sudo apt install python3 python3-venv")
        print("    Fedora/RHEL:    sudo dnf install python3\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

APEX_ROOT = Path(__file__).resolve().parent
VENV_DIR = APEX_ROOT / ".venv"
STATE_DIR = APEX_ROOT / "state"
SERVER_SCRIPT = APEX_ROOT / "server" / "apex.py"
DISCOVERY_PROMPTS_PATH = STATE_DIR / "discovery_prompts.json"
DB_PATH = STATE_DIR / "apex.db"

# Credential directory: ~/.apex on macOS, ~/.config/apex on Linux
if platform.system() == "Darwin":
    ENV_DIR = Path(os.environ.get("APEX_ENV_DIR", str(Path.home() / ".apex")))
else:
    ENV_DIR = Path.home() / ".config" / "apex"


# ---------------------------------------------------------------------------
# Virtual environment setup
# ---------------------------------------------------------------------------

def _ensure_venv() -> str:
    """Create a virtual environment and install dependencies.

    Returns the path to the venv Python interpreter.
    If running inside the venv already, returns sys.executable.
    """
    venv_python = VENV_DIR / "bin" / "python3"
    requirements = APEX_ROOT / "requirements.txt"

    # Already inside the venv?
    if sys.prefix != sys.base_prefix:
        return sys.executable

    # Create venv if it doesn't exist
    if not venv_python.exists():
        print("\n  Creating virtual environment...")
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            check=True,
        )
        print(f"  Created: {VENV_DIR}")

    # Install/upgrade dependencies
    if requirements.exists():
        print("  Installing dependencies...")
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-q",
             "--upgrade", "-r", str(requirements)],
            check=True,
        )
        print("  Dependencies installed.")

    return str(venv_python)


def _relaunch_in_venv() -> None:
    """If not already running in the venv, re-exec setup.py inside it."""
    if sys.prefix != sys.base_prefix:
        return  # already in a venv

    venv_python = _ensure_venv()

    # Re-exec this script with the venv Python, forwarding all args
    os.execv(venv_python, [venv_python, __file__] + sys.argv[1:])


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

        # Generate IDs matching the server format (8-char hex)
        chat_id = str(uuid.uuid4())[:8]
        msg_id = str(uuid.uuid4())[:8]
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

    Uses mTLS with the generated client certificate — the server enforces
    CERT_REQUIRED at the TLS layer, so a bare HTTPS connection without a
    client cert is rejected before any HTTP route is reached.
    """
    ssl_dir = STATE_DIR / "ssl"
    url = f"https://localhost:{port}/health"

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # self-signed CA, skip server verify
    # Present our client cert so the mTLS handshake succeeds
    client_crt = ssl_dir / "client.crt"
    client_key = ssl_dir / "client.key"
    if client_crt.exists() and client_key.exists():
        ctx.load_cert_chain(certfile=str(client_crt), keyfile=str(client_key))

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

    # Use venv Python for the server process
    venv_python = str(VENV_DIR / "bin" / "python3") if (VENV_DIR / "bin" / "python3").exists() else sys.executable
    print_info("Starting Apex server...")
    proc = subprocess.Popen(
        [venv_python, str(SERVER_SCRIPT)],
        env=env,
        stdout=subprocess.DEVNULL if not os.environ.get("APEX_DEBUG") else None,
        stderr=subprocess.DEVNULL if not os.environ.get("APEX_DEBUG") else None,
    )

    print_info(f"Waiting for server on port {port}...")
    if _wait_for_server(port):
        print_success("Server is ready.")
    else:
        print_warning("Server did not respond within 30 seconds.")
        print_info("It may still be starting. Check the logs if issues persist.")

    url = f"https://localhost:{port}"

    # Connection info — shown BEFORE browser open so user knows what to do
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

    print()
    # Auto-install certs on macOS; show manual instructions as fallback
    if platform.system() == "Darwin":
        _auto_trust_certs_macos()
        print()
        print_info(
            "If your browser still shows a certificate warning:\n"
            f"  • CA cert:     double-click {ssl_dir / 'ca.crt'} → Always Trust\n"
            f"  • Client cert: double-click {ssl_dir / 'client.p12'}"
            + (f" (password: {p12_password})" if p12_password else "")
        )
    else:
        print_warning(
            "IMPORTANT: Apex uses mutual TLS — your browser will not load the\n"
            "page until you install the client certificate (.p12 file)."
        )
        if p12_password:
            print_info(f".p12 install password: {p12_password}")
        print_info(
            f"  Linux:  Import {ssl_dir / 'client.p12'} into your browser's\n"
            f"          certificate manager (Settings → Privacy & Security → Certificates)."
        )

    print_info(
        "For phones/tablets: transfer the .p12 file and install it in\n"
        "  iOS:    Settings → Profile Downloaded → Install\n"
        "  Android: Settings → Security → Install certificates"
    )
    print()

    # Open /setup on first run, / if already set up
    setup_url = url + ("/setup" if not phase_completed(STATE_DIR, "setup_complete") else "")
    try:
        webbrowser.open(setup_url)
        print_success(f"Opened {setup_url} in your browser.")
        if not phase_completed(STATE_DIR, "setup_complete"):
            print_info("Complete setup in your browser — this terminal window can stay open.")
    except Exception:
        print_info(f"Open this URL in your browser: {setup_url}")
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


def _auto_trust_certs_macos() -> None:
    """Automatically add CA + client cert to macOS login keychain.

    - Trusts the CA so the browser stops showing security warnings.
    - Imports the client .p12 so Chrome/Safari can present it for mTLS.

    Requires sudo for add-trusted-cert (prompts the user once via macOS
    system dialog). Skips silently on non-macOS or if files are missing.
    """
    if platform.system() != "Darwin":
        return

    ssl_dir = STATE_DIR / "ssl"
    ca_crt   = ssl_dir / "ca.crt"
    client_p12 = ssl_dir / "client.p12"

    if not ca_crt.exists() or not client_p12.exists():
        return

    login_kc = str(Path.home() / "Library/Keychains/login.keychain-db")
    p12_password = _get_p12_password()

    print_info("Installing certificates into macOS keychain (you may be prompted for your Mac password)...")

    # 1. Trust the CA — requires sudo, macOS shows a system auth dialog
    try:
        result = subprocess.run(
            ["sudo", "security", "add-trusted-cert", "-d", "-r", "trustRoot",
             "-k", "/Library/Keychains/System.keychain", str(ca_crt)],
            timeout=60,
        )
        if result.returncode == 0:
            print_success("CA certificate trusted system-wide.")
        else:
            print_warning("Could not auto-trust CA. Install manually: double-click ca.crt → Always Trust.")
    except Exception as e:
        print_warning(f"CA trust step skipped: {e}")

    # 2. Import client .p12 into login keychain (no sudo needed)
    try:
        cmd = [
            "security", "import", str(client_p12),
            "-k", login_kc,
            "-T", "/usr/bin/security",  # allow security to use it without prompting
        ]
        if p12_password:
            cmd += ["-P", p12_password]
        result = subprocess.run(cmd, timeout=30, capture_output=True)
        if result.returncode == 0:
            print_success("Client certificate imported into login keychain.")
        elif b"already exists" in (result.stderr or b""):
            print_success("Client certificate already in keychain.")
        else:
            print_warning("Could not auto-import .p12. Install manually: double-click client.p12.")
    except Exception as e:
        print_warning(f"Client cert import skipped: {e}")


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
    _ws_raw = (
        config.get("workspace", {}).get("path", "")
        or os.environ.get("APEX_WORKSPACE", "")
        or str(Path.cwd())
    )
    workspace = Path(_ws_raw.split(":")[0].strip() or str(Path.cwd()))
    permission_mode = (
        config.get("models", {}).get("permission_mode", "")
        or os.environ.get("APEX_PERMISSION_MODE", "acceptEdits")
    )
    return run_knowledge_ingestion(APEX_ROOT, workspace, permission_mode)


def _run_phase_launch(bootstrap_result: dict) -> None:
    """Start the server and open the browser setup wizard."""
    print_header("Starting Apex")

    try:
        mark_phase_completed(STATE_DIR, "launch")
    except Exception:
        pass

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


def _encrypt_existing_keys() -> None:
    """Encrypt any plaintext private keys in state/ssl/."""
    from setup.ssl_keystore import migrate_plaintext_keys

    print_header("Encrypt Private Keys")

    ssl_dir = STATE_DIR / "ssl"
    if not ssl_dir.exists():
        print_error("No ssl directory found. Run setup first.")
        return

    result = migrate_plaintext_keys(ssl_dir)
    if result.get("skipped"):
        print_info(result.get("reason", "Nothing to do."))
        return

    migrated = result.get("migrated", 0)
    if migrated:
        print_success(f"Encrypted {migrated} key(s): {', '.join(result.get('encrypted', []))}")
        print_info("Passphrase stored in macOS Keychain (service: apex-ssl).")

    errors = result.get("errors")
    if errors:
        for err in errors:
            print_error(err)


def _setup_letsencrypt() -> None:
    """Launch the Let's Encrypt setup script."""
    le_script = APEX_ROOT / "scripts" / "letsencrypt" / "setup_le.sh"
    if not le_script.exists():
        print_error(f"Let's Encrypt setup script not found: {le_script}")
        return

    print_header("Let's Encrypt Setup")
    print_info("This will request a trusted certificate via Cloudflare DNS-01.")
    print_info("Prerequisites:")
    print_info("  1. Domain added to Cloudflare (free tier)")
    print_info("  2. Nameservers updated at your registrar")
    print_info("  3. A record: apex.<domain> -> your server IP (DNS only)")
    print_info("  4. Cloudflare API token (Edit zone DNS)")
    print()

    try:
        subprocess.run(["bash", str(le_script)], check=True)
    except subprocess.CalledProcessError:
        print_error("Let's Encrypt setup failed. Check the output above.")
    except KeyboardInterrupt:
        print()
        print_info("Setup cancelled.")


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
    """Run the setup wizard.

    Terminal handles Phase 1 (certs + dirs + server start) only.
    Phases 2-4 (models, workspace, knowledge, welcome seed) have moved
    to the browser wizard at /setup.
    """
    print_header("Apex Setup")

    # --- Phase 1: Bootstrap (certs + dirs) ---
    bootstrap_result = _run_phase_bootstrap()
    if bootstrap_result.get("error"):
        print_error("Bootstrap failed. Fix the issues above and try again.")
        if _offer_retry("Phase 1: Bootstrap"):
            bootstrap_result = _run_phase_bootstrap()
            if bootstrap_result.get("error"):
                print_error("Bootstrap failed again. Exiting.")
                sys.exit(1)
        else:
            sys.exit(1)

    if bootstrap_result.get("skipped"):
        bootstrap_result = _load_bootstrap_result()

    # --- Launch server + hand off to browser wizard ---
    _run_phase_launch(bootstrap_result)


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
            "  python3 setup.py --encrypt-keys   Encrypt existing private keys at rest\n"
            "  python3 setup.py --setup-letsencrypt  Set up Let's Encrypt (Cloudflare DNS)\n"
            "\n"
            "  apex                              Start the server (if setup complete)\n"
            "  apex --setup                      Show setup/config menu\n"
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
    group.add_argument(
        "--encrypt-keys",
        action="store_true",
        help="Encrypt existing plaintext private keys at rest",
    )
    group.add_argument(
        "--setup-letsencrypt",
        action="store_true",
        help="Set up Let's Encrypt certificate via Cloudflare DNS-01",
    )
    group.add_argument(
        "--setup",
        action="store_true",
        help="Show setup/config menu (re-run setup, update keys, regen certs)",
    )
    group.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove Apex (preserves memory/transcripts unless --purge)",
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Used with --uninstall: also remove backups and user data",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _ensure_cli_wrapper() -> None:
    """Create the `apex` CLI wrapper in .venv/bin/ if it doesn't exist."""
    wrapper = APEX_ROOT / ".venv" / "bin" / "apex"
    if wrapper.exists():
        return
    try:
        wrapper.write_text(
            f"#!/usr/bin/env bash\n"
            f"# Apex CLI — generated by setup.py\n"
            f'APEX_ROOT="{APEX_ROOT}"\n'
            f'exec "$APEX_ROOT/.venv/bin/python3" "$APEX_ROOT/setup.py" "$@"\n'
        )
        wrapper.chmod(0o755)
    except Exception:
        pass  # non-critical — user can always run setup.py directly


def main() -> None:
    """Main entry point with top-level error handling."""
    args = _parse_args()

    # Ensure we're running inside the venv (creates it if needed, re-execs)
    _relaunch_in_venv()

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

    if args.encrypt_keys:
        _encrypt_existing_keys()
        return

    if args.setup_letsencrypt:
        _setup_letsencrypt()
        return

    if args.uninstall:
        import subprocess as _sp
        cmd = [sys.executable, str(APEX_ROOT / "scripts" / "uninstall.py")]
        if args.purge:
            cmd.append("--purge")
        raise SystemExit(_sp.call(cmd))

    if args.setup:
        _show_returning_menu()
        return

    # Setup already complete + no flags = launch the server
    if phase_completed(STATE_DIR, "setup_complete") and not args.fast:
        bootstrap_result = _load_bootstrap_result()
        _run_phase_launch(bootstrap_result)
        return

    # First-time or --fast: run the wizard
    _run_full_wizard(fast=args.fast)

    # Ensure `apex` CLI wrapper exists in .venv/bin/
    _ensure_cli_wrapper()


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        print(
            f"\n  Apex requires Python 3.10 or later.\n"
            f"  You are running Python {sys.version.split()[0]}.\n",
            file=sys.stderr,
        )
        sys.exit(1)
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
