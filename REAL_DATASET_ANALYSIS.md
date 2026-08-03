# Analisis Dataset Real - OrderCloser Lite

## 📊 Ringkasan Eksekutif

Dari **740 chat logs** yang terekam:
- **Containment Rate**: ~61% (reply + order)
- **Fallback Rate**: ~26% (194 logs)
- **Error Rate**: ~6.4% (47 logs)
- **User Messages Captured**: **0%** ⚠️ KRITIS

---

## 🚨 Masalah Utama

### 1. Tidak Ada User Message (0 dari 740)
Database tidak menyimpan pesan asli dari buyer. Kita hanya bisa tebak dari response.

**Inferensi pertanyaan dari response patterns**:

| Response Pattern | Frekuensi | Inferensi Pertanyaan |
|------------------|-----------|----------------------|
| "Terima kasih pesannya sudah kami terima" | 83x | "Saya mau order" |
| "Garansi produk kami 1 bulan" | 51x | "Garansinya berapa?" |
| "Rp 150.000" | 40x | "Berapa harganya?" |
| "Kaos hitam size L tersedia" | 24x | "Ada stok ka?" |
| "Bisa diganti atau dikembalikan" | 45x | "Kalau rusak gimana?" |
| "Sedang kami cek, owner follow up" | 33x | (unclear/FAQ not matched) |

### 2. Fallback "unclear" Massal (79.4%)
Dari 194 fallback:
- **154 (79.4%)** → intent unclear
- Artinya classifier **gagal mengenali 3 dari 4 pesan fallback**

**Probable causes**:
- Message tidak match keyword yang ada
- Typo/slang tidak ditangani
- Multi-intent tidak dipecah
- Small talk (sapaan) langsung fallback

### 3. Complaint Signal Tidak Di-action
- 5 pesan terdeteksi `complaint_signal=True`
- Tapi intent tetap `faq` atau `unclear`
- Bot tidak memberi response empati khusus

---

## 📈 Distribusi Aktual

### Intent Distribution
```
faq         ████████████████████████████████████  64.3% (476)
unclear     ██████████████                        25.4% (188)
confirm     ████                                  6.5%  (48)
check_prod  ██                                    3.8%  (28)
```

### Status Distribution
```
reply   ████████████████████████████████          60.9% (451)
fallback██████████████                            26.2% (194)
order   ███                                       6.5%  (48)
error   ███                                       6.4%  (47)
```

### Fallback Breakdown
```
unclear        ████████████████████████████████████████████  79.4% (154)
no_faq_match   ████████                                      13.4% (26)
low_confidence ███                                            4.1%  (8)
no_product     ██                                             3.6%  (7)
complaint      █                                              2.6%  (5)
```

---

## 🎯 Rekomendasi Prioritas (Berbasis Data)

### HIGH PRIORITY (Impact Besar)

#### 1. Perbaiki Intent Classifier
**Problem**: 154 fallback karena "unclear"
**Solution**:
- Expand keyword lists (cek FAQ sheets untuk keyword yang sering ditanya)
- Tambah fuzzy matching (difflib/rapidfuzz)
- Normalize input (lowercase, hapus special chars, normalize typo)

#### 2. Capture User Messages
**Problem**: 0 data user message
**Solution**:
- ✅ Sudah ditambahkan kolom `user_message`
- ✅ Update `insert_chat_log()` sudah done
- Test dengan chat baru

#### 3. Tambah Small-Talk Handler
**Problem**: Sapaan → fallback semua
**Solution**:
- Pre-processing node sebelum classify
- Template: "Halo Kak! Ada yang bisa kami bantu? 😊"
- Target: kurangi fallback rate 10-15%

### MEDIUM PRIORITY

#### 4. Complaint-Specific Response
**Problem**: 5 complaint signals, tidak ada response khusus
**Solution**:
- Tambah empathy prefix: "Mohon maaf kak, kami akan segera..."
- Atau buat intent `complaint` terpisah

#### 5. Error Handling
**Problem**: 47 errors (6.4%)
**Solution**:
- Debug error logs
- Improve fallback chain (sudah ada Anthropic→Gemini→AdaCode)
- Add retry mechanism

---

## 📋 Action Plan

### Phase 1: Data Collection (Hari Ini)
- [ ] Test chat baru dengan user_message capture
- [ ] Export sample conversations (minimal 50)
- [ ] Analisis pattern pertanyaan real

### Phase 2: Classifier Improvement (1-2 Hari)
- [ ] Expand keyword lists dari FAQ sheets
- [ ] Implement fuzzy matching
- [ ] Add typo normalization
- [ ] Re-test dengan synthetic + real data

### Phase 3: Small-Talk Handler (1 Hari)
- [ ] Buat pre-processing node
- [ ] Tambah template responses
- [ ] Measure impact pada fallback rate

### Phase 4: Advanced (Minggu Depan)
- [ ] Multi-intent detection
- [ ] Active learning pipeline
- [ ] Analytics dashboard

---

## 💡 Pertanyaan untuk Anda

1. **Apakah ada akses ke log WhatsApp/Fonnte?**
   - Bisa ambil pesan real buyer untuk dataset training
   - Minimal 100-200 conversations

2. **Berapa volume chat per hari?**
   - Untuk estimasi containment rate needed

3. **Apa kategori FAQ paling sering ditanyakan?**
   - Dari sheets FAQ atau experience sehari-hari

---

## 🎯 Target Metrics

| Metric | Current | Target 1 Bulan | Target 3 Bulan |
|--------|---------|----------------|----------------|
| Containment Rate | ~61% | 75% | 85% |
| Fallback Rate | ~26% | 18% | 10% |
| Error Rate | ~6.4% | 4% | <2% |
| User Messages | 0% | 100% | 100% |

