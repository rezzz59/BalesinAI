# Analisis Bias Dataset Chatbot

## Pertanyaan
Apakah dataset yang ada akan membias system saat inference?

## Jawaban
**Tidak terlalu berbahaya**, karena sistem punya 3 lapis protection:

1. **FAQ Fast Path** - Exact/prefix matching untuk pertanyaan yang ada di dataset
2. **Semantic Search** - Vector similarity untuk generalisasi variasi kata
3. **LLM Composition** - Gemini API untuk handle bahasa natural & fallback

## Risiko Bias

### 1. Domain Specific
- Dataset fokus pada "kaos", "harga", "warna"
- User bisa tanya: "baju", "clothing", "price"
- **Mitigasi**: Semantic search + LLM

### 2. Bahasa/Formalitas
- Dataset formal (sopan)
- User bisa slang: "yg", "brp", "gimana"
- **Mitigasi**: LLM composition handle

### 3. Intent Out-of-Scope
- Hanya 4 intent: faq, check_product, confirm_order, unclear
- User dengan intent lain dapat fallback
- **Mitigasi**: LLM compose context-aware reply

### 4. Multi-language
- Dataset Indonesia
- User bisa pakai English
- **Mitigasi**: LLM composition (Gemini multilingual)

## Rekomendasi

1. **Expand FAQ** - Tambah variasi kata di Google Sheets
2. **Monitor Fallback Rate** - Kalau >20%, dataset kurang lengkap
3. **Synonym Mapping** - Tambah mapping kata sinonim
4. **Regular Update** - Export chat logs bulanan untuk update dataset

## Kesimpulan
Sistem sudah dirancang untuk universal dengan LLM layer. Dataset lokal hanya untuk fast-path & context, bukan satu-satunya sumber kebenaran.
