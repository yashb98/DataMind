"""
MCP Report Generator — Configuration.
Day 11: Phase 2 — WeasyPrint PDF + PPTX + Merkle provenance + IPFS anchoring.

Protocols: MCP (JSON-RPC 2.0, streamable-HTTP)
SOLID: SRP (config only), DIP (injected into all components)
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = "mcp-report-generator"
    port: int = 8080
    env: str = "development"

    # ── MinIO ────────────────────────────────────────────────────────────────
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_bucket: str = "datamind-reports"
    minio_secure: bool = False

    # ── Pinata IPFS (optional — gracefully degraded if not set) ──────────────
    pinata_api_key: str = ""
    pinata_secret_key: str = ""
    pinata_endpoint: str = "https://api.pinata.cloud"

    # ── OpenTelemetry ────────────────────────────────────────────────────────
    otel_endpoint: str = "http://otel-collector:4317"

    # ── Langfuse ─────────────────────────────────────────────────────────────
    langfuse_host: str = "http://langfuse:3000"
    langfuse_public_key: str = "pk-lf-datamind"
    langfuse_secret_key: str = "sk-lf-datamind"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
