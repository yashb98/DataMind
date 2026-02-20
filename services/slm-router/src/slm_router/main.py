"""
SLM Router — FastAPI application entry point.
Day 2: Full intent + complexity + sensitivity routing service.
"""
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langfuse import Langfuse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app

from slm_router.classifiers.complexity import OllamaComplexityScorer
from slm_router.classifiers.intent import OllamaIntentClassifier
from slm_router.classifiers.sensitivity import RuleBasedSensitivityDetector
from slm_router.config import settings
from slm_router.models import RouteRequest, RouteResponse

log = structlog.get_logger(__name__)

# ---- Prometheus metrics ----------------------------------------------------
ROUTE_COUNTER = Counter(
    "slm_router_requests_total",
    "Total routing requests",
    ["tier", "intent", "complexity"],
)
ROUTE_LATENCY = Histogram(
    "slm_router_latency_ms",
    "Routing decision latency in ms",
    buckets=[10, 20, 50, 100, 200, 500],
)
CACHE_HIT = Counter(
    "slm_router_cache_hits_total",
    "Routing cache hits",
    ["hit"],
)

# ---- Global state (wired at startup via DI) --------------------------------
_router_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _router_instance

    # OTel
    resource = Resource.create({"service.name": settings.service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)

    # Redis
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    # Langfuse
    langfuse = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )

    # Wire up classifiers (DIP — inject abstractions)
    from slm_router.router import SLMRouter
    _router_instance = SLMRouter(
        intent_clf=OllamaIntentClassifier(
            ollama_url=settings.ollama_url,
            model=settings.intent_model,
            timeout_s=settings.ollama_timeout_s,
        ),
        complexity_scorer=OllamaComplexityScorer(
            ollama_url=settings.ollama_url,
            model=settings.complexity_model,
            timeout_s=settings.ollama_timeout_s,
        ),
        sensitivity_detector=RuleBasedSensitivityDetector(),
        redis_client=redis_client,
        langfuse=langfuse,
    )

    log.info("slm_router.startup", intent_model=settings.intent_model, complexity_model=settings.complexity_model)
    yield

    await redis_client.aclose()
    log.info("slm_router.shutdown")


app = FastAPI(
    title="DataMind SLM Router",
    description="Intelligent query routing: edge → SLM → cloud LLM → RLM",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
FastAPIInstrumentor.instrument_app(app)

# Mount Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health/liveness")
async def liveness():
    return {"status": "alive", "service": settings.service_name}


@app.get("/health/readiness")
async def readiness():
    # Check Ollama is reachable
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{settings.ollama_url}/api/tags")
            ollama_ok = r.status_code == 200
    except Exception:
        ollama_ok = False

    status = "healthy" if ollama_ok else "degraded"
    return {"status": status, "ollama": "healthy" if ollama_ok else "unreachable"}


@app.post("/route", response_model=RouteResponse)
async def route_query(req: RouteRequest):
    """
    Route a query to the optimal inference tier.
    Returns tier, model name, and full classification metadata.
    """
    if _router_instance is None:
        raise HTTPException(status_code=503, detail="Router not initialised")

    import time
    start = time.perf_counter()
    result = await _router_instance.route(req)
    latency_ms = (time.perf_counter() - start) * 1000

    ROUTE_COUNTER.labels(
        tier=result.tier.value,
        intent=result.intent.value,
        complexity=result.complexity.value,
    ).inc()
    ROUTE_LATENCY.observe(latency_ms)
    CACHE_HIT.labels(hit=str(result.cached)).inc()

    return result


@app.post("/classify")
async def classify_only(req: RouteRequest):
    """Return just the classification without routing — useful for debugging."""
    if _router_instance is None:
        raise HTTPException(status_code=503, detail="Router not initialised")
    result = await _router_instance.route(req)
    return result.classification
