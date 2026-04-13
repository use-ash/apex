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

from setup.compat import safe_chmod
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

# Packages installed automatically if missing — not listed in dep check UI
# but essential for core features (execute_code tool).
_AUTO_INSTALL_PACKAGES = {
    "jupyter_client": ["jupyter_client", "ipykernel"],
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

    # Auto-install packages needed for core features (no prompt)
    for import_name, pip_names in _AUTO_INSTALL_PACKAGES.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q"] + pip_names,
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                print_success(f"Jupyter kernel installed (enables execute_code tool)")
            else:
                print_warning(f"Jupyter install failed (execute_code tool unavailable)")

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
    elif system == "Windows":
        found.extend(_detect_ips_windows(seen))
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


def _detect_ips_windows(seen: set[str]) -> list[dict]:
    """Parse 'ipconfig' output on Windows."""
    results: list[dict] = []
    try:
        output = subprocess.run(
            ["ipconfig"], capture_output=True, text=True, timeout=5
        ).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return results
    current_adapter = ""
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not line.startswith(" ") and line.rstrip().endswith(":"):
            current_adapter = stripped.rstrip(":")
        elif "IPv4 Address" in stripped or "IPv4-Adresse" in stripped:
            parts = stripped.split(":")
            if len(parts) >= 2:
                ip = parts[-1].strip()
                if ip not in seen and not ip.startswith("127."):
                    results.append({
                        "ip": ip,
                        "interface": current_adapter[:20],
                        "description": "Network",
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


def _has_openssl() -> bool:
    """Check whether the openssl CLI is available."""
    try:
        result = subprocess.run(
            ["openssl", "version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


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

    Uses openssl CLI if available, otherwise falls back to the Python
    ``cryptography`` library (required for Windows which lacks openssl).

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
    if _has_openssl():
        return _generate_certificates_openssl(state_dir, ips, dns_names)
    else:
        print_info("openssl CLI not found — using Python cryptography library.")
        return _generate_certificates_python(state_dir, ips, dns_names)


def _generate_certificates_python(
    state_dir: Path,
    ips: list[str],
    dns_names: list[str],
) -> dict:
    """Generate mTLS certificates using the Python cryptography library.

    Pure Python — no openssl CLI required. Works on Windows, macOS, Linux.
    """
    import datetime
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    print_step(4, "Generating TLS certificates (Python)")

    ssl_dir = state_dir / "ssl"
    ssl_dir.mkdir(parents=True, exist_ok=True)
    safe_chmod(ssl_dir, 0o700)

    ca_key_path = ssl_dir / "ca.key"
    ca_crt_path = ssl_dir / "ca.crt"
    server_key_path = ssl_dir / "apex.key"
    server_crt_path = ssl_dir / "apex.crt"
    ext_cnf_path = ssl_dir / "ext.cnf"
    client_key_path = ssl_dir / "client.key"
    client_crt_path = ssl_dir / "client.crt"
    client_p12_path = ssl_dir / "client.p12"

    p12_password = secrets.token_urlsafe(12)
    total_steps = 5
    now = datetime.datetime.now(datetime.timezone.utc)

    def _gen_key() -> rsa.RSAPrivateKey:
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def _write_key(path: Path, key: rsa.RSAPrivateKey) -> None:
        path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))

    def _write_cert(path: Path, cert: x509.Certificate) -> None:
        path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    # ---- Step 1: CA ----
    print_progress(1, total_steps, "Generating CA")
    ca_key = _gen_key()
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Apex CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    _write_key(ca_key_path, ca_key)
    _write_cert(ca_crt_path, ca_cert)

    # ---- Step 2: Server cert with SANs ----
    print_progress(2, total_steps, "Generating server certificate")
    server_key = _gen_key()
    san_entries: list[x509.GeneralName] = []
    for ip in ips:
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            pass
    for dns in dns_names:
        san_entries.append(x509.DNSName(dns))

    server_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "apex-server"),
        ]))
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_encipherment=True,
                content_commitment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.SubjectAlternativeName(san_entries), critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    _write_key(server_key_path, server_key)
    _write_cert(server_crt_path, server_cert)

    # Write ext.cnf for compatibility (not used by Python path but
    # keeps the file layout consistent for external tools)
    san_parts: list[str] = []
    for ip in ips:
        san_parts.append(f"IP:{ip}")
    for dns in dns_names:
        san_parts.append(f"DNS:{dns}")
    ext_cnf_path.write_text(
        f"basicConstraints=CA:FALSE\n"
        f"keyUsage=digitalSignature,keyEncipherment\n"
        f"extendedKeyUsage=serverAuth\n"
        f"subjectAltName={','.join(san_parts)}\n",
        encoding="utf-8",
    )

    # ---- Step 3: Client cert ----
    print_progress(3, total_steps, "Generating client certificate")
    client_key = _gen_key()
    client_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "apex-client"),
        ]))
        .issuer_name(ca_name)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_encipherment=False,
                content_commitment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    _write_key(client_key_path, client_key)
    _write_cert(client_crt_path, client_cert)

    # ---- Step 4: .p12 bundle ----
    print_progress(4, total_steps, "Creating .p12 bundle")
    p12_data = pkcs12.serialize_key_and_certificates(
        b"Apex Client",
        client_key,
        client_cert,
        [ca_cert],
        serialization.BestAvailableEncryption(p12_password.encode()),
    )
    client_p12_path.write_bytes(p12_data)

    # ---- Set file permissions ----
    for key_file in [ca_key_path, server_key_path, client_key_path, client_p12_path]:
        safe_chmod(key_file, 0o600)
    for cert_file in [ca_crt_path, server_crt_path, client_crt_path]:
        safe_chmod(cert_file, 0o644)

    # ---- Step 5: Encrypt private keys at rest ----
    print_progress(5, total_steps, "Encrypting keys")
    _encrypt_keys_at_rest(ca_key_path, server_key_path)

    print()
    print_success("CA certificate:     " + str(ca_crt_path))
    print_success("Server certificate: " + str(server_crt_path))
    print_success("Client certificate: " + str(client_crt_path))
    print_success("Client .p12 bundle: " + str(client_p12_path))
    print_info(f".p12 password: {p12_password}")
    print_info("Save this password — you will need it to install the .p12 on your device.")

    return {
        "ca_crt": str(ca_crt_path),
        "ca_key": str(ca_key_path),
        "server_crt": str(server_crt_path),
        "server_key": str(server_key_path),
        "client_crt": str(client_crt_path),
        "client_key": str(client_key_path),
        "client_p12": str(client_p12_path),
        "ext_cnf": str(ext_cnf_path),
        "p12_password": p12_password,
    }


def _generate_certificates_openssl(
    state_dir: Path,
    ips: list[str],
    dns_names: list[str],
) -> dict:
    """Generate mTLS certificates using the openssl CLI (original path)."""
    print_step(4, "Generating TLS certificates")

    ssl_dir = state_dir / "ssl"
    ssl_dir.mkdir(parents=True, exist_ok=True)
    safe_chmod(ssl_dir, 0o700)

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
    for key_file in [ca_key, server_key, client_key, client_p12]:
        safe_chmod(key_file, 0o600)
    for cert_file in [ca_crt, server_crt, client_crt]:
        safe_chmod(cert_file, 0o644)

    # ---- Encrypt private keys at rest ----
    _encrypt_keys_at_rest(ca_key, server_key)

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


def _encrypt_keys_at_rest(ca_key_path: Path, server_key_path: Path) -> None:
    """Encrypt server-side private keys at rest (shared by both cert paths)."""
    from setup.ssl_keystore import (
        encrypt_key_file,
        generate_passphrase,
        retrieve_passphrase,
        store_passphrase,
    )

    passphrase = retrieve_passphrase()
    if not passphrase:
        passphrase = generate_passphrase()

    if store_passphrase(passphrase):
        encrypted_count = 0
        # Only encrypt server-side keys; client key stays plaintext
        # for direct PEM usage (curl, browser import, etc.)
        for key_file in [ca_key_path, server_key_path]:
            try:
                encrypt_key_file(key_file, passphrase)
                encrypted_count += 1
            except RuntimeError as exc:
                print_warning(f"Could not encrypt {key_file.name}: {exc}")
        if encrypted_count:
            print_success(f"Encrypted {encrypted_count} private key(s) at rest.")
            if platform.system() == "Darwin":
                print_info("Passphrase stored in macOS Keychain (service: apex-ssl).")
            else:
                print_info("Passphrase stored securely.")
    else:
        print_warning("Could not store passphrase — private keys left unencrypted.")


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
    print_step(8, "Writing configuration")

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
        "seed_default_profiles": True,
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
        safe_chmod(config_path, 0o600)
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


def _seed_workspace(workspace: Path) -> None:
    """Create starter files in the workspace so it's not an empty box.

    Only creates files that don't already exist — safe to re-run.
    """
    print_step(9, "Seeding workspace")

    # --- APEX.md (project instructions) ---
    apex_md = workspace / "APEX.md"
    if not apex_md.exists():
        apex_md.write_text(
            "# My Workspace\n"
            "\n"
            "## About\n"
            "Describe your project here. AI agents will read this file for context\n"
            "about your codebase, preferences, and conventions.\n"
            "\n"
            "## Rules\n"
            "- Be concise and direct\n"
            "- Ask before making large changes\n"
            "\n"
            "## Notes\n"
            "Add anything you want agents to know about this workspace.\n",
            encoding="utf-8",
        )
        print_success(f"Created starter {apex_md}")
    else:
        print_info(f"APEX.md already exists — skipped")

    # --- memory/ directory + index ---
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_index = memory_dir / "MEMORY.md"
    if not memory_index.exists():
        memory_index.write_text(
            "# Memory\n"
            "\n"
            "Agent memory files are stored here. Each file captures decisions,\n"
            "context, and lessons learned across sessions.\n"
            "\n"
            "Files are created automatically as you work with agents.\n",
            encoding="utf-8",
        )
        print_success(f"Created {memory_index}")
    else:
        print_info(f"Memory index already exists — skipped")

    # --- skills/ directory ---
    skills_dir = workspace / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    skills_readme = skills_dir / "README.md"
    if not skills_readme.exists():
        skills_readme.write_text(
            "# Skills\n"
            "\n"
            "Custom skills extend what your agents can do.\n"
            "\n"
            "Each skill lives in its own directory with a `SKILL.md` file\n"
            "that defines its name, description, and instructions.\n"
            "\n"
            "Built-in skills (recall, codex, grok) are available automatically.\n"
            "Add custom skills here to teach agents new capabilities.\n",
            encoding="utf-8",
        )
        print_success(f"Created {skills_readme}")
    else:
        print_info(f"Skills directory already exists — skipped")

    link_stats = _seed_workspace_links(workspace)
    if any(link_stats.values()):
        print_success(
            "Linked external agent assets: "
            f"{link_stats['skill_links']} skills, "
            f"{link_stats['history_links']} history directories"
        )


def _discover_skill_dirs(root: Path) -> list[Path]:
    """Return directories under root that contain a SKILL.md file."""
    if not root.is_dir():
        return []

    seen: set[str] = set()
    results: list[Path] = []
    for skill_md in sorted(root.rglob("SKILL.md")):
        skill_dir = skill_md.parent
        if skill_dir.name == "lib":
            continue
        try:
            key = str(skill_dir.resolve())
        except OSError:
            key = str(skill_dir)
        if key in seen:
            continue
        seen.add(key)
        results.append(skill_dir)
    return results


def _ensure_symlink(link_path: Path, target: Path) -> bool:
    """Create a symlink if absent. Returns True when created."""
    if not target.exists():
        return False

    if link_path.is_symlink():
        try:
            if link_path.resolve() == target.resolve():
                return False
        except OSError:
            pass
        print_warning(f"Existing symlink points elsewhere — skipped: {link_path}")
        return False

    if link_path.exists():
        print_warning(f"Existing path blocks symlink creation — skipped: {link_path}")
        return False

    link_path.parent.mkdir(parents=True, exist_ok=True)
    link_path.symlink_to(target, target_is_directory=target.is_dir())
    print_success(f"Linked {link_path} -> {target}")
    return True


def _populate_skill_mirror(dest_dir: Path, sources: list[Path]) -> int:
    """Mirror skill directories into one destination directory via symlinks."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    seen_names: set[str] = set()
    for source_root in sources:
        for skill_dir in _discover_skill_dirs(source_root):
            skill_name = skill_dir.name
            if skill_name in seen_names:
                continue
            seen_names.add(skill_name)
            if _ensure_symlink(dest_dir / skill_name, skill_dir):
                created += 1
    return created


def _seed_workspace_links(workspace: Path) -> dict[str, int]:
    """Create workspace-local symlinks to external Claude/Codex assets."""
    home = Path.home()
    stats = {"skill_links": 0, "history_links": 0}

    workspace_skills = workspace / "skills"
    claude_skills = home / ".claude" / "skills"
    codex_skills = home / ".codex" / "skills"

    # Create workspace-local mirrors that Claude/Codex can discover natively.
    skill_sources = [workspace_skills, claude_skills, codex_skills]
    stats["skill_links"] += _populate_skill_mirror(
        workspace / ".claude" / "skills",
        skill_sources,
    )
    stats["skill_links"] += _populate_skill_mirror(
        workspace / ".codex" / "skills",
        skill_sources,
    )

    # Link conversation / memory directories so Apex can reference them
    # without duplicating transcript or memory files into the workspace.
    history_links = [
        (workspace / ".claude" / "projects", home / ".claude" / "projects"),
        (workspace / ".codex" / "sessions", home / ".codex" / "sessions"),
        (workspace / ".codex" / "memories", home / ".codex" / "memories"),
    ]
    for link_path, target in history_links:
        if _ensure_symlink(link_path, target):
            stats["history_links"] += 1

    return stats


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
    print_info("Private keys will be encrypted at rest in: " + str(state_dir / "ssl"))
    print_info("Decryption passphrase will be stored in macOS Keychain.")
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

    # 9. Seed workspace with starter files
    _seed_workspace(workspace)
    print()

    # Mark phase complete
    summary = {
        "workspace": str(workspace),
        "permission_mode": permission_mode,
        "ips": all_ips,
        "dns_names": dns_names,
        "p12_password": cert_info["p12_password"],
    }
    mark_phase_completed(state_dir, "bootstrap", **summary)

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
