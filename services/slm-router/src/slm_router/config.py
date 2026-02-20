"""SLM Router configuration — DIP-compliant via Pydantic Settings."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # Service
    service_name: str = "datamind-slm-router"
    port: int = 8020
    log_level: str = "info"
    env: str = "development"

    # Ollama — SLM inference
    ollama_url: str = "http://ollama:11434"
    intent_model: str = "phi3.5"         # intent + sensitivity
    complexity_model: str = "gemma2:2b"  # complexity scoring
    ollama_timeout_s: int = 15
    slm_confidence_threshold: float = 0.85  # below = escalate tier

    # Redis — routing decision cache
    redis_url: str = "redis://:changeme@redis:6379"
    cache_ttl_s: int = 300  # 5 min cache for identical queries

    # LiteLLM models by tier
    cloud_default_model: str = "claude-sonnet-4-6"
    cloud_sql_model: str = "codestral:22b"
    cloud_analysis_model: str = "llama3.3:70b"
    rlm_model: str = "deepseek-r1:32b"
    edge_model: str = "phi3.5"

    # Latency budgets (ms)
    latency_edge_ms: int = 100
    latency_slm_ms: int = 500
    latency_cloud_ms: int = 5_000
    latency_rlm_ms: int = 60_000

    # Complexity thresholds (from 0..1 complexity score)
    complexity_simple_max: float = 0.35
    complexity_medium_max: float = 0.65
    complexity_complex_max: float = 0.85
    # > complex_max → expert/RLM

    # Observability
    langfuse_public_key: str = "lf-pk-dev"
    langfuse_secret_key: str = "lf-sk-dev"
    langfuse_host: str = "http://langfuse-web:3000"
    otel_endpoint: str = "http://otel-collector:4317"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
