"""Integration tests for /webhook/whatsapp/ endpoint (Fonnte auth only)."""
import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


FONNTE_TOKEN = "test-fonnte-token-for-testing"


@pytest.fixture
def client(monkeypatch):
    """Test client with FONNTE_API_KEY set."""
    monkeypatch.setenv("FONNTE_API_KEY", FONNTE_TOKEN)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./dummy.json")
    get_settings.cache_clear()
    from app.main import app
    return TestClient(app)


def _build_payload_bytes() -> bytes:
    return json.dumps({
        "tenant_id": "demo",
        "wa_number": "+6281234567890",
        "thread_id": "thread-abc",
        "message_text": "Halo",
    }, separators=(",", ":")).encode("utf-8")


def test_missing_authorization_header_returns_401(client):
    """Webhook rejects request without Authorization header (HTTP 401)."""
    body = _build_payload_bytes()
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 401
    assert "Missing Bearer" in response.json()["detail"]


def test_wrong_authorization_scheme_returns_401(client):
    """Webhook rejects request without Bearer prefix (HTTP 401)."""
    body = _build_payload_bytes()
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": FONNTE_TOKEN,  # raw token, no Bearer prefix
        },
    )
    assert response.status_code == 401
    assert "Missing Bearer" in response.json()["detail"]


def test_invalid_token_returns_401(client):
    """Webhook rejects request with wrong Bearer token (HTTP 401)."""
    body = _build_payload_bytes()
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer wrong-token",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Fonnte API key"


def test_valid_token_passes_verification(client, monkeypatch):
    """Webhook accepts request with correct Bearer token and returns success."""
    from app import main as app_main

    class MockGraph:
        async def ainvoke(self, state):
            return {**state, "intent": "faq", "reply_text": "Mocked"}

    app_main._compiled_graph = MockGraph()
    app_main._llm_client = object()
    app_main._sheets_client = object()
    app_main._phone_gateway = object()

    body = _build_payload_bytes()
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {FONNTE_TOKEN}",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["state"]["intent"] == "faq"
