# Research Prompt: Context-Aware Customer Service Chatbot untuk UMKM

## Cara Pakai

Copy bagian **PROMPT** di bawah (di antara `--- PROMPT START ---` dan `--- PROMPT END ---`) ke sesi Claude / GPT / Gemini lain. Dia akan kerjakan riset tanpa bias arsitektur kita, lalu kita bandingkan hasilnya.

---

## PROMPT START

Anda adalah arsitek AI customer service yang diminta riset dan rekomendasi. **JANGAN implementasi kode.** Fokus: **riset, sintesis pola, rekomendasi desain**.

### Konteks Sistem Kami

Kami menjalankan chatbot WhatsApp untuk UMKM Indonesia (1-3 SKU, owner balas manual untuk setelah-penjualan). Tech stack:

- **Frontend**: WhatsApp via Fonnte (webhook → POST /webhook/whatsapp/)
- **Backend**: FastAPI + LangGraph (compiled graph dengan node)
- **Memory**: SQLite (chat log) + checkpointer
- **LLM**: Anthropic Claude Haiku 4.5 / Google Gemini 3.1-flash-lite (switchable via env)
- **Knowledge source**: Google Sheets (FAQ sheet + Catalog sheet)
- **Owner notification**: Fonnte ke nomor owner

**Arsitektur saat ini (linear pipeline)**:

```
START
  → classify_intent (LLM)
      → (confidence < 0.6 OR intent=="unclear") → fallback_human → write_chat_log → END
      → else lookup_catalog
          → (faq AND no answer) OR (check_product AND no match) → compose_reply_fallback → fallback_human → END
          → else compose_reply (LLM) → send_whatsapp (Fonnte) → write_chat_log → END
```

**Intent categories saat ini** (Literal type):
- `faq` — pertanyaan umum (harga, ongkir, jam buka, payment)
- `check_product` — pertanyaan ketersediaan/varian produk
- `confirm_order` — buyer mau order
- `unclear` — pesan kacau / di luar topik

**Lookup logic**: tokenize pesan, first-match row yang punya 1+ kata overlap (sudah di-improve dengan stopword ID + scoring 0.3 threshold).

**Fallback path**: kalau intent unclear / confidence rendah / no match → kirim ke owner via Fonnte + ack buyer "Sedang kami cek, owner akan follow up ya 🙏".

### Masalah Inti yang Kami Hadapi

Kami baru saja kecewa dengan hasil chatbot di skenario berikut. **Pesan nyata dari buyer**:

> "punya saya pas udah sampe rumah malah kekecilan min, dan nggak sesuai sama dipesanan, saya pesan L malah XL yang sampai"

**Yang terjadi**:
1. LLM klasifikasi → `check_product` (confidence 0.85). **Salah** — ini bukan pertanyaan ketersediaan, ini komplain ukuran.
2. `lookup_catalog` jalan, zero match → masuk browse-list branch → menampilkan 354 varian ready.
3. `match_kind: none` tidak trigger fallback karena intent dianggap "pasti".
4. Bot tidak mengarahkan pesan ke owner, tidak acknowledge komplain.

**Diagnostik kami**: arsitektur *pipeline-based dan kategori-driven* — setiap node cuma lihat label kategori, bukan isi pesan. Begitu klasifikasi meleset, semua node berikutnya ikut salah. Kami menambahkan kategori baru (`complaint`) hanya akan menambah panjang daftar, **tidak menyelesaikan** masalah fundamental bahwa pesan adalah **bermakna ganda atau mengandung banyak aspek sekaligus**.

### Pertanyaan Riset

Untuknya kerjakan riset terhadap **produk AI customer service yang sudah terbukti di industri** — bagaimana mereka menghindari jebakan klasifikasi-kaku dan tetap terdengar seperti manusia. Jawab dengan **sintesis, bukan daftar produk**.

#### 1. Intent Classification vs Contextual Understanding

- Referensi: Intercom Fin, Kustomer ML routing, Zendesk 2026 CX Trends ("contextual intelligence")
- Pertanyaan: apakah mereka masih pakai intent classification sebagai router? Atau ada pendekatan lain (LLM-as-router, semantic routing, intent-free, multi-intent)?
- Carikan: bagaimana mereka handle pesan yang punya **multiple intents** (buyer komplain + tanya retur + mau re-order)?

#### 2. Complaint & After-Sales Handling

- Referensi: Shopee Choki, Tokopedia Natasha, Gorgias, Tidio, WATI
- Pertanyaan: bagaimana mereka mengarahkan pesan komplain, retur, refund, barang rusak, salah kirim ke **tim yang tepat** secara otomatis?
- Carikan: apakah mereka deteksi komplain via keyword, classifier terpisah, atau sinyal lain (sentiment, emoji, foto)?
- Carikan: bagaimana mereka **avoid memaksa buyer menjelaskan dua kali** ketika sudah di-handoff ke human?

#### 3. Conversation Memory & Multi-Turn Context

- Pertanyaan: bagaimana produk-produk di atas mempertahankan konteks **dalam 1 thread** dan **antar thread** (buyer balik 3 hari kemudian)?
- Carikan: berapa context window yang mereka operasikan? Apakah ada summarization/entities extraction per turn?
- Carikan: bagaimana mereka handle **intent drift** (buyer mulai dari tanya ongkir, tiba-tiba komplain, lalu minta refund)?

#### 4. Fallback & Escalation Strategy

- Referensi: Intercom Fin "escalation-first" vs "conversational-first" (Reddit diskusi)
- Pertanyaan: kapan mereka putuskan untuk escalate ke human? **Confidence threshold** saja, atau ada sinyal lain?
- Carikan: bagaimana pesan ke human agent diformat (verbatim inquiry + chat history + extracted intent)?
- Carikan: apakah ada **hybrid** (bot jawab sebagian, transfer untuk sisanya)?

#### 5. Tools (function calling) vs Pure LLM

- Carikan: apakah produk menggunakan **LLM dengan function calling** ke order DB/policy DB, atau retrieval murni (RAG)?
- Carikan: bagaimana mereka mencegah halusinasi pada data sensitif (harga, status order)?

#### 6. Voice & Tone untuk Pasar Indonesia

- Referensi: Chatbot Choki (Shopee), Natasha (Tokopedia), chatbot pulsa HP
- Carikan: bagaimana mereka menangani **bahasa campur, singkatan, slang** ("gpp", "udh", "kekecilan", "men", "min")?
- Carikan: apakah ada **emoji-aware** (buyer pakai emoji marah 😡, mereka detect)?

### Yang Tidak Saya Minta

- Jangan implementasi kode.
- Jangan membahas produk yang tidak relevan (e.g., building chatbot from scratch).
- Jangan daftar panjang vendor — saya butuh **sintesis**, bukan katalog.

### Yang Saya Minta (Output Format)

Tulis **deep-dive per fitur** (saya memilih format ini sebelumnya). Minimal 6 section, satu per pertanyaan riset di atas. Setiap section:

1. **Nama pendekatan** (1-2 kata): mis. "Intent-free routing", "Multi-intent decomposition"
2. **Penjelasan 3-5 kalimat**: apa dan mengapa
3. **Contoh real**: produk mana yang pakai, bagaimana mereka handle kasus konkret
4. **Trade-off**: kelemahan / kapan tidak cocok
5. **Relevansi untuk kami**: apakah applicable untuk UMKM 1-3 SKU, atau overkill?

### Output Structure yang Diminta

```
# 1. Intent Classification vs Contextual Understanding
   [Pendekatan: ...]
   [Penjelasan: ...]
   [Contoh: ...]
   [Trade-off: ...]
   [Relevansi: ...]

# 2. Complaint & After-Sales Handling
   ...

# 3. Conversation Memory & Multi-Turn Context
   ...

# 4. Fallback & Escalation Strategy
   ...

# 5. Tools (Function Calling) vs Pure LLM
   ...

# 6. Voice & Tone untuk Pasar Indonesia
   ...

# 7. Sintesis Akhir (WAJIB)
   Pola umum apa yang muncul dari 6 section di atas?
   Apakah ada satu arsitektur dominan di industri 2026?
   Rekomendasi 3-5 prinsip yang bisa kami adopsi, dengan justifikasi.
```

### Constraint

- **Boleh pakai web_search** untuk verifikasi dan temuan terkini.
- **Setiap klaim tentang produk spesifik** harus ada nama sumber (artikel, blog, paper) — boleh di-endnote.
- **Sintesis > katalog**: kalau Anda cuma daftar produk, output ini gagal.
- **Bilingual**: boleh campur Inggris-Indonesia, prefer istilah teknis Inggris dengan konteks Indonesia.

---

## PROMPT END

---

## Insight Kunci dari Riset Mandatori Saya (sebagai pembanding)

Sebelum Anda pakai prompt di atas, ini yang saya temukan dari riset independen saya (sebagai baseline). Bandingkan dengan prompt output nanti — kalau ada gap signifikan, bagus: kita diskusi.

### 1. Intent Classification vs Contextual Understanding
- **Tema 2026: "Contextual intelligence"** — Zendesk CX Trends 2026 dan Kustomer sama-sama menonjolkan ini.
- **Intercom Fin**: "uses natural language understanding to interpret real customer intent and context across a full conversation — not simple keyword matching or scripted paths" (sumber: intercom.com/conversational-ai).
- **Insight**: pasar bergerak dari "intent classifier → routing" ke "**LLM-as-router with semantic understanding**". Kustomer pakai ML "context and intent" untuk routing — bukan pure keyword.

### 2. Complaint & After-Sales
- **Shopee Choki** (research paper, JBIS 2025): buyer banyak pakai untuk "delivery status, refunds, returns" — chatbot sudah punya integrasi OMS, eligibility check policy.
- **Pola yang muncul**: complaint routing pakai **reasoning AI agent** (cek order → cek policy → decide resolution → escalate kalau tidak eligible), bukan rule-based classifier.
- **Hybrid real-time + scroll**: Infobip guide 2026 menekankan chatbot "walk customers through returns, confirm eligibility" bukan hanya classify → forward.

### 3. Conversation Memory
- Mayoritas platform **summarize per turn** + **entity extraction** (order_id, sku, issue_type) untuk cross-session continuity.
- **Gap kami**: kami hanya simpan raw message log, tidak ada entity extraction atau per-turn summary.

### 4. Fallback & Escalation
- **Intercom Fin style conversational-first** vs **escalation-first** masih jadi perdebatan (r/CustomerSuccess thread 2026).
- **Vendor yang menerapkan escalation-first** lebih transparan tapi CSAT lebih rendah pada autonomous run.
- **Pola dominan**: **selective escalation** — bot jawab pertanyaan yang bisa dijawab, escalate kalau ambiguous atau tindakan sensitif.
- **Penting**: pesan ke human agent **harus sudah berisi** extracted intent + history (bukan cuma raw chat log).

### 5. Tools vs RAG
- **Dominan 2026**: **LLM with function calling** ke OMS, policy DB, knowledge base — bukan RAG murni.
- **Cara cegah halusinasi**: setiap **numeric fact** (price, order status) harus datang dari function call, bukan LLM internal knowledge.

### 6. Bahasa Indonesia & WhatsApp
- **Choki論文** (Akademik Indonesia) dan studi perbandingan Shopee/Tokopedia/Lazada: chatbot lokal dilatih dengan **dataset bahasa percakapan Indonesia + slang + code-switching**.
- **Penelitian**: Choki "natural language understanding" di Shopee dilatih pada data lokal, bukan model global.
- **Implikasi**: untuk UMKM, model general-purpose (Claude/GPT) perlu **prompt engineering spesifik** untuk handle slang + emoji.

### Sumber Saya

- [Intercom Fin complete guide & pricing 2026](https://www.getmacha.com/blog/intercom-fin-ai-agent-complete-guide)
- [Intercom Conversational AI](https://www.intercom.com/conversational-ai)
- [Zendesk vs Intercom 2026 (Kustomer)](https://www.kustomer.com/resources/blog/zendesk-vs-intercom/)
- [Zendesk CX Trends 2026 — Contextual Intelligence](https://www.youtube.com/watch?v=048JheRKVig)
- [Zendesk AI vs Fin AI head-to-head 2026 (Kustomer)](https://www.kustomer.com/resources/blog/zendesk-vs-fin-ai/)
- [11 Best AI Chatbots for Customer Support 2026 (Fin)](https://fin.ai/learn/best-ai-chatbots-customer-support)
- [AI Customer Support 2026: 50+ Adoption + ROI Data Points](https://www.digitalapplied.com/blog/ai-customer-support-statistics-2026-adoption-roi-data)
- [Customer Service Chatbots 2026 Enterprise Guide (Infobip)](https://www.infobip.com/blog/customer-service-chatbots)
- [Best AI Customer Service Chatbots and Agents for E-commerce (2026)](https://letsengaige.com/blog/best-ai-customer-service-chatbot-e-commerce/)
- [Impact of AI-Powered Chatbot Choki on Shopee Users — research paper](https://thejbis.upy.ac.id/index.php/jbis/article/download/327/147)
- [Best AI Chatbot for Shopee Customer Service (2026, SellerAIhub)](https://selleraihub.com/ai-chatbot-for-shopee-customer-service/)
- [Top AI Chatbots for Customer Service in Southeast Asia 2026 (Sobot)](https://www.sobot.io/blog/top-ai-chatbots-customer-service-southeast-asia-2026/)
- [Intercom Fin style chat vs escalation-first AI tradeoffs (Reddit)](https://www.reddit.com/r/CustomerSuccess/comments/1qjr6bt/intercom_fin_style_chat_vs_escalationfirst_ai/)

---

## Langkah Selanjutnya untuk Kami

1. **Anda** paste prompt di atas ke Claude/GPT/Gemini lain (model berbeda dari saya).
2. **Bandingkan** output-nya dengan insight kunci di atas.
3. **Diskusi** dengan saya: sintesis mana yang paling applicable untuk UMKM 1-3 SKU?
4. **Decide**: arah implementasi (rule-based preprocessor, LLM-as-router, atau hybrid).

Cost 0 untuk kita, NPM 0, dan kita dapat **2nd opinion independen** sebelum invest waktu coding.
