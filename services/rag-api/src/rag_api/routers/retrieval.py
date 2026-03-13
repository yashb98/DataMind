"""
RAG API — Retrieval Router.
Day 22: Phase 5 — MMR retrieval and RAGAS evaluation endpoints.

Endpoints:
  POST /api/retrieval/mmr      — MMR retrieval from knowledge_base
  POST /api/retrieval/evaluate — RAGAS quality evaluation

Protocols: None (REST)
SOLID: SRP (routing only), DIP (MMRRetriever + RAGASEvaluator from app.state)
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from prometheus_client import Counter, Histogram

from rag_api.models import (
    EvaluateRequest,
    MMRRetrievalRequest,
    MMRRetrievalResponse,
    MMRMode,
    RAGASResult,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/retrieval", tags=["Retrieval"])

# ── Prometheus Metrics ────────────────────────────────────────────────────────

RETRIEVAL_OPS = Counter(
    "rag_api_retrieval_ops_total",
    "Retrieval operations",
    ["operation", "mode", "status"],
)
RETRIEVAL_LATENCY = Histogram(
    "rag_api_retrieval_latency_ms",
    "Retrieval operation latency in milliseconds",
    ["operation"],
    buckets=[50, 100, 300, 600, 1200, 2000, 5000],
)


# ── Dependencies ──────────────────────────────────────────────────────────────


def _get_mmr_retriever(request: Request) -> Any:
    retriever = getattr(request.app.state, "mmr_retriever", None)
    if retriever is None:
        raise HTTPException(status_code=503, detail="MMRRetriever not initialised")
    return retriever


def _get_ragas_evaluator(request: Request) -> Any:
    evaluator = getattr(request.app.state, "ragas_evaluator", None)
    if evaluator is None:
        raise HTTPException(status_code=503, detail="RAGASEvaluator not initialised")
    return evaluator


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/mmr", response_model=MMRRetrievalResponse)
async def mmr_retrieve(
    body: MMRRetrievalRequest,
    request: Request,
) -> MMRRetrievalResponse:
    """Retrieve diverse, relevant chunks using Maximal Marginal Relevance.

    MMR balances relevance (sim to query) and diversity (dissimilarity to
    already-selected chunks). Enforces max 3 chunks per source document to
    prevent one document from flooding the result set (L7 temporal grounding).

    Mode presets:
      - ``default``     → λ=0.7 (balanced)
      - ``precise``     → λ=0.9 (maximise relevance, less diversity)
      - ``exploratory`` → λ=0.5 (maximise diversity)

    Args:
        body: MMRRetrievalRequest with query, tenant_id, collection, top_k, mode.

    Returns:
        MMRRetrievalResponse with chunks, stale count, and latency.
    """
    t0 = time.perf_counter()
    retriever = _get_mmr_retriever(request)
    bound_log = log.bind(tenant_id=body.tenant_id, collection=body.collection)

    try:
        chunks, retrieval_ms = await retriever.retrieve(
            query=body.query,
            tenant_id=body.tenant_id,
            collection=body.collection,
            top_k=body.top_k,
            lambda_param=body.lambda_param,
            mode=body.mode,
        )

        elapsed = (time.perf_counter() - t0) * 1000
        RETRIEVAL_LATENCY.labels(operation="mmr").observe(elapsed)
        RETRIEVAL_OPS.labels(operation="mmr", mode=body.mode.value, status="ok").inc()

        stale_count = sum(1 for c in chunks if c.stale)

        # Resolve the actual lambda used
        from rag_api.config import settings as _settings
        lambda_map = {
            MMRMode.PRECISE: _settings.mmr_lambda_precise,
            MMRMode.EXPLORATORY: _settings.mmr_lambda_exploratory,
            MMRMode.DEFAULT: _settings.mmr_lambda,
        }
        lambda_used = body.lambda_param if body.lambda_param is not None else lambda_map.get(
            body.mode, _settings.mmr_lambda
        )

        bound_log.info(
            "retrieval.mmr.ok",
            chunks=len(chunks),
            stale=stale_count,
            latency_ms=round(elapsed, 1),
        )

        return MMRRetrievalResponse(
            chunks=chunks,
            total_candidates=len(chunks),
            lambda_used=lambda_used,
            retrieval_ms=round(retrieval_ms, 2),
            stale_count=stale_count,
        )

    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        RETRIEVAL_LATENCY.labels(operation="mmr").observe(elapsed)
        RETRIEVAL_OPS.labels(operation="mmr", mode=body.mode.value, status="error").inc()
        bound_log.error("retrieval.mmr.failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MMR retrieval failed: {exc}") from exc


@router.post("/evaluate", response_model=RAGASResult)
async def evaluate_rag(
    body: EvaluateRequest,
    request: Request,
) -> RAGASResult:
    """Run RAGAS-style evaluation on a question-answer-context triplet.

    Computes 3 metrics logged to MLflow:
      - faithfulness:      fraction of claims in answer supported by contexts (NLI)
      - answer_relevancy:  cosine sim(embed(answer), embed(question))
      - context_recall:    fraction of ground truth facts covered (if ground_truth provided)

    Args:
        body: EvaluateRequest with question, answer, contexts, and optional ground_truth.

    Returns:
        RAGASResult with all metric scores and MLflow run_id.
    """
    t0 = time.perf_counter()
    evaluator = _get_ragas_evaluator(request)
    bound_log = log.bind(tenant_id=body.tenant_id)

    try:
        result = await evaluator.evaluate(
            question=body.question,
            answer=body.answer,
            contexts=body.contexts,
            ground_truth=body.ground_truth,
            tenant_id=body.tenant_id,
            run_name=body.run_name,
        )

        elapsed = (time.perf_counter() - t0) * 1000
        RETRIEVAL_LATENCY.labels(operation="evaluate").observe(elapsed)
        RETRIEVAL_OPS.labels(operation="evaluate", mode="ragas", status="ok").inc()

        bound_log.info(
            "retrieval.evaluate.ok",
            faithfulness=result.faithfulness,
            answer_relevancy=result.answer_relevancy,
            latency_ms=round(elapsed, 1),
        )
        return result

    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        RETRIEVAL_LATENCY.labels(operation="evaluate").observe(elapsed)
        RETRIEVAL_OPS.labels(operation="evaluate", mode="ragas", status="error").inc()
        bound_log.error("retrieval.evaluate.failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"RAGAS evaluation failed: {exc}") from exc
