"""End-to-end complaint flow validation (C4)."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Any

from app.graph.graph import build_graph
from app.graph.state import ChatState
from app.services.llm import LLMClient


class MockE2E(LLMClient):
    """Mock LLM that returns predictable values for E2E tests."""

    def __init__(self, responses=None):
        self.responses = responses or {}

    def classify(self, message):
        if "order" in message.lower() and "mau" in message.lower():
            return {"intent": "confirm_order", "confidence": 0.9}
        return {"intent": "faq", "confidence": 0.8, "has_complaint_signal": False, "sentiment": "neutral"}

    def classify_with_history(self, messages):
        last_msg = messages[-1]["content"] if messages else ""
        if "order" in last_msg.lower() and "mau" in last_msg.lower():
            return {"intent": "confirm_order", "confidence": 0.9}
        return {"intent": "faq", "confidence": 0.8, "has_complaint_signal": False, "sentiment": "neutral"}

    def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
        key = f"compose_{message[:30]}"
        if key in self.responses:
            return self.responses[key]
        if "lubang" in message.lower():
            return "Mohon maaf, produk kami bisa diganti atau dikembalikan karena rusak. Boleh kami bantu proses penggantiannya sekarang, Kak?"
        elif "garansi" in message.lower():
            return "Garansi produk kami 1 bulan dari tanggal pembelian. Ada yang mau ditanyakan lagi, Kak?"
        elif "harga" in message.lower():
            return "Untuk informasi harga, silakan hubungi kami. Boleh dibantu produk yang mana, Kak?"
        elif "ada" in message.lower() and "kaos" in message.lower():
            return "Kaos hitam tersedia di gudang. Mau dibantu pesan kaosnya sekarang, Kak?"
        elif "Saya mau order" in message:
            return "Owner akan follow up via WhatsApp untuk konfirmasi pesanan Anda. Boleh dibantu nama dan alamat pengirimannya, Kak?"
        return "Terima kasih pesannya sudah kami terima. Boleh kami bantu apa lagi, Kak?"

    def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
        return self.compose_reply(message, retrieved_row, match_kind, customer_context)


def _build_mock_graph(llm_client=None, sheets_faq_response=None, sheets_catalog_response=None):
    """Build graph with customizable sheet responses."""
    sheets_client = MagicMock()

    default_faq_answer = {
        "pertanyaan": "faqa",
        "jawaban": "Default jawaban.",
    }
    sheets_client.lookup_faq = MagicMock(return_value=sheets_faq_response if sheets_faq_response is not None else default_faq_answer)
    sheets_client.read_catalog = MagicMock(return_value=sheets_catalog_response if sheets_catalog_response else [
        {"id": "1", "nama_produk": "Kaos Hitam", "deskripsi": "Kaos hitam ukuran L tersedia"},
        {"id": "2", "nama_produk": "Hoodie Biru", "deskripsi": "Hoodie biru hangat dan nyaman"},
    ])
    gateway_client = MagicMock()
    gateway_client.send_message = AsyncMock(return_value={"ok": True})
    return build_graph(llm_client=llm_client, sheets_client=sheets_client, gateway_client=gateway_client)


@pytest.mark.parametrize("message,expected_action,expected_contains,lookup_faq_response,products,intent_override", [
    ("Garansi berapa bulan?", "reply", ["garansi", "bulan"], {
        "pertanyaan": "garansi berapa bulan", "jawaban": "Garansi produk kami 1 bulan dari tanggal pembelian."
    }, [], None),
    ("Kaos hitam ukuran L ada ga?", "reply", ["kaos", "hitam"], None, [
        {"id": "1", "nama_produk": "Kaos Hitam", "deskripsi": "Kaos hitam ukuran L tersedia"},
    ], None),
    ("produk saya ada lubang di leher padahal baru sampe", "reply", ["rusak", "dikembalikan"], None, [], None),
    ("gak suka barangnya", "fallback", [], None, [], {"intent": "unclear", "confidence": 0.3, "has_complaint_signal": False, "sentiment": "negative"}),
], ids=["faq_match", "product_check", "complaint_no_faq", "unclear_intent"])
def test_e2e_basic_scenarios(message, expected_action, expected_contains, lookup_faq_response, products, intent_override):
    """Run full graph and verify outcome matches expectations."""
    # If intent_override is provided, use a custom LLM that returns that intent
    if intent_override:
        class OverrideLLM(MockE2E):
            def classify_with_history(self, messages):
                return intent_override
        llm = OverrideLLM()
    else:
        llm = MockE2E()
    graph = _build_mock_graph(llm_client=llm, sheets_faq_response=lookup_faq_response, sheets_catalog_response=products)

    # Patch semantic search to avoid HF connection issues during tests
    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": "test_tenant",
        "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc",
        "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }), patch("app.graph.nodes.SemanticSearchClient.from_defaults") as mock_semantic_cls:
        mock_semantic = MagicMock()
        mock_semantic.search.return_value = []
        mock_semantic_cls.return_value = mock_semantic

        state: ChatState = {
            "tenant_id": "test_tenant",
            "wa_number": "+6281234567890",
            "thread_id": "test:+6281234567890",
            "message_text": message,
        }

        result = graph.invoke(state)

    assert result.get("action") == expected_action, f"Expected action={expected_action}, got {result.get('action')}, fallback_reason={result.get('fallback_reason')}"

    if expected_contains:
        reply_text = result.get("reply_text", "")
        for keyword in expected_contains:
            assert keyword.lower() in reply_text.lower(), f"Keyword '{keyword}' not found in: {reply_text}"


def test_e2e_customer_context_is_propagated():
    """Verify customer_context from B1 gets passed to C2 compose_reply when lookup finds no faq match."""
    captured_context = {"ctx": None}

    class CapturingLLM(MockE2E):
        def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
            captured_context["ctx"] = customer_context
            return "Responding normally. Boleh dibantu apa lagi, Kak?"

        def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
            captured_context["ctx"] = customer_context
            return "Responding normally. Boleh dibantu apa lagi, Kak?"

    llm = CapturingLLM()
    graph = _build_mock_graph(llm_client=llm)

    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": "test_tenant", "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc", "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }), patch("app.graph.nodes.SemanticSearchClient.from_defaults") as mock_semantic:
        mock_semantic.return_value = MagicMock(search=lambda *a, **kw: [])
        state: ChatState = {
            "tenant_id": "test_tenant",
            "wa_number": "+6281234567890",
            "thread_id": "test:+6281234567890",
            "message_text": "produk saya ada lubang di leher padahal baru sampe",
        }

        result = graph.invoke(state)

    assert captured_context["ctx"] is not None, "customer_context was not populated by analyze_customer_context"
    assert isinstance(captured_context["ctx"], dict), f"customer_context should be dict, got {type(captured_context['ctx'])}"
    assert result.get("action") == "reply"


def test_order_confirmation_shortcuts_llm():
    """Confirm order should skip LLM call entirely per existing behavior."""
    call_count = {"value": 0}

    class CountingLLM(LLMClient):
        def classify(self, message):
            return {"intent": "confirm_order", "confidence": 0.9}

        def classify_with_history(self, messages):
            return {"intent": "confirm_order", "confidence": 0.9}

        def compose_reply(self, *args, **kwargs):
            call_count["value"] += 1
            return "Should not be called"

        def compose_reply_with_history(self, *args, **kwargs):
            call_count["value"] += 1
            return "Should not be called"

    llm = CountingLLM()
    graph = _build_mock_graph(llm_client=llm)

    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": "test_tenant", "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc", "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }), patch("app.graph.nodes.SemanticSearchClient.from_defaults") as mock_semantic:
        mock_semantic.return_value = MagicMock(search=lambda *a, **kw: [])
        state: ChatState = {
            "tenant_id": "test_tenant",
            "wa_number": "+6281234567890",
            "thread_id": "test:+6281234567890",
            "message_text": "Saya mau order 2 pcs hoodie",
        }

        result = graph.invoke(state)

    assert call_count["value"] == 0, f"LLM compose was called {call_count['value']} times for order confirmation"
    assert result.get("action") == "order"
    assert "order diterima" in str(result.get("reply_text", "")).lower()


# ============================================
# EDGE CASE TESTS: Semantic Search Failure
# ============================================

@pytest.mark.parametrize("mock_semantic_exception,expected_action", [
    (None, "reply"),  # No exception → success path
    (Exception("HF down"), "reply"),  # Exception but keyword match should still work
    (ConnectionError("timeout"), "reply"),  # Connection error
], ids=["no_exception", "semantic_error", "connection_error"])
def test_semantic_search_failure_handling(mock_semantic_exception, expected_action):
    """Verify graph degrades gracefully when semantic search fails — still replies via fallback path."""
    from app.graph.nodes import SemanticSearchError

    llm = MockE2E()
    graph = _build_mock_graph(llm_client=llm)

    # Simulate semantic search returning no hits or raising exception
    class MockSemantic:
        def search(self, **kwargs):
            if isinstance(mock_semantic_exception, Exception):
                raise mock_semantic_exception
            return []

    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": "test_tenant",
        "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc",
        "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }), patch("app.graph.nodes.SemanticSearchClient.from_defaults", return_value=MockSemantic()):
        state: ChatState = {
            "tenant_id": "test_tenant",
            "wa_number": "+6281234567890",
            "thread_id": "test:+6281234567890",
            "message_text": "garansi berapa bulan?",
        }

        result = graph.invoke(state)

    assert result.get("action") == expected_action, f"Expected action={expected_action}, got {result.get('action')}"


# ============================================
# EDGE CASE TESTS: Empty Catalog / Missing Data
# ============================================

def test_empty_catalog_faq_lookup():
    """When catalog is empty and no FAQ match, route should go to product check or analyze path."""
    from app.graph.nodes import SemanticSearchError

    llm = MockE2E()
    # Empty catalog + faq match from lookup_fqa default → should use catalog_answer path to compose
    graph = _build_mock_graph(llm_client=llm, sheets_catalog_response=[])

    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": "test_tenant", "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc", "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }), patch("app.graph.nodes.SemanticSearchClient.from_defaults") as mock_semantic:
        mock_semantic.return_value = MagicMock(search=lambda *a, **kw: [])
        state: ChatState = {
            "tenant_id": "test_tenant",
            "wa_number": "+6281234567890",
            "thread_id": "test:+6281234567890",
            "message_text": "produk saya rusak",
        }

        result = graph.invoke(state)

    # With empty catalog but default faq_match, route goes analyze_customer_context → compose_reply_fallback
    # This results in action=fallback because compose_reply_fallback is the node for this path
    assert result.get("action") in ("fallback", "reply"), f"Expected action in fallback/reply, got {result.get('action')}"
    if result.get("action") == "fallback":
        assert "fallback_reason" in result, "fallback_reason should be set on fallback"


def test_lookup_catalog_no_sheets_client():
    """Ensure graph validates required clients at compilation time — should raise when none injected."""
    from app.graph.graph import get_compiled_graph
    with pytest.raises(RuntimeError, match="Clients not injected"):
        get_compiled_graph()


# ============================================
# EDGE CASE TESTS: Multi-Turn Conversation Flow
# ============================================

async def send_mock_message(gateway, thread, message):
    """Helper to simulate sending a message in multi-turn."""
    return {"ok": True}


class MultiTurnMockE2E(MockE2E):
    """Mock that remembers conversation history across turns."""

    def __init__(self):
        super().__init__()
        self.history_calls = 0

    def classify_with_history(self, messages):
        self.history_calls += 1
        last_msg = messages[-1]["content"] if messages else ""

        # Check previous messages for order intent from earlier turns
        if any("order" in m.get("content", "").lower() for m in messages[:-1]):
            return {"intent": "confirm_order", "confidence": 0.95}

        if "garansi" in last_msg.lower():
            return {"intent": "faq", "confidence": 0.85, "has_complaint_signal": False, "sentiment": "neutral"}
        if "lubang" in last_msg.lower():
            return {"intent": "faq", "confidence": 0.75, "has_complaint_signal": True, "sentiment": "negative"}
        # Product inquiry keywords
        if any(kw in last_msg.lower() for kw in ["harga", "tersedia", "ada", "ukuran", "kaos", "hoodie", "topi", "tas"]):
            return {"intent": "check_product", "confidence": 0.85, "has_complaint_signal": False, "sentiment": "neutral"}
        return {"intent": "faq", "confidence": 0.8, "has_complaint_signal": False, "sentiment": "neutral"}


def test_multi_turn_garansi_then_product():
    """Garansi (FAQ) followed by product check — context should persist across turns."""
    llm = MultiTurnMockE2E()
    # Provide faq response via _build_mock_graph parameters
    graph = _build_mock_graph(
        llm_client=llm,
        sheets_faq_response={"pertanyaan": "garansi berapa bulan", "jawaban": "Garansi produk kami 1 bulan dari tanggal pembelian."},
        sheets_catalog_response=[{"id": "1", "nama_produk": "Kaos Hitam", "deskripsi": "Kaos hitam ukuran L tersedia"}],
    )

    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": "test_tenant", "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc", "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }), patch("app.services.semantic_search.SemanticSearchClient.from_defaults") as mock_semantic:
        mock_semantic.return_value = MagicMock(search=lambda *a, **kw: [])

        # First turn: garansi — should get proper faq reply from catalog
        state1: ChatState = {
            "tenant_id": "test_tenant",
            "wa_number": "+6281234567890",
            "thread_id": "test:+6281234567890",
            "message_text": "garansi berapa bulan?",
            "message_history": [],
        }
        result1 = graph.invoke(state1)
        assert result1.get("action") == "reply"
        reply1 = result1.get("reply_text", "")
        # Expect garansi-related content since faq match was successful
        assert "garansi" in reply1.lower() or "bulan" in reply1.lower(), f"Expected garansi or bulan in reply: {reply1}"

        # Second turn: product inquiry using same thread
        state2: ChatState = {
            "tenant_id": "test_tenant",
            "wa_number": "+6281234567890",
            "thread_id": "test:+6281234567890",
            "message_text": "harga kaos hitam?",
            "message_history": [{"role": "user", "content": "garansi berapa bulan?"},
                               {"role": "assistant", "content": result1.get("reply_text", "")}],
        }
        result2 = graph.invoke(state2)
        # This goes through catalog/product lookup → analyze → reply
        assert result2.get("action") == "reply"
        reply2 = result2.get("reply_text", "")
        # Should contain product-related content (kaos, harga, tersedia)
        assert any(kw in reply2.lower() for kw in ["kaos", "harga", "hitam"]), f"Expected product keywords in reply: {reply2}"


def test_empty_message_handling():
    """Empty or whitespace-only messages should trigger fallback."""
    llm = MultiTurnMockE2E()
    graph = _build_mock_graph(llm_client=llm)

    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": "test_tenant", "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc", "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }), patch("app.graph.nodes.SemanticSearchClient.from_defaults") as mock_semantic:
        mock_semantic.return_value = MagicMock(search=lambda *a, **kw: [])

        state: ChatState = {
            "tenant_id": "test_tenant",
            "wa_number": "+6281234567890",
            "thread_id": "test:+6281234567890",
            "message_text": "   \t\n  ",  # whitespace only
            "message_history": [],
        }
        result = graph.invoke(state)
        # Empty/whitespace messages should go to fallback (graph-level guard)
        assert result.get("action") == "fallback", f"Expected fallback for empty message, got {result.get('action')}"
        assert result.get("fallback_reason") in ["no_data", "unclear"], f"Expected fallback reason, got {result.get('fallback_reason')}"


def test_long_message_handling():
    """Long messages (exceeding typical token limits) should be handled gracefully."""
    # Create a very long message (e.g., 5000 characters) by repeating a base phrase.
    base = "Mesin pemprosesan teks adalah alat yang sangat berguna untuk memproses berbagai jenis teks. " * 100
    llm = MultiTurnMockE2E()
    graph = _build_mock_graph(llm_client=llm)

    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": "test_tenant", "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc", "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }), patch("app.graph.nodes.SemanticSearchClient.from_defaults") as mock_semantic:
        mock_semantic.return_value = MagicMock(search=lambda *a, **kw: [])

        state: ChatState = {
            "tenant_id": "test_tenant",
            "wa_number": "+6281234567890",
            "thread_id": "test:+6281234567890",
            "message_text": base,
            "message_history": [],
        }
        result = graph.invoke(state)
        assert result.get("action") in ("reply", "fallback", "order"), f"Expected valid action, got {result.get('action')}"
        # Ensure the result contains expected keys
        assert "action" in result, "Result must contain 'action' key"
        # Should either have a reply_text or fall back gracefully
        assert "reply_text" in result or result.get("action") == "fallback", f"Expected reply_text or fallback, got result: {result}"


def test_message_with_only_special_characters():
    """Messages with only special characters (no alphanumeric) should also trigger fallback.

    Only checks that the system handles these gracefully (no crash); the LLM
    may classify them as complaints or unclear, both of which are valid paths.
    """
    special_messages = ["!!!", "???###", "€@@%", "", "   "]
    llm = MultiTurnMockE2E()
    graph = _build_mock_graph(llm_client=llm)

    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": "test_tenant", "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc", "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }), patch("app.graph.nodes.SemanticSearchClient.from_defaults") as mock_semantic:
        mock_semantic.return_value = MagicMock(search=lambda *a, **kw: [])

        for msg in special_messages:
            state: ChatState = {
                "tenant_id": "test_tenant",
                "wa_number": "+6281234567890",
                "thread_id": "test:+6281234567890",
                "message_text": msg,
                "message_history": [],
            }
            result = graph.invoke(state)
            # Whitespace-only/empty messages fallback; non-empty special chars
            # are handled gracefully (no crash, sensible action).
            assert result.get("action") in ("reply", "fallback", "order"), (
                f"Expected valid action for message '{msg}', got {result.get('action')}"
            )
            # Should not crash and should produce a usable response
            assert "reply_text" in result or result.get("action") == "fallback"


def test_long_message_handling():
    """Long messages (exceeding typical token limits) should be handled gracefully."""
    # Create a very long message (e.g., 5000 characters) by repeating a base phrase.
    base = "Mesin pemprosesan teks adalah alat yang sangat berguna untuk memproses berbagai jenis teks. " * 100
    llm = MultiTurnMockE2E()
    graph = _build_mock_graph(llm_client=llm)

    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": "test_tenant", "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc", "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }), patch("app.graph.nodes.SemanticSearchClient.from_defaults") as mock_semantic:
        mock_semantic.return_value = MagicMock(search=lambda *a, **kw: [])

        state: ChatState = {
            "tenant_id": "test_tenant",
            "wa_number": "+6281234567890",
            "thread_id": "test:+6281234567890",
            "message_text": base,
            "message_history": [],
        }
        result = graph.invoke(state)
        assert result.get("action") in ("reply", "fallback")
        # Ensure no exception or crash occurred
        assert "reply_text" in result or "action" in result


def test_multi_turn_complaint_then_followup():
    """Complaint followed by follow-up — customer context should propagate."""
    llm = MultiTurnMockE2E()
    graph = _build_mock_graph(llm_client=llm)

    captured_contexts = []

    class TrackingLLM(MultiTurnMockE2E):
        def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
            captured_contexts.append(customer_context)
            if "baru sampe" in message:
                return "Mohon maaf, produk kami bisa diganti atau dikembalikan karena rusak."
            return "Terima kasih, akan kami proses."

    llm_tracker = TrackingLLM()
    graph = _build_mock_graph(llm_client=llm_tracker)

    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": "test_tenant", "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc", "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }), patch("app.graph.nodes.SemanticSearchClient.from_defaults") as mock_semantic:
        mock_semantic.return_value = MagicMock(search=lambda *a, **kw: [])

        # First turn: complaint — classified with complaint signal → routed to
        # fallback_human (owner handoff), NOT compose/reply.
        state1: ChatState = {
            "tenant_id": "test_tenant",
            "wa_number": "+6281234567890",
            "thread_id": "test:+6281234567890",
            "message_text": "produk saya ada lubang di leher padahal baru sampe",
            "message_history": [],
        }
        result1 = graph.invoke(state1)
        assert result1.get("action") == "fallback"

        # Second turn: follow-up about replacement process
        state2: ChatState = {
            "tenant_id": "test_tenant",
            "wa_number": "+6281234567890",
            "thread_id": "test:+6281234567890",
            "message_text": "bagaimana proses penggantian?",
            "message_history": [{"role": "user", "content": "produk saya ada lubang di leher padahal baru sampe"},
                               {"role": "assistant", "content": result1.get("reply_text", "")}],
        }
        result2 = graph.invoke(state2)
        # Customer context should be populated on the follow-up turn (turn 1
        # went to fallback_human, which does not run analyze_customer_context).
        assert len(captured_contexts) >= 1, f"At least one customer context, got {len(captured_contexts)}"
        assert captured_contexts[0] is not None, "Second turn should have customer_context"
        assert result2.get("action") == "reply"


def test_multi_turn_order_shortcut():
    """Order intent detected by classifier should shortcut to order action without compose."""
    order_called = {"value": False}
    compose_called = {"value": False}

    class OrderShortcutLLM(MockE2E):
        def classify(self, message):
            if "order" in message.lower():
                order_called["value"] = True
                return {"intent": "confirm_order", "confidence": 0.95}
            return super().classify(message)

        def classify_with_history(self, messages):
            last = messages[-1].get("content", "") if messages else ""
            if "order" in last.lower():
                order_called["value"] = True
                return {"intent": "confirm_order", "confidence": 0.95}
            return super().classify_with_history(messages)

        def compose_reply(self, *args, **kwargs):
            compose_called["value"] = True
            return "Should not be called for order"

        def compose_reply_with_history(self, *args, **kwargs):
            compose_called["value"] = True
            return "Should not be called for order"

    llm = OrderShortcutLLM()
    graph = _build_mock_graph(llm_client=llm)

    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": "test_tenant", "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc", "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }), patch("app.graph.nodes.SemanticSearchClient.from_defaults") as mock_semantic:
        mock_semantic.return_value = MagicMock(search=lambda *a, **kw: [])

        state: ChatState = {
            "tenant_id": "test_tenant",
            "wa_number": "+6281234567890",
            "thread_id": "test:+6281234567890",
            "message_text": "setelah tanya garansi, saya mau order hoodie",
            # Include current message as last entry so classify_with_history can detect it
            "messages": [{"role": "user", "content": "setelah tanya garansi, saya mau order hoodie"}],
        }
        result = graph.invoke(state)

        assert order_called["value"] is True, "Order intent should be detected by classify"
        assert result.get("action") == "order", f"Expected order action, got {result.get('action')}"
        assert "order diterima" in str(result.get("reply_text", "")).lower(), "Reply should confirm the order"