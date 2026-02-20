"""
DataMind FastAPI Application — Entry Point
Day 1: Health checks, CORS, OpenTelemetry, router registration skeleton.
Day 3: TenantIsolationMiddleware, Redis connection pool, Prometheus metrics mount.
"""
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import make_asgi_app

from datamind_api.config import settings
from datamind_api.middleware.tenant import TenantIsolationMiddleware
from datamind_api.routers import health, llm, agents, datasets, workers, gdpr

log = structlog.get_logger(__name__)


def _configure_otel() -> None:
    resource = Resource.create({
        "service.name": "datamind-api",
        "service.version": "0.1.0",
        "deployment.environment": settings.env,
    })
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — startup and shutdown."""
    log.info("datamind.api.startup", version="0.1.0", env=settings.env)
    _configure_otel()

    # Redis connection pool — shared across all requests
    app.state.redis = aioredis.from_url(
        settings.redis_url, decode_responses=True, max_connections=20
    )

    yield

    await app.state.redis.aclose()
    log.info("datamind.api.shutdown")


app = FastAPI(
    title="DataMind API",
    description="AI-Native Data Analytics & Digital Labor Platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---- Middleware (applied in reverse order — last added = first executed) ----
# 1. CORS (outermost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 2. Tenant isolation (reads Kong-injected headers, establishes context)
app.add_middleware(TenantIsolationMiddleware)

# ---- OpenTelemetry instrumentation ----
FastAPIInstrumentor.instrument_app(app)

# ---- Prometheus metrics ----
app.mount("/metrics", make_asgi_app())

# ---- Routers ----
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(llm.router, prefix="/api/llm", tags=["LLM"])
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
app.include_router(datasets.router, prefix="/api/datasets", tags=["Datasets"])
app.include_router(workers.router, prefix="/api/workers", tags=["Digital Workers"])
app.include_router(gdpr.router, prefix="/api/gdpr", tags=["GDPR / Privacy"])
