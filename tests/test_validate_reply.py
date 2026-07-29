"""Tests for post-generation reply validation."""
import pytest

from app.services.llm import LLMValidationError, validate_reply


def test_validate_reply_accepts_reply_with_verbatim_numbers():
    source = {"name": "Hoodie Fleece", "price": "Rp 150.000"}
    reply = "Halo Kak! Hoodie Fleece harga Rp 150.000 ya 🙏"
    validate_reply(reply, source)  # should not raise


def test_validate_reply_rejects_invented_number():
    source = {"name": "Hoodie Fleece", "price": "Rp 150.000"}
    reply = "Hoodie Fleece harga Rp 200.000"
    with pytest.raises(LLMValidationError):
        validate_reply(reply, source)


def test_validate_reply_rejects_invented_size():
    source = {"name": "Kaos", "sizes": "S, M, L"}
    reply = "Kaos ready size XL ya Kak"
    with pytest.raises(LLMValidationError):
        validate_reply(reply, source)


def test_validate_reply_accepts_referenced_size():
    source = {"name": "Kaos", "sizes": "S, M, L"}
    reply = "Size L ready ya Kak"
    validate_reply(reply, source)


def test_validate_reply_rejects_invented_stock_status():
    source = {"name": "Sepatu", "stock": "habis"}
    reply = "Stok ready ya Kak"
    with pytest.raises(LLMValidationError):
        validate_reply(reply, source)


def test_validate_reply_accepts_quoted_stock_status():
    source = {"name": "Sepatu", "stock": "habis"}
    reply = "Mohon maaf stok habis Kak"
    validate_reply(reply, source)


def test_validate_reply_handles_none_source_row():
    # When no row matched, the reply should not contain any made-up facts.
    # We can't validate against None, so validate_reply should treat None
    # as "nothing to check" (no exception raised for empty/short reply).
    validate_reply("Mohon maaf Kak, produk belum tersedia.", None)


def test_validate_reply_handles_dict_or_string_source_row():
    source_dict = {"name": "Hoodie", "price": "Rp 100.000"}
    source_str = "Hoodie Rp 100.000"
    validate_reply("Hoodie Rp 100.000 ready", source_dict)
    validate_reply("Hoodie Rp 100.000 ready", source_str)


def test_validate_reply_rejects_reformatted_price():
    # "Rp 50.000" must not appear as "Rp50,000" or "50000" in reply.
    source = {"price": "Rp 50.000"}
    with pytest.raises(LLMValidationError):
        validate_reply("Harga Rp 50000 ya", source)
    with pytest.raises(LLMValidationError):
        validate_reply("Harga Rp50,000 ya", source)
