"""
MCP Knowledge Base — BM25 sparse retrieval for hybrid search fusion.
Day 9: BM25s (Okapi BM25) over in-memory corpus for keyword matching.

Hybrid fusion: 0.3 * BM25_score + 0.7 * dense_score (Reciprocal Rank Fusion variant).

Protocols: None (internal)
SOLID: SRP (BM25 only), OCP (swap BM25 variant = new class)
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import structlog

log = structlog.get_logger(__name__)


class BM25Retriever:
    """In-memory BM25 retrieval over a document corpus.

    Maintains a per-tenant in-memory index. In production, this would be
    backed by Elasticsearch/OpenSearch with a BM25 scorer.
    For the DataMind dev environment, uses the bm25s library.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        # tenant_id → (corpus_texts, bm25_retriever_instance)
        self._indexes: dict[str, Any] = {}

    def index_documents(
        self,
        tenant_id: str,
        documents: list[dict[str, object]],
    ) -> None:
        """Build BM25 index for tenant documents.

        Args:
            tenant_id: Tenant identifier.
            documents: List of dicts with "chunk_id" and "content" keys.
        """
        try:
            import bm25s

            corpus = [str(doc.get("content", "")) for doc in documents]
            tokenised = bm25s.tokenize(corpus)
            retriever = bm25s.BM25(k1=self._k1, b=self._b)
            retriever.index(tokenised)
            self._indexes[tenant_id] = {
                "retriever": retriever,
                "docs": documents,
                "tokenised": tokenised,
            }
            log.info("bm25.indexed", tenant_id=tenant_id, doc_count=len(documents))
        except ImportError:
            log.warning("bm25.unavailable", reason="bm25s not installed, skipping BM25 index")

    def retrieve(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 20,
    ) -> list[tuple[str, float]]:
        """Retrieve top-k documents by BM25 score.

        Args:
            query: Search query string.
            tenant_id: Tenant identifier.
            top_k: Number of results to return.

        Returns:
            List of (chunk_id, normalised_bm25_score) tuples, descending by score.
        """
        index = self._indexes.get(tenant_id)
        if index is None:
            log.debug("bm25.no_index", tenant_id=tenant_id)
            return []

        try:
            import bm25s

            query_tokens = bm25s.tokenize([query])
            results, scores = index["retriever"].retrieve(
                query_tokens, corpus=None, k=min(top_k, len(index["docs"]))
            )
            docs = index["docs"]
            # Normalise scores to [0, 1]
            max_score = float(np.max(scores)) if scores.size > 0 else 1.0
            if max_score == 0:
                max_score = 1.0

            return [
                (str(docs[idx]["chunk_id"]), float(scores[0][i]) / max_score)
                for i, idx in enumerate(results[0])
            ]
        except Exception as exc:
            log.warning("bm25.retrieve_failed", error=str(exc), tenant_id=tenant_id)
            return []


def hybrid_fusion(
    dense_results: list[tuple[str, float]],
    bm25_results: list[tuple[str, float]],
    dense_weight: float = 0.7,
    bm25_weight: float = 0.3,
) -> list[tuple[str, float]]:
    """Fuse dense and BM25 scores using Reciprocal Rank Fusion (RRF).

    RRF score = dense_weight * (1 / (rank_d + 60)) + bm25_weight * (1 / (rank_b + 60))
    Then normalised to [0, 1].

    Args:
        dense_results: List of (chunk_id, dense_score) from vector search.
        bm25_results: List of (chunk_id, bm25_score) from BM25.
        dense_weight: Weight for dense retrieval component.
        bm25_weight: Weight for BM25 component.

    Returns:
        Fused and re-ranked list of (chunk_id, fused_score).
    """
    k = 60  # RRF constant
    scores: dict[str, float] = {}

    for rank, (chunk_id, _) in enumerate(dense_results):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + dense_weight / (rank + k)

    for rank, (chunk_id, _) in enumerate(bm25_results):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + bm25_weight / (rank + k)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Normalise to [0, 1]
    if not ranked:
        return []
    max_score = ranked[0][1]
    return [(cid, score / max_score) for cid, score in ranked]


def tokenise(text: str) -> list[str]:
    """Simple whitespace + punctuation tokeniser for BM25.

    Args:
        text: Input text.

    Returns:
        List of lowercase tokens.
    """
    return re.findall(r"\b[a-z0-9]+\b", text.lower())
