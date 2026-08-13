# Roadmap Pengembangan Arsitektur AI (Cekat AI Parity)

## Phase 1: Dynamic Merchant Prompt (AI Agent Behavior) [HIGH PRIORITY]
- **Goal:** Merchant bisa mengatur gaya bicara dan aturan khusus AI via teks bebas.
- **Implementasi:**
  - Tambah kolom/key `custom_behavior` di JSON `onboarding_data` (tabel `tenant_config`).
  - Update `_persona_for_tenant()` di `nodes.py` untuk membaca dan meng-inject teks ini ke `SALES_CONSULTANT_FRAMEWORK`.
  - Buat endpoint `PUT /api/tenant/{id}/behavior` di `onboard.py`.

## Phase 2: Knowledge Source Text (Unstructured SOP) [HIGH PRIORITY]
- **Goal:** AI bisa membaca teks SOP/FAQ bebas (bukan cuma format tabel/sheet).
- **Implementasi:**
  - Tambah fungsi `replace_knowledge_text()` dan `read_knowledge_text()` di `local_data_repo.py`.
  - Update `lookup_catalog()` di `nodes.py` agar melakukan pencarian RAG di teks ini jika FAQ tabel gagal.
  - Buat endpoint `PUT /api/tenant/{id}/knowledge` di `onboard.py`.

## Phase 3: Welcome Message [MEDIUM PRIORITY]
- **Goal:** Pesan otomatis khusus saat pelanggan pertama kali chat.
- **Implementasi:**
  - Simpan `welcome_message` di `onboarding_data`.
  - Sisipkan logic di `graph.py` (sebelum `classify_intent`): jika `messages` kosong (percakapan baru), *yield* Welcome Message lalu stop/tunggu balasan.

## Phase 4: AI Follow-up (Anti-Ghosting) [MEDIUM PRIORITY]
- **Goal:** Kirim pesan otomatis jika pelanggan tidak membalas dalam durasi tertentu.
- **Implementasi:**
  - Worker/cron job terpisah yang membaca *thread* terakhir yang belum closing.
  - Memanggil node khusus `compose_followup`.

## Phase 5: Evaluation AI (Continuous Learning) [LOW PRIORITY]
- **Goal:** Merchant mengoreksi jawaban AI, otomatis jadi data training/RAG.
- **Implementasi:**
  - Endpoint untuk *submit* koreksi.
  - Simpan di tabel baru `evaluations`.
  - Inject tabel `evaluations` ke `lookup_catalog()`.

## YAGNI (Skipped for MVP)
- Flow Builder Drag & Drop (Intent routing bawaan sudah cukup).
- Multi-Agent Orchestration (Skala UMKM cukup dengan satu agent cerdas).
- Omnichannel (Fokus WhatsApp API/Fonnte dulu).
