"""
MCP Knowledge Base — Pydantic models for retrieval I/O.
Day 9: MMR + BM25 + ColBERT result shapes.

Protocols: MCP
SOLID: SRP (data shapes only)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RetrievalMode(str, Enum):
    DENSE = "dense"          # Pure vector similarity
    BM25 = "bm25"            # Sparse keyword
    HYBRID = "hybrid"        # BM25 + dense fusion (default)
    MMR = "mmr"              # Maximal Marginal Relevance (diversity-aware)
    GRAPH = "graph"          # Neo4j community summary traversal


class RetrievedChunk(BaseModel):
    chunk_id: str
    source_id: str
    source_type: str   # "document", "table", "api", "report"
    content: str
    score: float = Field(..., ge=0.0, le=1.0)
    tenant_id: str
    ingested_at: datetime | None = None
    stale: bool = False  # L7: flagged if > staleness_threshold_days
    metadata: dict[str, object] = Field(default_factory=dict)


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8_000)
    tenant_id: str
    collection: str = "knowledge_base"
    mode: RetrievalMode = RetrievalMode.HYBRID
    top_k: int = Field(default=5, ge=1, le=50)
    mmr_lambda: float | None = Field(default=None, ge=0.0, le=1.0)
    filters: dict[str, object] | None = None


class RetrieveResponse(BaseModel):
    chunks: list[RetrievedChunk]
    total_candidates: int
    mode_used: RetrievalMode
    query_embedding_ms: float
    retrieval_ms: float
    reranking_ms: float = 0.0
    stale_chunks: int = 0  # L7 temporal grounding count


class GraphSearchRequest(BaseModel):
    entity: str = Field(..., description="Entity name to traverse from in the knowledge graph")
    tenant_id: str
    max_hops: int = Field(default=2, ge=1, le=4)
    limit: int = Field(default=10, ge=1, le=50)


class GraphSearchResult(BaseModel):
    entity: str
    related_entities: list[dict[str, object]]
    community_summary: str | None = None
    path_count: int
