"""
RAG API — Latency Benchmarks.
Day 22: Phase 5 — MMR retrieval and memory operation SLO benchmarks.

Targets:
  MMR retrieval p99 < 2s
  Memory STM store p99 < 50ms
  Memory STM retrieve p99 < 100ms

Run with:
  pytest tests/benchmarks/bench_rag.py --benchmark-only --benchmark-sort=mean
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from rag_api.memory.stm import RedisSTMStore, make_memory_entry
from rag_api.models import MemoryEntry, MemoryTier
from rag_api.retrieval.mmr import _mmr_select


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_candidates() -> list[tuple[float, np.ndarray, dict[str, Any], str]]:
    """Generate 100 random candidate vectors for MMR benchmarking."""
    rng = np.random.default_rng(42)
    candidates = []
    for i in range(100):
        vec = rng.random(1024).astype(np.float32)
        payload: dict[str, Any] = {
            "source_id": f"doc-{i % 20}",  # 20 distinct sources
            "content": f"Content chunk {i} about quarterly results and revenue growth.",
            "tenant_id": "bench-tenant",
        }
        candidates.append((float(rng.random()), vec, payload, f"chunk-{i}"))
    return candidates


@pytest.fixture
def query_vector() -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.random(1024).astype(np.float32)


# ── MMR Algorithm Benchmarks ──────────────────────────────────────────────────


def test_benchmark_mmr_select_100_candidates(
    benchmark: Any,
    sample_candidates: list[Any],
    query_vector: np.ndarray,
) -> None:
    """Benchmark MMR selection over 100 candidates for top-10 results.

    SLO: p99 < 50ms (pure CPU algorithm, no I/O).
    """
    result = benchmark(
        _mmr_select,
        query_vector=query_vector,
        candidates=sample_candidates,
        top_k=10,
        lam=0.7,
        max_per_source=3,
    )
    # Correctness assertions
    assert len(result) <= 10
    # No source appears more than 3 times
    source_counts: dict[str, int] = {}
    for _, _, payload, _ in result:
        src = str(payload.get("source_id", ""))
        source_counts[src] = source_counts.get(src, 0) + 1
    assert all(v <= 3 for v in source_counts.values())


def test_benchmark_mmr_select_lambda_exploratory(
    benchmark: Any,
    sample_candidates: list[Any],
    query_vector: np.ndarray,
) -> None:
    """Benchmark MMR with exploratory lambda (0.5) — maximises diversity."""
    result = benchmark(
        _mmr_select,
        query_vector=query_vector,
        candidates=sample_candidates,
        top_k=10,
        lam=0.5,
        max_per_source=3,
    )
    assert len(result) <= 10


def test_benchmark_mmr_select_precise(
    benchmark: Any,
    sample_candidates: list[Any],
    query_vector: np.ndarray,
) -> None:
    """Benchmark MMR with precise lambda (0.9) — maximises relevance."""
    result = benchmark(
        _mmr_select,
        query_vector=query_vector,
        candidates=sample_candidates,
        top_k=10,
        lam=0.9,
        max_per_source=3,
    )
    assert len(result) <= 10


# ── Memory STM Benchmarks ──────────────────────────────────────────────────────


def _make_redis_mock_for_bench() -> AsyncMock:
    """Create a mock Redis client for benchmarking (no real I/O)."""
    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    return mock_redis


def _run_async(coro: Any) -> Any:
    return asyncio.get_event_loop().run_until_complete(coro)


def test_benchmark_stm_store_single_entry(benchmark: Any) -> None:
    """Benchmark STM store for a single memory entry.

    SLO: mean < 5ms (mock Redis, pure serialisation overhead).
    """
    from rag_api.config import Settings

    mock_redis = _make_redis_mock_for_bench()
    store = RedisSTMStore(redis=mock_redis, settings=Settings())  # type: ignore[arg-type]
    entry = make_memory_entry(
        tenant_id="bench",
        agent_id="aria",
        session_id="s1",
        content="This is a benchmark memory entry about quarterly revenue analysis.",
    )

    def _bench() -> str:
        return _run_async(store.store(entry))

    result = benchmark(_bench)
    assert len(result) == 36  # UUID


def test_benchmark_stm_make_entry(benchmark: Any) -> None:
    """Benchmark MemoryEntry construction (pure Python overhead).

    SLO: mean < 1ms.
    """
    result = benchmark(
        make_memory_entry,
        tenant_id="bench",
        agent_id="aria",
        session_id="s1",
        content="test content " * 50,  # ~600 chars
    )
    assert result.tier == MemoryTier.STM


# ── Latency Threshold Assertions ──────────────────────────────────────────────


def test_mmr_select_latency_slo() -> None:
    """MMR select on 100 candidates completes in < 100ms (SLO for synchronous path)."""
    rng = np.random.default_rng(99)
    candidates = [
        (
            float(rng.random()),
            rng.random(1024).astype(np.float32),
            {"source_id": f"doc-{i % 10}", "content": f"chunk {i}"},
            f"c{i}",
        )
        for i in range(100)
    ]
    q = rng.random(1024).astype(np.float32)

    start = time.perf_counter()
    result = _mmr_select(query_vector=q, candidates=candidates, top_k=10, lam=0.7, max_per_source=3)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert len(result) <= 10
    assert elapsed_ms < 100.0, f"MMR select took {elapsed_ms:.1f}ms, SLO is 100ms"
