# OrderCloser Lite 🤖

AI agent berbasis LangGraph untuk auto-reply WhatsApp + fallback ke owner.

Fitur utama:
- **Classifikasi intent** menggunakan Gemini API (Google GenAI)
- **Auto-reply dinamis** lookup catalog dari Google Sheets
- **Fallback ke owner** otomatis saat tidak bisa bantu
- **Support multi-gateway**: Wablas atau Fonnte WhatsApp gateway

## Quick Start

### 1. Setup Lingkungan

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Konfigurasi `.env`

Buat file `.env` dari template dan sesuaikan:

```bash
cp .env.example .env
nano .env
```

**Variable wajib:**

| Env Var | Description |
|---------|-------------|
| `ANTHROPIC_API_KEY` | Key LLM Anthropic/Gemini |
| `ENCRYPTION_KEY` | Kunci Fernet untuk enkripsi data (generate via `python scripts/gen_encryption_key.py`) |
| `GOOGLE_SHEETS_CREDENTIALS_JSON_PATH` | Path ke service account JSON |

**WhatsApp Gateway (pilih salah satu):**

```env
# Option A: Menggunakan Wablas (default)
WHATAPP_GATEWAY=wablas
WABLAS_BASE_URL=https://api.wablas.example
WABLAS_API_KEY=<your_wablas_key>

# Option B: Menggunakan Fonnte (recommended)
WHATAPP_GATEWAY=fonnte
FONTTE_API_KEY=<your_fonnte_api_key>
```

> 💡 Tip: Ganti `WHATAPP_GATEWAY` di `.env` untuk ganti gateway. API key Fonnte masuk sesuai field `FONTTE_API_KEY` (huruf N ganda).

### 3. Generate Kunci Enkripsi & Seed Tenant

```bash
python scripts/gen_encryption_key.py  # Output: xN5JAsZO7lnG9XkRX9fC3BUV7Wf1WHTC4As4N8rnjlg (simpan di .env)
python scripts/seed_tenant.py \
    --tenant demo \
    --sheet-id YOUR_GOOGLE_SHEET_ID \
    --wa-number +628XXXXXXXXX \
    --api-key <wablas_fonnte_key>
```

### 4. Jalankan Server

```bash
uvicorn app.main:app --reload --port 8000
```

Endpoint webhook: `POST http://localhost:8000/webhook`

## Testing

### Run Test Suites

```bash
# Semua tests
pytest -v

# Khusus Fonnte
pytest tests/test_fonnte.py -v

# LLM classification (mock)
pytest tests/test_llm.py -v
```

Coverage: 80%+ (termasuk FonnteGateway dengan 8 test cases).

### Kirim Pesan Uji Manual

```bash
# Via Fonnte gateway (pastikan WHATSAPP_GATEWAY=fonnte)
python scripts/test_fonnte_send.py
```

## Arsitekture

```
app/
├── main.py                 # FastAPI app, auth middleware, webhook endpoint
├── graph/
│   ├── __init__.py
│   ├── graph.py            # LangGraph StateGraph build (nodes + edges)
│   └── nodes.py            # Node logics: compose_reply, send_whatsapp, fallback_human
├── services/
│   ├── llm.py              # Gemini/Anthropic LLM client
│   ├── sheets.py           # Google Sheets client
│   ├── phone_gateway.py    # Abstract base (PhoneGateway, PhoneGatewayException)
│   ├── fonnte.py           # FonnteGateway implementation (retry, HTTP POST)
│   └── wablas.py           # WablasClient implementation (HMAC signature)
├── auth/                   # Auth middleware & signature verification
└── db/                     # SQLite checkpointer for LangGraph persistence
```
🚀 Built on LangGraph + FastAPI + Google Gemini
