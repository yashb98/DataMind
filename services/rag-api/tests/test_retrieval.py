"""
RAG API — Unit tests for MMR retrieval and RAGAS evaluator.
Day 22: Phase 5 — Tests for MMRRetriever, ColBERTReranker, RAGASEvaluator.

Coverage target: ≥80%
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from rag_api.models import MMRMode, RAGASResult, RetrievedChunk
from rag_api.retrieval.mmr import MMRRetriever, _mmr_select, _build_chunks, _resolve_lambda
from rag_api.retrieval.reranker import ColBERTReranker


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_candidate(
    score: float = 0.9,
    source_id: str = "doc-1",
    content: str = "some content",
    chunk_id: str = "c1",
) -> tuple[float, np.ndarray, dict[str, Any], str]:
    vec = np.random.rand(8).astype(np.float32)
    payload: dict[str, Any] = {
        "source_id": source_id,
        "content": content,
        "tenant_id": "t1",
    }
    return score, vec, payload, chunk_id


# ── MMR Algorithm ─────────────────────────────────────────────────────────────


def test_mmr_select_empty_candidates() -> None:
    """MMR select returns empty list for empty candidate set."""
    result = _mmr_select(
        query_vector=np.random.rand(8).astype(np.float32),
        candidates=[],
        top_k=5,
        lam=0.7,
        max_per_source=3,
    )
    assert result == []


def test_mmr_select_respects_top_k() -> None:
    """MMR select returns at most top_k items."""
    candidates = [_make_candidate(chunk_id=f"c{i}", source_id=f"doc-{i}") for i in range(10)]
    result = _mmr_select(
        query_vector=np.random.rand(8).astype(np.float32),
        candidates=candidates,
        top_k=3,
        lam=0.7,
        max_per_source=3,
    )
    assert len(result) <= 3


def test_mmr_select_max_chunks_per_source() -> None:
    """MMR select never selects more than max_per_source chunks from one source."""
    # All candidates from the same source
    candidates = [
        _make_candidate(chunk_id=f"c{i}", source_id="same-doc", score=0.9 - i * 0.01)
        for i in range(10)
    ]
    result = _mmr_select(
        query_vector=np.random.rand(8).astype(np.float32),
        candidates=candidates,
        top_k=10,
        lam=0.7,
        max_per_source=3,
    )
    assert len(result) == 3  # Hard cap at 3 per source


def test_resolve_lambda_explicit_override() -> None:
    """Explicit lambda_param takes priority over mode."""
    from rag_api.config import Settings
    settings = Settings()
    lam = _resolve_lambda(override=0.42, mode=MMRMode.PRECISE, settings=settings)
    assert lam == 0.42


def test_resolve_lambda_mode_mapping() -> None:
    """Mode presets map to correct lambda values."""
    from rag_api.config import Settings
    s = Settings()
    assert _resolve_lambda(None, MMRMode.PRECISE, s) == s.mmr_lambda_precise
    assert _resolve_lambda(None, MMRMode.EXPLORATORY, s) == s.mmr_lambda_exploratory
    assert _resolve_lambda(None, MMRMode.DEFAULT, s) == s.mmr_lambda


# ── build_chunks ──────────────────────────────────────────────────────────────


def test_build_chunks_stale_flag() -> None:
    """build_chunks flags chunks older than staleness_days as stale."""
    old_date = datetime.now(tz=timezone.utc) - timedelta(days=100)
    vec = np.random.rand(8).astype(np.float32)
    candidate = (
        0.8,
        vec,
        {
            "source_id": "doc-1",
            "content": "old content",
            "ingested_at": old_date.isoformat(),
        },
        "c1",
    )
    chunks = _build_chunks([candidate], tenant_id="t1", staleness_days=90)
    assert len(chunks) == 1
    assert chunks[0].stale is True


def test_build_chunks_fresh_not_stale() -> None:
    """build_chunks does not flag recent chunks as stale."""
    recent_date = datetime.now(tz=timezone.utc) - timedelta(days=10)
    vec = np.random.rand(8).astype(np.float32)
    candidate = (
        0.9,
        vec,
        {
            "source_id": "doc-2",
            "content": "fresh content",
            "ingested_at": recent_date.isoformat(),
        },
        "c2",
    )
    chunks = _build_chunks([candidate], tenant_id="t1", staleness_days=90)
    assert chunks[0].stale is False


# ── ColBERTReranker ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reranker_reorders_by_score() -> None:
    """Reranker reorders chunks by descending cross-encoder score."""
    mock_http = AsyncMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"scores": [0.3, 0.9, 0.6]})
    mock_http.post = AsyncMock(return_value=mock_response)

    from rag_api.config import Settings
    reranker = ColBERTReranker(http=mock_http, settings=Settings())  # type: ignore[arg-type]

    chunks = [
        RetrievedChunk(chunk_id="c1", source_id="s1", content="low", score=0.5),
        RetrievedChunk(chunk_id="c2", source_id="s2", content="high", score=0.4),
        RetrievedChunk(chunk_id="c3", source_id="s3", content="mid", score=0.6),
    ]

    result, elapsed = await reranker.rerank(query="test", chunks=chunks, top_k=3)

    assert result[0].content == "high"   # score 0.9
    assert result[1].content == "mid"    # score 0.6
    assert result[2].content == "low"    # score 0.3


@pytest.mark.asyncio
async def test_reranker_graceful_fallback_on_error() -> None:
    """Reranker returns original order when endpoint is unavailable."""
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(side_effect=Exception("connection refused"))

    from rag_api.config import Settings
    reranker = ColBERTReranker(http=mock_http, settings=Settings())  # type: ignore[arg-type]

    chunks = [
        RetrievedChunk(chunk_id="c1", source_id="s1", content="a", score=0.7),
        RetrievedChunk(chunk_id="c2", source_id="s2", content="b", score=0.5),
    ]

    result, _ = await reranker.rerank(query="test", chunks=chunks)
    # Order preserved
    assert result[0].chunk_id == "c1"
    assert result[1].chunk_id == "c2"


# ── RAGASResult model ─────────────────────────────────────────────────────────


def test_ragas_result_score_bounds() -> None:
    """RAGASResult accepts valid scores in [0, 1]."""
    r = RAGASResult(
        faithfulness=0.85,
        answer_relevancy=0.72,
        context_recall=0.91,
        run_id="run-123",
        tenant_id="t1",
    )
    assert r.faithfulness == 0.85
    assert r.answer_relevancy == 0.72
    assert r.context_recall == 0.91


def test_ragas_result_context_recall_optional() -> None:
    """RAGASResult context_recall is optional (None when no ground truth)."""
    r = RAGASResult(faithfulness=0.7, answer_relevancy=0.8)
    assert r.context_recall is None
