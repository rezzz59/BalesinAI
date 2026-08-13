# Balesin.ai — AI Asisten WhatsApp untuk UMKM

AI agent (LangGraph) yang menjawab chat WhatsApp pelanggan dengan suara milik
toko, menangkap pesanan, dan menyerahkan ke owner saat tidak bisa dijawab.

> **Fokus pengembangan saat ini: 2 vertikal bisnis + platformnya sendiri.**
> Jangan menambah vertikal baru di luar itu tanpa keputusan eksplisit.

---

## Prioritas Pengembangan

### 1. Katering / Kuliner (`business_type: "kuliner"`)
Alur paling lengkap — hitungan pesanan **deterministik, tanpa LLM** agar angka
tidak pernah mengarang.

| Kemampuan | Lokasi |
|-----------|--------|
| Kuotasi catering: subtotal + ongkir + DP 50% + minimal porsi + tanggal acara | `app/services/business_rules.py` |
| Deteksi tanggal acara & wilayah kirim dari pesan pembeli | `business_rules.extract_event_date/extract_wilayah` |
| Ongkir per wilayah dari sheet `Ongkir` | `find_ongkir` + `local_data_repo` |
| Balasan kuotasi terformat ke pembeli | `format_catering_reply` |
| Pesanan tanpa tanggal acara **tidak dipersist** (draft sampai jadwal dapur dikonfirmasi) | `capture_order` di `app/graph/nodes.py` |

Aturan emas: semua matematika kuotasi bersumber dari katalog + sheet ongkir.
LLM hanya untuk gaya bicara, bukan angka.

### 2. Fashion / Pakaian (`business_type: "fashion"`)
Cek stok, ukuran, warna, dan pemesanan item katalog.

| Kemampuan | Lokasi |
|-----------|--------|
| Lookup produk + cek stok/ukuran/warna | `lookup_catalog` di `app/graph/nodes.py` |
| Ukuran dalam rentang ("M-XXL") — reply "size L" dianggap valid | `validate_reply` di `app/services/llm.py` |
| List produk ready per keluarga (browse) | `_format_browse_reply` |
| Foto produk terkirim ke pembeli (tier Pro/Enterprise) | `send_whatsapp` + `_find_photo_url` |

Aturan emas: harga, ukuran, warna, stok **harus verbatim dari source row**.
Validator anti-halusinasi (`validate_reply`) menolak reply yang mengarang
angka/ukuran/stok di luar data.

### 3. Platform Inti (Balesin.ai)
Layanan AI asisten WhatsApp untuk UMKM Indonesia.

- **Multi-tenant** — tiap toko = tenant dengan data lokal sendiri (SQLite).
- **Onboarding self-service** — `app/api/onboard.py`: buat tenant → upload XLSX
  (FAQ + katalog) → hubungkan WhatsApp (QR Fonnte) → test → live.
- **Style Profiler** — `POST /api/onboard/style` menganalisis teks onboarding
  owner dan menyimpan profil gaya bicara (`formality`, `emoji_density`,
  `tone`, `key_phrases`) ke `onboarding_data.style_profile`. Profil ini
  disuntikkan ke prompt compose sebagai blok `GAYA BICARA TOKO`, jadi bot
  meniru suara toko asli (lihat `_style_profile_block` di `app/graph/nodes.py`
  dan `STYLE_PROFILER_SYSTEM` di `app/graph/prompts.py`).
- **Persona per vertikal** — `PERSONA_TEMPLATES` di `app/graph/prompts.py`
  (`jualan`, `klinik`, `kuliner`, `fashion`, `saas`). Profil gaya toko
  menimpa sapaan default persona.
- **Fallback ke owner** — pesan komplain/keberatan/tidak jelas diteruskan ke
  WhatsApp owner dengan ringkasan alasan (`fallback_human`).

---

## Alur Percakapan (Graph)

```
WhatsApp → /webhook → classify_intent → lookup_catalog → analyze_context → compose_reply
                                        (fallback_human)  └─ confirm_order → capture_order
compose_reply → send_whatsapp → write_chat_log
```

- Intent: `faq` | `check_product` | `confirm_order` | `unclear`
- `compose_reply` memakai: source row (fakta verbatim) + persona vertikal +
  GAYA BICARA TOKO dari style profiler.
- Validasi balasan: `validate_reply` (anti-halusinasi angka/ukuran/stok) dan
  `validate_sales_style` (≤6 kalimat, ≤2 emoji, tepat 1 pertanyaan pemandu di
  akhir, anti-sycophancy).

---

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # isi LLM_BACKEND + ADACODE_API_KEY (default backend)
```

LLM backend: `adacode` (default, direkomendasikan) → `gemini` → `anthropic`,
dengan fallback otomatis antar-backend.

Jalankan server:

```bash
uvicorn app.main:app --reload --port 8000
```

Webhook WhatsApp: `POST http://localhost:8000/webhook`

## Testing

```bash
pytest -q                 # seluruh suite (~335 test)
pytest tests/test_style_profiler.py     # style profiler
pytest tests/test_reply_validator.py    # aturan gaya balasan
pytest tests/test_validate_reply.py     # anti-halusinasi
pytest tests/test_graph.py              # alur graph
```

Simulasi E2E nyata (LLM asli, graph penuh, tanpa kirim WhatsApp):
`ml-work/tmp/opencode/sim_e2e_fokus.py` — studi kasus fashion + katering.

## Arsitektur Singkat

```
app/
├── main.py                 # FastAPI, auth, webhook
├── api/                    # onboard (self-service), provision, auth
├── graph/
│   ├── graph.py            # StateGraph build + routing
│   ├── nodes.py            # classify, lookup, compose, order, fallback, log
│   ├── prompts.py          # semua prompt LLM + PERSONA_TEMPLATES + STYLE_PROFILER
│   └── context_analyzer.py # pemetaan konteks pelanggan
├── services/
│   ├── llm.py              # klien LLM (AdaCode/Gemini/Anthropic/Mock) + validator
│   ├── business_rules.py   # aturan catering (deterministik)
│   ├── reply_validator.py  # validasi gaya balasan
│   ├── order_extractor.py  # ekstrak item/qty/harga dari pesan order
│   ├── semantic_search.py  # cari FAQ/produk secara semantik
│   ├── local_data.py       # data upload tenant (FAQ/katalog/ongkir)
│   └── fonnte.py           # gateway WhatsApp
└── db/                     # SQLite: tenant, user, katalog, order, chat log
```

---

## Aturan Kontribusi

- **Jangan tambah vertikal baru** (selain kuliner/fashion/inti) tanpa konfirmasi.
- **Angka = data, bukan LLM.** Semua harga/ongkir/DP/min-order dari source row.
- **Suara toko = style profiler.** Jangan hardcode gaya bicara baru di prompt
  selain lewat `PERSONA_TEMPLATES` + `GAYA BICARA TOKO`.
- Setiap logika non-trivial wajib meninggalkan satu test yang bisa dijalankan.
