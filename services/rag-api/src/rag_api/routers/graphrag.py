"""
RAG API — GraphRAG Router.
Day 22: Phase 5 — Entity extraction, Neo4j community traversal, DSR erasure.

Endpoints:
  POST   /api/graphrag/ingest          — extract entities + store in Neo4j
  POST   /api/graphrag/search          — community context retrieval for query
  DELETE /api/graphrag/{tenant_id}     — DSR erasure from Neo4j

Protocols: None (REST)
SOLID: SRP (routing only), DIP (GraphRAGPipeline from app.state)
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from prometheus_client import Counter, Histogram

from rag_api.models import (
    GraphDSRResponse,
    GraphIngestRequest,
    GraphIngestResponse,
    GraphSearchRequest,
    GraphSearchResponse,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/graphrag", tags=["GraphRAG"])

# ── Prometheus Metrics ────────────────────────────────────────────────────────

GRAPHRAG_OPS = Counter(
    "rag_api_graphrag_ops_total",
    "GraphRAG operations",
    ["operation", "status"],
)
GRAPHRAG_LATENCY = Histogram(
    "rag_api_graphrag_latency_ms",
    "GraphRAG operation latency in milliseconds",
    ["operation"],
    buckets=[100, 500, 1000, 3000, 8000, 15000],
)


# ── Dependency ────────────────────────────────────────────────────────────────


def _get_graphrag_pipeline(request: Request) -> Any:
    pipeline = getattr(request.app.state, "graphrag_pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="GraphRAGPipeline not initialised")
    return pipeline


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/ingest", response_model=GraphIngestResponse)
async def ingest_text(
    body: GraphIngestRequest,
    request: Request,
) -> GraphIngestResponse:
    """Extract entities and relationships from text, persist to Neo4j.

    Pipeline:
    1. EntityExtractor calls LiteLLM → structured JSON (entities + relationships)
    2. GraphRAGStore MERGE-upserts Entity nodes and RELATED_TO edges

    All nodes carry ``tenant_id`` for multi-tenant isolation.

    Args:
        body: GraphIngestRequest with text, tenant_id, and optional source_id.

    Returns:
        GraphIngestResponse with counts of upserted entities and relationships.
    """
    t0 = time.perf_counter()
    pipeline = _get_graphrag_pipeline(request)
    bound_log = log.bind(tenant_id=body.tenant_id, source_id=body.source_id)

    try:
        result = await pipeline.ingest(
            text=body.text,
            tenant_id=body.tenant_id,
            source_id=body.source_id,
        )

        elapsed = (time.perf_counter() - t0) * 1000
        GRAPHRAG_LATENCY.labels(operation="ingest").observe(elapsed)
        GRAPHRAG_OPS.labels(operation="ingest", status="ok").inc()

        bound_log.info(
            "graphrag.ingest.ok",
            entities=result.entities_upserted,
            relationships=result.relationships_upserted,
            latency_ms=round(elapsed, 1),
        )
        return result

    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        GRAPHRAG_LATENCY.labels(operation="ingest").observe(elapsed)
        GRAPHRAG_OPS.labels(operation="ingest", status="error").inc()
        bound_log.error("graphrag.ingest.failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"GraphRAG ingest failed: {exc}") from exc


@router.post("/search", response_model=GraphSearchResponse)
async def search_graph(
    body: GraphSearchRequest,
    request: Request,
) -> GraphSearchResponse:
    """Retrieve community context for a natural language query via Neo4j traversal.

    Pipeline:
    1. Extract query entities inline (lightweight LLM call)
    2. 1..max_hops neighbourhood traversal from query entities
    3. Return community descriptions as context strings for RAG prompts

    Args:
        body: GraphSearchRequest with query, tenant_id, max_hops, and limit.

    Returns:
        GraphSearchResponse with community summaries and related entity details.
    """
    t0 = time.perf_counter()
    pipeline = _get_graphrag_pipeline(request)
    bound_log = log.bind(tenant_id=body.tenant_id)

    try:
        result = await pipeline.search(
            query=body.query,
            tenant_id=body.tenant_id,
            max_hops=body.max_hops,
            limit=body.limit,
        )

        elapsed = (time.perf_counter() - t0) * 1000
        GRAPHRAG_LATENCY.labels(operation="search").observe(elapsed)
        GRAPHRAG_OPS.labels(operation="search", status="ok").inc()

        bound_log.info(
            "graphrag.search.ok",
            summaries=len(result.community_summaries),
            entities=result.total,
            latency_ms=round(elapsed, 1),
        )
        return result

    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        GRAPHRAG_LATENCY.labels(operation="search").observe(elapsed)
        GRAPHRAG_OPS.labels(operation="search", status="error").inc()
        bound_log.error("graphrag.search.failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"GraphRAG search failed: {exc}") from exc


@router.delete("/{tenant_id}", response_model=GraphDSRResponse)
async def erase_tenant_graph(
    tenant_id: str,
    request: Request,
) -> GraphDSRResponse:
    """GDPR Art.17 erasure — delete ALL Neo4j nodes and relationships for a tenant.

    Uses DETACH DELETE to cleanly remove all edges before node deletion.
    Called as part of the DSR Subject Erasure Request pipeline.

    Args:
        tenant_id: Tenant whose graph data to erase.

    Returns:
        GraphDSRResponse with count of deleted nodes.
    """
    t0 = time.perf_counter()
    pipeline = _get_graphrag_pipeline(request)
    bound_log = log.bind(tenant_id=tenant_id)
    bound_log.info("graphrag.dsr_erase.start")

    try:
        store = pipeline._store  # Access store directly for deletion
        deleted = await store.delete_tenant(tenant_id=tenant_id)

        elapsed = (time.perf_counter() - t0) * 1000
        GRAPHRAG_LATENCY.labels(operation="dsr_erase").observe(elapsed)
        GRAPHRAG_OPS.labels(operation="dsr_erase", status="ok").inc()

        bound_log.info(
            "graphrag.dsr_erase.ok",
            nodes_deleted=deleted,
            latency_ms=round(elapsed, 1),
        )
        return GraphDSRResponse(tenant_id=tenant_id, nodes_deleted=deleted)

    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        GRAPHRAG_LATENCY.labels(operation="dsr_erase").observe(elapsed)
        GRAPHRAG_OPS.labels(operation="dsr_erase", status="error").inc()
        bound_log.error("graphrag.dsr_erase.failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"GraphRAG DSR erase failed: {exc}") from exc
