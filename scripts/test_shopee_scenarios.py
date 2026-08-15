"""Run a comprehensive, human-like scenario battery against the scraped Shopee catalog.

Loads data/shopee_thxsevendays.json into a throwaway tenant (data_source='upload')
and pushes natural Indonesian WhatsApp buyer phrasing — slang, typos, abbreviations,
context — plus rare edge cases through dry_run_reply.

Usage: python scripts/test_shopee_scenarios.py
"""
from __future__ import annotations

import json
import time

from app.db.local_data_repo import replace_catalog, replace_faq
from app.db.tenant_repo import insert_or_update_tenant
from app.services.bot_tester import _build_llm_client, _build_sheets_client, dry_run_reply

TENANT = "shopee-thx"
JSON_PATH = "data/shopee_thxsevendays.json"

# FAQ built from the shop's real public info (description + store notes).
FAQ = [
    ("bisa retur barang?", "Bisa refund/return jika barang tidak sesuai atau cacat produksi, syarat video unboxing, foto nota, dan label pembeli."),
    ("salah ukuran bisa tukar?", "Bisa tukar/refund jika barang tidak sesuai, syarat video unboxing, foto nota, dan label pembeli."),
    ("bahannya apa?", "Bahan 100% Cotton Combed 24s, lembut, menyerap keringat, tidak kaku, nyaman dipakai sehari-hari."),
    ("sablonnya gampang luntur?", "Sablon Plastisol High Quality, lentur, tidak mudah pecah, tidak luntur. Jangan setrika langsung di bagian sablon."),
    ("size apa aja yang tersedia?", "Size M, L, XL, XXL. M lebar dada 48cm x panjang 70cm, L 50x72, XL 52x74, XXL 55x76 (bukan oversize)."),
    ("kirim hari minggu bisa?", "Hari minggu tidak ada pengiriman."),
    ("dikirim dari mana?", "Dikirim dari Kab. Bandung."),
    ("stok ready?", "Barang kami selalu ready stock, silakan langsung checkout."),
    ("bisa cod?", "Info pembayaran COD disesuaikan dengan area pengiriman."),
    ("berapa lama pengiriman?", "Estimasi pengiriman tergantung area tujuan, umumnya 2-5 hari kerja."),
]

# (category, question) — natural buyer phrasing: common first, rare/edge last.
SCENARIOS = [
    # --- stok (pasti ditanya) ---
    ("stok", "kak kaosnya masih ready?"),
    ("stok", "min kaos warna hitam ada?"),
    ("stok", "kak ada size L ga?"),
    ("stok", "kaos hitam size xxl ada gak kak?"),
    ("stok", "yg warna sage masih ada kak?"),
    ("stok", "kak kaos bahan combed 24s ready stock?"),
    ("stok", "paket 3 kaos ada kak?"),
    ("stok", "kaos warna denim ready ga?"),
    # --- harga (pasti ditanya) ---
    ("harga", "kaosnya berapaan kak?"),
    ("harga", "kak yg warna navy brp?"),
    ("harga", "harga paket 3 kaos brp kak?"),
    ("harga", "kaos putih berapa harganya min?"),
    ("harga", "paling murah yg mana kak?"),
    ("harga", "kak kaos ivory brp?"),
    # --- order (pasti terjadi) ---
    ("order", "kak aku mau order kaos hitam L 2"),
    ("order", "pesen 1 ya kaos navy xl"),
    ("order", "min aku mau beli kaos putih ukuran M"),
    ("order", "order paket 3 kaosnya kak"),
    ("order", "kaos sage size S ada? aku mau 1"),
    ("order", "kak beli 3 kaos hitam size L bisa?"),
    ("order", "kaos denim aku mau 1 kak"),
    ("order", "kak kaos hitam 1 ya"),
    # --- bahan/kualitas (sering) ---
    ("bahan", "kak bahannya apa ya?"),
    ("bahan", "kaosnya adem gak kak?"),
    ("bahan", "sablonnya gampang luntur gak?"),
    ("bahan", "kak ini bahannya tebel apa tipis?"),
    ("bahan", "yg warna putih nembus gak kak?"),
    # --- ukuran (sering) ---
    ("ukuran", "kak size apa aja?"),
    ("ukuran", "ada size xxl gak?"),
    ("ukuran", "kaosnya jumbo gak sih kak?"),
    ("ukuran", "aku biasa pake L, ini muat gak?"),
    ("ukuran", "kak L panjangnya brp cm?"),
    # --- pengiriman (sering) ---
    ("ongkir", "ongkir ke jakarta brp kak?"),
    ("ongkir", "kalau order sekarang kapan dikirim?"),
    ("ongkir", "kak kirim hari minggu bisa?"),
    ("ongkir", "dari mana kak pengirimannya?"),
    ("ongkir", "sampai depok berapa lama ya kak?"),
    # --- retur (sering) ---
    ("retur", "kak bisa retur gak kalo gak cocok?"),
    ("retur", "salah ukuran bisa tukar ga?"),
    ("retur", "kalo ada cacat gimana kak?"),
    ("retur", "barangnya beda sama foto, bisa balikin gak?"),
    # --- bayar / nego (sering) ---
    ("bayar", "kak bisa cod?"),
    ("bayar", "ada diskon gak kak?"),
    ("bayar", "nego dikit boleh kak?"),
    ("bayar", "beli banyak ada harga khusus gak?"),
    # --- rare / edge (jarang tapi mungkin) ---
    ("edge", "kak ini buat cewek bisa?"),
    ("edge", "bisa custom desain gak kak?"),
    ("edge", "kak barang aku rusak pas dateng, gimana ini?"),
    ("edge", "mau batalkan pesanan aku"),
    ("edge", "😊"),
    ("edge", "how much?"),
    ("edge", "kaos htm brp kak"),
    ("edge", "kak ini jual makanan gak?"),
    ("edge", "   "),
    ("edge", "gimana cara ordernya kak?"),
    ("edge", "toko kalian di bandung mana ya?"),
    ("edge", "kaosnya original gak kak?"),
    ("edge", "kalo beli 10 pcs dapet harga brp?"),
    ("edge", "kak aku udah transfer, gimana konfirmasinya?"),
]


def main() -> None:
    data = json.load(open(JSON_PATH))
    catalog = data["catalog"]

    insert_or_update_tenant(
        TENANT,
        wa_api_key_encrypted=b"",
        google_sheet_id="FAKE_SHOPEE_THX",
        owner_wa_number="6280000000000",
        business_type="fashion",
        data_source="upload",
    )
    replace_faq(TENANT, [{"pertanyaan": q, "jawaban": a} for q, a in FAQ])
    replace_catalog(TENANT, catalog)

    llm = _build_llm_client()
    sheets = _build_sheets_client(TENANT)

    print(f"tenant {TENANT} | {len(catalog)} catalog rows | {len(FAQ)} FAQ")
    print("=" * 100)
    t0 = time.time()
    for i, (cat, q) in enumerate(SCENARIOS, 1):
        t1 = time.time()
        try:
            r = dry_run_reply(TENANT, q, llm_client=llm, sheets_client=sheets)
            reply = (r.get("reply_text") or "").replace("\n", " ").strip()
            intent = r.get("intent")
            action = r.get("action")
            items = r.get("order_items") or []
            detail = ""
            if action == "order" and items:
                detail = " | ".join(
                    f"{it.get('nama_produk','?')[:40]} x{it.get('qty')} @{it.get('price')}" for it in items
                )
            print(f"[{i:2d}] {cat:8} {q!r}")
            print(f"      intent={intent} action={action} {detail}")
            print(f"      {reply[:170]}")
        except Exception as e:  # noqa: BLE001
            print(f"[{i:2d}] {cat:8} {q!r}  ERROR {e}")
        print(f"      ({time.time()-t1:.1f}s)")
    print("=" * 100)
    print(f"total {len(SCENARIOS)} skenario, {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
