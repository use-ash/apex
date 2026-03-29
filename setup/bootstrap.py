#!/usr/bin/env python3
"""Phase 1: Bootstrap — get the Apex server runnable.

Checks dependencies, creates directories, detects network interfaces,
generates TLS certificates, selects workspace, and writes initial config.
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import secrets
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from setup.progress import mark_phase_completed, phase_completed
from setup.ui import (
    clear_line,
    print_error,
    print_header,
    print_info,
    print_progress,
    print_step,
    print_success,
    print_table,
    print_warning,
    prompt_choice,
    prompt_confirm,
    prompt_text,
    prompt_yes_no,
)

# ---------------------------------------------------------------------------
# Dependency checking
# ---------------------------------------------------------------------------

# Required packages — server will not start without these
_REQUIRED_PACKAGES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "claude_agent_sdk": "claude-agent-sdk",
}

# Optional packages — enhance functionality but not required
_OPTIONAL_PACKAGES = {
    "numpy": "numpy",
    "google.genai": "google-genai",
}


def check_dependencies() -> dict[str, bool]:
    """Check for required and optional Python packages.

    Returns a dict mapping package import names to availability bools.
    If any required packages are missing, offers to install them.
    """
    results: dict[str, bool] = {}

    print_step(1, "Checking Python dependencies")
    print_info(f"Python: {sys.executable} ({platform.python_version()})")
    print()

    # Check required
    missing_required: list[str] = []
    for import_name, pip_name in _REQUIRED_PACKAGES.items():
        try:
            importlib.import_module(import_name)
            results[import_name] = True
            print_success(f"{import_name}")
        except ImportError:
            results[import_name] = False
            missing_required.append(pip_name)
            print_error(f"{import_name} — not installed")

    # Check optional
    for import_name, pip_name in _OPTIONAL_PACKAGES.items():
        try:
            importlib.import_module(import_name)
            results[import_name] = True
            print_success(f"{import_name} (optional)")
        except ImportError:
            results[import_name] = False
            print_warning(f"{import_name} — not installed (optional)")

    # Offer to install missing required packages
    if missing_required:
        print()
        names = ", ".join(missing_required)
        if prompt_yes_no(f"Install missing required packages ({names})?"):
            cmd = [sys.executable, "-m", "pip", "install"] + missing_required
            print_info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print_success("Packages installed successfully")
                # Re-check after install
                for import_name, pip_name in _REQUIRED_PACKAGES.items():
                    if pip_name in missing_required:
                        try:
                            importlib.import_module(import_name)
                            results[import_name] = True
                        except ImportError:
                            results[import_name] = False
            else:
                print_error("pip install failed:")
                for line in result.stderr.strip().splitlines()[-5:]:
                    print_info(line)
        else:
            print_warning("Skipped. The server will not start without these packages.")

    return results


# ---------------------------------------------------------------------------
# Directory initialization
# ---------------------------------------------------------------------------


def init_state_dirs(apex_root: Path) -> None:
    """Create required state and credential directories.

    State dirs under apex_root:
        state/, state/ssl/, state/uploads/, state/embeddings/

    Credential dir:
        ~/.apex/ on macOS, ~/.config/apex/ on Linux
    """
    print_step(2, "Creating directories")

    state_dir = apex_root / "state"
    dirs = [
        state_dir,
        state_dir / "ssl",
        state_dir / "uploads",
        state_dir / "embeddings",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print_success(str(d))

    # Credential directory
    if platform.system() == "Darwin":
        cred_dir = Path.home() / ".apex"
    else:
        cred_dir = Path.home() / ".config" / "apex"

    cred_dir.mkdir(parents=True, exist_ok=True)
    print_success(f"{cred_dir} (credentials)")


# ---------------------------------------------------------------------------
# Network detection
# ---------------------------------------------------------------------------


def detect_local_ips() -> list[dict]:
    """Detect local IP addresses for certificate SANs.

    Returns a list of dicts with keys: ip, interface, description.
    Always includes 127.0.0.1 (localhost).
    """
    print_step(3, "Detecting network interfaces")

    found: list[dict] = [
        {"ip": "127.0.0.1", "interface": "lo0", "description": "Loopback"},
    ]
    seen = {"127.0.0.1"}

    system = platform.system()

    if system == "Darwin":
        found.extend(_detect_ips_macos(seen))
    elif system == "Linux":
        found.extend(_detect_ips_linux(seen))

    # Fallback: socket-based detection for primary IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Connect to a public address to determine the default route IP.
            # No data is actually sent.
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip not in seen:
                found.append({"ip": ip, "interface": "default", "description": "Default route"})
                seen.add(ip)
        finally:
            s.close()
    except OSError:
        pass

    # Display results
    headers = ["IP Address", "Interface", "Description"]
    rows = [[e["ip"], e["interface"], e["description"]] for e in found]
    print_table(headers, rows)

    return found


def _detect_ips_macos(seen: set[str]) -> list[dict]:
    """Parse ifconfig output on macOS for en0 (WiFi) and utun (VPN)."""
    results: list[dict] = []
    try:
        output = subprocess.run(
            ["ifconfig"], capture_output=True, text=True, timeout=5
        ).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return results

    current_iface = ""
    for line in output.splitlines():
        # Interface header line: "en0: flags=..."
        if not line.startswith("\t") and ":" in line:
            current_iface = line.split(":")[0].strip()
        # IPv4 line: "\tinet 192.168.1.100 netmask ..."
        elif "inet " in line and "inet6" not in line:
            parts = line.strip().split()
            idx = parts.index("inet") if "inet" in parts else -1
            if idx >= 0 and idx + 1 < len(parts):
                ip = parts[idx + 1]
                if ip not in seen and not ip.startswith("127."):
                    desc = "WiFi" if current_iface.startswith("en") else (
                        "VPN" if current_iface.startswith("utun") else "Network"
                    )
                    results.append({
                        "ip": ip,
                        "interface": current_iface,
                        "description": desc,
                    })
                    seen.add(ip)

    return results


def _detect_ips_linux(seen: set[str]) -> list[dict]:
    """Parse 'ip addr' output on Linux."""
    results: list[dict] = []
    try:
        output = subprocess.run(
            ["ip", "addr"], capture_output=True, text=True, timeout=5
        ).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return results

    current_iface = ""
    for line in output.splitlines():
        stripped = line.strip()
        # Interface line: "2: eth0: <BROADCAST,..."
        if not line.startswith(" ") and ":" in stripped:
            parts = stripped.split(":")
            if len(parts) >= 2:
                current_iface = parts[1].strip()
        # IPv4 line: "    inet 192.168.1.100/24 ..."
        elif stripped.startswith("inet "):
            parts = stripped.split()
            if len(parts) >= 2:
                ip = parts[1].split("/")[0]
                if ip not in seen and not ip.startswith("127."):
                    desc = "Ethernet" if current_iface.startswith("eth") else (
                        "WiFi" if current_iface.startswith("wl") else "Network"
                    )
                    results.append({
                        "ip": ip,
                        "interface": current_iface,
                        "description": desc,
                    })
                    seen.add(ip)

    return results


# ---------------------------------------------------------------------------
# TLS certificate generation
# ---------------------------------------------------------------------------


def generate_certificates(
    state_dir: Path,
    ips: list[str],
    dns_names: list[str],
) -> dict:
    """Generate a full TLS certificate chain for mTLS.

    Generates:
        - CA cert/key (10yr, RSA 2048)
        - Server cert with SANs (825 days)
        - Client cert + .p12 bundle (825 days)

    Parameters
    ----------
    state_dir : Path
        The apex state directory (certs go in state_dir/ssl/).
    ips : list[str]
        IP addresses for server cert SANs.
    dns_names : list[str]
        DNS names for server cert SANs (always includes "localhost").

    Returns
    -------
    dict
        Paths to generated files and the .p12 password.
    """
    print_step(4, "Generating TLS certificates")

    ssl_dir = state_dir / "ssl"
    ssl_dir.mkdir(parents=True, exist_ok=True)

    ca_key = ssl_dir / "ca.key"
    ca_crt = ssl_dir / "ca.crt"
    server_key = ssl_dir / "apex.key"
    server_crt = ssl_dir / "apex.crt"
    ext_cnf = ssl_dir / "ext.cnf"
    client_key = ssl_dir / "client.key"
    client_crt = ssl_dir / "client.crt"
    client_ext_cnf = ssl_dir / "client_ext.cnf"
    client_p12 = ssl_dir / "client.p12"

    p12_password = secrets.token_urlsafe(12)
    total_steps = 7

    # ---- Step 1: Generate CA key ----
    print_progress(1, total_steps, "Generating CA key")
    _run_openssl(["openssl", "genrsa", "-out", str(ca_key), "2048"])

    # ---- Step 2: Generate CA certificate ----
    print_progress(2, total_steps, "Generating CA certificate")
    _run_openssl([
        "openssl", "req", "-x509", "-new", "-nodes",
        "-key", str(ca_key),
        "-sha256", "-days", "3650",
        "-out", str(ca_crt),
        "-subj", "/CN=Apex CA",
    ])

    # ---- Step 3: Write server ext.cnf ----
    print_progress(3, total_steps, "Writing SAN configuration")
    san_parts: list[str] = []
    for ip in ips:
        san_parts.append(f"IP:{ip}")
    for dns in dns_names:
        san_parts.append(f"DNS:{dns}")
    san_string = ",".join(san_parts)

    ext_cnf.write_text(
        f"basicConstraints=CA:FALSE\n"
        f"keyUsage=digitalSignature,keyEncipherment\n"
        f"extendedKeyUsage=serverAuth\n"
        f"subjectAltName={san_string}\n",
        encoding="utf-8",
    )

    client_ext_cnf.write_text(
        "basicConstraints=CA:FALSE\n"
        "keyUsage=digitalSignature\n"
        "extendedKeyUsage=clientAuth\n",
        encoding="utf-8",
    )

    # ---- Step 4: Generate server key ----
    print_progress(4, total_steps, "Generating server key")
    _run_openssl(["openssl", "genrsa", "-out", str(server_key), "2048"])

    # ---- Step 5: Generate server certificate (CSR + sign in pipeline) ----
    print_progress(5, total_steps, "Signing server certificate")
    # Create CSR, pipe to x509 for signing
    csr_proc = subprocess.Popen(
        [
            "openssl", "req", "-new",
            "-key", str(server_key),
            "-subj", "/CN=apex-server",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    sign_result = subprocess.run(
        [
            "openssl", "x509", "-req",
            "-CA", str(ca_crt),
            "-CAkey", str(ca_key),
            "-CAcreateserial",
            "-days", "825",
            "-sha256",
            "-extfile", str(ext_cnf),
            "-out", str(server_crt),
        ],
        stdin=csr_proc.stdout,
        capture_output=True,
        text=True,
        timeout=30,
    )
    csr_proc.wait()
    if sign_result.returncode != 0:
        raise RuntimeError(f"Server cert signing failed: {sign_result.stderr.strip()}")

    # ---- Step 6: Generate client key + cert ----
    print_progress(6, total_steps, "Generating client certificate")
    _run_openssl(["openssl", "genrsa", "-out", str(client_key), "2048"])

    client_csr_proc = subprocess.Popen(
        [
            "openssl", "req", "-new",
            "-key", str(client_key),
            "-subj", "/CN=apex-client",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    client_sign = subprocess.run(
        [
            "openssl", "x509", "-req",
            "-CA", str(ca_crt),
            "-CAkey", str(ca_key),
            "-CAcreateserial",
            "-days", "825",
            "-sha256",
            "-extfile", str(client_ext_cnf),
            "-out", str(client_crt),
        ],
        stdin=client_csr_proc.stdout,
        capture_output=True,
        text=True,
        timeout=30,
    )
    client_csr_proc.wait()
    if client_sign.returncode != 0:
        raise RuntimeError(f"Client cert signing failed: {client_sign.stderr.strip()}")

    # ---- Step 7: Create .p12 bundle ----
    print_progress(7, total_steps, "Creating .p12 bundle")
    _run_openssl([
        "openssl", "pkcs12", "-export",
        "-out", str(client_p12),
        "-inkey", str(client_key),
        "-in", str(client_crt),
        "-certfile", str(ca_crt),
        "-passout", f"pass:{p12_password}",
    ])

    # ---- Set file permissions ----
    for key_file in [ca_key, server_key, client_key]:
        key_file.chmod(0o600)
    for cert_file in [ca_crt, server_crt, client_crt, client_p12]:
        cert_file.chmod(0o644)

    print()
    print_success("CA certificate:     " + str(ca_crt))
    print_success("Server certificate: " + str(server_crt))
    print_success("Client certificate: " + str(client_crt))
    print_success("Client .p12 bundle: " + str(client_p12))
    print_info(f".p12 password: {p12_password}")
    print_info("Save this password — you will need it to install the .p12 on your device.")

    return {
        "ca_crt": str(ca_crt),
        "ca_key": str(ca_key),
        "server_crt": str(server_crt),
        "server_key": str(server_key),
        "client_crt": str(client_crt),
        "client_key": str(client_key),
        "client_p12": str(client_p12),
        "ext_cnf": str(ext_cnf),
        "p12_password": p12_password,
    }


def _run_openssl(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run an openssl command, raising RuntimeError on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"openssl command failed: {' '.join(cmd[:3])}...\n{result.stderr.strip()}"
        )
    return result


# ---------------------------------------------------------------------------
# Workspace selection
# ---------------------------------------------------------------------------


def select_workspace() -> Path:
    """Prompt user for workspace directory.

    Defaults to the current working directory. Validates that the
    selected path exists and is a directory.
    """
    print_step(5, "Select workspace directory")
    print_info("The workspace is the directory the AI agent can access.")
    print_info("It should contain your project files, code, or documents.")

    default = str(Path.cwd())

    while True:
        raw = prompt_text("Workspace path", default=default)
        path = Path(raw).expanduser().resolve()

        if not path.exists():
            print_error(f"Path does not exist: {path}")
            if prompt_yes_no("Create it?", default=False):
                path.mkdir(parents=True, exist_ok=True)
                print_success(f"Created {path}")
                return path
            continue

        if not path.is_dir():
            print_error(f"Not a directory: {path}")
            continue

        print_success(f"Workspace: {path}")
        return path


# ---------------------------------------------------------------------------
# Initial config
# ---------------------------------------------------------------------------


def create_initial_config(
    apex_root: Path,
    workspace: Path,
    permission_mode: str,
    host: str = "127.0.0.1",
) -> None:
    """Write state/config.json with sensible defaults.

    Uses atomic write (temp + rename) to prevent corruption.
    """
    print_step(7, "Writing configuration")

    state_dir = apex_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    config_path = state_dir / "config.json"

    config = {
        "server": {
            "host": host,
            "port": 8300,
            "debug": False,
        },
        "models": {
            "default_model": "claude-sonnet-4-6",
            "permission_mode": permission_mode,
            "ollama_url": "http://localhost:11434",
            "mlx_url": "http://localhost:8400",
            "compaction_threshold": 100000,
            "compaction_model": "grok-4-1-fast-non-reasoning",
            "compaction_ollama_fallback": "gemma3:27b",
            "sdk_query_timeout": 30,
            "sdk_stream_timeout": 300,
            "enable_skill_dispatch": True,
            "max_turns": 50,
        },
        "workspace": {
            "path": str(workspace),
            "enable_whisper": False,
        },
        "alerts": {},
    }

    fd, tmp = tempfile.mkstemp(
        dir=str(state_dir), suffix=".tmp", prefix="config_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
        os.replace(tmp, str(config_path))
        # Config should not be world-readable (contains settings)
        config_path.chmod(0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    print_success(f"Config written: {config_path}")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_bootstrap(apex_root: Path) -> dict:
    """Run the full bootstrap phase.

    Steps:
        1. Check dependencies
        2. Create state directories
        3. Detect network interfaces
        4. Generate TLS certificates (with security acknowledgment)
        5. Select workspace
        6. Write initial config

    Returns a summary dict for the progress tracker.
    """
    state_dir = apex_root / "state"

    # Check for prior completion
    if phase_completed(state_dir, "bootstrap"):
        print_warning("Bootstrap phase was already completed.")
        if not prompt_yes_no("Run it again? (will regenerate certificates)", default=False):
            return {"skipped": True}

    print_header("Apex Setup — Phase 1: Bootstrap")

    print_info("This phase prepares the server for first run:")
    print_info("  - Check Python dependencies")
    print_info("  - Create state directories")
    print_info("  - Detect network interfaces")
    print_info("  - Generate TLS certificates (mTLS)")
    print_info("  - Select agent workspace")
    print_info("  - Write initial configuration")
    print()

    # 1. Dependencies
    deps = check_dependencies()
    missing_required = [
        name for name, installed in deps.items()
        if name in _REQUIRED_PACKAGES and not installed
    ]
    if missing_required:
        print_error("Cannot continue without required packages.")
        return {"error": "missing_dependencies", "missing": missing_required}

    print()

    # 2. State directories
    init_state_dirs(apex_root)
    print()

    # 3. Network detection
    ip_entries = detect_local_ips()
    all_ips = [e["ip"] for e in ip_entries]

    # Let user add extra IPs or DNS names
    if prompt_yes_no("Add additional IPs or hostnames for the certificate?", default=False):
        extra = prompt_text("Additional SANs (comma-separated IPs or hostnames)", required=False)
        if extra:
            for part in extra.split(","):
                part = part.strip()
                if not part:
                    continue
                # Simple heuristic: if it looks like an IP, add as IP
                try:
                    socket.inet_aton(part)
                    all_ips.append(part)
                except OSError:
                    # Treat as DNS name — handled below
                    pass

    dns_names = ["localhost"]
    if prompt_yes_no("Add a custom DNS name (e.g., apex.local)?", default=False):
        extra_dns = prompt_text("DNS names (comma-separated)", required=False)
        if extra_dns:
            for part in extra_dns.split(","):
                part = part.strip()
                if part and part not in dns_names:
                    dns_names.append(part)
    print()

    # 4. Certificates — security acknowledgment
    print_header("TLS Certificate Generation")
    print_info("Apex uses mutual TLS (mTLS) for all connections.")
    print_info("A self-signed CA will be created to sign server and client certificates.")
    print_info("The client .p12 bundle must be installed on each device that connects.")
    print()
    print_warning("Private keys will be stored in: " + str(state_dir / "ssl"))
    print_warning("Keep this directory secure. Do not share private keys.")
    print()

    prompt_confirm("I understand")

    cert_info = generate_certificates(state_dir, all_ips, dns_names)
    print()

    # 5. Workspace
    workspace = select_workspace()
    print()

    # 6. Permission mode
    print_step(6, "Agent permission mode")
    print_info("Controls what the AI agent can do without asking:")
    mode_idx = prompt_choice(
        "Permission mode:",
        [
            "acceptEdits — Agent can edit files, asks for other actions (recommended)",
            "plan — Agent proposes changes, you approve each one (safest)",
            "bypassPermissions — Agent acts freely (for trusted/isolated environments)",
        ],
        default=1,
    )
    permission_modes = ["acceptEdits", "plan", "bypassPermissions"]
    permission_mode = permission_modes[mode_idx]
    print()

    # 7. Network access
    print_step(7, "Network access")
    print_info(
        "By default, Apex only accepts connections from this computer (localhost).\n"
        "If you want to access Apex from other devices — like your phone, tablet,\n"
        "or another computer on your Wi-Fi network — you need to enable network access."
    )
    print()
    net_idx = prompt_choice(
        "Who should be able to connect to this server?",
        [
            "This computer only (localhost) — most secure, recommended for testing",
            "Any device on my network (Wi-Fi, VPN) — required for phone/tablet access",
        ],
        default=1,
    )
    if net_idx == 1:  # network access
        host = "0.0.0.0"
        print()
        print_info(
            "IMPORTANT: Network access means any device that can reach this computer\n"
            "can attempt to connect. Apex uses mTLS (client certificates) to block\n"
            "unauthorized connections — only devices with your client certificate\n"
            "can access the server. But you should still only run this on a trusted\n"
            "network (your home Wi-Fi or VPN). Do NOT expose Apex to the public internet."
        )
        print()
    else:
        host = "127.0.0.1"
    print()

    # 8. Write config
    create_initial_config(apex_root, workspace, permission_mode, host=host)
    print()

    # Mark phase complete
    summary = {
        "workspace": str(workspace),
        "permission_mode": permission_mode,
        "ips": all_ips,
        "dns_names": dns_names,
        "p12_password": cert_info["p12_password"],
    }
    mark_phase_completed(state_dir, "bootstrap", **{
        k: v for k, v in summary.items() if k != "p12_password"
    })

    # Final summary
    print_header("Bootstrap Complete")
    print_table(
        ["Setting", "Value"],
        [
            ["Workspace", str(workspace)],
            ["Permission mode", permission_mode],
            ["Network access", "All interfaces (0.0.0.0)" if host == "0.0.0.0" else "Localhost only (127.0.0.1)"],
            ["Server cert SANs", ", ".join(all_ips + dns_names)],
            ["Config", str(state_dir / "config.json")],
            ["SSL directory", str(state_dir / "ssl")],
        ],
    )
    print_success("Phase 1 complete. The server is ready to start.")
    print_info("Next: run Phase 2 (model configuration) to set up AI backends.")
    print()

    return summary
