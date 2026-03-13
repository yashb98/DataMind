"""
MCP Report Generator — Pinata IPFS anchoring for Merkle provenance.
Day 11: Phase 2 — Tamper-evident external verification via IPFS CID.

Protocols: None (HTTP client utility; called by MCP tools in main.py)
SOLID: SRP (IPFS anchoring only), OCP (add new anchoring backends by implementing
    IIPFSAnchor ABC without modifying this file)
Benchmark: Not latency-critical (external I/O, < 30s SLA)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)


async def anchor_to_ipfs(
    http_client: httpx.AsyncClient,
    report_id: str,
    merkle_root: str,
    pinata_api_key: str,
    pinata_secret_key: str,
    pinata_endpoint: str,
) -> dict[str, Any]:
    """Anchor a report's Merkle root to IPFS via Pinata pinJSONToIPFS.

    Pins a JSON object containing the report ID, Merkle root, timestamp, and
    service identity to IPFS using the Pinata REST API. The returned IPFS CID
    (IpfsHash) is a content-addressed pointer to the provenance record.

    If `pinata_api_key` is empty the function returns immediately with an
    ``IPFS_UNAVAILABLE`` error code so the caller can degrade gracefully
    without raising exceptions.

    Args:
        http_client: Shared httpx.AsyncClient instance from lifespan.
        report_id: Unique identifier of the report being anchored.
        merkle_root: SHA-256 Merkle root hash of the report content.
        pinata_api_key: Pinata API key (may be empty string if not configured).
        pinata_secret_key: Pinata secret API key.
        pinata_endpoint: Base URL of the Pinata API (default: https://api.pinata.cloud).

    Returns:
        On success:
            ``{"ipfs_hash": str, "pinata_url": str, "anchored_at": str}``
        On missing credentials:
            ``{"error": "Pinata not configured", "code": "IPFS_UNAVAILABLE"}``
        On API failure:
            ``{"error": str, "code": "IPFS_ANCHOR_FAILED"}``
    """
    if not pinata_api_key:
        log.info("ipfs.skipped", reason="pinata_api_key_not_configured", report_id=report_id)
        return {"error": "Pinata not configured", "code": "IPFS_UNAVAILABLE"}

    anchored_at = datetime.now(timezone.utc).isoformat()

    payload: dict[str, Any] = {
        "pinataContent": {
            "report_id": report_id,
            "merkle_root": merkle_root,
            "anchored_at": anchored_at,
            "service": "datamind-enterprise",
            "protocol": "MCP+A2A",
            "version": "2.0",
        },
        "pinataMetadata": {
            "name": f"datamind-report-{report_id}",
            "keyvalues": {
                "report_id": report_id,
                "merkle_root": merkle_root[:16],  # Partial for indexing
            },
        },
    }

    try:
        response = await http_client.post(
            f"{pinata_endpoint}/pinning/pinJSONToIPFS",
            json=payload,
            headers={
                "pinata_api_key": pinata_api_key,
                "pinata_secret_api_key": pinata_secret_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()

        ipfs_hash: str = data["IpfsHash"]
        pinata_url = f"https://gateway.pinata.cloud/ipfs/{ipfs_hash}"

        log.info(
            "ipfs.anchored",
            report_id=report_id,
            ipfs_hash=ipfs_hash,
            pinata_url=pinata_url,
        )

        return {
            "ipfs_hash": ipfs_hash,
            "pinata_url": pinata_url,
            "anchored_at": anchored_at,
        }

    except httpx.HTTPStatusError as exc:
        log.error(
            "ipfs.anchor.http_error",
            status_code=exc.response.status_code,
            report_id=report_id,
            error=str(exc),
        )
        return {"error": f"Pinata HTTP {exc.response.status_code}: {exc}", "code": "IPFS_ANCHOR_FAILED"}

    except Exception as exc:
        log.error("ipfs.anchor.failed", error=str(exc), report_id=report_id)
        return {"error": str(exc), "code": "IPFS_ANCHOR_FAILED"}
