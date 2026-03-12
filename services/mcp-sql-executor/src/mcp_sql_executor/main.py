"""
MCP SQL Executor — FastAPI + FastMCP server entry point.
Day 8: Phase 2 — MCP Tool Server for NL-to-SQL, SQL execution, and numerical verification.

Protocols: MCP (JSON-RPC 2.0, streamable-HTTP transport, tools/list + tools/call)
SOLID: SRP (wiring only), DIP (all deps injected in lifespan)
Benchmark: tests/benchmarks/bench_nl_to_sql.py

MCP Endpoint: http://mcp-sql-executor:8040/mcp/
Health:       http://mcp-sql-executor:8040/health/liveness
Metrics:      http://mcp-sql-executor:8040/metrics
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import structlog
from fastapi import FastAPI
from langfuse import Langfuse
from mcp.server.fastmcp import FastMCP
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app

from mcp_sql_executor.config import settings
from mcp_sql_executor.models import DatabaseTarget
from mcp_sql_executor.sql.executor import (
    ClickHouseExecutor,
    PostgreSQLExecutor,
    SQLExecutorRouter,
)
from mcp_sql_executor.sql.generator import NLToSQLGenerator
from mcp_sql_executor.sql.verifier import NumberVerifier

log = structlog.get_logger(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────

TOOL_CALLS = Counter(
    "mcp_sql_executor_tool_calls_total",
    "MCP tool invocation count",
    ["tool", "status"],
)
TOOL_LATENCY = Histogram(
    "mcp_sql_executor_tool_latency_ms",
    "MCP tool call latency in milliseconds",
    ["tool"],
    buckets=[50, 100, 250, 500, 1000, 2000, 5000],
)

# ── Global component refs (set in lifespan) ───────────────────────────────────

_generator: NLToSQLGenerator | None = None
_executor_router: SQLExecutorRouter | None = None
_verifier: NumberVerifier | None = None
_pg_pool: asyncpg.Pool | None = None

# ── FastMCP Server ────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="datamind-sql-executor",
    instructions=(
        "Execute SQL queries, convert natural language to SQL, and verify numerical claims "
        "against PostgreSQL and ClickHouse databases. All queries are tenant-isolated."
    ),
    stateless_http=True,
)


# ── MCP Tools ─────────────────────────────────────────────────────────────────


@mcp.tool()
async def nl_to_sql(
    natural_language: str,
    tenant_id: str,
    database: str = "postgres",
    schema_hint: list[str] | None = None,
) -> dict[str, Any]:
    """Convert a natural language question to SQL.

    Generates tenant-aware SQL with confidence scoring and table attribution.
    Uses Anthropic prompt caching for schema context (>90% cache hit rate target).

    Args:
        natural_language: The question in plain English.
        tenant_id: Tenant identifier for row-level security injection.
        database: Target database — "postgres" or "clickhouse".
        schema_hint: Optional list of table names to focus schema context.

    Returns:
        dict with keys: sql, dialect, confidence, tables_referenced, explanation, langfuse_trace_id
    """
    import time
    start = time.perf_counter()
    try:
        db = DatabaseTarget(database)
        executor = _executor_router.get_executor(db)  # type: ignore[union-attr]
        tables = await executor.get_schema(tenant_id=tenant_id, table_names=schema_hint)
        response = await _generator.generate(  # type: ignore[union-attr]
            natural_language=natural_language,
            schema_tables=tables,
            database=db,
            tenant_id=tenant_id,
        )
        elapsed = (time.perf_counter() - start) * 1000
        TOOL_CALLS.labels(tool="nl_to_sql", status="ok").inc()
        TOOL_LATENCY.labels(tool="nl_to_sql").observe(elapsed)
        return response.model_dump()
    except Exception as exc:
        TOOL_CALLS.labels(tool="nl_to_sql", status="error").inc()
        log.error("mcp.nl_to_sql.error", error=str(exc), tenant_id=tenant_id)
        return {"error": str(exc), "code": "NL_TO_SQL_FAILED"}


@mcp.tool()
async def execute_sql(
    sql: str,
    tenant_id: str,
    database: str = "postgres",
    max_rows: int = 1000,
) -> dict[str, Any]:
    """Execute a SQL SELECT query against PostgreSQL or ClickHouse.

    Safety: Only SELECT statements are permitted. All queries are tenant-isolated.
    Results are capped at max_rows (hard limit: 10,000).

    Args:
        sql: SQL SELECT query to execute.
        tenant_id: Tenant identifier for row-level security.
        database: Target database — "postgres" or "clickhouse".
        max_rows: Maximum rows to return (1–10,000).

    Returns:
        dict with keys: rows, row_count, columns, execution_time_ms, truncated
    """
    import time
    start = time.perf_counter()
    try:
        db = DatabaseTarget(database)
        executor = _executor_router.get_executor(db)  # type: ignore[union-attr]
        response = await executor.execute(
            sql=sql,
            tenant_id=tenant_id,
            parameters=None,
            max_rows=min(max_rows, settings.max_rows),
            timeout_s=settings.query_timeout_s,
        )
        elapsed = (time.perf_counter() - start) * 1000
        TOOL_CALLS.labels(tool="execute_sql", status="ok").inc()
        TOOL_LATENCY.labels(tool="execute_sql").observe(elapsed)
        return response.model_dump()
    except ValueError as exc:
        TOOL_CALLS.labels(tool="execute_sql", status="rejected").inc()
        return {"error": str(exc), "code": "WRITE_REJECTED"}
    except Exception as exc:
        TOOL_CALLS.labels(tool="execute_sql", status="error").inc()
        log.error("mcp.execute_sql.error", error=str(exc), tenant_id=tenant_id)
        return {"error": str(exc), "code": "EXECUTION_FAILED"}


@mcp.tool()
async def get_schema(
    tenant_id: str,
    database: str = "postgres",
    table_names: list[str] | None = None,
) -> dict[str, Any]:
    """Retrieve table schemas from the database.

    Returns column names, types, and nullability for schema-aware SQL generation.

    Args:
        tenant_id: Tenant identifier.
        database: Target database — "postgres" or "clickhouse".
        table_names: Optional list to filter specific tables.

    Returns:
        dict with key "tables" containing list of table schema dicts.
    """
    import time
    start = time.perf_counter()
    try:
        db = DatabaseTarget(database)
        executor = _executor_router.get_executor(db)  # type: ignore[union-attr]
        tables = await executor.get_schema(tenant_id=tenant_id, table_names=table_names)
        elapsed = (time.perf_counter() - start) * 1000
        TOOL_CALLS.labels(tool="get_schema", status="ok").inc()
        TOOL_LATENCY.labels(tool="get_schema").observe(elapsed)
        return {"tables": tables, "count": len(tables)}
    except Exception as exc:
        TOOL_CALLS.labels(tool="get_schema", status="error").inc()
        log.error("mcp.get_schema.error", error=str(exc))
        return {"error": str(exc), "code": "SCHEMA_FETCH_FAILED"}


@mcp.tool()
async def verify_numbers(
    claim: str,
    verification_sql: str,
    tenant_id: str,
    database: str = "postgres",
    tolerance: float = 0.01,
) -> dict[str, Any]:
    """Verify a numerical claim against source data (Anti-Hallucination Layer 8).

    Re-executes the provided SQL and compares the result to the claimed value.
    Zero tolerance for hallucinated statistics in financial/medical/legal contexts.

    Args:
        claim: The numerical claim to verify (e.g., "total revenue is $1.2M").
        verification_sql: SQL that recomputes the claimed figure.
        tenant_id: Tenant identifier.
        database: Target database — "postgres" or "clickhouse".
        tolerance: Acceptable relative tolerance (default 1% = 0.01).

    Returns:
        dict with keys: verified, claimed_value, actual_value, discrepancy_pct, verdict, details
    """
    import time
    start = time.perf_counter()
    try:
        db = DatabaseTarget(database)
        response = await _verifier.verify(  # type: ignore[union-attr]
            claim=claim,
            verification_sql=verification_sql,
            database=db,
            tenant_id=tenant_id,
            tolerance=tolerance,
        )
        elapsed = (time.perf_counter() - start) * 1000
        TOOL_CALLS.labels(tool="verify_numbers", status="ok").inc()
        TOOL_LATENCY.labels(tool="verify_numbers").observe(elapsed)
        return response.model_dump()
    except Exception as exc:
        TOOL_CALLS.labels(tool="verify_numbers", status="error").inc()
        log.error("mcp.verify_numbers.error", error=str(exc), tenant_id=tenant_id)
        return {"error": str(exc), "code": "VERIFICATION_FAILED"}


# ── FastAPI Application ───────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _generator, _executor_router, _verifier, _pg_pool

    _configure_otel()

    # PostgreSQL connection pool
    _pg_pool = await asyncpg.create_pool(
        settings.postgres_sync_url.replace(
            "postgresql+asyncpg", "postgresql"
        ).replace("postgresql+asyncpg", "postgresql"),
        min_size=2,
        max_size=10,
        command_timeout=settings.query_timeout_s,
    )

    # Build executors
    pg_executor = PostgreSQLExecutor(settings=settings, pool=_pg_pool)
    ch_executor = ClickHouseExecutor(settings=settings)
    _executor_router = SQLExecutorRouter(
        postgres=pg_executor,
        clickhouse=ch_executor,
        settings=settings,
    )

    # LLM components
    langfuse = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    _generator = NLToSQLGenerator(settings=settings, langfuse=langfuse)
    _verifier = NumberVerifier(executor_router=_executor_router)

    log.info(
        "mcp_sql_executor.started",
        service=settings.service_name,
        port=settings.port,
        mcp_endpoint=f"http://localhost:{settings.port}/mcp/",
    )
    yield

    if _pg_pool:
        await _pg_pool.close()
    log.info("mcp_sql_executor.stopped")


def _configure_otel() -> None:
    resource = Resource.create(
        {"service.name": settings.service_name, "service.version": "0.1.0"}
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


app = FastAPI(
    title="DataMind MCP SQL Executor",
    description="MCP Tool Server for NL-to-SQL, SQL execution, and numerical verification.",
    version="0.1.0",
    lifespan=lifespan,
)

FastAPIInstrumentor.instrument_app(app)
app.mount("/metrics", make_asgi_app())

# Mount FastMCP server — exposes tools/list and tools/call at /mcp/
app.mount("/mcp", mcp.get_asgi_app())


@app.get("/health/liveness", tags=["Health"])
async def liveness() -> dict[str, str]:
    return {"status": "alive", "service": settings.service_name}


@app.get("/health/readiness", tags=["Health"])
async def readiness() -> dict[str, Any]:
    checks: dict[str, str] = {}

    # PostgreSQL check
    try:
        async with _pg_pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.fetchval("SELECT 1")
        checks["postgres"] = "healthy"
    except Exception:
        checks["postgres"] = "unhealthy"

    overall = "healthy" if all(v == "healthy" for v in checks.items()) else "degraded"
    return {"status": overall, "checks": checks, "service": settings.service_name}


@app.get("/tools", tags=["MCP"])
async def list_tools() -> dict[str, Any]:
    """List available MCP tools (convenience REST endpoint)."""
    return {
        "tools": ["nl_to_sql", "execute_sql", "get_schema", "verify_numbers"],
        "mcp_endpoint": f"/mcp/",
        "transport": "streamable-http",
    }
