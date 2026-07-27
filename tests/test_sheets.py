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