"""
Orchestration Engine — Configuration.
Day 10: LangGraph orchestrator + anti-hallucination pipeline + A2A protocol.

Protocols: MCP (client, calls tool servers), A2A (server, delegates to Digital Workers)
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

    service_name: str = "orchestration-engine"
    port: int = 8060
    env: str = "development"

    # ── LiteLLM ─────────────────────────────────────────────────────────────
    litellm_url: str = "http://litellm:4000"
    litellm_api_key: str = "sk-litellm-dev"

    # LLM model assignments (matching CLAUDE.md Digital Workers)
    cloud_model: str = "claude-sonnet-4"          # Aria, Atlas, Echo
    rlm_model: str = "deepseek/deepseek-r1:32b"   # Luna, Nova, Sage, Quant
    local_model: str = "ollama/llama3.3:70b"       # Iris, Rex, Geo
    slm_model: str = "ollama/phi3.5"               # Swift, routing

    # Prompt caching — Anthropic
    enable_prompt_caching: bool = True

    # ── SLM Router ───────────────────────────────────────────────────────────
    slm_router_url: str = "http://slm-router:8020"

    # ── MCP Tool Servers ─────────────────────────────────────────────────────
    mcp_sql_executor_url: str = "http://mcp-sql-executor:8040/mcp/"
    mcp_knowledge_base_url: str = "http://mcp-knowledge-base:8050/mcp/"

    # ── Redis (agent working memory) ─────────────────────────────────────────
    redis_url: str = "redis://:changeme@redis:6379"
    redis_stm_ttl_s: int = 1800  # 30 min short-term memory

    # ── Langfuse ────────────────────────────────────────────────────────────
    langfuse_public_key: str = "lf-pk-dev"
    langfuse_secret_key: str = "lf-sk-dev"
    langfuse_host: str = "http://langfuse-web:3000"

    # ── OpenTelemetry ────────────────────────────────────────────────────────
    otel_endpoint: str = "http://otel-collector:4317"

    # ── Anti-Hallucination Pipeline ──────────────────────────────────────────
    nli_threshold: float = 0.7              # L2: DeBERTa NLI faithfulness
    self_consistency_samples: int = 5       # L3: samples at T=0.7
    enable_self_consistency: bool = True    # L3: only for high-stakes (finance/legal/medical)
    temporal_staleness_days: int = 90       # L7: flag chunks older than N days
    numerical_tolerance: float = 0.01      # L8: 1% tolerance for number verification

    # ── LangGraph ────────────────────────────────────────────────────────────
    max_agent_steps: int = 25           # Hard ceiling on graph traversal steps
    human_gate_enabled: bool = True     # L4: human-in-the-loop for high-stakes
    agent_timeout_s: int = 300          # 5-minute hard timeout per workflow

    # ── A2A Protocol ─────────────────────────────────────────────────────────
    a2a_registry_url: str = ""  # Worker Agent Card registry (self-hosted or external)
    a2a_task_timeout_s: int = 600  # 10-minute timeout for Digital Worker tasks


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
