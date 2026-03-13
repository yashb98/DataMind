"""
RAG API — ColBERT Re-Ranker (stub delegating to embedding service).
Day 22: Phase 5 — Re-rank retrieved chunks using cross-encoder scoring via HTTP.

In production: ColBERT or a cross-encoder model is hosted alongside the
embedding service. This client calls the /rerank endpoint if available,
and falls back to preserving the original MMR order gracefully.

Protocols: None
SOLID: SRP (re-ranking only), OCP (swap model by changing endpoint), DIP (client injected)
"""

from __future__ import annotations

import time

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from rag_api.config import Settings
from rag_api.models import RetrievedChunk

log = structlog.get_logger(__name__)


class ColBERTReranker:
    """Cross-encoder re-ranker delegating to the embedding service.

    Calls ``POST /rerank`` on the embedding service with (query, passages) pairs.
    If the endpoint is unavailable the original MMR-ordered list is returned
    unchanged — degraded precision, never an error.

    Attributes:
        _http: Async HTTP client.
        _settings: Service configuration.
    """

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int | None = None,
    ) -> tuple[list[RetrievedChunk], float]:
        """Re-rank chunks by cross-encoder relevance score.

        Sends the query and all chunk contents to the embedding service's
        ``/rerank`` endpoint. Falls back to original order on any error.

        Args:
            query: The original search query.
            chunks: Candidate chunks from MMR retrieval.
            top_k: Max results to return after re-ranking. Defaults to len(chunks).

        Returns:
            Tuple of (re-ranked chunks, reranking_ms).
        """
        if not chunks:
            return [], 0.0

        if top_k is None:
            top_k = len(chunks)

        t0 = time.perf_counter()
        try:
            scores = await self._call_rerank_endpoint(
                query=query,
                passages=[c.content for c in chunks],
            )
            elapsed = (time.perf_counter() - t0) * 1000

            # Attach cross-encoder scores and sort descending
            scored = [
                chunk.model_copy(update={"score": scores[i]})
                for i, chunk in enumerate(chunks)
            ]
            scored.sort(key=lambda c: c.score, reverse=True)

            log.debug(
                "reranker.completed",
                input_count=len(chunks),
                output_count=top_k,
                reranking_ms=round(elapsed, 1),
            )
            return scored[:top_k], elapsed

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            log.warning(
                "reranker.fallback",
                reason=str(exc),
                chunks_preserved=len(chunks),
            )
            # Graceful degradation: return original MMR order
            return chunks[:top_k], elapsed

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.3, min=0.3, max=2))
    async def _call_rerank_endpoint(
        self, query: str, passages: list[str]
    ) -> list[float]:
        """Call embedding service /rerank endpoint.

        Args:
            query: Search query.
            passages: List of passage strings to score.

        Returns:
            List of float scores, one per passage.

        Raises:
            httpx.HTTPStatusError: If the service returns a non-2xx response.
        """
        response = await self._http.post(
            f"{self._settings.embedding_service_url}/rerank",
            json={"query": query, "passages": passages},
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
        return [float(s) for s in data["scores"]]
