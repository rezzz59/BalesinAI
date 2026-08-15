"""Auto-scoring kualitas AI — jalankan 50 skenario pembeli ke bot (dry-run).

Mengukur kualitas jawaban AI tanpa mengirim WhatsApp apa pun:
  1. Answered  : action reply/order (bukan fallback) untuk pertanyaan yang harus bisa dijawab
  2. Intent    : intent cocok ekspektasi
  3. Grounded  : angka pada jawaban ada di katalog (anti-halusinasi)
  4. Clean     : tidak ada aksara asing

Pakai: python scripts/ai_quality_report.py
Output: tabel terminal + data/ai_report.json
"""
import json
import re
import sys
import time
from pathlib import Path

from app.services.bot_tester import dry_run_reply, _build_llm_client, _build_sheets_client
from app.services.reply_validator import _NON_LATIN

TENANT = "tes-9ca4"

# (pertanyaan, kategori, intent_diharapkan, action_diharapkan, check_grounded)
SCENARIOS = [
    # --- tanya stok (check_product) ---
    ("kaos oversize crop hitam ready?", "stok", "check_product", "reply", False),
    ("crewneck navy size S ada?", "stok", "check_product", "reply", False),
    ("stok hoodie fleece tebal?", "stok", "check_product", "reply", False),
    ("jogger putih masih ada ga?", "stok", "check_product", "reply", False),
    ("kaos dry fit polos ready stock?", "stok", "check_product", "reply", False),
    ("topi snapback ada?", "stok", "check_product", "reply", False),
    ("kaos oversize crop dustypink ready?", "stok", "check_product", "reply", False),
    ("hoodie basic navy ready ga?", "stok", "check_product", "reply", False),
    # --- tanya harga (faq, grounded) ---
    ("berapa harga kaos polos?", "harga", "faq", "reply", True),
    ("harga hoodie fleece?", "harga", "faq", "reply", True),
    ("kaos dry fit berapa?", "harga", "faq", "reply", True),
    ("crewneck heavyweight harganya?", "harga", "faq", "reply", True),
    ("jogger pants cotton berapa?", "harga", "faq", "reply", True),
    ("harga kaos oversize crop?", "harga", "faq", "reply", True),
    ("topi berapa harganya?", "harga", "faq", "reply", True),
    ("berapa harga grosir 100 pcs?", "harga", "faq", "reply", True),
    # --- warna/ukuran (faq) ---
    ("warna apa aja yang ready?", "warna", "faq", "reply", False),
    ("ada size XXL?", "ukuran", "faq", "reply", False),
    ("dusty pink ada ga?", "warna", "faq", "reply", False),
    ("size apa aja yang tersedia?", "ukuran", "faq", "reply", False),
    ("ada warna sage green?", "warna", "faq", "reply", False),
    ("kaos polos ukurannya sampai mana?", "ukuran", "faq", "reply", False),
    # --- ongkir/pengiriman (faq) ---
    ("ongkir ke Jakarta berapa?", "ongkir", "faq", "reply", False),
    ("berapa lama pengirimannya?", "ongkir", "faq", "reply", False),
    ("bisa COD?", "ongkir", "faq", "reply", False),
    ("kirim ke luar kota berapa lama?", "ongkir", "faq", "reply", False),
    ("ongkir ke Surabaya?", "ongkir", "faq", "reply", False),
    # --- retur/garansi (faq) ---
    ("bisa retur barang?", "retur", "faq", "reply", False),
    ("garansi berapa lama?", "retur", "faq", "reply", False),
    ("salah ukuran bisa tukar?", "retur", "faq", "reply", False),
    ("barang beda sama foto bisa balikin?", "retur", "faq", "reply", False),
    ("kalau cacat bisa refund?", "retur", "faq", "reply", False),
    # --- order (confirm_order, grounded) ---
    ("saya order kaos hitam size L 2 pcs", "order", "confirm_order", "order", True),
    ("mau pesan hoodie navy 1", "order", "confirm_order", "order", True),
    ("order 3 kaos putih", "order", "confirm_order", "order", True),
    ("saya mau beli kaos oversize crop hitam size L 2", "order", "confirm_order", "order", True),
    ("pesan jogger putih size xxl 1", "order", "confirm_order", "order", True),
    ("mau order crewneck heavyweight navy size s", "order", "confirm_order", "order", True),
    ("beli kaos dry fit hitam 2 pcs", "order", "confirm_order", "order", True),
    ("order kaos polos putih 3", "order", "confirm_order", "order", True),
    # --- komplain/keberatan (route fallback) ---
    ("barang saya rusak padahal baru sampai", "komplain", None, "fallback", False),
    ("kecewa banget barangnya jelek", "komplain", None, "fallback", False),
    ("mahal banget, ada diskon ga?", "keberatan", None, "fallback", False),
    ("udah 3 hari belum nyampe, komplain!", "komplain", None, "fallback", False),
    ("nggak sesuai ekspektasi, mau refund", "komplain", None, "fallback", False),
    # --- edge case (tidak crash) ---
    ("😊😊😊", "edge", None, None, False),
    ("how much harga kaos? ready stock?", "edge", None, None, False),
    ("makanan kucing tuh gimana sih", "edge", None, None, False),
    ("   ", "edge", None, None, False),
    ("batalkan pesanan saya", "edge", None, None, False),
]

_NUM_RE = re.compile(r"\d[\d.,]*")


def _catalog_numbers(sheets_client) -> set[str]:
    """Kumpulkan semua angka (harga) dari katalog + FAQ untuk cek grounded."""
    nums: set[str] = set()
    try:
        rows = list(sheets_client.read_catalog()) + list(sheets_client.read_faq())
        for row in rows:
            for v in row.values():
                if v is None:
                    continue
                for m in _NUM_RE.findall(str(v)):
                    nums.add(m.replace(".", "").replace(",", ""))
    except Exception:
        pass
    return nums


def main():
    print("Membangun klien LLM + data...")
    llm = _build_llm_client()
    sheets = _build_sheets_client(TENANT)
    catalog_nums = _catalog_numbers(sheets)
    print(f"  katalog: {len(catalog_nums)} angka harga unik\n")

    results = []
    answered_n = intent_n = grounded_n = clean_n = 0
    answered_den = intent_den = grounded_den = clean_den = 0
    t0 = time.time()

    for i, (q, cat, exp_intent, exp_action, check_g) in enumerate(SCENARIOS, 1):
        t1 = time.time()
        try:
            r = dry_run_reply(TENANT, q, llm_client=llm, sheets_client=sheets)
            reply = r.get("reply_text") or ""
            intent = r.get("intent")
            action = r.get("action")
        except Exception as e:  # noqa: BLE001
            results.append({"q": q, "cat": cat, "error": str(e)})
            print(f"[{i:2d}] ERROR {q!r}: {e}")
            continue

        # clean
        clean_den += 1
        clean = not bool(_NON_LATIN.search(reply))
        clean_n += int(clean)

        # answered (hanya untuk kategori yang harus dijawab, bukan komplain/edge)
        if cat not in ("komplain", "keberatan", "edge"):
            answered_den += 1
            answered = action in ("reply", "order") and bool(reply)
            answered_n += int(answered)
        else:
            answered = None

        # intent
        if exp_intent is not None:
            intent_den += 1
            intent_ok = intent == exp_intent
            intent_n += int(intent_ok)
        else:
            intent_ok = None

        # grounded
        grounded = None
        if check_g:
            grounded_den += 1
            if cat == "order":
                # Order items already carry catalog prices — check each item's
                # product+price appears in the catalog (not the computed total,
                # which is qty×price and legitimately not a catalog value).
                items = r.get("order_items") or []
                prices = {str(i.get("price", "")).replace(".0", "") for i in items if i.get("price")}
                grounded = bool(items) and prices.issubset(catalog_nums)
            else:
                # FAQ price answer: any Rp amount in the reply must be a known
                # catalog/FAQ value. No Rp amount claimed → grounded (deferred).
                rp_values = {
                    re.sub(r"[^0-9]", "", m)
                    for m in re.findall(r"Rp\s*[\d.,]+", reply)
                }
                grounded = rp_values.issubset(catalog_nums)
            grounded_n += int(bool(grounded))

        dt = time.time() - t1
        status = "✓" if (answered is not False and intent_ok is not False and grounded is not False and clean) else "✗"
        results.append({
            "q": q, "cat": cat, "intent": intent, "exp_intent": exp_intent,
            "action": action, "reply": reply[:180],
            "answered": answered, "intent_ok": intent_ok, "grounded": grounded, "clean": clean,
            "seconds": round(dt, 1),
        })
        print(f"[{i:2d}]{status} {dt:4.1f}s {cat:10} {intent or '-':14} {action or '-':9} {q[:44]!r}")

    total = time.time() - t0
    print("\n" + "=" * 60)
    print(" SKOR TOTAL")
    print("=" * 60)
    print(f"  Answered : {answered_n}/{answered_den}  ({answered_n/answered_den*100:.0f}%)" if answered_den else "  Answered : n/a")
    print(f"  Intent   : {intent_n}/{intent_den}  ({intent_n/intent_den*100:.0f}%)" if intent_den else "  Intent   : n/a")
    print(f"  Grounded : {grounded_n}/{grounded_den}  ({grounded_n/grounded_den*100:.0f}%)" if grounded_den else "  Grounded : n/a")
    print(f"  Clean    : {clean_n}/{clean_den}  ({clean_n/clean_den*100:.0f}%)" if clean_den else "  Clean    : n/a")
    print(f"  Runtime  : {total:.0f}s ({total/len(SCENARIOS):.1f}s/skenario)")
    print("=" * 60)

    # daftar gagal
    fails = [r for r in results if r.get("error") or r.get("answered") is False or r.get("intent_ok") is False or r.get("grounded") is False or r.get("clean") is False]
    if fails:
        print(f"\n GAGAL ({len(fails)}):")
        for r in fails:
            if r.get("error"):
                print(f"  - ERROR {r['q']!r}: {r['error']}")
                continue
            why = []
            if r.get("answered") is False:
                why.append("fallback")
            if r.get("intent_ok") is False:
                why.append(f"intent={r['intent']}(≠{r['exp_intent']})")
            if r.get("grounded") is False:
                why.append("angka diluar katalog")
            if r.get("clean") is False:
                why.append("aksara asing")
            print(f"  - {r['q']!r} → {', '.join(why)}")

    out = {"tenant": TENANT, "summary": {
        "answered": [answered_n, answered_den], "intent": [intent_n, intent_den],
        "grounded": [grounded_n, grounded_den], "clean": [clean_n, clean_den],
        "runtime_s": round(total, 1),
    }, "results": results}
    Path("data/ai_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nDetail tersimpan: data/ai_report.json")


if __name__ == "__main__":
    main()
