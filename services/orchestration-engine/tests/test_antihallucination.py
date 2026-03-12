"""
Unit tests for the 8-layer Anti-Hallucination Pipeline.
Day 10: ≥80% coverage. Tests each layer independently.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestration_engine.antihallucination.pipeline import (
    CoTAuditLayer,
    KnowledgeBoundaryLayer,
    RetrievalGroundingLayer,
    SelfConsistencyLayer,
    StructuredOutputLayer,
    TemporalGroundingLayer,
)
from orchestration_engine.models import ValidationLayer


# ── L1: Retrieval Grounding ───────────────────────────────────────────────────


class TestRetrievalGroundingLayer:
    @pytest.fixture
    def layer(self) -> RetrievalGroundingLayer:
        return RetrievalGroundingLayer()

    async def test_passes_with_citations(self, layer: RetrievalGroundingLayer) -> None:
        ctx = {"retrieved_chunks": [{"chunk_id": "c1"}, {"chunk_id": "c2"}]}
        result = await layer.validate("Revenue grew [SOURCE 1] and profit increased [SOURCE 2].", ctx)
        assert result.passed
        assert result.layer == ValidationLayer.L1_RETRIEVAL_GROUNDING

    async def test_fails_without_citations(self, layer: RetrievalGroundingLayer) -> None:
        ctx = {"retrieved_chunks": [{"chunk_id": "c1"}, {"chunk_id": "c2"}]}
        result = await layer.validate("Revenue grew significantly last year.", ctx)
        assert not result.passed
        assert result.action_taken == "flagged_amber"

    async def test_passes_with_no_chunks(self, layer: RetrievalGroundingLayer) -> None:
        ctx = {"retrieved_chunks": []}
        result = await layer.validate("Any answer here.", ctx)
        assert result.passed  # Skip check if no context


# ── L3: Self-Consistency ──────────────────────────────────────────────────────


class TestSelfConsistencyLayer:
    @pytest.fixture
    def layer(self) -> SelfConsistencyLayer:
        return SelfConsistencyLayer()

    async def test_skips_non_high_stakes(self, layer: SelfConsistencyLayer) -> None:
        ctx = {"is_high_stakes": False}
        result = await layer.validate("Any output.", ctx)
        assert result.passed
        assert "Skipped" in result.message

    async def test_passes_for_high_stakes_no_numbers(self, layer: SelfConsistencyLayer) -> None:
        ctx = {"is_high_stakes": True}
        result = await layer.validate("Revenue grew significantly without specific numbers.", ctx)
        assert result.passed


# ── L4: CoT Audit ────────────────────────────────────────────────────────────


class TestCoTAuditLayer:
    @pytest.fixture
    def layer(self) -> CoTAuditLayer:
        return CoTAuditLayer()

    async def test_passes_with_reasoning(self, layer: CoTAuditLayer) -> None:
        output = "Revenue increased because of strong Q4 sales, therefore we project growth."
        result = await layer.validate(output, {})
        assert result.passed
        assert result.score >= 0.9

    async def test_detects_contradiction(self, layer: CoTAuditLayer) -> None:
        output = "Sales increased significantly but also decreased this quarter."
        result = await layer.validate(output, {})
        assert not result.passed
        assert result.action_taken == "force_revision"

    async def test_passes_simple_output(self, layer: CoTAuditLayer) -> None:
        result = await layer.validate("Q4 revenue was $1.2M.", {})
        assert result.passed


# ── L5: Structured Output ─────────────────────────────────────────────────────


class TestStructuredOutputLayer:
    @pytest.fixture
    def layer(self) -> StructuredOutputLayer:
        return StructuredOutputLayer()

    async def test_passes_without_schema(self, layer: StructuredOutputLayer) -> None:
        result = await layer.validate("Any free-form output.", {})
        assert result.passed
        assert "No schema" in result.message


# ── L6: Knowledge Boundary ────────────────────────────────────────────────────


class TestKnowledgeBoundaryLayer:
    @pytest.fixture
    def layer(self) -> KnowledgeBoundaryLayer:
        return KnowledgeBoundaryLayer()

    async def test_detects_ood_phrase(self, layer: KnowledgeBoundaryLayer) -> None:
        output = "As of my knowledge cutoff, I cannot confirm this data."
        result = await layer.validate(output, {})
        assert not result.passed
        assert result.action_taken == "replace_with_insufficient_data"

    async def test_detects_fabrication_signal(self, layer: KnowledgeBoundaryLayer) -> None:
        output = "I believe the revenue was approximately maybe $5M."
        result = await layer.validate(output, {})
        assert not result.passed

    async def test_passes_clean_output(self, layer: KnowledgeBoundaryLayer) -> None:
        output = "Based on [SOURCE 1], revenue for Q4 was $1.2M [SOURCE 2]."
        result = await layer.validate(output, {})
        assert result.passed


# ── L7: Temporal Grounding ────────────────────────────────────────────────────


class TestTemporalGroundingLayer:
    @pytest.fixture
    def layer(self) -> TemporalGroundingLayer:
        return TemporalGroundingLayer()

    async def test_passes_no_stale_chunks(self, layer: TemporalGroundingLayer) -> None:
        ctx = {"retrieved_chunks": [{"stale": False}, {"stale": False}]}
        result = await layer.validate("Output.", ctx)
        assert result.passed
        assert result.score == 1.0

    async def test_fails_majority_stale(self, layer: TemporalGroundingLayer) -> None:
        ctx = {"retrieved_chunks": [
            {"stale": True}, {"stale": True}, {"stale": False}
        ]}
        result = await layer.validate("Output.", ctx)
        assert not result.passed
        assert result.action_taken == "add_staleness_warning"

    async def test_passes_minority_stale(self, layer: TemporalGroundingLayer) -> None:
        ctx = {"retrieved_chunks": [
            {"stale": True}, {"stale": False}, {"stale": False}, {"stale": False}
        ]}
        result = await layer.validate("Output.", ctx)
        assert result.passed

    async def test_passes_empty_chunks(self, layer: TemporalGroundingLayer) -> None:
        ctx = {"retrieved_chunks": []}
        result = await layer.validate("Output.", ctx)
        assert result.passed


# ── A2A Models ────────────────────────────────────────────────────────────────


class TestA2AModels:
    def test_agent_card_serialises(self) -> None:
        from orchestration_engine.a2a.server import _ORCHESTRATOR_CARD
        data = _ORCHESTRATOR_CARD.model_dump(mode="json")
        assert "skills" in data
        assert len(data["skills"]) >= 1
        assert data["protocol"] == "A2A/0.3"

    def test_a2a_task_default_state(self) -> None:
        from orchestration_engine.models import A2ATask, A2ATaskState
        task = A2ATask(session_id="s1", message={"parts": [{"type": "text", "text": "hello"}]})
        assert task.state == A2ATaskState.SUBMITTED
