# Dataset Analysis & Evaluation Results

## Summary
- Total chat logs in database: **740 rows**
- Historical logs with user messages: **0** (kolom user_message belum pernah dicatat)
- Synthetic test messages created: **62 messages**

## Evaluation Results (MockLLMClient)

### Pass Rate: 13.3% (8/60)

### Breakdown by Category:
| Category | Pass | Total | Rate |
|----------|------|-------|------|
| unclear | 8 | 8 | 100% |
| faq | 0 | 10 | 0% |
| check_product | 0 | 8 | 0% |
| confirm_order | 0 | 6 | 0% |
| small_talk | 0 | 6 | 0% |
| complaint | 0 | 8 | 0% |
| multi_intent | 0 | 4 | 0% |
| edge_cases | 0 | 10 | 0% |

**Note**: "unclear" pass karena "Halo", "Test", emoji, dll memang di-classify sebagai "unclear" oleh MockLLMClient.

## Issues Found

### 1. Tidak Ada Kategori "small_talk"
MockLLMClient dan prompt system hanya support 4 intents:
- `faq`
- `check_product`
- `confirm_order`
- `unclear`

Tidak ada kategori untuk:
- Sapaan (halo, selamat pagi, siang, sore)
- Ucapan terima kasih
- Stiker/emoji-only messages

**Dampak**: Small talk langsung di-fallback ke owner, meningkatkan workload owner.

### 2. Complaint Signal ≠ Intent
MockLLMClient mendeteksi complaint signal (`has_complaint_signal=True`) tapi **tidak mengubah intent** ke kategori khusus.

Contoh: "Barang rusak, mau refund"
- Expected: `complaint`
- Got: `unclear` (dengan has_complaint_signal=True)

**Dampak**: Bot tidak merespons dengan empathy yang sesuai untuk komplain.

### 3. Multi-Intent Tidak Ditangani
Contoh: "Baju biru ready? Kalau ready saya order"
- Ada 2 intent dalam 1 pesan: check_product + confirm_order
- Classifier hanya memilih 1 intent

**Dampak**: Salah satu intent terlewat.

### 4. Edge Cases Tidak Optimal
- Message kosong: `""` → unclear (OK)
- Punctuation only: `"!!!"` → unclear (OK, tapi response mungkin aneh)
- Typo: `"B-aru ready?"` → unclear (seharusnya bisa di-match)
- Mixed language: `"Bhs inggris dong"` → unclear

## Recommendations

### Immediate Fixes (High Priority)

1. **Tambah Small-Talk Handler**
   - Tambahkan pre-processing sebelum classify_intent
   - Message sapaan → balas template sederhana tanpa LLM
   - Contoh: "Halo" → "Halo Kak! Ada yang bisa kami bantu? 😊"

2. **Tambah Intent "complaint"**
   - Update MockLLMClient dan prompt classifier
   - Saat has_complaint_signal=True, set intent="complaint"
   - Tambahkan empathy prefix dalam compose_reply

3. **Improve Typo Tolerance**
   - Tambahkan fuzzy matching untuk keyword detection
   - Normalisasi karakter (hapus `-`, uppercase, dll)

### Medium Priority

4. **Multi-Intent Detection**
   - Parse pesan menjadi multiple intents
   - Handle dengan multiple lookups

5. **Active Learning Pipeline**
   - Simpan unhandled queries
   - Review mingguan → tambahkan ke FAQ/katalog

### Data Collection Improvements

6. **Capture User Messages**
   - Sudah ditambahkan `user_message` kolom ke chat_log
   - Mulai capture untuk semua chat baru

## Next Steps

1. Implement small-talk handler
2. Add complaint intent
3. Improve typo tolerance
4. Update evaluation script untuk testing dengan real LLM

## Dataset Files

- `/tmp/chat_dataset.csv` - 500 historical logs (tanpa user_message)
- `/tmp/synthetic_dataset.csv` - 62 synthetic test messages
- `/tmp/eval_results.csv` - Evaluation results
