"""Tests for classify_intent node."""
from unittest.mock import MagicMock

import pytest

from app.graph.nodes import classify_intent
from app.graph.state import ChatState
from app.services.llm import LLMError


def test_classify_intent_writes_intent_and_confidence():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "Berapa harga kaos?",
    }

    fake_llm = MagicMock()
    fake_llm.classify_with_history = MagicMock(return_value={"intent": "faq", "confidence": 0.85})

    result = classify_intent(state, llm_client=fake_llm)

    assert result["intent"] == "faq"
    assert result["confidence"] == 0.85


def test_classify_intent_low_confidence_returns_unclear():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "zzzqx",
    }

    fake_llm = MagicMock()
    fake_llm.classify_with_history = MagicMock(return_value={"intent": "faq", "confidence": 0.3})

    result = classify_intent(state, llm_client=fake_llm)

    # Original intent kept, but caller (graph router) checks confidence
    assert result["intent"] == "faq"
    assert result["confidence"] == 0.3


def test_classify_intent_llm_error_raises():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
    }

    fake_llm = MagicMock()
    fake_llm.classify_with_history = MagicMock(side_effect=LLMError("timeout"))

    with pytest.raises(LLMError):
        classify_intent(state, llm_client=fake_llm)


def test_classify_intent_overrides_faq_order_with_quantity():
    """A catering order with a trailing price question must route to
    confirm_order even when the LLM misclassifies it as faq."""
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "kak mau pesan paket prasmanan a 100 porsi buat acara tanggal 12 juli, kirim ke jakarta barat, totalnya berapa ya?",
    }

    fake_llm = MagicMock()
    fake_llm.classify_with_history = MagicMock(
        return_value={"intent": "faq", "confidence": 0.7, "has_complaint_signal": False,
                      "has_objection_signal": False, "sentiment": "neutral"}
    )

    result = classify_intent(state, llm_client=fake_llm)
    assert result["intent"] == "confirm_order"
    assert result["confidence"] >= 0.9


def test_classify_intent_keeps_faq_when_no_order_verb():
    """A pure price question without an order verb stays faq."""
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "paket prasmanan a 100 porsi itu harganya berapa ya?",
    }

    fake_llm = MagicMock()
    fake_llm.classify_with_history = MagicMock(
        return_value={"intent": "faq", "confidence": 0.9, "has_complaint_signal": False,
                      "has_objection_signal": False, "sentiment": "neutral"}
    )

    result = classify_intent(state, llm_client=fake_llm)
    assert result["intent"] == "faq"


def test_classify_intent_keeps_faq_when_order_verb_negated():
    """'belum mau pesan' is a price question, not an order — must stay faq."""
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "paket prasmanan a 100 porsi itu harganya berapa ya? belum mau pesan",
    }

    fake_llm = MagicMock()
    fake_llm.classify_with_history = MagicMock(
        return_value={"intent": "faq", "confidence": 0.9, "has_complaint_signal": False,
                      "has_objection_signal": False, "sentiment": "neutral"}
    )

    result = classify_intent(state, llm_client=fake_llm)
    assert result["intent"] == "faq"
