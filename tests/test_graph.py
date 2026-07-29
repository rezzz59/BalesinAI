"""Tests for app.graph.graph — verify routing logic."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.graph.graph import should_fallback, route_after_classify
from app.graph.nodes import compose_reply
from app.graph.state import ChatState
from app.services.llm import LLMClient, LLMError, LLMValidationError, MockLLMClient


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


# ---------------------------------------------------------------------------
# compose_with_llm orchestrator — Task 6
# ---------------------------------------------------------------------------


def _base_high_state() -> ChatState:
    return {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "berapa harga hoodie?",
        "intent": "faq",
        "confidence": 0.9,
        "match_kind": "high",
        "catalog_answer": "Rp 150.000 untuk Hoodie",
        "product_match": None,
    }


def test_compose_reply_uses_llm_for_high_confidence():
    """High-confidence path: LLM.compose_reply is called and its reply is returned."""
    state = _base_high_state()
    update = compose_reply(state, llm_client=MockLLMClient())
    assert update["action"] == "reply"
    assert isinstance(update["reply_text"], str) and update["reply_text"]


def test_compose_reply_uses_no_match_prompt_when_match_kind_none():
    """match_kind == 'none' should still call LLM with retrieved_row=None."""
    state = _base_high_state()
    state["match_kind"] = "none"
    state["catalog_answer"] = None
    state["product_match"] = None

    class CaptureLLM(LLMClient):
        def __init__(self):
            self.captured_kind = None
            self.captured_row = None

        def classify(self, message):
            return {"intent": "faq", "confidence": 0.5}

        def compose_reply(self, message, retrieved_row, match_kind):
            self.captured_kind = match_kind
            self.captured_row = retrieved_row
            return "Mohon maaf, produk belum tersedia."

    llm = CaptureLLM()
    update = compose_reply(state, llm_client=llm)
    assert llm.captured_kind == "none"
    assert llm.captured_row is None
    assert update["action"] == "reply"


def test_compose_reply_falls_back_to_verbatim_when_llm_raises():
    """When LLM raises LLMError, the orchestrator falls back to verbatim catalog_answer."""

    class FailingLLM(LLMClient):
        def classify(self, message):
            return {"intent": "faq", "confidence": 0.5}

        def compose_reply(self, message, retrieved_row, match_kind):
            raise LLMError("API down")

    state = _base_high_state()
    update = compose_reply(state, llm_client=FailingLLM())
    # Verbatim fallback returns catalog_answer as-is.
    assert update["action"] == "reply"
    assert update["reply_text"] == "Rp 150.000 untuk Hoodie"


def test_compose_reply_retries_on_validation_failure_then_falls_back():
    """Validation failure retries once, then falls back to verbatim."""

    class HallucinatingLLM(LLMClient):
        def __init__(self):
            self.calls = 0

        def classify(self, message):
            return {"intent": "faq", "confidence": 0.5}

        def compose_reply(self, message, retrieved_row, match_kind):
            self.calls += 1
            # Always invent a foreign number (999000) — fails validation
            return f"Hoodie Rp 999.000 ready ya Kak (call {self.calls})"

    state = _base_high_state()
    llm = HallucinatingLLM()
    update = compose_reply(state, llm_client=llm)
    # Initial + 1 retry = 2 calls total. After 2 failures, fall back to verbatim.
    assert llm.calls == 2
    assert update["action"] == "reply"
    assert update["reply_text"] == "Rp 150.000 untuk Hoodie"


def test_compose_reply_accepts_valid_reply_after_first_failure():
    """Validation succeeds on retry — return the good reply (no fallback)."""

    class FirstBadThenGoodLLM(LLMClient):
        def __init__(self):
            self.calls = 0

        def classify(self, message):
            return {"intent": "faq", "confidence": 0.5}

        def compose_reply(self, message, retrieved_row, match_kind):
            self.calls += 1
            if self.calls == 1:
                # Foreign price "999.000" — fails validation
                return "Hoodie Rp 999.000 ready ya Kak"
            # Valid: uses source numbers only
            return "Hoodie Rp 150.000 ready ya Kak"

    state = _base_high_state()
    llm = FirstBadThenGoodLLM()
    update = compose_reply(state, llm_client=llm)
    assert llm.calls == 2
    assert update["action"] == "reply"
    assert "150.000" in update["reply_text"]
    assert "999" not in update["reply_text"]


def test_compose_reply_skips_llm_for_confirm_order():
    """Order confirmation is template-only — never calls LLM."""
    state = _base_high_state()
    state["intent"] = "confirm_order"

    class SpyLLM(LLMClient):
        def __init__(self):
            self.called = False

        def classify(self, message):
            return {"intent": "confirm_order", "confidence": 0.9}

        def compose_reply(self, message, retrieved_row, match_kind):
            self.called = True
            return "should not be used"

    llm = SpyLLM()
    update = compose_reply(state, llm_client=llm)
    assert llm.called is False
    assert update["action"] == "order"
    assert "Owner akan follow up" in update["reply_text"]


def test_compose_reply_fallback_when_no_data_anywhere():
    """No catalog_answer + no product_match + match_kind none → LLM still called.

    Even with no row, the LLM is invoked with match_kind="none" so it can
    produce the polite "kami cek dulu" reply. The fallback (human-handoff)
    message is only returned when LLMError is raised.
    """

    class SpyLLM(LLMClient):
        def __init__(self):
            self.called = False
            self.captured_row = "unset"

        def classify(self, message):
            return {"intent": "faq", "confidence": 0.4}

        def compose_reply(self, message, retrieved_row, match_kind):
            self.called = True
            self.captured_row = retrieved_row
            return "Halo Kak! Kami cek dulu ya 🙏"

    state = _base_high_state()
    state["match_kind"] = "none"
    state["catalog_answer"] = None
    state["product_match"] = None
    llm = SpyLLM()
    update = compose_reply(state, llm_client=llm)
    assert llm.called is True
    assert llm.captured_row is None
    assert update["action"] == "reply"
    assert "kami" in update["reply_text"].lower()


def test_compose_reply_falls_back_when_llm_raises_on_no_match():
    """No row + LLM raises → human-handoff message (verbatim_fallback path)."""

    class FailingLLM(LLMClient):
        def classify(self, message):
            return {"intent": "faq", "confidence": 0.4}

        def compose_reply(self, message, retrieved_row, match_kind):
            raise LLMError("API down")

    state = _base_high_state()
    state["match_kind"] = "none"
    state["catalog_answer"] = None
    state["product_match"] = None
    update = compose_reply(state, llm_client=FailingLLM())
    assert update["action"] == "fallback"
    assert "owner akan follow up" in update["reply_text"].lower()