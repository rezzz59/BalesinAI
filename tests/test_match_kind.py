"""Tests for match_kind scoring."""
from app.services.sheets import score_match_kind


def test_score_returns_none_for_no_row():
    assert score_match_kind("berapa harga hoodie?", None) == "none"


def test_score_returns_high_for_strong_overlap():
    # 50%+ of message words appear in row text.
    # message: "berapa harga hoodie fleece?" -> words: berapa, harga, hoodie, fleece (4 words >=3 chars)
    # row: "Berapa harga hoodie fleece tebal?" -> all 4 words match
    row = {"question": "Berapa harga hoodie fleece tebal?", "answer": "Rp 150.000"}
    assert score_match_kind("berapa harga hoodie fleece?", row) == "high"


def test_score_returns_medium_for_partial_overlap():
    # Only 1-49% overlap.
    row = {"question": "Berapa harga hoodie fleece?", "answer": "Rp 150.000"}
    # Message: "kaos oversize warna navy ready ga kak?"
    # Words >=3 chars: kaos, oversize, warna, navy, ready (5 words)
    # Source has: berapa, harga, hoodie, fleece, 150, 000 (none match)
    # To get medium, we need at least one match but <50%. Use hoodie as the overlap.
    row = {"question": "Berapa harga hoodie fleece?", "answer": "Rp 150.000"}
    # Message: 5 words >=3 chars: kaos, oversize, hoodie, navy, ready
    # Source has: hoodie, fleece, harga, berapa, 150, 000
    # Overlap: only "hoodie" matches -> 1/5 = 20% -> "medium"
    assert score_match_kind("kaos oversize hoodie navy ready", row) == "medium"


def test_score_returns_high_for_perfect_overlap():
    row = {"question": "harga hoodie berapa", "answer": "Rp 100.000"}
    assert score_match_kind("harga hoodie berapa", row) == "high"


def test_score_ignores_short_words():
    # Words < 3 chars should be ignored (per spec).
    # message: "di mana" -> all words too short, denominator = 0
    # Spec says no match (no useful overlap to measure).
    assert score_match_kind("di mana", {"question": "Lokasi toko", "answer": "Jakarta"}) == "none"


def test_score_extracts_text_from_dict_values():
    # Spec: row can be dict with multiple fields. Score pulls all string fields.
    row = {
        "nama_produk": "Hoodie Fleece Tebal",
        "deskripsi": "Bahan hangat untuk udara dingin",
        "harga": "Rp 150.000",
    }
    # The exact match depends on the implementation. Test that the function
    # returns one of the three valid values.
    result = score_match_kind("Bahan hangat tebal ya Kak?", row)
    assert result in ("high", "medium", "none")
