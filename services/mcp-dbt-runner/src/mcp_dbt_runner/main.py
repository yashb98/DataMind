"""
MCP dbt Runner — FastAPI + FastMCP server entry point.
Day 11: Phase 2 — MCP Tool Server for dbt model execution and DAG lineage.

Protocols: MCP (JSON-RPC 2.0, streamable-HTTP transport, tools/list + tools/call)
SOLID: SRP (wiring only), DIP (all deps injected in lifespan)
Benchmark: tests/benchmarks/bench_dbt.py

MCP Endpoint: http://mcp-dbt-runner:8090/mcp/
Health:       http://mcp-dbt-runner:8090/health/liveness
Metrics:      http://mcp-dbt-runner:8090/metrics
"""

from __future__ import annotations

import subprocess
import time
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app

from mcp_dbt_runner.config import settings
from mcp_dbt_runner.runner.executor import DBTExecutor, IModelExecutor
from mcp_dbt_runner.runner.lineage import (
    ILineageProvider,
    ManifestLineageProvider,
    Neo4jLineagePersister,
)

log = structlog.get_logger(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────

TOOL_CALLS = Counter(
    "mcp_dbt_tool_calls_total",
    "MCP dbt Runner tool invocation count",
    ["tool", "status"],
)
TOOL_LATENCY = Histogram(
    "mcp_dbt_tool_latency_ms",
    "MCP dbt Runner tool call latency in milliseconds",
    ["tool"],
    buckets=[100, 500, 1000, 5000, 15000, 30000, 60000, 120000, 300000],
)
DBT_RUNS = Counter(
    "mcp_dbt_runs_total",
    "dbt model run outcomes",
    ["model", "status"],
)

# ── Global Component Refs (set in lifespan) ───────────────────────────────────

_executor: IModelExecutor | None = None
_lineage_provider: ILineageProvider | None = None
_neo4j_persister: Neo4jLineagePersister | None = None
_neo4j_driver: Any | None = None

# ── FastMCP Server ────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="datamind-dbt-runner",
    instructions=(
        "Execute dbt models against the DataMind data warehouse and retrieve "
        "upstream/downstream lineage from the dbt manifest DAG. All runs are "
        "tenant-isolated via per-tenant output schemas."
    ),
    stateless_http=True,
)


# ── MCP Tools ─────────────────────────────────────────────────────────────────


@mcp.tool()
async def run_model(
    model_name: str,
    tenant_id: str,
    full_refresh: bool = False,
    vars: dict[str, Any] | None = None,
    select: str | None = None,
) -> dict[str, Any]:
    """Execute a dbt model and return structured run results.

    Runs ``dbt run --select <model_name>`` (or the provided ``select`` expression)
    in a tenant-isolated schema (``dbt_{tenant_id}``).  A 300-second hard timeout
    prevents runaway queries from blocking the service.

    Args:
        model_name: dbt model name (e.g., ``stg_orders``, ``fct_revenue``).
        tenant_id: Tenant identifier; output schema becomes ``dbt_{tenant_id}``.
        full_refresh: Pass ``--full-refresh`` to rebuild incremental models from scratch.
        vars: Optional dict of dbt variable overrides (serialised as ``--vars``).
        select: dbt node selector expression (defaults to ``model_name``).

    Returns:
        dict with keys: run_id, model_name, status, rows_affected,
        execution_ms, compiled_sql, logs.
    """
    start = time.perf_counter()
    resolved_vars = vars or {}

    try:
        assert _executor is not None, "Executor not initialised"
        response = await _executor.run(
            model_name=model_name,
            tenant_id=tenant_id,
            full_refresh=full_refresh,
            vars=resolved_vars,
            select=select,
        )

        elapsed = (time.perf_counter() - start) * 1000
        TOOL_CALLS.labels(tool="run_model", status="ok").inc()
        TOOL_LATENCY.labels(tool="run_model").observe(elapsed)
        DBT_RUNS.labels(model=model_name, status=response.status).inc()

        return response.model_dump()

    except Exception as exc:
        TOOL_CALLS.labels(tool="run_model", status="error").inc()
        DBT_RUNS.labels(model=model_name, status="error").inc()
        log.error("mcp.run_model.error", model=model_name, tenant_id=tenant_id, error=str(exc))
        return {"error": str(exc), "code": "RUN_MODEL_FAILED"}


@mcp.tool()
async def get_lineage(
    model_name: str,
    tenant_id: str,
    direction: str = "both",
    depth: int = 3,
) -> dict[str, Any]:
    """Get upstream/downstream lineage for a dbt model from the manifest DAG.

    Reads the compiled ``manifest.json`` to traverse the model dependency graph.
    Lineage edges are optionally persisted to Neo4j for GraphRAG queries.

    Args:
        model_name: dbt model name to query (e.g., ``fct_orders``).
        tenant_id: Tenant identifier for Neo4j node scoping.
        direction: Traversal direction — ``'upstream'``, ``'downstream'``, or ``'both'``.
        depth: Maximum hops to include per direction (1–10; default 3).

    Returns:
        dict with keys: model_name, upstream, downstream, sources, exposures, dag_summary.
    """
    start = time.perf_counter()

    try:
        assert _lineage_provider is not None, "Lineage provider not initialised"
        response = await _lineage_provider.get_lineage(
            model_name=model_name,
            tenant_id=tenant_id,
            direction=direction,
            depth=depth,
        )

        # Best-effort Neo4j persistence (non-blocking fire-and-forget)
        if _neo4j_persister is not None:
            import asyncio

            asyncio.create_task(
                _neo4j_persister.persist(
                    model_name=model_name,
                    tenant_id=tenant_id,
                    response=response,
                )
            )

        elapsed = (time.perf_counter() - start) * 1000
        TOOL_CALLS.labels(tool="get_lineage", status="ok").inc()
        TOOL_LATENCY.labels(tool="get_lineage").observe(elapsed)

        return response.model_dump()

    except Exception as exc:
        TOOL_CALLS.labels(tool="get_lineage", status="error").inc()
        log.error("mcp.get_lineage.error", model=model_name, tenant_id=tenant_id, error=str(exc))
        return {"error": str(exc), "code": "GET_LINEAGE_FAILED"}


# ── FastAPI Application ───────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Application lifespan: initialise executor, lineage provider, Neo4j."""
    global _executor, _lineage_provider, _neo4j_persister, _neo4j_driver

    _configure_otel()

    _executor = DBTExecutor()
    _lineage_provider = ManifestLineageProvider()

    # Attempt Neo4j connection (graceful fallback if unavailable)
    try:
        from neo4j import AsyncGraphDatabase

        _neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        await _neo4j_driver.verify_connectivity()
        _neo4j_persister = Neo4jLineagePersister(driver=_neo4j_driver)
        log.info("neo4j.connected", uri=settings.neo4j_uri)
    except Exception as exc:
        log.warning("neo4j.unavailable", error=str(exc))
        _neo4j_driver = None
        _neo4j_persister = None

    log.info(
        "mcp_dbt_runner.started",
        service=settings.service_name,
        port=settings.port,
        mcp_endpoint=f"http://localhost:{settings.port}/mcp/",
        dbt_project_dir=settings.dbt_project_dir,
    )
    yield

    if _neo4j_driver is not None:
        await _neo4j_driver.close()
    log.info("mcp_dbt_runner.stopped")


def _configure_otel() -> None:
    """Configure OpenTelemetry tracer provider with OTLP gRPC exporter."""
    resource = Resource.create(
        {"service.name": settings.service_name, "service.version": "0.1.0"}
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


app = FastAPI(
    title="DataMind MCP dbt Runner",
    description=(
        "MCP Tool Server for dbt model execution, lineage tracking, "
        "and OpenLineage-compatible DAG queries."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

FastAPIInstrumentor.instrument_app(app)
app.mount("/metrics", make_asgi_app())

# Mount FastMCP server — exposes tools/list and tools/call at /mcp/
app.mount("/mcp", mcp.get_asgi_app())


@app.get("/health/liveness", tags=["Health"])
async def liveness() -> dict[str, str]:
    """Liveness probe — returns 200 if the process is running."""
    return {"status": "alive", "service": settings.service_name}


@app.get("/health/readiness", tags=["Health"])
async def readiness() -> dict[str, Any]:
    """Readiness probe — checks dbt binary availability.

    Returns:
        JSON with overall status (``healthy`` or ``degraded``) and
        per-component checks.
    """
    checks: dict[str, str] = {}

    try:
        result = subprocess.run(
            ["dbt", "--version"],
            capture_output=True,
            timeout=10,
        )
        checks["dbt"] = "healthy" if result.returncode == 0 else "unhealthy"
    except Exception:
        checks["dbt"] = "unhealthy"

    overall = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks, "service": settings.service_name}


@app.get("/tools", tags=["MCP"])
async def list_tools() -> dict[str, Any]:
    """List available MCP tools (convenience REST endpoint)."""
    return {
        "tools": ["run_model", "get_lineage"],
        "mcp_endpoint": "/mcp/",
        "transport": "streamable-http",
    }
