# OrderCloser Lite — Fase 1 Design Spec

**Tanggal**: 2026-07-27
**Versi**: 1.0
**Status**: Draft (menunggu review user)

## 1. Ringkasan

Implementasi Fase 1 MVP dari PRD `OrderCloser_Lite_PRD_Final.md`: webhook WhatsApp + LangGraph (intent classification, lookup katalog/FAQ, auto reply, fallback ke manusia) untuk **single tenant**, dideploy lokal + ngrok dengan modal $0.

**Out of scope** (ditunda ke Fase 2/3):
- Payment link generation (Xendit) → Fase 2
- Auto-onboarding multi-tenant → Fase 3
- Admin panel → tidak ada (sesuai PRD)
- Integrasi marketplace real-time → tidak ada (sesuai PRD)

## 2. Goals & Non-Goals

### Goals
- Webhook Fonnte → 200 OK dalam <10 detik (sesuai PRD §3)
- Bearer token auth WAJIB sebelum masuk graph (sesuai PRD §2)
- Intent classification dengan Claude Haiku, threshold confidence tunggal
- Multi-turn stateful via SQLite checkpointer
- Fallback ke owner WAJIB aktif sejak MVP (bukan fase terpisah)
- Unit tests untuk semua logic inti

### Non-Goals
- Payment integration
- Multi-tenant runtime (schema & repo sudah siap, tapi Fase 1 = single row)
- Vector search / semantic lookup di Sheets (pakai keyword match)
- Production-grade observability (cukup structlog JSON)
- CI/CD pipeline otomatis (manual deploy untuk MVP)

## 3. Arsitektur Tingkat Tinggi

### Komponen & Tanggung Jawab

| Komponen | Tanggung Jawab | Bekerja dengan |
|----------|----------------|----------------|
| **FastAPI app** | Menerima HTTP POST webhook, return 200 OK | Fonnte (HTTP), Bearer token verifier |
| **Auth/Signature** | Verifikasi Fonnte Bearer token sebelum masuk graph | Fonnte `Authorization` header, `tenant_repo` |
| **Tenant Repo** | Load konfigurasi tenant (wa_api_key encrypted, google_sheet_id, owner_wa_number) | SQLite `tenant_config` |
| **LangGraph Orchestrator** | State graph: classify → lookup → compose → send, atau fallback | Claude Haiku, Sheets, Fonnte |
| **SQLite Checkpointer** | Persistensi state percakapan per thread (tenant_id + wa_number) | LangGraph runtime (see `app/db/checkpoints.py`) |
| **Chat Log Repo** | Catat hasil percakapan (intent, confidence, response, status) | SQLite `chat_log` |
| **Services Layer** | LLM (Claude Haiku), Sheets (katalog/FAQ), Fonnte (send), Crypto | External APIs |

### Alur Pesan (End-to-End)

```
Fonnte ─POST──> /webhook/whatsapp/{tenant_id}
                       │
                       ▼
              [Bearer token verifier] ── invalid ──> 401
                       │ valid
                       ▼
              [load tenant_config]
                       │
                       ▼
              [LangGraph invoke, thread_id=tenant:wa_number]
                       │
                       ▼
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
 classify_intent   lookup_catalog   fallback_human
 (Claude Haiku)    (Google Sheets)  (Fonnte ke owner)
       │               │
       └──── compose_reply ────> send_whatsapp
                                       │
                                       ▼
                              [chat_log insert]
                                       │
                                       ▼
                                  200 OK ke Fonnte
```

### Prinsip Pemisahan

- **Inbound** (webhook → graph) dan **outbound** (graph → Fonnte) dipisah biar tidak saling tunggu
- Fonnte webhook dibalas `200 OK` segera setelah graph selesai
- Semua external API call di-boundary `services/` — domain logic tidak pernah import SDK eksternal langsung

## 4. Tech Stack & Deployment

| Layer | Pilihan | Alasan |
|-------|---------|--------|
| Runtime | Python 3.11 | Sesuai PRD §7 |
| Web framework | FastAPI | Async support, mudah deploy |
| Orchestration | LangGraph 1.x | Stateful chat workflow |
| LLM | Claude Haiku (`claude-haiku-4-5`) | Murah, cepat, cukup untuk klasifikasi |
| Database | SQLite | MVP volume rendah, sesuai PRD §7 |
| Checkpointer | In-house `SqliteCheckpointer` (see `app/db/checkpoints.py`) | Persistensi state percakapan per thread |
| WA Provider | Fonnte | Bearer token auth sesuai standar PRD §2; paid tier dengan API key |
| Sheets | gspread (service account) | Standard library untuk Google Sheets API |
| Encryption | `cryptography` (AES-GCM 256-bit) | Enkripsi `wa_api_key` at rest |
| Hosting | Local + ngrok | Modal $0 untuk MVP |
| Testing | pytest + pytest-asyncio | Unit tests murni |

## 5. State Graph & Node Spec

### State Schema

```python
class ChatState(TypedDict):
    # Identitas
    tenant_id: str
    wa_number: str              # nomor pembeli
    thread_id: str              # tenant_id + ":" + wa_number
    message_text: str           # pesan masuk
    
    # Hasil klasifikasi
    intent: Literal["faq", "check_product", "confirm_order", "unclear"]
    confidence: float           # 0.0 - 1.0
    
    # Lookup result
    catalog_answer: str | None  # jawaban dari Sheets (FAQ/katalog)
    product_match: dict | None  # kalau intent=check_product
    
    # Output
    reply_text: str             # balasan final
    action: Literal["reply", "fallback", "order"]
    fallback_reason: str | None # kenapa fallback (low_conf / unclear / dll)
    timestamp: datetime
```

### Graph (Transitions)

```
START
  └─> classify_intent
        │
        ├─ intent="faq" ─────────> lookup_catalog (sheet=FAQ)
        │                             │
        ├─ intent="check_product" ─> lookup_catalog (sheet=Katalog)
        │                             │
        ├─ intent="confirm_order" ─> compose_order_reply ─> send_whatsapp ─> END
        │
        ├─ intent="unclear" ─────> fallback_human ─> END
        │
        └─ confidence < 0.6 ──────> fallback_human ─> END
```

Setelah `lookup_catalog` selesai, semua flow lewat `compose_reply` → `send_whatsapp` → END, kecuali confidence rendah yang trigger fallback.

### Detail Tiap Node

**`classify_intent`**
- Prompt ke Claude Haiku dengan few-shot examples (4 intent)
- Output: `{intent, confidence}`
- Latency target: <2 detik

**`lookup_catalog`**
- Baca tab FAQ atau Katalog dari Google Sheets
- Simple keyword/regex match (untuk MVP), bukan vector search
- Cache result per sheet_id selama 60 detik (avoid Sheets API rate limit)

**`compose_reply`**
- Susun balasan natural dari template + jawaban Sheets
- Kalau intent=confirm_order, compose khusus dengan placeholder "owner akan follow up" (payment link di Fase 2)

**`send_whatsapp`**
- POST ke Fonnte API: `/send`
- Pakai `wa_api_key` (decrypted) dari tenant_config
- Retry 3x dengan exponential backoff kalau 5xx

**`fallback_human`**
- Ambil `owner_wa_number` dari tenant_config
- Forward pesan asli pembeli ke owner via Fonnte (wajib, sesuai PRD §3)
- Kirim auto-reply singkat ke pembeli: "Sedang kami cek, owner akan follow up ya 🙏" (default UX, configurable via prompt template di `graph/prompts.py`)
- Set `status="fallback"` di chat_log

### Threshold & Rules

- Default confidence threshold: **0.6** (di-baca dari `config.py`, gampang di-tune)
- Kalau Haiku return `intent="unclear"` → langsung fallback, apapun confidence-nya
- Selalu fallback kalau `lookup_catalog` return None untuk intent FAQ/katalog

## 6. Database Schema

### SQLite

**`tenant_config`** (single row untuk MVP, schema siap multi-tenant)
```sql
CREATE TABLE tenant_config (
    tenant_id           TEXT PRIMARY KEY,
    wa_api_key_encrypted BLOB NOT NULL,    -- encrypted via AES-GCM
    google_sheet_id     TEXT NOT NULL,
    payment_provider    TEXT NOT NULL DEFAULT 'xendit',  -- reserved untuk Fase 2
    owner_wa_number     TEXT NOT NULL,     -- untuk fallback_human
    created_at          DATETIME NOT NULL,
    updated_at          DATETIME NOT NULL
);
```

**`chat_log`**
```sql
CREATE TABLE chat_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id    TEXT NOT NULL,            -- tenant_id:wa_number
    tenant_id    TEXT NOT NULL,
    wa_number    TEXT NOT NULL,
    intent       TEXT,
    confidence   REAL,
    response     TEXT,
    fallback_reason TEXT,
    status       TEXT NOT NULL,            -- 'sent' | 'fallback' | 'error'
    timestamp    DATETIME NOT NULL,
    INDEX idx_thread (thread_id),
    INDEX idx_tenant_time (tenant_id, timestamp)
);
```

**LangGraph checkpointer table** — dibuat oleh `SqliteCheckpointer` (lihat `app/db/checkpoints.py` dan model `Checkpoint` di `app/db/models.py`). Tabel menyimpan pickle state per `(config_key, fnode_id)`.

### Google Sheets (per tenant)

Wajib ada tab:
- `Katalog` — kolom: nama_produk, harga, ready (Y/N), deskripsi
- `FAQ` — kolom: pertanyaan, jawaban
- `Order_Log` — reserved untuk Fase 2

## 7. API Contract

### `POST /webhook/whatsapp/{tenant_id}`

Headers (dari Fonnte):
```
Authorization: <fonnte_api_key>
Content-Type: application/json
```

Body (Fonnte format):
```json
{
  "phone": "+6281234567890",
  "message": "Halo, barang ready ga?",
  "isgroup": false,
  "sender": "+6281234567890"
}
```

Response codes:
- `200` — accepted & processed
- `401` — invalid signature
- `404` — tenant_id not found
- `422` — malformed payload
- `500` — internal error (logged)

### `GET /healthz` — liveness check
### `GET /readyz` — checks SQLite, Sheets, LLM reachable

## 8. Security

1. **Bearer token auth** (wajib, sebelum apa-apa):
   ```python
   auth_header = request.headers.get("Authorization", "")
   if not auth_header.startswith("Bearer "):
       return 401
   provided_token = auth_header[7:]
   if provided_token != settings.fonnte_api_key:
       return 401
   ```
   - Bearer token comparison via constant-time string compare
   - Token Fonnte = `FONNTE_API_KEY` env var (server-side)

2. **Encryption at rest** untuk `wa_api_key_encrypted`:
   - Algoritma: AES-GCM (256-bit)
   - Key dari env var: `ENCRYPTION_KEY` (32 bytes, base64-encoded)

3. **No PII in logs**:
   - Chat log simpan wa_number tapi truncate kalau log ke stdout
   - LLM prompt tidak include phone number, hanya message text

4. **Rate limiting** (basic):
   - Per-thread: max 10 pesan/menit (return 429 kalau lewat)
   - In-memory token bucket

5. **No secrets in code or git**:
   - `.env.example` hanya berisi key names
   - `.env` di-`.gitignore`
   - Encryption key di-generate sekali & simpan manual

## 9. Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...
FONNTE_API_KEY=<your_fonnte_api_key>
GOOGLE_SHEETS_CREDENTIALS_JSON_PATH=./secrets/sheets-sa.json

# Encryption
ENCRYPTION_KEY=<base64-32-bytes>

# LangGraph checkpointer
CHECKPOINTER_DB_PATH=./data/checkpoints.db

# Logging
LOG_LEVEL=INFO

# Confidence threshold (optional, default 0.6)
INTENT_CONFIDENCE_THRESHOLD=0.6
```

## 10. Error Handling

| Failure mode | Response | Action |
|--------------|----------|--------|
| Invalid signature | 401 | Log, no retry |
| Tenant not found | 404 | Log, alert owner manual |
| LLM timeout (>5s) | 200 + fallback | Mark `status="error"`, fallback_human |
| Sheets API error | 200 + fallback | Mark `status="error"`, fallback_human |
| Fonnte send fail | 200 + log error | Retry 3x; kalau gagal mark `status="error"` |
| DB write fail | 200 + log error | Continue, alert (chat_log is best-effort) |

**Prinsip**: selalu return 200 OK ke Fonnte kalau request sudah tervalidasi, biar Fonnte tidak retry spam. Error internal kita handle via fallback ke owner.

## 11. Project Structure

```
ordercloser-lite/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, lifespan, route mount
│   ├── webhook.py               # POST /webhook/whatsapp/{tenant_id}
│   ├── health.py                # GET /healthz, /readyz
│   ├── config.py                # pydantic-settings, baca .env
│   ├── auth/
│   │   ├── __init__.py
│   │   └── signature.py         # verify_fonnte_bearer_token()
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── state.py             # ChatState TypedDict
│   │   ├── nodes.py             # classify_intent, lookup_catalog, dll.
│   │   ├── graph.py             # build_graph(), compile_graph()
│   │   └── prompts.py           # Prompt templates untuk Haiku
│   ├── services/
│   │   ├── __init__.py
│   │   ├── llm.py               # ClaudeHaikuClient (intent classify)
│   │   ├── sheets.py            # GoogleSheetsClient (FAQ/Katalog)
│   │   ├── fonnte.py            # FonnteGateway (send_message)
│   │   └── crypto.py            # encrypt/decrypt API keys
│   └── db/
│       ├── __init__.py
│       ├── engine.py            # SQLAlchemy engine + session factory
│       ├── models.py            # TenantConfig, ChatLog ORM
│       ├── checkpointer.py     # SQLite checkpointer (SqliteCheckpointer)
│       ├── tenant_repo.py       # get_tenant(), decrypt_api_key()
│       └── chat_log_repo.py     # insert_log()
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # fixtures
│   ├── test_signature.py
│   ├── test_webhook.py
│   ├── test_classify.py
│   ├── test_lookup.py
│   ├── test_fallback.py
│   └── test_crypto.py
├── scripts/
│   ├── seed_tenant.py           # CLI: insert 1 tenant row
│   └── gen_encryption_key.py    # generate random 32-byte key
├── data/
│   ├── .gitkeep
│   └── checkpoints.db           # runtime, di-ignore
├── secrets/
│   └── .gitkeep
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
└── docs/
    └── setup.md
```

## 12. Testing Strategy

**Unit test** untuk MVP:

| File | Coverage |
|------|----------|
| `test_signature.py` | Valid signature → lanjut; invalid → 401; missing header → 401 |
| `test_webhook.py` | Happy path; 404 tenant; 401 signature; 422 payload |
| `test_classify.py` | Mock Haiku return; cek routing ke node berikutnya |
| `test_lookup.py` | Mock Sheets return FAQ/Katalog; cek cache TTL |
| `test_fallback.py` | confidence < 0.6 → fallback; intent="unclear" → fallback; Fonnte send ke owner dipanggil |
| `test_crypto.py` | encrypt/decrypt round-trip; tampered ciphertext raise |

**Mocking strategy**:
- LLM: stub `services.llm.ClaudeHaikuClient.classify`
- Sheets: stub `services.sheets.GoogleSheetsClient.read_range`
- Fonnte: stub `services.fonnte.FonnteGateway.send_message`
- DB: SQLite in-memory per test
- No network calls during tests

**Test command**: `pytest -v`

## 13. Development Workflow

```bash
# Setup
uv venv && uv pip install -e ".[dev]"
cp .env.example .env
# edit .env: ANTHROPIC_API_KEY, ENCRYPTION_KEY, GOOGLE_SHEETS_CREDENTIALS_JSON_PATH

# Seed tenant
python scripts/gen_encryption_key.py
python scripts/seed_tenant.py --tenant demo --sheet-id <id> --wa-number <owner> --api-key <fonnte-key>

# Run dev
uvicorn app.main:app --reload --port 8000

# Expose ke Fonnte
ngrok http 8000

# Test
pytest -v

# Lint/type
ruff check .
mypy app/
```

## 14. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Fonnte downtime | Retry 3x backoff; fallback_human tetap jalan (log error) |
| LLM quota habis | Threshold confidence < 0.6 = fallback otomatis |
| SQLite corrupt | Backup mingguan via cron (manual untuk MVP) |
| Encryption key bocor | Rotate key + decrypt-reencrypt semua `wa_api_key_encrypted` |
| Single-tenant bottleneck | Schema & repo sudah siap multi-tenant, tinggal loop di Fase 3 |
| Laptop mati (modal $0 hosting) | Pilot tahu jam operasional; backup plan fallback manual |

## 15. Open Questions / TBD

- [ ] **Fonnte Bearer token format**: docs perlu dicek saat implementation (header `Authorization: <token>` raw, atau `Authorization: Bearer <token>`). **TBD** — akan dikonfirmasi via Fonnte docs sebelum coding, dan dimasukan ke `verify_fonnte_bearer_token()` dengan header parsing yang sesuai.
- [ ] **Google Sheets service account setup**: user perlu buat service account di Google Cloud Console & share sheet ke email SA. Akan dibuat setup guide terpisah di `docs/setup.md`.

## 16. References

- PRD: `OrderCloser_Lite_PRD_Final.md`
- Fonnte docs: https://api.fonnte.com
- LangGraph 1.x docs: https://langchain-ai.github.io/langgraph/
- Claude Haiku: https://docs.anthropic.com/en/docs/about-claude/models