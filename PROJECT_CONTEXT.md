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

## Current Status (verified 2026-07-29)

✅ **Working — end-to-end verified on localhost:**
- FastAPI server starts on port 8000
- `/docs` Swagger UI accessible
- `.env` keys loaded successfully
- LLM classification works with Gemini (`gemini-3.1-flash-lite`)
- Full graph flow end-to-end working via **Fonnte gateway** (tested: classify → lookup → compose → send)
- Logger bug fixed in `llm.py` (extra kwarg must be dict, not string)
- Google Sheets lookup verified working (both FAQ and Catalog tabs read correctly)
- Webhook authentication (BBearer token for Fonnte) works correctly
- Input validation at webhook endpoint rejects missing fields
- Sheets lookup error handling: fallback to no-match path
- `/health` endpoint returns dependency readiness status (all dependencies ready)
- Integration tests exist (14+ test files covering auth, sheets, llm, graph, etc.)
- **Tested 2026-07-29**: Full WhatsApp round-trip via curl + local API call succeeded
- Agent workflow diagram generated (`docs/diagrams/workflow.png/svg`)

⏳ **Remaining / Recommended:**
- Rotate `FONNTE_API_KEY` in `.env` (this token appeared in chat — see security note below)
- Set up ngrok + real device for full WhatsApp inbound testing
- Add unit tests for the typo fix (`FonnteError` exception handling)
- Update `README.md` with current setup guide (optional — already has good docs)
- Consider migrating to Anthropic/Claude Haiku if Gemini quota becomes unstable (fallback exists)
- Prepare Phase 2 spec (payment link generation, Order_Log tab) when MVP stable

---

### ⚠️ Security Note
The `FONNTE_API_KEY` shown during this session should be rotated on your Fonnte dashboard after confirming MVP works. Regenerate it in https://fonnte.com and update `.env`.

---

---

## Known Issues & Fixes

| Issue | Fix | Location |
|-------|-----|----------|
| `logger.error()` crashed on kwarg `error=` | Use `logger.exception(msg, e)` instead | `llm.py:147` |
| Gemini free-tier quota exhausted | Switched to `gemini-3.1-flash-lite` | `llm.py:MODEL` |
| Missing `.env` entries early in config loading | Added guard to avoid empty key warning | `config.py:validation` |
| `asyncio.run() cannot be called from a running event loop` crash on webhook | Convert async node wrappers to sync nodes; use `_run_async_from_sync` helper to bridge inside FastAPI handler | `app/graph/graph.py` |
| Sheets lookup raising FileNotFoundError/SDK errors crashed webhook 500 | Wrap `lookup_catalog` body in try/except and fall through to no-match | `app/graph/nodes.py` |
| Webhook accepted empty `wa_number`/`thread_id`/`message_text` silently | Required-field validation with 400 + list of missing fields | `app/main.py` |
| Server couldn't boot when `google-genai` SDK not installed | `MockLLMClient` heuristic fallback in `_create_llm_client()` | `app/main.py`, `app/services/llm.py` |

---

## Known Issues & Fixes — Phase 1 Status

The following issues have been **resolved** during Phase 1 MVP development:

| Issue | Resolution | Location | Date |
|-------|-----------|----------|------|
| Wablas endpoint `/api/v1/send-message` changed to `/api/send-message` | Updated in `wablas.py` | v2.1 | — |
| Gemini free-tier quota exhausted | Switched to `gemini-3.1-flash-lite` | `llm.py:MODEL` | — |
| Typo `FonneteError` → `FonnteError` in except clause | Fixed | `main.py:271` | 2026-07-29 |
| MockLLMClient as fallback when `google-genai` not installed | Existing in code | `llm.py:_create_llm_client()` | — |

---

### ⚠️ Security Note — Rotate Tokens

During this session, `FONNTE_API_KEY`, `GEMINI_API_KEY`, and `ENCRYPTION_KEY` values were visible in the chat. **Do not use these tokens in production**. After confirming MVP works, regenerate each on its provider dashboard and update your `.env`:

1. **Fonnte**: https://fonnte.com → Generate new API key
2. **Google Cloud Console**: Rotate Gemini API key if exposed
3. **Generate fresh encryption key**: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

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