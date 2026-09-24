from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    app_name: str = "KIKI Tech"
    database_url: str = "sqlite:///./kiki.db"
    cors_origins: str = "http://localhost:5173"
    max_upload_mb: int = 15
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
def get_settings() -> Settings: return Settings()
