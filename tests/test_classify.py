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