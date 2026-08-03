# Analisis Dataset & Temuan Chatbot OrderCloser Lite

## 📊 Ringkasan Data Real (740 logs)

### 1. Distribusi Intent
| Intent | Count | % | Keterangan |
|--------|-------|---|------------|
| `faq` | 476 | 64.3% | Mayoritas - pertanyaan umum |
| `unclear` | 188 | 25.4% | Tingginya fallback rate |
| `confirm_order` | 48 | 6.5% | Order konfirmasi |
| `check_product` | 28 | 3.8% | Cek stok produk |

### 2. Status
| Status | Count | % |
|--------|-------|---|
| `reply` | 451 | 60.9% |
| `fallback` | 194 | 26.2% |
| `order` | 48 | 6.5% |
| `error` | 47 | 6.4% |

### 3. Fallback Reasons (194 total)
| Reason | Count | % |
|--------|-------|---|
| `unclear` | 154 | 79.4% ← **MASSAL** |
| `no_faq_match` | 26 | 13.4% |
| `low_confidence` | 8 | 4.1% |
| `no_product_match` | 7 | 3.6% |
| `complaint_signal` | 5 | 2.6% |

### 4. Error Breakdown (47 errors)
- 34 errors dari `intent=unclear` → kemungkinan LLM call gagal atau exception
- 13 errors lainnya (faq check, dll)

---

## 🚨 Temuan Kritis

### 1. **79.4% Fallback = "unclear"**
Ini adalah masalah paling kritis. Dari 194 fallback:
- 154 (79.4%) karena intent unclear
- Artinya classifier **gagal mengenali mayoritas pesan**

**Analisis**: 
- Message tidak terdeteksi keyword → fallback ke owner
- Contoh kemungkinan: "ada kaos hitam?", "bisa COD?", "berapa ongkir"
- MockLLMClient pakai keyword matching sederhana, tidak robust

### 2. **Tidak Ada User Message di Database**
- 0 dari 740 logs punya `user_message`
- Kita buta terhadap apa yang sebenarnya ditanyakan buyer
- Hanya bisa tebak dari `response` dan `intent`

**Contoh response yang bisa diinfer**:
```
- "Garansi produk kami 1 bulan..." → pasti ada yang tanya garansi
- "Rp 150.000" → pasti ada yang tanya harga
- "Kaos hitam size L tersedia" → pasti ada yang tanya stok
```

### 3. **Multi-Intent Tidak Ditangani**
Dari response patterns, terlihat buyer sering tanya banyak hal dalam 1 pesan:
- Harga + stok + ongkir
- Produk A + produk B

Classifier hanya pilih 1 intent → informasi lain terlewat.

### 4. **Complaint Signal Ada Tapi Tidak Di-action**
- 5 pesan terdeteksi `complaint_signal=True`
- Tapi intent tetap `faq` atau `unclear`
- Bot tidak memberi response empati khusus

### 5. **Error Rate 6.4%**
- 47 dari 740 chat error
- Mayoritas dari `intent=unclear` yang gagal diproses
- Berarti ada masalah di LLM atau pipeline, bukan cuma "pesan tidak dikenali"

---

## 🎯 Rekomendasi Prioritas (Berbasis Data Real)

### HIGH PRIORITY (Paling Impact)

#### 1. **Perbaiki Classifier - Deteksi Intent Lebih Robust**
- Masalah: 154/194 fallback = "unclear"
- Solusi:
  - Tambah fuzzy matching (difflib/ratio)
  - Expand keyword lists untuk tiap intent
  - Tambah NLP lightweight (spaCy/indonesian-nlp)

#### 2. **Capture User Messages**
- Masalah: 0 data user message
- Solusi:
  - ✅ Sudah ditambahkan kolom `user_message`
  - Update `insert_chat_log()` untuk capture
  - Mulai collect untuk chat baru

#### 3. **Tambah Small-Talk Handler**
- Masalah: "Halo", "Hai", emoji → fallback semua
- Solusi:
  - Pre-processing node sebelum classify
  - Template responses untuk sapaan
  - Hemat LLM cost + turunkan fallback rate

### MEDIUM PRIORITY

#### 4. **Complaint-Specific Response**
- Masalah: 5 complaint signals, tidak di-action
- Solusi:
  - Tambah intent `complaint` atau `has_complaint_signal=True` → special handling
  - Tambah empathy prefix: "Mohon maaf kak, kami akan segera..."

#### 5. **Multi-Intent Parsing**
- Masalah: Buyer tanya banyak hal dalam 1 pesan
- Solusi:
  - Split pesan berdasarkan "?" atau konjungsi
  - Classify tiap segment
  - Merge results

#### 6. **Error Handling Improvement**
- Masalah: 47 errors (6.4%)
- Solusi:
  - Better logging untuk debug errors
  - Fallback chain untuk LLM (sudah ada, tapi perlu diperbaiki)
  - Retry mechanism

### LOW PRIORITY (Nice-to-Have)

#### 7. **Active Learning Pipeline**
- Simpan unhandled queries → review mingguan → tambahkan ke FAQ

#### 8. **Analytics Dashboard**
- Containment rate, CSAT, unhandled intents per minggu

---

## 📋 Next Steps

### Langkah 1: Perbaiki Data Capture (Hari Ini)
- ✅ Tambah `user_message` kolom - DONE
- Update `nodes.py` untuk capture - DONE
- Test dengan chat baru

### Langkah 2: Perbaiki Classifier (1-2 Hari)
- Expand keyword lists di MockLLMClient
- Tambah fuzzy matching
- Re-test dengan synthetic dataset

### Langkah 3: Tambah Small-Talk Handler (1 Hari)
- Pre-processing node
- Template responses
- Reduce fallback rate

### Langkah 4: Koleksi Real Conversations (Minggu Ini)
- Jalankan bot dengan user_message capture
- Export minimal 200 conversations
- Analisis pattern untuk improve classifier

---

## 💡 Pertanyaan untuk Anda

1. **Apakah bisa akses log WhatsApp/Fonnte?** - Bisa ambil pesan real buyer untuk dataset training
2. **Berapa banyak chat per hari?** - Untuk estimasi coverage needed
3. **Apa kategori pertanyaan paling sering?** - Fokus improvement di sana

---

## 📈 Metrics yang Perlu Dipantau

| Metric | Target | Current (Estimasi) |
|--------|--------|-------------------|
| Containment Rate | >80% | ~40% (tinggi unclear fallback) |
| Fallback Rate | <20% | ~26% |
| Error Rate | <5% | ~6.4% |
| Avg Response Time | <3s | ? |
| CSAT | >4/5 | ? (belum ada tracking) |

