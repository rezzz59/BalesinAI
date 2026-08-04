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
    re.compile(r"(?:nama\s*(?:saya|aku)?|atas\s+nama|a\.?n\.?)\s*:?\s*([A-Za-z][A-Za-z.\s]{1,49})"),
    re.compile(r"(?:untuk\s+|buat\s+)([A-Za-z][A-Za-z.\s]{1,49})$"),
]
_ADDRESS_PATTERNS = [
    re.compile(r"(?:alamat|kirim\s+ke|di\s+kirim\s+ke|antar\s+ke|lokasi)\s*:?\s*(.{3,90})"),
]


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
    return 1


def _match_products(message: str, catalog: list[dict]) -> list[dict]:
    """Return catalog rows whose product name appears in the message.

    Matches on whole product name OR the product family (text before the first
    " - "), so "kaos oversize crop - hitam" matches a catalog row named
    "Kaos Oversize Crop - Hitam - Size L" via its family "Kaos Oversize Crop".
    Each row is only claimed once, longest-name-first so "Kaos Oversize Crop"
    wins over a bare "Kaos".
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
            matched.append(row)
        elif family and family in msg and len(family) >= 3:
            # Family match — claim the family so a generic "kaos" doesn't also claim it.
            claimed.add(family)
            matched.append(row)
    return matched


def extract_items(message: str, catalog: list[dict]) -> list[dict]:
    """Extract [{product, qty, price}] from a confirm_order message.

    price is the catalog's unit price (float) or None when unparseable; qty
    defaults to 1. If no catalog row matches, returns [] (caller decides the
    fallback reply).
    """
    items: list[dict] = []
    for row in _match_products(message, catalog):
        name = (row.get("nama_produk") or "").strip()
        qty = _find_quantity(message, name)
        price = _parse_price(row.get("harga"))
        items.append({"product": name, "qty": qty, "price": price})
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
