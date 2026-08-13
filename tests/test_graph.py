"""Tests for app.graph.graph — verify routing logic."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.graph.graph import build_graph, should_fallback, route_after_classify, route_after_lookup
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
        "messages": [{"role": "user", "content": "hi"}], # Ensure it's not the first message
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
        "messages": [{"role": "user", "content": "hi"}], # Ensure it's not the first message
    }
    assert route_after_classify(state) == "fallback_human"


def test_route_after_lookup_skips_fallback_when_browse_reply_prebuilt():
    """Catalog-browse path: lookup_catalog pre-built reply_text. Router must
    route through analyze_customer_context (then to compose_reply, which short-
    circuits to the prebuilt reply), not to compose_reply_fallback. Regression:
    prior bug routed this to fallback."""
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "ada produk apa aja kak?",
        "intent": "check_product",
        "reply_text": "Ini lineup yang ready ya kak 😊",
        "product_match": None,
    }
    # Phase 2: all non-fallback paths pass through analyze_customer_context
    # for the context-aware reply engine. compose_reply then short-circuits
    # the prebuilt reply without an LLM round-trip.
    assert route_after_lookup(state) == "analyze_customer_context"


def test_route_after_lookup_routes_to_fallback_for_check_product_without_match_and_no_reply():
    """No keyword match + no prebuilt reply → fallback (no data)."""
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "apa produk baru?",
        "intent": "check_product",
        "product_match": None,
    }
    assert route_after_lookup(state) == "compose_reply_fallback"


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
            return {"intent": "faq", "confidence": 0.5, "has_complaint_signal": False, "sentiment": "neutral"}

        def classify_with_history(self, messages):
            return {"intent": "faq", "confidence": 0.5, "has_complaint_signal": False, "sentiment": "neutral"}

        def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
            self.captured_kind = match_kind
            self.captured_row = retrieved_row
            return "Mohon maaf, produk belum tersedia. Boleh kami bantu cari yang lain, Kak?"

        def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
            self.captured_kind = match_kind
            self.captured_row = retrieved_row
            return "Mohon maaf, produk belum tersedia. Boleh kami bantu cari yang lain, Kak?"

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

        def classify_with_history(self, messages):
            return {"intent": "faq", "confidence": 0.5, "has_complaint_signal": False, "sentiment": "neutral"}
        def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
            raise LLMError("down")
        def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
            raise LLMError("API down")

    state = _base_high_state()
    update = compose_reply(state, llm_client=FailingLLM())
    # Fallback returns a human-handoff reply that includes the catalog answer.
    assert update["action"] == "reply"
    assert "Rp 150.000 untuk Hoodie" in update["reply_text"]


def test_compose_reply_retries_on_validation_failure_then_falls_back():
    """Validation failure retries once, then falls back to verbatim."""

    class HallucinatingLLM(LLMClient):
        def __init__(self):
            self.calls = 0

        def classify(self, message):
            return {"intent": "faq", "confidence": 0.5, "has_complaint_signal": False, "sentiment": "neutral"}

        def classify_with_history(self, messages):
            return {"intent": "faq", "confidence": 0.5, "has_complaint_signal": False, "sentiment": "neutral"}

        def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
            self.calls += 1
            return f"Hoodie Rp 999.000 ready ya Kak (call {self.calls})"

        def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
            self.calls += 1
            return f"Hoodie Rp 999.000 ready ya Kak (call {self.calls})"

    state = _base_high_state()
    llm = HallucinatingLLM()
    update = compose_reply(state, llm_client=llm)
    # Initial + 1 retry = 2 calls total. After 2 failures, fall back to human-handoff.
    assert llm.calls == 2
    assert update["action"] == "reply"
    assert "Rp 150.000 untuk Hoodie" in update["reply_text"]


def test_compose_reply_accepts_valid_reply_after_first_failure():
    """Validation succeeds on retry — return the good reply (no fallback)."""

    class FirstBadThenGoodLLM(LLMClient):
        def __init__(self):
            self.calls = 0

        def classify(self, message):
            return {"intent": "faq", "confidence": 0.5, "has_complaint_signal": False, "sentiment": "neutral"}

        def classify_with_history(self, messages):
            return {"intent": "faq", "confidence": 0.5, "has_complaint_signal": False, "sentiment": "neutral"}

        def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
            self.calls += 1
            if self.calls == 1:
                # Foreign price "999.000" — fails validation
                return "Hoodie Rp 999.000 ready ya Kak"
            # Valid: uses source numbers only
            return "Hoodie Rp 150.000 ready ya Kak"

        def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
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

        def classify_with_history(self, messages):
            return {"intent": "faq", "confidence": 0.5, "has_complaint_signal": False, "sentiment": "neutral"}
        def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
            return "Mohon maaf, produk belum tersedia. Boleh kami bantu cari yang lain, Kak?"
        def classify(self, message):
            return {"intent": "confirm_order", "confidence": 0.9}

        def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
            self.called = True
            return "should not be used"

    llm = SpyLLM()
    update = compose_reply(state, llm_client=llm)
    assert llm.called is False
    assert update["action"] == "order"
    assert "metode bayar" in update["reply_text"]


def test_compose_reply_skips_llm_for_browse_mode():
    """If lookup_catalog pre-built a reply (catalog-browse), compose_reply
    returns it verbatim — never calls LLM (no hallucination on multi-row)."""
    state = _base_high_state()
    state["intent"] = "check_product"
    state["match_kind"] = "none"
    prebuilt = "Ini lineup yang ready ya kak 😊\n\n1. Hoodie - Rp 150.000\n2. Kaos - Rp 50.000\n\nMau yang mana kak? 😊"
    state["reply_text"] = prebuilt
    state["action"] = "reply"

    class SpyLLM(LLMClient):
        def __init__(self):
            self.called = False

        def classify_with_history(self, messages):
            return {"intent": "faq", "confidence": 0.5, "has_complaint_signal": False, "sentiment": "neutral"}
        def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
            return "Mohon maaf, produk belum tersedia. Boleh kami bantu cari yang lain, Kak?"
        def classify(self, message):
            return {"intent": "check_product", "confidence": 0.9}

        def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
            self.called = True
            return "should not be used"

    llm = SpyLLM()
    update = compose_reply(state, llm_client=llm)
    assert llm.called is False
    assert update["reply_text"] == prebuilt
    assert update["action"] == "reply"


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

        def classify_with_history(self, messages):
            return {"intent": "faq", "confidence": 0.5, "has_complaint_signal": False, "sentiment": "neutral"}
        def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
            return "Mohon maaf, produk belum tersedia. Boleh kami bantu cari yang lain, Kak?"
        def classify(self, message):
            return {"intent": "faq", "confidence": 0.4}

        def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
            self.called = True
            self.captured_row = retrieved_row
            return "Halo Kak! Kami cek dulu ya 🙏 Boleh dibantu cari yang lain, Kak?"

        def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
            self.called = True
            self.captured_row = retrieved_row
            return "Halo Kak! Kami cek dulu ya 🙏 Boleh dibantu cari yang lain, Kak?"

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

        def classify_with_history(self, messages):
            return {"intent": "faq", "confidence": 0.5, "has_complaint_signal": False, "sentiment": "neutral"}
        def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
            raise LLMError("down")
        def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
            raise LLMError("API down")

    state = _base_high_state()
    state["match_kind"] = "none"
    state["catalog_answer"] = None
    state["product_match"] = None
    update = compose_reply(state, llm_client=FailingLLM())
    assert update["action"] == "fallback"
    assert "kami cek dulu ke tim" in update["reply_text"].lower()


# ---------------------------------------------------------------------------
# Task 7: Wire llm_client through graph build
# ---------------------------------------------------------------------------


def test_build_graph_accepts_llm_client_kwarg():
    """build_graph should accept llm_client as a keyword argument."""
    class FakeSheets:
        def lookup_faq(self, msg):
            return None

        def read_catalog(self):
            return []

    class FakeGateway:
        async def send_message(self, *args, **kwargs):
            return {"ok": True}

    llm = MockLLMClient()
    # This should not raise. If build_graph doesn't accept llm_client kwarg,
    # this will TypeError.
    graph = build_graph(llm_client=llm, sheets_client=FakeSheets(), gateway_client=FakeGateway())
    assert graph is not None


def test_built_graph_runs_end_to_end_with_llm_client():
    """Built graph must invoke compose_reply with the bound llm_client at runtime.

    This is the wiring-level proof that Task 7's responsibility is fulfilled:
    without the fix, _compose_sync(state) would call compose_reply(state) and
    TypeError on the missing llm_client kwarg.
    """
    class FakeSheets:
        def lookup_faq(self, msg):
            return {"pertanyaan": "harga hoodie", "jawaban": "Rp 150.000"}

        def read_catalog(self):
            return []

    class FakeGateway:
        def __init__(self):
            self.sent = []

        async def send_message(self, *args, **kwargs):
            self.sent.append((args, kwargs))
            return {"ok": True}

    class CapturingLLM(LLMClient):
        """Calls MockLLMClient.compose_reply; tracks call count."""

        def classify_with_history(self, messages):
            return {"intent": "faq", "confidence": 0.7, "has_complaint_signal": False, "sentiment": "neutral"}
        def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
            return "Mohon maaf, produk belum tersedia. Boleh kami bantu cari yang lain, Kak?"
        def __init__(self):
            self._mock = MockLLMClient()
            self.compose_calls = 0

        def classify(self, message):
            return {"intent": "faq", "confidence": 0.9}

        def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
            self.compose_calls += 1
            return self._mock.compose_reply(message, retrieved_row, match_kind)

        def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
            self.compose_calls += 1
            return self._mock.compose_reply(message, retrieved_row, match_kind)

    llm = CapturingLLM()
    gateway = FakeGateway()
    graph = build_graph(llm_client=llm, sheets_client=FakeSheets(), gateway_client=gateway)

    state = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "berapa harga hoodie?",
    }
    result = graph.invoke(state)

    # If wiring is broken, this would TypeError on missing llm_client.
    assert llm.compose_calls >= 1, "compose_reply was not called via graph wiring"
    assert isinstance(result.get("reply_text"), str)
    assert result.get("action") in ("reply", "fallback", "order")


def test_built_graph_handles_no_faq_match_via_sync_invoke():
    """Sync invoke must work on the no-match path (compose_reply_fallback -> fallback_human).

    Regression: _compose_fallback_node was `async def`, which broke graph.invoke()
    on the no-match path because every other node is sync.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    class FakeSheets:
        def lookup_faq(self, msg):
            return None  # no match

        def read_catalog(self):
            return []

    class FakeGateway:
        def __init__(self):
            self.sent = []

        async def send_message(self, *args, **kwargs):
            self.sent.append((args, kwargs))
            return {"ok": True}

    fake_tenant = {
        "tenant_id": "demo",
        "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc",
        "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }
    fake_repo = MagicMock(return_value=fake_tenant)

    llm = MockLLMClient()
    gateway = FakeGateway()
    graph = build_graph(llm_client=llm, sheets_client=FakeSheets(), gateway_client=gateway)

    state = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "apa ini laundry?",  # "apa" → faq; FakeSheets returns None → no match
        "messages": [{"role": "user", "content": "hello"}], # Add history so unclear falls back
        "intent": "check_product" # Force check_product to trigger fallback since we changed faq to not fallback
    }

    with patch("app.db.tenant_repo.get_tenant", fake_repo):
        result = graph.invoke(state)

    # Now that we let LLM handle empty FAQ matches via knowledge_text, it should reply
    assert result.get("action") in ("fallback", "reply"), result
    # Owner should receive a fallback alert and buyer a polite ack.
    assert len(gateway.sent) == 2