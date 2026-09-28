from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "KIKI Tech"
    database_url: str = "sqlite:///./kiki.db"
    cors_origins: str = "http://localhost:5173"
    max_upload_mb: int = 15
    ml_client_id: str = ""
    ml_client_secret: str = ""
    ml_redirect_uri: str = ""
    ml_api_url: str = "https://api.mercadolibre.com"
    ml_authorization_url: str = "https://auth.mercadolibre.com.ar/authorization"
    ml_state_ttl_minutes: int = 10
    ml_snapshot_fresh_hours: int = 24

    @field_validator("database_url")
    @classmethod
    def normalize_render_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://") and "+" not in value.split("://", 1)[0]:
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
