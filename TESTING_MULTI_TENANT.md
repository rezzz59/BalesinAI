# Testing Multi-Tenant Functionality

## Current Tenants in Database

| tenant_id | google_sheet_id | owner_wa_number |
|-----------|-----------------|-----------------|
| demo | [shared] | +6283142298645 |
| default | [shared] | +6283142298645 |
| default_tenant | [shared] | +6283142298645 |
| test_tenant_123 | [shared] | +6283142298645 |
| klinik_test | FAKE_SHEET_ID_KLINIK | +6281234567890 |
| klinik_sehat | FAKE_SHEET_KLINIK_123 | +6281234567890 |
| cafe_kopi | FAKE_SHEET_CAFE_456 | +6289876543210 |

## How to Test with Different Tenant

### Step 1: Create Real Google Sheet

1. Buat Google Sheet baru untuk klinik
2. Format yang sama dengan FAQ sheet existing:
   - Kolom A: pertanyaan
   - Kolom B: jawaban
   - Kolom C-F: opsional (keywords, metadata)
3. Share sheet ke service account email
4. Copy Sheet ID dari URL

### Step 2: Update Database

```bash
sqlite3 data/checkpoints.db
UPDATE tenant_config 
SET google_sheet_id = 'YOUR_REAL_SHEET_ID' 
WHERE tenant_id = 'klinik_sehat';
```

### Step 3: Test Webhook

```bash
curl -X POST http://localhost:8000/webhook/whatsapp/ \
  -H "X-Tenant-ID: klinik_sehat" \
  -H "Authorization: Bearer YOUR_GLOBAL_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "pengirim": "6281234567890",
    "pesan": "jam buka"
  }'
```

### Step 4: Verify Response

Response harus berbeda tergantung tenant:
- `toko_fashion` → reply tentang kaos
- `klinik_sehat` → reply tentang jam buka klinik
- `cafe_kopi` → reply tentang menu cafe

## Key Points

1. **Data Isolation**: Setiap tenant punya sheet sendiri
2. **No Cross-Contamination**: FAQ klinik tidak tercampur dengan FAQ toko
3. **Independent Scaling**: Tambah tenant baru tanpa impact tenant lain
4. **Shared Infrastructure**: LLM dan semantic search bisa shared (hemat biaya)

## Production Checklist

- [ ] Validasi tenant_id di setiap request
- [ ] Encrypt semua API keys
- [ ] Rate limiting per tenant
- [ ] Audit log untuk tracking akses
- [ ] Backup per-tenant data
- [ ] Monitoring error rate per tenant
