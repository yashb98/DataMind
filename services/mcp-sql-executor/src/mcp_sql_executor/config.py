"""
MCP SQL Executor — Configuration.
Day 8: Phase 2 MCP Tool Server — NL-to-SQL, execution, verification.

Protocols: MCP (JSON-RPC 2.0, streamable-HTTP)
SOLID: SRP (config only), DIP (injected into all components)
Benchmark: tests/benchmarks/bench_nl_to_sql.py
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = "mcp-sql-executor"
    port: int = 8040
    env: str = "development"

    # ── PostgreSQL ──────────────────────────────────────────────────────────
    postgres_url: str = "postgresql+asyncpg://datamind:changeme@postgres:5432/datamind"
    postgres_sync_url: str = "postgresql://datamind:changeme@postgres:5432/datamind"
    postgres_schema: str = "datamind_core"

    # ── ClickHouse ──────────────────────────────────────────────────────────
    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 8123
    clickhouse_db: str = "analytics"
    clickhouse_user: str = "default"
    clickhouse_password: str = "changeme"

    # ── LiteLLM ─────────────────────────────────────────────────────────────
    litellm_url: str = "http://litellm:4000"
    litellm_api_key: str = "sk-litellm-dev"
    nl_to_sql_model: str = "claude-sonnet-4"
    nl_to_sql_max_tokens: int = 2048
    nl_to_sql_temperature: float = 0.0  # Deterministic SQL generation

    # ── Langfuse ────────────────────────────────────────────────────────────
    langfuse_public_key: str = "lf-pk-dev"
    langfuse_secret_key: str = "lf-sk-dev"
    langfuse_host: str = "http://langfuse-web:3000"

    # ── OpenTelemetry ───────────────────────────────────────────────────────
    otel_endpoint: str = "http://otel-collector:4317"

    # ── Safety Limits ───────────────────────────────────────────────────────
    max_rows: int = 10_000          # Hard cap on result set size
    query_timeout_s: int = 30       # SQL execution timeout
    max_schema_tables: int = 100    # Max tables to include in context


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
