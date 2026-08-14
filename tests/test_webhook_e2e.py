"""End-to-end webhook integration tests with real graph + in-memory DB.

Covers the full request path through app.main.whatsapp_webhook:
- FAQ and check_product replies
- Multi-turn order draft carryover
- Order cancellation clears draft
- Complaint/objection routes to fallback_human
"""
import json
import os
import tempfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import create_engine

import app.db.engine as engine_mod
from app.db.models import Base

from app.graph.state import ChatState
from app.services.llm import LLMClient


WEBHOOK_TOKEN = "test-webhook-token"


class ScriptedLLM(LLMClient):
    """Deterministic LLM that maps message keywords to classifications."""

    def __init__(self, script):
        self.script = script

    def _classify(self, text):
        text = (text or "").lower()
        for key, result in self.script.items():
            if key in text:
                return result
        return {"intent": "unclear", "confidence": 0.3, "has_complaint_signal": False, "has_objection_signal": False, "sentiment": "neutral"}

    def classify(self, message):
        return self._classify(message)

    def classify_with_history(self, messages):
        last = messages[-1]["content"] if messages else ""
        return self._classify(last)

    def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
        answer = retrieved_row.get("jawaban") if isinstance(retrieved_row, dict) else None
        return f"Baik Kak, {answer or 'kami bantu'}" if answer else "Terima kasih Kak, kami bantu segera."

    def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
        return self.compose_reply(message, retrieved_row, match_kind, customer_context, persona)


@pytest.fixture(autouse=True)
def reset_db():
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="webhook_e2e_")
    os.close(fd)
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    engine_mod.reset_engine_for_testing(eng)
    yield
    eng.dispose()
    engine_mod.reset_engine_for_testing(None)
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("WEBHOOK_AUTH_TOKEN", WEBHOOK_TOKEN)
    monkeypatch.setenv("ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    from app.config import get_settings
    get_settings.cache_clear()

    from app import main as main_mod
    main_mod._cached_clients.clear()
    return TestClient(main_mod.app)


def _tenant_row(tenant_id: str = "t-web"):
    from app.services.crypto import encrypt_api_key
    from app.config import get_settings
    return {
        "tenant_id": tenant_id,
        "wa_api_key_encrypted": encrypt_api_key("dev-token", get_settings().encryption_key),
        "google_sheet_id": "sheet-1",
        "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
        "business_type": "jualan",
        "onboarding_status": "ready",
        "data_source": "upload",
    }


def _make_sheets_client():
    m = MagicMock()
    m.read_catalog = MagicMock(return_value=[
        {"nama_produk": "Kaos Oversize Crop - Hitam - Size L", "harga": "70000", "ready": "Y"},
        {"nama_produk": "Hoodie Fleece Tebal - Navy - Size M", "harga": "150000", "ready": "Y"},
    ])
    m.read_faq = MagicMock(return_value=[
        {"pertanyaan": "Jam buka", "jawaban": "Jam buka kami 09.00-21.00 WIB."}
    ])
    return m


def _post(client, tenant_id, wa_number, message, monkeypatch, tenant_row=None):
    from app.db.tenant_repo import insert_or_update_tenant
    from app.config import get_settings
    get_settings.cache_clear()
    row = tenant_row or _tenant_row(tenant_id)
    insert_or_update_tenant(**row)

    from app import main as main_mod
    main_mod._cached_clients.clear()

    # Mock tenant clients: scripted LLM + fake sheets + fake gateway
    llm = ScriptedLLM({
        "harga": {"intent": "faq", "confidence": 0.9, "has_complaint_signal": False, "has_objection_signal": False, "sentiment": "neutral"},
        "ada kaos": {"intent": "check_product", "confidence": 0.9, "has_complaint_signal": False, "has_objection_signal": False, "sentiment": "neutral"},
        "order": {"intent": "confirm_order", "confidence": 0.9, "has_complaint_signal": False, "has_objection_signal": False, "sentiment": "neutral"},
        "tambah": {"intent": "confirm_order", "confidence": 0.9, "has_complaint_signal": False, "has_objection_signal": False, "sentiment": "neutral"},
        "batalkan": {"intent": "faq", "confidence": 0.9, "has_complaint_signal": False, "has_objection_signal": False, "sentiment": "neutral"},
        "rusak": {"intent": "unclear", "confidence": 0.3, "has_complaint_signal": True, "has_objection_signal": False, "sentiment": "negative"},
        "mahal": {"intent": "unclear", "confidence": 0.3, "has_complaint_signal": False, "has_objection_signal": True, "sentiment": "negative"},
    })

    async def _send(*args, **kwargs):
        return {"ok": True}

    gateway = MagicMock()
    gateway.send_message = _send
    gateway.send_attachment = _send

    monkeypatch.setattr(main_mod, "_get_tenant_clients", lambda tid, cfg, stg: (llm, _make_sheets_client(), gateway))

    payload = {
        "tenant_id": tenant_id,
        "sender": wa_number.lstrip("+"),
        "message": message,
    }
    return client.post(
        "/webhook/whatsapp/",
        json=payload,
        headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}", "X-Tenant-ID": tenant_id},
    )


class TestWebhookE2E:
    def test_faq_reply(self, client, monkeypatch):
        r = _post(client, "t-faq", "+628123", "harga", monkeypatch)
        assert r.status_code == 200
        data = r.json()["state"]
        assert data["intent"] == "faq"
        assert data["action"] == "reply"

    def test_check_product_reply(self, client, monkeypatch):
        r = _post(client, "t-check", "+628123", "ada kaos hitam?", monkeypatch)
        assert r.status_code == 200
        data = r.json()["state"]
        assert data["intent"] == "check_product"
        assert data["action"] == "reply"

    def test_multi_turn_order_then_cancel(self, client, monkeypatch):
        tenant, wa = "t-order", "+628124"
        # business_type=fashion: size+color required. Message has color but no size,
        # so order is incomplete → draft persists → cancel override can fire.
        row = _tenant_row(tenant)
        row["business_type"] = "fashion"

        r1 = _post(client, tenant, wa, "order kaos hitam 2", monkeypatch, tenant_row=row)
        assert r1.status_code == 200
        s1 = r1.json()["state"]
        assert s1["intent"] == "confirm_order"
        assert s1["action"] == "reply"  # consultation: missing size
        assert s1.get("order_draft")

        r2 = _post(client, tenant, wa, "batalkan pesanan saya", monkeypatch, tenant_row=row)
        assert r2.status_code == 200
        s2 = r2.json()["state"]
        assert s2["intent"] == "cancel_order"
        assert s2["action"] == "reply"

        from app.db.conversation_repo import get_conversation_state
        memory = get_conversation_state(tenant, f"{tenant}:{wa}")
        assert memory.get("order_draft") == []

    def test_complaint_routes_to_fallback(self, client, monkeypatch):
        r = _post(client, "t-complaint", "+628125", "barang saya rusak", monkeypatch)
        assert r.status_code == 200
        data = r.json()["state"]
        assert data["action"] == "fallback"
        assert data["fallback_reason"]

    def test_objection_routes_to_fallback(self, client, monkeypatch):
        r = _post(client, "t-objection", "+628126", "mahal banget", monkeypatch)
        assert r.status_code == 200
        data = r.json()["state"]
        assert data["action"] == "fallback"

    def test_unauthorized_webhook(self, client, monkeypatch):
        from app.db.tenant_repo import insert_or_update_tenant
        insert_or_update_tenant(**_tenant_row("t-auth"))
        r = client.post(
            "/webhook/whatsapp/",
            json={"tenant_id": "t-auth", "sender": "8123", "message": "halo"},
            headers={"Authorization": "Bearer wrong-token", "X-Tenant-ID": "t-auth"},
        )
        assert r.status_code == 401

    def test_tenant_not_found(self, client, monkeypatch):
        r = client.post(
            "/webhook/whatsapp/",
            json={"tenant_id": "t-missing", "sender": "8123", "message": "halo"},
            headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}", "X-Tenant-ID": "t-missing"},
        )
        assert r.status_code == 404

    def test_empty_message_skipped(self, client, monkeypatch):
        from app.db.tenant_repo import insert_or_update_tenant
        insert_or_update_tenant(**_tenant_row("t-empty"))
        r = client.post(
            "/webhook/whatsapp/",
            json={"tenant_id": "t-empty", "sender": "", "message": ""},
            headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}", "X-Tenant-ID": "t-empty"},
        )
        assert r.status_code == 200
        assert r.json()["reason"] == "empty_message"
