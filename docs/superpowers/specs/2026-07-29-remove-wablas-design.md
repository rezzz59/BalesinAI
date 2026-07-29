# OrderCloser Lite — Remove Wablas Gateway

**Tanggal**: 2026-07-29
**Versi**: 1.0
**Status**: Approved

## 1. Ringkasan

Project OrderCloser Lite saat ini mendukung dua WhatsApp gateway (`wablas` dan `fonnte`) yang dipilih via env `WHATSAPP_GATEWAY`. Karena alasan operasional, project ini tidak lagi menggunakan Wablas. Spec ini menghapus seluruh kode, konfigurasi, test, dan dokumentasi yang merujuk ke Wablas, dan menjadikan Fonnte sebagai single supported gateway.

**Motivasi**: Mengurangi attack surface, menyederhanakan konfigurasi, dan agar PROJECT_CONTEXT.md/README.md tidak lagi menyebut Wablas.

## 2. Goals & Non-Goals

### Goals
- Webhook tunggal menggunakan Fonnte auth (`Authorization: <fonnte_token>`).
- Menghapus modul Wablas: client, HMAC signature, dual-auth branch di webhook.
- Menghapus branching `whatsapp_gateway` di kode dan config — hanya Fonnte yang berlaku.
- Memperbaiki 2 test failure yang sudah ada sebelumnya di `test_fallback.py` (disebabkan drift dari migrasi Wablas→Fonnte).
- PROJECT_CONTEXT.md, README.md, dan spec/plan Fase 1 di-update agar tidak menyebut Wablas.
- Semua test yang sebelumnya pass harus tetap pass.

### Non-Goals
- Tidak menambah fitur baru.
- Tidak menulis ulang logika Fonnte.
- Tidak mengubah interface `PhoneGateway` (tetap dipertahankan untuk konsistensi, walau hanya Fonnte yang mengimplementasikan).

## 3. Arsitektur

**Sebelum:**
- `app/services/wablas.py` — `WablasClient` dengan retry + HMAC signature path di webhook.
- `app/services/fonnte.py` — `FonnteGateway` di belakang `PhoneGateway` ABC.
- `app/auth/signature.py` — `verify_wablas_signature` (HMAC-SHA256 + constant-time compare).
- `app/main.py` — Branch auth Wablas (`Bearer <key>` ATAU `X-Wablas-Signature`) + branch auth Fonnte (`Bearer <token>`).
- `app/config.py` — Field `wablas_base_url`, `wablas_api_key`, `whatsapp_gateway`.

**Sesudah:**
- `app/services/fonnte.py` tetap, menjadi single implementation.
- `app/main.py` — Single auth path: cek `Authorization` header cocok dengan `FONNTE_API_KEY`. Tidak ada branch Wablas.
- `app/config.py` — Hanya `fonnte_api_key` yang terkait gateway. Field Wablas dan `whatsapp_gateway` dihapus.
- `PhoneGateway` ABC tetap, hanya FonnteGateway yang implement.

## 4. Perubahan File

### Dihapus
| Path | Alasan |
|---|---|
| `app/services/wablas.py` | Implementasi Wablas sudah tidak dipakai |
| `app/auth/signature.py` | HMAC verify khusus Wablas |
| `app/auth/__init__.py` | Kosong setelah signature dihapus (cek dulu) |
| `tests/test_wablas.py` | Test untuk modul yang dihapus |
| `tests/test_signature.py` | Test untuk modul yang dihapus |

### Dimodifikasi
| Path | Perubahan |
|---|---|
| `app/main.py` | Hapus branch Wablas; Fonnte jadi default tunggal; rename `_create_phone_gateway` → `_create_fonnte_gateway`; update imports |
| `app/config.py` | Hapus field Wablas; keep `fonnte_api_key` dan default `fonnte_api_key: str = ""` |
| `app/graph/graph.py` | Bersihkan sisa referensi Wablas (cek & hapus import) |
| `tests/test_webhook.py` | Hapus test Wablas signature; tulis ulang auth test untuk Fonnte token |
| `tests/test_fallback.py` | Fix 2 test yang sudah failure (param `wablas_client=` → cocok dengan signature function sekarang) |
| `tests/test_config.py` | Hapus test Wablas config |
| `tests/test_repos.py` | Hapus test Wablas references |
| `tests/test_crypto.py` | Hapus test Wablas references (jika ada) |
| `tests/conftest.py` | Hapus Wablas fixtures/env setup |
| `.env` | Hapus `WABLAS_BASE_URL`, `WABLAS_API_KEY`, `whatsapp_gateway` |
| `PROJECT_CONTEXT.md` | Tulis ulang arsitektur — sebut Fonnte-only |
| `README.md` | Ganti Wablas → Fonnte |
| `docs/superpowers/specs/2026-07-27-ordercloser-lite-fase1-design.md` | Ganti Wablas → Fonnte di section yang relevan |
| `docs/superpowers/plans/2026-07-27-ordercloser-lite-fase1.md` | Ganti Wablas → Fonnte di section yang relevan |

## 5. Perubahan Behavior

- **Webhook auth** sekarang tunggal: cek header `Authorization` cocok dengan `settings.fonnte_api_key`. Tidak ada fallback ke HMAC.
- **Sebelumnya 401 dengan detail "Invalid webhook signature"** digantikan dengan 401 dengan detail "Invalid Fonnte API key" atau generic "Unauthorized".
- Setiap inbound lama yang mengandalkan `X-Wablas-Signature` akan menerima 401.
- Error messages di webhook sekarang generic (sudah di-hardening dari work security sebelumnya): `LLM error` → "Language service unavailable", `WhatsApp gateway error` → "Message delivery failed".

## 6. Test Plan

### Unit/integration test
- `test_webhook.py`:
  - Test auth success dengan token Fonnte valid → 200.
  - Test auth gagal dengan token salah → 401.
  - Test missing Authorization header → 401.
- `test_fallback.py`: fix 2 failure yang menyebut `wablas_client=` (ganti parameter atau rename argumen agar cocok dengan signature `fallback_human` saat ini).
- Test lain yang sudah pass harus tetap pass (`grep -r wablas tests/` harus kosong setelahnya).

### Verifikasi manual
- `grep -r -i wablas app/ tests/ docs/ PROJECT_CONTEXT.md README.md` harus return empty (atau hanya referensi historis di git log).
- Test suite hijau: `python -m pytest`.

## 7. Di Luar Scope

- Tidak menulis Fonnte retry logic yang lebih baik.
- Tidak menambah logging untuk audit gateway.
- Tidak menghapus `PhoneGateway` ABC (dipertahankan untuk konsistensi dan agar diff minimal).

## 8. Risiko

- **Risiko rendah**: Fonnte sudah jadi default di `.env` dan dipakai end-to-end. So existing functional behavior sudah benar.
- **Risiko kecil**: Beberapa spec/plan historical menyebut Wablas — ditulis ulang sebagai Fonnte tanpa mengubah intent aslinya.
- **Tidak ada migrasi data**: tidak ada state Wablas di DB.
