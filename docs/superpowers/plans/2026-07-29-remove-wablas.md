# Remove Wablas Gateway — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all Wablas code, config, and documentation from the project so Fonnte is the single supported WhatsApp gateway.

**Architecture:** Delete `app/services/wablas.py` and `app/auth/signature.py`. Collapse the webhook auth to a single Fonnte-token path. Remove Wablas fields from `app/config.py` and the `whatsapp_gateway` selection branch. Update tests to drop Wablas references and fix the 2 pre-existing `test_fallback.py` failures.

**Tech Stack:** FastAPI, LangGraph, Pydantic V2, Fonnte WhatsApp Gateway API.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `app/services/wablas.py` | DELETE | Wablas client (unused) |
| `app/auth/signature.py` | DELETE | HMAC verify for Wablas (unused) |
| `app/auth/__init__.py` | MODIFY | Remove empty package |
| `app/config.py` | MODIFY | Drop Wablas fields; drop `whatsapp_gateway` |
| `app/main.py` | MODIFY | Single Fonnte auth path; rename helper; drop Wablas imports |
| `app/graph/graph.py` | MODIFY | Drop Wablas mention in docstring |
| `app/services/sheets.py` | KEEP | Already Fonnte-agnostic (no change needed) |
| `tests/test_wablas.py` | DELETE | Tests for deleted client |
| `tests/test_signature.py` | DELETE | Tests for deleted module |
| `tests/test_webhook.py` | MODIFY | Fonnte-only auth tests |
| `tests/test_fallback.py` | MODIFY | Fix kwarg name; replace WablasError import |
| `tests/test_config.py` | MODIFY | Drop Wablas env sets and assertions |
| `tests/test_repos.py` | MODIFY | Update test data value (Wablas → Fonnte) |
| `tests/test_crypto.py` | MODIFY | Update test data value |
| `tests/conftest.py` | MODIFY | Replace WABLAS_BASE_URL with FONNTE_API_KEY |
| `.env` | MODIFY | Drop Wablas lines; drop whatsapp_gateway line |
| `PROJECT_CONTEXT.md` | MODIFY | Fonnte-only architecture narrative |
| `README.md` | MODIFY | Replace Wablas refs with Fonnte |
| `docs/superpowers/specs/2026-07-27-ordercloser-lite-fase1-design.md` | MODIFY | Replace Wablas refs |
| `docs/superpowers/plans/2026-07-27-ordercloser-lite-fase1.md` | MODIFY | Replace Wablas refs |

---

## Task 1: Delete Wablas code modules

**Files:**
- Delete: `app/services/wablas.py`
- Delete: `app/auth/signature.py`
- Delete: `app/auth/__init__.py`
- Delete: `tests/test_wablas.py`
- Delete: `tests/test_signature.py`

- [ ] **Step 1: Delete the 5 files**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
rm app/services/wablas.py
rm app/auth/signature.py
rm app/auth/__init__.py
rm tests/test_wablas.py
rm tests/test_signature.py
```

- [ ] **Step 2: Verify the auth package directory is empty**

```bash
ls -la app/auth/
```

Expected: directory listing shows no files (only `.` and `..`).

- [ ] **Step 3: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add -u
git commit -m "refactor: delete Wablas client, HMAC verify, and their tests"
```

---

## Task 2: Update app/config.py to remove Wablas fields

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: Replace config.py content**

Write this to `app/config.py`:

```python
"""Application configuration via pydantic-settings."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM backend selection: "anthropic" or "gemini"
    llm_backend: str = "gemini"

    # LLM API keys — left empty until configured; validation occurs later when used
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    # Required (must be provided via environment)
    encryption_key: str = ""
    fonnte_api_key: str = ""  # API key for Fonnte WhatsApp Gateway
    google_sheets_credentials_json_path: str = "./secrets/sheets-sa.json"
    google_sheets_spreadsheet_id: str = ""  # filled from tenant context or env

    # Optional with defaults
    checkpointer_db_path: str = "./data/checkpoints.db"
    log_level: str = "INFO"
    intent_confidence_threshold: float = 0.6


@lru_cache(maxsize=1)
def get_settings(**overrides) -> Settings:
    """Return application settings. Pass overrides for testing."""
    return Settings(**overrides)  # type: ignore[call-arg]
```

- [ ] **Step 2: Verify config loads without error**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && python -c "from app.config import get_settings; get_settings.cache_clear(); s = get_settings(); print(s.fonnte_api_key[:5] if s.fonnte_api_key else 'empty')"`
Expected: prints first 5 chars of fonnte key (e.g. "mzWit") or "empty".

- [ ] **Step 3: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add app/config.py
git commit -m "refactor(config): drop Wablas fields, keep only Fonnte config"
```

---

## Task 3: Update app/main.py to single Fonnte auth path

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Update imports**

In `app/main.py`, replace the import block (lines 12-29) with:

```python
from app.config import get_settings
from app.db import init_db  # Ensure DB tables are created
from app.db.checkpointer import SqliteCheckpointer
from app.graph.graph import (
    build_graph,
    reset_compiled_graph_for_testing,
)
from app.graph.state import ChatState
from app.services.llm import (
    AnthropicLLMClient,
    GeminiLLMClient,
    LLMError,
)
from app.services.sheets import GoogleSheetsClient
from app.services.fonnte import FonnteGateway, FonnteError
from app.services.phone_gateway import PhoneGatewayException
```

Removed: `verify_wablas_signature`, `SignatureError`, `WablasClient`, `WablasError`, `PhoneGateway` (still needed in `_create_fonnte_gateway` for type? — no, see step 2).

- [ ] **Step 2: Rename helper and drop gateway branching**

In `app/main.py`, replace the function `_create_phone_gateway` (lines 94-119) with:

```python
def _create_fonnte_gateway():
    """Create the Fonnte WhatsApp gateway client.

    Raises:
        RuntimeError if FONNTE_API_KEY is not configured.
    """
    settings = get_settings()
    if not settings.fonnte_api_key:
        raise RuntimeError("FONNTE_API_KEY not configured")
    return FonnteGateway(api_key=settings.fonnte_api_key)
```

- [ ] **Step 3: Update `_ensure_clients` to use the new helper**

In `app/main.py`, replace `_create_phone_gateway` references and the variable `_phone_gateway` initialization. Replace the block at lines 141-148 with:

```python
    try:
        if _phone_gateway is None:
            _phone_gateway = _create_fonnte_gateway()
            logger.info("fonnte_gateway_initialized")
    except Exception as e:
        logger.error("fonnte_gateway_init_failed", exc_info=True)
        _phone_gateway = None
```

- [ ] **Step 4: Replace the webhook auth block**

In `app/main.py`, replace lines 181-232 (the entire `if gateway == "fonnte": ... else: ...` block) with:

```python
    settings = get_settings()
    fonnte_api_key = settings.fonnte_api_key or ""
    if not fonnte_api_key:
        raise HTTPException(
            status_code=500, detail="FONNTE_API_KEY not configured on server"
        )
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing Bearer Authorization header",
        )
    provided_token = auth_header[7:]
    if provided_token != fonnte_api_key:
        raise HTTPException(status_code=401, detail="Invalid Fonnte API key")
```

- [ ] **Step 5: Drop WablasError from the gateway-error except clause**

In `app/main.py`, replace line 272-276:

Old:
```python
    except (FonnteError, WablasError, PhoneGatewayException):
        logger.error("whatsapp_gateway_error", exc_info=True)
        raise HTTPException(status_code=500, detail="Message delivery failed")
```

New:
```python
    except (FonnteError, PhoneGatewayException):
        logger.error("whatsapp_gateway_error", exc_info=True)
        raise HTTPException(status_code=500, detail="Message delivery failed")
```

- [ ] **Step 6: Verify the file parses**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && python -c "from app.main import app; print('ok')"`
Expected: prints `ok` (no ImportError).

- [ ] **Step 7: Run webhook tests to confirm**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && python -m pytest tests/test_webhook.py -v`
Expected: many failures (we haven't updated the test yet) — that's fine, this confirms the new auth path is in place.

- [ ] **Step 8: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add app/main.py
git commit -m "refactor(main): collapse webhook auth to single Fonnte path"
```

---

## Task 4: Update app/graph/graph.py docstring

**Files:**
- Modify: `app/graph/graph.py:116`

- [ ] **Step 1: Fix the gateway docstring**

In `app/graph/graph.py`, find line 116:
```
        gateway_client: Phone gateway (Wablas or Fonnte) for sending WhatsApp messages.
```

Replace with:
```
        gateway_client: Phone gateway (Fonnte) for sending WhatsApp messages.
```

- [ ] **Step 2: Verify graph imports cleanly**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && python -c "from app.graph.graph import build_graph; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add app/graph/graph.py
git commit -m "docs(graph): drop Wablas mention from gateway docstring"
```

---

## Task 5: Rewrite tests/test_webhook.py for Fonnte-only auth

**Files:**
- Modify: `tests/test_webhook.py` (full rewrite)

- [ ] **Step 1: Replace test_webhook.py content**

Write this to `tests/test_webhook.py`:

```python
"""Integration tests for /webhook/whatsapp/ endpoint (Fonnte auth only)."""
import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


FONNTE_TOKEN = "test-fonnte-token-for-testing"


@pytest.fixture
def client(monkeypatch):
    """Test client with FONNTE_API_KEY set."""
    monkeypatch.setenv("FONNTE_API_KEY", FONNTE_TOKEN)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./dummy.json")
    get_settings.cache_clear()
    from app.main import app
    return TestClient(app)


def _build_payload_bytes() -> bytes:
    return json.dumps({
        "tenant_id": "demo",
        "wa_number": "+6281234567890",
        "thread_id": "thread-abc",
        "message_text": "Halo",
    }, separators=(",", ":")).encode("utf-8")


def test_missing_authorization_header_returns_401(client):
    """Webhook rejects request without Authorization header (HTTP 401)."""
    body = _build_payload_bytes()
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 401
    assert "Missing Bearer" in response.json()["detail"]


def test_wrong_authorization_scheme_returns_401(client):
    """Webhook rejects request without Bearer prefix (HTTP 401)."""
    body = _build_payload_bytes()
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": FONNTE_TOKEN,  # raw token, no Bearer prefix
        },
    )
    assert response.status_code == 401
    assert "Missing Bearer" in response.json()["detail"]


def test_invalid_token_returns_401(client):
    """Webhook rejects request with wrong Bearer token (HTTP 401)."""
    body = _build_payload_bytes()
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer wrong-token",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Fonnte API key"


def test_valid_token_passes_verification(client, monkeypatch):
    """Webhook accepts request with correct Bearer token and returns success."""
    from app import main as app_main

    class MockGraph:
        async def ainvoke(self, state):
            return {**state, "intent": "faq", "reply_text": "Mocked"}

    app_main._compiled_graph = MockGraph()
    app_main._llm_client = object()
    app_main._sheets_client = object()
    app_main._phone_gateway = object()

    body = _build_payload_bytes()
    response = client.post(
        "/webhook/whatsapp/",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {FONNTE_TOKEN}",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["state"]["intent"] == "faq"
```

- [ ] **Step 2: Run the new webhook tests**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && python -m pytest tests/test_webhook.py -v`
Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add tests/test_webhook.py
git commit -m "test(webhook): rewrite for Fonnte-only auth"
```

---

## Task 6: Fix tests/test_fallback.py — replace Wablas refs and fix kwarg

**Files:**
- Modify: `tests/test_fallback.py`

- [ ] **Step 1: Update the import**

Replace `from app.services.wablas import WablasError` with `from app.services.fonnte import FonnteError`.

- [ ] **Step 2: Rename mock variable and fix kwarg**

In `tests/test_fallback.py`, find the two `async def test_fallback_human_*` tests. In each test, replace:
- `fake_wablas` → `fake_gateway` (variable rename)
- `AsyncMock(side_effect=WablasError("wablas down"))` → `AsyncMock(side_effect=FonnteError("fonnte down"))`
- `fallback_human(state, wablas_client=fake_wablas)` → `fallback_human(state, gateway_client=fake_gateway)`
- All references to `fake_wablas.send_message` → `fake_gateway.send_message`

- [ ] **Step 3: Run the fallback tests**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && python -m pytest tests/test_fallback.py -v`
Expected: all 5 tests pass (3 compose_reply + 2 fallback_human).

- [ ] **Step 4: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add tests/test_fallback.py
git commit -m "test(fallback): fix pre-existing Wablas kwarg bug, use FonnteError"
```

---

## Task 7: Update tests/test_config.py to remove Wablas env sets

**Files:**
- Modify: `tests/test_config.py`

- [ ] **Step 1: Replace WABLAS_BASE_URL sets with FONNTE_API_KEY**

In each of the 4 test functions in `tests/test_config.py`, replace the line `monkeypatch.setenv("WABLAS_BASE_URL", "https://test.wablas.com")` with `monkeypatch.setenv("FONNTE_API_KEY", "test-fonnte-token")`.

- [ ] **Step 2: Replace the assertion**

Find `assert settings.wablas_base_url == "https://test.wablas.com"` and replace with `assert settings.fonnte_api_key == "test-fonnte-token"`.

- [ ] **Step 3: Run config tests**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && python -m pytest tests/test_config.py -v`
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add tests/test_config.py
git commit -m "test(config): replace Wablas env sets with Fonnte"
```

---

## Task 8: Update tests/test_repos.py — test data only

**Files:**
- Modify: `tests/test_repos.py`

- [ ] **Step 1: Update test data values**

In `tests/test_repos.py`, replace the string `"wablas-key-xyz"` with `"fonnte-token-xyz"` (two occurrences: line 27 and line 42).

- [ ] **Step 2: Run tests**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && python -m pytest tests/test_repos.py -v`
Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add tests/test_repos.py
git commit -m "test(repos): rename Wablas test data to Fonnte"
```

---

## Task 9: Update tests/test_crypto.py — test data only

**Files:**
- Modify: `tests/test_crypto.py`

- [ ] **Step 1: Update test data value**

In `tests/test_crypto.py`, replace the string `"wablas-api-key-abc123"` with `"fonnte-api-key-abc123"`.

- [ ] **Step 2: Run tests**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && python -m pytest tests/test_crypto.py -v`
Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add tests/test_crypto.py
git commit -m "test(crypto): rename Wablas test data to Fonnte"
```

---

## Task 10: Update tests/conftest.py — replace Wablas env with Fonnte

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Replace env var setup**

In `tests/conftest.py`, replace `monkeypatch.setenv("WABLAS_BASE_URL", "https://api.wablas.example")` with `monkeypatch.setenv("FONNTE_API_KEY", "test-fonnte-token")`.

- [ ] **Step 2: Run full test suite**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && python -m pytest -v`
Expected: all tests pass except possibly no others. Count should be 4 (webhook) + 5 (fallback) + 4 (config) + 4 (repos) + 4 (crypto) + 7 (other) ≈ 28+ passed, 0 failed.

- [ ] **Step 3: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add tests/conftest.py
git commit -m "test(conftest): replace Wablas env with Fonnte"
```

---

## Task 11: Update .env — drop Wablas and whatsapp_gateway lines

**Files:**
- Modify: `.env`

- [ ] **Step 1: Edit .env to drop Wablas lines**

In `.env`, delete the lines:
- `# ---- Wablas (required) ----`
- `WABLAS_BASE_URL=https://smg.wablas.com/`
- `WABLAS_API_KEY=D2nEyb7xQ5oSzQuC7MKPdWvIY0E4SsUAUKGrdgmIHoSkUBdbXQM8Ibv`
- `# ---- WhatsApp Gateway ----`
- `# Switch to "fonnte" or keep as "wablas"`
- `whatsapp_gateway=fonnte`

The remaining `.env` file should contain: LLM section, Fonnte section, Google Sheets section, Encryption section, Optional section.

- [ ] **Step 2: Verify server starts**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && python -c "from app.config import get_settings; get_settings.cache_clear(); s = get_settings(); assert s.fonnte_api_key; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add .env
git commit -m "chore(env): drop Wablas and whatsapp_gateway lines"
```

---

## Task 12: Update PROJECT_CONTEXT.md — Fonnte-only narrative

**Files:**
- Modify: `PROJECT_CONTEXT.md`

- [ ] **Step 1: Replace Wablas references with Fonnte**

Edit `PROJECT_CONTEXT.md` to:
- Replace "Wablas" with "Fonnte" wherever it refers to the gateway.
- Replace the "Wablas Client" section to "Fonnte Client".
- Replace the data flow example's `[send_whatsapp] → Wablas API` with `[send_whatsapp] → Fonnte API`.
- Remove `WABLAS_API_KEY` from env example, keep `FONNTE_API_KEY`.
- Remove the security note about rotating Wablas tokens.
- Replace `POST /webhook/wablas` references with `POST /webhook/whatsapp` (already correct).

- [ ] **Step 2: Verify no Wablas mentions remain**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && grep -i wablas PROJECT_CONTEXT.md`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add PROJECT_CONTEXT.md
git commit -m "docs(context): describe Fonnte-only architecture"
```

---

## Task 13: Update README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace Wablas references with Fonnte**

Edit `README.md`:
- Replace any "Wablas" with "Fonnte" in the gateway section.
- Update env table: remove Wablas rows, ensure Fonnte row is correct.
- Update setup guide if it mentions Wablas.
- Update webhook authentication description.

- [ ] **Step 2: Verify no Wablas mentions remain**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && grep -i wablas README.md`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add README.md
git commit -m "docs(readme): replace Wablas with Fonnte"
```

---

## Task 14: Update Fase 1 design spec and plan

**Files:**
- Modify: `docs/superpowers/specs/2026-07-27-ordercloser-lite-fase1-design.md`
- Modify: `docs/superpowers/plans/2026-07-27-ordercloser-lite-fase1.md`

- [ ] **Step 1: Replace Wablas references in spec**

In `docs/superpowers/specs/2026-07-27-ordercloser-lite-fase1-design.md`:
- Replace "Webhook Wablas" with "Webhook Fonnte"
- Replace "Signature verification WAJIB" references — note Fonnte uses Bearer token auth instead
- Any other Wablas mentions

- [ ] **Step 2: Replace Wablas references in plan**

In `docs/superpowers/plans/2026-07-27-ordercloser-lite-fase1.md`:
- Replace Wablas client references with Fonnte
- Update auth setup steps

- [ ] **Step 3: Verify no Wablas mentions remain**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && grep -ri wablas docs/`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot
git add docs/superpowers/specs/2026-07-27-ordercloser-lite-fase1-design.md docs/superpowers/plans/2026-07-27-ordercloser-lite-fase1.md
git commit -m "docs(fase1): replace Wablas refs with Fonnte in spec and plan"
```

---

## Task 15: Final verification

**Files:**
- None (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && python -m pytest -v`
Expected: 0 failures. All tests pass.

- [ ] **Step 2: Verify no Wablas references remain in code/tests/docs**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && grep -ri wablas app/ tests/ docs/ PROJECT_CONTEXT.md README.md --include="*.py" --include="*.md"`
Expected: no output.

- [ ] **Step 3: Verify .env is gitignored**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && git check-ignore .env`
Expected: prints `.env`.

- [ ] **Step 4: Verify final git state**

Run: `cd /media/ahmad/84a8377e-0bbf-4a05-bc83-75f57016cb6c/bisnis/ai_agent/chatbot && git log --oneline -10 && echo --- && git status`
Expected: clean working tree. `git status` should show no uncommitted changes except the `dummy_faq_katalog.xlsx` untracked file (which was untracked from the start of this session, unrelated to this work).