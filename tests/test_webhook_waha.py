"""Tests for WAHA webhook payload parsing — message event, non-message skip, fromMe skip, group ignore, session→tenant, field aliases."""
import json

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.config import get_settings

WEBHOOK_AUTH_TOKEN = "test-fonnte-token-for-testing"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FONNTE_API_KEY", "test-fonnte-api-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./dummy.json")
    monkeypatch.setenv("WEBHOOK_AUTH_TOKEN", WEBHOOK_AUTH_TOKEN)
    get_settings.cache_clear()
    from app.main import app
    return TestClient(app)


def _waha_event(event="message", fromMe=False, chat_id="6281234567890@c.us", body="Halo kak", session="default"):
    return {
        "event": event,
        "payload": {
            "from": chat_id,
            "body": body,
            "fromMe": fromMe,
            "session": session,
        },
    }


def test_waha_message_event_parses(client, monkeypatch):
    from unittest.mock import MagicMock, patch
    from app.services.llm import MockLLMClient

    mock_tenant = MagicMock()
    mock_tenant.wa_api_key_encrypted = "dummy_enc"
    mock_tenant.google_sheet_id = "test-sheet-id"

    mock_llm = MockLLMClient()
    mock_sheets = MagicMock()
    mock_sheets.faq_lookup_faq.return_value = None
    mock_sheets.catalog_browse.return_value = []
    mock_sheets.policy_load.return_value = []
    mock_sheets.search_replies.return_value = []

    mock_gateway = MagicMock()
    mock_gateway.send_message = MagicMock(return_value={"status": "sent"})

    async def _mock_send(phone=None, message=None):
        return {"status": "sent"}

    mock_gateway.send_message = _mock_send

    monkeypatch.setattr("app.main._get_tenant_clients", lambda *a, **k: (mock_llm, mock_sheets, mock_gateway))
    monkeypatch.setattr("app.main.get_tenant", lambda *a, **k: mock_tenant)

    body = json.dumps(_waha_event()).encode("utf-8")
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {WEBHOOK_AUTH_TOKEN}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_waha_non_message_event_skipped(client, monkeypatch):
    body = json.dumps(_waha_event(event="message_reaction")).encode("utf-8")
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {WEBHOOK_AUTH_TOKEN}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "ignored_event" in data["reason"]


def test_waha_fromMe_skipped(client, monkeypatch):
    body = json.dumps(_waha_event(fromMe=True)).encode("utf-8")
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {WEBHOOK_AUTH_TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json()["reason"] == "outbound_message"


def test_waha_group_message_ignored(client, monkeypatch):
    group_payload = _waha_event(chat_id="6281234567890-1234567890@g.us")
    body = json.dumps(group_payload).encode("utf-8")
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {WEBHOOK_AUTH_TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json()["reason"] == "group_message_ignored"


def test_waha_session_used_as_device(client, monkeypatch):
    from unittest.mock import MagicMock, patch

    captured_tenant_id = []

    def mock_get_tenant(tenant_id, config=None, settings=None):
        captured_tenant_id.append(tenant_id)
        return None

    monkeypatch.setattr("app.main.get_tenant", mock_get_tenant)
    monkeypatch.setattr(
        "app.db.tenant_repo.get_tenant_by_device",
        lambda device: None,
    )

    body = json.dumps(_waha_event(session="my-waha-session")).encode("utf-8")
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {WEBHOOK_AUTH_TOKEN}"},
    )
    assert response.status_code == 404
    assert "my-waha-session" in captured_tenant_id[0] or captured_tenant_id[0] == "my-waha-session"


def test_fonnte_delivery_callback_skipped(client, monkeypatch):
    body = json.dumps({"device": "6281234567890", "state": "delivered"}).encode("utf-8")
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {WEBHOOK_AUTH_TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json()["reason"] == "delivery_callback"


def test_fonnte_field_aliases_sender_and_message(client, monkeypatch):
    from unittest.mock import MagicMock

    mock_tenant = MagicMock()
    mock_tenant.wa_api_key_encrypted = "dummy_enc"
    mock_tenant.google_sheet_id = "test-sheet-id"

    from app.services.llm import MockLLMClient

    mock_llm = MockLLMClient()
    mock_sheets = MagicMock()
    mock_sheets.faq_lookup_faq.return_value = None
    mock_sheets.catalog_browse.return_value = []
    mock_sheets.policy_load.return_value = []
    mock_sheets.search_replies.return_value = []

    mock_gateway = MagicMock()

    async def _mock_send(phone=None, message=None):
        return {"status": "sent"}

    mock_gateway.send_message = _mock_send

    monkeypatch.setattr("app.main._get_tenant_clients", lambda *a, **k: (mock_llm, mock_sheets, mock_gateway))
    monkeypatch.setattr("app.main.get_tenant", lambda *a, **k: mock_tenant)

    payload = json.dumps({
        "sender": "+6281234567890",
        "message": "Berapa harga kaos?",
        "device": "default_device",
    }).encode("utf-8")

    response = client.post(
        "/webhook/whatsapp/",
        content=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {WEBHOOK_AUTH_TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_fonnte_field_aliases_pengirim_and_pesan(client, monkeypatch):
    from unittest.mock import MagicMock

    mock_tenant = MagicMock()
    mock_tenant.wa_api_key_encrypted = "dummy_enc"
    mock_tenant.google_sheet_id = "test-sheet-id"

    from app.services.llm import MockLLMClient

    mock_llm = MockLLMClient()
    mock_sheets = MagicMock()
    mock_sheets.faq_lookup_faq.return_value = None
    mock_sheets.catalog_browse.return_value = []
    mock_sheets.policy_load.return_value = []
    mock_sheets.search_replies.return_value = []

    mock_gateway = MagicMock()

    async def _mock_send(phone=None, message=None):
        return {"status": "sent"}

    mock_gateway.send_message = _mock_send

    monkeypatch.setattr("app.main._get_tenant_clients", lambda *a, **k: (mock_llm, mock_sheets, mock_gateway))
    monkeypatch.setattr("app.main.get_tenant", lambda *a, **k: mock_tenant)

    payload = json.dumps({
        "pengirim": "+6281234567890",
        "pesan": "Halo",
        "device": "default_device",
    }).encode("utf-8")

    response = client.post(
        "/webhook/whatsapp/",
        content=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {WEBHOOK_AUTH_TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_empty_wa_number_or_message_skipped(client, monkeypatch):
    payload = json.dumps({
        "sender": "",
        "message": "",
        "device": "default_device",
    }).encode("utf-8")

    monkeypatch.setattr("app.main.get_tenant", lambda *a, **k: MagicMock())
    monkeypatch.setattr(
        "app.db.tenant_repo.get_tenant_by_device",
        lambda device: None,
    )

    response = client.post(
        "/webhook/whatsapp/",
        content=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {WEBHOOK_AUTH_TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json()["reason"] == "empty_message"