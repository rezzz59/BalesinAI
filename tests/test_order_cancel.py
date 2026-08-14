"""Tests for order cancellation: buyer cancels a running draft."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.graph.nodes import compose_reply, classify_intent, _looks_like_cancel
from app.graph.state import ChatState
from app.services.llm import MockLLMClient


def test_looks_like_cancel_detects_keywords():
    assert _looks_like_cancel("batalkan pesanan saya") is True
    assert _looks_like_cancel("batal dulu deh") is True
    assert _looks_like_cancel("cancel order") is True
    assert _looks_like_cancel("gak jadi pesan") is True
    assert _looks_like_cancel("Saya mau beli kaos") is False
    assert _looks_like_cancel("") is False


def test_classify_intent_cancel_override_when_draft_exists():
    state: ChatState = {
        "tenant_id": "t-1",
        "wa_number": "6281",
        "thread_id": "t-1",
        "message_text": "batalkan pesanan saya",
        "order_draft": [{"product": "Kaos", "qty": 2, "price": 50000}],
    }
    # MockLLM would classify "batalkan..." → complaint signal but let's ensure
    # the cancel override fires regardless of LLM result.
    result = classify_intent(state, llm_client=MockLLMClient())
    assert result["intent"] == "cancel_order"
    assert result["confidence"] == 0.99


def test_classify_intent_no_cancel_without_draft():
    state: ChatState = {
        "tenant_id": "t-1",
        "wa_number": "6281",
        "thread_id": "t-1",
        "message_text": "batalkan pesanan saya",
        # No order_draft
    }
    result = classify_intent(state, llm_client=MockLLMClient())
    # Without a draft, "batalkan" → complaint signal → not cancel_order
    assert result["intent"] != "cancel_order"


def test_compose_reply_cancel_clears_draft():
    state: ChatState = {
        "tenant_id": "t-1",
        "wa_number": "6281",
        "thread_id": "t-1",
        "message_text": "batalkan pesanan saya",
        "intent": "cancel_order",
        "order_draft": [{"product": "Kaos", "qty": 2, "price": 50000}],
    }
    result = compose_reply(state, llm_client=MockLLMClient())
    assert result["action"] == "reply"
    assert result["order_draft"] == []
    assert "kami batalkan" in result["reply_text"]
