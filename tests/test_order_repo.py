"""Tests for app.db.order_repo."""
import json
import pytest
from sqlalchemy import create_engine

import app.db.engine as engine_mod
from app.db.models import Base


@pytest.fixture(autouse=True)
def reset_db():
    """Fresh in-memory DB per test."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    engine_mod.reset_engine_for_testing(eng)
    yield
    eng.dispose()
    engine_mod.reset_engine_for_testing(None)


from app.db.order_repo import (
    generate_order_code,
    get_order,
    get_order_by_code,
    insert_order,
    list_orders,
    update_order_status,
)


class TestGenerateOrderCode:
    def test_format(self):
        code = generate_order_code()
        assert code.startswith("C-")
        assert len(code) == 8  # "C-" + 6 hex

    def test_uniqueness(self):
        codes = {generate_order_code() for _ in range(100)}
        assert len(codes) == 100


class TestInsertAndGetOrder:
    def test_basic(self):
        items = [{"product": "Kaos Hitam", "qty": 2, "price": 50000}]
        order = insert_order(
            tenant_id="t1",
            thread_id="th1",
            wa_number="+6281234567890",
            items=items,
            total=100000,
            buyer_name="Budi",
            buyer_address="Jl. Merdeka 10",
        )
        assert order["id"] is not None
        assert order["order_code"].startswith("C-")
        assert order["items"] == items
        assert order["total"] == 100000
        assert order["buyer_name"] == "Budi"
        assert order["status"] == "pending"

    def test_get_by_id(self):
        order = insert_order(
            tenant_id="t1",
            thread_id="th1",
            wa_number="+628",
            items=[],
        )
        fetched = get_order("t1", order["id"])
        assert fetched is not None
        assert fetched["order_code"] == order["order_code"]

    def test_get_wrong_tenant(self):
        order = insert_order(
            tenant_id="t1",
            thread_id="th1",
            wa_number="+628",
            items=[],
        )
        assert get_order("t2", order["id"]) is None

    def test_get_by_code(self):
        order = insert_order(
            tenant_id="t1",
            thread_id="th1",
            wa_number="+628",
            items=[],
            order_code="C-CUSTOM1",
        )
        fetched = get_order_by_code("t1", "C-CUSTOM1")
        assert fetched is not None
        assert fetched["order_code"] == "C-CUSTOM1"

    def test_get_nonexistent(self):
        assert get_order("t1", 99999) is None

    def test_items_parsed_json(self):
        items = [{"product": "Kaos", "qty": 1, "price": 50000}]
        order = insert_order(tenant_id="t1", thread_id="th1", wa_number="+628", items=items)
        fetched = get_order("t1", order["id"])
        assert fetched["items"] == items


class TestListOrders:
    def test_list_by_tenant(self):
        insert_order(tenant_id="t1", thread_id="th1", wa_number="+628", items=[{"product": "A", "qty": 1}])
        insert_order(tenant_id="t2", thread_id="th1", wa_number="+628", items=[{"product": "B", "qty": 1}])
        insert_order(tenant_id="t1", thread_id="th1", wa_number="+628", items=[{"product": "C", "qty": 1}])
        orders = list_orders("t1")
        assert len(orders) == 2

    def test_list_all(self):
        insert_order(tenant_id="t1", thread_id="th1", wa_number="+628", items=[])
        insert_order(tenant_id="t2", thread_id="th1", wa_number="+628", items=[])
        assert len(list_orders(None)) == 2

    def test_list_limit(self):
        for _ in range(5):
            insert_order(tenant_id="t1", thread_id="th1", wa_number="+628", items=[])
        assert len(list_orders("t1", limit=3)) == 3

    def test_list_filter_status(self):
        insert_order(tenant_id="t1", thread_id="th1", wa_number="+628", items=[], status="pending")
        insert_order(tenant_id="t1", thread_id="th1", wa_number="+628", items=[], status="confirmed")
        pending = list_orders("t1", status="pending")
        assert len(pending) == 1
        assert pending[0]["status"] == "pending"


class TestUpdateStatus:
    def test_update(self):
        order = insert_order(tenant_id="t1", thread_id="th1", wa_number="+628", items=[])
        updated = update_order_status("t1", order["id"], "confirmed")
        assert updated["status"] == "confirmed"

    def test_update_not_found(self):
        assert update_order_status("t1", 99999, "confirmed") is None
