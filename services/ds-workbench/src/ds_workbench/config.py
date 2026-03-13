"""
DS Workbench Config — Pydantic Settings for Phase 4 Data Science Workbench.
Day 18: Phase 4 — AutoML, Forecasting, Causal Inference, Model Deployment.

Protocols: None (REST only — no MCP/A2A in this service)
SOLID: SRP (configuration only), DIP (injected via get_settings())
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "ds-workbench"
    port: int = 8120

    # MLflow
    mlflow_tracking_uri: str = "http://mlflow:5000"
    mlflow_experiment_name: str = "datamind-automl"

    # MinIO (for storing trained models + artifacts)
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_bucket: str = "datamind-models"
    minio_secure: bool = False

    # LiteLLM (for causal analysis with DeepSeek-R1)
    litellm_url: str = "http://litellm:4000"
    litellm_api_key: str = "sk-litellm-dev"
    rlm_model: str = "deepseek/deepseek-r1:32b"

    # OTel + Langfuse
    otel_endpoint: str = "http://otel-collector:4317"
    langfuse_host: str = "http://langfuse:3000"
    langfuse_public_key: str = "pk-lf-datamind"
    langfuse_secret_key: str = "sk-lf-datamind"

    # AutoML defaults
    automl_time_limit_s: int = 300
    automl_presets: str = "medium_quality"

    # D-Wave (optional, falls back to classical QUBO)
    dwave_api_token: str = ""
    dwave_endpoint: str = "https://cloud.dwavesys.com/sapi/v2"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
