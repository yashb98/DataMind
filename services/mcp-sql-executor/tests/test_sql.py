"""
Unit tests for MCP SQL Executor — generator, executor helpers, and verifier.
Day 8: ≥80% coverage requirement.
"""

from __future__ import annotations

import pytest

from mcp_sql_executor.sql.executor import _assert_read_only, _inject_limit
from mcp_sql_executor.sql.generator import _parse_llm_output
from mcp_sql_executor.sql.verifier import (
    NumberVerifier,
    _extract_first_number,
    _extract_number_from_claim,
)


# ── _assert_read_only ─────────────────────────────────────────────────────────


class TestAssertReadOnly:
    def test_select_passes(self) -> None:
        _assert_read_only("SELECT id, name FROM users WHERE tenant_id = 'abc'")

    def test_select_with_cte_passes(self) -> None:
        _assert_read_only("WITH cte AS (SELECT 1) SELECT * FROM cte")

    def test_insert_raises(self) -> None:
        with pytest.raises(ValueError, match="INSERT"):
            _assert_read_only("INSERT INTO users VALUES (1, 'test')")

    def test_update_raises(self) -> None:
        with pytest.raises(ValueError, match="UPDATE"):
            _assert_read_only("UPDATE users SET name = 'x' WHERE id = 1")

    def test_drop_raises(self) -> None:
        with pytest.raises(ValueError, match="DROP"):
            _assert_read_only("DROP TABLE users")

    def test_delete_raises(self) -> None:
        with pytest.raises(ValueError, match="DELETE"):
            _assert_read_only("DELETE FROM users WHERE id = 1")


# ── _inject_limit ─────────────────────────────────────────────────────────────


class TestInjectLimit:
    def test_adds_limit_when_absent(self) -> None:
        sql = "SELECT id FROM users"
        result = _inject_limit(sql, 100)
        assert "LIMIT 100" in result

    def test_does_not_duplicate_limit(self) -> None:
        sql = "SELECT id FROM users LIMIT 50"
        result = _inject_limit(sql, 100)
        assert result.count("LIMIT") == 1
        assert "LIMIT 50" in result

    def test_strips_trailing_semicolons(self) -> None:
        sql = "SELECT id FROM users;"
        result = _inject_limit(sql, 100)
        assert not result.endswith(";")


# ── _parse_llm_output ─────────────────────────────────────────────────────────


class TestParseLLMOutput:
    def test_parses_valid_output(self) -> None:
        raw = (
            "SELECT id FROM users WHERE tenant_id = :tenant_id\n"
            "---\n"
            '{"confidence": 0.95, "tables": ["users"], "explanation": "Lists users"}'
        )
        sql, meta = _parse_llm_output(raw)
        assert "SELECT" in sql
        assert meta["confidence"] == 0.95
        assert "users" in meta["tables"]

    def test_handles_missing_metadata(self) -> None:
        raw = "SELECT 1"
        sql, meta = _parse_llm_output(raw)
        assert sql == "SELECT 1"
        assert meta == {}

    def test_strips_markdown_fences(self) -> None:
        raw = "```sql\nSELECT 1\n```\n---\n{}"
        sql, _ = _parse_llm_output(raw)
        assert "```" not in sql

    def test_handles_malformed_json_gracefully(self) -> None:
        raw = "SELECT 1\n---\nnot-json"
        sql, meta = _parse_llm_output(raw)
        assert sql == "SELECT 1"
        assert meta == {}


# ── _extract_number_from_claim ────────────────────────────────────────────────


class TestExtractNumberFromClaim:
    def test_extracts_dollar_amount(self) -> None:
        result = _extract_number_from_claim("total revenue is $1.2M")
        assert result == pytest.approx(1_200_000.0, rel=0.01)

    def test_extracts_plain_number(self) -> None:
        result = _extract_number_from_claim("count is 42,000")
        assert result == pytest.approx(42_000.0, rel=0.01)

    def test_extracts_billion(self) -> None:
        result = _extract_number_from_claim("$3.5B market cap")
        assert result == pytest.approx(3_500_000_000.0, rel=0.01)

    def test_returns_none_when_no_number(self) -> None:
        result = _extract_number_from_claim("no numbers here")
        assert result is None


# ── _extract_first_number ─────────────────────────────────────────────────────


class TestExtractFirstNumber:
    def test_extracts_int(self) -> None:
        row = {"total": 42, "name": "test"}
        assert _extract_first_number(row) == 42.0

    def test_extracts_float(self) -> None:
        row = {"revenue": 123.45}
        assert _extract_first_number(row) == pytest.approx(123.45)

    def test_extracts_string_number(self) -> None:
        row = {"value": "1,234.56"}
        assert _extract_first_number(row) == pytest.approx(1234.56)

    def test_returns_none_for_all_strings(self) -> None:
        row = {"name": "alice", "dept": "eng"}
        assert _extract_first_number(row) is None

    def test_returns_none_for_empty_row(self) -> None:
        assert _extract_first_number({}) is None
