# Balesin.ai — AI Asisten WhatsApp untuk UMKM (Cekat AI Parity)

AI agent berbasis LangGraph yang menjawab chat WhatsApp pelanggan dengan gaya bahasa spesifik toko, menangkap pesanan otomatis, mendukung RAG Hybrid, Anti-Ghosting, dan menyerahkan ke *owner* (fallback) bila obrolan di luar konteks.

> **Fokus pengembangan saat ini: 2 vertikal bisnis + platformnya sendiri.**
> Jangan menambah vertikal baru di luar itu tanpa keputusan eksplisit.

---

## Fitur Unggulan (Arsitektur Setara SaaS Enterprise)

BalesinAI memiliki arsitektur cerdas yang mengadopsi fungsionalitas terbaik dari platform *Customer Service* level Enterprise (seperti Cekat AI) dengan implementasi yang efisien (*Ponytail mode*):

1. **Dynamic Merchant Prompt (AI Behavior)**
   Merchant dapat menyuntikkan instruksi khusus (misal: *"Gunakan sapaan Sis/Bro, dan tawarkan diskon jika order 2 pcs"*) langsung ke otak AI via Dashboard. AI akan otomatis menyesuaikan diri tanpa merusak *guardrails* anti-halusinasi inti.
2. **Unstructured Knowledge Text (SOP Bebas / RAG)**
   AI tidak hanya membaca tabel Excel kaku. Merchant bisa mencantumkan teks panjang (contoh: "Jam operasional kami Senin-Sabtu 09.00-17.00. Kami menerima retur dengan syarat video unboxing."). AI akan menjawab pertanyaan layaknya agen manusia berdasarkan RAG (*Retrieval-Augmented Generation*).
3. **Unified Hybrid Search (Cross-search FAQ & Katalog)**
   Ketika pengguna bertanya *"Berapa harga kemeja?"* (Intent: FAQ), AI secara pintar akan memindai *Katalog Produk* jika data tidak ditemukan di FAQ sheet.
4. **Welcome Message Otomatis**
   Sapaan terformat yang dikirimkan kepada prospek/pelanggan baru pada detik pertama mereka mengirimkan pesan.
5. **AI Auto Follow-up (Anti-Ghosting)**
   Tugas latar belakang (*background loop* di FastAPI) yang memindai percakapan yang "menggantung". Jika prospek tidak membalas selama $X$ menit, AI secara proaktif dan ramah akan mengirim pesan *follow-up* (misal: "Halo Kak, apakah ada yang bisa kami bantu kembali?").
6. **Order Flow Templates**
   Saat pengguna mengetik pesanan yang datanya tidak lengkap, AI otomatis menyodorkan *template* isian (Nama, Ukuran, Warna, Alamat, Tanggal) secara presisi alih-alih hanya berbalas pesan secara acak.

---

## Prioritas Vertikal Bisnis

### 1. Katering / Kuliner (`business_type: "kuliner"`)
Alur paling lengkap — hitungan pesanan **deterministik, tanpa LLM** agar angka
tidak pernah mengarang.

| Kemampuan | Lokasi |
|-----------|--------|
| Kuotasi catering: subtotal + ongkir + DP 50% + minimal porsi + tanggal acara | `app/services/business_rules.py` |
| LLM Enforces Contextual Rules (Minimal porsi ditangani dengan human-like) | `app/graph/nodes.py` (via LLM) |
| Ongkir per wilayah dari sheet `Ongkir` | `find_ongkir` + `local_data_repo` |
| Balasan kuotasi terformat ke pembeli | `format_catering_reply` |
| Pesanan tanpa tanggal acara **tidak dipersist** (draft sampai jadwal dapur dikonfirmasi) | `capture_order` di `app/graph/nodes.py` |

Aturan emas: semua matematika kuotasi bersumber dari katalog + sheet ongkir.
LLM hanya untuk gaya bicara, bukan menghitung angka.

### 2. Fashion / Pakaian (`business_type: "fashion"`)
Cek stok, ukuran, warna, dan pemesanan item katalog.

| Kemampuan | Lokasi |
|-----------|--------|
| Lookup produk + cek stok/ukuran/warna | `lookup_catalog` di `app/graph/nodes.py` |
| Ukuran dalam rentang ("M-XXL") — reply "size L" dianggap valid | `validate_reply` di `app/services/llm.py` |
| List produk ready per keluarga (browse) | `_format_browse_reply` |
| Order Template Incomplete Input | `_format_order_consultation` |

Aturan emas: harga, ukuran, warna, stok **harus verbatim dari source row**.
Validator anti-halusinasi (`validate_reply`) menolak reply yang mengarang angka/ukuran/stok di luar data.

### 3. Platform Inti (Balesin.ai)
Layaknya SaaS CS Chatbot:

- **Multi-tenant** — tiap toko = tenant dengan data lokal sendiri (SQLite).
- **Onboarding self-service** — `app/api/onboard.py`: buat tenant → upload XLSX (FAQ + katalog) → Set Custom Behavior / Welcome Msg / Followup → hubungkan WhatsApp (QR Fonnte) → live.
- **Frontend Dashboard** — Terletak di `static/dashboard.html` memuat metrik bisnis, pengatur *behavior*, *knowledge base*, *welcome message*, dan konfigurasi *Anti-Ghosting*.
- **Style Profiler** — `POST /api/onboard/style` menganalisis teks onboarding
  owner dan menyimpan profil gaya bicara ke `onboarding_data.style_profile`.
- **Persona per vertikal** — `PERSONA_TEMPLATES` di `app/graph/prompts.py`
  (`jualan`, `klinik`, `kuliner`, `fashion`, `saas`).

---

## Alur Percakapan (Graph)

```
WhatsApp → /webhook → classify_intent → lookup_catalog → analyze_context → compose_reply
       (Background) └─ auto_followup                      (fallback_human) └─ confirm_order → capture_order
```

- Intent: `faq` | `check_product` | `confirm_order` | `unclear` | `auto_followup`
- `compose_reply` memakai: source row (fakta verbatim) + persona vertikal + GAYA BICARA TOKO + Custom Behavior merchant.
- Validasi balasan: `validate_reply` (anti-halusinasi) dan `validate_sales_style` (ramah, human-touch, CS expert, anti-sycophancy, wajib tanya 1 pertanyaan pemandu).

---

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # isi LLM_BACKEND + API KEYS (9Router / AdaCode direkomendasikan)
```

Jalankan server (Uvicorn + Background Task):

```bash
./start.sh
# Atau secara manual:
# uvicorn app.main:app --reload --port 8000
```

Dashboard Merchant (Pengaturan UI): `http://localhost:8000/dashboard`
Webhook WhatsApp: `POST http://localhost:8000/webhook`

## Testing

Proyek ini diproteksi oleh 345+ passing Unit Tests.

```bash
pytest -q                 # seluruh suite (100% Passed)
pytest tests/test_graph.py              # alur routing graph
pytest tests/test_reply_validator.py    # aturan gaya balasan
```

## Arsitektur Singkat

```
app/
├── main.py                 # FastAPI, auth, webhook, Auto-Followup (Background Task)
├── api/                    # onboard (self-service), provision, auth
├── graph/
│   ├── graph.py            # StateGraph build + routing (termasuk rute auto_followup)
│   ├── nodes.py            # classify, lookup, compose, order, fallback
│   ├── prompts.py          # semua prompt LLM, Framework CS Ahli, Anti-Sycophancy
│   └── context_analyzer.py 
├── services/
│   ├── llm.py              # klien LLM + Streaming SSE handler
│   ├── followup.py         # Loop worker untuk fitur Anti-Ghosting (Phase 4)
│   ├── business_rules.py   # Aturan domain (determinism order kuliner/fashion)
│   ├── reply_validator.py  # Validasi gaya balasan
│   ├── semantic_search.py  # Cari FAQ/produk semantik
│   └── fonnte.py           # gateway WhatsApp
└── db/                     # SQLite: tenant, user, katalog, order, chat log
```

---

## Aturan Kontribusi (The Ponytail Rule)

- **Do Not Over-engineer**: Skala prioritas harus selalu mencari solusi termudah, asli (`native`), dan tidak menambah tumpukan kode yang rumit. (Contoh: Pekerjaan asinkron *cron* digantikan dengan *loop sweep* yang ringan di dalam `app.main`).
- **Angka = data, bukan LLM.** Semua harga/ongkir/DP/min-order harus dari baris sumber (*source row*).
- **Test What Matters**: Setiap logika esensial (seperti validasi *min-order* katering dan transisi *graph*) wajib meninggalkan *test suite* yang dapat dijalankan secara sinkron maupun asinkron.
