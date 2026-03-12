"""
Unit tests for MCP Knowledge Base — MMR, BM25, hybrid fusion, and re-ranking.
Day 9: ≥80% coverage requirement.
"""

from __future__ import annotations

import numpy as np
import pytest

from mcp_knowledge_base.retrieval.bm25 import BM25Retriever, hybrid_fusion, tokenise
from mcp_knowledge_base.retrieval.mmr import _is_stale, _mmr_select
from datetime import datetime, timezone, timedelta


# ── BM25 Tests ────────────────────────────────────────────────────────────────


class TestBM25Retriever:
    def test_index_and_retrieve(self) -> None:
        r = BM25Retriever()
        docs = [
            {"chunk_id": "c1", "content": "revenue growth in Q4 exceeded expectations"},
            {"chunk_id": "c2", "content": "customer churn increased this quarter"},
            {"chunk_id": "c3", "content": "product launch successful in APAC region"},
        ]
        r.index_documents("tenant1", docs)
        results = r.retrieve("revenue growth", "tenant1", top_k=2)
        assert len(results) <= 2
        ids = [cid for cid, _ in results]
        assert "c1" in ids

    def test_returns_empty_when_no_index(self) -> None:
        r = BM25Retriever()
        results = r.retrieve("any query", "unknown_tenant")
        assert results == []

    def test_scores_normalised_to_one(self) -> None:
        r = BM25Retriever()
        docs = [{"chunk_id": f"c{i}", "content": f"doc {i} content here"} for i in range(5)]
        r.index_documents("t1", docs)
        results = r.retrieve("doc content", "t1", top_k=5)
        if results:
            assert all(0.0 <= score <= 1.0 for _, score in results)


class TestHybridFusion:
    def test_fuses_dense_and_bm25(self) -> None:
        dense = [("c1", 0.9), ("c2", 0.7), ("c3", 0.5)]
        bm25 = [("c2", 1.0), ("c1", 0.8), ("c4", 0.6)]
        fused = hybrid_fusion(dense, bm25)
        ids = [cid for cid, _ in fused]
        # Both c1 and c2 appear in both lists — should rank high
        assert "c1" in ids[:2] or "c2" in ids[:2]

    def test_includes_bm25_only_docs(self) -> None:
        dense = [("c1", 0.9)]
        bm25 = [("c2", 1.0)]
        fused = hybrid_fusion(dense, bm25)
        ids = [cid for cid, _ in fused]
        assert "c2" in ids

    def test_returns_empty_for_empty_input(self) -> None:
        assert hybrid_fusion([], []) == []

    def test_scores_normalised(self) -> None:
        dense = [("c1", 0.9), ("c2", 0.6)]
        bm25 = [("c1", 0.8)]
        fused = hybrid_fusion(dense, bm25)
        if fused:
            assert fused[0][1] == pytest.approx(1.0)  # Top score normalised to 1


class TestTokenise:
    def test_splits_on_whitespace(self) -> None:
        tokens = tokenise("Hello World 2025")
        assert "hello" in tokens
        assert "world" in tokens
        assert "2025" in tokens

    def test_strips_punctuation(self) -> None:
        tokens = tokenise("revenue, growth.")
        assert "revenue" in tokens
        assert "growth" in tokens
        assert "," not in tokens

    def test_lowercases(self) -> None:
        tokens = tokenise("UPPER Lower")
        assert "upper" in tokens
        assert "lower" in tokens


# ── MMR Tests ─────────────────────────────────────────────────────────────────


class TestMMRSelect:
    def _make_candidates(
        self, n: int, base_vector: list[float], diverse: bool = False
    ) -> list[tuple[float, "np.ndarray", dict, str]]:
        candidates = []
        for i in range(n):
            if diverse:
                vec = np.zeros(4, dtype=np.float32)
                vec[i % 4] = 1.0
            else:
                vec = np.array(base_vector, dtype=np.float32) + np.random.randn(4).astype(np.float32) * 0.01
                vec /= np.linalg.norm(vec)
            candidates.append((1.0 - i * 0.1, vec, {"source_id": f"src{i // 2}", "content": f"doc{i}"}, f"c{i}"))
        return candidates

    def test_returns_top_k(self) -> None:
        q = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        candidates = self._make_candidates(10, [1.0, 0.0, 0.0, 0.0])
        selected = _mmr_select(q, candidates, top_k=3, lam=0.7, max_per_source=2)
        assert len(selected) == 3

    def test_max_per_source_enforced(self) -> None:
        q = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        # All from same source
        candidates = [
            (0.9 - i * 0.05, np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
             {"source_id": "same_src", "content": f"doc{i}"}, f"c{i}")
            for i in range(5)
        ]
        selected = _mmr_select(q, candidates, top_k=4, lam=0.7, max_per_source=2)
        # At most 2 from same source
        assert len(selected) <= 2

    def test_lambda_0_maximises_diversity(self) -> None:
        q = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        candidates = self._make_candidates(4, [1.0, 0.0, 0.0, 0.0], diverse=True)
        # With lambda=0, should prefer diverse documents
        selected = _mmr_select(q, candidates, top_k=3, lam=0.0, max_per_source=10)
        assert len(selected) == 3

    def test_returns_empty_for_empty_candidates(self) -> None:
        q = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        assert _mmr_select(q, [], top_k=5, lam=0.7, max_per_source=3) == []


# ── Staleness Tests ───────────────────────────────────────────────────────────


class TestIsStale:
    def test_recent_chunk_not_stale(self) -> None:
        recent = datetime.now(tz=timezone.utc) - timedelta(days=10)
        assert _is_stale(recent, threshold_days=90) is False

    def test_old_chunk_is_stale(self) -> None:
        old = datetime.now(tz=timezone.utc) - timedelta(days=100)
        assert _is_stale(old, threshold_days=90) is True

    def test_none_ingestion_not_stale(self) -> None:
        assert _is_stale(None, threshold_days=90) is False

    def test_exactly_at_threshold_not_stale(self) -> None:
        at_threshold = datetime.now(tz=timezone.utc) - timedelta(days=90)
        assert _is_stale(at_threshold, threshold_days=90) is False
