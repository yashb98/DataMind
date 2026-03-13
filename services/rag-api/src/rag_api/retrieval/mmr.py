"""
RAG API — Maximal Marginal Relevance (MMR) Retrieval.
Day 22: Phase 5 — λ-adaptive diverse retrieval from Qdrant knowledge_base.

MMR score: λ * sim(d, query) - (1-λ) * max_{s∈selected} sim(d, s)
λ=0.9 precise | λ=0.7 default | λ=0.5 exploratory

Protocols: None
SOLID: SRP (MMR algorithm only), OCP (extend by subclassing), DIP (client injected)
Benchmark: tests/benchmarks/bench_rag.py — SLO p99 < 2s
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx
import numpy as np
import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchValue
from tenacity import retry, stop_after_attempt, wait_exponential

from rag_api.config import Settings
from rag_api.models import MMRMode, RetrievedChunk

log = structlog.get_logger(__name__)


class MMRRetriever:
    """Maximal Marginal Relevance retrieval from Qdrant.

    Fetches ``top_k * 3`` candidates via dense search, applies the MMR
    selection loop, enforces ``max_chunks_per_source`` cap (L7: prevent
    one document from flooding results), and flags stale chunks (>90 days).

    Attributes:
        _qdrant: Async Qdrant client.
        _http: Async HTTP client for embedding service.
        _settings: Service configuration.
    """

    def __init__(
        self,
        qdrant: AsyncQdrantClient,
        http: httpx.AsyncClient,
        settings: Settings,
    ) -> None:
        self._qdrant = qdrant
        self._http = http
        self._settings = settings

    # ── Public API ────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        collection: str = "knowledge_base",
        top_k: int = 10,
        lambda_param: float | None = None,
        mode: MMRMode = MMRMode.DEFAULT,
    ) -> tuple[list[RetrievedChunk], float]:
        """Retrieve diverse, relevant chunks using MMR.

        Steps:
        1. Embed query via embedding service.
        2. Fetch ``top_k * 3`` dense candidates from Qdrant with tenant filter.
        3. Apply MMR selection loop (vectorised cosine arithmetic).
        4. Enforce ``max_chunks_per_source`` = 3.
        5. Flag stale chunks (ingestion_date > 90 days).

        Args:
            query: Natural language search query.
            tenant_id: Tenant isolation key.
            collection: Qdrant collection name.
            top_k: Number of final chunks to return.
            lambda_param: Override λ (takes priority over mode).
            mode: Preset λ mode — "precise" (0.9), "default" (0.7), "exploratory" (0.5).

        Returns:
            Tuple of (selected chunks, retrieval_ms).
        """
        lam = _resolve_lambda(lambda_param, mode, self._settings)
        candidate_k = min(top_k * 3, 100)

        # 1. Embed query
        query_vec, embed_ms = await self._embed_with_timing(query)
        q_arr = np.array(query_vec, dtype=np.float32)

        # 2. Dense candidates from Qdrant
        t0 = time.perf_counter()
        tenant_filter = Filter(
            must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        )
        search_results = await self._qdrant.search(
            collection_name=collection,
            query_vector=query_vec,
            limit=candidate_k,
            query_filter=tenant_filter,
            with_payload=True,
            with_vectors=True,
        )
        retrieval_ms = (time.perf_counter() - t0) * 1000

        if not search_results:
            return [], retrieval_ms

        # 3. Prepare candidates: (score, np.array, payload, chunk_id)
        candidates: list[tuple[float, np.ndarray, dict[str, Any], str]] = []
        for hit in search_results:
            raw_vec = hit.vector
            if raw_vec is None:
                continue
            vec = np.array(raw_vec, dtype=np.float32)
            candidates.append((hit.score, vec, hit.payload or {}, str(hit.id)))

        # 4. MMR selection
        selected = _mmr_select(
            query_vector=q_arr,
            candidates=candidates,
            top_k=top_k,
            lam=lam,
            max_per_source=self._settings.max_chunks_per_source,
        )

        # 5. Build result chunks with staleness flags
        chunks = _build_chunks(selected, tenant_id, self._settings.staleness_days)

        log.info(
            "mmr.retrieved",
            tenant_id=tenant_id,
            collection=collection,
            candidates=len(candidates),
            selected=len(chunks),
            lambda_used=lam,
            mode=mode.value,
            embed_ms=round(embed_ms, 1),
            retrieval_ms=round(retrieval_ms, 1),
        )
        return chunks, retrieval_ms

    # ── Internal ──────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
    async def _embed_with_timing(self, text: str) -> tuple[list[float], float]:
        """Call embedding service and return (vector, latency_ms)."""
        t0 = time.perf_counter()
        response = await self._http.post(
            f"{self._settings.embedding_service_url}/embed",
            json={"texts": [text]},
            timeout=15.0,
        )
        response.raise_for_status()
        elapsed = (time.perf_counter() - t0) * 1000
        return response.json()["embeddings"][0], elapsed


# ── MMR Algorithm ─────────────────────────────────────────────────────────────


def _mmr_select(
    query_vector: np.ndarray,
    candidates: list[tuple[float, np.ndarray, dict[str, Any], str]],
    top_k: int,
    lam: float,
    max_per_source: int,
) -> list[tuple[float, np.ndarray, dict[str, Any], str]]:
    """Apply MMR greedy selection over the candidate set.

    MMR score = λ * sim(doc, query) - (1-λ) * max_{s∈selected} sim(doc, s)

    Args:
        query_vector: Query embedding (1024-dim).
        candidates: List of (relevance_score, vector, payload, chunk_id).
        top_k: Number of documents to select.
        lam: Relevance-diversity balance (0=fully diverse, 1=fully relevant).
        max_per_source: Maximum chunks selected from the same source_id.

    Returns:
        Selected candidates in MMR ranking order.
    """
    if not candidates:
        return []

    q = query_vector / (np.linalg.norm(query_vector) + 1e-9)
    selected: list[tuple[float, np.ndarray, dict[str, Any], str]] = []
    source_counts: dict[str, int] = {}
    remaining = list(candidates)

    while len(selected) < top_k and remaining:
        best_score = -float("inf")
        best_idx = 0
        found_valid = False

        for i, (_, vec, payload, cid) in enumerate(remaining):
            source_id = str(payload.get("source_id", cid))
            if source_counts.get(source_id, 0) >= max_per_source:
                continue

            v = vec / (np.linalg.norm(vec) + 1e-9)
            rel_score = float(np.dot(q, v))

            if not selected:
                mmr_score = lam * rel_score
            else:
                selected_vecs = np.stack([s[1] / (np.linalg.norm(s[1]) + 1e-9) for s in selected])
                sims_to_selected = np.dot(selected_vecs, v)
                max_sim = float(np.max(sims_to_selected))
                mmr_score = lam * rel_score - (1.0 - lam) * max_sim

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i
                found_valid = True

        if not found_valid:
            break

        item = remaining.pop(best_idx)
        selected.append(item)
        src = str(item[2].get("source_id", item[3]))
        source_counts[src] = source_counts.get(src, 0) + 1

    return selected


# ── Helpers ───────────────────────────────────────────────────────────────────


def _resolve_lambda(
    override: float | None,
    mode: MMRMode,
    settings: Settings,
) -> float:
    """Resolve effective λ from explicit override or mode preset."""
    if override is not None:
        return override
    return {
        MMRMode.PRECISE: settings.mmr_lambda_precise,
        MMRMode.EXPLORATORY: settings.mmr_lambda_exploratory,
        MMRMode.DEFAULT: settings.mmr_lambda,
    }.get(mode, settings.mmr_lambda)


def _build_chunks(
    selected: list[tuple[float, np.ndarray, dict[str, Any], str]],
    tenant_id: str,
    staleness_days: int,
) -> list[RetrievedChunk]:
    """Build RetrievedChunk objects from MMR-selected candidates."""
    now = datetime.now(tz=timezone.utc)
    chunks: list[RetrievedChunk] = []

    for score, _, payload, chunk_id in selected:
        ingestion_raw = payload.get("ingested_at") or payload.get("ingestion_date")
        ingestion_date: datetime | None = None

        if isinstance(ingestion_raw, str):
            try:
                ingestion_date = datetime.fromisoformat(ingestion_raw)
            except ValueError:
                pass
        elif isinstance(ingestion_raw, datetime):
            ingestion_date = ingestion_raw

        # L7 temporal grounding: flag stale chunks
        stale = False
        if ingestion_date is not None:
            idt = ingestion_date
            if idt.tzinfo is None:
                idt = idt.replace(tzinfo=timezone.utc)
            stale = (now - idt).days > staleness_days

        chunks.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                source_id=str(payload.get("source_id", chunk_id)),
                content=str(payload.get("content", "")),
                score=min(1.0, max(0.0, float(score))),
                stale=stale,
                ingestion_date=ingestion_date,
                metadata={
                    k: v
                    for k, v in payload.items()
                    if k not in ("content", "tenant_id", "source_id", "ingested_at", "ingestion_date")
                },
            )
        )

    return chunks
