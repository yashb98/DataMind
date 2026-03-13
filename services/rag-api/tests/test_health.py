"""
RAG API — Integration-style tests for health endpoints and router wiring.
Day 22: Phase 5 — Tests that the FastAPI app starts and health endpoints respond.

Coverage target: ≥80%
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient


# ── Health endpoints ──────────────────────────────────────────────────────────


def test_liveness_endpoint() -> None:
    """GET /health/liveness returns 200 with alive status."""
    # Patch all heavy dependencies to avoid real connections
    with (
        patch("rag_api.main.asyncpg.create_pool", new_callable=AsyncMock) as mock_pg,
        patch("rag_api.main.AsyncIOMotorClient") as mock_mongo,
        patch("rag_api.main.Redis.from_url") as mock_redis,
        patch("rag_api.main.AsyncQdrantClient") as mock_qdrant,
        patch("rag_api.main.AsyncGraphDatabase.driver") as mock_neo4j,
        patch("rag_api.main.NarrativeAgent") as mock_narrative,
        patch("rag_api.main.CompilerAgent"),
        patch("rag_api.main.DSRAutomation") as mock_dsr,
    ):
        # Setup mock returns for lifespan
        mock_pg.return_value = AsyncMock()
        mock_mongo.return_value = MagicMock()
        mock_qdrant.return_value = AsyncMock()
        neo4j_mock = AsyncMock()
        neo4j_mock.verify_connectivity = AsyncMock()
        mock_neo4j.return_value = neo4j_mock

        narrative_inst = AsyncMock()
        narrative_inst.startup = AsyncMock()
        narrative_inst.shutdown = AsyncMock()
        mock_narrative.return_value = narrative_inst

        dsr_inst = AsyncMock()
        dsr_inst.startup = AsyncMock()
        mock_dsr.return_value = dsr_inst

        from rag_api.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/health/liveness")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "alive"
            assert "service" in data


# ── Models validation ─────────────────────────────────────────────────────────


def test_store_memory_request_validation() -> None:
    """StoreMemoryRequest validates required fields."""
    from pydantic import ValidationError
    from rag_api.models import StoreMemoryRequest, MemoryTier

    with pytest.raises(ValidationError):
        # content is required
        StoreMemoryRequest(
            agent_id="aria",
            session_id="s1",
            tenant_id="t1",
            content="",  # min_length=1
        )


def test_mmr_retrieval_request_defaults() -> None:
    """MMRRetrievalRequest uses correct defaults."""
    from rag_api.models import MMRRetrievalRequest, MMRMode

    req = MMRRetrievalRequest(query="test", tenant_id="t1")
    assert req.collection == "knowledge_base"
    assert req.top_k == 10
    assert req.mode == MMRMode.DEFAULT
    assert req.lambda_param is None


def test_graph_ingest_request_defaults() -> None:
    """GraphIngestRequest uses correct defaults."""
    from rag_api.models import GraphIngestRequest

    req = GraphIngestRequest(text="some text", tenant_id="t1")
    assert req.source_id == ""
    assert req.metadata == {}


def test_evaluate_request_optional_ground_truth() -> None:
    """EvaluateRequest allows ground_truth to be None."""
    from rag_api.models import EvaluateRequest

    req = EvaluateRequest(
        question="What is RAG?",
        answer="RAG is retrieval augmented generation.",
        contexts=["RAG stands for Retrieval Augmented Generation."],
        tenant_id="t1",
    )
    assert req.ground_truth is None
    assert req.run_name is None
