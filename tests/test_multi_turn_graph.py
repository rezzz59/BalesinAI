"""Multi-turn order flow driven through the REAL compiled graph + conversation_repo.

Unlike test_multi_turn_order.py (which reimplements the webhook loop), these
tests invoke the actual build_graph() and persist state via conversation_repo,
so integration bugs in classify/lookup/compose/capture round-trips surface.
"""
import os
import tempfile

import pytest
from sqlalchemy import create_engine
from unittest.mock import MagicMock, AsyncMock, patch

import app.db.engine as engine_mod
from app.db.models import Base
from app.db.conversation_repo import get_conversation_state, save_conversation_state

from app.graph.graph import build_graph
from app.graph.state import ChatState
from app.services.llm import LLMClient


class TurnLLM(LLMClient):
    """Scripted LLM: each turn's message maps to a classification result."""

    def __init__(self, script):
        self.script = script

    def _classify(self, text):
        text = text or ""
        for key, result in self.script.items():
            if key in text.lower():
                return result
        return {"intent": "unclear", "confidence": 0.3, "has_complaint_signal": False, "sentiment": "neutral"}

    def classify(self, message):
        return self._classify(message)

    def classify_with_history(self, messages):
        last = messages[-1]["content"] if messages else ""
        return self._classify(last)

    def compose_reply(self, message, retrieved_row, match_kind, customer_context=None, persona=None):
        return "Baik Kak, kami bantu carikan. Boleh dibantu detailnya, Kak?"

    def compose_reply_with_history(self, messages, message, retrieved_row, match_kind, customer_context=None, persona=None):
        return "Baik Kak, kami bantu carikan. Boleh dibantu detailnya, Kak?"


@pytest.fixture(autouse=True)
def reset_db():
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="test_graph_")
    os.close(fd)
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    engine_mod.reset_engine_for_testing(eng)
    yield
    eng.dispose()
    engine_mod.reset_engine_for_testing(None)
    try:
        os.unlink(db_path)
    except OSError:
        pass


def _build_graph(llm):
    sheets_client = MagicMock()
    sheets_client.read_catalog = MagicMock(return_value=[
        {"nama_produk": "Kaos Hitam", "harga": "50000", "ready": "Y"},
        {"nama_produk": "Hoodie Biru", "harga": "150000", "ready": "Y"},
    ])
    sheets_client.lookup_faq = MagicMock(return_value=None)
    gateway = MagicMock()
    gateway.send_message = AsyncMock(return_value={"ok": True})
    return build_graph(
        llm_client=llm,
        sheets_client=sheets_client,
        gateway_client=gateway,
        include_chat_log=False,
        persist_orders=False,
    )


def _run_turn(graph, tenant_id, thread_id, message_text, llm):
    prior = get_conversation_state(tenant_id, thread_id)
    state: ChatState = {
        "tenant_id": tenant_id,
        "wa_number": "+628123",
        "thread_id": thread_id,
        "message_text": message_text,
    }
    if prior.get("order_draft"):
        state["order_draft"] = prior["order_draft"]
    if prior.get("messages"):
        state["messages"] = prior["messages"]

    with patch("app.db.tenant_repo.get_tenant", return_value={
        "tenant_id": tenant_id,
        "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc",
        "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
        "business_type": "fashion",
    }), patch("app.graph.nodes.SemanticSearchClient.from_defaults") as mock_sem:
        mock_sem.return_value = MagicMock(search=lambda *a, **kw: [])
        result = graph.invoke(state)

    draft = result.get("order_draft")
    memory = {}
    if draft is not None:
        memory["order_draft"] = draft
    if result.get("messages"):
        memory["messages"] = result["messages"][-40:]
    if result.get("action") == "order" and result.get("order_code"):
        memory.pop("order_draft", None)
    if memory:
        save_conversation_state(tenant_id, thread_id, memory)
    return result


def test_multi_turn_order_build_across_real_graph():
    llm = TurnLLM({
        "kaos hitam 2": {"intent": "confirm_order", "confidence": 0.9},
        "tambah hoodie": {"intent": "confirm_order", "confidence": 0.9},
    })
    graph = _build_graph(llm)

    r1 = _run_turn(graph, "t-real", "th-real", "mau kaos hitam 2", llm)
    assert r1.get("action") == "reply"  # fashion: size/color missing → consultation
    assert get_conversation_state("t-real", "th-real").get("order_draft")

    r2 = _run_turn(graph, "t-real", "th-real", "tambah hoodie 1", llm)
    products = {i["product"]: i["qty"] for i in r2.get("order_draft", [])}
    assert products.get("Kaos Hitam") == 2
    assert products.get("Hoodie Biru") == 1


def test_multi_turn_cancel_clears_draft_real_graph():
    llm = TurnLLM({
        "kaos hitam 2": {"intent": "confirm_order", "confidence": 0.9},
        "batalkan": {"intent": "faq", "confidence": 0.9},
    })
    graph = _build_graph(llm)

    _run_turn(graph, "t-cancel", "th-cancel", "mau kaos hitam 2", llm)
    assert get_conversation_state("t-cancel", "th-cancel").get("order_draft")

    r = _run_turn(graph, "t-cancel", "th-cancel", "batalkan pesanan saya", llm)
    assert r.get("intent") == "cancel_order"
    assert r.get("action") == "reply"
    assert get_conversation_state("t-cancel", "th-cancel").get("order_draft") == []


def test_message_history_stays_bounded():
    llm = TurnLLM({"faq": {"intent": "faq", "confidence": 0.9}})
    graph = _build_graph(llm)

    thread = "th-history"
    for i in range(50):
        _run_turn(graph, "t-hist", thread, f"faq pertanyaan {i}", llm)

    state = get_conversation_state("t-hist", thread)
    msgs = state.get("messages", [])
    assert len(msgs) <= 40
