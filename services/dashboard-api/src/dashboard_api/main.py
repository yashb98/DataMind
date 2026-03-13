"""
Dashboard API — FastAPI REST + WebSocket service for dashboard management.
Day 15: Phase 3 — Visualization & Dashboard backend (CRUD + real-time + NL generation).

Protocols: A2A (delegates NL generation to orchestration-engine)
SOLID: SRP (wiring only), DIP (all deps injected via lifespan → app.state)
Benchmark: tests/benchmarks/bench_nl_dashboard.py

REST:  http://dashboard-api:8110/api/dashboards
WS:    ws://dashboard-api:8110/ws/dashboards/{id}
Health: http://dashboard-api:8110/health/liveness
Metrics: http://dashboard-api:8110/metrics
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import httpx
import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

from dashboard_api.config import settings
from dashboard_api.routers.dashboards import CREATE_TABLE_SQL
from dashboard_api.routers.dashboards import router as dashboards_router
from dashboard_api.routers.nl_dashboard import router as nl_router
from dashboard_api.routers.realtime import router as realtime_router

log = structlog.get_logger(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────

DASHBOARD_CREATES = Counter(
    "dashboard_api_creates_total",
    "Number of dashboards created",
    ["tenant_id"],
)
NL_DASHBOARD_LATENCY = Histogram(
    "dashboard_api_nl_latency_ms",
    "NL-to-Dashboard generation latency in milliseconds",
    buckets=[500, 1000, 2000, 4000, 8000, 16000],
)
WS_CONNECTIONS = Gauge(
    "dashboard_api_ws_connections_active",
    "Active WebSocket dashboard connections",
)

# ── Global state (set in lifespan) ────────────────────────────────────────────

_db_pool: asyncpg.Pool | None = None
_redis: aioredis.Redis | None = None  # type: ignore[type-arg]
_http_client: httpx.AsyncClient | None = None


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """FastAPI lifespan: initialise all shared resources.

    Startup:
      - Configure OpenTelemetry tracing
      - Create asyncpg connection pool and run DDL migrations
      - Create Redis async connection
      - Create shared httpx.AsyncClient

    Shutdown:
      - Close all connections cleanly
    """
    global _db_pool, _redis, _http_client

    _configure_otel()

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    _db_pool = await asyncpg.create_pool(
        settings.postgres_dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    # Run DDL: create dashboards table if not exists
    async with _db_pool.acquire() as conn:
        await conn.execute(CREATE_TABLE_SQL)
    log.info("dashboard_api.postgres.ready", dsn=settings.postgres_dsn.split("@")[-1])

    # ── Redis ─────────────────────────────────────────────────────────────────
    _redis = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    await _redis.ping()
    log.info("dashboard_api.redis.ready")

    # ── HTTP Client ───────────────────────────────────────────────────────────
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    )

    # ── Inject into app.state ────────────────────────────────────────────────
    app.state.db_pool = _db_pool
    app.state.redis = _redis
    app.state.http_client = _http_client
    # Prometheus metric refs for router access
    app.state.dashboard_creates_counter = DASHBOARD_CREATES
    app.state.nl_dashboard_latency_histogram = NL_DASHBOARD_LATENCY
    app.state.ws_connections_gauge = WS_CONNECTIONS

    log.info(
        "dashboard_api.started",
        service=settings.service_name,
        port=settings.port,
    )
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    if _db_pool:
        await _db_pool.close()
        log.info("dashboard_api.postgres.closed")
    if _redis:
        await _redis.aclose()
        log.info("dashboard_api.redis.closed")
    if _http_client:
        await _http_client.aclose()
        log.info("dashboard_api.http_client.closed")
    log.info("dashboard_api.stopped")


# ── OTel ──────────────────────────────────────────────────────────────────────


def _configure_otel() -> None:
    """Configure OpenTelemetry tracing with OTLP gRPC exporter."""
    resource = Resource.create(
        {"service.name": settings.service_name, "service.version": "0.1.0"}
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


# ── FastAPI Application ───────────────────────────────────────────────────────

app = FastAPI(
    title="DataMind Dashboard API",
    description=(
        "Phase 3 dashboard backend: CRUD, real-time WebSocket streaming, "
        "and NL-to-Dashboard generation via A2A orchestration."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

FastAPIInstrumentor.instrument_app(app)
app.mount("/metrics", make_asgi_app())

# Include routers
app.include_router(dashboards_router)
app.include_router(realtime_router)
app.include_router(nl_router)


# ── Health Endpoints ──────────────────────────────────────────────────────────


@app.get("/health/liveness", tags=["Health"])
async def liveness() -> dict[str, str]:
    """Kubernetes liveness probe — always returns 200 if process is running.

    Returns:
        dict with status and service name.
    """
    return {"status": "alive", "service": settings.service_name}


@app.get("/health/readiness", tags=["Health"])
async def readiness() -> dict[str, Any]:
    """Kubernetes readiness probe — checks PostgreSQL and Redis connectivity.

    Returns:
        dict with overall status ("healthy"|"degraded"), per-service checks,
        and service name.
    """
    checks: dict[str, str] = {}

    # PostgreSQL check
    try:
        if _db_pool is not None:
            async with _db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            checks["postgres"] = "healthy"
        else:
            checks["postgres"] = "unhealthy"
    except Exception:
        checks["postgres"] = "unhealthy"

    # Redis check
    try:
        if _redis is not None:
            await _redis.ping()
            checks["redis"] = "healthy"
        else:
            checks["redis"] = "unhealthy"
    except Exception:
        checks["redis"] = "unhealthy"

    overall = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks, "service": settings.service_name}
