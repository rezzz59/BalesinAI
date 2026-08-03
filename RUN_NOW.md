# CARA MENJALANKAN SEKARANG

## 1. Buka Terminal Baru

Buka terminal di folder ini:
```
/media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
```

## 2. Jalankan Server (2 terminal terpisah)

### Terminal 1 - Uvicorn:
```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Terminal 2 - Ngrok:
```bash
ngrok http 8000
```

## 3. Ambil URL dari Ngrok

Di terminal ngrok, akan muncul:
```
Forwarding    https://xxxx-xxxx-xxxx.ngrok-free.app -> http://localhost:8000
```

Copy URL tersebut (contoh: `https://xxxx-xxxx-xxxx.ngrok-free.app`)

## 4. Set Webhook di Fonnte

Buka https://dashboard.fonnte.com → Devices → pilih device → Webhook:

Isi:
```
https://xxxx-xxxx-xxxx.ngrok-free.app/webhook/whatsapp/
```

**(Jangan ada spasi di awal/akhir!)**

## 5. Test

Kirim pesan "tes" ke WhatsApp Anda.

## 6. Cek Log

Di terminal uvicorn, akan muncul log saat webhook dipanggil.
