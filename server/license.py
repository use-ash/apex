"""Apex Licensing — Ed25519 license validation and trial management.

Provides LicenseManager which handles:
  - Ed25519 signature verification of license files
  - Open access period (free until cutoff date) with rolling trial fallback
  - Feature gating (free vs premium)
  - Cached validation with periodic refresh

Usage:
    from license import LicenseManager
    mgr = LicenseManager(state_dir=Path("state"), db_path=Path("state/apex.db"))
    mgr.status()  # -> {"tier": "trial", "premium_active": True, ...}
    mgr.is_premium_active()  # -> True/False
    mgr.is_feature_enabled("groups")  # -> True/False
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key
from cryptography.exceptions import InvalidSignature

import env

log = logging.getLogger("apex.license")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LICENSE_VERSION = 1
TRIAL_DAYS = 30  # legacy — overridden by OPEN_ACCESS_CUTOFF when set
CACHE_TTL_SECONDS = 3600  # re-validate license every hour

# Open access period: all features free until this date (inclusive).
# After this date, premium features require a license key.
# Set to None to revert to rolling TRIAL_DAYS behavior.
OPEN_ACCESS_CUTOFF = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
LICENSE_FILENAME = "license.json"
CHECK_IN_INTERVAL_SECONDS = 7 * 24 * 3600  # 7 days
LICENSE_SERVER_URL = env.LICENSE_SERVER_URL

# Ed25519 public key for verifying license signatures.
# This is the ONLY key that can validate licenses signed by ash-services.
# Replace with production key before release.
# Generate keypair: python scripts/license_keygen.py
_PUBLIC_KEY_B64 = "MCowBQYDK2VwAyEAMpcaT3DwUoyKyyhPePw39LaMCoN+nIGZU724WYak7Vw="  # prod key (2026-03-31)

# Premium features gated by license
PREMIUM_FEATURES = frozenset({
    "groups",
    "orchestration",
    "agent_profiles",
})

# Features available to all tiers (never gated)
FREE_FEATURES = frozenset({
    "chat",
    "multi_model",
    "memory",
    "whisper",
    "skills",
    "alerts",
    "dashboard_basic",
})

_LICENSE_MANAGER: LicenseManager | None = None
_LICENSE_MANAGER_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# License file parsing
# ---------------------------------------------------------------------------

def _parse_license_file(path: Path) -> dict[str, Any] | None:
    """Read and parse a license JSON file. Returns None on any error."""
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        # Required fields
        for field in ("version", "license_id", "tier", "features",
                      "issued_at", "expires_at", "signature"):
            if field not in data:
                log.warning("License file missing field: %s", field)
                return None
        return data
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to read license file: %s", exc)
        return None


def _verify_signature(data: dict[str, Any], public_key_b64: str) -> bool:
    """Verify Ed25519 signature on a license payload.

    The signature covers the canonical JSON of all fields except 'signature',
    sorted by key, with compact separators (no whitespace).
    """
    if not public_key_b64:
        log.debug("No public key configured — signature verification skipped")
        return False

    try:
        sig_b64 = data.get("signature", "")
        if not sig_b64:
            return False

        signature = base64.b64decode(sig_b64)

        # Reconstruct canonical payload
        payload = {k: v for k, v in data.items() if k != "signature"}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))

        # Load public key
        pub_key_bytes = base64.b64decode(public_key_b64)
        public_key = load_der_public_key(pub_key_bytes)

        if not isinstance(public_key, Ed25519PublicKey):
            log.error("Public key is not Ed25519")
            return False

        # Verify — raises InvalidSignature on failure
        public_key.verify(signature, canonical.encode("utf-8"))
        return True

    except (InvalidSignature, ValueError, TypeError) as exc:
        log.warning("License signature verification failed: %s", exc)
        return False
    except Exception as exc:
        log.error("Unexpected error during signature verification: %s", exc)
        return False


def _is_expired(data: dict[str, Any], include_grace: bool = True) -> bool:
    """Check if a license has expired, optionally including the grace period.

    Subscription licenses carry a grace_period_days field — the license
    remains valid for that many days past expires_at while awaiting renewal.
    """
    try:
        expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        if include_grace:
            grace_days = int(data.get("grace_period_days", 0))
            expires = expires + timedelta(days=grace_days)
        return datetime.now(timezone.utc) > expires
    except (KeyError, ValueError):
        return True  # fail closed — treat unparseable dates as expired


# ---------------------------------------------------------------------------
# Database helpers (trial tracking)
# ---------------------------------------------------------------------------

def _ensure_meta_table(conn: sqlite3.Connection) -> None:
    """Create apex_meta table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS apex_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()


def _get_trial_start(conn: sqlite3.Connection) -> datetime | None:
    """Get trial start timestamp from database. Returns None if not set."""
    _ensure_meta_table(conn)
    row = conn.execute(
        "SELECT value FROM apex_meta WHERE key = 'trial_started_at'"
    ).fetchone()
    if row is None:
        return None
    try:
        return datetime.fromisoformat(row[0])
    except ValueError:
        return None


def _set_trial_start(conn: sqlite3.Connection, when: datetime) -> None:
    """Record trial start timestamp. Only writes if not already set."""
    _ensure_meta_table(conn)
    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR IGNORE INTO apex_meta (key, value, updated_at)
           VALUES ('trial_started_at', ?, ?)""",
        (when.isoformat(), now_iso),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# LicenseManager
# ---------------------------------------------------------------------------

class LicenseManager:
    """Manages license validation, trial tracking, and feature gating.

    Thread-safe. Caches validation results and refreshes periodically.
    """

    def __init__(
        self,
        state_dir: Path | str,
        db_path: Path | str,
        public_key_b64: str = "",
    ) -> None:
        self._state_dir = Path(state_dir)
        self._db_path = Path(db_path)
        self._public_key = public_key_b64 or _PUBLIC_KEY_B64
        self._license_path = self._state_dir / LICENSE_FILENAME
        self._lock = threading.Lock()
        self._premium_loader = None  # set by apex.py after PremiumLoader init

        # Cached state
        self._cached_status: dict[str, Any] | None = None
        self._cache_time: float = 0

    # -- public API ---------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return current license status. Cached with periodic refresh.

        Returns dict with keys:
            tier: "free" | "trial" | "pro" | "enterprise"
            premium_active: bool
            trial_active: bool
            trial_days_remaining: int (0 if no trial or expired)
            license_valid: bool
            license_id: str | None
            license_expires: str | None
            features: dict[str, bool]  (feature_name -> enabled)
        """
        now = time.monotonic()
        with self._lock:
            if self._cached_status and (now - self._cache_time) < CACHE_TTL_SECONDS:
                return self._cached_status

        result = self._compute_status()
        with self._lock:
            self._cached_status = result
            self._cache_time = time.monotonic()
        return result

    def is_premium_active(self) -> bool:
        """Check if premium features are currently available (trial or license)."""
        return self.status()["premium_active"]

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a specific feature is enabled."""
        if feature in FREE_FEATURES:
            return True
        if feature in PREMIUM_FEATURES:
            return self.is_premium_active()
        # Unknown feature — fail closed
        log.warning("Unknown feature checked: %s", feature)
        return False

    def invalidate_cache(self) -> None:
        """Force re-evaluation on next status() call."""
        with self._lock:
            self._cached_status = None
            self._cache_time = 0

    def activate(self, license_json: str, feature_key: str = "") -> dict[str, Any]:
        """Write a license file and validate it. Optionally store a feature key.

        Args:
            license_json: Raw JSON string of the license.
            feature_key: Base64 Fernet key for decrypting premium modules.

        Returns:
            {"success": True, "tier": "pro", ...} on success
            {"success": False, "error": "..."} on failure
        """
        try:
            data = json.loads(license_json)
        except json.JSONDecodeError as exc:
            return {"success": False, "error": f"Invalid JSON: {exc}"}

        # Validate before writing
        if not _verify_signature(data, self._public_key):
            return {"success": False, "error": "Invalid license signature"}

        if _is_expired(data):
            return {"success": False, "error": "License has expired"}

        if data.get("version") != LICENSE_VERSION:
            return {
                "success": False,
                "error": f"Unsupported license version: {data.get('version')}",
            }

        # Bind license to this instance (single-use enforcement)
        import urllib.request
        import urllib.error
        license_id = data.get("license_id", "")
        if license_id:
            try:
                bind_url = LICENSE_SERVER_URL.rsplit("/", 2)[0] + "/license/bind"
                bind_payload = json.dumps({
                    "license_id": license_id,
                    "instance_id": self._instance_id(),
                }).encode()
                bind_req = urllib.request.Request(
                    bind_url, data=bind_payload,
                    headers={"Content-Type": "application/json", "User-Agent": "ApexLicense/1"},
                    method="POST",
                )
                bind_resp = urllib.request.urlopen(bind_req, timeout=10)
                bind_data = json.loads(bind_resp.read().decode())
                # Server may return an updated feature key
                if not feature_key and bind_data.get("feature_key"):
                    feature_key = bind_data["feature_key"]
                log.info("License bound to instance %s", self._instance_id()[:8])
            except urllib.error.HTTPError as exc:
                if exc.code == 409:
                    return {"success": False, "error": "License already activated on another machine. Each license is single-use."}
                log.debug("License bind failed (non-fatal, will retry on check-in): %s", exc)
            except Exception as exc:
                log.debug("License bind unavailable (offline activation): %s", exc)

        # Write license file (atomic)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._license_path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            tmp.replace(self._license_path)
        except OSError as exc:
            return {"success": False, "error": f"Failed to write license: {exc}"}

        # Store feature key if provided (for premium module decryption)
        if feature_key:
            self.store_feature_key(feature_key)

        self.invalidate_cache()
        status = self.status()
        return {
            "success": True,
            "tier": status["tier"],
            "features": status["features"],
            "expires": data.get("expires_at"),
        }

    def deactivate(self) -> dict[str, Any]:
        """Remove the license file and feature key. Reverts to trial or free tier."""
        try:
            if self._license_path.exists():
                self._license_path.unlink()
            self.clear_feature_key()
            self.invalidate_cache()
            return {"success": True, "tier": self.status()["tier"]}
        except OSError as exc:
            return {"success": False, "error": str(exc)}

    # -- feature key management ------------------------------------------------

    def store_feature_key(self, key_b64: str) -> None:
        """Store the feature key via PremiumLoader (instance-bound keystore)."""
        if self._premium_loader and key_b64:
            self._premium_loader.store_feature_key(key_b64)

    def clear_feature_key(self) -> None:
        """Remove the feature key on deactivation/revocation."""
        if self._premium_loader:
            self._premium_loader.clear_feature_key()

    # -- internal -----------------------------------------------------------

    def _compute_status(self) -> dict[str, Any]:
        """Evaluate license + trial state from disk and database."""
        result: dict[str, Any] = {
            "tier": "free",
            "premium_active": False,
            "trial_active": False,
            "trial_days_remaining": 0,
            "license_valid": False,
            "license_id": None,
            "license_expires": None,
            "features": {},
        }

        # --- Check for signed license file ---
        license_data = _parse_license_file(self._license_path)
        if license_data:
            sig_valid = _verify_signature(license_data, self._public_key)
            not_expired = not _is_expired(license_data)
            version_ok = license_data.get("version") == LICENSE_VERSION

            if sig_valid and not_expired and version_ok:
                tier = license_data.get("tier", "pro")
                result.update({
                    "tier": tier,
                    "premium_active": True,
                    "license_valid": True,
                    "license_id": license_data.get("license_id"),
                    "license_expires": license_data.get("expires_at"),
                })
                # Build feature map
                licensed_features = set(license_data.get("features", []))
                for f in PREMIUM_FEATURES:
                    result["features"][f] = f in licensed_features
                for f in FREE_FEATURES:
                    result["features"][f] = True
                return result
            else:
                reasons = []
                if not sig_valid:
                    reasons.append("invalid signature")
                if not not_expired:
                    reasons.append("expired")
                if not version_ok:
                    reasons.append(f"version {license_data.get('version')}")
                log.info("License file present but invalid: %s", ", ".join(reasons))

        # --- Check open access / trial ---
        now_utc = datetime.now(timezone.utc)

        if OPEN_ACCESS_CUTOFF and now_utc <= OPEN_ACCESS_CUTOFF:
            # Fixed open-access period — everything free until cutoff
            remaining = (OPEN_ACCESS_CUTOFF - now_utc).days
            result.update({
                "tier": "trial",
                "premium_active": True,
                "trial_active": True,
                "trial_days_remaining": max(1, remaining),
            })
            for f in PREMIUM_FEATURES:
                result["features"][f] = True
        else:
            # Fallback: rolling trial from first run (legacy behavior)
            trial_start = self._get_trial_start_safe()
            if trial_start is None:
                trial_start = now_utc
                self._set_trial_start_safe(trial_start)
                log.info("Trial started: %s (expires %s)",
                         trial_start.isoformat(),
                         (trial_start + timedelta(days=TRIAL_DAYS)).isoformat())

            elapsed = now_utc - trial_start
            remaining = TRIAL_DAYS - elapsed.days
            trial_active = remaining > 0

            if trial_active:
                result.update({
                    "tier": "trial",
                    "premium_active": True,
                    "trial_active": True,
                    "trial_days_remaining": max(0, remaining),
                })
                for f in PREMIUM_FEATURES:
                    result["features"][f] = True
            else:
                result.update({
                    "tier": "free",
                    "premium_active": False,
                    "trial_active": False,
                    "trial_days_remaining": 0,
                })
                for f in PREMIUM_FEATURES:
                    result["features"][f] = False

        for f in FREE_FEATURES:
            result["features"][f] = True

        return result

    def _get_trial_start_safe(self) -> datetime | None:
        """Read trial start from DB with error handling."""
        try:
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            try:
                return _get_trial_start(conn)
            finally:
                conn.close()
        except sqlite3.Error as exc:
            log.error("Failed to read trial start from DB: %s", exc)
            return None

    def _set_trial_start_safe(self, when: datetime) -> None:
        """Write trial start to DB with error handling."""
        try:
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            try:
                _set_trial_start(conn, when)
            finally:
                conn.close()
        except sqlite3.Error as exc:
            log.error("Failed to write trial start to DB: %s", exc)

    # -- subscription check-in ----------------------------------------------

    async def check_in(self) -> bool:
        """Call ash-services to refresh a subscription license.

        Sends the current license_id and instance_id. On success, writes
        the updated license.json (new expires_at, fresh signature).
        Returns True if the license was refreshed, False otherwise.

        Safe to call even if the server is unreachable — fails silently
        and the grace period keeps the existing license valid.
        """
        import asyncio
        import urllib.request
        import urllib.error

        status = self.status()
        license_id = status.get("license_id")
        if not license_id:
            log.debug("check_in: no active license to refresh")
            return False

        payload = json.dumps({
            "license_id": license_id,
            "instance_id": self._instance_id(),
        }).encode()

        try:
            req = urllib.request.Request(
                LICENSE_SERVER_URL,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "ApexLicense/1"},
                method="POST",
            )
            resp = await asyncio.to_thread(
                lambda: urllib.request.urlopen(req, timeout=15)
            )
            body = resp.read().decode()
            data = json.loads(body)
            license_json = data.get("license")
            if not license_json:
                log.warning("check_in: server returned no license")
                return False

            # Extract feature key (current + previous for rotation grace period)
            fk = data.get("feature_key", "")
            fk_prev = data.get("feature_key_previous", "")

            result = self.activate(
                json.dumps(license_json) if isinstance(license_json, dict) else license_json,
                feature_key=fk,
            )
            if result.get("success"):
                log.info("check_in: license refreshed, expires %s (feature_key=%s)",
                         result.get("expires"), "delivered" if fk else "none")
                return True
            else:
                log.warning("check_in: activate failed: %s", result.get("error"))
                return False

        except urllib.error.HTTPError as exc:
            if exc.code == 402:
                log.warning("check_in: subscription not active (402) — license will expire at grace period end")
            else:
                log.warning("check_in: HTTP %s from license server", exc.code)
            return False
        except Exception as exc:
            log.debug("check_in: unreachable or error (%s) — will retry next interval", exc)
            return False

    def _instance_id(self) -> str:
        """Stable per-installation ID stored in state/."""
        id_file = self._state_dir / ".instance_id"
        try:
            if id_file.exists():
                return id_file.read_text().strip()
            import uuid as _uuid
            iid = str(_uuid.uuid4())
            id_file.write_text(iid)
            from compat import safe_chmod
            safe_chmod(id_file, 0o600)
            return iid
        except OSError:
            return "unknown"

    async def run_check_in_loop(self) -> None:
        """Background asyncio loop — checks in with license server every 7 days.

        Call from FastAPI lifespan or a background task. Runs indefinitely.
        First check-in runs eagerly (after 10s) for trials so the feature key
        arrives promptly. Subsequent check-ins use the normal 7-day interval.
        """
        import asyncio
        log.debug("License check-in loop started (interval=%ds)", CHECK_IN_INTERVAL_SECONDS)

        # Eager first check-in — delivers the feature key for trials
        await asyncio.sleep(10)
        try:
            status = self.status()
            if status.get("trial_active") or status.get("license_valid"):
                result = await self.check_in()
                log.info("Eager check-in: %s", "success" if result else "no update")
        except Exception as exc:
            log.debug("Eager check-in failed (non-fatal): %s", exc)

        while True:
            await asyncio.sleep(CHECK_IN_INTERVAL_SECONDS)
            try:
                await self.check_in()
            except Exception as exc:
                log.error("check_in loop error: %s", exc)


def get_license_manager() -> LicenseManager:
    """Return the process-wide LicenseManager singleton."""
    global _LICENSE_MANAGER
    with _LICENSE_MANAGER_LOCK:
        if _LICENSE_MANAGER is None:
            state_dir = env.APEX_ROOT / "state"
            db_path = state_dir / env.DB_NAME
            _LICENSE_MANAGER = LicenseManager(state_dir=state_dir, db_path=db_path)
        return _LICENSE_MANAGER
