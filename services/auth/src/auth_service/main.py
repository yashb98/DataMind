"""
DataMind Auth Service — FastAPI entry point.
Day 3: JWT issuance, ABAC evaluation, token verification for Kong.
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

from auth_service.config import settings
from auth_service.routers.auth import router as auth_router

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # OTel
    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.service_name})
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)

    # Redis — token revocation store
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    log.info("auth.startup", env=settings.env)
    yield

    await app.state.redis.aclose()
    log.info("auth.shutdown")


app = FastAPI(
    title="DataMind Auth Service",
    description="JWT issuance, ABAC policy evaluation, multi-tenancy",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FastAPIInstrumentor.instrument_app(app)
app.mount("/metrics", make_asgi_app())


@app.get("/health/liveness")
async def liveness():
    return {"status": "alive", "service": settings.service_name}


@app.get("/health/readiness")
async def readiness():
    redis_ok = False
    try:
        await app.state.redis.ping()
        redis_ok = True
    except Exception:
        pass
    status_str = "healthy" if redis_ok else "degraded"
    return {"status": status_str, "redis": redis_ok}


app.include_router(auth_router, prefix="/auth", tags=["Auth"])
