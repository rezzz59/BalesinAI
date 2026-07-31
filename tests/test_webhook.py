"""Integration tests for /webhook/whatsapp/ endpoint (Fonnte auth only)."""
import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


WEBHOOK_AUTH_TOKEN = "test-fonnte-token-for-testing"
FONNTE_API_KEY = "test-fonnte-api-key"


@pytest.fixture
def client(monkeypatch):
    """Test client with webhook_auth_token set so Bearer auth passes."""
    monkeypatch.setenv("FONNTE_API_KEY", FONNTE_API_KEY)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./dummy.json")
    monkeypatch.setenv("WEBHOOK_AUTH_TOKEN", WEBHOOK_AUTH_TOKEN)  # Key untuk auth webhook
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
    assert "Missing" in response.json()["detail"] or "Invalid" in response.json()["detail"]


def test_wrong_authorization_scheme_returns_401(client):
    """Webhook rejects request without Bearer prefix (HTTP 401)."""
    body = _build_payload_bytes()
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": WEBHOOK_AUTH_TOKEN,  # raw token, no Bearer prefix
        },
    )
    assert response.status_code == 401
    assert "Missing" in response.json()["detail"] or "Invalid" in response.json()["detail"]


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
    assert response.json()["detail"] in ["Invalid or missing webhook token", "Invalid webhook token"]


def test_valid_token_passes_verification(client, monkeypatch):
    """Webhook accepts request with correct Bearer token and returns success."""
    from unittest.mock import MagicMock, patch
    from app.main import _get_tenant_clients, get_tenant

    # Mock tenant config that has required fields
    mock_tenant = MagicMock()
    mock_tenant.wa_api_key_encrypted = "dummy_enc"
    mock_tenant.google_sheet_id = "test-sheet-id"

    # Create mock responses for all needed services - use MockLLMClient for compatibility
    from app.services.llm import MockLLMClient
    mock_llm = MockLLMClient()
    # Override classify_with_history to return specific value for testing
    original_classify = mock_llm.classify
    def mock_classify_with_history(messages):
        # Check if the message contains 'Halo' and return faq
        for m in messages:
            if m.get("role") == "user" and "Halo" in str(m.get("content", "")):
                return {"intent": "faq", "confidence": 0.9, "has_complaint_signal": False, "sentiment": "neutral"}
        return {"intent": "faq", "confidence": 0.9, "has_complaint_signal": False, "sentiment": "neutral"}
    mock_llm.classify_with_history = mock_classify_with_history

    mock_sheets = MagicMock()
    mock_sheets.faq_cache_get.return_value = None
    mock_sheets.faq_lookup_faq.return_value = None
    mock_sheets.catalog_browse.return_value = []
    mock_sheets.policy_load.return_value = []
    mock_sheets.search_replies.return_value = []

    mock_gateway = MagicMock()

    async def mock_send_message(phone=None, message=None):
        # Return a fake response that looks like successful send
        return {"status": "sent", "message_id": "test-123"}

    mock_gateway.send_message = mock_send_message

    def mock_get_clients(tenant_id, config, settings):
        return mock_llm, mock_sheets, mock_gateway

    def mock_get_tenant(tenant_id, config=None, settings=None):
        return mock_tenant

    monkeypatch.setattr("app.main._get_tenant_clients", mock_get_clients)
    monkeypatch.setattr("app.main.get_tenant", mock_get_tenant)

    body = _build_payload_bytes()
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {WEBHOOK_AUTH_TOKEN}",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    # Intent comes from the classified result
    assert data["state"].get("intent") == "faq"
