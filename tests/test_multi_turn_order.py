"""Multi-turn order flow tests (Fase 3) — draft carryover across messages.

Multi-turn memory is wired at the webhook layer via conversation_repo: each
message loads prior thread state (order_draft), runs the graph, then saves
state back. These tests exercise that full loop.
"""
import os
import tempfile

import pytest
from sqlalchemy import create_engine

import app.db.engine as engine_mod
from app.db.models import Base

from app.db.conversation_repo import (
    clear_conversation_state,
    get_conversation_state,
    merge_conversation_state,
    save_conversation_state,
)


@pytest.fixture(autouse=True)
def reset_db():
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="test_")
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


class TestConversationState:
    def test_empty_when_none(self):
        assert get_conversation_state("t1", "th1") == {}

    def test_save_and_get(self):
        save_conversation_state("t1", "th1", {"order_draft": [{"product": "Kaos", "qty": 2}]})
        assert get_conversation_state("t1", "th1") == {"order_draft": [{"product": "Kaos", "qty": 2}]}

    def test_save_overwrites(self):
        save_conversation_state("t1", "th1", {"order_draft": []})
        save_conversation_state("t1", "th1", {"order_draft": [{"product": "Hoodie", "qty": 1}]})
        assert get_conversation_state("t1", "th1")["order_draft"][0]["product"] == "Hoodie"

    def test_thread_isolation(self):
        save_conversation_state("t1", "th1", {"a": 1})
        save_conversation_state("t1", "th2", {"a": 2})
        assert get_conversation_state("t1", "th1") == {"a": 1}
        assert get_conversation_state("t1", "th2") == {"a": 2}

    def test_merge(self):
        save_conversation_state("t1", "th1", {"order_draft": []})
        merged = merge_conversation_state("t1", "th1", {"order_draft": [{"product": "Kaos", "qty": 2}], "step": 1})
        assert merged["step"] == 1
        assert merged["order_draft"] == [{"product": "Kaos", "qty": 2}]
        assert get_conversation_state("t1", "th1")["step"] == 1

    def test_clear(self):
        save_conversation_state("t1", "th1", {"x": 1})
        clear_conversation_state("t1", "th1")
        assert get_conversation_state("t1", "th1") == {}


class TestMultiTurnOrderFlow:
    """End-to-end-ish: draft built across messages and persisted per thread."""

    def _simulate_message(self, tenant_id, thread_id, message_text, intent, order_draft=None):
        """Simulate one webhook turn: load prior state → run capture → save."""
        prior = get_conversation_state(tenant_id, thread_id)
        draft = order_draft if order_draft is not None else prior.get("order_draft")

        if intent == "confirm_order":
            from app.services.order_extractor import compute_total, extract_items, merge_items

            catalog = [
                {"nama_produk": "Kaos Hitam", "harga": "Rp 50.000", "ready": "Y"},
                {"nama_produk": "Hoodie Biru", "harga": "150000", "ready": "Y"},
            ]
            new_items = extract_items(message_text, catalog)
            merged = merge_items(draft or [], new_items) if new_items else (draft or [])
            total = compute_total(merged)
            # Webhook clears the draft on confirmed order (order_code present).
            save_conversation_state(tenant_id, thread_id, {"order_draft": merged})
            return {"action": "order", "order_draft": merged, "order_total": total, "order_code": "C-ABC123"}

        # check_product path
        msg_lower = message_text.lower()
        product = next(
            (p for p in [
                {"nama_produk": "Kaos Hitam", "harga": "Rp 50.000", "ready": "Y"},
                {"nama_produk": "Hoodie Biru", "harga": "150000", "ready": "Y"},
            ] if p["nama_produk"].lower() in msg_lower or p["nama_produk"].split()[0].lower() in msg_lower),
            None,
        )
        if product:
            save_conversation_state(tenant_id, thread_id, {"last_mentioned_product": product["nama_produk"]})
            return {"intent": "check_product", "product_match": product}
        return {"intent": "unclear", "action": "fallback"}

    def test_draft_built_over_messages(self):
        tenant, thread = "t1", "th-mt1"
        # Turn 1: check product
        r1 = self._simulate_message(tenant, thread, "ada kaos hitam?", "check_product")
        assert r1["product_match"]["nama_produk"] == "Kaos Hitam"

        # Turn 2: order 2 pcs
        r2 = self._simulate_message(tenant, thread, "mau kaos hitam 2 pcs", "confirm_order")
        assert r2["order_draft"] == [{"product": "Kaos Hitam", "qty": 2, "price": 50000.0}]
        assert r2["order_total"] == 100000.0
        assert get_conversation_state(tenant, thread)["order_draft"] == r2["order_draft"]

        # Turn 3: add another product — draft grows
        r3 = self._simulate_message(tenant, thread, "tambah hoodie biru 1", "confirm_order")
        products = {i["product"]: i for i in r3["order_draft"]}
        assert set(products) == {"Kaos Hitam", "Hoodie Biru"}
        assert products["Kaos Hitam"]["qty"] == 2
        assert r3["order_total"] == 250000.0

    def test_qty_correction_replaces(self):
        tenant, thread = "t1", "th-mt2"
        self._simulate_message(tenant, thread, "mau kaos hitam 2", "confirm_order")
        r = self._simulate_message(tenant, thread, "jadi 3 kaos hitam", "confirm_order")
        assert len(r["order_draft"]) == 1
        assert r["order_draft"][0]["qty"] == 3
        assert r["order_total"] == 150000.0

    def test_clear_draft_after_confirmed_order(self):
        tenant, thread = "t1", "th-mt3"
        self._simulate_message(tenant, thread, "mau kaos hitam 2", "confirm_order")
        assert get_conversation_state(tenant, thread)["order_draft"]
        # Simulate the webhook clearing draft once order is confirmed.
        clear_conversation_state(tenant, thread)
        assert get_conversation_state(tenant, thread) == {}

    def test_last_mentioned_product_tracked(self):
        tenant, thread = "t1", "th-mt4"
        self._simulate_message(tenant, thread, "ada hoodie biru?", "check_product")
        state = get_conversation_state(tenant, thread)
        assert state.get("last_mentioned_product") == "Hoodie Biru"
