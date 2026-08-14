"""Google Sheets client adapter — reads FAQ & Katalog tabs."""
import logging
import os
import re
import time
from threading import Lock
from typing import Any

import gspread

logger = logging.getLogger(__name__)


# Indonesian stopwords filtered out before FAQ scoring. Without this, filler
# words like "kalau", "ya", "kak", "gimana" counted as overlap signal and
# could steal a match from a more meaningful row.
STOPWORDS_ID = frozenset({
    # question words
    "apa", "siapa", "kapan", "dimana", "kemana", "bagaimana", "gimana",
    "kenapa", "mengapa", "apakah", "berapa",
    # pronouns
    "saya", "aku", "kamu", "dia", "kami", "kita", "mereka",
    # auxiliary verbs
    "adalah", "akan", "bisa", "dapat", "harus", "mau", "ingin",
    "punya", "ada", "belum", "sudah", "sedang", "tidak", "nggak",
    "tak", "jangan", "jadi",
    # prepositions / conjunctions
    "di", "ke", "dari", "pada", "untuk", "dengan", "oleh",
    "dan", "atau", "tetapi", "tapi", "karena", "kalau", "kalo",
    "jika", "bila", "saat", "ketika",
    # polite particles (common in WhatsApp)
    "kak", "ya", "ga", "gak", "deh", "sih", "dong",
    "kok", "lho", "lah", "kan", "mah", "ajah",
    # connective / determiner fillers that carry no matching signal
    "yang", "aja", "saja", "nih", "itu", "ini", "toh",
    # generic time
    "sekarang", "nanti", "kemarin", "besok", "hari",
    "minggu", "bulan", "tahun", "tadi",
    # generic nouns / fillers
    "hal", "sesuatu", "semua", "beberapa", "mungkin", "seperti",
    "misalnya", "kira", "kira-kira", "kayaknya",
})

# Minimum overlap ratio for lookup_faq to return a row. 0.3 = at least 1 of 3
# meaningful message words must match. Lower than this risks false positives;
# higher drops short legitimate queries.
FAQ_MATCH_THRESHOLD = 0.3

# --- Flexible tab discovery (multi-tenant onboarding) ---
# Merchants can name their tabs & columns anything they like. We infer the
# intended tab type from tab-name keywords first, then from header keywords.
FAQ_TAB_KEYWORDS = ("faq", "pertanyaan", "qna", "tanya", "question")
CATALOG_TAB_KEYWORDS = (
    "katalog", "catalog", "produk", "product", "menu", "barang", "item", "daftar harga",
)
ONGKIR_TAB_KEYWORDS = ("ongkir", "tarif", "pengiriman", "shipping", "biaya kirim")

# Canonical column name -> accepted aliases (normalized: lowercase, stripped of
# non-alphanumeric). Used to map a merchant's spreadsheet onto the internal
# keys that lookup/embedding code expects.
FAQ_COL_MAP = {
    "pertanyaan": ["pertanyaan", "question", "q", "tanya", "pertanyaann"],
    "jawaban": ["jawaban", "answer", "a", "response", "reply", "respon"],
}
CATALOG_COL_MAP = {
    "nama_produk": ["nama_produk", "nama", "produk", "product", "productname", "item", "barang", "nama product"],
    "harga": ["harga", "price", "hrg", "harga jual"],
    "ready": ["ready", "stok", "stock", "status", "tersedia", "ketersediaan", "stockstatus"],
    "deskripsi": ["deskripsi", "desc", "description", "detail", "keterangan", "kategori"],
    "min_order": ["min_order", "minimal", "minimal_order", "min_porsi", "minimal_porsi", "minimum"],
}
# Columns for the optional "Ongkir" (shipping cost) tab.
ONGKIR_COL_MAP = {
    "wilayah": ["wilayah", "area", "lokasi", "kecamatan", "daerah", "tujuan"],
    "ongkir": ["ongkir", "harga", "biaya", "tarif", "cost", "harga_ongkir"],
    "min_order": ["min_order", "minimal", "minimal_order", "min_porsi", "minimum"],
}

# Values treated as "in stock" for the 'ready' column across merchant sheets.
READY_TRUE_VALUES = frozenset({"y", "yes", "ya", "ada", "ready", "tersedia", "1", "true", "t"})


def _tokenize_meaningful(text: str) -> set[str]:
    """Lowercase, split into words >=3 chars, drop Indonesian stopwords."""
    if not text:
        return set()
    tokens = re.findall(r"\w+", text.lower())
    return {t for t in tokens if len(t) >= 3 and t not in STOPWORDS_ID}


def _score_faq_row(message: str, row: dict) -> float:
    """Overlap ratio: meaningful message words ∩ the row's QUESTION text.

    Returns 0.0 if no meaningful words or no overlap. Range: 0.0 .. ~1.1.

    The QUESTION field is what the buyer's phrasing must match. The ANSWER only
    contributes a small tie-break bonus so a "bahan" question whose answer
    happens to mention "warna" can't outrank the real "warna" question.
    """
    msg_words = _tokenize_meaningful(message)
    if not msg_words:
        return 0.0

    question = str(row.get("pertanyaan") or row.get("text") or "")
    answer = str(row.get("jawaban") or "")

    q_words = _tokenize_meaningful(question)
    if not q_words:
        # No question field (e.g. a catalog row passed as {"text": ...}) — match
        # against the answer/description text instead.
        q_words = _tokenize_meaningful(answer)
        answer = ""

    q_overlap = len(msg_words & q_words) / len(msg_words)

    a_words = _tokenize_meaningful(answer)
    a_overlap = len(msg_words & a_words) / len(msg_words) if a_words else 0.0

    if q_overlap > 0.0:
        # Question overlaps: it dominates; the answer only breaks ties.
        base_score = q_overlap + 0.1 * a_overlap
    else:
        # No question overlap: the answer carries the match (e.g. "tukar size"
        # → question "bisa retur kalau salah ukuran?" whose answer says "bisa
        # tukar size"). Slightly discounted vs a direct question match.
        base_score = 0.9 * a_overlap

    # Score bonus based on question-message similarity
    message_clean = message.lower().strip('?! ')
    question_lower = question.lower().strip('?! ')

    # Exact match (ignoring punctuation) gets highest priority
    if message_clean == question_lower:
        base_score += 0.10  # Extra bonus for exact match
    # Partial prefix match gets moderate bonus
    elif question_lower.startswith(message_clean) or message_clean.startswith(question_lower):
        base_score += 0.05  # Bonus for prefix overlap

    # Don't cap at 1.0 to allow prefix bonus to break ties
    return base_score


def parse_sheet_url(url: str) -> str | None:
    """Extract spreadsheet ID from a Google Sheets share URL.

    Accepts the long share URL and returns the 44-char id, or None if the URL
    isn't a spreadsheet link.
    """
    if not url:
        return None
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else None


def _normalize_header(h: str) -> str:
    """Lowercase and strip punctuation so 'Product Name' == 'product_name'."""
    return re.sub(r"[^a-z0-9]+", "", (h or "").strip().lower())


def _infer_tab_type(title: str, headers: list[str]) -> str:
    """Infer whether a tab is FAQ, catalog, ongkir, or unknown.

    Tab-name keywords win (strong signal, e.g. 'FAQ'), then header keywords.
    """
    t = title.strip().lower()
    for kw in FAQ_TAB_KEYWORDS:
        if kw in t:
            return "faq"
    for kw in CATALOG_TAB_KEYWORDS:
        if kw in t:
            return "catalog"
    for kw in ONGKIR_TAB_KEYWORDS:
        if kw in t:
            return "ongkir"

    norm_headers = {_normalize_header(h) for h in headers}
    faq_cols = {_normalize_header(a) for aliases in FAQ_COL_MAP.values() for a in aliases}
    cat_cols = {_normalize_header(a) for aliases in CATALOG_COL_MAP.values() for a in aliases}
    if norm_headers & faq_cols and norm_headers & cat_cols:
        return "catalog"
    if norm_headers & faq_cols:
        return "faq"
    if norm_headers & cat_cols:
        return "catalog"
    return "unknown"


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
        self._discovered: dict[str, str | None] | None = None

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

                # Get all raw values to handle irregular headers
                raw_rows = worksheet.get_all_values()
                if not raw_rows:
                    self._cache[tab_name] = (now, [])
                    logger.info(
                        "sheets_read_ok",
                        extra={"tab": tab_name, "rows": 0},
                    )
                    return []

                # Use first row as header, skip empty/duplicate headers
                header_row = raw_rows[0]
                # Clean headers: strip whitespace, lowercase (consumers expect
                # 'pertanyaan'/'jawaban'/'ready'/... regardless of sheet case),
                # remove empty ones, make unique.
                headers = []
                seen = set()
                for h in header_row:
                    clean_h = (h or "").strip().lower()
                    if clean_h and clean_h not in seen:
                        headers.append(clean_h)
                        seen.add(clean_h)

                # If no valid headers, use positional access (index-based)
                if not headers:
                    headers = [f"col_{i}" for i in range(len(raw_rows[0]))]

                # Convert rows to dict list
                rows_list = []
                for row in raw_rows[1:]:
                    row_dict = {}
                    for i, val in enumerate(row):
                        if i < len(headers):
                            row_dict[headers[i]] = val
                        else:
                            # Extra columns beyond headers, store as col_n
                            row_dict[f"col_{i}"] = val
                    rows_list.append(row_dict)

                self._cache[tab_name] = (now, rows_list)
                logger.info(
                    "sheets_read_ok",
                    extra={"tab": tab_name, "rows": len(rows_list)},
                )
                return rows_list
            except Exception as e:
                raise SheetsError(f"Failed to read tab {tab_name}: {e}") from e

    def discover_tabs(self) -> list[dict]:
        """Scan every worksheet and report its inferred type + headers.

        Returns a list of dicts:
          {title, inferred_type ('faq'|'catalog'|'unknown'), headers, row_count}
        Discovery result is cached so provisioning & lookups stay cheap.
        """
        if self._discovered is not None:
            return self._discovered

        sheet = self._get_spreadsheet()
        found: list[dict] = []
        for ws in sheet.worksheets():
            raw = ws.get_all_values()
            headers = [h for h in (raw[0] if raw else []) if h]
            row_count = max(0, len(raw) - 1) if raw else 0
            found.append({
                "title": ws.title,
                "inferred_type": _infer_tab_type(ws.title, headers),
                "headers": headers,
                "row_count": row_count,
            })
        self._discovered = found
        return found

    def find_tab(self, kind: str) -> str | None:
        """Return the worksheet title for kind ('faq'|'catalog'), or None."""
        for tab in self.discover_tabs():
            if tab["inferred_type"] == kind:
                return tab["title"]
        return None

    @staticmethod
    def _canonicalize_row(row: dict, col_map: dict) -> dict:
        """Rename a row's alias columns to canonical keys.

        Example: {'Question': 'Harga?', 'Answer': 'Rp50k'}
          -> {'pertanyaan': 'Harga?', 'jawaban': 'Rp50k'}
        Non-mapped columns are passed through untouched.
        """
        lookup: dict[str, str] = {}
        for canonical, aliases in col_map.items():
            for a in aliases:
                lookup[_normalize_header(a)] = canonical
        out: dict = {}
        for k, v in row.items():
            canonical = lookup.get(_normalize_header(str(k)), k)
            out[canonical] = v
        return out

    def read_faq(self) -> list[dict[str, str]]:
        tab = self.find_tab("faq") or "FAQ"
        return [
            self._canonicalize_row(r, FAQ_COL_MAP)
            for r in self._read_tab(tab)
        ]

    def read_catalog(self) -> list[dict[str, str]]:
        tab = self.find_tab("catalog") or "Katalog"
        return [
            self._canonicalize_row(r, CATALOG_COL_MAP)
            for r in self._read_tab(tab)
        ]

    def read_ongkir(self) -> list[dict[str, str]]:
        """Read the optional 'Ongkir' tab (shipping cost per wilayah/kecamatan).

        Returns [{wilayah, ongkir, min_order}] canonicalized via ONGKIR_COL_MAP,
        or [] when no ongkir tab exists. Used by catering rules to add shipping
        cost + area minimums to a quote.
        """
        tab = self.find_tab("ongkir")
        if tab is None:
            return []
        return [
            self._canonicalize_row(r, ONGKIR_COL_MAP)
            for r in self._read_tab(tab)
        ]

    def list_ready_products(self) -> list[dict[str, str]]:
        """Return catalog rows where ready indicates in-stock (case-insensitive)."""
        return [
            r for r in self.read_catalog()
            if (r.get("ready") or "").strip().lower() in READY_TRUE_VALUES
        ]

    def lookup_faq(self, message: str) -> dict[str, str] | None:
        """Score every FAQ row and return the best above FAQ_MATCH_THRESHOLD.

        Replaces the previous first-match binary logic which could return a row
        with 1-word overlap while a more relevant row with 3-word overlap sat
        below it in the sheet. Iterates through the cached FAQ list, scores
        each row, and returns the row with the highest overlap whose score
        meets the threshold. On a tie, the row with shorter question text wins
        (more specific match).
        """
        if not message or not message.strip():
            return None

        best_row: dict[str, str] | None = None
        best_score = 0.0
        # Scan in reverse order so newer entries win on tie (last matching row wins)
        for row in reversed(self.read_faq()):
            score = _score_faq_row(message, row)
            if score > best_score:
                best_score = score
                best_row = row
        if best_score < FAQ_MATCH_THRESHOLD:
            return None
        return best_row

    def clear_cache(self) -> None:
        """Test helper: clear the cache."""
        with self._lock:
            self._cache.clear()
        self._discovered = None


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