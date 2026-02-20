"""
DataMind API Configuration — Pydantic Settings (DIP compliant).
All config loaded from environment variables / .env file.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    env: Literal["development", "staging", "production"] = "development"
    secret_key: str = Field(default="dev-secret-change-in-prod")
    cors_origins: list[str] = Field(default=["http://localhost:3000"])
    log_level: str = "info"

    # LiteLLM
    litellm_proxy_url: str = "http://localhost:4000"
    litellm_master_key: str = "sk-litellm-dev"

    # Langfuse
    langfuse_public_key: str = "lf-pk-dev"
    langfuse_secret_key: str = "lf-sk-dev"
    langfuse_host: str = "http://localhost:3001"

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://datamind:changeme@localhost:5432/datamind"

    # ClickHouse
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_db: str = "analytics"
    clickhouse_user: str = "default"
    clickhouse_password: str = "changeme"

    # Redis
    redis_url: str = "redis://:changeme@localhost:6379"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # MongoDB
    mongodb_url: str = "mongodb://datamind:changeme@localhost:27017/datamind"

    # Neo4j
    neo4j_url: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_schema_registry_url: str = "http://localhost:8081"

    # Ollama
    ollama_url: str = "http://localhost:11434"

    # Nessie
    nessie_url: str = "http://localhost:19120/api/v1"

    # GDPR
    presidio_analyzer_url: str = "http://localhost:5001"
    presidio_anonymizer_url: str = "http://localhost:5002"
    fpe_encryption_key: str = "00000000000000000000000000000000"

    # Vault
    vault_url: str = "http://localhost:8200"
    vault_token: str = "root-token-dev-only"

    # OpenTelemetry
    otel_endpoint: str = "http://localhost:4317"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",")]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
