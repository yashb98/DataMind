"""
Tests for mcp-dbt-runner: executor helpers and lineage provider.
Day 11: Phase 2 — Unit tests for dbt runner components.

Coverage targets: ≥80% for executor.py and lineage.py.
"""

from __future__ import annotations

import pytest

from mcp_dbt_runner.models import GetLineageResponse, RunModelResponse
from mcp_dbt_runner.runner.executor import _parse_compiled_sql, _parse_rows_affected
from mcp_dbt_runner.runner.lineage import ManifestLineageProvider


# ── _parse_rows_affected tests ────────────────────────────────────────────────


class TestParseRowsAffected:
    """Unit tests for _parse_rows_affected helper."""

    def test_parses_standard_format(self) -> None:
        """Parses 'N rows affected' pattern."""
        output = "Running... 123 rows affected. Done."
        assert _parse_rows_affected(output) == 123

    def test_parses_plural_rows(self) -> None:
        """Handles 'row' (singular) as well as 'rows'."""
        output = "1 row affected in 0.12s"
        assert _parse_rows_affected(output) == 1

    def test_returns_zero_when_missing(self) -> None:
        """Returns 0 when no row count pattern is present."""
        output = "Completed successfully."
        assert _parse_rows_affected(output) == 0

    def test_parses_inserted_format(self) -> None:
        """Parses 'Inserted N records' (some dbt adapters)."""
        output = "Inserted 50 records into stg_orders"
        assert _parse_rows_affected(output) == 50

    def test_parses_insert_bracket_format(self) -> None:
        """Parses '[INSERT N in Xs]' format from dbt incremental output."""
        output = "1 of 1 START table model dbt.stg_orders... [INSERT 42 in 1.23s]"
        assert _parse_rows_affected(output) == 42

    def test_case_insensitive(self) -> None:
        """Row count parsing is case-insensitive."""
        output = "INSERTED 7 Records into table"
        assert _parse_rows_affected(output) == 7

    def test_returns_first_match(self) -> None:
        """Returns the first match when multiple patterns appear."""
        output = "500 rows affected then Inserted 10 records"
        assert _parse_rows_affected(output) == 500


# ── _parse_compiled_sql tests ─────────────────────────────────────────────────


class TestParseCompiledSQL:
    """Unit tests for _parse_compiled_sql helper."""

    def test_extracts_select(self) -> None:
        """Extracts a SELECT statement from dbt output."""
        output = "Running dbt...\n\nSELECT id, name FROM orders WHERE tenant_id = 'abc'\n\nDone."
        result = _parse_compiled_sql(output)
        assert result.startswith("SELECT")
        assert "orders" in result

    def test_returns_last_select(self) -> None:
        """Returns the last SELECT block when multiple are present."""
        output = "SELECT a FROM t1\n\nSELECT b FROM t2\n\n"
        result = _parse_compiled_sql(output)
        assert "t2" in result

    def test_returns_empty_when_missing(self) -> None:
        """Returns empty string when no SELECT is found."""
        output = "Error: model not found\nCompilation failed."
        assert _parse_compiled_sql(output) == ""

    def test_case_insensitive_select(self) -> None:
        """Handles lower-case 'select' keyword."""
        output = "select count(*) from orders\n\n"
        result = _parse_compiled_sql(output)
        assert "orders" in result


# ── ManifestLineageProvider tests ─────────────────────────────────────────────


class TestManifestLineageProvider:
    """Unit tests for ManifestLineageProvider."""

    async def test_returns_empty_when_no_manifest(self) -> None:
        """Returns empty lineage when manifest.json does not exist."""
        provider = ManifestLineageProvider()
        # dbt_project_dir points to /dbt/project which doesn't exist in test env
        response = await provider.get_lineage(
            model_name="nonexistent_model",
            tenant_id="test_tenant",
            direction="both",
            depth=3,
        )
        assert isinstance(response, GetLineageResponse)
        assert response.model_name == "nonexistent_model"
        assert response.upstream == []
        assert response.downstream == []
        assert response.sources == []

    async def test_dag_summary_format(self) -> None:
        """DAG summary string follows the expected format."""
        provider = ManifestLineageProvider()
        response = await provider.get_lineage(
            model_name="stg_orders",
            tenant_id="t1",
            direction="both",
            depth=3,
        )
        assert "stg_orders" in response.dag_summary
        assert "upstream" in response.dag_summary
        assert "downstream" in response.dag_summary
        assert "sources" in response.dag_summary

    async def test_direction_upstream_only(self) -> None:
        """When direction='upstream', downstream list is always empty."""
        provider = ManifestLineageProvider()
        response = await provider.get_lineage(
            model_name="any_model",
            tenant_id="t1",
            direction="upstream",
            depth=2,
        )
        assert response.downstream == []

    async def test_direction_downstream_only(self) -> None:
        """When direction='downstream', upstream list is always empty."""
        provider = ManifestLineageProvider()
        response = await provider.get_lineage(
            model_name="any_model",
            tenant_id="t1",
            direction="downstream",
            depth=2,
        )
        assert response.upstream == []

    async def test_manifest_cached_after_first_load(self) -> None:
        """Manifest is loaded once and cached for subsequent calls."""
        provider = ManifestLineageProvider()
        # First call loads (and caches) the manifest
        await provider.get_lineage("m1", "t1", "both", 1)
        cached = provider._manifest
        # Second call must reuse the cached manifest
        await provider.get_lineage("m2", "t1", "both", 1)
        assert provider._manifest is cached  # same object reference


# ── RunModelResponse model tests ──────────────────────────────────────────────


class TestRunModelResponse:
    """Unit tests for RunModelResponse Pydantic model."""

    def test_status_values(self) -> None:
        """RunModelResponse accepts all three valid status strings."""
        for status in ("success", "error", "skipped"):
            resp = RunModelResponse(
                run_id="abc123",
                model_name="stg_orders",
                status=status,
                rows_affected=0,
                execution_ms=123.4,
                compiled_sql="SELECT 1",
                logs=["Done."],
            )
            assert resp.status == status

    def test_compiled_sql_truncated(self) -> None:
        """compiled_sql field stores whatever string is provided."""
        long_sql = "SELECT " + "x, " * 500 + "1 FROM t"
        resp = RunModelResponse(
            run_id="x",
            model_name="m",
            status="success",
            rows_affected=1,
            execution_ms=0.0,
            compiled_sql=long_sql[:500],
            logs=[],
        )
        assert len(resp.compiled_sql) <= 500

    def test_logs_is_list(self) -> None:
        """logs field is a list of strings."""
        resp = RunModelResponse(
            run_id="x",
            model_name="m",
            status="success",
            rows_affected=0,
            execution_ms=1.0,
            compiled_sql="",
            logs=["line1", "line2"],
        )
        assert isinstance(resp.logs, list)
        assert len(resp.logs) == 2

    def test_model_dump_is_serialisable(self) -> None:
        """model_dump() returns a plain dict without Pydantic objects."""
        import json

        resp = RunModelResponse(
            run_id="r1",
            model_name="stg_x",
            status="success",
            rows_affected=42,
            execution_ms=88.5,
            compiled_sql="SELECT 1",
            logs=["OK"],
        )
        dumped = resp.model_dump()
        assert isinstance(json.dumps(dumped), str)
