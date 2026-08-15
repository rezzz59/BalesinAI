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


def test_validate_reply_accepts_size_within_source_range():
    """A reply naming 'L' is valid when the source offers 'M-XXL' — L is in range."""
    source = {"name": "Kemeja Batik", "deskripsi": "Kemeja batik bahan katun premium, size M-XXL."}
    validate_reply("Kemeja Batik size L warna navy ready ya Kak", source)


def test_validate_reply_rejects_size_outside_source_range():
    """A reply naming 'S' must be rejected when the source only offers 'M-XXL'."""
    source = {"name": "Kemeja Batik", "deskripsi": "Kemeja batik bahan katun premium, size M-XXL."}
    with pytest.raises(LLMValidationError):
        validate_reply("Kemeja Batik ready size S ya Kak", source)


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


def test_validate_reply_accepts_same_value_different_formatting():
    """Same numeric value with different thousand-separator formatting must pass
    (150.000 == 150000), while a genuinely different number must be rejected."""
    source = {"price": "Rp 50.000"}
    validate_reply("Harga Rp 50.000 ya", source)  # verbatim
    validate_reply("Harga Rp50000 ya", source)    # same value, no separator
    validate_reply("Harga 50.000 ya", source)     # same value
    validate_reply("Harga Rp 50.000 saja", source)
    with pytest.raises(LLMValidationError):
        validate_reply("Harga Rp 500.000 ya", source)  # different value
    with pytest.raises(LLMValidationError):
        validate_reply("Harga Rp 5.000 ya", source)    # different value
