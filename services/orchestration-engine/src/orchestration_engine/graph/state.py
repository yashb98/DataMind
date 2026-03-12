"""
Orchestration Engine — LangGraph State definition.
Day 10: TypedDict state passed between all graph nodes.

Protocols: None (internal LangGraph state)
SOLID: SRP (state schema only)
"""

from __future__ import annotations

from typing import Annotated, Any

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from orchestration_engine.models import (
    AgentResult,
    ComplexityTier,
    ValidationResult,
    WorkflowIntent,
    WorkflowStatus,
)


class AgentState(TypedDict):
    """LangGraph state passed between nodes.

    All fields must be serialisable for durable execution (Redis checkpoint).
    """

    # ── Workflow identity ─────────────────────────────────────────────────────
    workflow_id: str
    session_id: str
    tenant_id: str
    user_id: str

    # ── Input ─────────────────────────────────────────────────────────────────
    query: str
    dataset_ids: list[str]

    # ── Routing ───────────────────────────────────────────────────────────────
    intent: WorkflowIntent | None
    complexity: ComplexityTier | None
    is_sensitive: bool

    # ── Messages (LangGraph managed — supports add_messages reducer) ──────────
    messages: Annotated[list[Any], add_messages]

    # ── Working data ──────────────────────────────────────────────────────────
    retrieved_chunks: list[dict[str, Any]]  # From mcp-knowledge-base
    sql_result: dict[str, Any] | None       # From mcp-sql-executor
    generated_sql: str | None
    llm_output: str | None
    structured_output: dict[str, Any] | None

    # ── Anti-Hallucination ────────────────────────────────────────────────────
    validation_results: list[ValidationResult]
    regeneration_count: int
    anti_hallucination_passed: bool

    # ── Execution tracking ────────────────────────────────────────────────────
    agent_steps: list[AgentResult]
    current_step: int
    max_steps: int
    status: WorkflowStatus

    # ── Human gate ────────────────────────────────────────────────────────────
    awaiting_human: bool
    human_feedback: str | None

    # ── Output ────────────────────────────────────────────────────────────────
    final_response: dict[str, Any] | None
    error: str | None

    # ── Observability ─────────────────────────────────────────────────────────
    langfuse_trace_id: str | None
    total_tokens: int
    total_latency_ms: float
