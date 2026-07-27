# Project Context - OrderCloser Lite Chatbot (MVP Phase 1)

## Summary
A WhatsApp chatbot for an order/business system that uses AI intent classification to route user queries to appropriate business flows (FAQ, product lookup, order confirmation). Built with FastAPI + LangGraph + Gemini API.

---

## Architecture Overview

```
[WhatsApp] → [FastAPI Webhook] → [LangGraph State Machine]
                     ↓                       ↓
                 (verify signature)      [classify_intent] → Gemini API
                                      [lookup_catalog] → Google Sheets
                                      [compose_reply] → Logic per intent
                                      [send_whatsapp] → Wablas API
                                      [write_chat_log] → SQLite/DB
```

## Core Components

### 1. **app/config.py** – Configuration
- Loads environment variables from `.env` (Pydantic V2)
- Settings include: `GEMINI_API_KEY`, `WABLAS_API_KEY`, `SECRET_KEY`, etc.
- Intent confidence threshold configurable via `intent_confidence_threshold`

### 2. **app/services/llm.py** – LLM Client
Wrapper around Google GenAI SDK for intent classification:
- `GeminiLLMClient`: Uses Gemini model to classify user message into one of 4 intents
  - `faq`, `check_product`, `confirm_order`, `unclear`
- Returns JSON: `{"intent": "...", "confidence": float}`
- Error handling raises `LLMError` for downstream try/catch

**Current default**: `gemini-3.1-flash-lite` (replaced `gemini-2.0-flash-lite` due to quota exhaustion)

### 3. **app/graph/nodes.py** – Graph Nodes
Stateful nodes operating on `ChatState` (dict-like):

| Node | Purpose |
|------|---------|
| `classify_intent` | Call LLM to classify user message |
| `lookup_catalog` | Query Sheets client based on intent |
| `compose_reply` | Generate reply text based on state |
| `send_whatsapp` | Send reply via Wablas API |
| `fallback_human` | Forward to owner if low confidence |
| `write_chat_log` | Persist conversation log |

### 4. **app/graph/graph.py** – Graph Assembly
Builds a LangGraph `StateGraph` with edges:
```
START → classify_intent → {lookup_catalog | fallback_human}
lookup_catalog → {compose_reply | compose_reply_fallback}
compose_reply → send_whatsapp → write_log → END
fallback_human → write_log → END
```
Routing functions:
- `route_after_classify()`: checks confidence threshold → fallback or lookup
- `route_after_lookup()`: checks if catalog match exists → compose or fallback

### 5. **app/services/wablas.py** – Wablas Client
Sends messages via Wablas WhatsApp API (`https://wablas.com/api`). Uses session/auth with API key.

### 6. **app/services/sheets.py** – Google Sheets Client
Queries a public Google Sheet for FAQ and product catalog data.

### 7. **app/api/main.py** – FastAPI Application
Routes:
- `POST /message` – Incoming webhook from WhatsApp (or test endpoint)
- `POST /webhook/wablas` – Signature-verified inbound webhook
- `GET /docs` – Swagger UI
- `GET /health` – Health check (requires all env vars set)

---

## Environment Variables (`.env`)

```
# Required
GEMINI_API_KEY=<your_gemini_api_key>
WABLAS_API_KEY=<your_wablas_api_key>
SECRET_KEY=<encryption_key_for_signatures>

# Optional but recommended
CHECKPOINT_URI=sqlite:///checkpoints.db  # for LangGraph persistence
LOG_LEVEL=INFO
```

`.env` is `.gitignore`d for security.

---

## Data Flow Example

**User sends:** `"Apa saja cara pembayaran yang tersedia?"`

1. `classify_intent` → Gemini returns `{"intent":"faq","confidence":1.0}`
2. Routing: confidence ≥ 0.6 → go to `lookup_catalog`
3. `lookup_catalog`: Sheets lookup FAQ → found answer = "Cash, Bank Transfer, GoPay"
4. `compose_reply` → generates `reply_text` with that answer
5. `send_whatsapp` → sends answer back to buyer
6. `write_chat_log` → persists message pair in DB

**User sends:** `"Saya mau pesan dua kursi untuk esok."`

1. `classify_intent` → Gemini returns `{"intent":"confirm_order","confidence":0.95}`
2. Routing → `lookup_catalog` (no sheet lookup needed)
3. `compose_reply` → hardcoded order confirmation message
4. `send_whatsapp` → sends confirmation
5. `write_chat_log` → persists

---

## Current Status (as of commit 8397923)

✅ **Working:**
- FastAPI server starts on port 8765
- `/docs` Swagger UI accessible
- `.env` key loaded successfully
- Gemini API connection verified (key valid, model working)
- Intent classification producing correct JSON output
- Full graph flow end-to-end working (when all clients injected)
- Logger bug fixed in `llm.py` line 147
- Model switched to `gemini-3.1-flash-lite` (stable quota)

⏳ **Pending/Needs Setup:**
- Wablas API key required for actual WhatsApp sending/receiving
- Google Sheets service account key (`secrets/sheets-sa.json`) for lookup
- SQLite checkpointer setup for persistent state across sessions
- Encryption key generation for tenant data (if multi-tenant)

---

## Known Issues & Fixes

| Issue | Fix | Location |
|-------|-----|----------|
| `logger.error()` crashed on kwarg `error=` | Use `logger.exception(msg, e)` instead | `llm.py:147` |
| Gemini free-tier quota exhausted | Switched to `gemini-3.1-flash-lite` | `llm.py:MODEL` |
| Missing `.env` entries early in config loading | Added guard to avoid empty key warning | `config.py:validation` |

---

## Next Steps

1. Add Wablas API key to `.env` and test `/webhook/wablas` endpoint with curl
2. Set up Google Sheets service account and test sheets client
3. Create `checkpoints.db` and verify checkpointer
4. Write integration tests for the full graph flow
5. Add environment validation at app startup (`/health` should reflect dependencies)
6. Commit any remaining `.env` changes to local repo only (not pushed)

---

## Dependencies (from requirements.txt)

```
fastapi==0.115.0
uvicorn==0.32.0
google-genai==2.14.0
langgraph==0.2.59
pydantic==2.9.1
python-multipart==0.0.6
httpx==0.27.0
cryptography==43.0.0
tenacity==8.5.3
```

All installed in Python 3.10 environment.

---

*Document generated automatically as project context snapshot.*