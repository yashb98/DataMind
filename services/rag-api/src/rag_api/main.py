"""
RAG API — FastAPI entry point for Phase 5 RAG & Reporting services.
Day 22: Phase 5 — 4-Tier Memory, GraphRAG, MMR Retrieval, RAGAS Eval,
        NarrativeAgent, CompilerAgent, DSR Automation.

Protocols: None (REST; internal service behind Kong)
SOLID: SRP (wiring only), DIP (all dependencies injected in lifespan)
Benchmark: tests/benchmarks/bench_rag.py
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import httpx
import structlog
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from neo4j import AsyncGraphDatabase
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from rag_api.config import settings
from rag_api.evaluation.ragas_eval import RAGASEvaluator
from rag_api.graphrag.extractor import EntityExtractor
from rag_api.graphrag.neo4j_store import GraphRAGStore
from rag_api.graphrag.pipeline import GraphRAGPipeline
from rag_api.memory.episodic import MongoEpisodicStore
from rag_api.memory.ltm import QdrantLTMStore
from rag_api.memory.manager import MemoryManager
from rag_api.memory.semantic_facts import PgVectorSemanticStore
from rag_api.memory.stm import RedisSTMStore
from rag_api.narrative.compiler_agent import CompilerAgent
from rag_api.narrative.dsr_automation import DSRAutomation
from rag_api.narrative.narrative_agent import NarrativeAgent
from rag_api.retrieval.mmr import MMRRetriever
from rag_api.routers.dsr import router as dsr_router
from rag_api.routers.graphrag import router as graphrag_router
from rag_api.routers.memory import router as memory_router
from rag_api.routers.narrative import router as narrative_router
from rag_api.routers.retrieval import router as retrieval_router

log = structlog.get_logger(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────

NARRATIVE_REQUESTS = Counter(
    "rag_api_narrative_requests_total",
    "Total narrative generation requests",
    ["tenant_id", "section_type", "status"],
)
DSR_REQUESTS = Counter(
    "rag_api_dsr_requests_total",
    "Total DSR requests processed",
    ["tenant_id", "request_type", "status"],
)
NARRATIVE_LATENCY = Histogram(
    "rag_api_narrative_latency_ms",
    "Narrative section generation latency in milliseconds",
    ["section_type"],
    buckets=[500, 1000, 3000, 8000, 15000, 30000],
)
DSR_LATENCY = Histogram(
    "rag_api_dsr_latency_ms",
    "DSR operation latency in milliseconds",
    ["request_type"],
    buckets=[1000, 5000, 10000, 20000, 30000, 60000],
)
COMPILE_LATENCY = Histogram(
    "rag_api_compile_latency_ms",
    "PDF compilation latency in milliseconds",
    buckets=[1000, 5000, 10000, 20000, 30000, 60000],
)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Initialise all service components and inject into app.state."""
    _configure_otel()

    # ── Shared HTTP client ─────────────────────────────────────────────────────
    http_client = httpx.AsyncClient(timeout=30.0)
    app.state.http_client = http_client

    # ── Redis (STM) ────────────────────────────────────────────────────────────
    redis: Redis[Any] = Redis.from_url(settings.redis_url, decode_responses=False)  # type: ignore[type-arg]
    app.state.redis = redis

    # ── Qdrant (LTM + MMR) ────────────────────────────────────────────────────
    qdrant = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
    )
    app.state.qdrant = qdrant

    # ── MongoDB (Episodic) ────────────────────────────────────────────────────
    mongo_client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongodb_url)  # type: ignore[type-arg]
    mongo_db = mongo_client[settings.episodic_db]
    app.state.mongo_client = mongo_client

    # ── PostgreSQL (pgvector Semantic Facts) ──────────────────────────────────
    pg_pool: asyncpg.Pool = await asyncpg.create_pool(  # type: ignore[type-arg]
        settings.postgres_url,
        min_size=2,
        max_size=10,
    )
    app.state.pg_pool = pg_pool

    # ── Neo4j (GraphRAG) ──────────────────────────────────────────────────────
    neo4j_driver = None
    try:
        neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_url,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        await neo4j_driver.verify_connectivity()
        log.info("neo4j.connected", url=settings.neo4j_url)
    except Exception as exc:
        log.warning("neo4j.unavailable", error=str(exc))
        neo4j_driver = None
    app.state.neo4j_driver = neo4j_driver

    # ── Memory Tier Stores ────────────────────────────────────────────────────
    stm_store = RedisSTMStore(redis=redis, settings=settings)
    ltm_store = QdrantLTMStore(qdrant=qdrant, http=http_client, settings=settings)
    episodic_store = MongoEpisodicStore(db=mongo_db, settings=settings)
    semantic_store = PgVectorSemanticStore(pool=pg_pool, http=http_client, settings=settings)

    # Ensure schemas/indexes exist
    try:
        await ltm_store.ensure_collection()
    except Exception as exc:
        log.warning("ltm.ensure_collection.skip", error=str(exc))
    try:
        await episodic_store.ensure_indexes()
    except Exception as exc:
        log.warning("episodic.ensure_indexes.skip", error=str(exc))
    try:
        await semantic_store.ensure_schema()
    except Exception as exc:
        log.warning("semantic_facts.ensure_schema.skip", error=str(exc))

    # ── MemoryManager ─────────────────────────────────────────────────────────
    memory_manager = MemoryManager(
        stm=stm_store,
        ltm=ltm_store,
        episodic=episodic_store,
        semantic=semantic_store,
    )
    app.state.memory_manager = memory_manager

    # ── MMR Retriever ─────────────────────────────────────────────────────────
    mmr_retriever = MMRRetriever(qdrant=qdrant, http=http_client, settings=settings)
    app.state.mmr_retriever = mmr_retriever

    # ── RAGAS Evaluator ───────────────────────────────────────────────────────
    ragas_evaluator = RAGASEvaluator(http=http_client, settings=settings)
    app.state.ragas_evaluator = ragas_evaluator

    # ── GraphRAG Pipeline ─────────────────────────────────────────────────────
    if neo4j_driver is not None:
        graph_store = GraphRAGStore(driver=neo4j_driver, settings=settings)
        try:
            await graph_store.ensure_constraints()
        except Exception as exc:
            log.warning("graphrag.constraints.skip", error=str(exc))

        entity_extractor = EntityExtractor(http=http_client, settings=settings)
        graphrag_pipeline = GraphRAGPipeline(
            extractor=entity_extractor,
            store=graph_store,
        )
        app.state.graphrag_pipeline = graphrag_pipeline
        log.info("graphrag.ready")
    else:
        app.state.graphrag_pipeline = None
        log.warning("graphrag.disabled", reason="Neo4j unavailable")

    # ── NarrativeAgent ────────────────────────────────────────────────────────
    narrative_agent = NarrativeAgent(
        litellm_url=settings.litellm_url,
        langfuse_settings={
            "public_key": settings.langfuse_public_key,
            "secret_key": settings.langfuse_secret_key,
            "host": settings.langfuse_host,
        },
    )
    await narrative_agent.startup()
    app.state.narrative_agent = narrative_agent

    # ── CompilerAgent ─────────────────────────────────────────────────────────
    compiler_agent = CompilerAgent()
    app.state.compiler_agent = compiler_agent

    # ── DSRAutomation ─────────────────────────────────────────────────────────
    dsr_automation = DSRAutomation(
        pg_url=settings.postgres_url,
        redis_url=settings.redis_url,
        mongo_url=settings.mongodb_url,
        qdrant_url=settings.qdrant_url,
        neo4j_url=settings.neo4j_url,
        neo4j_user=settings.neo4j_user,
        neo4j_password=settings.neo4j_password,
        minio_url=settings.minio_url,
        minio_access_key=settings.minio_access_key,
        minio_secret_key=settings.minio_secret_key,
        qdrant_api_key=settings.qdrant_api_key,
    )
    await dsr_automation.startup()
    app.state.dsr_automation = dsr_automation

    log.info(
        "rag_api.started",
        service=settings.service_name,
        port=settings.port,
        litellm_url=settings.litellm_url,
        qdrant_url=settings.qdrant_url,
        neo4j_available=neo4j_driver is not None,
    )

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    await narrative_agent.shutdown()
    await http_client.aclose()
    await redis.aclose()
    await qdrant.close()
    await pg_pool.close()
    mongo_client.close()
    if neo4j_driver:
        await neo4j_driver.close()

    log.info("rag_api.stopped")


def _configure_otel() -> None:
    """Configure OpenTelemetry tracing with OTLP gRPC exporter."""
    resource = Resource.create(
        {"service.name": settings.service_name, "service.version": "0.1.0"}
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


# ── FastAPI Application ───────────────────────────────────────────────────────

app = FastAPI(
    title="DataMind RAG API",
    description=(
        "Phase 5 RAG & Reporting: 4-Tier Agent Memory (Redis STM + Qdrant LTM + "
        "MongoDB Episodic + pgvector Semantic), GraphRAG (Entity extraction → Neo4j), "
        "MMR Retrieval (λ=0.7 adaptive), RAGAS Eval → MLflow, NarrativeAgent, "
        "CompilerAgent (WeasyPrint PDF + Merkle provenance), DSR Automation (GDPR Art. 15/17/20)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

FastAPIInstrumentor.instrument_app(app)

# Include all domain routers
app.include_router(memory_router)
app.include_router(retrieval_router)
app.include_router(graphrag_router)
app.include_router(narrative_router)
app.include_router(dsr_router)

# Prometheus metrics endpoint
app.mount("/metrics", make_asgi_app())


# ── Health Endpoints ──────────────────────────────────────────────────────────


@app.get("/health/liveness", tags=["Health"])
async def liveness() -> dict[str, str]:
    """Liveness probe — always returns 200 if the process is running."""
    return {"status": "alive", "service": settings.service_name}


@app.get("/health/readiness", tags=["Health"])
async def readiness() -> dict[str, Any]:
    """Readiness probe — checks Redis, Qdrant, MongoDB, PostgreSQL, Neo4j, LiteLLM.

    Returns:
        Dict with overall status ("healthy" | "degraded") and per-service checks.
    """
    checks: dict[str, str] = {}

    # Redis
    try:
        redis: Redis[Any] = app.state.redis  # type: ignore[type-arg]
        await redis.ping()
        checks["redis"] = "healthy"
    except Exception:
        checks["redis"] = "unhealthy"

    # Qdrant
    try:
        qdrant: AsyncQdrantClient = app.state.qdrant
        await qdrant.get_collections()
        checks["qdrant"] = "healthy"
    except Exception:
        checks["qdrant"] = "unhealthy"

    # PostgreSQL
    try:
        pool: asyncpg.Pool = app.state.pg_pool  # type: ignore[type-arg]
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["postgres"] = "healthy"
    except Exception:
        checks["postgres"] = "unhealthy"

    # MongoDB
    try:
        mongo: AsyncIOMotorClient = app.state.mongo_client  # type: ignore[type-arg]
        await mongo.admin.command("ping")
        checks["mongodb"] = "healthy"
    except Exception:
        checks["mongodb"] = "unhealthy"

    # Neo4j
    try:
        neo4j_driver = app.state.neo4j_driver
        if neo4j_driver is not None:
            await neo4j_driver.verify_connectivity()
            checks["neo4j"] = "healthy"
        else:
            checks["neo4j"] = "disabled"
    except Exception:
        checks["neo4j"] = "unhealthy"

    # LiteLLM (via HTTP)
    try:
        http: httpx.AsyncClient = app.state.http_client
        r = await http.get(f"{settings.litellm_url}/health/liveliness", timeout=5.0)
        checks["litellm"] = "healthy" if r.status_code == 200 else "degraded"
    except Exception:
        checks["litellm"] = "degraded"

    overall = "healthy" if all(v in ("healthy", "disabled") for v in checks.values()) else "degraded"
    return {
        "status": overall,
        "checks": checks,
        "service": settings.service_name,
        "port": settings.port,
    }
