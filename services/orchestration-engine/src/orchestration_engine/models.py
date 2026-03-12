"""
Orchestration Engine — Pydantic models for agent requests, workflow state, and A2A protocol.
Day 10: LangGraph state types + A2A task lifecycle models.

Protocols: MCP (client), A2A (server)
SOLID: SRP (data shapes only)
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


# ── Agent Workflow ────────────────────────────────────────────────────────────


class WorkflowIntent(str, Enum):
    SQL_QUERY = "sql_query"
    EDA = "eda"
    VISUALIZATION = "visualization"
    FORECASTING = "forecasting"
    REPORT = "report"
    CAUSAL = "causal"
    COMPLIANCE = "compliance"
    NLP = "nlp"
    GEOSPATIAL = "geospatial"
    MONITORING = "monitoring"
    DATA_QUALITY = "data_quality"
    GENERAL = "general"


class ComplexityTier(str, Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    EXPERT = "expert"


class WorkflowRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=32_000)
    tenant_id: str
    user_id: str
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    dataset_ids: list[str] = Field(default_factory=list)
    intent_hint: WorkflowIntent | None = None
    enable_human_gate: bool = True
    max_steps: int = Field(default=25, ge=1, le=50)


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_HUMAN = "awaiting_human"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentResult(BaseModel):
    """Standardised result from any agent node. LSP: never None from BaseAgent.execute()."""
    agent_name: str
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    tokens_used: int = 0
    latency_ms: float = 0.0
    langfuse_trace_id: str | None = None


class WorkflowResponse(BaseModel):
    workflow_id: str
    status: WorkflowStatus
    intent: WorkflowIntent
    result: dict[str, Any] | None = None
    agent_steps: list[AgentResult] = Field(default_factory=list)
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    anti_hallucination_passed: bool = True
    validation_details: list[str] = Field(default_factory=list)
    langfuse_trace_id: str | None = None


# ── Anti-Hallucination ────────────────────────────────────────────────────────


class ValidationLayer(str, Enum):
    L1_RETRIEVAL_GROUNDING = "L1_retrieval_grounding"
    L2_NLI_FAITHFULNESS = "L2_nli_faithfulness"
    L3_SELF_CONSISTENCY = "L3_self_consistency"
    L4_COT_AUDIT = "L4_cot_audit"
    L5_STRUCTURED_OUTPUT = "L5_structured_output"
    L6_KNOWLEDGE_BOUNDARY = "L6_knowledge_boundary"
    L7_TEMPORAL_GROUNDING = "L7_temporal_grounding"
    L8_NUMERICAL_VERIFICATION = "L8_numerical_verification"


class ValidationResult(BaseModel):
    layer: ValidationLayer
    passed: bool
    score: float | None = None
    message: str = ""
    action_taken: str = ""  # "none", "regenerated", "flagged", "blocked"


class PipelineResult(BaseModel):
    overall_passed: bool
    layer_results: list[ValidationResult]
    regeneration_count: int = 0
    final_output: str


# ── A2A Protocol (Google A2A v0.3) ────────────────────────────────────────────


class A2ATaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"


class A2ASkill(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    input_modes: list[str] = Field(default=["text"])
    output_modes: list[str] = Field(default=["text"])


class AgentCard(BaseModel):
    """A2A Agent Card — published at .well-known/agent.json per spec."""
    name: str
    description: str
    url: str  # Base URL of the agent's A2A endpoint
    version: str = "0.1.0"
    protocol: str = "A2A/0.3"
    skills: list[A2ASkill] = Field(default_factory=list)
    authentication: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class A2ATask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    state: A2ATaskState = A2ATaskState.SUBMITTED
    message: dict[str, Any]  # A2A Message format
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class A2ASendTaskRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    message: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class A2ATaskResponse(BaseModel):
    id: str
    session_id: str
    state: A2ATaskState
    result: dict[str, Any] | None = None
    error: str | None = None
