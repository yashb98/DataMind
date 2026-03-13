"""
MCP Report Generator — FastAPI + FastMCP server entry point.
Day 11: Phase 2 — WeasyPrint PDF + python-pptx PPTX + SHA-256 Merkle provenance
        + IPFS anchoring via Pinata.

Protocols: MCP (JSON-RPC 2.0, streamable-HTTP, tools/list + tools/call)
SOLID: SRP (wiring only), DIP (all deps injected in lifespan)
Benchmark: tests/benchmarks/bench_report.py

MCP Endpoint: http://mcp-report-generator:8080/mcp/
Health:       http://mcp-report-generator:8080/health/liveness
Metrics:      http://mcp-report-generator:8080/metrics
"""

from __future__ import annotations

import io
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from minio import Minio
from minio.error import S3Error
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app

from mcp_report_generator.config import settings
from mcp_report_generator.generation.ipfs import anchor_to_ipfs
from mcp_report_generator.generation.merkle import MerkleTree, build_report_claims
from mcp_report_generator.generation.pdf import generate_pdf
from mcp_report_generator.generation.pptx import generate_pptx

log = structlog.get_logger(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────

TOOL_CALLS = Counter(
    "mcp_report_tool_calls_total",
    "MCP Report Generator tool invocations",
    ["tool", "format", "status"],
)
TOOL_LATENCY = Histogram(
    "mcp_report_tool_latency_ms",
    "MCP Report Generator tool end-to-end latency in milliseconds",
    ["tool"],
    buckets=[500, 1000, 2000, 5000, 10000, 30000, 60000],
)
REPORT_SIZE_BYTES = Histogram(
    "mcp_report_size_bytes",
    "Generated report file size in bytes",
    ["format"],
    buckets=[10_000, 50_000, 200_000, 500_000, 1_000_000, 5_000_000, 20_000_000],
)

# ── Global Component Refs ─────────────────────────────────────────────────────

_minio_client: Minio | None = None
_http_client: httpx.AsyncClient | None = None

# ── FastMCP Server ────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="datamind-report-generator",
    instructions=(
        "Generate PDF or PPTX reports from structured data sections with "
        "cryptographic Merkle provenance certificates. Optionally anchor the "
        "Merkle root to IPFS via Pinata for tamper-evident external verification. "
        "Reports are stored in MinIO at {tenant_id}/reports/{report_id}.{ext}."
    ),
    stateless_http=True,
)

# ── MCP Tools ─────────────────────────────────────────────────────────────────


@mcp.tool()
async def generate_report(
    title: str,
    sections: list[dict[str, Any]],
    format: str,  # noqa: A002
    tenant_id: str,
    include_provenance: bool = True,
) -> dict[str, Any]:
    """Generate a PDF or PPTX report from structured sections with Merkle provenance.

    Each section may contain a heading, Markdown body text, an optional data
    table (list of row dicts), and an optional ECharts chart config. The report
    is stored in MinIO at ``{tenant_id}/reports/{report_id}.{ext}``.

    A SHA-256 Merkle tree is built over all section content claims, producing a
    tamper-evident root hash embedded in every report's provenance certificate.

    Args:
        title: Report title rendered at the top of every output format.
        sections: Ordered list of section dicts. Each dict must have:
            - ``heading`` (str): Section title.
            - ``content`` (str): Body text in Markdown format.
            - ``data`` (list[dict] | None): Optional rows for table rendering.
            - ``chart_config`` (dict | None): Optional ECharts config (stored
              in report metadata; not rendered in this service).
        format: Output format — ``"pdf"`` or ``"pptx"``.
        tenant_id: Tenant identifier used for MinIO path isolation.
        include_provenance: Embed Merkle certificate in the output (default True).

    Returns:
        GenerateReportResponse dict:
        ``{report_id, format, storage_path, merkle_root, ipfs_hash, page_count,
        generation_ms}``

    Raises:
        Returns error dict with code on any failure:
        ``{"error": str, "code": "REPORT_GENERATION_FAILED"|"MINIO_UPLOAD_FAILED"|...}``
    """
    start = time.perf_counter()
    report_id = str(uuid.uuid4())
    fmt = format.lower()
    generated_at = datetime.now(timezone.utc).isoformat()

    if fmt not in ("pdf", "pptx"):
        return {"error": f"Unsupported format: {fmt}", "code": "INVALID_FORMAT"}

    if _minio_client is None:
        return {"error": "MinIO client not initialised", "code": "MINIO_UNAVAILABLE"}

    log.info(
        "report.generation.started",
        report_id=report_id,
        format=fmt,
        tenant_id=tenant_id,
        section_count=len(sections),
    )

    try:
        # ── Step 1: Build Merkle tree over all section content ────────────────
        claims = build_report_claims(title, sections)
        tree = MerkleTree(claims)
        merkle_root = tree.root_hash

        # ── Step 2: Generate document bytes ──────────────────────────────────
        if fmt == "pdf":
            doc_bytes, page_count = await generate_pdf(
                report_id=report_id,
                title=title,
                sections=sections,
                merkle_root=merkle_root,
                generated_at=generated_at,
                include_provenance=include_provenance,
            )
        else:  # pptx
            doc_bytes, page_count = await generate_pptx(
                report_id=report_id,
                title=title,
                sections=sections,
                merkle_root=merkle_root,
                generated_at=generated_at,
            )

        # ── Step 3: Upload to MinIO ───────────────────────────────────────────
        ext = "pdf" if fmt == "pdf" else "pptx"
        content_type = (
            "application/pdf" if fmt == "pdf"
            else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
        storage_path = f"{tenant_id}/reports/{report_id}.{ext}"

        try:
            _ensure_bucket()
            _minio_client.put_object(
                bucket_name=settings.minio_bucket,
                object_name=storage_path,
                data=io.BytesIO(doc_bytes),
                length=len(doc_bytes),
                content_type=content_type,
                metadata={
                    "report_id": report_id,
                    "tenant_id": tenant_id,
                    "merkle_root": merkle_root,
                    "format": fmt,
                    "generated_at": generated_at,
                },
            )
            log.info(
                "report.uploaded",
                report_id=report_id,
                storage_path=storage_path,
                size_bytes=len(doc_bytes),
            )
        except S3Error as exc:
            log.error("minio.upload.failed", error=str(exc), report_id=report_id)
            TOOL_CALLS.labels(tool="generate_report", format=fmt, status="error").inc()
            return {"error": str(exc), "code": "MINIO_UPLOAD_FAILED"}

        # ── Step 4: Record metrics ────────────────────────────────────────────
        elapsed_ms = (time.perf_counter() - start) * 1000
        TOOL_CALLS.labels(tool="generate_report", format=fmt, status="ok").inc()
        TOOL_LATENCY.labels(tool="generate_report").observe(elapsed_ms)
        REPORT_SIZE_BYTES.labels(format=fmt).observe(len(doc_bytes))

        log.info(
            "report.generation.completed",
            report_id=report_id,
            format=fmt,
            page_count=page_count,
            merkle_root=merkle_root,
            elapsed_ms=round(elapsed_ms, 2),
        )

        return {
            "report_id": report_id,
            "format": fmt,
            "storage_path": storage_path,
            "merkle_root": merkle_root,
            "ipfs_hash": None,
            "page_count": page_count,
            "generation_ms": round(elapsed_ms, 2),
        }

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        TOOL_CALLS.labels(tool="generate_report", format=fmt, status="error").inc()
        log.error(
            "report.generation.failed",
            report_id=report_id,
            error=str(exc),
            elapsed_ms=round(elapsed_ms, 2),
        )
        return {"error": str(exc), "code": "REPORT_GENERATION_FAILED"}


@mcp.tool()
async def anchor_ipfs(
    report_id: str,
    merkle_root: str,
    tenant_id: str,
) -> dict[str, Any]:
    """Anchor a report's Merkle root to IPFS via Pinata for tamper-evident verification.

    Pins a JSON object containing the report ID, Merkle root, tenant, and
    timestamp to IPFS using the Pinata ``pinJSONToIPFS`` endpoint. The
    returned CID (IpfsHash) can be used to independently verify the report's
    integrity at any time.

    If Pinata credentials are not configured (``PINATA_API_KEY`` env var),
    returns ``{"error": ..., "code": "IPFS_UNAVAILABLE"}`` without raising.

    Args:
        report_id: Identifier of the report to anchor (used in Pinata metadata).
        merkle_root: SHA-256 Merkle root hash of the report content.
        tenant_id: Tenant identifier (stored in Pinata keyvalues for indexing).

    Returns:
        On success: ``{"ipfs_hash": str, "pinata_url": str, "anchored_at": str}``
        On failure: ``{"error": str, "code": "IPFS_UNAVAILABLE"|"IPFS_ANCHOR_FAILED"}``
    """
    start = time.perf_counter()

    if _http_client is None:
        return {"error": "HTTP client not initialised", "code": "HTTP_CLIENT_UNAVAILABLE"}

    log.info("ipfs.anchor.requested", report_id=report_id, tenant_id=tenant_id)

    result = await anchor_to_ipfs(
        http_client=_http_client,
        report_id=report_id,
        merkle_root=merkle_root,
        pinata_api_key=settings.pinata_api_key,
        pinata_secret_key=settings.pinata_secret_key,
        pinata_endpoint=settings.pinata_endpoint,
    )

    elapsed_ms = (time.perf_counter() - start) * 1000
    status = "ok" if "ipfs_hash" in result else "error"
    TOOL_CALLS.labels(tool="anchor_ipfs", format="json", status=status).inc()
    TOOL_LATENCY.labels(tool="anchor_ipfs").observe(elapsed_ms)

    return result


# ── MinIO Helpers ─────────────────────────────────────────────────────────────


def _ensure_bucket() -> None:
    """Create the MinIO bucket if it does not already exist.

    Raises:
        S3Error: If MinIO returns an unexpected error during bucket creation.
    """
    if _minio_client is None:
        return
    if not _minio_client.bucket_exists(settings.minio_bucket):
        _minio_client.make_bucket(settings.minio_bucket)
        log.info("minio.bucket.created", bucket=settings.minio_bucket)


# ── FastAPI Application ───────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Application lifespan: initialise / teardown shared resources.

    Initialises OpenTelemetry tracing, MinIO client, and the shared httpx
    AsyncClient. MinIO bucket creation is attempted eagerly; failures are
    logged as warnings so the service can start degraded during cold boot.
    """
    global _minio_client, _http_client

    _configure_otel()

    _http_client = httpx.AsyncClient()

    # MinIO client (synchronous SDK)
    _minio_client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )

    try:
        _ensure_bucket()
        log.info("minio.ready", endpoint=settings.minio_endpoint, bucket=settings.minio_bucket)
    except Exception as exc:
        log.warning("minio.bucket.init_failed", error=str(exc))

    log.info(
        "mcp_report_generator.started",
        service=settings.service_name,
        port=settings.port,
        mcp_endpoint=f"http://localhost:{settings.port}/mcp/",
    )
    yield

    await _http_client.aclose()
    log.info("mcp_report_generator.stopped")


def _configure_otel() -> None:
    """Configure OpenTelemetry tracing with OTLP gRPC exporter."""
    resource = Resource.create(
        {"service.name": settings.service_name, "service.version": "0.1.0"}
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


app = FastAPI(
    title="DataMind MCP Report Generator",
    description=(
        "MCP Tool Server for generating PDF/PPTX reports with SHA-256 Merkle "
        "provenance and IPFS anchoring via Pinata."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

FastAPIInstrumentor.instrument_app(app)
app.mount("/metrics", make_asgi_app())
app.mount("/mcp", mcp.get_asgi_app())


# ── Health Endpoints ──────────────────────────────────────────────────────────


@app.get("/health/liveness", tags=["Health"])
async def liveness() -> dict[str, str]:
    """Liveness probe — always returns 200 OK if the process is alive."""
    return {"status": "alive", "service": settings.service_name}


@app.get("/health/readiness", tags=["Health"])
async def readiness() -> dict[str, Any]:
    """Readiness probe — checks MinIO connectivity.

    Returns:
        ``{"status": "healthy"|"degraded", "checks": {...}, "service": str}``
    """
    checks: dict[str, str] = {}

    # MinIO check — attempt to list buckets
    try:
        if _minio_client is None:
            raise RuntimeError("client not initialised")
        list(_minio_client.list_buckets())
        checks["minio"] = "healthy"
    except Exception as exc:
        log.warning("readiness.minio.failed", error=str(exc))
        checks["minio"] = "unhealthy"

    overall = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks, "service": settings.service_name}


@app.get("/tools", tags=["MCP"])
async def list_tools() -> dict[str, Any]:
    """List available MCP tools and the MCP endpoint."""
    return {
        "tools": ["generate_report", "anchor_ipfs"],
        "mcp_endpoint": "/mcp/",
        "transport": "streamable-http",
    }
