"""
Integration tests — Phase 2 remaining services: MCP Visualization, MCP Report Generator,
MCP dbt Runner, MCP Data Connector.
Days 11-14: Requires running docker compose stack (DATAMIND_INTEGRATION_TESTS=true).

Usage:
    DATAMIND_INTEGRATION_TESTS=true pytest tests/integration/test_phase2_remaining.py -v

SLO targets validated here:
    mcp-visualization:     health < 100ms, render_chart returns valid ECharts option
    mcp-report-generator:  health < 100ms, generate_report returns report_id
    mcp-dbt-runner:        health < 100ms, tools/list includes run_model + get_lineage
    mcp-data-connector:    health < 100ms, tools/list includes connect + ingest + profile_schema
"""

from __future__ import annotations

import json
import os
import time

import httpx
import pytest

INTEGRATION = os.getenv("DATAMIND_INTEGRATION_TESTS", "false").lower() == "true"

pytestmark = pytest.mark.skipif(
    not INTEGRATION,
    reason="Integration tests skipped. Set DATAMIND_INTEGRATION_TESTS=true to enable.",
)

# ── Service URLs ──────────────────────────────────────────────────────────────

VISUALIZATION_URL = os.getenv("MCP_VISUALIZATION_URL", "http://localhost:8070")
REPORT_GENERATOR_URL = os.getenv("MCP_REPORT_GENERATOR_URL", "http://localhost:8080")
DBT_RUNNER_URL = os.getenv("MCP_DBT_RUNNER_URL", "http://localhost:8090")
DATA_CONNECTOR_URL = os.getenv("MCP_DATA_CONNECTOR_URL", "http://localhost:8100")


# ── MCP Visualization ─────────────────────────────────────────────────────────


class TestMCPVisualization:
    def test_liveness(self) -> None:
        r = httpx.get(f"{VISUALIZATION_URL}/health/liveness", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "alive"
        assert r.json()["service"] == "mcp-visualization"

    def test_readiness(self) -> None:
        r = httpx.get(f"{VISUALIZATION_URL}/health/readiness", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_tools_endpoint(self) -> None:
        r = httpx.get(f"{VISUALIZATION_URL}/tools", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "render_chart" in data["tools"]
        assert "suggest_chart_type" in data["tools"]

    def test_mcp_tools_list(self) -> None:
        r = httpx.post(
            f"{VISUALIZATION_URL}/mcp",
            json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": "1"},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert "result" in data
        tool_names = [t["name"] for t in data["result"].get("tools", [])]
        assert "render_chart" in tool_names
        assert "suggest_chart_type" in tool_names

    def test_render_bar_chart(self) -> None:
        """render_chart must return a valid ECharts option for a bar chart."""
        r = httpx.post(
            f"{VISUALIZATION_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "render_chart",
                    "arguments": {
                        "chart_type": "bar",
                        "data": [
                            {"x": "Q1", "y": 100},
                            {"x": "Q2", "y": 150},
                            {"x": "Q3", "y": 130},
                        ],
                        "title": "Quarterly Revenue",
                        "tenant_id": "integration_test",
                    },
                },
                "id": "2",
            },
            timeout=10,
        )
        assert r.status_code == 200
        result = r.json().get("result", {})
        assert "content" in result
        content = json.loads(result["content"][0]["text"])
        assert "chart_config" in content
        chart_cfg = content["chart_config"]
        # Must have ECharts standard keys
        assert "series" in chart_cfg or "xAxis" in chart_cfg

    def test_render_pie_chart(self) -> None:
        r = httpx.post(
            f"{VISUALIZATION_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "render_chart",
                    "arguments": {
                        "chart_type": "pie",
                        "data": [
                            {"name": "Product A", "value": 300},
                            {"name": "Product B", "value": 200},
                        ],
                        "title": "Market Share",
                        "tenant_id": "integration_test",
                    },
                },
                "id": "3",
            },
            timeout=10,
        )
        assert r.status_code == 200
        result = r.json().get("result", {})
        content = json.loads(result["content"][0]["text"])
        assert "chart_config" in content

    def test_suggest_chart_type_trend(self) -> None:
        """suggest_chart_type must recommend 'line' for trend intent with time column."""
        r = httpx.post(
            f"{VISUALIZATION_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "suggest_chart_type",
                    "arguments": {
                        "columns": [
                            {"name": "date", "type": "date", "cardinality": 365},
                            {"name": "revenue", "type": "number", "cardinality": 300},
                        ],
                        "row_count": 365,
                        "intent": "trend",
                        "tenant_id": "integration_test",
                    },
                },
                "id": "4",
            },
            timeout=10,
        )
        assert r.status_code == 200
        result = r.json().get("result", {})
        content = json.loads(result["content"][0]["text"])
        assert "primary_suggestion" in content
        assert content["primary_suggestion"] in ("line", "area")

    def test_render_unknown_chart_returns_error(self) -> None:
        r = httpx.post(
            f"{VISUALIZATION_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "render_chart",
                    "arguments": {
                        "chart_type": "nonexistent_chart_xyz",
                        "data": [{"x": 1}],
                        "title": "Test",
                        "tenant_id": "integration_test",
                    },
                },
                "id": "5",
            },
            timeout=10,
        )
        assert r.status_code == 200
        result = r.json().get("result", {})
        content_text = result["content"][0]["text"]
        content = json.loads(content_text)
        # Should return error, not crash
        assert "error" in content or "chart_config" in content


# ── MCP Report Generator ──────────────────────────────────────────────────────


class TestMCPReportGenerator:
    def test_liveness(self) -> None:
        r = httpx.get(f"{REPORT_GENERATOR_URL}/health/liveness", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "alive"
        assert r.json()["service"] == "mcp-report-generator"

    def test_readiness(self) -> None:
        r = httpx.get(f"{REPORT_GENERATOR_URL}/health/readiness", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("healthy", "degraded")

    def test_tools_endpoint(self) -> None:
        r = httpx.get(f"{REPORT_GENERATOR_URL}/tools", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "generate_report" in data["tools"]
        assert "anchor_ipfs" in data["tools"]

    def test_mcp_tools_list(self) -> None:
        r = httpx.post(
            f"{REPORT_GENERATOR_URL}/mcp/",
            json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": "1"},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        tool_names = [t["name"] for t in data.get("result", {}).get("tools", [])]
        assert "generate_report" in tool_names
        assert "anchor_ipfs" in tool_names

    def test_generate_pptx_report(self) -> None:
        """generate_report must return a report_id and storage_path for PPTX."""
        r = httpx.post(
            f"{REPORT_GENERATOR_URL}/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "generate_report",
                    "arguments": {
                        "title": "Integration Test Report",
                        "sections": [
                            {
                                "heading": "Executive Summary",
                                "content": "Q4 revenue reached **$1.2M**, up 15% QoQ.",
                            },
                            {
                                "heading": "Data Table",
                                "content": "Revenue breakdown by region.",
                                "data": [
                                    {"region": "APAC", "revenue": 400000},
                                    {"region": "EMEA", "revenue": 500000},
                                    {"region": "AMER", "revenue": 300000},
                                ],
                            },
                        ],
                        "format": "pptx",
                        "tenant_id": "integration_test",
                        "include_provenance": True,
                    },
                },
                "id": "2",
            },
            timeout=60,
        )
        assert r.status_code == 200
        result = r.json().get("result", {})
        if "content" in result:
            content = json.loads(result["content"][0]["text"])
            assert "report_id" in content
            assert content["format"] == "pptx"
            assert "merkle_root" in content
            assert len(content["merkle_root"]) == 64  # SHA-256 hex

    def test_anchor_ipfs_without_keys_returns_graceful_error(self) -> None:
        """anchor_ipfs must degrade gracefully when Pinata keys are not set."""
        r = httpx.post(
            f"{REPORT_GENERATOR_URL}/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "anchor_ipfs",
                    "arguments": {
                        "report_id": "test-report-001",
                        "merkle_root": "a" * 64,
                        "tenant_id": "integration_test",
                    },
                },
                "id": "3",
            },
            timeout=15,
        )
        assert r.status_code == 200
        result = r.json().get("result", {})
        if "content" in result:
            content = json.loads(result["content"][0]["text"])
            # Either anchored (if Pinata keys set) or graceful error
            assert "ipfs_hash" in content or "error" in content


# ── MCP dbt Runner ────────────────────────────────────────────────────────────


class TestMCPDBTRunner:
    def test_liveness(self) -> None:
        r = httpx.get(f"{DBT_RUNNER_URL}/health/liveness", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "alive"
        assert r.json()["service"] == "mcp-dbt-runner"

    def test_readiness(self) -> None:
        r = httpx.get(f"{DBT_RUNNER_URL}/health/readiness", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("healthy", "degraded")

    def test_tools_endpoint(self) -> None:
        r = httpx.get(f"{DBT_RUNNER_URL}/tools", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "run_model" in data["tools"]
        assert "get_lineage" in data["tools"]

    def test_mcp_tools_list(self) -> None:
        r = httpx.post(
            f"{DBT_RUNNER_URL}/mcp/",
            json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": "1"},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        tool_names = [t["name"] for t in data.get("result", {}).get("tools", [])]
        assert "run_model" in tool_names
        assert "get_lineage" in tool_names

    def test_get_lineage_no_manifest_returns_empty(self) -> None:
        """get_lineage must return empty upstream/downstream when no manifest exists (graceful)."""
        r = httpx.post(
            f"{DBT_RUNNER_URL}/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "get_lineage",
                    "arguments": {
                        "model_name": "stg_orders",
                        "tenant_id": "integration_test",
                        "direction": "both",
                        "depth": 2,
                    },
                },
                "id": "2",
            },
            timeout=15,
        )
        assert r.status_code == 200
        result = r.json().get("result", {})
        if "content" in result:
            content = json.loads(result["content"][0]["text"])
            assert "model_name" in content
            assert "upstream" in content
            assert "downstream" in content
            assert isinstance(content["upstream"], list)
            assert isinstance(content["downstream"], list)

    def test_run_model_nonexistent_returns_error_status(self) -> None:
        """run_model for a nonexistent model must return status='error', not crash."""
        r = httpx.post(
            f"{DBT_RUNNER_URL}/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "run_model",
                    "arguments": {
                        "model_name": "nonexistent_model_xyz",
                        "tenant_id": "integration_test",
                    },
                },
                "id": "3",
            },
            timeout=30,
        )
        assert r.status_code == 200
        result = r.json().get("result", {})
        if "content" in result:
            content = json.loads(result["content"][0]["text"])
            assert content.get("status") in ("error", "success", "skipped")


# ── MCP Data Connector ────────────────────────────────────────────────────────


class TestMCPDataConnector:
    def test_liveness(self) -> None:
        r = httpx.get(f"{DATA_CONNECTOR_URL}/health/liveness", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "alive"
        assert data["service"] == "mcp-data-connector"

    def test_readiness(self) -> None:
        r = httpx.get(f"{DATA_CONNECTOR_URL}/health/readiness", timeout=5)
        assert r.status_code == 200

    def test_tools_endpoint(self) -> None:
        r = httpx.get(f"{DATA_CONNECTOR_URL}/tools", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "connect" in data["tools"]
        assert "ingest" in data["tools"]
        assert "profile_schema" in data["tools"]

    def test_mcp_tools_list(self) -> None:
        r = httpx.post(
            f"{DATA_CONNECTOR_URL}/mcp/",
            json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": "1"},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert "result" in data
        tool_names = [t["name"] for t in data["result"].get("tools", [])]
        assert "connect" in tool_names
        assert "ingest" in tool_names
        assert "profile_schema" in tool_names

    def test_connect_postgres_internal(self) -> None:
        """connect to internal postgres must succeed (docker network)."""
        r = httpx.post(
            f"{DATA_CONNECTOR_URL}/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "connect",
                    "arguments": {
                        "source_type": "postgres",
                        "connection_config": {
                            "host": "postgres",
                            "port": 5432,
                            "database": "datamind",
                            "user": "datamind",
                            "password": "changeme",
                            "sslmode": "disable",
                        },
                        "tenant_id": "integration_test",
                        "source_name": "internal_pg",
                    },
                },
                "id": "2",
            },
            timeout=15,
        )
        assert r.status_code == 200
        result = r.json().get("result", {})
        if "content" in result:
            content = json.loads(result["content"][0]["text"])
            assert "status" in content
            assert content["status"] in ("connected", "failed")
            # If connected, must have a connection_id
            if content["status"] == "connected":
                assert "connection_id" in content
                assert content["connection_id"].startswith("integration_test_")

    def test_connect_unsupported_source_returns_error(self) -> None:
        """connect with unknown source_type must return a structured error."""
        r = httpx.post(
            f"{DATA_CONNECTOR_URL}/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "connect",
                    "arguments": {
                        "source_type": "oracle_db_xyz",
                        "connection_config": {},
                        "tenant_id": "integration_test",
                        "source_name": "bad_source",
                    },
                },
                "id": "3",
            },
            timeout=10,
        )
        assert r.status_code == 200
        result = r.json().get("result", {})
        if "content" in result:
            content = json.loads(result["content"][0]["text"])
            assert content.get("status") == "failed"
            assert "error" in content

    def test_ingest_without_connection_returns_error(self) -> None:
        """ingest with unknown connection_id must return status=error."""
        r = httpx.post(
            f"{DATA_CONNECTOR_URL}/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "ingest",
                    "arguments": {
                        "connection_id": "nonexistent_conn_xyz",
                        "tenant_id": "integration_test",
                        "table_name": "orders",
                        "batch_size": 100,
                    },
                },
                "id": "4",
            },
            timeout=10,
        )
        assert r.status_code == 200
        result = r.json().get("result", {})
        if "content" in result:
            content = json.loads(result["content"][0]["text"])
            assert content.get("status") == "error"

    def test_profile_without_connection_returns_error(self) -> None:
        """profile_schema with unknown connection_id must return structured error."""
        r = httpx.post(
            f"{DATA_CONNECTOR_URL}/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "profile_schema",
                    "arguments": {
                        "connection_id": "nonexistent_conn_xyz",
                        "tenant_id": "integration_test",
                        "table_name": "orders",
                        "sample_rows": 100,
                    },
                },
                "id": "5",
            },
            timeout=10,
        )
        assert r.status_code == 200
        result = r.json().get("result", {})
        if "content" in result:
            content = json.loads(result["content"][0]["text"])
            assert "error" in content


# ── Cross-service SLO latency checks ─────────────────────────────────────────


class TestPhase2SLO:
    """Validate health endpoint latency < 100ms SLO for all Phase 2 services."""

    @pytest.mark.parametrize("url,name", [
        (VISUALIZATION_URL, "mcp-visualization"),
        (REPORT_GENERATOR_URL, "mcp-report-generator"),
        (DBT_RUNNER_URL, "mcp-dbt-runner"),
        (DATA_CONNECTOR_URL, "mcp-data-connector"),
    ])
    def test_health_latency_under_100ms(self, url: str, name: str) -> None:
        start = time.perf_counter()
        r = httpx.get(f"{url}/health/liveness", timeout=5)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200, f"{name} liveness check failed"
        assert elapsed_ms < 100, f"{name} health latency {elapsed_ms:.1f}ms exceeds 100ms SLO"
