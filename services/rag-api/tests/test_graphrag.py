"""
RAG API — Unit tests for GraphRAG extractor, Neo4j store, and pipeline.
Day 22: Phase 5 — Tests for entity extraction parsing and pipeline orchestration.

Coverage target: ≥80%
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag_api.graphrag.extractor import EntityExtractor, _parse_graph
from rag_api.graphrag.pipeline import GraphRAGPipeline
from rag_api.models import Entity, ExtractedGraph, Relationship


# ── _parse_graph ──────────────────────────────────────────────────────────────


def test_parse_graph_valid_json() -> None:
    """_parse_graph correctly parses well-formed LLM JSON output."""
    raw = json.dumps(
        {
            "entities": [
                {"id": "e1", "name": "OpenAI", "type": "org", "description": "AI company"}
            ],
            "relationships": [
                {"source_id": "e1", "target_id": "e2", "relation": "founded", "weight": 1.0}
            ],
        }
    )
    graph = _parse_graph(raw, source_text="text")

    assert len(graph.entities) == 1
    assert graph.entities[0].name == "OpenAI"
    assert graph.entities[0].entity_type == "org"
    assert len(graph.relationships) == 1
    assert graph.relationships[0].relation == "founded"


def test_parse_graph_empty_arrays() -> None:
    """_parse_graph handles empty entity/relationship arrays gracefully."""
    raw = json.dumps({"entities": [], "relationships": []})
    graph = _parse_graph(raw, source_text="nothing")
    assert graph.entities == []
    assert graph.relationships == []


def test_parse_graph_invalid_json_raises() -> None:
    """_parse_graph raises ValueError on malformed JSON."""
    with pytest.raises(ValueError, match="invalid JSON"):
        _parse_graph("not json {{{", source_text="text")


def test_parse_graph_missing_fields_uses_defaults() -> None:
    """_parse_graph uses defaults for missing optional fields."""
    raw = json.dumps(
        {
            "entities": [{"name": "Aria"}],
            "relationships": [],
        }
    )
    graph = _parse_graph(raw, source_text="text")
    assert graph.entities[0].entity_type == "concept"  # default type
    assert graph.entities[0].description == ""


# ── EntityExtractor ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extractor_returns_graph_on_success() -> None:
    """EntityExtractor returns populated ExtractedGraph on successful LLM call."""
    mock_http = AsyncMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "entities": [
                                    {
                                        "id": "e1",
                                        "name": "DataMind",
                                        "type": "org",
                                        "description": "AI analytics platform",
                                    }
                                ],
                                "relationships": [],
                            }
                        )
                    }
                }
            ]
        }
    )
    mock_http.post = AsyncMock(return_value=mock_response)

    from rag_api.config import Settings
    extractor = EntityExtractor(http=mock_http, settings=Settings())  # type: ignore[arg-type]
    graph = await extractor.extract(text="DataMind is an AI analytics platform.", tenant_id="t1")

    assert len(graph.entities) == 1
    assert graph.entities[0].name == "DataMind"


@pytest.mark.asyncio
async def test_extractor_returns_empty_graph_on_llm_error() -> None:
    """EntityExtractor returns empty graph (not exception) when LLM fails."""
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(side_effect=Exception("timeout"))

    from rag_api.config import Settings
    extractor = EntityExtractor(http=mock_http, settings=Settings())  # type: ignore[arg-type]
    graph = await extractor.extract(text="some text", tenant_id="t1")

    assert graph.entities == []
    assert graph.relationships == []


# ── GraphRAGPipeline ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_ingest_calls_extractor_and_store() -> None:
    """GraphRAGPipeline.ingest calls extractor + store upsert methods."""
    mock_extractor = AsyncMock()
    mock_extractor.extract = AsyncMock(
        return_value=ExtractedGraph(
            entities=[Entity(id="e1", name="Aria", entity_type="person", description="AI agent")],
            relationships=[],
        )
    )

    mock_store = AsyncMock()
    mock_store.upsert_entities = AsyncMock()
    mock_store.upsert_relationships = AsyncMock()

    pipeline = GraphRAGPipeline(extractor=mock_extractor, store=mock_store)  # type: ignore[arg-type]
    result = await pipeline.ingest(text="Aria is a data analyst.", tenant_id="t1", source_id="doc-1")

    mock_extractor.extract.assert_awaited_once()
    mock_store.upsert_entities.assert_awaited_once()
    assert result.entities_upserted == 1
    assert result.relationships_upserted == 0


@pytest.mark.asyncio
async def test_pipeline_search_returns_community_summaries() -> None:
    """GraphRAGPipeline.search returns community summaries from Neo4j."""
    mock_extractor = AsyncMock()
    mock_extractor.extract = AsyncMock(
        return_value=ExtractedGraph(
            entities=[Entity(id="e1", name="OpenAI", entity_type="org", description="")],
            relationships=[],
        )
    )

    mock_store = AsyncMock()
    mock_store.get_community_summaries = AsyncMock(
        return_value=["[org] Anthropic: AI safety company", "[person] Sam Altman: CEO"]
    )
    mock_store.get_neighbours = AsyncMock(
        return_value=[{"name": "Anthropic", "type": "org", "description": "AI safety", "min_hops": 1}]
    )

    pipeline = GraphRAGPipeline(extractor=mock_extractor, store=mock_store)  # type: ignore[arg-type]
    result = await pipeline.search(query="OpenAI competitors", tenant_id="t1")

    assert len(result.community_summaries) == 2
    assert result.total >= 1
