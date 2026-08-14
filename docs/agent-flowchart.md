# Flowchart Agen Balesin.ai

Diagram ini menjelaskan alur percakapan agent WhatsApp berdasarkan kode di:

- `app/main.py` — webhook & persistence
- `app/graph/graph.py` — routing & graph assembly
- `app/graph/nodes.py` — node implementations
- `app/services/followup.py` — anti-ghosting background loop
- `app/services/order_extractor.py` — deterministic order parsing

Render dengan Mermaid di GitHub, VS Code, atau https://mermaid.live.

---

## 1. Alur Utama (Graph)

```mermaid
flowchart TD
    START([START])

    subgraph MASUK["INPUT WEBHOOK"]
        WB[POST /webhook/whatsapp/]
        AUTH{Valid token?}
        AUTH_NO[401 Unauthorized]
        AUTH_YES{Group / empty?}
        IGN[Ignored]
        TENANT{Tenant ditemukan?}
        T404[404 Not Found]
        SEED[Seed state dari conversation_repo:<br/>order_draft, last_mentioned_product,<br/>messages]
    end

    subgraph PIPELINE["PIPELINE LangGraph"]
        CLS([classify_intent])
        LOOKUP([lookup_catalog])
        CTX([analyze_customer_context])
        COMPOSE([compose_reply])
        COMPOSE_FB([compose_reply_fallback])
        CAPTURE([capture_order])
        SEND([send_whatsapp])
        FALLBACK([fallback_human])
        LOG([write_chat_log])
        END([END])

        CLS -->|auto_followup|COMPOSE
        CLS -->|cancel_order|COMPOSE
        CLS -->|komplain / objektif / unclear<br/>confidence rendah|FALLBACK
        CLS -->|confirm_order|CAPTURE
        CLS -->|faq / check_product|LOOKUP

        LOOKUP -->|faq|CTX
        LOOKUP -->|check_product tanpa match|COMPOSE_FB
        LOOKUP -->|check_product match|CTX

        COMPOSE_FB --> FALLBACK
        CTX --> COMPOSE
        COMPOSE --> SEND
        CAPTURE --> SEND
        SEND --> LOG
        FALLBACK --> LOG
        LOG --> END
    end

    WB --> AUTH
    AUTH -- no --> AUTH_NO
    AUTH -- yes --> AUTH_YES
    AUTH_YES -- yes --> IGN
    AUTH_YES -- no --> TENANT
    TENANT -- no --> T404
    TENANT -- yes --> SEED
    SEED --> CLS

    style CLS fill:#1f6feb,color:#fff
    style SEND fill:#1f6feb,color:#fff
    style FALLBACK fill:#e3b341,color:#000
    style CAPTURE fill:#3fb950,color:#000
```

---

## 2. Rincian Node

### 2.1 classify_intent (`nodes.py:208`)

```mermaid
flowchart TD
    A[Mulai] --> B{message_text diawali<br/>__SYSTEM_AUTO_FOLLOWUP__?}
    B -- ya --> C[intent = auto_followup]
    B -- tidak --> D{message kosong?}
    D -- ya --> E[intent = unclear,<br/>confidence = 1.0]
    D -- tidak --> F[LLM classify_with_history]
    F --> G{Ada verb order + qty?}
    G -- ya --> H[intent = confirm_order<br/>confidence >= 0.9]
    G -- tidak --> I{Ada kata batal<br/>& order_draft aktif?}
    I -- ya --> J[intent = cancel_order]
    I -- tidak --> K[Output intent, confidence,<br/>complaint/objection signal, sentiment]
```

**Catatan:**

- `cancel_order` hanya muncul jika ada `order_draft` non-kosong di state.
- `confirm_order` juga bisa di-override dari `faq` jika pesan mengandung kata order + kuantitas.

### 2.2 compose_reply (`nodes.py:500`)

```mermaid
flowchart TD
    A[compose_reply] --> B{reply_text sudah ada<br/>& action=reply?}
    B -- ya --> C[Kirim verbatim]
    B -- tidak --> D{intent?}
    D -->|confirm_order| E[Template order siap diproses]
    D -->|cancel_order| F[Template batal,<br/>kosongkan order_draft]
    D -->|auto_followup| G[LLM: pesan follow-up]
    D -->|faq / check_product| H[LLM compose + validate_reply]
    H --> I{Valid?}
    I -- ya --> J[action = reply]
    I -- gagal, retry 1 --> K[Strict hint]
    K --> H
    I -- gagal 2x --> L[Verbatim fallback]
    L --> M[Human handoff jika tidak ada data]
```

### 2.3 capture_order (`nodes.py:1013`)

```mermaid
flowchart TD
    A[confirm_order] --> B[extract_items + buyer_info + total]
    B --> C{business_type?}
    C -->|kuliner| D[catering_quote:<br/>ongkir, DP 50%, min order,<br/>tanggal acara]
    C -->|fashion| E[cek size + color wajib]
    C -->|lain| F[cek items saja]
    D --> G{Lengkap?}
    E --> G
    F --> G
    G -- ya --> H[insert_order pending]
    H --> I[Notifikasi owner WhatsApp]
    G -- tidak --> J[action = reply<br/>konsultasi minta field kurang]
    I --> K[action = order<br/>konfirmasi + total]
```

**Catatan multi-turn:**

- `order_draft` dibawa antar pesan lewat `conversation_repo`.
- Buyer bisa menambah/ubah item: "tambah hoodie 1", "jadi 3 kaos hitam".
- Jika memesan ulang setelah konfirmasi, draft kosong kembali.

### 2.4 Order Cancellation

```mermaid
flowchart TD
    A[Pesan: batalkan pesanan saya] --> B{order_draft aktif?}
    B -- ya --> C[classify_intent override<br/>intent = cancel_order]
    C --> D[compose_reply cancel]
    D --> E[order_draft = []]
    E --> F[Webhook persist empty draft]
    B -- tidak --> G[Perlakukan sebagai FAQ/unclear]
```

### 2.5 send_whatsapp (`nodes.py:782`)

```mermaid
flowchart TD
    A[send_whatsapp] --> B{photo_url?}
    B -- ya & pro/enterprise --> C[Kirim gambar + caption]
    B -- tidak --> D{Pesan pertama<br/>dalam thread?}
    D -- ya --> E[Tambahkan intro:<br/>Halo Kak, selamat datang...]
    D -- tidak --> F[Kirim reply_text]
    E --> F
    C --> G[Selesai]
    F --> G
```

---

## 3. Anti-Ghosting Follow-up (`app/services/followup.py`)

```mermaid
flowchart TD
    LOOP[Loop tiap 60 detik] --> SCAN[Scan ChatLog 24 jam<br/>per thread]
    SCAN --> SKIP{Intent auto_followup?<br/>Status ordered/fallback?}
    SKIP -- ya --> SCAN
    SKIP -- tidak --> DELAY{Usia chat >=<br/>followup_delay_minutes?}
    DELAY -- tidak --> SCAN
    DELAY -- ya --> TRIGGER[Kirim state sintetis:<br/>message_text = __SYSTEM_AUTO_FOLLOWUP__ + prompt]
    TRIGGER --> GRAPH[Graph: classify auto_followup<br/>compose reply<br/>send WhatsApp]
```

---

## 4. Order Extraction (`app/services/order_extractor.py`)

```mermaid
flowchart TD
    A[Pesan order] --> B[Extract size + color]
    B --> C[Match product family]
    C --> D{Variant match?}
    D -- ya --> E[Pick variant by<br/>color/size overlap]
    D -- tidak --> F[Token-overlap fallback]
    F --> G{Narrow by color/size?}
    G -- ya --> H[Accept bare token<br/>e.g. jogger + putih]
    G -- tidak --> I[Keep 0.5 threshold]
    E --> J[Return items]
    H --> J
    I --> J
```

---

## 5. Routing Rules

| Fungsi | File | Aturan |
|--------|------|--------|
| `should_fallback` | `graph.py:47` | True jika complaint/objection, `unclear` (kecuali pesan pertama), atau confidence < 0.6. |
| `route_after_classify` | `graph.py:64` | Prioritas: `auto_followup` / `cancel_order` → compose, lalu fallback, lalu `confirm_order` → capture, sisanya lookup. |
| `route_after_lookup` | `graph.py:80` | `faq` → context analyzer; `check_product` tanpa match → fallback; lainnya → context analyzer. |

---

## 6. Persona & Jawaban

Persona per `business_type` disimpan di `app/graph/prompts.py`. Setiap persona menyertakan:

- Sapaan hangat di pesan pertama.
- Akhiri balasan dengan pertanyaan pemandu.
- Gunakan data dari katalog/FAQ; jangan mengarang angka/fakta.

Welcome message custom bisa diatur lewat `onboarding_data.welcome_message` di `TenantConfig`.
