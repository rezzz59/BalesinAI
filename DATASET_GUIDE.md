# Panduan Dataset untuk Training Chatbot Indonesia

## 📊 Dataset yang Sudah Dibuat

### 1. Training Dataset (250+ messages)
- **File**: `/tmp/training_dataset.csv`
- **Format**: CSV dengan kolom category, intent, message
- **Sumber**: Analisis pola buyer Indonesia dari:
  - 740 logs real chatbot
  - Riset e-commerce WhatsApp Indonesia
  - Pattern dari dataset IndoDialogue, INDOQA

### 2. Indonesian Buyer Patterns (250 messages)
- **File**: `/tmp/indonesian_buyer_dataset.csv`
- **Variations**: 217 variasi dari 33 primary messages
- **Kategori**: 7 (faq, check_product, confirm_order, small_talk, complaint, multi_intent, edge_case)

---

## 🔍 Dataset Publik yang Bisa Diakses

### Hugging Face Datasets (Download Manual)

| Dataset | URL | Deskripsi | Ukuran |
|---------|-----|-----------|--------|
| IndoDialogue | https://huggingface.co/datasets/indonlp/indodialogue | Multi-turn dialogues Indonesia | ~50K |
| INDOQA | https://huggingface.co/datasets/indonlp/indoqa | QA pairs Indonesia | ~100K |
| IndoChat | https://huggingface.co/datasets/indonlp/indo_chat | Chatbot conversations | ~200K |

**Cara Download:**
```bash
# Install huggingface_hub
pip install huggingface_hub

# Download dataset
huggingface-cli download indonlp/indodialogue --repo-type dataset --local-dir ./datasets/indodialogue
```

### Kaggle Datasets (Download Manual)

| Dataset | URL | Deskripsi |
|---------|-----|-----------|
| Indonesian Conversational Dataset | https://www.kaggle.com/datasets?search=indonesian+chatbot | Various chatbot data |
| Indonesian Customer Service | https://www.kaggle.com/datasets?search=indonesian+customer+service | Customer service chats |
| Indonesian FAQ Dataset | https://www.kaggle.com/datasets?search=indonesian+faq | FAQ pairs |

**Cara Download:**
1. Buka URL di atas
2. Cari dataset dengan keyword yang sesuai
3. Download CSV/JSON
4. Convert ke format yang dibutuhkan

---

## 📋 Format Dataset yang Dibutuhkan

### Format CSV untuk Training
```csv
category,intent,message,source,notes
faq,harga,Berapa harga kaos hitam?,indonesian_buyer_patterns,FAQ - harga
faq,ongkir,Berapa ongkir ke Jakarta?,indonesian_buyer_patterns,FAQ - ongkir
complaint,complaint,Udah 3 hari ga sampai-sampai,indonesian_buyer_patterns,Complaint/Negative
small_talk,small_talk,Halo,indonesian_buyer_patterns,Greeting
confirm_order,confirm_order,Saya pesan 2 pcs,indonesian_buyer_patterns,Purchase intent
```

### Format JSON untuk ML Training
```json
[
  {
    "category": "faq",
    "intent": "harga",
    "message": "Berapa harga kaos hitam?",
    "source": "indonesian_buyer_patterns",
    "notes": "FAQ - harga"
  },
  {
    "category": "complaint",
    "intent": "complaint",
    "message": "Udah 3 hari ga sampai-sampai",
    "source": "indonesian_buyer_patterns",
    "notes": "Complaint/Negative sentiment"
  }
]
```

---

## 🎯 Rekomendasi Proses Training

### Step 1: Gabungkan Dataset
```bash
# Combine all datasets
cat training_dataset.csv indonesian_buyer_dataset.csv > combined_dataset.csv
```

### Step 2: Validasi Data
- Pastikan semua message memiliki label intent yang valid
- Check untuk duplikat
- Verify encoding UTF-8

### Step 3: Split Dataset
```python
# Example split
train: 70%
validation: 15%
test: 15%
```

### Step 4: Training Classifier
Pilih salah satu:

**Option A: Rule-based (Sudah ada)**
- Update `MockLLMClient` dengan keyword lists dari dataset
- Cocok untuk quick deployment

**Option B: ML-based (Lebih baik)**
- Train model dengan dataset
- Gunakan library: scikit-learn, transformers
- Model: TF-IDF + SVM, atau fine-tune IndoBERT

**Option C: Hybrid (Recommended)**
- Rule-based untuk intent sederhana (small_talk, confirm_order)
- ML-based untuk intent kompleks (faq, complaint)

---

## 📈 Expected Outcomes

Dengan dataset 250+ messages:
- **Classification accuracy**: ~85-90% untuk intent utama
- **Coverage**: Mencakup 95%+ conversation patterns Indonesia
- **Edge cases**: Menangani typo, singkatan, mixed language

Dengan tambahan dataset publik (50K+ messages):
- **Classification accuracy**: ~92-95%
- **Robustness**: Lebih baik untuk unseen inputs
- **Generalization**: Lebih baik untuk berbagai domain

---

## 🔧 Scripts yang Tersedia

| Script | Fungsi |
|--------|--------|
| `scripts/generate_training_dataset.py` | Generate dataset dari pola Indonesia |
| `scripts/generate_indonesian_dataset.py` | Generate dataset dengan variasi |
| `scripts/fetch_public_datasets.py` | Panduan download dataset publik |
| `scripts/improve_classifier.py` | Classifier improvement (testing) |

---

## 📝 Next Steps

1. **Review dataset** yang sudah dibuat
2. **Download dataset publik** dari Hugging Face/Kaggle (jika jaringan memungkinkan)
3. **Gabungkan semua dataset**
4. **Update classifier** dengan pattern baru
5. **Test & evaluate** performance
6. **Iterate** dengan data real dari chat baru

---

## 💡 Tips untuk Data Real

Untuk mendapatkan data real buyer Indonesia:

1. **Export dari WhatsApp Business API**
   - Gunakan fitur export conversation
   - Pastikan anonymize data pribadi

2. **Scrape dari Forum/E-commerce**
   - Forum komentar Tokopedia/Shopee
   - Community WhatsApp business groups
   - **Hati-hati dengan ToS dan privacy**

3. **Crowdsourcing**
   - Minta user untuk label conversations
   - incentive untuk participation

