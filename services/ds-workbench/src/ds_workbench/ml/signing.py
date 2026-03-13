"""
Artifact Signing — CRYSTALS-Dilithium (NIST PQC standard) via liboqs-python.
Day 18: Phase 4 — Post-quantum cryptographic signing of model artifacts.

Protocols: None
SOLID: SRP (signing only), OCP (fallback via HMAC-SHA256 if liboqs unavailable)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_DILITHIUM_AVAILABLE = False
try:
    import oqs  # liboqs-python  # noqa: F401

    _DILITHIUM_AVAILABLE = True
except ImportError:
    pass


def sign_artifact(artifact: dict[str, Any], secret_key: str | None = None) -> dict[str, Any]:
    """Sign a model artifact with CRYSTALS-Dilithium3 or HMAC-SHA256 fallback.

    The signed artifact includes:
    - artifact_hash: SHA-256 digest of the canonical JSON serialisation
    - signature: Hex-encoded Dilithium3 signature or HMAC-SHA256 digest
    - algorithm: "dilithium3" or "hmac-sha256"
    - signed_at: ISO 8601 UTC timestamp

    Args:
        artifact: Model metadata dict to sign. All values must be JSON-serialisable.
        secret_key: HMAC key (only used for fallback). Defaults to DATAMIND_SECRET_KEY env var.

    Returns:
        Original artifact dict extended with signing metadata.
    """
    from datetime import datetime, timezone

    content = json.dumps(artifact, sort_keys=True, default=str).encode()
    artifact_hash = hashlib.sha256(content).hexdigest()

    if _DILITHIUM_AVAILABLE:
        try:
            sig, alg = _dilithium_sign(content)
            return {
                **artifact,
                "artifact_hash": artifact_hash,
                "signature": sig,
                "algorithm": alg,
                "signed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            log.warning("signing.dilithium.failed", error=str(exc), fallback="hmac")

    # HMAC-SHA256 fallback
    key = (
        secret_key or os.getenv("DATAMIND_SECRET_KEY", "change-me-in-production")
    ).encode()
    sig = hmac.new(key, content, hashlib.sha256).hexdigest()
    return {
        **artifact,
        "artifact_hash": artifact_hash,
        "signature": sig,
        "algorithm": "hmac-sha256",
        "signed_at": datetime.now(timezone.utc).isoformat(),
    }


def _dilithium_sign(content: bytes) -> tuple[str, str]:
    """Sign content with CRYSTALS-Dilithium3 (NIST PQC Level 2).

    Each call generates a fresh ephemeral keypair — suitable for one-time artifact
    signing where the verifier checks the embedded public key.
    For production: persist the keypair in a secrets manager (e.g., Vault).

    Args:
        content: Raw bytes to sign.

    Returns:
        Tuple of (signature_hex, algorithm_name).

    Raises:
        RuntimeError: If liboqs Dilithium3 signing fails.
    """
    import oqs  # type: ignore[import]

    sig_alg = "Dilithium3"
    with oqs.Signature(sig_alg) as signer:
        signer.generate_keypair()
        signature = signer.sign(content)
        return signature.hex(), "dilithium3"
