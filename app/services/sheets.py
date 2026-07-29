"""Google Sheets client adapter — reads FAQ & Katalog tabs."""
import logging
import os
import re
import time
from threading import Lock
from typing import Any

import gspread

logger = logging.getLogger(__name__)


class SheetsError(Exception):
    """Raised when Sheets API call fails."""


class GoogleSheetsClient:
    """Reads FAQ and Katalog tabs from a tenant's Google Sheet.

    Caches reads for 60 seconds per tab to avoid rate limits.
    """

    CACHE_TTL_SECONDS = 60

    def __init__(self, credentials_json_path: str, spreadsheet_id: str):
        self.credentials_json_path = credentials_json_path
        self.spreadsheet_id = spreadsheet_id
        self._client: Any = None
        self._spreadsheet: Any = None
        self._cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
        self._lock = Lock()

    def _get_spreadsheet(self):
        if self._spreadsheet is None:
            try:
                if not self.credentials_json_path:
                    raise SheetsError("Credentials path is empty")
                if not os.path.isfile(self.credentials_json_path):
                    raise SheetsError(
                        f"Credentials file not found: {self.credentials_json_path}"
                    )
                gc = gspread.service_account(filename=self.credentials_json_path)
                self._spreadsheet = gc.open_by_key(self.spreadsheet_id)
            except Exception as e:
                raise SheetsError(f"Failed to open sheet: {e}") from e
        return self._spreadsheet

    def _read_tab(self, tab_name: str) -> list[dict[str, str]]:
        """Read a tab with caching."""
        with self._lock:
            now = time.time()
            cached = self._cache.get(tab_name)
            if cached and (now - cached[0]) < self.CACHE_TTL_SECONDS:
                logger.debug("sheets_cache_hit", extra={"tab": tab_name})
                return cached[1]

            try:
                sheet = self._get_spreadsheet()
                worksheet = sheet.worksheet(tab_name)
                rows = worksheet.get_all_records()
                rows_list = [dict(r) for r in rows]
                self._cache[tab_name] = (now, rows_list)
                logger.info(
                    "sheets_read_ok",
                    extra={"tab": tab_name, "rows": len(rows_list)},
                )
                return rows_list
            except Exception as e:
                raise SheetsError(f"Failed to read tab {tab_name}: {e}") from e

    def read_faq(self) -> list[dict[str, str]]:
        return self._read_tab("FAQ")

    def read_catalog(self) -> list[dict[str, str]]:
        return self._read_tab("Katalog")

    def list_ready_products(self) -> list[dict[str, str]]:
        """Return catalog rows where ready == 'Y' (case-insensitive)."""
        return [
            r for r in self.read_catalog()
            if (r.get("ready") or "").strip().upper() == "Y"
        ]

    def lookup_faq(self, message: str) -> dict[str, str] | None:
        """Simple keyword lookup. Returns first row whose 'pertanyaan' contains message keywords."""
        message_lower = message.lower()
        words = [w for w in message_lower.split() if len(w) >= 3]
        if not words:
            return None

        for row in self.read_faq():
            pertanyaan = (row.get("pertanyaan") or "").lower()
            if any(w in pertanyaan for w in words):
                return row
        return None

    def clear_cache(self) -> None:
        """Test helper: clear the cache."""
        with self._lock:
            self._cache.clear()


def score_match_kind(message: str, row: dict | None) -> str:
    """Score the match between a buyer message and a catalog row.

    Args:
      message: buyer's WhatsApp message.
      row: matched FAQ/product row as dict, or None.

    Returns:
      'high' if >=50% of message words (>=3 chars) appear in row.
      'medium' if 1-49% appear.
      'none' if no row, no overlap, or all words are too short to measure.
    """
    if row is None:
        return "none"

    # Build source text from all string fields of the row.
    source_text = " ".join(str(v) for v in row.values() if v is not None).lower()

    # Tokenize message - words >=3 chars, lowercased.
    msg_words = [w for w in re.findall(r"\w+", (message or "").lower()) if len(w) >= 3]
    if not msg_words:
        return "none"

    # Count how many message words appear in source text.
    overlap = sum(1 for w in msg_words if w in source_text)
    ratio = overlap / len(msg_words)

    if ratio >= 0.5:
        return "high"
    if overlap > 0:
        return "medium"
    return "none"