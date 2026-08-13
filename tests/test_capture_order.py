"""Tests for the order state machine in capture_order (B: complete/consultation)."""
import secrets

import pytest

from app.db.tenant_repo import delete_tenant, insert_or_update_tenant
from app.graph.nodes import capture_order

FASHION_CATALOG = [
    {"nama_produk": "Kemeja Batik Pria Premium", "harga": "Rp 135.000", "ready": "Y",
     "deskripsi": "Kemeja batik bahan katun premium, warna hitam dan navy, size M-XXL."},
    {"nama_produk": "Kaos Oversize Cotton - Hitam", "harga": "Rp 85.000", "ready": "Y",
     "deskripsi": "Kaos oversize bahan katun 24s, size M-XXL."},
]
KATERING_CATALOG = [
    {"nama_produk": "Paket Prasmanan A", "harga": "Rp 35.000", "ready": "Y",
     "deskripsi": "Nasi, lauk 3 macam, sayur, buah, air mineral. Minimal 50 porsi.", "min_order": "50"},
]
ONGKIR = [
    {"wilayah": "jakarta selatan", "ongkir": "Rp 85.000", "min_order": "50"},
]


class FakeSheets:
    def __init__(self, catalog, ongkir=None):
        self._catalog = catalog
        self._ongkir = ongkir or []

    def read_catalog(self):
        return self._catalog

    def read_ongkir(self):
        return self._ongkir


class FakeGateway:
    async def send_message(self, *args, **kwargs):
        return {"ok": True}


def _state(tenant_id, message):
    return {
        "tenant_id": tenant_id,
        "wa_number": "+6281234567890",
        "thread_id": f"test:{tenant_id}",
        "message_text": message,
        "timestamp": None,
    }


def _tenant(business_type: str) -> str:
    tid = f"cap-{secrets.token_hex(3)}"
    insert_or_update_tenant(
        tenant_id=tid, wa_api_key_encrypted=b"", google_sheet_id="",
        owner_wa_number="6281234567890", business_type=business_type,
        onboarding_status="ready", onboarding_data={}, data_source="upload",
    )
    return tid


@pytest.fixture
def fashion_tenant():
    tid = _tenant("fashion")
    yield tid
    delete_tenant(tid)


@pytest.fixture
def catering_tenant():
    tid = _tenant("kuliner")
    yield tid
    delete_tenant(tid)


async def test_fashion_order_complete_requires_size_and_color(fashion_tenant):
    r = await capture_order(
        _state(fashion_tenant, "mau beli 2 kemeja batik premium size L warna navy"),
        sheets_client=FakeSheets(FASHION_CATALOG),
        gateway_client=FakeGateway(),
        persist_orders=False,
    )
    assert r["action"] == "order"
    assert "Order diterima" in r["reply_text"]
    assert r["order_items"][0]["size"] == "L"
    assert r["order_items"][0]["color"] == "navy"


async def test_fashion_order_missing_color_is_consultation(fashion_tenant):
    r = await capture_order(
        _state(fashion_tenant, "mau beli 2 kemeja batik premium size L"),
        sheets_client=FakeSheets(FASHION_CATALOG),
        gateway_client=FakeGateway(),
        persist_orders=False,
    )
    assert r["action"] == "reply"
    assert "warna" in r["reply_text"]
    assert "Order diterima" not in r["reply_text"]


async def test_fashion_order_missing_size_is_consultation(fashion_tenant):
    r = await capture_order(
        _state(fashion_tenant, "mau beli 2 kemeja batik premium warna navy"),
        sheets_client=FakeSheets(FASHION_CATALOG),
        gateway_client=FakeGateway(),
        persist_orders=False,
    )
    assert r["action"] == "reply"
    assert "ukuran" in r["reply_text"]


async def test_catering_order_without_date_is_quote_not_accepted(catering_tenant):
    r = await capture_order(
        _state(catering_tenant, "mau pesan paket prasmanan a 50 porsi, kirim ke jakarta selatan"),
        sheets_client=FakeSheets(KATERING_CATALOG, ONGKIR),
        gateway_client=FakeGateway(),
        persist_orders=False,
    )
    assert r["action"] == "reply"
    assert "Ini rincian pesanan" in r["reply_text"]
    assert "Order diterima" not in r["reply_text"]
    assert "tanggal acaranya kapan" in r["reply_text"]
    assert r["order_total"] is None


async def test_catering_order_with_date_is_accepted(catering_tenant):
    r = await capture_order(
        _state(catering_tenant, "mau pesan paket prasmanan a 100 porsi tanggal 12 juli kirim ke jakarta selatan"),
        sheets_client=FakeSheets(KATERING_CATALOG, ONGKIR),
        gateway_client=FakeGateway(),
        persist_orders=False,
    )
    assert r["action"] == "order"
    assert "Order diterima" in r["reply_text"]
    assert r["order_total"] == 3585000.0


async def test_catering_below_minimum_is_not_accepted(catering_tenant):
    r = await capture_order(
        _state(catering_tenant, "mau pesan paket prasmanan a 10 porsi tanggal 12 juli"),
        sheets_client=FakeSheets(KATERING_CATALOG, ONGKIR),
        gateway_client=FakeGateway(),
        persist_orders=False,
    )
    assert r["action"] == "reply"
    assert "Order diterima" not in r["reply_text"]


async def test_token_partial_match_orders_fashion_item(fashion_tenant):
    """'kaos oversize hitam 2' must match 'Kaos Oversize Cotton - Hitam'."""
    r = await capture_order(
        _state(fashion_tenant, "mau beli 2 kaos oversize hitam"),
        sheets_client=FakeSheets(FASHION_CATALOG),
        gateway_client=FakeGateway(),
        persist_orders=False,
    )
    assert r["order_draft"][0]["product"] == "Kaos Oversize Cotton - Hitam"
    assert r["order_draft"][0]["qty"] == 2
    assert r["order_draft"][0]["color"] == "hitam"
