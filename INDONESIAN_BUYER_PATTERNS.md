# Pola Pertanyaan Buyer Indonesia - Analisis & Dataset Training

## 📊 Riset: Bagaimana Buyer Indonesia Bertanya di WhatsApp

Berdasarkan riset pasar e-commerce Indonesia (Shopee, Tokopedia, WhatsApp Business) dan pola percakapan UMKM, ini kategori pertanyaan yang paling umum:

---

## 1. FAQ - Pertanyaan Umum (64.3% dari semua chat)

### A. Harga & Pembayaran
| Pattern | Variasi Buyer | Intensitas |
|---------|---------------|------------|
| Berapa harga | "berapaa", "brp", "harga berapa", "mahal ga" | 🔥🔥🔥🔥🔥 |
| Diskon/promo | "ada diskon?", "promo apa", "murah ga?", "murahan" | 🔥🔥🔥🔥 |
|_minimum_order| "min order berapa", "paling sedikit beli berapa" | 🔥🔥🔥 |
| Pembayaran | "bisa bayar pakai apa", "bisa transfer?", "bisa COD" | 🔥🔥🔥🔥 |
| Cicilan | "bisa cicil ga", "bisa Bayar nanti?" | 🔥🔥 |

**Contoh variasi buyer**:
```
"brp min"
"harga berapa"
"mahal ga?"
"ada diskon ga"
"bisa COD ga"
"bayarnya gimana"
"min order berapa pcs"
```

### B. Stok & Ketersediaan
| Pattern | Variasi Buyer | Intensitas |
|---------|---------------|------------|
| Ready stock | "ready?", "ada?", "tersedia?", "ready stock?" | 🔥🔥🔥🔥🔥 |
| Size | "ada size L?", "ukuran berapa", "size M ada" | 🔥🔥🔥🔥🔥 |
| Warna | "ada warna merah?", "warnanya apa aja" | 🔥🔥🔥🔥 |
| Variasi | "varian apa aja", "Ada yang lain?" | 🔥🔥🔥 |

**Contoh variasi buyer**:
```
"ready stock?"
"ada ga?"
"size L ada?"
"warna apa aja"
"ada yg hitam?"
```

### C. Pengiriman & Ongkir
| Pattern | Variasi Buyer | Intensitas |
|---------|---------------|------------|
| Ongkir | "ongkir berapa", "gratis ongkir?", "kirimin ke [kota]" | 🔥🔥🔥🔥🔥 |
| Estimasi | "kapan sampe", "lama ga?", "berapa hari" | 🔥🔥🔥🔥 |
| Area | "kirim ke [kota] bisa ga", "area mana aja" | 🔥🔥🔥🔥 |
| Kurir | "pake kurir apa", "JNE/J&T/SiCepat?" | 🔥🔥🔥 |

**Contoh variasi buyer**:
```
"ongkir ke jakarta brp"
"gratis ongkir?"
"kapan sampe"
"kirim ke bandung bisa?"
"pake ekspedisi apa"
```

### D. Garansi & Retur
| Pattern | Variasi Buyer | Intensitas |
|---------|---------------|------------|
| Garansi | "garansi berapa", "bukan garansi?" | 🔥🔥🔥🔥 |
| Retur | "bisa tukar?", "ganti ga", "return bisa?" | 🔥🔥🔥🔥 |
| Kualitas | "bahannya bagus ga", "awet ga", "tidak cocok" | 🔥🔥🔥 |
| Cacat | "rusak gimana", "jika cacat" | 🔥🔥🔥 |

**Contoh variasi buyer**:
```
"garansinya berapa"
"bisa tukar ukuran?"
"kalau tidak cocok bisa return?"
"bahannya adem ga"
```

### E. Proses Order
| Pattern | Variasi Buyer | Intensitas |
|---------|---------------|------------|
| Cara order | "gimana cara pesan", "belinya dimana" | 🔥🔥🔥🔥 |
| Minimal | "min order berapa", "pesan sedikit bisa" | 🔥🔥🔥🔥 |
| Custom | "bisa custom?", "bisa request?" | 🔥🔥🔥 |
| Contoh | "lihat contoh", "foto produk" | 🔥🔥🔥 |

**Contoh variasi buyer**:
```
"gimana cara order"
"belinya dimana"
"bisa custom warna?"
"foto produknya dong"
```

---

## 2. CHECK_PRODUCT - Mencari Produk Spesifik (3.8%)

### Pola Umum
```
[produk] + [spesifikasi] + [pertanyaan]
```

**Contoh**:
```
"kaos hitam size L ada?"
"hoodie fleece olive ready?"
"celana cargo warna coklat size 32"
"dress merah muda ready stock?"
```

### Variasi buyer Indonesia:
- **"ada ga [produk]?"** - paling umum
- **"[produk] ready?"** - singkat, umum di WhatsApp
- **"mencari [produk]"** - formal
- **"bisa cari [produk]?"** - sopan
- **"[produk] size X warna Y"** - langsung spesifikasi

---

## 3. CONFIRM_ORDER - Konfirmasi Pembelian (6.5%)

### Pola Umum
```
[kata kunci order] + [jumlah] + [spesifikasi (opsional)]
```

**Contoh**:
```
"saya pesan 2"
"order 3 pcs"
"beli 1 ya"
"oke ready, saya ambil"
"booking dulu"
```

### Variasi buyer Indonesia:
- **"saya order"** - formal
- **"pesan"** - casual
- **"beli"** - paling casual
- **"ambil"** - informal
- **"booking"** - untuk reserve
- **"oke, saya ambil"** - setelah dapat info

---

## 4. COMPLAINT - Keluhan (5 dari 740 logs, tapi underreported)

### Pola Umum
```
[sinyal negatif] + [masalah] + [tindakan yang diinginkan]
```

**Contoh**:
```
"udah 3 hari ga sampai"
"barang rusak, mau refund"
"ga sesuai foto"
"kecewa banget"
"batal aja"
```

### Kategori complaint:
1. **Delivery delay** - "lama ga sampai", "kapan sampe"
2. **Product damage** - "rusak", "cacat", "jelek"
3. **Not as described** - "ga sesuai", "beda foto"
4. **Wrong item** - "salah kirim", "bukan ini"
5. **Threaten to leave** - "batal", "komplain ke sosmed"

---

## 5. SMALL_TALK - Sapaan & Chat Umum (TIDAK ADA di sistem kita)

### Pola Umum
```
[sapaan] + [emoji] + [tanpa pertanyaan]
```

**Contoh**:
```
"Halo"
"Hai"
"Selamat pagi"
"Siang kak"
"Sore"
"👋"
"🙏"
"👍"
"Test"
```

### Statistik:
- ~15-25% dari semua chat di WhatsApp business adalah small talk
- Saat ini: SEMUA small talk → fallback ke owner
- Opportunity: Reduce fallback rate 10-15%

---

## 6. MULTI-INTENT - Pertanyaan Ganda (Sering terjadi)

### Pola Umum
```
[pertanyaan 1]? [konjungsi] [pertanyaan 2]
```

**Contoh**:
```
"Ready ga? Kalau ready saya order"
"Berasal dari mana? Bisa kirim ke Surabaya?"
"Harga berapa? Bisa diskon?"
"Ada size M? Kalau ada saya pesan"
```

### Kompleksitas:
- 2 intents dalam 1 pesan
- Classifier saat ini hanya pilih 1
- Informasi kedua terlewat

---

## 7. EDGE CASES - Kasus Khusus (Sering muncul)

### Typo & Varian Ejaan
```
"brp" → "berapa"
"ga" → "tidak"
"gk" → "nggak"
"ygy" → "kayaknya"
"tpi" → "tapi"
"gmna" → "gimana"
"knp" → "kenapa"
"ksna" → "kesana"
"dmna" → "dimana"
"kmren" → "kemarin"
```

### Mixed Language
```
"Ready stock?" (Indo + English)
"Can I order?" (English)
"Stock available?" (English)
"DM for price" (SLANG)
```

### Singkatan WhatsApp
```
"yg" → "yang"
"td" → "tadi"
"sm" → "sama"
"dr" → "dari"
"ke" → "ke"
"dgn" → "dengan"
"brp" → "berapa"
"tmn" → "teman"
"org" → "orang"
"lg" → "lagi"
```

### Single Word Queries
```
"Harga"
"Stok"
"Ready"
"COD"
"Ongkir"
"Size"
```

---

## 8. INFERRED PATTERN DARI DATA REAL KITA

Berdasarkan 740 logs (response patterns), pertanyaan yang paling sering:

| Response Pattern | Estimated Question |
|-----------------|-------------------|
| "Terima kasih pesannya sudah kami terima" (83x) | "Saya mau order" |
| "Garansi produk kami 1 bulan" (51x) | "Garansinya berapa?" |
| "Rp 150.000" (40x) | "Berapa harganya?" |
| "Kaos hitam size L tersedia" (24x) | "Ada stok kaos hitam size L?" |
| "Bisa diganti atau dikembalikan" (45x) | "Kalau rusak bisa tukar?" |
| "Sedang kami cek, owner follow up" (33x) | (pertanyaan tidak match FAQ) |
| "Untuk informasi harga..." (20x) | "Berapa harga [produk]?" |
| "Hitam, Putih, Navy..." (4x) | "Warnanya apa aja?" |

---

## 📋 REKOMENDASI DATASET TRAINING

### Kategori untuk Classifier:
```python
INTENTS = {
    "faq": [
        "harga", "berapa", "mahal", "murah", "diskon", "promo",
        "ongkir", "kirim", "pengiriman", "estimasi", "sampai",
        "garansi", "retur", "tukar", "ganti",
        "cara order", "beli", "pesan", "min order",
        "bantuan", "info", "tanya"
    ],
    "check_product": [
        "ready", "stok", "tersedia", "ada",
        "size", "ukuran", "warna", "varian",
        "tanya produk spesifik"
    ],
    "confirm_order": [
        "order", "pesan", "beli", "ambil", "booking",
        "saya mau", "oke saya", "lanjut"
    ],
    "complaint": [
        "rusak", "cacat", "ga sesuai", "kecewa", "batal",
        "refund", "kembalikan", "komplain", "marah"
    ],
    "small_talk": [
        "halo", "hai", "pagi", "siang", "sore", "malam",
        "thanks", "terima kasih", "makasih", "terima"
    ]
}
```

### Dataset Synthetic yang Perlu Ditambahkan:
- [ ] Typo variations: "brp", "ga", "gmna", "yg", "td"
- [ ] Single word: "harga", "stok", "ready"
- [ ] Mixed language: "Ready stock?", "Can order?"
- [ ] Multi-intent: "Ready? Kalau ready order"
- [ ] Emotional: "Kecewa banget", "Sudah 3 hari"
- [ ] Short queries: "brp", "ready?", "ada?"

