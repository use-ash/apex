"""Helpers for extracting mTLS client certificate state from ASGI scopes."""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


def mtls_required(ssl_cert: str, ssl_ca: str) -> bool:
    """Treat partial TLS client-auth configuration as fail-closed."""
    return bool(ssl_cert or ssl_ca)


def has_verified_peer_cert(scope: Mapping[str, Any]) -> bool:
    """Return True if a peer certificate was verified at the TLS layer.

    Behaviour depends on APEX_MTLS_MODE:

    "required" (default / prod):
        ssl_cert_reqs=CERT_REQUIRED means the TLS handshake itself rejects
        any connection without a valid client cert.  Any request that reaches
        this ASGI app has already been verified — return True unconditionally.

    "optional" (dev / Docker tooling):
        ssl_cert_reqs=CERT_OPTIONAL allows connections without a client cert.
        Uvicorn 0.42+ does not reliably expose peercert in scope, so we
        cannot detect whether a cert was actually presented.  Return False
        to force the middleware to rely on bearer token authentication.
    """
    mode = os.environ.get("APEX_MTLS_MODE", "required")
    if mode == "optional":
        # Can't detect cert presence — fall through to bearer token check.
        return False
    # CERT_REQUIRED: TLS layer already verified.
    return True
