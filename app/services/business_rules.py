"""Per-industry business rules that keep the bot honest (no invented numbers).

Catering (business_type='kuliner'):
  - Shipping cost per wilayah from the 'Ongkir' sheet.
  - Minimum order (porsi) per product or per wilayah.
  - Event date is always requested so the kitchen schedule can be checked.
  - Down payment (DP) = 50% of the quote.
All math is deterministic (catalog price + ongkir lookup) — no LLM in the hot
path. Fashion rules can live here later.
"""
import re
from typing import Any

_MONEY = re.compile(r"(\d{1,9}(?:[.,]\d{1,3})?)")
# "tanggal 12 juli", "12 juli 2025", "tanggal 12/07", "acara tanggal X", "tgl 12".
_DATE = re.compile(
    r"(?:tanggal|tgl|acara|event|hari)\s*:?\s*(\d{1,2})[\/\-.\s]+([a-z]{3,9}|\d{1,2})(?:[\/\-\s]+(\d{2,4}))?",
    re.IGNORECASE,
)
# "kirim ke jakarta barat", "wilayah jakarta utara", "ke cibubur", "alamat jakarta".
_WILAYAH = re.compile(
    r"(?:kirim\s*(?:ke)?|wilayah|area|daerah|kecamatan|antar\s*ke|lokasi|ke)\s*:?\s*([a-z]{3,40}(?:[\s\-][a-z]{3,40}){0,2})",
    re.IGNORECASE,
)

# Indonesian month names → number (for the event date prompt echo).
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "jun": 6,
    "jul": 7, "agu": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
}

DP_PERCENT = 50


def _money(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = re.sub(r"\s+", "", str(raw))
    s = re.sub(r"^(rp|idr)", "", s, flags=re.IGNORECASE)
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _fmt(money: float) -> str:
    if money == int(money):
        return f"Rp {int(money):,}".replace(",", ".")
    return f"Rp {money:,.2f}".replace(",", ".")


def extract_event_date(message: str) -> str | None:
    """Return a readable event date (e.g. '12 juli') if present, else None."""
    m = _DATE.search(message or "")
    if not m:
        return None
    day = m.group(1)
    month = m.group(2).lower()
    year = m.group(3)
    if month.isdigit():
        out = f"{day}-{int(month):02d}"
    else:
        month_num = _MONTHS.get(month[:3])
        out = f"{day} {month}" if month_num else f"{day}"
    if year:
        out += f" {year}"
    return out


def extract_wilayah(message: str) -> str | None:
    """Return a shipping area token if the buyer mentioned one."""
    m = _WILAYAH.search(message or "")
    if not m:
        return None
    area = m.group(1).strip().rstrip(".,!?")
    return area or None


def find_ongkir(ongkir_rows: list[dict], wilayah: str) -> dict | None:
    """Match an ongkir row whose wilayah appears in the given area string."""
    if not wilayah or not ongkir_rows:
        return None
    w = wilayah.lower()
    best: dict | None = None
    best_len = 0
    for row in ongkir_rows:
        key = (row.get("wilayah") or "").strip().lower()
        if key and key in w and len(key) > best_len:
            best, best_len = row, len(key)
    return best


def catering_quote(
    items: list[dict],
    ongkir_rows: list[dict],
    message: str,
) -> dict:
    """Compute a catering quote with ongkir + DP + min-order checks.

    Returns a dict the caller merges into the order reply:
      total, ongkir, dp, needs_date (bool), min_order_gap (int),
      detected_wilayah, detected_date
    All math deterministic from catalog prices + ongkir sheet.
    """
    subtotal = round(sum(
        (it.get("qty") or 0) * (it.get("price") or 0)
        for it in items if it.get("price") is not None
    ), 2)

    wilayah = extract_wilayah(message)
    ongkir_row = find_ongkir(ongkir_rows, wilayah) if wilayah else None
    ongkir = _money(ongkir_row.get("ongkir") if ongkir_row else None) or 0.0

    total = round(subtotal + ongkir, 2)
    dp = round(total * DP_PERCENT / 100, 2)

    # Minimum order: max of per-product min_order and per-wilayah min_order.
    min_order = 0
    for it in items:
        mo = _money(it.get("min_order"))
        if mo and mo > min_order:
            min_order = int(mo)
    if ongkir_row:
        mo_w = _money(ongkir_row.get("min_order"))
        if mo_w and mo_w > min_order:
            min_order = int(mo_w)
    total_porsi = sum(it.get("qty") or 0 for it in items)
    min_order_gap = max(0, min_order - total_porsi) if min_order else 0

    date = extract_event_date(message)

    return {
        "subtotal": subtotal,
        "ongkir": ongkir,
        "total": total,
        "dp": dp,
        "needs_date": date is None,
        "min_order": min_order,
        "total_porsi": total_porsi,
        "min_order_gap": min_order_gap,
        "detected_wilayah": wilayah,
        "detected_date": date,
        "ongkir_known": ongkir_row is not None or not wilayah,
    }


def format_catering_reply(quote: dict, items: list[dict], confirmed: bool = False) -> str:
    """Build the buyer-facing catering reply.

    confirmed=False → consultation/quote preview (missing date or below
    minimum), never claims the order is accepted. confirmed=True → order
    accepted (date + minimum order satisfied).
    """
    header = (
        f"Order diterima — total {quote['total_porsi']} porsi 🎉"
        if confirmed
        else f"Ini rincian pesanan Kakak ya 🙏"
    )
    lines = [header, ""]
    for it in items:
        qty = it.get("qty", 1)
        price = it.get("price")
        lines.append(f"• {it['product']} x{qty}" + (f" = {_fmt(price * qty)}" if price else ""))

    if quote.get("ongkir"):
        lines.append(f"• Ongkir ({quote.get('detected_wilayah') or 'area'}): {_fmt(quote['ongkir'])}")
    lines.append("")
    lines.append(f"Total: {_fmt(quote['total'])}")
    lines.append(f"DP 50%: {_fmt(quote['dp'])}")

    if quote.get("needs_date"):
        lines.append("")
        lines.append("Sebelum lanjut, tanggal acaranya kapan ya? Kami cek dulu ketersediaan jadwal dapur 🙏")
    elif not confirmed:
        lines.append(f"Tanggal acara: {quote['detected_date']}")
        lines.append("")
        lines.append("Kalau rincian ini sudah oke, boleh kami proses pesanannya ya Kak?")
    else:
        lines.append(f"Tanggal acara: {quote['detected_date']}")
        lines.append("")
        lines.append("Kami kirimkan detailnya ke owner untuk konfirmasi jadwal dapur 🙏")

    if quote.get("min_order_gap"):
        lines.append("")
        lines.append(f"⚠️ Minimal pemesanan {quote['min_order']} porsi. "
                     f"Masih kurang {quote['min_order_gap']} porsi. Mau ditambah?")
    return "\n".join(lines)