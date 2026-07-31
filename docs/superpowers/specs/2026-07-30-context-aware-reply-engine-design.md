# Design Document: Context-Aware Reply Engine for OrderCloser Lite (Phase 2)

**Date:** 2026-07-30  
**Project:** OrderClores Lite (OrderCloser Lite) MVP → Phase 2 Enhancement  
**Version:** 1.0  

---

## 1. Executive Summary

**Goal:** Transform OrderClores Lite dari bot lookup keyword sembelit menjadi **AI chatbot yang memahami konteks percakapan**, memetakan deskripsi customer ke kondisi kebijakan/policy di Sheets, dan merespons dengan bahasa **sepels sales sebenarnya** — peduli, proaktif, dan akurat.

**Core philosophy:** Focus on **data processing quality** (embedding + semantic search) rather than adding more complexity. Owner UMKM hanya perlu isi Sheets — tidak perlu pikirkan logic apa pun.

---

## 2. Scope & Constraints

### In Scope
- Replace `lookup_catalog()` with **semantic vector search + hybrid scoring**
- Add **context reasoning layer** (`analyze_customer_context`) to map customer descriptions to policy conditions
- Update compose prompts with **sales-style guidelines** (empathy, listener rule, ≤3 sentences + 1 emoji)
- Maintain existing gateway (Fonnte), fallback-to-human mechanism, SQLite logging
- Minimal new dependencies (`sentence-transformers`, `numpy`)

### Out of Scope (Phase 2 only)
- Multi-tenant scaling beyond per-tenant config
- Rich order state / payment confirmation workflows
- Monitoring/alerting dashboard
- Full multi-agent orchestration (will be considered Phase 3)
- Backend OMS integration

### Constraints
- Must work with **local/embedded models** to reduce cost/latency (no API call per embedding for MVP)
- Must preserve backward compatibility with existing `ChatState` schema
- Owner must not need technical training — Sheets interface remains unchanged

---

## 3. Data Schema Changes

### 3.1 New Table: `embedding_cache`

Stores pre-computed embeddings for FAQ, catalog products, and policy rows to avoid re-calculating embeddings on every message.

```sql
CREATE TABLE embedding_cache (
    tenant_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('faq', 'catalog_product', 'policy')),
    source_id TEXT NOT NULL,      -- FAQ row index, product name/code, policy key
    content_hash TEXT NOT NULL,   -- SHA-256 of content text, for cache invalidation on edit
    embedding BLOB NOT NULL,      -- serialized numpy array (float32, shape (384,) for MiniLM)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, source_type, source_id)
);
CREATE INDEX idx_embedding_content_hash ON embedding_cache(content_hash);
```

**Cache invalidation strategy:** When owner edits a row in Sheets, compute `content_hash(new_text)` and update `embedding_cache` record on next load — no full re-embed needed.

### 3.2 Storage Strategy for Vectors

| Option | Description | Recommendation |
|--------|-------------|----------------|
| **Local `sentence-transformers`** | Load model `paraphrase-multilingual-MiniLM-L12-v2` (~120MB), run offline embedding. Supports Bahasa Indonesia well. | ✅ Primary choice — zero API cost, fast once model loaded |
| **LLM API embedding** | Use Anthropic/Gemini embedding endpoint. Slower, costs money. | ⚠️ Fallback if local install fails |
| **Cloud vector DB** | Pinecone, Weaviate, etc. Overkill for single-tenant SMB use case. | ❌ Not for MVP |

Model: `paraphrase-multilingual-MiniLM-L12-v2` from Hugging Face — fine-tuned for cross-lingual similarity, works well for Indonesian, lightweight (384-d vectors).

### 3.3 Recommended Sheets Structure (for owners)

| Sheet | Columns | Notes |
|-------|---------|-------|
| FAQ | `pertanyaan`, `jawaban` | Existing. Add **variant questions** as separate rows for better coverage (e.g., "garansi berapa?", "lama garansi?", "warranty length?") |
| Katalog | `nama_produk`, `deskripsi`, `harga`, `ready`, `colors`, `sizes`, `category` | Existing. `category` helps with semantic grouping |
| Policy (NEW) | `rule_key`, `description`, `conditions`, `examples`, `response_template` | **New sheet** for business rules. Example: rule_key=`return_policy`, description="Return hanya jika rusak dan belum dicuci", conditions=["rusak", "belum_dicuci"], examples=["lubang di leher", "barang sampai rusak"], response_template="Produk eligible retur karena..." |

---

## 4. Semantic Search Component

### 4.1 Hybrid Scoring Formula

Instead of simple keyword overlap score, use:

```
final_score = w_semantic × cosine_similarity(query_vec, candidate_vec) 
              + w_keyword × keyword_overlap_score(message, content_text)
where w_semantic = 0.7, w_keyword = 0.3
```

- **Semantic score** captures meaning: "lubang di leher" ≈ "cacat produk" ≈ "rusak"
- **Keyword score** captures specificity: "kaos hitam ukuran M" harus match ke produk tepat, bukan kategori umum

Threshold: `final_score < 0.45` → trigger fallback (no relevant data found).

### 4.2 Module: `app/services/embeddings.py`

```python
from sentence_transformers import SentenceTransformer
import numpy as np
import pickle

class EmbeddingService:
    """Local sentence-transformers wrapper for multilingual embedding."""

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model = SentenceTransformer(model_name, device='cpu')  # CPU only for safety

    def embed_text(self, text: str) -> np.ndarray:
        """Return normalized 384-d float32 vector."""
        vec = self.model.encode(text, normalize_embeddings=True)
        return vec.astype(np.float32)

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Since both are normalized, dot product = cosine similarity."""
        return float(np.dot(a, b))

    @staticmethod
    def save_vector(vec: np.ndarray, path: str):
        with open(path, 'wb') as f:
            pickle.dump(vec, f)

    @staticmethod
    def load_vector(path: str) -> np.ndarray:
        with open(path, 'rb') as f:
            return pickle.load(f)
```

### 4.3 Module: `app/services/semantic_search.py`

```python
class SemanticSearch:
    """Hybrid semantic + keyword search over cached embeddings."""

    def __init__(self, sheets_client, embedding_service, embedding_cache_repo):
        self.sheets = sheets_client
        self.embed = embedding_service
        self.cache_repo = embedding_cache_repo
        self.stopwords = set(["dan", "dan", "atau", "yang", "ada", "yg", "di", "ke", "dari"])

    def keyword_overlap(self, msg: str, content: str) -> float:
        """Simple bag-of-words overlap excluding stopwords."""
        msg_words = set(msg.lower().replace(/[^\w\s]/g, '').split()) - self.stopwords
        content_words = set(content.lower().replace(/[^\w\s]/g, '').split()) - self.stopwords
        if not msg_words or not content_words:
            return 0.0
        return len(msg_words & content_words) / max(len(msg_words), len(content_words))

    def load_candidates(self, intent: str) -> list[dict]:
        """Load all relevant cached embeddings from cache for given intent."""
        candidates = []
        if intent == 'faq':
            cache_entries = self.cache_repo.get_all('faq')
            for entry in cache_entries:
                candidates.append({
                    'content': entry['content'],  # FAQ pertanyaan + jawaban
                    'type': 'faq',
                    'id': entry['source_id'],
                    'embedding': self.load_vector(entry['embedding_path'])
                })
        elif intent == 'check_product':
            # Catalog products
            products = self.sheets.read_catalog()
            for p in products:
                combined = f"{p['nama_produk']} {p.get('deskripsi', '')}"
                cache_entry = self.cache_repo.get_or_create('catalog_product', p['nama_produk'], combined)
                candidates.append({
                    'content': combined,
                    'type': 'catalog_product',
                    'id': p['nama_produk'],
                    'embedding': self.load_vector(cache_entry['embedding_path'])
                })
        return candidates

    def search(self, message: str, intent: str, top_k: int = 5) -> list[dict]:
        """Run hybrid search, return top-k candidates sorted by final_score."""
        query_vec = self.embed.embed_text(message)
        candidates = self.load_candidates(intent)

        scored = []
        for c in candidates:
            sem_score = self.embed.cosine_similarity(query_vec, c['embedding'])
            kw_score = self.keyword_overlap(message, c['content'])
            final = 0.7 * sem_score + 0.3 * kw_score
            scored.append({**c, 'final_score': final})

        scored.sort(key=lambda x: x['final_score'], reverse=True)
        # Filter out low-confidence matches
        scored = [c for c in scored if c['final_score'] >= 0.45]
        return scored[:top_k]
```

### 4.4 Integration: Modify `lookup_catalog()`

Replace current `lookup_catalog()` in `app/graph/nodes.py`:

```python
def lookup_catalog(state: ChatState, sheets_client: Any) -> dict:
    """Enhanced version using semantic search + context analysis."""
    intent = state["intent"]

    # Initialize services (singleton-ish)
    # embedding_service = get_global_embedding_service()
    # semantic_search = SemanticSearch(sheets_client, embedding_service, embedding_cache_repo)

    try:
        if intent == 'faq':
            results = semantic_search.search(state['message_text'], intent)
            if results:
                top = results[0]
                return {
                    'catalog_answer': top.get('jawaban') or top['content'].split('\n')[1] if '\n' in top['content'] else top['content'],
                    'product_match': None,
                    'match_kind': _to_match_kind(top['final_score'])
                }
            return {}

        if intent == 'check_product':
            results = semantic_search.search(state['message_text'], intent)
            if results:
                top = results[0]
                # Extract product info from content (need to parse back or store separately)
                # Simpler: store product_id in cache instead of just content
                product = find_product_by_name(top['id'])
                if product and product.get('ready') == 'Y':
                    return {
                        'catalog_answer': None,
                        'product_match': product,
                        'match_kind': _to_match_kind(top['final_score'])
                    }
            # Handle browse pattern (same as before)
            ready = sheets_client.list_ready_products()
            if ready:
                return {
                    'reply_text': _format_browse_reply(ready),
                    'action': 'reply',
                    'product_match': None,
                    'catalog_answer': None,
                    'match_kind': 'none',
                }
            return {}

        return {}
    except Exception as e:
        logger.error("semantic_lookup_failed", extra={"error": str(e)})
        return {}
```

---

## 5. Context Reasoning Layer (Key Differentiator)

### 5.1 Purpose

Before composing reply, analyze whether the customer's description maps to any known policy condition(s). This enables the bot to say "I understand your situation" instead of generic responses.

### 5.2 Implementation: `analyze_customer_context()`

New node in graph (file: `app/graph/context_analyzer.py`):

```python
def analyze_customer_context(state: ChatState, llm_client: Any) -> dict:
    """Map customer description to policy/product conditions via LLM reasoning."""
    retrieved_rows = state.get('catalog_answer') or state.get('product_match') or []
    
    # Build context prompt
    policy_info = ""
    if state.get('policy_sheet_rows'):
        for row in state['policy_sheet_rows']:
            policy_info += f"\n{row['rule_key']}: {row['description']}"

    prompt = f"""
Anda adalah analis konteks pesanan. Tugaskan: pemetasikan deskripsi pelanggan ke kondisi-kondisi dalam data yang diberikan.

PESAN PELANGGAN: {state['message_text']}

DATA RELEVAN:
Faq/Produk: {retrieved_rows}
Kebijakan: {policy_info}

TUGAS:
1. Kondisi/kriteria apa saja dari data yang DIPENUHI oleh situasi pelanggan ini? (list string)
2. Apa jenis issue/keluhan jika ada? (misal: product_damage, wrong_size, delivery_delay, none)
3. Apa intent utama? (faq, check_product, confirm_order, complaint, return_request)
4. Berapa tingkat keyakinan mapping ini? (skor 0.0-1.0)
5. Mengapa Anda melakukan pemetaan ini? (justifikasi singkat 1-2 kalimat)

FORMAT HARUS JSON TIDAK ADA teks pendahuluan atau penutup:
{
  "mapped_conditions": [],
  "issue_type": "",
  "primary_intent": "",
  "confidence": 0.0,
  "reasoning": ""
}
"""

    try:
        result = llm_client.classify_with_history(state.get("messages", []) + [
            {"role": "user", "content": prompt}
        ])
        # Parse JSON output
        import json
        mapping = json.loads(result.get("text", "{}")) if isinstance(result, dict) else {}
        return mapping or {
            "mapped_conditions": [], "issue_type": "none", "primary_intent": state["intent"],
            "confidence": 0.5, "reasoning": "No clear mapping detected"
        }
    except Exception as e:
        logger.error("context_analysis_failed", extra={"error": str(e)})
        return {
            "mapped_conditions": [], "issue_type": "none", "primary_intent": state["intent"],
            "confidence": 0.3, "reasoning": "Analysis failed"
        }
```

### 5.3 State Schema Update

Add field to `ChatState` (in `app/graph/state.py`):

```python
class ChatState(TypedDict, total=False):
    # ... existing fields ...
    customer_context: dict | None  # {mapped_conditions, issue_type, primary_intent, confidence, reasoning}
```

Update `classify_intent` flow:

```
classify_intent() → lookup_catalog() → analyze_customer_context() → compose_reply()
```

`compose_reply()` receives `customer_context` and uses it to personalize replies.

---

## 6. Sales-style Prompt Guidelines (Updated)

### 6.1 Updated `COMPOSE_SYSTEM_PROMPT` (in `app/graph/prompts.py`)

```python
COMPOSE_SYSTEM = """
Anda adalah agen penjualan/pelayanan pelanggan WhatsApp yang profesional dan ramah. 
Tugas Anda: jawab pertanyaan pelanggan tentang produk/komplain berdasarkan data yang diberikan,
dan bantu pelanggan menyelesaikan masalahnya.

ATURAN PENTING:
1. JAWAB DALAM BAHASA INDONESIA natural, santai tapi profesional. Gunakan "Kak/Pak" 
   sesuai situasi (tidak perlu dipaksakan).
2. EMPATHY: Jika pelanggan keluh ("lubang di leher", "baru sampe"), tunjukkan pengertian 
   langsung: "Maaf ya Kak.." atau "Saya paham betul kakak kecewa..".
3. JELASKAN ALASAN DENGAN PRODUKTIF: jangan cuma "saya tidak tahu", tapi berikan 
   solusi atau langkah selanjutnya realistis.
4. PANJANG RESPONS: TIDAK LEBIH DARI 3 KALIMAT + MAKSIMAL 1 EMOJI. Pendek, padat, mengalir.
5. LISTENER RULE: JANGAN tanya kembali hal yang sudah pelanggan sebutkan di pesan sebelumnya 
   (misal: kalau udah sebut ukuran M, jangan tanya "ukuran berapa?").
6. AKURASI DATA: hanya gunakan fakta benar-benar ada di data yang diberikan (harga, stok, warna, 
   ukuran). JANGAN mengarang informasi palsu.
7. SOLUSI POSITIF: selalu akhiri dengan nada membantu — apakah info, menawarkan solusi, 
   atau mengarahkan pada tindakan selanjutnya.
8. KONTEKS PEMETAAN: {customer_context}. Gunakan informasi ini untuk merespons lebih 
   tepat dan personal.

DATA DIBERIKAN:
- FAQ: {faq_content}
- Produk: {product_info}
- Kondisi pemetaan pelanggan: {context_mapping}

BALAS PERTANYAAN/PESAN PELANGGAN SESUAI GUIDELINE DI ATAS."
```

### 6.2 Key Changes from Previous Version

| Aspect | Before | After |
|--------|--------|-------|
| Empathy | Generic | Explicit requirement based on `customer_context.issue_type` |
| Listener rule | Basic | Emphasized — do not ask things already provided |
| Positive ending | Implicit | Explicit requirement |
| Context awareness | None | `{customer_context}` injected into prompt |
| Language tone | Standard | More natural, conversational Indonesian |

---

## 7. Implementation Plan (Phased)

### Phase A (Week 1-2): Semantic Search Foundation

| Task | Owner | Effort |
|------|-------|--------|
| 1. Add `sentence-transformers`, `numpy`, `pickle` to requirements.txt | Dev | Low |
| 2. Implement `EmbeddingService` class (local model loading) | Dev | Medium |
| 3. Create `embedding_cache` table + repo layer (CRUD ops) | Dev | Medium |
| 4. Pre-load embeddings from Sheets on startup/cache-on-miss | Dev | Medium |
| 5. Rewrite `lookup_catalog()` to use `SemanticSearch` hybrid scoring | Dev | High |
| 6. Test FAQ lookup with variant phrasings ("garansi berapa?" vs "lama warranty?") | QA/Tech Lead | Medium |

### Phase B (Week 3): Context Reasoning Layer

| Task | Owner | Effort |
|------|-------|--------|
| 7. Create `app/graph/context_analyzer.py` with `analyze_customer_context()` | Dev | High |
| 8. Extend `ChatState` schema with `customer_context` field | Dev | Low |
| 9. Integrate analyzer into flow after `lookup_catalog` in main pipeline | Dev | Medium |
| 10. Test mapping: "lubang di leher" → ["rusak"], "baru sampe" → ["belum_dicuci"] | QA/Tech Lead | High |
| 11. Add test cases for edge cases (ambiguous messages, no policy match) | QA | Medium |

### Phase C (Week 4): Sales-style Tuning & Validation

| Task | Owner | Effort |
|------|-------|--------|
| 12. Update `COMPOSE_SYSTEM_PROMPT` per Section 6 | Tech Lead | Low |
| 13. Update `compose_reply()` to inject `customer_context` into prompt | Dev | Medium |
| 14. Write unit tests for constraint validation (≤3 sentences, ≤1 emoji, listener rule check) | Dev | Medium |
| 15. End-to-end test: complaint message → correct auto-reply with empathy | QA/Tech Lead | High |
| 16. Gather feedback from 5+ test conversations, iterate on prompts | Tech Lead | Medium |

---

## 8. Testing Strategy

### 8.1 Unit Tests

- `test_semantic_search_hybrid_scoring.py` — verify embedding + keyword combo produces meaningful scores
- `test_context_analyzer_basic_mapping.py` — simple case: "produk rusak" maps to condition "rusak"
- `test_context_analyzer_complex_mapping.py` — complex: "ada lubang di leher, baru sampe" → ["rusak", "belum_dicuci"]
- `test_prompt_constraints.py` — validate reply length, emoji count, listener rule violations

### 8.2 Integration Tests

- `test_full_flow_complaint_scenario.py` — end-to-end: complaint message → context mapping → empathetic reply
- `test_fallback_on_low_confidence.py` — when context confidence < threshold, should trigger fallback properly

### 8.3 Manual Validation Suite

Create a test script that runs these scenarios and verifies expected behaviors:

| Test Case | Input Message | Expected Output |
|-----------|---------------|-----------------|
| FAQ variant 1 | "berapa lama garansinya?" | Correct FAQ answer from Sheets |
| FAQ variant 2 | "barusan saya pesan, tapi belum ada garansinya mana?" | Same FAQ (semantic match), not fallback |
| Product check | "kaos warna biruukuran L ada ga?" | Product catalog reply if available |
| Complaint 1 | "produk saya ada lubang di leher baru sampe" → auto-reply with return policy mention | Correct empathetic reply with return guidance |
| Complaint 2 | "gak suka sama barangnya mau balikin" → needs clarification | Fallback with polite request for details |
| Order confirmation | "saya mau order 2 pcs kaos hitam" → template reply | Order confirmation template (fast path) |
| Unknown query | "kirim telegram ke sini" → unclear intent | Fallback to owner |

Success criteria: ≥8 out of 10 test cases handled correctly (auto-reply, not false fallback).

---

## 9. Success Metrics & KPIs

After Phase 2 deployment, track and measure:

| Metric | Baseline (Pre-Phase 2) | Target (Post-Phase 2) | Measurement Method |
|--------|----------------------|---------------------|-------------------|
| **Auto-reply rate** (bukan fallback ke owner) | ~60% estimated (varies by usage) | ≥85% | Count: total replies / total messages where no fallback triggered |
| **Context understanding accuracy** | 0% (keyword-only) | ≥80% (human eval on 50 sample complaints) | Manual review: did bot correctly identify issue type & mapped conditions? |
| **Average resolution time** | Dependent on owner reply speed | Instant (auto-reply within seconds) | Time from webhook receipt to WhatsApp send |
| **False-positive fallback rate** | N/A | <15% (when context exists but bot missed) | Cases where human needed to step in because bot didn't know answer |
| **Customer satisfaction proxy** | High manual handling load | Reduced owner ticket volume by 40-60% | Count of owner notifications sent; downward trend indicates improvement |

Weekly metric reporting recommended during first month post-launch.

---

## 10. Dependencies & Risk Mitigation

| Risk | Probability | Impact | Mitigation Strategy |
|------|-------------|--------|---------------------|
| Local `sentence-transformers` libtorch dependency fails on production server | Medium | High | Provide fallback: use Anthropic Claude API for embeddings (documented config toggle) |
| Semantic search retrieves wrong row due to overly broad similarity | Medium | Medium | Conservative threshold (0.45), hybrid weighting favors semantic, low-confidence triggers fallback |
| Context analyzer mis-maps intent (e.g., complaint treated as FAQ) | Low-High | High | Confidence threshold in context analysis (<0.7 triggers cautious/emphatic fallback) |
| Owner adds many policy rows (>100) slowing down load time | Low | Medium | Implement async embedding refresh on sheet change detection; limit cache size via LRU |
| Prompt constraints (≤3 sentences) make empathetic feel constrained | Low | Medium | Allow one exception: when explaining solution/next steps clearly requires slightly longer; still keep under 4 |

---

## 11. Architecture Diagram (Textual Representation)

```
┌─────────────────┐      ┌──────────────────┐      ┌─────��────────┐
│ WhatsApp Webhook │─────►│ Route Handler    │─────►│ LangGraph    │
│ (Fonnte)        │      │ auth/validation  │      │ Graph State  │
└─────────────────┘      └──────────────────┘      └──────┬───────┘
                                                           │
                                        ┌──────────────────▼──────────────────┐
                                        │       classify_intent (LLM)         │
                                        │ intent/confidence/complaint_signal  │
                                        └──────────────┬──────────────────────┘
                                                       │
                                    ┌──────────────────▼──────────────────┐
                                    │     lookup_catalog (SEMANTIC)       │
                                    │ hybrid search: emb + keyword match  │
                                    │ → returns relevant FAQ/product/policy│
                                    └──────────────┬──────────────────────┘
                                                   │
                          ┌────────────────────────▼────────────────────────┐
                          │          analyze_customer_context (LLM mini)    │
                          │ maps "lubang di leher" → ["rusak","belum_dicuci"]│
                          │ outputs: {mapped_conditions, issue_type,...}    │
                          └──────────────┬──────────────────────────────────┘
                                         │
                  ┌───────────────────────┼───────────────────────┐
                  ▼                       ▼                       ▼
    ┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
    │ compose_reply(NEW)  │   │ fallback_human()    │   │ send_whatsapp()     │
    │ injects context     │   │ if confidence <thr  │   │ + write_log         │
    │ into prompt         │   │ or no match         │   │                     │
    │ sales-style style   │   │                     │   │                     │
    └─────────────────────┘   └─────────────────────┘   └─────────────────────┘
```

---

## 12. Conclusion

This Phase 2 enhancement focuses on the right levers to make OrderCloser Lite feel like a real sales assistant who **understands your customers**:

1. **Better data ingestion** — semantic search understands meaning, not just keywords
2. **Context-aware responses** — the chatbot knows what you're describing before replying
3. **Natural, empathetic language** — sales-style tone that makes customers feel heard

The approach preserves the simplicity of the existing architecture while adding meaningful intelligence. Owner UMKM continue to manage content through Sheets — no technical barriers.

Next step: Generate detailed implementation plan for development execution.

---

*Design approved by user on 2026-07-30.*  
*File location: docs/superpowers/specs/2026-07-30-context-aware-reply-engine-design.md*