"""Generate comprehensive training dataset for Indonesian chatbot.

Based on:
1. Analisis 740 logs real
2. Riset pola buyer Indonesia (WhatsApp e-commerce)
3. Pattern dari dataset IndoDialogue, INDOQA, dll

This creates a training-ready dataset without external dependencies.
"""
import csv
import json
import random


# ============================================
# INDONESIAN BUYER QUESTION PATTERNS
# Based on e-commerce WhatsApp research
# ============================================

FAQ_PATTERNS = {
    "harga": [
        "Berapa harga kaos hitam?",
        "Brp min?",
        "Harga berapa?",
        "Mahal ga?",
        "Ada diskon ga?",
        "Murah ga?",
        "Harga grosir?",
        "Bisa nego?",
        "Promo apa?",
        "Diskon berapa?",
        "Harga termurah?",
        "Bisa nego min?",
        "Harga untuk 100 pcs?",
        "Harga per piece?",
    ],
    "ongkir": [
        "Berapa ongkir ke Jakarta?",
        "Ongkir brp?",
        "Gratis ongkir?",
        "Kirim ke Bandung bisa?",
        "Biaya kirim?",
        "Ekspedisi apa?",
        "Pake JNE/J&T?",
        "Kapan sampe?",
        "Estimasi sampai?",
        "Lama pengiriman?",
        "Ongkir ke Surabaya?",
        "Kirim ke luar Jawa?",
    ],
    "pembayaran": [
        "Bisa COD ga?",
        "Cod?",
        "Bisa transfer?",
        "Bayarnya gimana?",
        "Bisa cicil?",
        "Bisa bayar nanti?",
        "Metode pembayaran?",
        "Bisa bayar dimana?",
    ],
    "stok": [
        "Ada stock kaos hitam size L?",
        "Ready stock?",
        "Ada ga?",
        "Tersedia?",
        "Stok habis?",
        "Baru datang?",
        "Restock?",
        "Ada stok?",
    ],
    "size": [
        "Ukurannya ada yang L ga?",
        "Size M ada?",
        "Ukuran berapa?",
        "Size XXL?",
        "Size S?",
        "Size XL?",
        "Ada size 32?",
        "Size 30?",
    ],
    "warna": [
        "Warnanya apa aja?",
        "Ada warna merah?",
        "Pilihan warna?",
        "Warnanya hitam?",
        "Varian warna?",
    ],
    "garansi": [
        "Garansinya berapa lama?",
        "Garansi?",
        "Bukan garansi?",
        "Jaminan?",
        "Garansi resmi?",
        "Ganti baru?",
    ],
    "retur": [
        "Bisa tukar ukuran?",
        "Bisa return?",
        "Tukar size?",
        "Ganti ukuran?",
        "Kalau tidak cocok?",
        "Bisa exchange?",
    ],
    "kualitas": [
        "Bahannya adem ga?",
        "Bahannya bagus?",
        "Awet ga?",
        "Luntur?",
        "Bahan apa?",
        "Tebal ga?",
    ],
    "order": [
        "Gimana cara order?",
        "Cara pesan?",
        "Belinya dimana?",
        "Order dimana?",
        "Link order?",
        "Tempat order?",
        "Checkout dimana?",
    ],
    "min_order": [
        "Minimal order berapa?",
        "Min order?",
        "Paling sedikit beli berapa?",
        "Pesan 1 pcs bisa?",
        "Order minimum?",
    ],
}

COMPLAINT_PATTERNS = [
    "Udah 3 hari ga sampai-sampai",
    "Barang belum sampai",
    "Lama banget",
    "Kapan sampe",
    "Barang rusak, mau refund",
    "Produk cacat",
    "Rusak pas sampai",
    "Ga sesuai foto",
    "Beda sama foto",
    "Tidak sesuai deskripsi",
    "Kecewa banget sih",
    "Kecewa",
    "Saya marah",
    "Batal aja",
    "Saya batalkan",
    "Ga jadi beli",
    "Mau komplain",
    "Komplain ke sosmed",
    "Saya review jelek",
]

SMALL_TALK_PATTERNS = [
    "Halo",
    "Hai",
    "Hello",
    "Hi",
    "Selamat pagi",
    "Selamat siang",
    "Selamat sore",
    "Selamat malam",
    "Pagi",
    "Siang",
    "Sore",
    "Malam",
    "Kak",
    "Min",
    "Admin",
    "Terima kasih",
    "Makasih",
    "Thanks",
    "Thank you",
    "👋",
    "🙏",
    "👍",
    "👌",
    "💯",
    "😍",
    "🔥",
    "👀",
    "😊",
]

CONFIRM_ORDER_PATTERNS = [
    "Saya pesan 2 pcs",
    "Order 3 pcs",
    "Beli 1 ya",
    "Saya ambil",
    "Oke saya pesan",
    "Booking dulu",
    "Saya order sekarang",
    "Lanjut order",
    "Checkout",
    "Pesen dong",
    "Saya order kaos hitam size L",
    "Pesan hoodie fleece olive size XL",
    "Beli celana cargo coklat 32",
]

MULTI_INTENT_PATTERNS = [
    "Ready ga? Kalau ready saya order",
    "Ada stock? Saya pesan 2",
    "Size L ada? Order sekarang",
    "Harga berapa? Kalau murah saya beli",
    "Gratis ongkir? Saya order",
    "COD? Saya pesan",
    "Berapa ongkir ke Surabaya? Saya mau order",
    "Ada warna merah? Size L?",
    "Garansi berapa? Kalau rusak bisa tukar?",
    "Minimal order berapa? Saya mau pesan 10",
    "Bisa custom? Price?",
]

EDGE_CASE_PATTERNS = {
    "typo": [
        "brp harga kaos",
        "berpa",
        "hrga",
        "kalo ada",
        "yg ready",
        "yg ada",
    ],
    "singkatan": [
        "yg ready?",
        "yg size L",
        "yg warna hitam",
        "td ada?",
        "sm orang",
    ],
    "mixed": [
        "Ready stock?",
        "Is it available?",
        "Can I order?",
        "Stock available?",
    ],
    "single_word": [
        "Harga",
        "Stok",
        "Ready",
        "COD",
        "Ongkir",
        "Size",
        "Warna",
        "Promo",
        "Garansi",
    ],
    "emoji_only": [
        "👍",
        "👋",
        "🙏",
        "👌",
        "💯",
        "😍",
        "🔥",
        "❤️",
        "👀",
        "😊",
    ],
    "empty": [
        "",
        "   ",
        "\n",
    ],
    "punctuation": [
        "!!!",
        "???",
        "...",
        "!?!?",
        "??",
    ],
}

CHECK_PRODUCT_PATTERNS = [
    "Kaos oversize hitam size L ready?",
    "Hoodie fleece olive ready?",
    "Celana cargo coklat size 32?",
    "Dress merah muda ready stock?",
    "Jaket denim ada?",
    "Tas ini ready stock?",
    "Sepatu putih size 42?",
    "Kemeja motif bunga ready?",
    "Topi blacky ready?",
]


def generate_dataset():
    """Generate comprehensive training dataset."""
    dataset = []
    
    # FAQ patterns
    for category, patterns in FAQ_PATTERNS.items():
        for pattern in patterns:
            dataset.append({
                "category": "faq",
                "intent": category,
                "message": pattern,
                "source": "indonesian_buyer_patterns",
                "notes": f"FAQ - {category}"
            })
    
    # Complaint patterns
    for pattern in COMPLAINT_PATTERNS:
        dataset.append({
            "category": "complaint",
            "intent": "complaint",
            "message": pattern,
            "source": "indonesian_buyer_patterns",
            "notes": "Complaint/Negative sentiment"
        })
    
    # Small talk patterns
    for pattern in SMALL_TALK_PATTERNS:
        dataset.append({
            "category": "small_talk",
            "intent": "small_talk",
            "message": pattern,
            "source": "indonesian_buyer_patterns",
            "notes": "Greeting/Polite conversation"
        })
    
    # Confirm order patterns
    for pattern in CONFIRM_ORDER_PATTERNS:
        dataset.append({
            "category": "confirm_order",
            "intent": "confirm_order",
            "message": pattern,
            "source": "indonesian_buyer_patterns",
            "notes": "Purchase intent"
        })
    
    # Multi-intent patterns
    for pattern in MULTI_INTENT_PATTERNS:
        dataset.append({
            "category": "multi_intent",
            "intent": "multi_intent",
            "message": pattern,
            "source": "indonesian_buyer_patterns",
            "notes": "Multiple intents in one message"
        })
    
    # Check product patterns
    for pattern in CHECK_PRODUCT_PATTERNS:
        dataset.append({
            "category": "check_product",
            "intent": "check_product",
            "message": pattern,
            "source": "indonesian_buyer_patterns",
            "notes": "Product availability inquiry"
        })
    
    # Edge cases
    for category, patterns in EDGE_CASE_PATTERNS.items():
        for pattern in patterns:
            dataset.append({
                "category": "edge_case",
                "intent": f"edge_{category}",
                "message": pattern,
                "source": "indonesian_buyer_patterns",
                "notes": f"Edge case - {category}"
            })
    
    return dataset


def export_to_csv(dataset, output_path="/tmp/training_dataset.csv"):
    """Export dataset to CSV for training."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["category", "intent", "message", "source", "notes"])
        writer.writeheader()
        writer.writerows(dataset)
    
    print(f"Exported {len(dataset)} messages to {output_path}")
    return output_path


def export_to_json(dataset, output_path="/tmp/training_dataset.json"):
    """Export dataset to JSON for ML training."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    
    print(f"Exported {len(dataset)} messages to {output_path}")
    return output_path


def print_statistics(dataset):
    """Print dataset statistics."""
    print("=" * 60)
    print("TRAINING DATASET STATISTICS")
    print("=" * 60)
    print()
    
    # Total
    print(f"Total messages: {len(dataset)}")
    print()
    
    # By category
    print("By Category:")
    categories = {}
    for item in dataset:
        cat = item["category"]
        categories[cat] = categories.get(cat, 0) + 1
    
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        pct = 100 * count / len(dataset)
        print(f"  {cat:20} {count:4} ({pct:5.1f}%)")
    
    print()
    
    # By intent
    print("By Intent:")
    intents = {}
    for item in dataset:
        intent = item["intent"]
        intents[intent] = intents.get(intent, 0) + 1
    
    for intent, count in sorted(intents.items(), key=lambda x: -x[1]):
        pct = 100 * count / len(dataset)
        print(f"  {intent:20} {count:4} ({pct:5.1f}%)")
    
    print()
    
    # Sample messages
    print("Sample Messages:")
    samples = random.sample(dataset, min(10, len(dataset)))
    for i, item in enumerate(samples, 1):
        print(f"  {i}. [{item['category']}] {item['message'][:50]}")


if __name__ == "__main__":
    random.seed(42)
    
    dataset = generate_dataset()
    print_statistics(dataset)
    print()
    
    export_to_csv(dataset)
    export_to_json(dataset)
    
    print()
    print("Files created:")
    print("  - /tmp/training_dataset.csv")
    print("  - /tmp/training_dataset.json")
