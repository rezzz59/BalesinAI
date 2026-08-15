"""Order extraction — turn a confirm_order buyer message into structured order data.

Deterministic, catalog-driven parsing (no LLM in the hot path): match product
names from the catalog to words in the message, sniff a quantity (e.g. "2 pcs",
"3", "x4"), and pull the unit price straight from the catalog row so totals are
never hallucinated. Also does a light best-effort pull of buyer name/address
from common Indonesian order phrasings.
"""
import re
from typing import Any

# Common Indonesian quantity markers. "pcs"/"unit"/"orang" must follow a number;
# a bare number before/after the product name is also accepted.
_QTY_PATTERN = re.compile(r"(\d{1,3})\s*(?:pcs|unit|buah|biji|lembar|orang|pack|paket|botol|cup|kotak|porsi|kg|gr|liter|l)\b", re.IGNORECASE)
_XQTY_PATTERN = re.compile(r"x\s*(\d{1,3})\b", re.IGNORECASE)
_XQTY_REV_PATTERN = re.compile(r"(\d{1,3})\s*x\b", re.IGNORECASE)
# "3 (kaos)" / "(kaos) 3" — bare number immediately adjacent to the product token.
_BARE_QTY = re.compile(r"(?:^|\s)(\d{1,3})(?=\s*(?:x\s*)?{name}\b)|(?:^|\s){name}\s*x?\s*(\d{1,3})(?=\s|$)", re.IGNORECASE)

_NAME_PATTERNS = [
    re.compile(r"(?:nama\s*(?:saya|aku)?|atas\s+nama|\ba\.?n\.?)\s*:?\s*([A-Za-z][A-Za-z.\s]{1,49})"),
    re.compile(r"(?:untuk\s+|buat\s+)([A-Za-z][A-Za-z.\s]{1,49})$"),
]
_ADDRESS_PATTERNS = [
    re.compile(r"(?:alamat|kirim\s+ke|di\s+kirim\s+ke|antar\s+ke|lokasi)\s*:?\s*(.{3,90})"),
]

# Tokens that carry no product signal when matching buyer phrasing to catalog
# names (order verbs, polite filler, quantity units, attribute labels).
_STOP_TOKENS = {
    "saya", "aku", "mau", "beli", "pesan", "order", "ya", "kak", "dong", "tolong",
    "lagi", "pcs", "porsi", "buah", "biji", "unit", "orang", "buat", "untuk",
    "warna", "ukuran", "size", "kotak", "paket", "saja", "dong", "gimana", "berapa",
}
# Attribute tokens that must NOT be consumed as product words (size/color labels).
_ATTR_TOKENS = {"hitam", "putih", "navy", "biru", "merah", "abu", "krem", "coklat",
                "cokelat", "hijau", "ungu", "pink", "cream", "maroon", "kuning",
                "orange", "s", "m", "l", "xl", "xxl", "xxxl", "xs"}

_SIZE_TOKENS = {"xs", "s", "m", "l", "xl", "xxl", "xxxl"}
_SIZE_RE = re.compile(r"\b(?:size|ukuran|sz)\s*[:=]?\s*(xxxl|xxl|xl|l|m|s|xs)\b", re.IGNORECASE)
_COLORS = ("hitam", "putih", "navy", "biru", "merah", "abu", "krem", "coklat",
           "cokelat", "hijau", "ungu", "pink", "cream", "maroon", "kuning", "orange", "toska")


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _parse_price(raw: Any) -> float | None:
    """Parse a catalog price value (int, "50000", "Rp 50.000") to a float.

    Returns None when the value cannot be parsed. `harga` in sheets is usually
    a number; some merchants store "Rp 50.000" text.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = re.sub(r"\s+", "", str(raw))
    s = re.sub(r"^(rp|idr)\s*", "", s, flags=re.IGNORECASE)
    s = s.replace(".", "").replace(",", "")
    if not s.isdigit():
        return None
    return float(s)


def _find_quantity(message: str, product_name: str) -> int:
    """Best-effort quantity for a product mentioned in the message. Default 1."""
    m = _QTY_PATTERN.search(message)
    if m:
        return int(m.group(1))
    m = _XQTY_PATTERN.search(message)
    if m:
        return int(m.group(1))
    m = _XQTY_REV_PATTERN.search(message)
    if m:
        return int(m.group(1))
    name = re.escape(product_name)
    # "kaos oversize crop 2" — number after product
    m = re.search(name + r"[^0-9]{0,5}(\d{1,3})", message, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    # "2 kaos hitam" — number before product
    m = re.search(r"(\d{1,3})[^a-z]{0,5}" + name, message, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Token fallback (partial/phrase matches): qty adjacent to a meaningful
    # token of the product name, e.g. "2 kaos" in "mau beli 2 kaos oversize
    # hitam" matching "Kaos Oversize Cotton - Hitam".
    for token in sorted(_name_tokens(_normalize(product_name)), key=len, reverse=True):
        m = re.search(r"(\d{1,3})[^a-z]{0,4}" + re.escape(token), message, flags=re.IGNORECASE)
        if m:
            return int(m.group(1))
        m = re.search(re.escape(token) + r"[^0-9]{0,4}(\d{1,3})", message, flags=re.IGNORECASE)
        if m:
            return int(m.group(1))
    # Bare trailing number ("kaos hitam L 2" -> 2).
    m = re.search(r"\b(\d{1,3})\s*$", message)
    if m:
        return int(m.group(1))
    return 1


def _match_products(message: str, catalog: list[dict]) -> list[dict]:
    """Return catalog rows whose product name appears in the message.

    Matches on whole product name OR the product family (text before the first
    " - "), so "kaos oversize crop - hitam" matches a catalog row named
    "Kaos Oversize Crop - Hitam - Size L" via its family "Kaos Oversize Crop".
    Each row is only claimed once, longest-name-first so "Kaos Oversize Crop"
    wins over a bare "Kaos".

    When no exact/family match is found, falls back to token-overlap scoring so
    buyer phrasing like "kaos oversize hitam" matches a catalog row named
    "Kaos Oversize Cotton - Hitam" (shared tokens: kaos, oversize, hitam).
    """
    msg = _normalize(message)
    if not msg:
        return []
    rows = sorted(
        [r for r in catalog if (r.get("nama_produk") or "").strip()],
        key=lambda r: len(r.get("nama_produk", "")),
        reverse=True,
    )
    claimed: set[str] = set()
    matched: list[dict] = []
    for row in rows:
        name = row["nama_produk"].strip()
        family = _normalize(name.split(" - ")[0].strip())
        key = _normalize(name)
        if key in claimed:
            continue
        # If this product's family or name is already subsumed by a longer
        # claimed family/name, skip it so e.g. "kaos" doesn't also match
        # when "kaos oversize crop" is already claimed.
        if any(key in c or (family and family in c) for c in claimed):
            continue
        if key and key in msg:
            claimed.add(key)
            matched.append(row)
        elif family and family in msg and len(family) >= 3:
            # Family match — claim the family so a generic "kaos" doesn't also claim it.
            claimed.add(family)
            matched.append(_best_variant(rows, family, msg))

    # Token-overlap fallback for unmatched messages (partial phrasing).
    if not matched:
        msg_tokens = _name_tokens(msg)
        msg_color_terms = _msg_color_terms(rows, msg)
        msg_size = (extract_size_color(msg)[0] or "").lower()
        if msg_tokens:
            def _score_row(row: dict) -> float | None:
                name = row["nama_produk"].strip()
                key = _normalize(name)
                if key in claimed:
                    return None
                name_tokens = _name_tokens(_normalize(name.split(" - ")[0]))
                if not name_tokens:
                    return None
                # Narrow to the buyer's named color/size when variants exist for it.
                if msg_color_terms and not (_row_color_terms(name) & msg_color_terms):
                    return None
                if msg_size and msg_size not in set(_normalize(name).split()):
                    return None
                overlap = len(msg_tokens & name_tokens)
                score = overlap / len(name_tokens)
                # Color/size already pinned the variant family — a bare token
                # like "jogger" (1/3 vs "Jogger Pants Cotton") is enough.
                min_score = 1 / max(len(name_tokens), 1) if (msg_color_terms or msg_size) else 0.5
                if overlap >= 1 and score >= min_score:
                    return score
                return None

            scored = []
            for idx, row in enumerate(rows):
                s = _score_row(row)
                if s is not None:
                    scored.append((s, -idx, row))
            # Color/size filters can over-reject catalogs that store variants in
            # the description (e.g. "size M-XXL"). If the filters left nothing,
            # retry without them so a plain family-token match still wins.
            if not scored:
                for idx, row in enumerate(rows):
                    name = row["nama_produk"].strip()
                    key = _normalize(name)
                    if key in claimed:
                        continue
                    name_tokens = _name_tokens(_normalize(name.split(" - ")[0]))
                    if not name_tokens:
                        continue
                    overlap = len(msg_tokens & name_tokens)
                    score = overlap / len(name_tokens)
                    if overlap >= 1 and score >= 0.5:
                        scored.append((score, -idx, row))
            # Pick the best-scoring variant per DISTINCT family. A bare
            # "kaos hitam" names one intent → one family; with an explicit
            # connector ("kaos ... dan hoodie ...") each family yields one item.
            best_by_family: dict[str, tuple[float, int, dict]] = {}
            for score, neg_idx, row in sorted(scored, key=lambda t: (t[0], t[1]), reverse=True):
                family = _normalize(row["nama_produk"].strip().split(" - ")[0])
                if family not in best_by_family:
                    best_by_family[family] = (score, neg_idx, row)
            for _, _, row in sorted(best_by_family.values(), key=lambda t: (t[0], t[1]), reverse=True):
                key = _normalize(row["nama_produk"].strip())
                if key in claimed:
                    continue
                claimed.add(key)
                matched.append(row)
                if not _has_item_connector(msg):
                    break
    return matched


_ITEM_CONNECTOR = re.compile(r"\b(dan|sama|plus|sekalian|serta|&)\b", re.IGNORECASE)


def _has_item_connector(message: str) -> bool:
    """True when the message lists multiple items with an explicit connector."""
    return bool(_ITEM_CONNECTOR.search(message or ""))


def _name_tokens(text: str) -> set[str]:
    """Meaningful tokens in a product name/phrase (stopwords and pure
    size/color/attribute labels excluded so they can't over-match)."""
    tokens = {w for w in re.findall(r"[a-z0-9]{2,}", text)}
    return {t for t in tokens if t not in _STOP_TOKENS and t not in _ATTR_TOKENS}


def _row_color_terms(name: str) -> set[str]:
    """Color tokens in a catalog row name.

    Handles three naming conventions:
      - "Family - Color - Size X"     (middle segment, e.g. "Sage Green")
      - "Family Warna Hitam - Size M" (color inline after "warna")
      - fixed Indonesian color words anywhere as standalone tokens

    The middle segment is only read as color when it's short (a color phrase is
    1-3 words); a long description segment ("baju kaos pria wanita ... cotton")
    is not a color.
    """
    norm = _normalize(name)
    terms: set[str] = set()
    parts = norm.split(" - ")
    if len(parts) >= 3 and 1 <= len(parts[1].split()) <= 3:
        terms |= set(parts[1].split())
    for m in re.finditer(r"warna\s+([a-z]+(?:\s+[a-z]+)?)", norm):
        terms.update(m.group(1).split())
    for c in _COLORS:
        if re.search(rf"\b{c}\b", norm):
            terms.add(c)
    return terms


def _msg_color_terms(rows: list[dict], msg: str) -> set[str]:
    """Color tokens named in *msg*, from the catalog's own color labels plus the
    fixed _COLORS list.

    Handles compound colors like "dusty pink"/"sage green" that aren't in the
    fixed _COLORS list: any catalog color term that appears (even inside a
    joined token like "dustypink") is treated as named in the message.
    """
    msg = _normalize(msg)
    if not msg:
        return set()
    known = set()
    for r in rows:
        known |= _row_color_terms(r.get("nama_produk") or "")
    for c in _COLORS:
        if re.search(rf"\b{c}\b", msg):
            known.add(c)
    return {t for t in known if t in msg}


def _best_variant(rows: list[dict], family: str, msg: str) -> dict:
    """Pick the variant of *family* that best matches the color/size the buyer
    mentioned in *msg*; fall back to the first (longest-name) row.

    The catalog lists variants as "Family - Color - Size X". When the message
    says "kaos oversize crop hitam size L", the plain family match would grab
    whatever variant sorts first (wrong color/size). Score every sibling by
    color-then-size overlap with the message and take the best.
    """
    msg = _normalize(msg)
    msg_terms = set(msg.split())
    msg_color_terms = _msg_color_terms(rows, msg)
    msg_size = (extract_size_color(msg)[0] or "").lower()
    candidates = [
        r for r in rows
        if (r.get("nama_produk") or "").strip().split(" - ")[0].strip().lower() == family
    ] or [rows[0]]
    best, best_score = candidates[0], (-1, -1)
    for r in candidates:
        name_terms = set(_normalize(r.get("nama_produk", "")).split())
        c_score = len(name_terms & msg_color_terms)
        s_score = 1 if msg_size and msg_size in name_terms else 0
        if (c_score, s_score) > best_score:
            best, best_score = r, (c_score, s_score)
    return best


def extract_size_color(message: str) -> tuple[str | None, str | None]:
    """Pull (size, color) from a free-text order message.

    Size accepts "size L", "ukuran M", "sz xxl". Color matches a known
    Indonesian color word anywhere in the message ("warna navy", "kaos hitam").
    Returns (None, None) when absent.
    """
    size = None
    m = _SIZE_RE.search(message or "")
    if m:
        size = m.group(1).upper()
    else:
        # Bare size token without "size"/"ukuran" prefix ("kaos hitam L 2").
        # Whole-word only; single letters are size intent in an order message.
        m = re.search(r"\b(XXXL|XXL|XL|XS|[SML])\b", message or "", re.IGNORECASE)
        if m:
            size = m.group(1).upper()
    color = None
    lower = (message or "").lower()
    for c in _COLORS:
        if re.search(rf"\b{c}\b", lower):
            color = c
            break
    return size, color


def extract_items(message: str, catalog: list[dict]) -> list[dict]:
    """Extract [{product, qty, price, size, color}] from a confirm_order message.

    price is the catalog's unit price (float) or None when unparseable; qty
    defaults to 1; size/color are best-effort from the message text. If no
    catalog row matches, returns [] (caller decides the fallback reply).
    """
    items: list[dict] = []
    size, color = extract_size_color(message)
    for row in _match_products(message, catalog):
        name = (row.get("nama_produk") or "").strip()
        qty = _find_quantity(message, name)
        price = _parse_price(row.get("harga"))
        items.append({
            "product": name, "qty": qty, "price": price, "size": size, "color": color,
            "min_order": row.get("min_order") or "",
        })
    return items


def extract_buyer_info(message: str) -> tuple[str | None, str | None]:
    """Best-effort (name, address) from a confirm_order message. Both optional."""
    name: str | None = None
    for pat in _NAME_PATTERNS:
        m = pat.search(message)
        if m and m.group(1).strip():
            name = m.group(1).strip().rstrip(".")
            break
    address: str | None = None
    for pat in _ADDRESS_PATTERNS:
        m = pat.search(message)
        if m and m.group(1).strip():
            address = m.group(1).strip().rstrip(".")
            break
    return name, address


def merge_items(base: list[dict], additions: list[dict]) -> list[dict]:
    """Merge a set of extracted items into a running order draft.

    For each addition, if a row with the same product already exists in the
    draft, its qty is replaced by the new qty; otherwise it is appended. This
    lets a buyer refine an order across turns ("tambah hoodie 1", "jadi 3
    hoodie") without duplicating lines.
    """
    draft = [dict(i) for i in (base or [])]
    for add in additions:
        product = add.get("product")
        replaced = False
        for i, existing in enumerate(draft):
            if existing.get("product") == product:
                draft[i]["qty"] = int(add["qty"])
                draft[i]["price"] = add.get("price")
                replaced = True
                break
        if not replaced:
            draft.append(dict(add))
    return draft


def compute_total(items: list[dict]) -> float | None:
    """Sum qty*price over items with a known price; None if nothing is priced."""
    priced = [i for i in items if i.get("price") is not None]
    if not priced:
        return None
    return round(sum(i["qty"] * i["price"] for i in priced), 2)
