"""
DS Workbench — FastAPI entry point for Phase 4 Data Science services.
Day 18: Phase 4 — AutoML, Forecasting, Causal Inference, Model Deployment.

Protocols: None (REST only)
SOLID: SRP (wiring only), DIP (all dependencies injected in lifespan)
Benchmark: tests/benchmarks/bench_automl.py
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app

from ds_workbench.config import settings
from ds_workbench.routers.automl import router as automl_router
from ds_workbench.routers.causal import router as causal_router
from ds_workbench.routers.deployment import router as deployment_router
from ds_workbench.routers.forecast import router as forecast_router

log = structlog.get_logger(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────

AUTOML_JOBS = Counter(
    "ds_workbench_automl_jobs_total",
    "Total AutoML training jobs started",
    ["tenant_id", "problem_type", "status"],
)

TRAINING_DURATION = Histogram(
    "ds_workbench_training_duration_seconds",
    "AutoML training job duration",
    ["problem_type", "presets"],
    buckets=[10, 30, 60, 120, 300, 600],
)

FORECAST_LATENCY = Histogram(
    "ds_workbench_forecast_latency_ms",
    "Forecasting prediction latency in milliseconds",
    ["model"],
    buckets=[50, 100, 200, 500, 1000, 3000],
)

CAUSAL_LATENCY = Histogram(
    "ds_workbench_causal_latency_ms",
    "Causal analysis latency in milliseconds",
    ["method"],
    buckets=[100, 500, 1000, 3000, 10000, 30000],
)

DEPLOY_COUNT = Counter(
    "ds_workbench_deployments_total",
    "Total model deployments",
    ["tenant_id", "status"],
)

# ── Global HTTP client ────────────────────────────────────────────────────────

_http_client: httpx.AsyncClient | None = None


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Configure OTel, HTTP client, and verify external connectivity."""
    global _http_client

    _configure_otel()

    _http_client = httpx.AsyncClient(timeout=10.0)

    log.info(
        "ds_workbench.started",
        service=settings.service_name,
        port=settings.port,
        mlflow_uri=settings.mlflow_tracking_uri,
    )

    yield

    if _http_client:
        await _http_client.aclose()
    log.info("ds_workbench.stopped")


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
    title="DataMind DS Workbench",
    description=(
        "Phase 4 Data Science Workbench: AutoML (AutoGluon 1.2+), "
        "Forecasting (Prophet/NeuralForecast/Chronos), "
        "Causal Inference (DoWhy/EconML + DeepSeek-R1 CoT), "
        "Model Deployment (BentoML + CRYSTALS-Dilithium signing)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

FastAPIInstrumentor.instrument_app(app)

# Include all domain routers
app.include_router(automl_router)
app.include_router(forecast_router)
app.include_router(causal_router)
app.include_router(deployment_router)

# Prometheus metrics endpoint
app.mount("/metrics", make_asgi_app())


# ── Health Endpoints ──────────────────────────────────────────────────────────


@app.get("/health/liveness", tags=["Health"])
async def liveness() -> dict[str, str]:
    """Liveness probe — always returns 200 if process is running."""
    return {"status": "alive", "service": settings.service_name}


@app.get("/health/readiness", tags=["Health"])
async def readiness() -> dict[str, Any]:
    """Readiness probe — checks MLflow connectivity.

    Returns:
        Dict with overall status ("healthy" | "degraded") and per-service checks.
    """
    checks: dict[str, str] = {}

    try:
        if _http_client is None:
            raise RuntimeError("HTTP client not initialised")
        response = await _http_client.get(
            f"{settings.mlflow_tracking_uri}/health", timeout=5.0
        )
        checks["mlflow"] = "healthy" if response.status_code == 200 else "degraded"
    except Exception as exc:
        log.warning("readiness.mlflow.failed", error=str(exc))
        checks["mlflow"] = "degraded"

    overall = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"
    return {
        "status": overall,
        "checks": checks,
        "service": settings.service_name,
        "port": settings.port,
    }
