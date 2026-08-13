# Balesin.ai — Intelligent WhatsApp Assistant for SMEs

**Balesin.ai** adalah platform *Customer Service* dan *Sales Automation* berbasis AI yang dirancang khusus untuk UMKM Indonesia. Ditenagai oleh arsitektur **LangGraph**, Balesin.ai mampu menangani interaksi pelanggan di WhatsApp layaknya agen manusia profesional—mengerti konteks percakapan, menangkap detail pesanan otomatis, mendukung pencarian basis pengetahuan, dan menjaga prospek agar tidak hilang (*anti-ghosting*).

---

## 🌟 Fitur Utama

Balesin.ai menghadirkan kemampuan setara platform SaaS *Enterprise* ke dalam ekosistem UMKM dengan arsitektur yang ringan dan efisien:

- **Adaptive AI Persona:** *Merchant* dapat mengatur sendiri gaya bahasa AI (misal: menggunakan sapaan "Sis/Bro") langsung melalui Dashboard. AI akan beradaptasi tanpa melanggar batasan sistem (*guardrails*).
- **Hybrid RAG Knowledge Base:** AI tidak hanya membaca tabel data terstruktur, tetapi juga dapat memproses teks SOP bebas (aturan garansi, jam buka, dll) menggunakan *Retrieval-Augmented Generation* untuk menjawab pertanyaan spesifik dengan akurat.
- **Smart Order Extraction:** Saat pengguna ingin membeli namun datanya kurang lengkap, AI secara otomatis menyodorkan *template* isian (Nama, Ukuran, Warna, Alamat) secara interaktif.
- **Automated Anti-Ghosting (Follow-up):** Rutinitas otomatis di latar belakang yang memantau percakapan tertunda. Jika prospek tidak membalas dalam durasi tertentu, AI akan mengirim pesan *follow-up* yang ramah.
- **Human Handoff (Fallback):** Ketika AI mendeteksi keluhan (*complaint*), keberatan (*objection*), atau pertanyaan di luar konteks toko, percakapan akan langsung diteruskan ke nomor WhatsApp pemilik bisnis.

---

## 💼 Dukungan Vertikal Bisnis

Balesin.ai saat ini dioptimalkan untuk dua sektor vertikal utama dengan logika bisnis bawaan:

### 1. Kuliner & Katering (`kuliner`)
Alur percakapan berfokus pada ketepatan perhitungan dan manajemen pesanan dalam skala besar.
- **Deterministik:** Perhitungan subtotal, ongkos kirim berdasarkan wilayah, DP 50%, dan batas pemesanan minimum divalidasi secara matematis di luar LLM.
- **Context-Aware Enforcement:** Jika pelanggan memesan di bawah batas minimum, AI akan dengan ramah menyarankan penambahan porsi.

### 2. Fashion & Retail (`fashion`)
Alur percakapan berfokus pada ketersediaan varian produk.
- **Verbatim Variant Validation:** Ketersediaan stok, ukuran (contoh: rentang "M-XXL"), dan warna diverifikasi langsung dari katalog. AI tidak diizinkan menciptakan varian fiktif.
- **Visual Engagement:** Dukungan untuk mengirimkan katalog dan foto produk langsung ke WhatsApp pelanggan (pada *tier* langganan pro).

---

## ⚙️ Arsitektur & Teknologi

Sistem dibangun dengan prinsip modularitas dan latensi rendah.

- **Framework Inti:** FastAPI (Backend), LangGraph (Stateful AI Routing).
- **Database:** SQLite (Manajemen *Tenant*, Katalog, Order, Log Percakapan).
- **LLM Gateway:** Ekosistem Multi-LLM (Mendukung integrasi AdaCode, Gemini, Anthropic) dengan fitur *streaming* dan penanganan *failover* otomatis.
- **Komunikasi Pesan:** Integrasi *Webhook* dengan *provider* WhatsApp (Fonnte).
- **Background Tasks:** Sistem *sweep loop* *asynchronous* yang ringan di dalam FastAPI untuk *task* terjadwal (seperti fitur *Anti-Ghosting*).

### Alur Representasi Graph (LangGraph)
```text
WhatsApp Webhook → Intent Classification → Catalog/Knowledge Lookup → Context Analysis → Compose Reply
                        (Auto-Followup)                                (Fallback)      (Order Capture)
```

---

## 🚀 Panduan Instalasi (Quick Start)

### Persyaratan Sistem
- Python 3.10 atau lebih baru.
- Kredensial API LLM (disarankan menggunakan 9Router / AdaCode).

### Langkah Instalasi

1. **Kloning dan Persiapkan *Environment***
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. **Konfigurasi Environment**
   Salin berkas konfigurasi dan isi kunci API yang diperlukan.
   ```bash
   cp .env.example .env
   ```

3. **Jalankan Layanan**
   Jalankan server menggunakan skrip yang telah disediakan (mencakup Uvicorn dan *routing* lokal jika menggunakan Ngrok).
   ```bash
   ./start.sh
   ```
   *Atau jalankan secara manual:* `uvicorn app.main:app --reload --port 8000`

4. **Akses Dashboard**
   Buka `http://localhost:8000/dashboard` di peramban Anda untuk mengatur *AI Behavior*, Katalog, dan *Welcome Message*.

---

## 🧪 Pengujian (Testing)

Proyek ini dilengkapi dengan cakupan *Unit Test* dan *End-to-End Test* ekstensif untuk menjaga stabilitas produksi.

```bash
# Menjalankan seluruh test suite
pytest -q

# Menjalankan spesifik test module
pytest tests/test_graph.py              # Menguji alur percakapan dan state machine
pytest tests/test_reply_validator.py    # Menguji kepatuhan gaya bahasa AI
pytest tests/test_validate_reply.py     # Menguji fitur Anti-Halusinasi
```

---

## 🤝 Pedoman Kontribusi

Balesin.ai dibangun dengan prinsip efisiensi yang tinggi. Bila Anda ingin berkontribusi, harap patuhi panduan berikut:
- **Prioritaskan Kesederhanaan (KISS):** Gunakan fungsi bawaan platform selama memungkinkan sebelum menambahkan dependensi pihak ketiga atau infrastruktur yang berat.
- **Pemisahan Logika:** Semua angka krusial (harga, diskon, ongkir) harus bersumber langsung dari baris data terstruktur (*source row*). LLM hanya bertugas merangkai kata.
- **Test-Driven:** Setiap perubahan yang menyentuh logika *routing*, validasi order, atau transisi *state* wajib disertai dengan pembaruan pada *test suite*.
