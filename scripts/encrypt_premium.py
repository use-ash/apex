#!/usr/bin/env python3
"""Build-time tool: encrypt premium module .py files into .enc blobs.

Usage:
    python scripts/encrypt_premium.py --key <feature_key_b64> [files...]

If no files are specified, encrypts all three premium modules from server/.
Verifies each .enc decrypts back to the original source (round-trip check).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cryptography.fernet import Fernet


def encrypt_file(py_path: Path, feature_key: str) -> Path:
    """Encrypt a .py file → .enc. Returns the .enc path."""
    source = py_path.read_bytes()
    f = Fernet(feature_key.encode())
    encrypted = f.encrypt(source)

    enc_path = py_path.with_suffix(".enc")
    enc_path.write_bytes(encrypted)

    # Round-trip verification
    decrypted = f.decrypt(enc_path.read_bytes())
    if decrypted != source:
        enc_path.unlink()
        raise RuntimeError(f"Round-trip verification FAILED for {py_path.name}")

    print(f"  {py_path.name} → {enc_path.name} ({len(source)} → {len(encrypted)} bytes) ✓")
    return enc_path


def generate_key() -> str:
    """Generate a new Fernet feature key."""
    return Fernet.generate_key().decode()


def main() -> None:
    parser = argparse.ArgumentParser(description="Encrypt premium modules")
    parser.add_argument("--key", help="Fernet feature key (base64). Omit to generate a new one.")
    parser.add_argument("--generate-key", action="store_true", help="Generate and print a new key, then exit")
    parser.add_argument("files", nargs="*", help="Python files to encrypt (default: all premium modules)")
    args = parser.parse_args()

    if args.generate_key:
        print(generate_key())
        return

    feature_key = args.key
    if not feature_key:
        feature_key = generate_key()
        print(f"Generated feature key: {feature_key}")
        print("Store this key securely — it is needed for license activation.\n")

    # Validate key format
    try:
        Fernet(feature_key.encode())
    except Exception as exc:
        print(f"Invalid Fernet key: {exc}", file=sys.stderr)
        sys.exit(1)

    # Resolve files
    if args.files:
        paths = [Path(f) for f in args.files]
    else:
        server_dir = Path(__file__).resolve().parent.parent / "server"
        paths = [
            server_dir / "routes_chat_premium.py",
            server_dir / "context_premium.py",
            server_dir / "ws_handler_premium.py",
        ]

    print("Encrypting premium modules:")
    errors = []
    for p in paths:
        if not p.is_file():
            print(f"  {p.name} — SKIPPED (file not found)")
            continue
        try:
            encrypt_file(p, feature_key)
        except Exception as exc:
            print(f"  {p.name} — ERROR: {exc}")
            errors.append(p.name)

    if errors:
        print(f"\nFailed: {', '.join(errors)}", file=sys.stderr)
        sys.exit(1)
    print("\nDone.")


if __name__ == "__main__":
    main()
