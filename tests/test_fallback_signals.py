"""Tests for fallback human branches (complaint, objection, default) and order cancel."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.graph.nodes import fallback_human
from app.graph.state import ChatState


@pytest.fixture
def fake_gateway():
    gateway = MagicMock()
    gateway.send_message = AsyncMock(return_value={"status": "ok"})
    return gateway


@pytest.fixture
def fake_tenant_repo(monkeypatch):
    def _get_tenant(tid):
        return {
            "tenant_id": "demo",
            "wa_api_key_encrypted": b"dummy",
            "owner_wa_number": "+62811",
            "fonnte_device_id": "+62899", # Different from owner
        }
    monkeypatch.setattr("app.db.tenant_repo.get_tenant", _get_tenant)


@pytest.mark.asyncio
async def test_fallback_human_complaint_signal(fake_gateway, fake_tenant_repo):
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+62822",
        "thread_id": "t-1",
        "message_text": "barang cacat",
        "has_complaint_signal": True,
        "has_objection_signal": False,
        "fallback_reason": "complaint_signal",
    }
    res = await fallback_human(state, fake_gateway)
    assert res["action"] == "fallback"
    
    # 2 messages: to owner, to buyer
    assert fake_gateway.send_message.call_count == 2
    
    buyer_msg = fake_gateway.send_message.call_args_list[1][1]["message"]
    assert "Mohon maaf ya Kak atas ketidaknyamanannya" in buyer_msg
    assert "solusi seperti apa" in buyer_msg
    
    owner_msg = fake_gateway.send_message.call_args_list[0][1]["message"]
    assert "pelanggan tampak tidak senang/kecewa" in owner_msg


@pytest.mark.asyncio
async def test_fallback_human_objection_signal(fake_gateway, fake_tenant_repo):
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+62822",
        "thread_id": "t-1",
        "message_text": "mahal banget diskon dong",
        "has_complaint_signal": False,
        "has_objection_signal": True,
        "fallback_reason": "objection_signal",
    }
    res = await fallback_human(state, fake_gateway)
    assert res["action"] == "fallback"
    
    buyer_msg = fake_gateway.send_message.call_args_list[1][1]["message"]
    assert "bantu pertimbangkan dulu ya" in buyer_msg
    assert "budget Kakak di angka berapa" in buyer_msg
    
    owner_msg = fake_gateway.send_message.call_args_list[0][1]["message"]
    assert "ragu pada harga/biaya" in owner_msg


@pytest.mark.asyncio
async def test_fallback_human_default_ack(fake_gateway, fake_tenant_repo):
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+62822",
        "thread_id": "t-1",
        "message_text": "resep ayam rica",
        "has_complaint_signal": False,
        "has_objection_signal": False,
        "fallback_reason": "unclear",
    }
    res = await fallback_human(state, fake_gateway)
    assert res["action"] == "fallback"
    
    buyer_msg = fake_gateway.send_message.call_args_list[1][1]["message"]
    assert "Mohon tunggu sebentar" in buyer_msg
    assert "Sambil menunggu" in buyer_msg
