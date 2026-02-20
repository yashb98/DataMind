"""
DataMind FastAPI Application — Entry Point
Day 1: Health checks, CORS, OpenTelemetry, router registration skeleton.
"""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from datamind_api.config import settings
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
    yield
    log.info("datamind.api.shutdown")


app = FastAPI(
    title="DataMind API",
    description="AI-Native Data Analytics & Digital Labor Platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---- Middleware ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- OpenTelemetry instrumentation ----
FastAPIInstrumentor.instrument_app(app)

# ---- Routers ----
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(llm.router, prefix="/api/llm", tags=["LLM"])
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
app.include_router(datasets.router, prefix="/api/datasets", tags=["Datasets"])
app.include_router(workers.router, prefix="/api/workers", tags=["Digital Workers"])
app.include_router(gdpr.router, prefix="/api/gdpr", tags=["GDPR / Privacy"])
