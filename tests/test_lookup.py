"""Tests for lookup_catalog node."""
from unittest.mock import MagicMock

from app.graph.nodes import lookup_catalog
from app.graph.state import ChatState


def test_lookup_faq_finds_match():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "Berapa harga?",
        "intent": "faq",
    }

    fake_sheets = MagicMock()
    fake_sheets.lookup_faq = MagicMock(
        return_value={"pertanyaan": "Berapa harga?", "jawaban": "Mulai Rp 50.000"}
    )

    result = lookup_catalog(state, sheets_client=fake_sheets)

    assert result["catalog_answer"] == "Mulai Rp 50.000"
    assert result["product_match"] is None


def test_lookup_faq_no_match_returns_empty():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "xyzzy",
        "intent": "faq",
    }

    fake_sheets = MagicMock()
    fake_sheets.lookup_faq = MagicMock(return_value=None)

    result = lookup_catalog(state, sheets_client=fake_sheets)
    assert result == {}


def test_lookup_product_finds_match():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "Kaos ready ga?",
        "intent": "check_product",
    }

    fake_sheets = MagicMock()
    fake_sheets.read_catalog = MagicMock(
        return_value=[
            {"nama_produk": "Kaos Polos", "harga": "50000", "ready": "Y", "deskripsi": "Katun"},
            {"nama_produk": "Topi", "harga": "30000", "ready": "Y", "deskripsi": "Standar"},
        ]
    )

    result = lookup_catalog(state, sheets_client=fake_sheets)

    assert result["product_match"] is not None
    assert result["product_match"]["nama_produk"] == "Kaos Polos"


def test_lookup_product_no_keyword_match_returns_browse_list():
    """Catalog-browse query: zero keyword match → list all ready products."""
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "ada produk apa aja kak?",
        "intent": "check_product",
    }

    catalog = [
        {"nama_produk": "Hoodie Fleece", "harga": "150000", "ready": "Y", "deskripsi": "Bahan tebal"},
        {"nama_produk": "Kaos Polos", "harga": "50000", "ready": "Y", "deskripsi": "Katun combed"},
        {"nama_produk": "Totebag", "harga": "75000", "ready": "N", "deskripsi": "Pre-order"},
    ]
    fake_sheets = MagicMock()
    fake_sheets.read_catalog = MagicMock(return_value=catalog)
    fake_sheets.list_ready_products = MagicMock(
        return_value=[r for r in catalog if r["ready"] == "Y"]
    )

    result = lookup_catalog(state, sheets_client=fake_sheets)

    assert result["action"] == "reply"
    assert result["product_match"] is None
    assert "Hoodie Fleece" in result["reply_text"]
    assert "Kaos Polos" in result["reply_text"]
    assert "Totebag" not in result["reply_text"]  # non-ready excluded
    assert result["reply_text"].endswith("😊")


def test_lookup_product_no_keyword_match_no_ready_returns_empty():
    """If zero match AND zero ready products, fall through to fallback."""
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "apa aja yang ready?",
        "intent": "check_product",
    }

    fake_sheets = MagicMock()
    fake_sheets.read_catalog = MagicMock(
        return_value=[
            {"nama_produk": "X", "harga": "100", "ready": "N", "deskripsi": "PO"},
        ]
    )
    fake_sheets.list_ready_products = MagicMock(return_value=[])

    result = lookup_catalog(state, sheets_client=fake_sheets)
    assert result == {}