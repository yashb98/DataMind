"""
Config — Pydantic Settings for mcp-dbt-runner.
Day 11: Phase 2 — dbt Runner configuration.

Protocols: None
SOLID: SRP (configuration only)
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration loaded from environment variables."""

    service_name: str = "mcp-dbt-runner"
    port: int = 8090

    # dbt project
    dbt_project_dir: str = "/dbt/project"
    dbt_profiles_dir: str = "/dbt/profiles"
    dbt_target: str = "dev"

    # PostgreSQL (dbt target)
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "datamind_core"
    postgres_user: str = "datamind"
    postgres_password: str = "datamind_pass"
    postgres_schema: str = "dbt_datamind"

    # Neo4j for lineage
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "datamind_neo4j"

    # OTel + Langfuse
    otel_endpoint: str = "http://otel-collector:4317"
    langfuse_host: str = "http://langfuse:3000"
    langfuse_public_key: str = "pk-lf-datamind"
    langfuse_secret_key: str = "sk-lf-datamind"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance.

    Returns:
        Singleton Settings loaded from environment.
    """
    return Settings()


settings = get_settings()
