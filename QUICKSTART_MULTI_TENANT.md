# Quickstart: Multi-Tenant Setup

## Langkah Cepat Untuk Client Baru

### 1. Daftar Client
```bash
python3 -c "
from app.db.tenant_repo import insert_tenant
from app.services.crypto import encrypt_api_key
from app.config import get_settings

settings = get_settings()
insert_tenant(
    tenant_id='client_baru',
    wa_api_key_encrypted=encrypt_api_key('sk_fonnte_XXX', settings.encryption_key),
    google_sheet_id='1abc123def456...',  # Sheet ID dari Google Sheets
    owner_wa_number='+6281234567890',
)
print('✅ Tenant created!')
"
```

### 2. Buat Google Sheet
1. Buka https://sheets.google.com
2. Buat sheet baru
3. Isi dengan format:
   - Kolom A: pertanyaan
   - Kolom B: jawaban
   - Kolom C-F: kosongkan
4. Share sheet ke service account email
5. Copy Sheet ID dari URL (contoh: `1bf1bg1s8bjc...`)

### 3. Test Webhook
```bash
curl -X POST http://localhost:8000/webhook/whatsapp/ \
  -H "X-Tenant-ID: client_baru" \
  -H "Content-Type: application/json" \
  -d '{"wa_number": "6281234567890", "message_text": "test"}'
```

## Struktur Database

```sql
-- Tabel tenant_config
tenant_id     | google_sheet_id          | owner_wa_number
--------------|--------------------------|------------------
default       | 1bf1bg1s8bjc53v092pZ...  | +6283142298645
klinik_sehat  | 1xyz789abc...            | +6281234567890
cafe_kopi     | 1mno456pqr...            | +6289876543210
```

## Cara Kerja

```
Request masuk dengan X-Tenant-ID
        ↓
  Lookup di DB
        ↓
  Dapat config (sheet_id, api_key)
        ↓
  Init SheetsClient dengan sheet_id mereka
        ↓
  Process graph dengan data mereka
        ↓
  Reply via gateway mereka
```

## Important Notes

- Setiap tenant punya data TERPISAH
- Tidak ada cross-contamination antar tenant
- Tambah tenant baru tidak perlu deploy ulang
- LLM (Gemini) bisa shared (hemat biaya)
