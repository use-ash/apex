#!/usr/bin/env python3
"""Apex License Key Management — Generate keypairs and sign licenses.

Usage:
    # Generate a new Ed25519 keypair (dev or prod)
    python scripts/license_keygen.py keygen --env dev
    python scripts/license_keygen.py keygen --env prod

    # Sign a license (creates a license.json)
    python scripts/license_keygen.py sign \
        --private-key keys/dev_private.pem \
        --holder "user@example.com" \
        --tier pro \
        --days 365 \
        --output license.json

    # Verify a license file
    python scripts/license_keygen.py verify \
        --public-key keys/dev_public.b64 \
        --license license.json

Keys are written to keys/ directory (gitignored).
NEVER commit private keys. Store prod keys in GCP Secret Manager.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_der_public_key,
)


KEYS_DIR = Path(__file__).parent.parent / "keys"
LICENSE_VERSION = 1

PREMIUM_FEATURES = ["groups", "orchestration", "agent_profiles"]


def cmd_keygen(args: argparse.Namespace) -> None:
    """Generate an Ed25519 keypair."""
    KEYS_DIR.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    env = args.env
    priv_path = KEYS_DIR / f"{env}_private.pem"
    pub_pem_path = KEYS_DIR / f"{env}_public.pem"
    pub_b64_path = KEYS_DIR / f"{env}_public.b64"

    # Write private key (PEM format)
    priv_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    )
    priv_path.write_bytes(priv_pem)
    priv_path.chmod(0o600)

    # Write public key (PEM format — for reference)
    pub_pem = public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    pub_pem_path.write_bytes(pub_pem)

    # Write public key (DER, base64-encoded — this is what goes in license.py)
    pub_der = public_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    pub_b64 = base64.b64encode(pub_der).decode()
    pub_b64_path.write_text(pub_b64 + "\n")

    print(f"Keypair generated for env={env}:")
    print(f"  Private key: {priv_path}")
    print(f"  Public key (PEM): {pub_pem_path}")
    print(f"  Public key (b64): {pub_b64_path}")
    print()
    print("Copy this into server/license.py _PUBLIC_KEY_B64:")
    print(f'  _PUBLIC_KEY_B64 = "{pub_b64}"')
    print()
    print("IMPORTANT: Never commit the private key. Store in GCP Secret Manager for prod.")


def cmd_sign(args: argparse.Namespace) -> None:
    """Sign a license file."""
    # Load private key
    priv_pem = Path(args.private_key).read_bytes()
    private_key = load_pem_private_key(priv_pem, password=None)

    if not isinstance(private_key, type(Ed25519PrivateKey.generate())):
        # Check via public key type since private key type isn't directly exposed
        try:
            pub = private_key.public_key()
            if not isinstance(pub, Ed25519PublicKey):
                print("ERROR: Private key is not Ed25519", file=sys.stderr)
                sys.exit(1)
        except Exception:
            print("ERROR: Could not verify key type", file=sys.stderr)
            sys.exit(1)

    license_id = f"lic_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=args.days)

    features = args.features.split(",") if args.features else PREMIUM_FEATURES

    license_data = {
        "version": LICENSE_VERSION,
        "license_id": license_id,
        "tier": args.tier,
        "holder": args.holder,
        "features": features,
        "issued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "check_in_interval_days": args.check_in_days,
        "grace_period_days": args.grace_days,
    }
    if args.subscription_id:
        license_data["subscription_id"] = args.subscription_id

    # Compute canonical payload and sign
    canonical = json.dumps(license_data, sort_keys=True, separators=(",", ":"))
    signature = private_key.sign(canonical.encode("utf-8"))
    license_data["signature"] = base64.b64encode(signature).decode()

    # Write
    output = Path(args.output)
    output.write_text(json.dumps(license_data, indent=2) + "\n")
    print(f"License signed and written to: {output}")
    print(f"  ID: {license_id}")
    print(f"  Tier: {args.tier}")
    print(f"  Holder: {args.holder}")
    print(f"  Features: {', '.join(features)}")
    print(f"  Expires: {expires.strftime('%Y-%m-%d')}")


def cmd_verify(args: argparse.Namespace) -> None:
    """Verify a license file against a public key."""
    # Load public key
    pub_b64 = Path(args.public_key).read_text().strip()
    pub_der = base64.b64decode(pub_b64)
    public_key = load_der_public_key(pub_der)

    if not isinstance(public_key, Ed25519PublicKey):
        print("ERROR: Public key is not Ed25519", file=sys.stderr)
        sys.exit(1)

    # Load license
    license_data = json.loads(Path(args.license).read_text())
    sig_b64 = license_data.pop("signature", "")
    if not sig_b64:
        print("FAIL: No signature field in license", file=sys.stderr)
        sys.exit(1)

    signature = base64.b64decode(sig_b64)
    canonical = json.dumps(license_data, sort_keys=True, separators=(",", ":"))

    try:
        public_key.verify(signature, canonical.encode("utf-8"))
        print("VALID: Signature verified successfully")
    except Exception as exc:
        print(f"INVALID: Signature verification failed — {exc}", file=sys.stderr)
        sys.exit(1)

    # Check expiry
    try:
        expires = datetime.fromisoformat(
            license_data["expires_at"].replace("Z", "+00:00")
        )
        if datetime.now(timezone.utc) > expires:
            print(f"WARNING: License expired on {license_data['expires_at']}")
        else:
            days_left = (expires - datetime.now(timezone.utc)).days
            print(f"OK: {days_left} days remaining (expires {license_data['expires_at']})")
    except (KeyError, ValueError):
        print("WARNING: Could not parse expiration date")

    print(f"  Tier: {license_data.get('tier')}")
    print(f"  Holder: {license_data.get('holder')}")
    print(f"  Features: {', '.join(license_data.get('features', []))}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apex License Key Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # keygen
    kg = sub.add_parser("keygen", help="Generate Ed25519 keypair")
    kg.add_argument("--env", choices=["dev", "prod"], default="dev",
                    help="Environment label (default: dev)")

    # sign
    sg = sub.add_parser("sign", help="Sign a license file")
    sg.add_argument("--private-key", required=True, help="Path to private key PEM")
    sg.add_argument("--holder", required=True, help="License holder (email)")
    sg.add_argument("--tier", default="pro", choices=["pro", "enterprise"],
                    help="License tier (default: pro)")
    sg.add_argument("--days", type=int, default=365, help="Validity in days (default: 365)")
    sg.add_argument("--features", default="", help="Comma-separated features (default: all premium)")
    sg.add_argument("--subscription-id", default="", help="Stripe subscription ID (for recurring billing)")
    sg.add_argument("--check-in-days", type=int, default=7, help="Check-in interval in days (default: 7)")
    sg.add_argument("--grace-days", type=int, default=7, help="Grace period after expiry in days (default: 7)")
    sg.add_argument("--output", default="license.json", help="Output file path")

    # verify
    vf = sub.add_parser("verify", help="Verify a license file")
    vf.add_argument("--public-key", required=True, help="Path to public key b64 file")
    vf.add_argument("--license", required=True, help="Path to license.json")

    args = parser.parse_args()
    {"keygen": cmd_keygen, "sign": cmd_sign, "verify": cmd_verify}[args.command](args)


if __name__ == "__main__":
    main()
