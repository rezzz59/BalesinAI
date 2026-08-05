# DEPLOY CHECKLIST — Go-Live Balesin.ai

Checklist lengkap sebelum produk **go-live / publish**. Jangan lewatkan bagian
Sekuriti — beberapa key sempat terekspos di chat & docs earlier dan wajib di-rotate.

> Konvensi: `[x]` = selesai, `[ ]` = belum. Nilai key ada di `.env` (tidak di-commit).

---

## 1. Sekuriti — Rotasi & Bersihkan Key (WAJIB, PRIORITAS 1)

Semua key di bawah **wajib di-rotate** sebelum go-live karena pernah terekspos di
chat/docs/dll. Bukan soal apakah masih dipakai — kalau pernah terlihat di luar,
asumsikan bocor.

| Key | Provider | Cara Rotate |
|-----|----------|-------------|
| `FONNTE_API_KEY` | https://fonnte.com | Generate ulang di dashboard → update `.env` |
| `GEMINI_API_KEY` | Google Cloud Console | Rotate/create baru → update `.env` |
| `ADACODE_API_KEY` | https://adacode.ai | Regenerate → update `.env` |
| `ENCRYPTION_KEY` | lokal | `python scripts/gen_encryption_key.py` → update `.env` |
| `WEBHOOK_AUTH_TOKEN` | lokal | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `secrets/sheets-sa.json` | Google Cloud | Cek & rotasi service account jika perlu |

**Setelah rotate:**
- [ ] Update semua nilai di `.env`
- [ ] Restart server
- [ ] Test round-trip WhatsApp ulang (webhook → jawaban → notifikasi group)
- [ ] Scrub nilai lama dari `git history`: `git filter-repo` / BFG (lihat bagian 6)
- [ ] Dokumen lama: `TROUBLESHOOT.md` sudah di-scrub ke `<redacted>`

---

## 2. Sekuriti — Kontrol Akses

- [ ] `.env` & `secrets/` ter-ignore (sudah benar di `.gitignore`)
- [ ] **Aktifkan webhook auth** — saat ini di-skip di dev (`app/main.py`,
      komentar "SKIP in dev mode"). Wajib pakai Bearer/HMAC sebelum terbuka ke publik
- [ ] Pastikan endpoint admin (`/admin`, `_check_admin_auth`) butuh token — tidak terbuka bebas
- [ ] CORS disetel ketat (`allow_origins=["*"]` sekarang — batasi ke domain sendiri)
- [ ] `/debug/reset-all` hanya loopback (sudah ada guard) — pastikan tidak ter-expose

---

## 3. Infrastruktur & Deployment

- [ ] **Host permanen** (bukan ngrok), pilih salah satu:
  - Render / Railway / VM + Docker, atau
  - Vercel + backend terpisah
- [ ] **Persistent disk** untuk SQLite (`CHECKPOINTER_DB_PATH`) — kalau ephemeral,
      data hilang tiap redeploy. Opsional: migrasi ke Postgres
- [ ] **Domain + HTTPS** — gunakan `deploy/Caddyfile.example` (Caddy auto-TLS) atau CDN
- [ ] **Webhook URL permanen** → arahkan di dashboard Fonnte
  `https://<domain>/webhook/whatsapp/`
- [ ] Healthcheck terpasang (`/health`) & monitoring (uptime + log)
- [ ] Startup script / systemd berjalan otomatis (bukan manual `nohup`)

---

## 4. Data & Tenant

- [ ] Review isi Google Sheet (77 FAQ + 3 katalog) — angka/paket benar sebelum customer lihat
- [ ] Tenant produksi bersih: rename `balesin-ai-7d4b` → `balesin-ai`
- [ ] Hapus tenant test: `demo`, `default`, `default_tenant`, `test_tenant_123`,
      `083135333166`, `klinik_baru`, `test-order-demo`
- [ ] Bersihkan data uji (chat_log 29 entri, orders dummy) — atau reset DB awareness
- [ ] `owner_wa_number` tenant produksi = group admin final (`120363427473292076@g.us`)
- [ ] `fonnte_device_id` = `083135333166` (sudah benar di tenant ini)

---

## 5. LLM & Bot

- [ ] `LLM_BACKEND` produksi sudah ditentukan (`adacode` sedang aktif — konfirmasi)
- [ ] Fallback chain (Adacode → Gemini → Anthropic) lengkap dengan key valid semua
- [ ] Pastikan **latency < ~30 detik** (batas webhook Fonnte) —
      jangan sampai satu backend yang down membuat webhook timeout
- [ ] Evaluasi kualitas: sesekali classifier salah klasifikasi ("butuh coding ngga?" →
      unclear). Pertimbangkan evaluasi berkala sebelum skala besar
- [ ] (Opsional) tambahkan reranker / hybrid scoring untuk naik kualitas FAQ

---

## 6. Git Hygiene

- [ ] Cek key lama tidak ada di `git history`:
  ```bash
  git log -S 'Bvv7nJZ' --oneline
  git log -S 'ai-fonnte' --oneline
  ```
- [ ] Jika ada, scrub dengan `git filter-repo --invert-paths --path` atau BFG,
      lalu force-push (hati-hati, akan tulis ulang history)
- [ ] Pastikan commit message tidak memuat key/nomor

---

## 7. Test Terakhir (Smoke Test) Sebelum Publish

- [ ] `/health` 200
- [ ] Kirim pesan WA asli → balasan bot benar (cek harga/stok dari sheet)
- [ ] Kirim pesan random → fallback terpicu → notifikasi masuk group admin
- [ ] Simulasi order → order tercatat di dashboard + notifikasi group
- [ ] Landing page (`/`) & halaman marketing semua 200
- [ ] Uptime monitor berjalan

---

## Catatan Arsitektur (rekap singkat)

- **Sumber fakta (harga/stok)** = hanya dari Google Sheets (deterministik).
  LLM hanya parse intent + rangkai kalimat; `validate_reply` memblokir angka/ukuran inventif
- **Webhook**: payload Fonnte `device` → dipetakan ke tenant via `get_tenant_by_device`
  (10.x tak bisa langsung, tenant id = nama merchant)
- **Notifikasi admin**: `owner_wa_number` boleh nomor pribadi ATAU group ID;
  guard `_is_self_notify` cegah notifikasi ke nomor device sendiri
- **Tenant aktif saat ini**: `balesin-ai-7d4b` (saas, 80 embeddings, ready)