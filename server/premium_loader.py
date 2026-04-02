"""Cryptographic premium feature loader.

Manages an instance-bound keystore for the Fernet feature key and loads
encrypted premium modules at runtime.  Without a valid feature key the
encrypted .enc blobs are inert — the premium code never exists in memory.

In dev mode (APEX_DEV_MODE=1 or port != 8300) plaintext .py files are
loaded directly so IDE tooling and debugging work normally.
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import logging
import os

import types
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from compat import safe_chmod
import env

log = logging.getLogger("apex.premium")

# The three premium modules that can be encrypted
PREMIUM_MODULES = (
    "routes_chat_premium",
    "context_premium",
    "ws_handler_premium",
)

# Salt for PBKDF2 key derivation — constant per build, not secret.
# Changing this invalidates all existing keystores (forces re-activation).
_KDF_SALT = b"apex-premium-keystore-v1"
_KDF_ITERATIONS = 100_000


class PremiumLoader:
    """Load encrypted premium modules using an instance-bound feature key."""

    def __init__(self, server_dir: Path, state_dir: Path) -> None:
        self._server_dir = server_dir
        self._state_dir = state_dir
        self._keystore_path = state_dir / ".feature_keystore"

    # ------------------------------------------------------------------
    # Instance identity (reuses the license manager's .instance_id file)
    # ------------------------------------------------------------------

    def _instance_id(self) -> str:
        """Read the stable per-installation ID from state/."""
        id_file = self._state_dir / ".instance_id"
        try:
            if id_file.exists():
                return id_file.read_text().strip()
        except OSError:
            pass
        return "unknown"

    # ------------------------------------------------------------------
    # Derived key for keystore encryption (instance-bound)
    # ------------------------------------------------------------------

    def _derive_keystore_key(self) -> bytes:
        """PBKDF2 key derived from this installation's instance_id."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_KDF_SALT,
            iterations=_KDF_ITERATIONS,
        )
        return base64.urlsafe_b64encode(kdf.derive(self._instance_id().encode()))

    # ------------------------------------------------------------------
    # Feature key management
    # ------------------------------------------------------------------

    def store_feature_key(self, key_b64: str) -> None:
        """Encrypt the feature key with the instance-bound key and persist."""
        ks_key = self._derive_keystore_key()
        f = Fernet(ks_key)
        encrypted = f.encrypt(key_b64.encode())
        self._keystore_path.write_bytes(encrypted)
        safe_chmod(self._keystore_path, 0o600)
        log.info("Feature key stored in keystore")

    def load_feature_key(self) -> str | None:
        """Decrypt and return the feature key, or None if absent/invalid."""
        if not self._keystore_path.is_file():
            return None
        try:
            ks_key = self._derive_keystore_key()
            f = Fernet(ks_key)
            decrypted = f.decrypt(self._keystore_path.read_bytes())
            return decrypted.decode()
        except (InvalidToken, OSError) as exc:
            log.warning("Failed to decrypt keystore: %s", exc)
            return None

    def clear_feature_key(self) -> None:
        """Remove the keystore on deactivation."""
        try:
            if self._keystore_path.is_file():
                self._keystore_path.unlink()
                log.info("Feature keystore cleared")
        except OSError as exc:
            log.warning("Failed to clear keystore: %s", exc)

    # ------------------------------------------------------------------
    # Module loading
    # ------------------------------------------------------------------

    def _load_plaintext(self, name: str) -> types.ModuleType | None:
        """Load a premium module from its plaintext .py file (dev mode)."""
        py_path = self._server_dir / f"{name}.py"
        if not py_path.is_file():
            log.debug("Dev mode: %s.py not found — skipping", name)
            return None
        try:
            source = py_path.read_text(encoding="utf-8")
            module = types.ModuleType(name)
            module.__file__ = str(py_path)
            module.__loader__ = None
            code = compile(source, str(py_path), "exec")
            exec(code, module.__dict__)  # noqa: S102
            log.info("Loaded premium module (plaintext): %s", name)
            return module
        except Exception as exc:
            log.error("Failed to load %s.py: %s", name, exc)
            return None

    def _load_encrypted(self, name: str, feature_key: str) -> types.ModuleType | None:
        """Decrypt a .enc blob and load it as a module (production)."""
        enc_path = self._server_dir / f"{name}.enc"
        if not enc_path.is_file():
            log.debug("Encrypted module %s.enc not found — skipping", name)
            return None
        try:
            f = Fernet(feature_key.encode())
            decrypted = f.decrypt(enc_path.read_bytes())
            source = decrypted.decode("utf-8")
            module = types.ModuleType(name)
            module.__file__ = f"<premium:{name}>"
            module.__loader__ = None
            code = compile(source, f"<premium:{name}>", "exec")
            exec(code, module.__dict__)  # noqa: S102
            log.info("Loaded premium module (encrypted): %s", name)
            return module
        except InvalidToken:
            log.warning("Failed to decrypt %s.enc — invalid feature key or tampered file", name)
            return None
        except Exception as exc:
            log.error("Failed to load %s.enc: %s", name, exc)
            return None

    def load_premium_module(self, name: str, fallback_key: str = "") -> types.ModuleType | None:
        """Load a single premium module. Uses dev mode or encrypted mode.

        In encrypted mode, tries the current feature key first. If decryption
        fails and a fallback_key is provided (key rotation grace period), tries
        that before giving up.
        """
        if env.DEV_MODE:
            return self._load_plaintext(name)
        feature_key = self.load_feature_key()
        if not feature_key:
            log.debug("No feature key — premium module %s not loaded", name)
            return None
        mod = self._load_encrypted(name, feature_key)
        if mod is None and fallback_key and fallback_key != feature_key:
            log.info("Trying fallback key for %s (key rotation)", name)
            mod = self._load_encrypted(name, fallback_key)
        return mod

    def load_all(self) -> dict[str, types.ModuleType | None]:
        """Load all premium modules. Returns {name: module_or_None}."""
        result: dict[str, types.ModuleType | None] = {}
        for name in PREMIUM_MODULES:
            result[name] = self.load_premium_module(name)
        loaded = [n for n, m in result.items() if m is not None]
        if loaded:
            log.info("Premium modules loaded: %s", ", ".join(loaded))
        else:
            log.info("No premium modules loaded (mode=%s)", "dev" if env.DEV_MODE else "production")
        return result
