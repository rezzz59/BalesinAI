# Troubleshooting WhatsApp Webhook

## Status Saat Ini

✅ **Fonnte Token Baru**: `Bvv7nJZGPsYAmWZ4BPej` (sudah di `.env` dan DB)
✅ **Tenant DB**: `default` dan `default_tenant` sudah di-update dengan nomor owner yang benar
⚠️ **Server**: Terus mati karena sandbox restrictions

## Cara Menjalankan Manual

Buka terminal dan jalankan:

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot

# Start server
nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &

# Start ngrok
nohup ngrok http 8000 --log=stdout > /tmp/ngrok.log 2>&1 &

# Tunggu 5 detik, lihat URL
sleep 5
curl -s http://127.0.0.1:4040/api/tunnels | python3 -c "import sys,json; d=json.load(sys.stdin); [print(t['public_url']) for t in d['tunnels']]"
```

## Konfigurasi Webhook di Fonnte Dashboard

Setelah dapat URL ngrok, setting di https://dashboard.fonnte.com:

| Setting | Value |
|---------|-------|
| **Webhook URL** | `https://YOUR-Ngrok-URL.ngrok-free.dev/webhook/whatsapp/` |
| **Authorization** | `Bearer S4bfYPjfqWCZMm7j2dUAfAbiJB-Kb2b74Bat1T8UyYM` |
| **Custom Header** | `X-Tenant-ID: default_tenant` |

## Test Manual dengan Python

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
.venv/bin/python test_webhook.py
```

## Cek Log

```bash
# Lihat log server
tail -f /tmp/uvicorn.log

# Lihat log ngrok
tail -f /tmp/ngrok.log
```

## Masalah Umum

### 1. Device Disconnected
```bash
# Test kirim pesan langsung
.venv/bin/python -c "
import asyncio
from app.services.fonnte import FonnteGateway
from app.config import get_settings
s = get_settings()
g = FonnteGateway(api_key=s.fonnte_api_key)
asyncio.run(g.send_message('6283135333166', 'Test'))
"
```

### 2. Tenant Not Found
Pastikan di Fonnte webhook header ada:
- `X-Tenant-ID: default_tenant`

### 3. 401 Unauthorized
Pastikan token Bearer sesuai: `S4bfYPjfqWCZMm7j2dUAfAbiJB-Kb2b74Bat1T8UyYM`

## Payload Fonnte yang Diterima

Berdasarkan dokumentasi Fonnte, payload webhook memiliki field:
- `device`: nomor device Fonnte
- `sender`: nomor pengirim (tanpa +)
- `message`: teks pesan
- `inboxid`: ID conversation
- `senderlid`: Lid identifier
- `name`: nama pengirim
- `timestamp`: timestamp pesan
