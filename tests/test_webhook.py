"""Integration tests for /webhook/whatsapp/ endpoint."""
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


SECRET = "test-wablas-secret-for-testing"


@pytest.fixture
def client(monkeypatch):
    """Test client with WABLAS_API_KEY set."""
    monkeypatch.setenv("WABLAS_API_KEY", SECRET)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./dummy.json")
    get_settings.cache_clear()
    from app.main import app
    return TestClient(app)


def _sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _build_payload_bytes() -> bytes:
    return json.dumps({
        "tenant_id": "demo",
        "wa_number": "+6281234567890",
        "thread_id": "thread-abc",
        "message_text": "Halo",
    }, separators=(",", ":")).encode("utf-8")


def test_missing_signature_header_returns_401(client):
    """Webhook rejects request without X-Wablas-Signature header (HTTP 401)."""
    body = _build_payload_bytes()
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 401
    assert "Missing X-Wablas-Signature" in response.json()["detail"]


def test_valid_signature_passes_verification(client, monkeypatch):
    """Webhook accepts request with correct signature and returns success.

    Note: This verifies signature verification logic works correctly by
    using a valid signature and mocking the graph to avoid external deps.
    """
    from app import main as app_main

    class MockGraph:
        async def ainvoke(self, state):
            return {**state, "intent": "faq", "reply_text": "Mocked"}

    # Mock the compiled graph
    app_main._compiled_graph = MockGraph()
    app_main._llm_client = object()
    app_main._sheets_client = object()
    app_main._wablas_client = object()

    body = _build_payload_bytes()
    sig = _sign(body)

    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Wablas-Signature": sig,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["state"]["intent"] == "faq"


def test_invalid_signature_returns_401(client):
    """Webhook rejects request with incorrect signature (HTTP 401)."""
    body = _build_payload_bytes()
    sig_wrong = "deadbeef" * 8  # Completely wrong

    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Wablas-Signature": sig_wrong,
        },
    )
    assert response.status_code == 401
    assert "Invalid signature" in response.json()["detail"] or "Signature error" in response.json()["detail"]


def test_wrong_secret_rejects_signature(client):
    """Signature computed with different secret is rejected (HTTP 401)."""
    body = _build_payload_bytes()
    # Compute signature with different secret
    sig_wrong_secret = hmac.new(b"different-secret", body, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Wablas-Signature": sig_wrong_secret,
        },
    )
    assert response.status_code == 401