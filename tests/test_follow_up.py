"""Tests for ghosting follow-up touchpoint scheduling."""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from send_follow_ups import _due_touchpoint, _in_send_window, _match_product, _produk  # noqa: E402

WIB = ZoneInfo("Asia/Jakarta")


def test_below_24h_nothing():
    assert _due_touchpoint(5, 0) == 0
    assert _due_touchpoint(23.9, 0) == 0


def test_touchpoint1_at_24h():
    assert _due_touchpoint(24, 0) == 1
    assert _due_touchpoint(71, 0) == 1


def test_touchpoint2_at_72h():
    assert _due_touchpoint(72, 1) == 2
    assert _due_touchpoint(143, 1) == 2


def test_touchpoint3_at_144h_soft_exit():
    assert _due_touchpoint(144, 2) == 3
    assert _due_touchpoint(999, 2) == 3


def test_done_after_soft_exit():
    assert _due_touchpoint(999, 3) == 0


def test_not_due_until_previous_touchpoint_sent():
    assert _due_touchpoint(100, 0) == 1  # still TP1 until TP1 was sent
    assert _due_touchpoint(100, 1) == 2
    assert _due_touchpoint(100, 2) == 0  # 100h < 144h → not TP3 yet


def test_send_window_only_primetime():
    assert _in_send_window(datetime(2026, 8, 10, 10, 0, tzinfo=WIB)) is True
    assert _in_send_window(datetime(2026, 8, 10, 11, 59, tzinfo=WIB)) is True
    assert _in_send_window(datetime(2026, 8, 10, 18, 0, tzinfo=WIB)) is True
    assert _in_send_window(datetime(2026, 8, 10, 20, 59, tzinfo=WIB)) is True
    assert _in_send_window(datetime(2026, 8, 10, 2, 0, tzinfo=WIB)) is False
    assert _in_send_window(datetime(2026, 8, 10, 12, 0, tzinfo=WIB)) is False
    assert _in_send_window(datetime(2026, 8, 10, 21, 0, tzinfo=WIB)) is False


def test_match_product_substring():
    assert _match_product(["Hoodie Fleece", "Kaos Hitam"], "ada kaos hitam ukuran L?") == "Kaos Hitam"
    assert _match_product(["Hoodie Fleece"], "berapa harga hoodie fleece?") == "Hoodie Fleece"
    assert _match_product(["Hoodie Fleece"], "ongkir berapa?") == ""


def test_produk_phrasing():
    assert _produk(1, "Hoodie") == "produk Hoodie"
    assert _produk(1, "") == "menu/produk ini"
    assert _produk(2, "") == "pesanan"
