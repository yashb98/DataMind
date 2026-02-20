from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    embedding_model: str = "BAAI/bge-m3"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = ""
    otel_endpoint: str = "http://otel-collector:4317"
    port: int = 8030


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
