from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "PSB"
    environment: str = "development"
    log_level: str = "INFO"

    seaweedfs_url: str = "http://localhost:8333"
    seaweedfs_directory: str = "documents"
    seaweedfs_timeout_seconds: float = 20.0

    ai_service_url: str | None = None
    ai_service_api_key: str | None = None
    ai_timeout_seconds: float = 90.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
