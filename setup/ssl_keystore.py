"""SSL private key encryption utilities.

Encrypts TLS private keys at rest using AES-256-CBC (OpenSSL native).
The encryption passphrase is stored in macOS Keychain; on Linux it falls
back to a file in the credential directory with 0o600 permissions.

Phase 1 — setup-side only.  Server-side decrypt-at-startup is Phase 2.
"""

from __future__ import annotations

import os
import platform
import secrets
import subprocess

import tempfile
from pathlib import Path

from setup.compat import safe_chmod

# ---------------------------------------------------------------------------
# Keychain / passphrase storage
# ---------------------------------------------------------------------------

_KEYCHAIN_SERVICE = "apex-ssl"
_KEYCHAIN_ACCOUNT = "apex"

# Fallback file for Linux or environments without Keychain
if platform.system() == "Darwin":
    _FALLBACK_DIR = Path(os.environ.get("APEX_ENV_DIR", str(Path.home() / ".apex")))
else:
    _FALLBACK_DIR = Path.home() / ".config" / "apex"

_FALLBACK_FILE = _FALLBACK_DIR / ".ssl_passphrase"


def _has_keychain() -> bool:
    """Return True if macOS Keychain CLI is available."""
    if platform.system() != "Darwin":
        return False
    try:
        subprocess.run(
            ["security", "help"],
            capture_output=True, timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def store_passphrase(passphrase: str) -> bool:
    """Store the SSL passphrase in macOS Keychain (or fallback file).

    Returns True on success, False on failure.
    """
    if _has_keychain():
        try:
            # -U = update if exists, -s = service, -a = account, -w = password
            result = subprocess.run(
                [
                    "security", "add-generic-password",
                    "-U",
                    "-s", _KEYCHAIN_SERVICE,
                    "-a", _KEYCHAIN_ACCOUNT,
                    "-w", passphrase,
                ],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Fallback: write to file
    try:
        _FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
        _FALLBACK_FILE.write_text(passphrase, encoding="utf-8")
        safe_chmod(_FALLBACK_FILE, 0o600)
        return True
    except OSError:
        return False


def retrieve_passphrase() -> str | None:
    """Retrieve the SSL passphrase from Keychain or fallback file.

    Returns None if not found.
    """
    if _has_keychain():
        try:
            result = subprocess.run(
                [
                    "security", "find-generic-password",
                    "-s", _KEYCHAIN_SERVICE,
                    "-a", _KEYCHAIN_ACCOUNT,
                    "-w",
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Fallback: read from file
    if _FALLBACK_FILE.exists():
        try:
            content = _FALLBACK_FILE.read_text(encoding="utf-8").strip()
            if content:
                return content
        except OSError:
            pass

    return None


def generate_passphrase() -> str:
    """Generate a new 256-bit passphrase."""
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Key encryption / decryption
# ---------------------------------------------------------------------------

def is_key_encrypted(key_path: Path) -> bool:
    """Check whether a PEM key file is encrypted.

    Encrypted keys have headers like:
        -----BEGIN ENCRYPTED PRIVATE KEY-----
    or contain 'Proc-Type: 4,ENCRYPTED'.
    """
    try:
        header = key_path.read_bytes()[:256]
        return b"ENCRYPTED" in header
    except OSError:
        return False


def encrypt_key_file(key_path: Path, passphrase: str) -> Path:
    """Encrypt a PEM private key file in-place using AES-256-CBC.

    Uses openssl CLI if available, otherwise falls back to the Python
    ``cryptography`` library for encryption.

    The passphrase is passed via stdin (never on the command line).
    Returns the path to the encrypted file (same path, overwritten).

    Raises RuntimeError on failure.
    """
    if is_key_encrypted(key_path):
        return key_path  # already encrypted

    # Try openssl CLI first
    if _has_openssl_cli():
        return _encrypt_key_openssl(key_path, passphrase)
    else:
        return _encrypt_key_python(key_path, passphrase)


def _has_openssl_cli() -> bool:
    """Check if openssl CLI is available."""
    try:
        result = subprocess.run(
            ["openssl", "version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _encrypt_key_openssl(key_path: Path, passphrase: str) -> Path:
    """Encrypt a key using openssl CLI."""
    fd, tmp_path = tempfile.mkstemp(
        dir=str(key_path.parent), suffix=".enc", prefix=".key_"
    )
    os.close(fd)
    tmp = Path(tmp_path)

    try:
        result = subprocess.run(
            [
                "openssl", "rsa",
                "-in", str(key_path),
                "-out", str(tmp),
                "-aes256",
                "-passin", "stdin",
                "-passout", "stdin",
            ],
            input=f"{passphrase}\n{passphrase}\n",
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to encrypt {key_path.name}: {result.stderr.strip()}"
            )

        safe_chmod(tmp, 0o600)
        os.replace(str(tmp), str(key_path))
        return key_path

    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _encrypt_key_python(key_path: Path, passphrase: str) -> Path:
    """Encrypt a key using the Python cryptography library."""
    try:
        from cryptography.hazmat.primitives import serialization

        key_data = key_path.read_bytes()
        private_key = serialization.load_pem_private_key(key_data, password=None)

        encrypted_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.BestAvailableEncryption(
                passphrase.encode("utf-8")
            ),
        )

        fd, tmp_path = tempfile.mkstemp(
            dir=str(key_path.parent), suffix=".enc", prefix=".key_"
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(encrypted_pem)
            safe_chmod(Path(tmp_path), 0o600)
            os.replace(tmp_path, str(key_path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return key_path

    except ImportError:
        raise RuntimeError(
            f"Cannot encrypt {key_path.name}: "
            "neither openssl CLI nor Python cryptography library available"
        )


def decrypt_key_to_tempfile(key_path: Path, passphrase: str) -> Path:
    """Decrypt an encrypted PEM key to a temporary file.

    The caller is responsible for calling shred_file() on the returned path.
    Returns the path to the decrypted temp file (0o600 permissions).

    If the key is not encrypted, returns the original path unchanged.
    Uses openssl CLI if available, otherwise Python cryptography library.
    """
    if not is_key_encrypted(key_path):
        return key_path  # nothing to decrypt

    if _has_openssl_cli():
        return _decrypt_key_openssl(key_path, passphrase)
    else:
        return _decrypt_key_python(key_path, passphrase)


def _decrypt_key_openssl(key_path: Path, passphrase: str) -> Path:
    """Decrypt a key using openssl CLI."""
    fd, tmp_path = tempfile.mkstemp(suffix=".pem", prefix=".apex_dec_")
    os.close(fd)
    tmp = Path(tmp_path)

    try:
        result = subprocess.run(
            [
                "openssl", "rsa",
                "-in", str(key_path),
                "-out", str(tmp),
                "-passin", "stdin",
            ],
            input=passphrase,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to decrypt {key_path.name}: {result.stderr.strip()}"
            )

        safe_chmod(tmp, 0o600)
        return tmp

    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _decrypt_key_python(key_path: Path, passphrase: str) -> Path:
    """Decrypt a key using the Python cryptography library."""
    try:
        from cryptography.hazmat.primitives import serialization

        key_data = key_path.read_bytes()
        private_key = serialization.load_pem_private_key(
            key_data, password=passphrase.encode("utf-8"),
        )

        decrypted_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        fd, tmp_path = tempfile.mkstemp(suffix=".pem", prefix=".apex_dec_")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(decrypted_pem)
            safe_chmod(Path(tmp_path), 0o600)
            return Path(tmp_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    except ImportError:
        raise RuntimeError(
            f"Cannot decrypt {key_path.name}: "
            "neither openssl CLI nor Python cryptography library available"
        )


def shred_file(path: Path) -> None:
    """Overwrite a file with random bytes and delete it.

    Best-effort secure deletion. Skips if the path doesn't exist or
    points to a file that was never a temp decryption target.
    """
    try:
        if not path.exists():
            return
        size = path.stat().st_size
        with open(path, "wb") as f:
            f.write(os.urandom(size))
            f.flush()
            os.fsync(f.fileno())
        path.unlink()
    except OSError:
        # Best effort — don't crash on cleanup failure
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def migrate_plaintext_keys(ssl_dir: Path) -> dict:
    """Encrypt any unencrypted private keys in the SSL directory.

    Generates a new passphrase (or reuses existing Keychain entry) and
    encrypts all .key files that are not already encrypted.

    Returns a dict with migration results.
    """
    # Only encrypt server-side keys. Client keys must stay plaintext for
    # direct PEM usage (curl, browser import, etc.)
    key_files = [ssl_dir / name for name in ("ca.key", "apex.key")]
    existing = [k for k in key_files if k.exists()]

    if not existing:
        return {"migrated": 0, "skipped": True, "reason": "no key files found"}

    unencrypted = [k for k in existing if not is_key_encrypted(k)]
    if not unencrypted:
        return {"migrated": 0, "skipped": True, "reason": "all keys already encrypted"}

    # Reuse existing passphrase or generate a new one
    passphrase = retrieve_passphrase()
    if not passphrase:
        passphrase = generate_passphrase()
        if not store_passphrase(passphrase):
            return {
                "migrated": 0,
                "skipped": True,
                "reason": "failed to store passphrase in keychain",
            }

    encrypted = []
    errors = []
    for key_path in unencrypted:
        try:
            encrypt_key_file(key_path, passphrase)
            encrypted.append(key_path.name)
        except RuntimeError as exc:
            errors.append(f"{key_path.name}: {exc}")

    return {
        "migrated": len(encrypted),
        "encrypted": encrypted,
        "errors": errors if errors else None,
    }
