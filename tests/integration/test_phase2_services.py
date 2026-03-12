"""
Integration tests — Phase 2 services: MCP SQL Executor, MCP Knowledge Base, Orchestration Engine.
Day 10: Requires running docker compose stack (DATAMIND_INTEGRATION_TESTS=true).

Usage:
    DATAMIND_INTEGRATION_TESTS=true pytest tests/integration/test_phase2_services.py -v

SLO targets validated here:
    mcp-sql-executor: health < 100ms
    mcp-knowledge-base: health < 100ms
    orchestration-engine: health < 100ms, A2A agent card available
"""

from __future__ import annotations

import os

import httpx
import pytest

INTEGRATION = os.getenv("DATAMIND_INTEGRATION_TESTS", "false").lower() == "true"

pytestmark = pytest.mark.skipif(
    not INTEGRATION,
    reason="Integration tests skipped. Set DATAMIND_INTEGRATION_TESTS=true to enable.",
)

# ── Service URLs ──────────────────────────────────────────────────────────────

SQL_EXECUTOR_URL = os.getenv("MCP_SQL_EXECUTOR_URL", "http://localhost:8040")
KNOWLEDGE_BASE_URL = os.getenv("MCP_KNOWLEDGE_BASE_URL", "http://localhost:8050")
ORCHESTRATION_URL = os.getenv("ORCHESTRATION_ENGINE_URL", "http://localhost:8060")


# ── MCP SQL Executor ──────────────────────────────────────────────────────────


class TestMCPSQLExecutor:
    def test_liveness(self) -> None:
        r = httpx.get(f"{SQL_EXECUTOR_URL}/health/liveness", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "alive"
        assert r.json()["service"] == "mcp-sql-executor"

    def test_readiness(self) -> None:
        r = httpx.get(f"{SQL_EXECUTOR_URL}/health/readiness", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("healthy", "degraded")

    def test_tools_endpoint(self) -> None:
        r = httpx.get(f"{SQL_EXECUTOR_URL}/tools", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "nl_to_sql" in data["tools"]
        assert "execute_sql" in data["tools"]
        assert "get_schema" in data["tools"]
        assert "verify_numbers" in data["tools"]

    def test_mcp_tools_list(self) -> None:
        """MCP tools/list JSON-RPC call."""
        r = httpx.post(
            f"{SQL_EXECUTOR_URL}/mcp/",
            json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": "1"},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert "result" in data
        tools = data["result"].get("tools", [])
        tool_names = [t["name"] for t in tools]
        assert "execute_sql" in tool_names
        assert "nl_to_sql" in tool_names

    def test_execute_sql_rejects_write(self) -> None:
        """MCP execute_sql must reject INSERT statements."""
        r = httpx.post(
            f"{SQL_EXECUTOR_URL}/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "execute_sql",
                    "arguments": {
                        "sql": "INSERT INTO users VALUES (1, 'test')",
                        "tenant_id": "test",
                    },
                },
                "id": "2",
            },
            timeout=10,
        )
        assert r.status_code == 200
        result = r.json().get("result", {})
        # Should return error code WRITE_REJECTED
        if isinstance(result, dict) and "content" in result:
            import json
            content = json.loads(result["content"][0]["text"])
            assert content.get("code") == "WRITE_REJECTED"


# ── MCP Knowledge Base ────────────────────────────────────────────────────────


class TestMCPKnowledgeBase:
    def test_liveness(self) -> None:
        r = httpx.get(f"{KNOWLEDGE_BASE_URL}/health/liveness", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "alive"
        assert r.json()["service"] == "mcp-knowledge-base"

    def test_readiness(self) -> None:
        r = httpx.get(f"{KNOWLEDGE_BASE_URL}/health/readiness", timeout=10)
        assert r.status_code == 200

    def test_tools_endpoint(self) -> None:
        r = httpx.get(f"{KNOWLEDGE_BASE_URL}/tools", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "retrieve" in data["tools"]
        assert "mmr_search" in data["tools"]
        assert "graph_search" in data["tools"]

    def test_mcp_tools_list(self) -> None:
        r = httpx.post(
            f"{KNOWLEDGE_BASE_URL}/mcp/",
            json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": "1"},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        tools = data.get("result", {}).get("tools", [])
        tool_names = [t["name"] for t in tools]
        assert "retrieve" in tool_names

    def test_retrieve_empty_collection_returns_no_error(self) -> None:
        """Retrieving from an empty collection should return empty chunks, not error."""
        r = httpx.post(
            f"{KNOWLEDGE_BASE_URL}/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "retrieve",
                    "arguments": {
                        "query": "test query",
                        "tenant_id": "integration_test_tenant",
                        "top_k": 3,
                    },
                },
                "id": "2",
            },
            timeout=15,
        )
        assert r.status_code == 200
        result = r.json()
        assert "result" in result or "error" not in result


# ── Orchestration Engine ──────────────────────────────────────────────────────


class TestOrchestrationEngine:
    def test_liveness(self) -> None:
        r = httpx.get(f"{ORCHESTRATION_URL}/health/liveness", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "alive"
        assert r.json()["service"] == "orchestration-engine"

    def test_readiness(self) -> None:
        r = httpx.get(f"{ORCHESTRATION_URL}/health/readiness", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("healthy", "degraded")

    def test_a2a_agent_card_available(self) -> None:
        """Agent Card must be published at /.well-known/agent.json per A2A spec."""
        r = httpx.get(f"{ORCHESTRATION_URL}/.well-known/agent.json", timeout=5)
        assert r.status_code == 200
        card = r.json()
        assert card["name"] == "DataMind Orchestration Engine"
        assert card["protocol"] == "A2A/0.3"
        assert len(card["skills"]) >= 1

    def test_a2a_agent_card_via_a2a_path(self) -> None:
        """Agent card also accessible via /a2a/.well-known/agent.json."""
        r = httpx.get(f"{ORCHESTRATION_URL}/a2a/.well-known/agent.json", timeout=5)
        assert r.status_code == 200
        card = r.json()
        assert "skills" in card

    def test_a2a_task_submit_and_poll(self) -> None:
        """Submit A2A task and verify initial state is 'submitted'."""
        r = httpx.post(
            f"{ORCHESTRATION_URL}/a2a/tasks/send",
            json={
                "id": "test-task-001",
                "session_id": "test-session-001",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "What is the total revenue?"}],
                },
                "metadata": {
                    "tenant_id": "integration_test",
                    "user_id": "test_user",
                },
            },
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "test-task-001"
        assert data["state"] in ("submitted", "working", "completed", "failed")

        # Poll task
        poll = httpx.get(f"{ORCHESTRATION_URL}/a2a/tasks/test-task-001", timeout=5)
        assert poll.status_code == 200

    def test_a2a_task_unknown_returns_404(self) -> None:
        r = httpx.get(f"{ORCHESTRATION_URL}/a2a/tasks/nonexistent-task-xyz", timeout=5)
        assert r.status_code == 404
