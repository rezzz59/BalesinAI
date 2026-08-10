"""Tests for app.config."""
import pytest

from app.config import Settings, get_settings


def test_get_settings_returns_singleton(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("ENCRYPTION_KEY", "dGVzdC1rZXktMTIzNDU2Nzg5MGFiY2RlZg==")
    monkeypatch.setenv("FONNTE_API_KEY", "test-fonnte-token")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./secrets/test.json")

    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2  # singleton


def test_settings_loads_required_fields(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("ENCRYPTION_KEY", "dGVzdC1rZXktMTIzNDU2Nzg5MGFiY2RlZg==")
    monkeypatch.setenv("FONNTE_API_KEY", "test-fonnte-token")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./secrets/test.json")
    monkeypatch.setenv("LLM_BACKEND", "gemini")

    get_settings.cache_clear()  # type: ignore[attr-defined]
    settings = Settings()

    assert settings.anthropic_api_key == "test-key"
    assert settings.gemini_api_key == "test-gemini-key"
    assert settings.llm_backend == "gemini"  # default
    assert settings.fonnte_api_key == "test-fonnte-token"
    assert settings.intent_confidence_threshold == 0.6  # default


def test_settings_custom_threshold(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("ENCRYPTION_KEY", "dGVzdC1rZXktMTIzNDU2Nzg5MGFiY2RlZg==")
    monkeypatch.setenv("FONNTE_API_KEY", "test-fonnte-token")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./secrets/test.json")
    monkeypatch.setenv("INTENT_CONFIDENCE_THRESHOLD", "0.75")

    get_settings.cache_clear()  # type: ignore[attr-defined]
    settings = Settings()

    assert settings.intent_confidence_threshold == 0.75


def test_settings_explicit_llm_backend(monkeypatch):
    """Setting LLM_BACKEND env var overrides the default."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("LLM_BACKEND", "anthropic")
    monkeypatch.setenv("ENCRYPTION_KEY", "dGVzdC1rZXktMTIzNDU2Nzg5MGFiY2RlZg==")
    monkeypatch.setenv("FONNTE_API_KEY", "test-fonnte-token")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./secrets/test.json")

    get_settings.cache_clear()  # type: ignore[attr-defined]
    settings = Settings()

    assert settings.llm_backend == "anthropic"