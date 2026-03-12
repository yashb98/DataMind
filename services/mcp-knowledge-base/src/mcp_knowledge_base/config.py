"""
MCP Knowledge Base — Configuration.
Day 9: Phase 2 — MMR Qdrant + BM25 hybrid + ColBERT re-ranking.

Protocols: MCP (JSON-RPC 2.0, streamable-HTTP)
SOLID: SRP (config only), DIP (injected into all components)
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = "mcp-knowledge-base"
    port: int = 8050
    env: str = "development"

    # ── Qdrant ──────────────────────────────────────────────────────────────
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = ""
    # Collections (must exist — created by embedding service on Day 2)
    collection_knowledge_base: str = "knowledge_base"
    collection_agent_memory: str = "agent_memory"
    collection_entity_graph: str = "entity_graph"
    collection_schema_metadata: str = "schema_metadata"
    embedding_dim: int = 1024  # BAAI/bge-m3

    # ── Embedding Service ────────────────────────────────────────────────────
    embedding_service_url: str = "http://embedding:8030"

    # ── Neo4j (GraphRAG) ─────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"

    # ── Retrieval Parameters ─────────────────────────────────────────────────
    default_top_k: int = 20       # Candidates before re-ranking
    default_final_k: int = 5      # Results after MMR / re-ranking
    mmr_lambda: float = 0.7       # MMR relevance-diversity trade-off (0=diverse, 1=relevant)
    mmr_lambda_exploratory: float = 0.5
    mmr_lambda_precise: float = 0.9
    max_chunks_per_source: int = 3  # Cap per source document (prevents one source dominating)
    staleness_threshold_days: int = 90  # L7: temporal grounding flag

    # ── BM25 ─────────────────────────────────────────────────────────────────
    bm25_weight: float = 0.3      # Hybrid fusion weight (0.3 BM25 + 0.7 dense)
    dense_weight: float = 0.7

    # ── OpenTelemetry ────────────────────────────────────────────────────────
    otel_endpoint: str = "http://otel-collector:4317"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
