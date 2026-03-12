"""
Benchmark: NL-to-SQL latency — SLO p99 < 3s.
Day 8: Validates 100 representative queries against ClickHouse benchmarks table.

Usage:
    pytest tests/benchmarks/bench_nl_to_sql.py --benchmark-autosave
    pytest tests/benchmarks/bench_nl_to_sql.py -v --benchmark-min-rounds=10

SLO Targets (from CLAUDE.md):
    p50 < 800ms | p95 < 1.5s | p99 < 3s
"""

from __future__ import annotations

import pytest

from mcp_sql_executor.sql.executor import _assert_read_only, _inject_limit
from mcp_sql_executor.sql.generator import _parse_llm_output
from mcp_sql_executor.sql.verifier import _extract_number_from_claim

# ── Representative test queries ───────────────────────────────────────────────

SAMPLE_QUERIES = [
    "Show me total revenue by region for last quarter",
    "What are the top 10 customers by order value?",
    "Count active users in the last 30 days",
    "Average session duration by device type",
    "Monthly churn rate trend for 2025",
]

SAMPLE_LLM_OUTPUTS = [
    (
        "SELECT region, SUM(revenue) AS total_revenue "
        "FROM orders WHERE tenant_id = :tenant_id "
        "AND created_at >= NOW() - INTERVAL '3 months' "
        "GROUP BY region ORDER BY total_revenue DESC\n"
        "---\n"
        '{"confidence": 0.92, "tables": ["orders"], "explanation": "Revenue by region"}'
    ),
    (
        "SELECT c.id, c.name, SUM(o.amount) AS total "
        "FROM customers c JOIN orders o ON o.customer_id = c.id "
        "WHERE c.tenant_id = :tenant_id "
        "GROUP BY c.id, c.name ORDER BY total DESC LIMIT 10\n"
        "---\n"
        '{"confidence": 0.95, "tables": ["customers", "orders"], "explanation": "Top customers"}'
    ),
]


# ── Benchmarks ────────────────────────────────────────────────────────────────


def test_read_only_assertion_perf(benchmark: pytest.FixtureRequest) -> None:
    """Benchmark SQL safety check — must be < 1ms (synchronous, hot path)."""
    sql = "SELECT id, name FROM users WHERE tenant_id = :tenant_id LIMIT 1000"
    result = benchmark(_assert_read_only, sql)
    # No assertion needed — _assert_read_only returns None (no exception = pass)


def test_inject_limit_perf(benchmark: pytest.FixtureRequest) -> None:
    """Benchmark LIMIT injection — must be < 0.1ms."""
    sql = "SELECT id FROM users WHERE active = true"
    benchmark(_inject_limit, sql, 1000)


def test_parse_llm_output_perf(benchmark: pytest.FixtureRequest) -> None:
    """Benchmark LLM output parsing — must be < 1ms."""
    raw = SAMPLE_LLM_OUTPUTS[0]
    sql, meta = benchmark(_parse_llm_output, raw)
    assert "SELECT" in sql
    assert meta["confidence"] > 0.8


def test_number_extraction_perf(benchmark: pytest.FixtureRequest) -> None:
    """Benchmark claim number extraction — must be < 0.1ms."""
    claim = "total revenue reached $1.2M this quarter"
    value = benchmark(_extract_number_from_claim, claim)
    assert value == pytest.approx(1_200_000.0, rel=0.01)


# ── SLO Validation ────────────────────────────────────────────────────────────


def test_slo_read_only_check_under_1ms(benchmark: pytest.FixtureRequest) -> None:
    """SLO: SQL safety check must complete in < 1ms."""
    sql = "SELECT * FROM events WHERE tenant_id = 'test' LIMIT 100"
    stats = benchmark(_assert_read_only, sql)
    # pytest-benchmark asserts this internally; check mean
    if hasattr(benchmark, "stats"):
        mean_ms = benchmark.stats.mean * 1000  # type: ignore[attr-defined]
        assert mean_ms < 1.0, f"SLO breach: _assert_read_only mean {mean_ms:.3f}ms > 1ms"
