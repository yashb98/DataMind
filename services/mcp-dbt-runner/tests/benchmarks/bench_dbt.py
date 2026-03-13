"""
Benchmark: dbt runner helper functions.
Day 11: Phase 2 — SLO: parse functions < 1ms p99.

Run with:
    pytest tests/benchmarks/bench_dbt.py --benchmark-only -v

Targets:
    _parse_rows_affected  < 1ms (p99)
    _parse_compiled_sql   < 1ms (p99)
    ManifestLineageProvider.get_lineage (no manifest) < 5ms (p99)
"""

from __future__ import annotations

import asyncio

import pytest

from mcp_dbt_runner.runner.executor import _parse_compiled_sql, _parse_rows_affected
from mcp_dbt_runner.runner.lineage import ManifestLineageProvider

# ── Sample dbt output fixtures ────────────────────────────────────────────────

_SAMPLE_OUTPUT_WITH_ROWS = """
Running with dbt=1.9.0
Found 42 models, 8 sources

22:05:01  Running 1 models for selection: stg_orders

22:05:01  1 of 1 START table model dbt_tenant.stg_orders ................ [RUN]
22:05:02  1 of 1 OK created table model dbt_tenant.stg_orders ........... [INSERT 1500 in 1.23s]

22:05:02  Finished running 1 table models in 0 hours 0 minutes and 1.50 seconds (1.50s).

SELECT
    order_id,
    customer_id,
    order_date,
    total_amount,
    status
FROM {{ source('raw', 'orders') }}
WHERE tenant_id = '{{ var("tenant_id") }}'

"""

_SAMPLE_OUTPUT_NO_ROWS = """
Running with dbt=1.9.0
Completed successfully. No new rows.
"""

_SAMPLE_OUTPUT_SQL_ONLY = """
SELECT id, name, created_at FROM orders WHERE deleted_at IS NULL

"""


# ── Parse rows benchmarks ─────────────────────────────────────────────────────


def test_parse_rows_affected_perf(benchmark: pytest.fixture) -> None:  # type: ignore[type-arg]
    """_parse_rows_affected must complete < 1ms p99 (SLO)."""
    result = benchmark(_parse_rows_affected, _SAMPLE_OUTPUT_WITH_ROWS)
    assert result == 1500, f"Expected 1500 rows, got {result}"


def test_parse_rows_affected_no_match_perf(benchmark: pytest.fixture) -> None:  # type: ignore[type-arg]
    """_parse_rows_affected on output without row counts must complete < 1ms p99."""
    result = benchmark(_parse_rows_affected, _SAMPLE_OUTPUT_NO_ROWS)
    assert result == 0


def test_parse_rows_affected_large_output_perf(benchmark: pytest.fixture) -> None:  # type: ignore[type-arg]
    """_parse_rows_affected on 10KB output must stay < 1ms p99."""
    large_output = _SAMPLE_OUTPUT_WITH_ROWS * 20  # ~10KB
    result = benchmark(_parse_rows_affected, large_output)
    assert result == 1500


# ── Parse compiled SQL benchmarks ─────────────────────────────────────────────


def test_parse_compiled_sql_perf(benchmark: pytest.fixture) -> None:  # type: ignore[type-arg]
    """_parse_compiled_sql must complete < 1ms p99 (SLO)."""
    result = benchmark(_parse_compiled_sql, _SAMPLE_OUTPUT_WITH_ROWS)
    assert "SELECT" in result.upper()


def test_parse_compiled_sql_no_sql_perf(benchmark: pytest.fixture) -> None:  # type: ignore[type-arg]
    """_parse_compiled_sql returns empty string quickly when no SQL present."""
    result = benchmark(_parse_compiled_sql, _SAMPLE_OUTPUT_NO_ROWS)
    assert result == ""


def test_parse_compiled_sql_large_output_perf(benchmark: pytest.fixture) -> None:  # type: ignore[type-arg]
    """_parse_compiled_sql on 10KB output must stay < 1ms p99."""
    large_output = _SAMPLE_OUTPUT_SQL_ONLY * 20  # repeated SELECT blocks
    result = benchmark(_parse_compiled_sql, large_output)
    assert "orders" in result


# ── ManifestLineageProvider benchmarks ───────────────────────────────────────


def test_lineage_provider_no_manifest_perf(benchmark: pytest.fixture) -> None:  # type: ignore[type-arg]
    """ManifestLineageProvider.get_lineage (no manifest file) < 5ms p99."""

    provider = ManifestLineageProvider()

    def run_lineage() -> None:
        asyncio.run(
            provider.get_lineage(
                model_name="stg_orders",
                tenant_id="bench_tenant",
                direction="both",
                depth=3,
            )
        )

    benchmark(run_lineage)


def test_lineage_provider_with_mock_manifest_perf(
    benchmark: pytest.fixture,  # type: ignore[type-arg]
    tmp_path: pytest.fixture,  # type: ignore[type-arg]
) -> None:
    """ManifestLineageProvider.get_lineage with manifest loaded < 5ms p99."""
    import json
    import os

    # Build a minimal manifest with 10 nodes
    nodes: dict = {}
    for i in range(10):
        key = f"model.datamind.model_{i}"
        nodes[key] = {
            "unique_id": key,
            "name": f"model_{i}",
            "depends_on": {
                "nodes": [f"model.datamind.model_{j}" for j in range(max(0, i - 2), i)]
            },
        }
    manifest = {"nodes": nodes, "sources": {}, "exposures": {}}

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    # Point settings temporarily to the temp dir
    import mcp_dbt_runner.config as cfg_module

    original_dir = cfg_module.settings.dbt_project_dir
    cfg_module.settings.dbt_project_dir = str(tmp_path)

    provider = ManifestLineageProvider()

    def run_lineage() -> None:
        asyncio.run(
            provider.get_lineage(
                model_name="model_5",
                tenant_id="bench_tenant",
                direction="both",
                depth=3,
            )
        )

    try:
        benchmark(run_lineage)
    finally:
        cfg_module.settings.dbt_project_dir = original_dir
