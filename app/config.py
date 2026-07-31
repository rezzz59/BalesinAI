"""Application configuration via pydantic-settings."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM backend selection: "anthropic", "gemini", or "adacode"
    llm_backend: str = "gemini"

    # LLM API keys — left empty until configured; validation occurs later when used
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    adacode_api_key: str = ""

    # Optional base URL for AdaCode (default: https://api.adacode.ai)
    adacode_base_url: str | None = None
    # Optional model override (default: claude-sonnet-4-6)
    adacode_model: str | None = None

    # Required (must be provided via environment)
    encryption_key: str = ""
    fonnte_api_key: str = ""  # API key for Fonnte WhatsApp Gateway
    google_sheets_credentials_json_path: str = "./secrets/sheets-sa.json"
    google_sheets_spreadsheet_id: str = ""  # filled from tenant context or env
    webhook_auth_token: str = ""  # Secret for webhook endpoint authentication (Bearer token)

    # Optional with defaults
    checkpointer_db_path: str = "./data/checkpoints.db"
    log_level: str = "INFO"
    intent_confidence_threshold: float = 0.6


@lru_cache(maxsize=1)
def get_settings(**overrides) -> Settings:
    """Return application settings. Pass overrides for testing."""
    return Settings(**overrides)  # type: ignore[call-arg]
