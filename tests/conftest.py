"""Shared fixtures for all tests."""
import pytest
from app.config import get_settings


@pytest.fixture(autouse=True)
def setup_settings(monkeypatch):
    """Set required environment variables for all tests to avoid validation errors."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-for-testing")
    monkeypatch.setenv("ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")  # base64 of 32 zero bytes
    monkeypatch.setenv("FONNTE_API_KEY", "test-fonnte-token")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./secrets/test-sa.json")
    yield
    get_settings.cache_clear()