"""Tests for fallback_human and compose_reply fallback paths."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.graph.nodes import fallback_human, compose_reply
from app.graph.state import ChatState
from app.services.fonnte import FonnteError


def test_compose_reply_faq_with_answer():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "harga?",
        "intent": "faq",
        "catalog_answer": "Mulai Rp 50.000",
    }
    result = compose_reply(state)
    assert result["action"] == "reply"
    assert "Rp 50.000" in result["reply_text"]


def test_compose_reply_faq_no_match_triggers_fallback():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "xyzzy",
        "intent": "faq",
    }
    result = compose_reply(state)
    assert result["action"] == "fallback"
    assert result["fallback_reason"] == "no_faq_match"


def test_compose_reply_confirm_order():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "Saya order 1",
        "intent": "confirm_order",
    }
    result = compose_reply(state)
    assert result["action"] == "order"
    assert "Owner akan follow up" in result["reply_text"]


@pytest.mark.asyncio
async def test_fallback_human_sends_to_owner_and_buyer():
    fake_gateway = MagicMock()
    fake_gateway.send_message = AsyncMock(return_value={"status": "ok"})

    fake_tenant_repo = MagicMock()
    fake_tenant_repo.get_tenant = MagicMock(
        return_value={
            "tenant_id": "demo",
            "wa_api_key_encrypted": b"\x00" * 32,
            "google_sheet_id": "sheet-abc",
            "payment_provider": "xendit",
            "owner_wa_number": "+628111111",
        }
    )

    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "halo",
        "fallback_reason": "unclear",
    }

    with patch("app.db.tenant_repo.get_tenant", fake_tenant_repo.get_tenant):
        result = await fallback_human(state, gateway_client=fake_gateway)

    assert result == {}
    # Two calls: owner + buyer
    assert fake_gateway.send_message.call_count == 2
    owner_call = fake_gateway.send_message.call_args_list[0]
    assert owner_call[1]["phone"] == "+628111111"
    buyer_call = fake_gateway.send_message.call_args_list[1]
    assert buyer_call[1]["phone"] == "+628999"


@pytest.mark.asyncio
async def test_fallback_human_fonnte_error():
    fake_gateway = MagicMock()
    fake_gateway.send_message = AsyncMock(side_effect=FonnteError("fonnte down"))

    fake_tenant = {
        "tenant_id": "demo",
        "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc",
        "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }

    with patch("app.db.tenant_repo.get_tenant", return_value=fake_tenant):
        state: ChatState = {
            "tenant_id": "demo",
            "wa_number": "+628999",
            "thread_id": "demo:+628999",
            "message_text": "halo",
            "fallback_reason": "unclear",
        }
        result = await fallback_human(state, gateway_client=fake_gateway)
        assert result["action"] == "error"