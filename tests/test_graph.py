"""Tests for app.graph.graph — verify routing logic."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.graph.graph import should_fallback, route_after_classify
from app.graph.state import ChatState


def test_should_fallback_low_confidence():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "faq",
        "confidence": 0.3,
    }
    assert should_fallback(state, threshold=0.6) is True


def test_should_fallback_unclear_intent():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "unclear",
        "confidence": 0.95,
    }
    assert should_fallback(state, threshold=0.6) is True


def test_should_not_fallback_high_confidence_faq():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "faq",
        "confidence": 0.9,
    }
    assert should_fallback(state, threshold=0.6) is False


def test_route_after_classify_returns_lookup_for_faq():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "faq",
        "confidence": 0.9,
    }
    assert route_after_classify(state) == "lookup_catalog"


def test_route_after_classify_returns_fallback_for_low_conf():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "faq",
        "confidence": 0.3,
    }
    assert route_after_classify(state) == "fallback_human"


def test_route_after_classify_returns_fallback_for_unclear():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "unclear",
        "confidence": 0.95,
    }
    assert route_after_classify(state) == "fallback_human"