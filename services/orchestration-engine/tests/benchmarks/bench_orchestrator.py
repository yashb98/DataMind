"""
Benchmark: Orchestration Engine latency — SLO p99 < 15s (simple), < 90s (complex).
Day 10: Validates anti-hallucination pipeline layer latency targets.

SLO Targets (CLAUDE.md):
    Simple workflow (< 3 tools): p50 < 3s | p95 < 8s | p99 < 15s
    Complex workflow (> 5 tools): p50 < 15s | p95 < 45s | p99 < 90s
"""

from __future__ import annotations

import pytest

from orchestration_engine.antihallucination.pipeline import (
    CoTAuditLayer,
    KnowledgeBoundaryLayer,
    RetrievalGroundingLayer,
    TemporalGroundingLayer,
)

# ── Sample data ───────────────────────────────────────────────────────────────

SAMPLE_OUTPUT = (
    "Based on [SOURCE 1], Q4 revenue reached $1.2M, representing a 15% increase "
    "over Q3 [SOURCE 2]. Customer acquisition cost decreased by $50 [SOURCE 3], "
    "therefore margins improved significantly."
)

SAMPLE_CHUNKS = [
    {"chunk_id": "c1", "source_id": "report_q4", "content": "Q4 revenue was $1.2M", "stale": False},
    {"chunk_id": "c2", "source_id": "report_q4", "content": "Growth rate was 15% QoQ", "stale": False},
    {"chunk_id": "c3", "source_id": "cost_report", "content": "CAC decreased by $50", "stale": False},
]

CONTEXT = {
    "retrieved_chunks": SAMPLE_CHUNKS,
    "sql_result": None,
    "tenant_id": "bench_tenant",
    "is_high_stakes": False,
}


# ── Layer Benchmarks ──────────────────────────────────────────────────────────


def test_l1_retrieval_grounding_perf(benchmark: pytest.FixtureRequest) -> None:
    """L1 should complete in < 5ms (regex + count)."""
    layer = RetrievalGroundingLayer()
    import asyncio
    result = benchmark(lambda: asyncio.run(layer.validate(SAMPLE_OUTPUT, CONTEXT)))
    assert result.layer.value == "L1_retrieval_grounding"


def test_l4_cot_audit_perf(benchmark: pytest.FixtureRequest) -> None:
    """L4 should complete in < 5ms (regex + pattern matching)."""
    layer = CoTAuditLayer()
    import asyncio
    result = benchmark(lambda: asyncio.run(layer.validate(SAMPLE_OUTPUT, CONTEXT)))
    assert result.passed


def test_l6_knowledge_boundary_perf(benchmark: pytest.FixtureRequest) -> None:
    """L6 should complete in < 2ms (string search)."""
    layer = KnowledgeBoundaryLayer()
    import asyncio
    result = benchmark(lambda: asyncio.run(layer.validate(SAMPLE_OUTPUT, CONTEXT)))
    assert result.passed


def test_l7_temporal_grounding_perf(benchmark: pytest.FixtureRequest) -> None:
    """L7 should complete in < 1ms (list iteration)."""
    layer = TemporalGroundingLayer()
    import asyncio
    result = benchmark(lambda: asyncio.run(layer.validate(SAMPLE_OUTPUT, CONTEXT)))
    assert result.passed
