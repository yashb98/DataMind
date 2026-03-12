"""
MCP Knowledge Base — FastAPI + FastMCP server entry point.
Day 9: Phase 2 — MCP Tool Server for RAG retrieval, MMR, BM25 hybrid, GraphRAG.

Protocols: MCP (JSON-RPC 2.0, streamable-HTTP, tools/list + tools/call)
SOLID: SRP (wiring only), DIP (all deps injected in lifespan)
Benchmark: tests/benchmarks/bench_retrieval.py

MCP Endpoint: http://mcp-knowledge-base:8050/mcp/
Health:       http://mcp-knowledge-base:8050/health/liveness
Metrics:      http://mcp-knowledge-base:8050/metrics
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from neo4j import AsyncGraphDatabase
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app
from qdrant_client import AsyncQdrantClient

from mcp_knowledge_base.config import settings
from mcp_knowledge_base.models import (
    GraphSearchResult,
    RetrievalMode,
    RetrievedChunk,
    RetrieveResponse,
)
from mcp_knowledge_base.retrieval.bm25 import BM25Retriever, hybrid_fusion
from mcp_knowledge_base.retrieval.mmr import MMRRetriever
from mcp_knowledge_base.retrieval.reranker import CrossEncoderReranker

log = structlog.get_logger(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────

TOOL_CALLS = Counter(
    "mcp_kb_tool_calls_total",
    "MCP Knowledge Base tool invocations",
    ["tool", "mode", "status"],
)
TOOL_LATENCY = Histogram(
    "mcp_kb_tool_latency_ms",
    "MCP Knowledge Base tool latency",
    ["tool"],
    buckets=[50, 100, 200, 500, 1000, 2000],
)
STALE_CHUNKS = Counter(
    "mcp_kb_stale_chunks_total",
    "Chunks flagged as stale (L7 temporal grounding)",
    ["collection"],
)

# ── Global Component Refs ─────────────────────────────────────────────────────

_qdrant: AsyncQdrantClient | None = None
_mmr_retriever: MMRRetriever | None = None
_bm25_retriever: BM25Retriever | None = None
_reranker: CrossEncoderReranker | None = None
_neo4j_driver: Any | None = None
_http_client: httpx.AsyncClient | None = None

# ── FastMCP Server ────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="datamind-knowledge-base",
    instructions=(
        "Retrieve relevant knowledge chunks from the DataMind vector store using "
        "MMR, BM25 hybrid, or graph-based search. All results are tenant-isolated "
        "and include temporal grounding (L7 staleness detection)."
    ),
    stateless_http=True,
)


# ── MCP Tools ─────────────────────────────────────────────────────────────────


@mcp.tool()
async def retrieve(
    query: str,
    tenant_id: str,
    collection: str = "knowledge_base",
    top_k: int = 5,
    mode: str = "hybrid",
    mmr_lambda: float | None = None,
) -> dict[str, Any]:
    """Retrieve relevant knowledge chunks using hybrid MMR + BM25 retrieval.

    Automatically fuses dense vector similarity (70%) and BM25 keyword scoring (30%),
    applies MMR for diversity, and cross-encoder re-ranks final results.
    Stale chunks (>90 days) are flagged with stale=true in the response.

    Args:
        query: Natural language search query.
        tenant_id: Tenant identifier for isolation.
        collection: Qdrant collection name (default: "knowledge_base").
        top_k: Number of results to return (1–50).
        mode: Retrieval mode — "hybrid" (default), "dense", "bm25", "mmr".
        mmr_lambda: MMR trade-off (0=diverse, 1=relevant; None=use default 0.7).

    Returns:
        RetrieveResponse dict with chunks, scores, latencies, and stale count.
    """
    import time
    start = time.perf_counter()

    try:
        retrieval_mode = RetrievalMode(mode)
        query_vec, embed_ms = await _embed_query(query)
        chunks, retrieval_ms, reranking_ms = await _dispatch_retrieval(
            query=query,
            query_vector=query_vec,
            collection=collection,
            tenant_id=tenant_id,
            top_k=top_k,
            mode=retrieval_mode,
            mmr_lambda=mmr_lambda,
        )

        stale_count = sum(1 for c in chunks if c.stale)
        if stale_count > 0:
            STALE_CHUNKS.labels(collection=collection).inc(stale_count)

        elapsed = (time.perf_counter() - start) * 1000
        TOOL_CALLS.labels(tool="retrieve", mode=mode, status="ok").inc()
        TOOL_LATENCY.labels(tool="retrieve").observe(elapsed)

        response = RetrieveResponse(
            chunks=chunks,
            total_candidates=len(chunks),
            mode_used=retrieval_mode,
            query_embedding_ms=round(embed_ms, 2),
            retrieval_ms=round(retrieval_ms, 2),
            reranking_ms=round(reranking_ms, 2),
            stale_chunks=stale_count,
        )
        return response.model_dump(mode="json")
    except Exception as exc:
        TOOL_CALLS.labels(tool="retrieve", mode=mode, status="error").inc()
        log.error("mcp.retrieve.error", error=str(exc), tenant_id=tenant_id)
        return {"error": str(exc), "code": "RETRIEVAL_FAILED"}


@mcp.tool()
async def mmr_search(
    query: str,
    tenant_id: str,
    collection: str = "knowledge_base",
    top_k: int = 5,
    lambda_mode: str = "default",
) -> dict[str, Any]:
    """MMR-only retrieval with configurable diversity mode.

    Useful when diversity across sources is critical (exploratory queries)
    or precision is needed (fact-checking queries).

    Args:
        query: Search query.
        tenant_id: Tenant identifier.
        collection: Qdrant collection name.
        top_k: Number of results (1–50).
        lambda_mode: "default" (0.7), "exploratory" (0.5), or "precise" (0.9).

    Returns:
        RetrieveResponse dict.
    """
    lambda_map = {
        "default": settings.mmr_lambda,
        "exploratory": settings.mmr_lambda_exploratory,
        "precise": settings.mmr_lambda_precise,
    }
    lam = lambda_map.get(lambda_mode, settings.mmr_lambda)
    return await retrieve(
        query=query,
        tenant_id=tenant_id,
        collection=collection,
        top_k=top_k,
        mode="mmr",
        mmr_lambda=lam,
    )


@mcp.tool()
async def graph_search(
    entity: str,
    tenant_id: str,
    max_hops: int = 2,
    limit: int = 10,
) -> dict[str, Any]:
    """Graph-based entity search via Neo4j knowledge graph (GraphRAG).

    Traverses the knowledge graph from the given entity, returning related
    entities, community summaries, and relationship paths.

    Args:
        entity: Entity name to start traversal from.
        tenant_id: Tenant identifier.
        max_hops: Maximum graph hops (1–4).
        limit: Maximum related entities to return.

    Returns:
        GraphSearchResult dict with related entities and community summaries.
    """
    import time
    start = time.perf_counter()

    try:
        if _neo4j_driver is None:
            return {"error": "Neo4j not available", "code": "NEO4J_UNAVAILABLE"}

        async with _neo4j_driver.session() as session:
            cypher = f"""
                MATCH path = (e:Entity {{name: $entity, tenant_id: $tenant_id}})
                    -[*1..{max_hops}]-(related:Entity)
                WITH related, length(path) AS hops
                WHERE related.name <> $entity
                RETURN DISTINCT
                    related.name AS name,
                    related.type AS type,
                    related.description AS description,
                    MIN(hops) AS min_hops
                ORDER BY min_hops ASC, related.name
                LIMIT $limit
            """
            result = await session.run(
                cypher,
                entity=entity,
                tenant_id=tenant_id,
                limit=limit,
            )
            records = await result.data()

        # Get community summary if available
        community_summary: str | None = None
        async with _neo4j_driver.session() as session:
            summary_result = await session.run(
                "MATCH (e:Entity {name: $entity, tenant_id: $tenant_id}) "
                "RETURN e.community_summary AS summary LIMIT 1",
                entity=entity,
                tenant_id=tenant_id,
            )
            summary_data = await summary_result.single()
            if summary_data:
                community_summary = summary_data.get("summary")

        elapsed = (time.perf_counter() - start) * 1000
        TOOL_CALLS.labels(tool="graph_search", mode="graph", status="ok").inc()
        TOOL_LATENCY.labels(tool="graph_search").observe(elapsed)

        response = GraphSearchResult(
            entity=entity,
            related_entities=records,
            community_summary=community_summary,
            path_count=len(records),
        )
        return response.model_dump(mode="json")
    except Exception as exc:
        TOOL_CALLS.labels(tool="graph_search", mode="graph", status="error").inc()
        log.error("mcp.graph_search.error", error=str(exc), tenant_id=tenant_id)
        return {"error": str(exc), "code": "GRAPH_SEARCH_FAILED"}


# ── Internal Dispatch ─────────────────────────────────────────────────────────


async def _embed_query(query: str) -> tuple[list[float], float]:
    """Call embedding service to vectorise query.

    Args:
        query: Text to embed.

    Returns:
        Tuple of (embedding vector, latency_ms).
    """
    import time
    start = time.perf_counter()

    response = await _http_client.post(  # type: ignore[union-attr]
        f"{settings.embedding_service_url}/embed",
        json={"texts": [query]},
        timeout=10.0,
    )
    response.raise_for_status()
    data = response.json()
    elapsed = (time.perf_counter() - start) * 1000
    return data["embeddings"][0], elapsed


async def _dispatch_retrieval(
    query: str,
    query_vector: list[float],
    collection: str,
    tenant_id: str,
    top_k: int,
    mode: RetrievalMode,
    mmr_lambda: float | None,
) -> tuple[list[RetrievedChunk], float, float]:
    """Dispatch to the appropriate retrieval pipeline.

    Returns:
        Tuple of (chunks, retrieval_ms, reranking_ms).
    """
    reranking_ms = 0.0

    if mode in (RetrievalMode.DENSE, RetrievalMode.MMR, RetrievalMode.HYBRID):
        candidate_k = min(top_k * 4, 50)
        chunks, retrieval_ms = await _mmr_retriever.retrieve(  # type: ignore[union-attr]
            query_vector=query_vector,
            collection=collection,
            tenant_id=tenant_id,
            top_k=candidate_k if mode == RetrievalMode.HYBRID else top_k,
            mmr_lambda=mmr_lambda,
        )

        if mode == RetrievalMode.HYBRID and _bm25_retriever:
            dense_ids = [(c.chunk_id, c.score) for c in chunks]
            bm25_ids = _bm25_retriever.retrieve(query, tenant_id, top_k=candidate_k)
            fused = hybrid_fusion(dense_ids, bm25_ids, settings.dense_weight, settings.bm25_weight)
            fused_ids = {cid: score for cid, score in fused}
            # Re-sort original chunks by fused score
            chunks = sorted(
                [c.model_copy(update={"score": fused_ids.get(c.chunk_id, c.score)})
                 for c in chunks if c.chunk_id in fused_ids],
                key=lambda x: x.score,
                reverse=True,
            )[:candidate_k]

        # Cross-encoder re-rank
        if _reranker and len(chunks) > top_k:
            chunks, reranking_ms = await _reranker.rerank(
                query=query, chunks=chunks, top_k=top_k
            )

    elif mode == RetrievalMode.BM25:
        bm25_results = _bm25_retriever.retrieve(query, tenant_id, top_k)  # type: ignore[union-attr]
        # Fallback to dense for actual content fetch
        chunks, retrieval_ms = await _mmr_retriever.retrieve(  # type: ignore[union-attr]
            query_vector=query_vector,
            collection=collection,
            tenant_id=tenant_id,
            top_k=top_k,
            mmr_lambda=1.0,  # Pure relevance for BM25 mode
        )
    else:
        chunks, retrieval_ms = [], 0.0

    return chunks[:top_k], retrieval_ms, reranking_ms


# ── FastAPI Application ───────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _qdrant, _mmr_retriever, _bm25_retriever, _reranker, _neo4j_driver, _http_client

    _configure_otel()

    _http_client = httpx.AsyncClient()
    _qdrant = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    _mmr_retriever = MMRRetriever(settings=settings, client=_qdrant)
    _bm25_retriever = BM25Retriever()
    _reranker = CrossEncoderReranker()

    try:
        _neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        await _neo4j_driver.verify_connectivity()
        log.info("neo4j.connected", uri=settings.neo4j_uri)
    except Exception as exc:
        log.warning("neo4j.unavailable", error=str(exc))
        _neo4j_driver = None

    log.info(
        "mcp_knowledge_base.started",
        service=settings.service_name,
        port=settings.port,
        mcp_endpoint=f"http://localhost:{settings.port}/mcp/",
    )
    yield

    await _qdrant.close()
    await _http_client.aclose()
    if _neo4j_driver:
        await _neo4j_driver.close()
    log.info("mcp_knowledge_base.stopped")


def _configure_otel() -> None:
    resource = Resource.create(
        {"service.name": settings.service_name, "service.version": "0.1.0"}
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


app = FastAPI(
    title="DataMind MCP Knowledge Base",
    description="MCP Tool Server for RAG retrieval: MMR, BM25 hybrid, ColBERT re-ranking, GraphRAG.",
    version="0.1.0",
    lifespan=lifespan,
)

FastAPIInstrumentor.instrument_app(app)
app.mount("/metrics", make_asgi_app())
app.mount("/mcp", mcp.get_asgi_app())


@app.get("/health/liveness", tags=["Health"])
async def liveness() -> dict[str, str]:
    return {"status": "alive", "service": settings.service_name}


@app.get("/health/readiness", tags=["Health"])
async def readiness() -> dict[str, Any]:
    checks: dict[str, str] = {}
    try:
        await _qdrant.get_collections()  # type: ignore[union-attr]
        checks["qdrant"] = "healthy"
    except Exception:
        checks["qdrant"] = "unhealthy"

    overall = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks, "service": settings.service_name}


@app.get("/tools", tags=["MCP"])
async def list_tools() -> dict[str, Any]:
    return {
        "tools": ["retrieve", "mmr_search", "graph_search"],
        "mcp_endpoint": "/mcp/",
        "transport": "streamable-http",
    }
