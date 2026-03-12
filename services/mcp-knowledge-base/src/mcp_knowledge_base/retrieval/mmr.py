"""
MCP Knowledge Base — Maximal Marginal Relevance (MMR) retrieval.
Day 9: λ=0.7 default, adaptive modes, max 3 chunks per source document.

MMR balances relevance and diversity:
    score(d) = λ * sim(d, query) - (1-λ) * max_sim(d, selected)

Protocols: None (internal)
SOLID: SRP (MMR algorithm only), OCP (new retriever = new class)
Benchmark: tests/benchmarks/bench_retrieval.py — SLO p99 < 2s
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np
import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, SearchRequest

from mcp_knowledge_base.config import Settings
from mcp_knowledge_base.models import RetrievedChunk, RetrievalMode

log = structlog.get_logger(__name__)


class MMRRetriever:
    """Maximal Marginal Relevance retrieval from Qdrant.

    Fetches top_k * 4 candidates via dense search, then applies MMR
    to select diverse final_k results. Enforces max_chunks_per_source cap.

    Attributes:
        _settings: Service configuration.
        _client: Async Qdrant client.
    """

    def __init__(self, settings: Settings, client: AsyncQdrantClient) -> None:
        self._settings = settings
        self._client = client

    async def retrieve(
        self,
        query_vector: list[float],
        collection: str,
        tenant_id: str,
        top_k: int,
        mmr_lambda: float | None = None,
        filters: dict[str, object] | None = None,
    ) -> tuple[list[RetrievedChunk], float]:
        """Retrieve diverse chunks via MMR algorithm.

        Args:
            query_vector: Dense embedding of the query (1024-dim).
            collection: Qdrant collection name.
            tenant_id: Tenant ID for payload filtering.
            top_k: Number of final chunks to return.
            mmr_lambda: Relevance-diversity trade-off (None = use settings default).
            filters: Additional Qdrant payload filters.

        Returns:
            Tuple of (ranked chunks list, retrieval_ms).
        """
        lam = mmr_lambda if mmr_lambda is not None else self._settings.mmr_lambda
        candidate_k = min(top_k * 4, 100)  # Fetch 4x candidates for MMR selection

        # Build Qdrant filter for tenant isolation
        qdrant_filter = _build_filter(tenant_id, filters)

        start = time.perf_counter()
        search_result = await self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=candidate_k,
            query_filter=qdrant_filter,
            with_payload=True,
            with_vectors=True,  # Need vectors for MMR distance computation
        )
        retrieval_ms = (time.perf_counter() - start) * 1000

        if not search_result:
            return [], retrieval_ms

        # Extract candidates: (score, vector, payload)
        candidates = [
            (
                hit.score,
                np.array(hit.vector, dtype=np.float32),  # type: ignore[arg-type]
                hit.payload or {},
                str(hit.id),
            )
            for hit in search_result
        ]

        # Apply MMR selection
        selected = _mmr_select(
            query_vector=np.array(query_vector, dtype=np.float32),
            candidates=candidates,
            top_k=top_k,
            lam=lam,
            max_per_source=self._settings.max_chunks_per_source,
        )

        staleness_cutoff = self._settings.staleness_threshold_days

        chunks: list[RetrievedChunk] = []
        for score, _, payload, chunk_id in selected:
            ingested_at = _parse_datetime(payload.get("ingested_at"))
            stale = _is_stale(ingested_at, staleness_cutoff)

            chunks.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    source_id=str(payload.get("source_id", "")),
                    source_type=str(payload.get("source_type", "document")),
                    content=str(payload.get("content", "")),
                    score=float(score),
                    tenant_id=tenant_id,
                    ingested_at=ingested_at,
                    stale=stale,
                    metadata={k: v for k, v in payload.items()
                              if k not in ("content", "tenant_id", "source_id", "source_type")},
                )
            )

        log.info(
            "mmr.retrieved",
            tenant_id=tenant_id,
            collection=collection,
            candidates=len(candidates),
            selected=len(chunks),
            lambda_used=lam,
            retrieval_ms=round(retrieval_ms, 2),
        )

        return chunks, retrieval_ms


# ── MMR Algorithm ─────────────────────────────────────────────────────────────


def _mmr_select(
    query_vector: np.ndarray,
    candidates: list[tuple[float, np.ndarray, dict[str, object], str]],
    top_k: int,
    lam: float,
    max_per_source: int,
) -> list[tuple[float, np.ndarray, dict[str, object], str]]:
    """Apply MMR selection over candidate set.

    MMR score = λ * sim(doc, query) - (1-λ) * max_{s in selected} sim(doc, s)

    Args:
        query_vector: Query embedding.
        candidates: List of (relevance_score, vector, payload, id) tuples.
        top_k: Number of results to select.
        lam: Relevance-diversity balance (0=diverse, 1=relevant).
        max_per_source: Max chunks allowed per source_id.

    Returns:
        Selected candidates in MMR ranking order.
    """
    if not candidates:
        return []

    q = query_vector / (np.linalg.norm(query_vector) + 1e-9)
    selected: list[tuple[float, np.ndarray, dict[str, object], str]] = []
    source_counts: dict[str, int] = {}
    remaining = list(candidates)

    while len(selected) < top_k and remaining:
        best_score = -float("inf")
        best_idx = 0

        for i, (relevance, vec, payload, cid) in enumerate(remaining):
            # Check source cap
            source_id = str(payload.get("source_id", cid))
            if source_counts.get(source_id, 0) >= max_per_source:
                continue

            v = vec / (np.linalg.norm(vec) + 1e-9)
            rel_score = float(np.dot(q, v))  # Cosine similarity to query

            if not selected:
                mmr_score = lam * rel_score
            else:
                # Max similarity to already-selected documents
                max_sim_to_selected = max(
                    float(np.dot(v, s_vec / (np.linalg.norm(s_vec) + 1e-9)))
                    for _, s_vec, _, _ in selected
                )
                mmr_score = lam * rel_score - (1 - lam) * max_sim_to_selected

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i

        item = remaining.pop(best_idx)
        selected.append(item)
        source_id = str(item[2].get("source_id", item[3]))
        source_counts[source_id] = source_counts.get(source_id, 0) + 1

    return selected


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_filter(tenant_id: str, extra: dict[str, object] | None) -> Filter:
    conditions = [
        FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
    ]
    if extra:
        for key, value in extra.items():
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
    return Filter(must=conditions)


def _parse_datetime(val: object) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None
    return None


def _is_stale(ingested_at: datetime | None, threshold_days: int) -> bool:
    """L7 Temporal Grounding: flag chunks older than threshold."""
    if ingested_at is None:
        return False
    now = datetime.now(tz=timezone.utc)
    if ingested_at.tzinfo is None:
        ingested_at = ingested_at.replace(tzinfo=timezone.utc)
    age_days = (now - ingested_at).days
    return age_days > threshold_days
