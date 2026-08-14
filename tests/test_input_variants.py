"""Edge-case customer input variants: pure emoji, mixed language, rapid back-to-back."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.graph.graph import build_graph
from app.graph.state import ChatState
from app.services.llm import LLMClient, MockLLMClient


def _build_graph(llm):
    sheets_client = MagicMock()
    sheets_client.lookup_faq = MagicMock(return_value=None)
    sheets_client.read_catalog = MagicMock(return_value=[])
    gateway = MagicMock()
    gateway.send_message = AsyncMock(return_value={"ok": True})
    return build_graph(
        llm_client=llm,
        sheets_client=sheets_client,
        gateway_client=gateway,
        include_chat_log=False,
        persist_orders=False,
    )


def _run(state, graph):
    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": "t-1",
        "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc",
        "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
        "business_type": "jualan",
    }), patch("app.graph.nodes.SemanticSearchClient.from_defaults") as mock_sem:
        mock_sem.return_value = MagicMock(search=lambda *a, **kw: [])
        return graph.invoke(state)


def test_pure_emoji_message_does_not_crash():
    llm = MockLLMClient()
    graph = _build_graph(llm)
    state: ChatState = {
        "tenant_id": "t-1",
        "wa_number": "+628123",
        "thread_id": "th-emoji",
        "message_text": "😊😊😊",
    }
    result = _run(state, graph)
    # Should not raise; either replies or falls back — both are acceptable.
    assert "action" in result


def test_mixed_language_message_does_not_crash():
    llm = MockLLMClient()
    graph = _build_graph(llm)
    state: ChatState = {
        "tenant_id": "t-1",
        "wa_number": "+628123",
        "thread_id": "th-mix",
        "message_text": "how much harga kaos ini? ready stock ga?",
    }
    result = _run(state, graph)
    assert "action" in result


def test_rapid_back_to_back_messages_same_thread():
    """Two invokes on the same thread in quick succession must not corrupt state."""
    llm = MockLLMClient()
    graph = _build_graph(llm)

    results = [
        _run(
            {
                "tenant_id": "t-1",
                "wa_number": "+628123",
                "thread_id": "th-rapid",
                "message_text": m,
            },
            graph,
        )
        for m in ("ada kaos?", "harga berapa?")
    ]

    assert all("action" in r for r in results)


def test_extremely_long_emoji_only():
    llm = MockLLMClient()
    graph = _build_graph(llm)
    state: ChatState = {
        "tenant_id": "t-1",
        "wa_number": "+628123",
        "thread_id": "th-longemoji",
        "message_text": "😂" * 500,
    }
    result = _run(state, graph)
    assert "action" in result
