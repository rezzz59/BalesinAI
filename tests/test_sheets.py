"""Tests for app.services.sheets."""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.services.sheets import GoogleSheetsClient, SheetsError


@pytest.fixture
def client(tmp_path):
    creds_path = tmp_path / "creds.json"
    creds_path.write_text("{}")
    return GoogleSheetsClient(
        credentials_json_path=str(creds_path),
        spreadsheet_id="sheet-abc",
    )


@contextmanager
def patch_object_gspread(mock_worksheet):
    with patch("app.services.sheets.gspread") as mock_gspread:
        mock_client = MagicMock()
        mock_sheet = MagicMock()
        mock_sheet.worksheet = MagicMock(return_value=mock_worksheet)
        mock_client.open_by_key = MagicMock(return_value=mock_sheet)
        mock_gspread.service_account = MagicMock(return_value=mock_client)
        yield


def test_read_faq_returns_rows(client):
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[
            {"pertanyaan": "Harga?", "jawaban": "Rp 50.000"},
            {"pertanyaan": "Warna?", "jawaban": "Merah, Biru"},
        ]
    )

    with patch_object_gspread(mock_worksheet):
        client.clear_cache()
        rows = client.read_faq()
        assert len(rows) == 2
        assert rows[0]["pertanyaan"] == "Harga?"


def test_read_catalog_returns_rows(client):
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[
            {"nama_produk": "Kaos Polos", "harga": "50000", "ready": "Y", "deskripsi": "100% katun"},
        ]
    )

    with patch_object_gspread(mock_worksheet):
        client.clear_cache()
        rows = client.read_catalog()
        assert len(rows) == 1
        assert rows[0]["nama_produk"] == "Kaos Polos"


def test_lookup_faq_finds_match(client):
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[
            {"pertanyaan": "Berapa harga?", "jawaban": "Mulai Rp 50.000"},
            {"pertanyaan": "Ada warna merah?", "jawaban": "Ada, Ready stock"},
        ]
    )

    with patch_object_gspread(mock_worksheet):
        client.clear_cache()
        match = client.lookup_faq("harga berapa")
        assert match is not None
        assert "Rp 50.000" in match["jawaban"]


def test_lookup_faq_no_match_returns_none(client):
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[{"pertanyaan": "Halo", "jawaban": "Hai juga"}]
    )

    with patch_object_gspread(mock_worksheet):
        client.clear_cache()
        match = client.lookup_faq("xyzzy")
        assert match is None


def test_60s_cache_avoids_recalling_api(client):
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[{"pertanyaan": "Halo", "jawaban": "Hai"}]
    )

    with patch_object_gspread(mock_worksheet):
        client._cache_ttl_seconds = 60
        client.clear_cache()

        # First call
        client.read_faq()
        # Second call within TTL — should NOT call get_all_records again
        client.read_faq()

        # get_all_records only called once due to cache
        assert mock_worksheet.get_all_records.call_count == 1


def test_lookup_faq_picks_highest_scoring_match(client):
    """Regression: 'kalau salah ukuran gimana ya?' must return retur policy, not size chart.

    Before scoring was introduced, the first-match binary returned the size
    chart row because "gimana" overlapped — even though the retur policy
    row had a 3-word overlap (kalau/salah/ukuran).
    """
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[
            {"pertanyaan": "Berapa harga?", "jawaban": "Mulai Rp 50.000"},
            {"pertanyaan": "Ukuran kaosnya gimana?", "jawaban": "S M L XL"},
            {"pertanyaan": "Bisa retur kalau salah ukuran?", "jawaban": "Bisa tukar size"},
        ]
    )

    with patch_object_gspread(mock_worksheet):
        client.clear_cache()
        match = client.lookup_faq("kalau salah ukuran gimana ya?")
        assert match is not None
        assert "tukar size" in match["jawaban"]


def test_lookup_faq_filters_stopwords(client):
    """Stopwords (kalau, gimana, ya, kak) must not count as overlap signal."""
    from app.services.sheets import STOPWORDS_ID

    assert "kalau" in STOPWORDS_ID
    assert "ya" in STOPWORDS_ID
    assert "kak" in STOPWORDS_ID
    assert "gimana" in STOPWORDS_ID

    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[
            {"pertanyaan": "Bisa retur kalau salah ukuran?", "jawaban": "Bisa tukar size"},
        ]
    )

    with patch_object_gspread(mock_worksheet):
        client.clear_cache()
        # Message has only stopwords → no meaningful tokens → no match.
        match = client.lookup_faq("kak gimana ya kak")
        assert match is None


def test_lookup_faq_returns_none_when_no_meaningful_words(client):
    """A message that's only stopwords/punctuation must produce no match."""
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[{"pertanyaan": "Apa kabar?", "jawaban": "Baik"}]
    )

    with patch_object_gspread(mock_worksheet):
        client.clear_cache()
        match = client.lookup_faq("kak gimana ya kak")
        assert match is None


def test_lookup_faq_returns_none_for_empty_message(client):
    """Empty/whitespace message is treated as no query."""
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[{"pertanyaan": "Apa kabar?", "jawaban": "Baik"}]
    )

    with patch_object_gspread(mock_worksheet):
        client.clear_cache()
        assert client.lookup_faq("") is None
        assert client.lookup_faq("   ") is None


def test_score_faq_row_returns_zero_for_no_overlap():
    from app.services.sheets import _score_faq_row

    row = {"pertanyaan": "Berapa ongkir?", "jawaban": "Rp 10.000"}
    # "kaos", "oversize", "ready" all stopwords-free but don't appear in row.
    assert _score_faq_row("kaos oversize ready ga?", row) == 0.0


def test_score_faq_row_handles_question_and_answer():
    """Score should consider both pertanyaan and jawaban fields."""
    from app.services.sheets import _score_faq_row

    row = {
        "pertanyaan": "Bisa retur?",
        "jawaban": "Bisa, ongkir retur ditanggung pembeli",
    }
    # "ongkir" and "retur" both appear in jawaban — but "bisa" is a stopword
    # so message meaningful tokens are {"ongkir", "retur"} (2). Both overlap.
    score = _score_faq_row("ongkir retur", row)
    assert score == 1.0


def test_score_faq_row_treats_punctuation_consistently():
    """Punctuation like '?' or '.' shouldn't break tokenization."""
    from app.services.sheets import _score_faq_row

    row = {"pertanyaan": "Berapa harga?", "jawaban": "Rp 50.000"}
    # 'harga' appears; 'berapa' is a stopword. score = 1/1 = 1.0
    score = _score_faq_row("harga?", row)
    assert score == 1.0