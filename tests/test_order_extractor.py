"""Tests for app.services.order_extractor."""
from app.services.order_extractor import (
    compute_total,
    extract_buyer_info,
    extract_items,
    merge_items,
    _find_quantity,
    _parse_price,
)


# ---------------------------------------------------------------------------
# _parse_price
# ---------------------------------------------------------------------------

class TestParsePrice:
    def test_int(self):
        assert _parse_price(50000) == 50000.0

    def test_float(self):
        assert _parse_price(50000.5) == 50000.5

    def test_string_plain(self):
        assert _parse_price("50000") == 50000.0

    def test_string_rp_dot(self):
        assert _parse_price("Rp 50.000") == 50000.0

    def test_string_rp_no_space(self):
        assert _parse_price("Rp100.000") == 100000.0

    def test_string_idr(self):
        assert _parse_price("IDR 1.500.000") == 1500000.0

    def test_string_plain_without_rp(self):
        assert _parse_price("75000") == 75000.0

    def test_none(self):
        assert _parse_price(None) is None

    def test_non_numeric_string(self):
        assert _parse_price("harga hubungi") is None

    def test_comma_separator(self):
        assert _parse_price("Rp 1,500,000") == 1500000.0


# ---------------------------------------------------------------------------
# _find_quantity
# ---------------------------------------------------------------------------

class TestFindQuantity:
    def test_default_one(self):
        assert _find_quantity("mau beli kaos hitam", "kaos hitam") == 1

    def test_qty_after_product(self):
        assert _find_quantity("kaos hitam 3 pcs", "kaos hitam") == 3

    def test_qty_before_product(self):
        assert _find_quantity("2 kaos hitam", "kaos hitam") == 2

    def test_x_format(self):
        assert _find_quantity("kaos hitam x5", "kaos hitam") == 5

    def test_qty_with_unit(self):
        assert _find_quantity("kaos hitam 2 buah", "kaos hitam") == 2

    def test_qty_with_pcs(self):
        assert _find_quantity("kaos hitam 4pcs", "kaos hitam") == 4

    def test_qty_before_x(self):
        assert _find_quantity("3x kaos hitam", "kaos hitam") == 3

    def test_qty_porsi(self):
        assert _find_quantity("nasi goreng 2 porsi", "nasi goreng") == 2


# ---------------------------------------------------------------------------
# extract_items
# ---------------------------------------------------------------------------

CATALOG = [
    {"nama_produk": "Kaos Hitam", "harga": "Rp 50.000"},
    {"nama_produk": "Hoodie Biru", "harga": "150000"},
    {"nama_produk": "Nasi Goreng Spesial", "harga": 35000},
]


class TestExtractItems:
    def test_single_product(self):
        items = extract_items("mau beli kaos hitam 2 pcs", CATALOG)
        assert len(items) == 1
        assert items[0]["product"] == "Kaos Hitam"
        assert items[0]["qty"] == 2
        assert items[0]["price"] == 50000.0

    def test_multiple_products(self):
        items = extract_items("kaos hitam 2 dan hoodie biru 1", CATALOG)
        assert len(items) == 2
        names = {i["product"] for i in items}
        assert "Kaos Hitam" in names
        assert "Hoodie Biru" in names

    def test_no_match(self):
        items = extract_items("mau beli celana jeans", CATALOG)
        assert items == []

    def test_family_match(self):
        catalog = [{"nama_produk": "Kaos Oversize Crop - Hitam - Size L", "harga": 80000}]
        items = extract_items("kaos oversize crop 1", catalog)
        assert len(items) == 1
        assert items[0]["product"] == "Kaos Oversize Crop - Hitam - Size L"
        assert items[0]["qty"] == 1

    def test_qty_default_one_when_not_specified(self):
        items = extract_items("beli kaos hitam", CATALOG)
        assert items[0]["qty"] == 1

    def test_price_from_int_field(self):
        catalog = [{"nama_produk": "Nasi Goreng", "harga": 35000}]
        items = extract_items("nasi goreng 1", catalog)
        assert items[0]["price"] == 35000.0

    def test_longest_name_wins(self):
        """If catalog has 'Kaos' and 'Kaos Oversize Crop', 'kaos oversize crop'
        in the message should match the longer row."""
        catalog = [
            {"nama_produk": "Kaos", "harga": 50000},
            {"nama_produk": "Kaos Oversize Crop", "harga": 80000},
        ]
        items = extract_items("kaos oversize crop 2", catalog)
        assert len(items) == 1
        assert items[0]["product"] == "Kaos Oversize Crop"
        assert items[0]["qty"] == 2

    def test_empty_message(self):
        assert extract_items("", CATALOG) == []

    def test_empty_catalog(self):
        assert extract_items("kaos hitam 2", []) == []


# ---------------------------------------------------------------------------
# extract_buyer_info
# ---------------------------------------------------------------------------

class TestExtractBuyerInfo:
    def test_nama_saya(self):
        name, addr = extract_buyer_info("nama saya Budi Santoso")
        assert name == "Budi Santoso"
        assert addr is None

    def test_nama_aku(self):
        name, addr = extract_buyer_info("nama aku Andi")
        assert name == "Andi"

    def test_atas_nama(self):
        name, addr = extract_buyer_info("atas nama: Rina")
        assert name == "Rina"

    def test_alamat(self):
        name, addr = extract_buyer_info("alamat: Jl. Merdeka No. 10")
        assert addr == "Jl. Merdeka No. 10"

    def test_kirim_ke(self):
        name, addr = extract_buyer_info("kirim ke Jl. Sudirman 25 Jakarta")
        assert addr == "Jl. Sudirman 25 Jakarta"

    def test_both(self):
        name, addr = extract_buyer_info("nama saya Budi, alamat Jl. Merdeka 10")
        assert name == "Budi"
        assert addr == "Jl. Merdeka 10"

    def test_none_when_absent(self):
        name, addr = extract_buyer_info("beli kaos hitam 2")
        assert name is None
        assert addr is None


# ---------------------------------------------------------------------------
# compute_total
# ---------------------------------------------------------------------------

class TestComputeTotal:
    def test_basic(self):
        items = [
            {"product": "Kaos", "qty": 2, "price": 50000},
            {"product": "Hoodie", "qty": 1, "price": 150000},
        ]
        assert compute_total(items) == 250000.0

    def test_no_price(self):
        items = [{"product": "Kaos", "qty": 2, "price": None}]
        assert compute_total(items) is None

    def test_empty(self):
        assert compute_total([]) is None

    def test_mixed_prices(self):
        items = [
            {"product": "Kaos", "qty": 1, "price": 50000},
            {"product": "Hoodie", "qty": 1, "price": None},
        ]
        assert compute_total(items) == 50000.0


# ---------------------------------------------------------------------------
# merge_items (multi-turn order refinement)
# ---------------------------------------------------------------------------

class TestMergeItems:
    def test_merge_empty_base(self):
        assert merge_items([], [{"product": "Kaos", "qty": 2, "price": 50000}]) == [
            {"product": "Kaos", "qty": 2, "price": 50000}
        ]

    def test_append_new_product(self):
        base = [{"product": "Kaos", "qty": 2, "price": 50000}]
        result = merge_items(base, [{"product": "Hoodie", "qty": 1, "price": 150000}])
        assert len(result) == 2

    def test_replace_existing_product_qty(self):
        base = [{"product": "Kaos", "qty": 2, "price": 50000}]
        result = merge_items(base, [{"product": "Kaos", "qty": 3, "price": 50000}])
        assert len(result) == 1
        assert result[0]["qty"] == 3

    def test_empty_additions_keeps_base(self):
        base = [{"product": "Kaos", "qty": 2, "price": 50000}]
        assert merge_items(base, []) == base

    def test_does_not_mutate_base(self):
        base = [{"product": "Kaos", "qty": 2, "price": 50000}]
        merge_items(base, [{"product": "Kaos", "qty": 5, "price": 50000}])
        assert base[0]["qty"] == 2
