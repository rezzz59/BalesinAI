"""Tests for welcome message injection."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.graph.nodes import _persona_for_tenant, send_whatsapp
from app.graph.state import ChatState


def test_persona_injects_welcome_message():
    tenant = {
        "business_type": "jualan",
        "onboarding_data": '{"welcome_message": "Halo dari Toko Kita! Ada yang bisa dibantu?"}',
    }
    with patch("app.db.tenant_repo.get_tenant", return_value=tenant):
        persona = _persona_for_tenant("t-1")
    assert "Halo dari Toko Kita! Ada yang bisa dibantu?" in persona
    assert "ATURAN WELCOME MESSAGE" in persona


def test_persona_no_welcome_message():
    tenant = {
        "business_type": "jualan",
        "onboarding_data": '{}',
    }
    with patch("app.db.tenant_repo.get_tenant", return_value=tenant):
        persona = _persona_for_tenant("t-1")
    assert "ATURAN WELCOME MESSAGE" not in persona


@pytest.mark.asyncio
async def test_send_whatsapp_prepends_intro_on_empty_history():
    gateway = MagicMock()
    gateway.send_message = AsyncMock()

    state: ChatState = {
        "tenant_id": "t-1",
        "thread_id": "t-1",
        "wa_number": "6281",
        "reply_text": "Sepatu ini ready.",
        "messages": [],  # Empty history!
    }

    await send_whatsapp(state, gateway)

    sent = gateway.send_message.call_args[1]["message"]
    assert "Halo kak" in sent
    assert "Sepatu ini ready." in sent


@pytest.mark.asyncio
async def test_send_whatsapp_skips_intro_when_history_exists():
    gateway = MagicMock()
    gateway.send_message = AsyncMock()

    state: ChatState = {
        "tenant_id": "t-1",
        "thread_id": "t-1",
        "wa_number": "6281",
        "reply_text": "Sepatu ini ready.",
        "messages": [{"role": "user", "content": "hi"}],  # History exists
    }

    await send_whatsapp(state, gateway)

    sent = gateway.send_message.call_args[1]["message"]
    assert "Halo kak" not in sent
    assert sent == "Sepatu ini ready."
