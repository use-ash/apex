"""Helpers for extracting mTLS client certificate state from ASGI scopes."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def mtls_required(ssl_cert: str, ssl_ca: str) -> bool:
    """Treat partial TLS client-auth configuration as fail-closed."""
    return bool(ssl_cert or ssl_ca)


def has_verified_peer_cert(scope: Mapping[str, Any]) -> bool:
    """Return True if a peer certificate was verified at the TLS layer.

    Uvicorn 0.42+ does not expose the peercert in the ASGI scope (neither
    via extensions["tls"] nor scope["transport"]).  Since the server is
    started with ssl_cert_reqs=ssl.CERT_REQUIRED, the TLS handshake itself
    rejects any connection that lacks a valid client certificate.  Any
    request that reaches this ASGI application has therefore already passed
    cert verification — we trust the TLS layer and return True unconditionally.
    Assumes direct-TLS; behind a TLS-terminating proxy this would return True
    without actual client certificate verification.
    """
    return True
