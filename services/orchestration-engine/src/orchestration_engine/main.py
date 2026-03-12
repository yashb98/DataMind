"""
Orchestration Engine — FastAPI entry point.
Day 10: Phase 2 — LangGraph orchestrator + 8-layer anti-hallucination + A2A protocol.

Protocols: MCP (client), A2A (server — tasks/send, tasks/get, tasks/sendSubscribe)
SOLID: SRP (wiring only), DIP (all deps injected in lifespan)
Benchmark: tests/benchmarks/bench_orchestrator.py

Health:    http://orchestration-engine:8060/health/liveness
A2A:       http://orchestration-engine:8060/a2a/tasks/send
Agent Card: http://orchestration-engine:8060/a2a/.well-known/agent.json
Metrics:   http://orchestration-engine:8060/metrics
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import FastAPI
from langfuse import Langfuse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app

from orchestration_engine.a2a.server import router as a2a_router
from orchestration_engine.antihallucination.pipeline import AntiHallucinationPipeline
from orchestration_engine.config import settings
from orchestration_engine.graph.orchestrator import DataMindOrchestrator
from orchestration_engine.models import WorkflowRequest, WorkflowResponse

log = structlog.get_logger(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────

WORKFLOW_COUNTER = Counter(
    "orchestration_workflows_total",
    "Workflow execution count",
    ["intent", "status"],
)
WORKFLOW_LATENCY = Histogram(
    "orchestration_workflow_latency_ms",
    "End-to-end workflow latency",
    ["intent"],
    buckets=[500, 1000, 3000, 8000, 15000, 45000, 90000],
)
VALIDATION_FAILURES = Counter(
    "orchestration_antihallucination_failures_total",
    "Anti-hallucination layer failures",
    ["layer"],
)

# ── Global Refs ───────────────────────────────────────────────────────────────

_orchestrator: DataMindOrchestrator | None = None
_http_client: httpx.AsyncClient | None = None


# ── FastAPI Application ───────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _orchestrator, _http_client

    _configure_otel()

    _http_client = httpx.AsyncClient(timeout=30.0)
    anti_hallucination = AntiHallucinationPipeline(http_client=_http_client)
    _orchestrator = DataMindOrchestrator(
        http_client=_http_client,
        anti_hallucination=anti_hallucination,
    )

    langfuse = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )

    log.info(
        "orchestration_engine.started",
        service=settings.service_name,
        port=settings.port,
        a2a_endpoint=f"http://localhost:{settings.port}/a2a/",
    )
    yield

    await _http_client.aclose()
    log.info("orchestration_engine.stopped")


def _configure_otel() -> None:
    resource = Resource.create(
        {"service.name": settings.service_name, "service.version": "0.1.0"}
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


app = FastAPI(
    title="DataMind Orchestration Engine",
    description=(
        "LangGraph-based agent orchestrator with 8-layer anti-hallucination pipeline "
        "and A2A Digital Worker protocol. Routes analytics queries to specialised agents."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

FastAPIInstrumentor.instrument_app(app)
app.mount("/metrics", make_asgi_app())
app.include_router(a2a_router)

# A2A Agent Card at well-known URL (served by a2a_router, but also at root /.well-known)
app.add_api_route(
    "/.well-known/agent.json",
    a2a_router.routes[0].endpoint,  # type: ignore[attr-defined]
    methods=["GET"],
    include_in_schema=False,
)


@app.get("/health/liveness", tags=["Health"])
async def liveness() -> dict[str, str]:
    return {"status": "alive", "service": settings.service_name}


@app.get("/health/readiness", tags=["Health"])
async def readiness() -> dict[str, Any]:
    checks: dict[str, str] = {}

    # Check SLM Router
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{settings.slm_router_url}/health/liveness")
            checks["slm_router"] = "healthy" if r.status_code == 200 else "degraded"
    except Exception:
        checks["slm_router"] = "unhealthy"

    # Check MCP SQL Executor
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(
                settings.mcp_sql_executor_url.replace("/mcp/", "/health/liveness")
            )
            checks["mcp_sql_executor"] = "healthy" if r.status_code == 200 else "degraded"
    except Exception:
        checks["mcp_sql_executor"] = "unhealthy"

    overall = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks, "service": settings.service_name}


@app.post("/workflow/run", response_model=WorkflowResponse, tags=["Workflow"])
async def run_workflow(request: WorkflowRequest) -> WorkflowResponse:
    """Execute an analytics workflow through the LangGraph orchestrator.

    Routes the query through intent classification, retrieval, SQL generation,
    LLM synthesis, and the 8-layer anti-hallucination pipeline.

    Args:
        request: Workflow request with query, tenant, and options.

    Returns:
        WorkflowResponse with answer, audit trail, and validation results.
    """
    import time

    start = time.perf_counter()
    result = await _orchestrator.run(request)  # type: ignore[union-attr]
    elapsed_ms = (time.perf_counter() - start) * 1000

    WORKFLOW_COUNTER.labels(
        intent=result.intent.value,
        status=result.status.value,
    ).inc()
    WORKFLOW_LATENCY.labels(intent=result.intent.value).observe(elapsed_ms)

    for detail in result.validation_details:
        if "FAILED" in detail.upper() or "failed" in detail:
            layer = detail.split(":")[0].strip()
            VALIDATION_FAILURES.labels(layer=layer).inc()

    return result
