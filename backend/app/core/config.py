from functools import lru_cache
from pydantic import field_validator, Field, SecretStr
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
    tiendanube_store_id: str = ""
    tiendanube_access_token: SecretStr = SecretStr("")
    tiendanube_user_agent: str = "KIKI Tech 2.0"
    kiki_tiendanube_read_enabled: bool = False
    kiki_admin_username: str = ""
    kiki_admin_password_hash: str = ""
    app_session_secret: str = ""
    app_encryption_key: str = ""
    session_ttl_hours: int = 12
    frontend_url: str = "http://localhost:5173"
    auth_max_attempts: int = 5
    auth_window_minutes: int = 15
    auth_block_minutes: int = 15
    enable_api_docs: bool = False
    ecomm_app_api_token: str = ""
    kiki_refresh_token: str = ""
    kiki_ai_api_key: str = ""
    kiki_ai_model: str = "gpt-4.1-mini"
    kiki_editorial_batches_enabled: bool = False
    kiki_editorial_executor_enabled: bool = False
    kiki_editorial_preview_size: int = Field(default=100, ge=1, le=100)
    kiki_editorial_lease_seconds: int = Field(default=60, ge=3, le=120)
    kiki_editorial_batch_max_items: int = Field(default=5000, ge=100, le=10000)
    kiki_editorial_step_seconds: int = Field(default=10, ge=1, le=30)
    kiki_editorial_step_size: int = Field(default=5, ge=1, le=20)
    kiki_editorial_max_attempts: int = Field(default=3, ge=1, le=3)
    kiki_editorial_context_bytes: int = Field(default=2_000_000, ge=65536, le=8_000_000)
    kiki_editorial_review_soon_days: int = Field(default=7, ge=1, le=30)
    kiki_channel_workspace_enabled: bool = False
    kiki_document_workspace_enabled: bool = False
    kiki_tiendanube_writes_enabled: bool = False
    kiki_ml_official_validation_enabled: bool = False
    kiki_monthly_review_enabled: bool = False
    kiki_research_search_enabled: bool = False
    kiki_research_search_provider: str = "BRAVE"
    kiki_research_search_api_key: str = Field(default="", repr=False)
    kiki_research_search_max_requests: int = Field(default=20, ge=1, le=20)
    kiki_research_search_daily_requests: int = Field(default=20, ge=1, le=200)
    # Explicit pilot allowlist. No network access until every value is set.
    kiki_document_source_fetch_enabled: bool = False
    # Explicit manual URL pilot, sitemap optional; still requires domain allowlist,
    # isolated reader, robots and independent human evidence approval.
    kiki_document_explicit_url_intake_enabled: bool = False
    kiki_document_source_fetch_hosts: str = ""
    kiki_document_source_fetch_pilot_id: str = ""
    # Independent, explicit opt-in: one read-only manufacturer sitemap per request.
    kiki_document_sitemap_discovery_enabled: bool = False
    # Explicit two-source steps; archives PENDING originals only, never approves facts.
    kiki_document_batch_source_import_enabled: bool = False
    # Manual, resumable source-intake coordination; requires explicit migration.
    kiki_document_resumable_intake_enabled: bool = False
    # Separate guarded activation: source checkbox alone cannot make a pilot
    # fiche READY_FOR_CHANNELS without documentary source and approved facts.
    kiki_document_channel_guard_enabled: bool = False
    kiki_document_channel_guard_pilot_id: str = ""
    kiki_ai_enabled: bool = False
    # Paid IA pilot: source-grounded text only, explicit opt-in.
    kiki_document_ai_generation_enabled: bool = False
    kiki_document_ai_pilot_id: str = "7518949"
    # Default-off UI controls; existing provider/worker flags remain required.
    kiki_auto_create_schema: bool = True
    kiki_document_parser_kernel_required: bool = False
    kiki_document_parser_socket: str = "/document-parser/parser.sock"
    kiki_v2_enabled: bool = False
    kiki_v2_writes_enabled: bool = False
    kiki_v2_connections_enabled: bool = False
    kiki_v2_ai_generation_enabled: bool = False

    @field_validator("database_url")
    @classmethod
    def normalize_render_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://") and "+" not in value.split("://", 1)[0]:
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("cors_origins")
    @classmethod
    def require_explicit_cors_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if not origins or "*" in origins:
            raise ValueError("CORS_ORIGINS debe contener orígenes explícitos")
        return ",".join(origins)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
