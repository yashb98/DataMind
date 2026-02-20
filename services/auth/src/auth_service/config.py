"""Auth service configuration."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    service_name: str = "datamind-auth"
    port: int = 8010
    env: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://datamind:changeme@localhost:5432/datamind"

    # Redis (token revocation store)
    redis_url: str = "redis://:changeme@localhost:6379"
    revocation_ttl_s: int = 86400  # match max token lifetime

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_max_expire_minutes: int = 1440  # 24h hard cap

    # Vault (production key management)
    vault_url: str = "http://localhost:8200"
    vault_token: str = "root-token-dev-only"

    # OTel
    otel_endpoint: str = "http://otel-collector:4317"

    # Kong — for consumer bootstrapping
    kong_admin_url: str = "http://kong:8001"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
