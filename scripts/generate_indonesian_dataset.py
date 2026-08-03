"""Generate comprehensive Indonesian buyer question dataset.

Based on analysis of WhatsApp business patterns in Indonesia.
"""
import csv
import json



# Comprehensive Indonesian buyer question patterns
# Categorized by intent with multiple variations

INDONESIAN_BUYER_DATASET: list[dict] = [
    # ============================================
    # FAQ - Pertanyaan Umum (40% expected volume)
    # ============================================
    
    # --- HARGA & PEMBAYARAN ---
    {"category": "faq", "intent": "harga", "message": "Berapa harga kaos hitam?", "variations": [
        "brp harga kaos hitam?",
        "harga berapa min?",
        "mahal ga?",
        "ada diskon ga?",
        "murah ga?",
        "harga termurah?",
        "bisa nego?",
        "harga grosir?",
    ]},
    {"category": "faq", "intent": "harga", "message": "Berapa ongkir ke Jakarta?", "variations": [
        "ongkir jakarta brp?",
        "gratis ongkir?",
        "ongkir ke bandung?",
        "biaya kirim?",
        "ekspedisi apa?",
        "jnt/jne/sicepat?",
    ]},
    {"category": "faq", "intent": "pembayaran", "message": "Bisa COD ga?", "variations": [
        "cod?",
        "bisa transfer?",
        "bisa bayar dimana?",
        "metode pembayaran?",
        "bisa cicil?",
        "bayar nanti?",
    ]},
    {"category": "faq", "intent": "diskon", "message": "Ada promo diskon?", "variations": [
        "ada diskon?",
        "promo apa?",
        "diskon berapa?",
        "harga spesial?",
        "murah banget?",
    ]},
    {"category": "faq", "intent": "min_order", "message": "Minimal order berapa?", "variations": [
        "min order?",
        "paling sedikit beli berapa?",
        "pesan 1 pcs bisa?",
        "belum bisa?",
        "order minimum?",
    ]},
    
    # --- STOK & KESEDIADAAN ---
    {"category": "faq", "intent": "stok", "message": "Ada stock kaos hitam size L?", "variations": [
        "ready stock?",
        "ada ga?",
        "tersedia?",
        "stok habis?",
        "baru datang?",
        "restock?",
    ]},
    {"category": "faq", "intent": "size", "message": "Ukurannya ada yang L ga?", "variations": [
        "size M ada?",
        "ukuran berapa?",
        "size XXL?",
        "size S?",
        "size XL?",
        "ada size 32?",
        "size 30?",
    ]},
    {"category": "faq", "intent": "warna", "message": "Warnanya apa aja?", "variations": [
        "ada warna apa?",
        "pilihan warna?",
        "warnanya merah?",
        "ada warna hitam?",
        "varian warna?",
    ]},
    {"category": "faq", "intent": "produk", "message": "Ada produk lain?", "variations": [
        "ada ga yang lain?",
        "varian apa aja?",
        "lineup produk?",
        "catalog?",
        "liat produk lainnya",
    ]},
    
    # --- PENGIRIMAN ---
    {"category": "faq", "intent": "pengiriman", "message": "Kapan barang sampai?", "variations": [
        "kapan sampe?",
        "berapa hari?",
        "lama pengiriman?",
        " estimasi sampai?",
        "sudah sampai belum?",
        "udah sampe?",
    ]},
    {"category": "faq", "intent": "area", "message": "Bisa kirim ke Bandung?", "variations": [
        "kirim ke surabaya?",
        "area mana aja?",
        "kirim ke luar jawa?",
        "bisakirim ke [kota]?",
        "ekspedisi ke mana?",
    ]},
    
    # --- GARANSI & RETUR ---
    {"category": "faq", "intent": "garansi", "message": "Garansinya berapa lama?", "variations": [
        "garansi?",
        "bukan garansi?",
        "jaminan?",
        "garansi resmi?",
        "ganti baru?",
    ]},
    {"category": "faq", "intent": "retur", "message": "Bisa tukar ukuran?", "variations": [
        "bisa return?",
        "tukar size?",
        "ganti ukuran?",
        "kalau tidak cocok?",
        "bisa exchange?",
    ]},
    {"category": "faq", "intent": "kualitas", "message": "Bahannya adem ga?", "variations": [
        "bahannya bagus?",
        "awet ga?",
        "luntur?",
        "bahan apa?",
        "tebal ga?",
        "adem?",
    ]},
    
    # --- PROSES ORDER ---
    {"category": "faq", "intent": "cara_order", "message": "Gimana cara order?", "variations": [
        "cara pesan?",
        "belinya dimana?",
        "order dimana?",
        "link order?",
        "tempat order?",
        "checkout dimana?",
    ]},
    
    # ============================================
    # CHECK_PRODUCT - Produk Spesifik (15% expected)
    # ============================================
    {"category": "check_product", "intent": "check_product", "message": "Kaos oversize hitam size L ready?", "variations": [
        "hoodie fleece olive ready?",
        "celana cargo coklat size 32?",
        "dress merah muda stok?",
        "jaket denim ada?",
        "tas ini ready stock?",
        "sepatu putih size 42?",
        "kemeja motif bunga ready?",
        "topi blacky ready?",
    ]},
    
    # ============================================
    # CONFIRM_ORDER - Konfirmasi Pembelian (10% expected)
    # ============================================
    {"category": "confirm_order", "intent": "confirm_order", "message": "Saya pesan 2 pcs", "variations": [
        "order 3 pcs",
        "beli 1 ya",
        "saya ambil",
        "oke saya pesan",
        "booking dulu",
        "saya order sekarang",
        "lanjut order",
        "checkout",
        "pesen dong",
    ]},
    {"category": "confirm_order", "intent": "confirm_order", "message": "Saya order kaos hitam size L", "variations": [
        "pesan hoodie fleece olive size XL",
        "beli celana cargo coklat 32",
        "order dress merah muda size M",
    ]},
    
    # ============================================
    # SMALL_TALK - Sapaan (20% expected, currently 0%)
    # ============================================
    {"category": "small_talk", "intent": "small_talk", "message": "Halo", "variations": [
        "hai",
        "hello",
        "hi",
        "selamat pagi",
        "selamat siang",
        "selamat sore",
        "selamat malam",
        "pagi",
        "siang",
        "sore",
        "malam",
        "kak",
        "min",
        "admin",
        "👋",
        "🙏",
        "👍",
        "👌",
        "ok",
        "oke",
        "iya",
        "iya kak",
        "terima kasih",
        "makasih",
        "thanks",
        "thank you",
    ]},
    
    # ============================================
    # COMPLAINT - Keluhan (5% expected, underreported)
    # ============================================
    {"category": "complaint", "intent": "complaint", "message": "Udah 3 hari ga sampai-sampai", "variations": [
        "barang belum sampai",
        "lama banget",
        "kapan sampe",
        "udah berapa hari",
        "tracking no ga ada",
    ]},
    {"category": "complaint", "intent": "complaint", "message": "Barang rusak, mau refund", "variations": [
        "produk cacat",
        "rusak pas sampai",
        "ada bagian yang pecah",
        "mau kembalikan",
        "refund dong",
        "ganti baru",
    ]},
    {"category": "complaint", "intent": "complaint", "message": "Ga sesuai foto", "variations": [
        "beda sama foto",
        "tidak sesuai deskripsi",
        "warna beda",
        "size beda",
        "bahan beda",
        "penipuan",
    ]},
    {"category": "complaint", "intent": "complaint", "message": "Kecewa banget sih", "variations": [
        "kecewa",
        "kecewa banget",
        "sangat kecewa",
        "marah",
        "sAYA MARAH",
        "saya marah",
    ]},
    {"category": "complaint", "intent": "complaint", "message": "Batal aja", "variations": [
        "saya batalkan",
        "batal",
        "gak jadi",
        "gak jadi beli",
        "mau komplain",
        "komplain ke sosmed",
        "saya review jelek",
    ]},
    
    # ============================================
    # MULTI_INTENT - Pertanyaan Ganda (10% expected)
    # ============================================
    {"category": "multi_intent", "intent": "check_product+confirm", "message": "Ready ga? Kalau ready saya order", "variations": [
        "Ada stock? Saya pesan 2",
        "Size L ada? Order sekarang",
        "Harga berapa? Kalau murah saya beli",
        "Gratis ongkir? Saya order",
        " COD? Saya pesan",
    ]},
    {"category": "multi_intent", "intent": "faq+check_product", "message": "Berapa ongkir ke Surabaya? Saya mau order", "variations": [
        "Ada warna merah? Size L?",
        "Garansi berapa? Kalau rusak bisa tukar?",
        "Minimal order berapa? Saya mau pesan 10",
        "Bisa custom? Price?",
    ]},
    
    # ============================================
    # EDGE CASES - Typo, Singkatan, Mixed (10% expected)
    # ============================================
    {"category": "edge_case", "intent": "typo", "message": "brp harga kaos hitam", "variations": [
        "brp",
        "berpa",
        "brp2",
        "hrga",
        "harga",
        "kaos hitam",
        "kaso",
        "hitam",
        "htam",
    ]},
    {"category": "edge_case", "intent": "singkatan", "message": "yg ready?", "variations": [
        "yg",
        "yg ada",
        "yg ready stock",
        "yg size L",
        "yg warna hitam",
    ]},
    {"category": "edge_case", "intent": "mixed_language", "message": "Ready stock?", "variations": [
        "Ready?",
        "Is it available?",
        "Stock available?",
        "Can I order?",
        "Do you have?",
    ]},
    {"category": "edge_case", "intent": "single_word", "message": "Harga", "variations": [
        "Stok",
        "Ready",
        "COD",
        "Ongkir",
        "Size",
        "Warna",
        "Promo",
        "Diskon",
        "Garansi",
        "Return",
    ]},
    {"category": "edge_case", "intent": "emoji_only", "message": "👍", "variations": [
        "👋",
        "🙏",
        "👌",
        "💯",
        "😍",
        "🔥",
        "❤️",
        "👀",
        "😊",
        "🤔",
    ]},
    {"category": "edge_case", "intent": "empty", "message": "", "variations": [
        "   ",
        "\n",
        "\t",
    ]},
    {"category": "edge_case", "intent": "punctuation_only", "message": "!!!", "variations": [
        "???",
        "...",
        "!?!?",
        "??",
    ]},
]


def export_dataset(output_path: str = "/tmp/indonesian_buyer_dataset.csv"):
    """Export Indonesian buyer dataset to CSV."""
    rows = []
    for item in INDONESIAN_BUYER_DATASET:
        # Main message
        rows.append({
            "category": item["category"],
            "intent": item["intent"],
            "message": item["message"],
            "variations_count": len(item["variations"]),
            "is_primary": "yes",
            "notes": "Primary message",
        })
        # Add variations
        for i, var in enumerate(item["variations"]):
            rows.append({
                "category": item["category"],
                "intent": item["intent"],
                "message": var,
                "variations_count": len(item["variations"]),
                "is_primary": "no",
                "notes": f"Variation {i+1}",
            })
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["category", "intent", "message", "variations_count", "is_primary", "notes"],
        )
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"Exported {len(rows)} rows to {output_path}")
    print()
    print("Breakdown by category:")
    categories = {}
    for item in INDONESIAN_BUYER_DATASET:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = {"primary": 0, "variations": 0}
        categories[cat]["primary"] += 1
        categories[cat]["variations"] += len(item["variations"])
    
    for cat, stats in sorted(categories.items()):
        total = stats["primary"] + stats["variations"]
        print(f"  {cat:20} {stats['primary']:3} primary + {stats['variations']:3} variations = {total:4} total")


def print_summary():
    """Print dataset summary."""
    print("=" * 60)
    print("INDONESIAN BUYER QUESTION DATASET")
    print("=" * 60)
    print()
    
    total_items = len(INDONESIAN_BUYER_DATASET)
    total_variations = sum(len(item["variations"]) for item in INDONESIAN_BUYER_DATASET)
    total_messages = total_items + total_variations
    
    print(f"Primary messages: {total_items}")
    print(f"Variations: {total_variations}")
    print(f"Total messages: {total_messages}")
    print()
    
    print("Categories:")
    for item in INDONESIAN_BUYER_DATASET:
        print(f"  {item['category']:20} ({item['intent']}) - {1 + len(item['variations'])} messages")


if __name__ == "__main__":
    print_summary()
    print()
    export_dataset()
