"""
RAG API — Pydantic request/response models.
Day 22: Phase 5 — All I/O shapes for memory, retrieval, graphrag, and evaluation.

Protocols: None
SOLID: SRP (data shapes only)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────


class MemoryTier(str, Enum):
    STM = "stm"
    LTM = "ltm"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


class MMRMode(str, Enum):
    DEFAULT = "default"
    PRECISE = "precise"
    EXPLORATORY = "exploratory"


# ── Memory Models ──────────────────────────────────────────────────────────────


class MemoryEntry(BaseModel):
    """A single unit of agent memory, shared across all 4 tiers."""

    memory_id: str
    tenant_id: str
    agent_id: str
    session_id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    tier: MemoryTier
    created_at: datetime
    expires_at: datetime | None = None


class StoreMemoryRequest(BaseModel):
    content: str = Field(..., min_length=1)
    agent_id: str
    session_id: str
    tenant_id: str
    tiers: list[MemoryTier] = Field(default=[MemoryTier.STM])
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoreMemoryResponse(BaseModel):
    memory_ids: dict[str, str]  # {tier: memory_id}
    tenant_id: str


class RetrieveMemoryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    agent_id: str
    tenant_id: str
    tiers: list[MemoryTier] = Field(
        default=[MemoryTier.STM, MemoryTier.LTM, MemoryTier.EPISODIC]
    )
    top_k: int = Field(default=5, ge=1, le=50)


class RetrieveMemoryResponse(BaseModel):
    memories: list[MemoryEntry]
    total: int
    tiers_queried: list[MemoryTier]


class PromoteMemoryRequest(BaseModel):
    memory_id: str
    from_tier: MemoryTier
    to_tier: MemoryTier
    tenant_id: str


class PromoteMemoryResponse(BaseModel):
    new_memory_id: str
    from_tier: MemoryTier
    to_tier: MemoryTier


class DSREraseResponse(BaseModel):
    tenant_id: str
    deleted: dict[str, int]  # {tier: count}
    total_deleted: int


# ── Retrieval Models ───────────────────────────────────────────────────────────


class RetrievedChunk(BaseModel):
    chunk_id: str
    source_id: str
    content: str
    score: float = Field(..., ge=0.0, le=1.0)
    stale: bool = False
    ingestion_date: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MMRRetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    tenant_id: str
    collection: str = "knowledge_base"
    top_k: int = Field(default=10, ge=1, le=50)
    lambda_param: float | None = Field(default=None, ge=0.0, le=1.0)
    mode: MMRMode = MMRMode.DEFAULT


class MMRRetrievalResponse(BaseModel):
    chunks: list[RetrievedChunk]
    total_candidates: int
    lambda_used: float
    retrieval_ms: float
    stale_count: int


class EvaluateRequest(BaseModel):
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    contexts: list[str] = Field(..., min_length=1)
    ground_truth: str | None = None
    tenant_id: str = "system"
    run_name: str | None = None


# ── GraphRAG Models ────────────────────────────────────────────────────────────


class Entity(BaseModel):
    id: str
    name: str
    entity_type: str
    description: str = ""


class Relationship(BaseModel):
    source_id: str
    target_id: str
    relation: str
    weight: float = 1.0


class ExtractedGraph(BaseModel):
    entities: list[Entity]
    relationships: list[Relationship]
    source_text: str = ""


class GraphIngestRequest(BaseModel):
    text: str = Field(..., min_length=1)
    tenant_id: str
    source_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphIngestResponse(BaseModel):
    tenant_id: str
    entities_upserted: int
    relationships_upserted: int
    source_id: str


class GraphSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    tenant_id: str
    max_hops: int = Field(default=2, ge=1, le=4)
    limit: int = Field(default=10, ge=1, le=50)


class GraphSearchResponse(BaseModel):
    query: str
    tenant_id: str
    community_summaries: list[str]
    entities_found: list[dict[str, Any]]
    total: int


class GraphDSRResponse(BaseModel):
    tenant_id: str
    nodes_deleted: int


# ── RAGAS Eval Models ──────────────────────────────────────────────────────────


class RAGASResult(BaseModel):
    faithfulness: float = Field(..., ge=0.0, le=1.0)
    answer_relevancy: float = Field(..., ge=0.0, le=1.0)
    context_recall: float | None = None
    run_id: str | None = None
    tenant_id: str = "system"
    latency_ms: float = 0.0
