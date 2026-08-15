# Deploy Self-Hosted WhatsApp (WAHA)

Balesin memakai **WAHA** (WhatsApp HTTP API, berbasis Baileys) yang dijalankan
sendiri di VPS — bukan gateway pihak ketiga seperti Fonnte. Keuntungannya:
IP sendiri (tidak kena efek domino ban), nomor sendiri (lebih tepercaya di mata
Meta), data pelanggan tetap di VPS kita, dan kontrol penuh atas delay/rate-limit.

## 1. Jalankan WAHA di VPS

```bash
docker run -d \
  --name waha \
  --restart unless-stopped \
  -p 3000:3000 \
  -e WHATSAPP_API_KEY=GANTI_DENGAN_KEY_RAHASIA \
  -e WHATSAPP_HOOK_URL=https://domain-kamu/webhook/whatsapp/ \
  -v waha_data:/app/.waha \
  devlikeapro/waha:latest
```

- `WHATSAPP_API_KEY` → isi sama dengan `WAHA_API_KEY` di `.env` aplikasi.
- `WHATSAPP_HOOK_URL` → webhook inbound Balesin (optional, session config juga bisa set per-sesi).
- Pin versi image (`:latest` → ganti ke tag tetap misal `:2026.8.1`) agar tidak
  break diam-diam saat Meta ubah protokol. Update rutin terjadwal lebih aman.

Cek status: `curl -H "X-Api-Key: KEY" http://localhost:3000/api/sessions`

## 2. Konfigurasi aplikasi (.env)

```env
GATEWAY_PROVIDER=waha          # waha (default) | fonnte (fallback)
WAHA_BASE_URL=http://localhost:3000
WAHA_API_KEY=GANTI_DENGAN_KEY_RAHASIA
BASE_URL=https://domain-kamu   # untuk webhook + media URL
```

## 3. Alur onboarding (per tenant)

1. Tenant isi nomor WA bisnis → klik "Tampilkan QR".
2. Balesin panggil `POST /api/sessions` (session = `tenant_id`) → ambil QR.
3. Tenant scan QR via **WhatsApp > Perangkat Tertaut > Tautkan Perangkat**.
4. `GET /api/onboard/device/status` polling status sesi → `WORKING` = terhubung.
5. Balesin validasi nomor yang discan cocok dengan yang dimaksud; jika beda,
   sesi di-logout (`DELETE /api/sessions/{session}`) dan status jadi `rejected`.

## 4. Fallback ke Fonnte (darurat)

Jika WAHA down, set `GATEWAY_PROVIDER=fonnte` + isi `FONNTE_API_KEY` /
`FONNTE_ACCOUNT_TOKEN`, lalu restart. Tenant yang sudah paired di WAHA tidak
otomatis pindah — fallback ini untuk tenant baru/transisi.

## 5. Risiko & mitigasi

| Risiko | Mitigasi |
|---|---|
| Meta ubah protokol → Baileys break | Pin versi image, update rutin terjadwal |
| WAHA down | `GATEWAY_PROVIDER=fonnte` sebagai cadangan |
| Ban | Hanya balas chat masuk (tidak broadcast massal); `simulate_human_delay` aktif |
| Sesi hilang saat restart | Volume `waha_data` persist + `--restart unless-stopped` |
