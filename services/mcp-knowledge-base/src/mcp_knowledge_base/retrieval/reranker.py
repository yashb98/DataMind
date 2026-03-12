"""
MCP Knowledge Base — ColBERT-style cross-encoder re-ranking.
Day 9: Re-ranks top MMR/hybrid candidates for highest final relevance.

Uses sentence-transformers cross-encoder (ms-marco-MiniLM-L-6-v2) for
lightweight re-ranking without full ColBERT token-level interaction.
Replaces with ColBERT v2 when GPU budget allows.

Protocols: None (internal)
SOLID: SRP (re-ranking only), OCP (swap model = new class)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from mcp_knowledge_base.models import RetrievedChunk

log = structlog.get_logger(__name__)

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    """Re-ranks retrieved chunks using a cross-encoder model.

    The cross-encoder jointly encodes (query, document) pairs, providing
    higher-quality relevance scores than bi-encoder similarity alone.
    Runs in a thread pool to avoid blocking the async event loop.

    SLO: Reranking < 200ms for top-10 candidates (CPU inference).
    """

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        self._model_name = model_name
        self._model: Any = None  # Lazy load on first use

    def _load_model(self) -> None:
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self._model_name)
                log.info("reranker.model_loaded", model=self._model_name)
            except Exception as exc:
                log.warning(
                    "reranker.model_load_failed",
                    model=self._model_name,
                    error=str(exc),
                    fallback="score passthrough",
                )

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int | None = None,
    ) -> tuple[list[RetrievedChunk], float]:
        """Re-rank chunks using cross-encoder scoring.

        Args:
            query: Original query string.
            chunks: Retrieved chunks to re-rank.
            top_k: Optional cap on returned results.

        Returns:
            Tuple of (re-ranked chunks, reranking_ms).
        """
        if not chunks:
            return [], 0.0

        self._load_model()
        if self._model is None:
            # Fallback: return original order if model unavailable
            return chunks[:top_k] if top_k else chunks, 0.0

        loop = asyncio.get_event_loop()
        start = time.perf_counter()

        pairs = [(query, chunk.content) for chunk in chunks]

        def _sync_rerank() -> list[float]:
            return self._model.predict(pairs).tolist()  # type: ignore[no-any-return]

        scores: list[float] = await loop.run_in_executor(None, _sync_rerank)
        reranking_ms = (time.perf_counter() - start) * 1000

        # Attach cross-encoder scores and sort descending
        scored = sorted(
            zip(scores, chunks),
            key=lambda x: x[0],
            reverse=True,
        )

        # Normalise scores to [0, 1]
        if scored:
            max_score = scored[0][0]
            min_score = scored[-1][0]
            score_range = max(max_score - min_score, 1e-9)
        else:
            score_range = 1.0
            max_score = 1.0

        reranked: list[RetrievedChunk] = []
        for raw_score, chunk in scored:
            normalised = (raw_score - min_score) / score_range  # type: ignore[possibly-undefined]
            updated = chunk.model_copy(update={"score": round(float(normalised), 4)})
            reranked.append(updated)

        result = reranked[:top_k] if top_k else reranked

        log.info(
            "reranker.completed",
            input_count=len(chunks),
            output_count=len(result),
            reranking_ms=round(reranking_ms, 2),
            model=self._model_name,
        )

        return result, reranking_ms
