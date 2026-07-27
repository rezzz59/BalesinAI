"""Application configuration via pydantic-settings."""
import base64
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM backend selection: "anthropic" or "gemini"
    llm_backend: str = "gemini"

    # LLM API keys — left empty until configured; validation occurs later when used
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    # Required (must be provided)
    encryption_key: str = base64.b64encode(b"x" * 32).decode()  # 32-byte key
    wablas_base_url: str = "https://api.wablas.example"
    google_sheets_credentials_json_path: str = "./secrets/sheets-sa.json"
    google_sheets_spreadsheet_id: str = ""  # filled from tenant context or env

    # Default Wablas API key for backward compat (in production, fetched from tenant config)
    wablas_api_key: str = ""

    # Optional with defaults
    checkpointer_db_path: str = "./data/checkpoints.db"
    log_level: str = "INFO"
    intent_confidence_threshold: float = 0.6


@lru_cache(maxsize=1)
def get_settings(**overrides) -> Settings:
    """Return application settings. Pass overrides for testing."""
    return Settings(**overrides)  # type: ignore[call-arg]
