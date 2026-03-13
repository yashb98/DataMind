"""
RAG API — Configuration.
Day 22: Phase 5 — Pydantic Settings for all downstream connections.

Protocols: None
SOLID: SRP (config only), DIP (injected into all components)
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """RAG API service configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = "rag-api"
    port: int = 8130
    env: str = "development"

    # ── Storage ──────────────────────────────────────────────────────────────
    redis_url: str = "redis://:datamind@redis:6379/0"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = ""
    mongodb_url: str = "mongodb://datamind:datamind@mongo:27017/datamind_memory"
    postgres_url: str = "postgresql://datamind:datamind@postgres:5432/datamind"
    neo4j_url: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "datamind123"

    # ── Downstream Services ──────────────────────────────────────────────────
    embedding_service_url: str = "http://embedding:8030"
    litellm_url: str = "http://litellm:4000"

    # ── Observability ────────────────────────────────────────────────────────
    mlflow_tracking_uri: str = "http://mlflow:5000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://langfuse-web:3000"
    otlp_endpoint: str = "http://otel-collector:4317"

    # ── Memory Tier Parameters ────────────────────────────────────────────────
    stm_ttl_seconds: int = 1800           # 30 min Redis STM
    ltm_collection: str = "agent_memory"  # Qdrant collection
    episodic_db: str = "datamind_memory"
    episodic_collection: str = "episodic_memory"
    episodic_ttl_days: int = 365          # 1-year MongoDB TTL

    # ── Retrieval Parameters ─────────────────────────────────────────────────
    mmr_lambda: float = 0.7               # Default λ for MMR
    mmr_lambda_exploratory: float = 0.5
    mmr_lambda_precise: float = 0.9
    mmr_top_k: int = 10
    max_chunks_per_source: int = 3
    staleness_days: int = 90

    # ── LLM Parameters ───────────────────────────────────────────────────────
    default_model: str = "gpt-4o"         # via LiteLLM proxy
    graphrag_model: str = "gpt-4o"
    ragas_model: str = "gpt-4o"
    embedding_dim: int = 1024             # BAAI/bge-m3

    # ── Semantic Facts Table ──────────────────────────────────────────────────
    semantic_facts_schema: str = "datamind_agents"

    # ── MinIO (for DSR erasure) ───────────────────────────────────────────────
    minio_url: str = "http://minio:9000"
    minio_access_key: str = "datamind"
    minio_secret_key: str = "datamind123"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()


settings = get_settings()
