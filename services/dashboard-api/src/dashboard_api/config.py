"""
Dashboard API Config — Pydantic Settings for dashboard-api service.
Day 15: Phase 3 — Visualization & Dashboard backend configuration.

Protocols: None
SOLID: SRP (config only), DIP (injected via lru_cache)
Benchmark: N/A
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Dashboard API service configuration.

    All values can be overridden via environment variables or .env file.
    """

    service_name: str = "dashboard-api"
    port: int = 8110

    # PostgreSQL
    postgres_dsn: str = "postgresql://datamind:datamind_pass@postgres:5432/datamind_core"

    # Redis
    redis_url: str = "redis://:changeme@redis:6379"

    # Kafka
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_agent_events: str = "agent.events"
    kafka_group_id: str = "dashboard-api"

    # Downstream services
    orchestration_engine_url: str = "http://orchestration-engine:8060"
    mcp_report_generator_url: str = "http://mcp-report-generator:8080/mcp/"

    # OTel
    otel_endpoint: str = "http://otel-collector:4317"

    # Langfuse
    langfuse_host: str = "http://langfuse:3000"
    langfuse_public_key: str = "pk-lf-datamind"
    langfuse_secret_key: str = "sk-lf-datamind"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()


settings = get_settings()
