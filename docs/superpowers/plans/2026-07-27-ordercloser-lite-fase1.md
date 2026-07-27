# OrderCloser Lite — Fase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement MVP Fase 1 dari OrderCloser Lite — webhook WhatsApp + LangGraph (intent classification, lookup katalog/FAQ, auto reply, fallback ke manusia) untuk single tenant, deploy lokal + ngrok.

**Architecture:** FastAPI monolith dengan boundary jelas: `auth/` (signature verify), `services/` (LLM/Sheets/Wablas adapters), `graph/` (LangGraph state & nodes), `db/` (SQLAlchemy + LangGraph checkpointer). Single-process, single-tenant, semua external API di-boundary services.

**Tech Stack:** Python 3.11, FastAPI 0.115+, LangGraph 1.x, langgraph-checkpoint-sqlite, langchain-anthropic, gspread, httpx, SQLAlchemy 2.0, cryptography, pydantic-settings 2.4+, pytest.

**Spec:** `docs/superpowers/specs/2026-07-27-ordercloser-lite-fase1-design.md`

---

## File Structure Overview

Sebelum mulai task, ini peta file yang akan dibuat/diubah:

**Configuration & Infrastructure**
- `pyproject.toml` — Python project config, dependencies, tool configs
- `.env.example` — environment template (no secrets)
- `.gitignore` — ignore secrets, db files, virtualenv
- `README.md` — quick start
- `data/.gitkeep` — runtime db dir
- `secrets/.gitkeep` — credentials dir

**Application Code (`app/`)**
- `app/main.py` — FastAPI app factory & lifespan
- `app/webhook.py` — webhook endpoint handler
- `app/health.py` — health/readiness routes
- `app/config.py` — pydantic-settings
- `app/auth/signature.py` — Wablas HMAC verification
- `app/graph/state.py` — ChatState TypedDict
- `app/graph/prompts.py` — Claude Haiku prompt templates
- `app/graph/nodes.py` — 5 LangGraph nodes
- `app/graph/graph.py` — compile StateGraph
- `app/services/llm.py` — ClaudeHaikuClient adapter
- `app/services/sheets.py` — GoogleSheetsClient adapter
- `app/services/wablas.py` — WablasClient adapter
- `app/services/crypto.py` — AES-GCM encrypt/decrypt
- `app/db/engine.py` — SQLAlchemy engine + session factory
- `app/db/models.py` — TenantConfig & ChatLog ORM
- `app/db/checkpointer.py` — SqliteSaver singleton
- `app/db/tenant_repo.py` — tenant CRUD + decrypt_api_key
- `app/db/chat_log_repo.py` — insert log

**Scripts**
- `scripts/gen_encryption_key.py` — generate random 32-byte key
- `scripts/seed_tenant.py` — CLI to insert 1 tenant row

**Tests (`tests/`)**
- `tests/conftest.py` — fixtures (in-memory db, mock clients)
- `tests/test_signature.py`
- `tests/test_crypto.py`
- `tests/test_webhook.py`
- `tests/test_classify.py`
- `tests/test_lookup.py`
- `tests/test_fallback.py`

Total: ~28 source files + 7 test files + 5 config/docs.

---

## Task 1: Project Bootstrap & Configuration

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `data/.gitkeep`
- Create: `secrets/.gitkeep`
- Create: `README.md`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "ordercloser-lite"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.8",
    "pydantic-settings>=2.4",
    "langgraph>=1.0",
    "langgraph-checkpoint-sqlite>=2.0",
    "langchain-anthropic>=0.3",
    "anthropic>=0.39",
    "gspread>=6.1",
    "httpx>=0.27",
    "sqlalchemy>=2.0",
    "cryptography>=43",
    "structlog>=24.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "ruff>=0.6",
    "mypy>=1.11",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP"]
```

- [ ] **Step 2: Create `.gitignore`**

```
# Python
__pycache__/
*.py[cod]
*.so
.venv/
venv/

# Environment & secrets
.env
*.key

# Runtime data
data/*.db
data/*.sqlite
data/*.sqlite3

# Google Sheets credentials
secrets/*.json

# IDE
.vscode/
.idea/

# Testing
.pytest_cache/
.coverage
htmlcov/

# Logs
*.log
```

- [ ] **Step 3: Create `.env.example`**

```bash
# Anthropic (required)
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Wablas (required)
WABLAS_BASE_URL=https://api.wablas.com

# Google Sheets (required)
GOOGLE_SHEETS_CREDENTIALS_JSON_PATH=./secrets/sheets-sa.json

# Encryption (required - generate via scripts/gen_encryption_key.py)
ENCRYPTION_KEY=base64-encoded-32-bytes=

# LangGraph checkpointer (optional)
CHECKPOINTER_DB_PATH=./data/checkpoints.db

# Logging (optional)
LOG_LEVEL=INFO

# Confidence threshold (optional, default 0.6)
INTENT_CONFIDENCE_THRESHOLD=0.6
```

- [ ] **Step 4: Create `data/.gitkeep`**

```
```

- [ ] **Step 5: Create `secrets/.gitkeep`**

```
```

- [ ] **Step 6: Create `README.md`**

```markdown
# OrderCloser Lite

AI agent berbasis LangGraph untuk auto-reply WhatsApp + fallback ke owner.

## Quick Start

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env — at minimum:
#   ANTHROPIC_API_KEY
#   ENCRYPTION_KEY (generate via: python scripts/gen_encryption_key.py)
#   GOOGLE_SHEETS_CREDENTIALS_JSON_PATH (setup guide: docs/setup.md)

# Seed tenant
python scripts/gen_encryption_key.py
python scripts/seed_tenant.py \
    --tenant demo \
    --sheet-id YOUR_GOOGLE_SHEET_ID \
    --wa-number +6281234567890 \
    --api-key YOUR_WABLAS_API_KEY

# Run
uvicorn app.main:app --reload --port 8000
```

## Testing

```bash
pytest -v
```

## Architecture

See [design spec](../specs/2026-07-27-ordercloser-lite-fase1-design.md).
```

- [ ] **Step 7: Verify project installs**

Run: `pip install -e ".[dev]"`
Expected: Installation completes without errors. (Skip if not installing now; verify after all deps are written.)

---

## Task 2: Configuration Module

**Files:**
- Create: `app/__init__.py`
- Create: `app/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Create `app/__init__.py`**

```python
"""OrderCloser Lite — WhatsApp AI Agent."""
__version__ = "0.1.0"
```

- [ ] **Step 2: Write failing test `tests/test_config.py`**

```python
"""Tests for app.config."""
import pytest

from app.config import Settings, get_settings


def test_get_settings_returns_singleton(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ENCRYPTION_KEY", "dGVzdC1rZXktMTIzNDU2Nzg5MGFiY2RlZg==")
    monkeypatch.setenv("WABLAS_BASE_URL", "https://test.wablas.com")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./secrets/test.json")

    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2  # singleton


def test_settings_loads_required_fields(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ENCRYPTION_KEY", "dGVzdC1rZXktMTIzNDU2Nzg5MGFiY2RlZg==")
    monkeypatch.setenv("WABLAS_BASE_URL", "https://test.wablas.com")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./secrets/test.json")

    get_settings.cache_clear()  # type: ignore[attr-defined]
    settings = Settings()

    assert settings.anthropic_api_key == "test-key"
    assert settings.wablas_base_url == "https://test.wablas.com"
    assert settings.intent_confidence_threshold == 0.6  # default


def test_settings_custom_threshold(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ENCRYPTION_KEY", "dGVzdC1rZXktMTIzNDU2Nzg5MGFiY2RlZg==")
    monkeypatch.setenv("WABLAS_BASE_URL", "https://test.wablas.com")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./secrets/test.json")
    monkeypatch.setenv("INTENT_CONFIDENCE_THRESHOLD", "0.75")

    get_settings.cache_clear()  # type: ignore[attr-defined]
    settings = Settings()

    assert settings.intent_confidence_threshold == 0.75


def test_settings_missing_required_field(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ENCRYPTION_KEY", "dGVzdC1rZXktMTIzNDU2Nzg5MGFiY2RlZg==")

    get_settings.cache_clear()  # type: ignore[attr-defined]
    with pytest.raises(Exception):  # ValidationError or similar
        Settings()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 4: Implement `app/config.py`**

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

    # Required
    anthropic_api_key: str
    encryption_key: str  # base64-encoded 32 bytes
    wablas_base_url: str
    google_sheets_credentials_json_path: str

    # Optional with defaults
    checkpointer_db_path: str = "./data/checkpoints.db"
    log_level: str = "INFO"
    intent_confidence_threshold: float = 0.6


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: 4 tests pass

- [ ] **Step 6: Create `tests/__init__.py`**

```python
```

---

## Task 3: Crypto Service

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/crypto.py`
- Test: `tests/test_crypto.py`

- [ ] **Step 1: Create `app/services/__init__.py`**

```python
"""External service adapters."""
```

- [ ] **Step 2: Write failing test `tests/test_crypto.py`**

```python
"""Tests for app.services.crypto."""
import base64

import pytest

from app.services.crypto import CryptoError, decrypt_api_key, encrypt_api_key


def _key_b64() -> str:
    # 32 bytes = AES-256 key
    return base64.b64encode(b"x" * 32).decode()


def test_encrypt_decrypt_round_trip():
    key_b64 = _key_b64()
    plaintext = "wablas-api-key-abc123"

    ciphertext = encrypt_api_key(plaintext, key_b64)
    assert ciphertext != plaintext.encode()
    assert isinstance(ciphertext, bytes)

    decrypted = decrypt_api_key(ciphertext, key_b64)
    assert decrypted == plaintext


def test_decrypt_with_wrong_key_fails():
    key_b64 = _key_b64()
    other_key_b64 = base64.b64encode(b"y" * 32).decode()

    ciphertext = encrypt_api_key("secret", key_b64)

    with pytest.raises(CryptoError):
        decrypt_api_key(ciphertext, other_key_b64)


def test_decrypt_tampered_ciphertext_fails():
    key_b64 = _key_b64()
    ciphertext = encrypt_api_key("secret", key_b64)
    tampered = ciphertext[:-1] + bytes([(ciphertext[-1] ^ 0xFF)])

    with pytest.raises(CryptoError):
        decrypt_api_key(tampered, key_b64)


def test_encrypt_invalid_key_length():
    with pytest.raises(CryptoError):
        encrypt_api_key("text", base64.b64encode(b"short").decode())
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_crypto.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.crypto'`

- [ ] **Step 4: Implement `app/services/crypto.py`**

```python
"""AES-GCM encryption for tenant API keys at rest."""
import base64
import os

from Crypto.Cipher import AES


class CryptoError(Exception):
    """Raised when encryption/decryption fails."""


def _decode_key(key_b64: str) -> bytes:
    try:
        key = base64.b64decode(key_b64)
    except Exception as e:
        raise CryptoError(f"Invalid base64 encryption key: {e}") from e

    if len(key) != 32:
        raise CryptoError(f"Encryption key must be 32 bytes, got {len(key)}")

    return key


def encrypt_api_key(plaintext: str, key_b64: str) -> bytes:
    """Encrypt plaintext API key. Returns nonce || ciphertext."""
    try:
        key = _decode_key(key_b64)
        nonce = os.urandom(12)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode())
        return nonce + ciphertext + tag
    except ValueError as e:
        raise CryptoError(f"Encryption failed: {e}") from e
    except Exception as e:
        raise CryptoError(f"Encryption failed: {e}") from e


def decrypt_api_key(ciphertext: bytes, key_b64: str) -> str:
    """Decrypt ciphertext from encrypt_api_key. Returns plaintext."""
    try:
        key = _decode_key(key_b64)
        if len(ciphertext) < 12 + 16:
            raise CryptoError("Ciphertext too short")

        nonce = ciphertext[:12]
        tagged_data = ciphertext[12:-16]
        tag = ciphertext[-16:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(tagged_data, tag)
        return plaintext.decode()
    except CryptoError:
        raise
    except Exception as e:
        raise CryptoError(f"Decryption failed: {e}") from e
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_crypto.py -v`
Expected: 4 tests pass

---

## Task 4: Database Models & Engine

**Files:**
- Create: `app/db/__init__.py`
- Create: `app/db/engine.py`
- Create: `app/db/models.py`
- Test: `tests/test_db_models.py`

- [ ] **Step 1: Create `app/db/__init__.py`**

```python
"""Database layer — SQLAlchemy models and repos."""
```

- [ ] **Step 2: Write failing test `tests/test_db_models.py`**

```python
"""Tests for app.db.engine and app.db.models."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.engine import get_engine, get_session_factory
from app.db.models import Base, ChatLog, TenantConfig


@pytest.fixture
def in_memory_engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_base_metadata_creates_tables(in_memory_engine):
    inspector = __import__("sqlalchemy").inspect(in_memory_engine)
    tables = inspector.get_table_names()
    assert "tenant_config" in tables
    assert "chat_log" in tables


def test_tenant_config_insert_and_select(in_memory_engine):
    Session = sessionmaker(bind=in_memory_engine)
    with Session() as session:
        tenant = TenantConfig(
            tenant_id="demo",
            wa_api_key_encrypted=b"\x00" * 32,
            google_sheet_id="sheet-123",
            payment_provider="xendit",
            owner_wa_number="+6281234567890",
        )
        session.add(tenant)
        session.commit()

        loaded = session.query(TenantConfig).filter_by(tenant_id="demo").first()
        assert loaded is not None
        assert loaded.google_sheet_id == "sheet-123"
        assert loaded.owner_wa_number == "+6281234567890"


def test_chat_log_insert_and_select(in_memory_engine):
    from datetime import datetime, timezone

    Session = sessionmaker(bind=in_memory_engine)
    with Session() as session:
        log = ChatLog(
            thread_id="demo:+628999",
            tenant_id="demo",
            wa_number="+628999",
            intent="faq",
            confidence=0.85,
            response="Halo, produk ready.",
            status="sent",
            timestamp=datetime.now(timezone.utc),
        )
        session.add(log)
        session.commit()

        loaded = session.query(ChatLog).filter_by(thread_id="demo:+628999").first()
        assert loaded is not None
        assert loaded.intent == "faq"
        assert loaded.confidence == 0.85
        assert loaded.status == "sent"


def test_get_engine_returns_singleton():
    get_engine.cache_clear()  # type: ignore[attr-defined]
    e1 = get_engine()
    e2 = get_engine()
    assert e1 is e2


def test_get_session_factory():
    factory = get_session_factory()
    assert callable(factory)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_db_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db.engine'`

- [ ] **Step 4: Implement `app/db/engine.py`**

```python
"""SQLAlchemy engine and session factory."""
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    db_path = settings.checkpointer_db_path
    # SQLite: ensure parent dir exists
    if db_path != ":memory:":
        import os
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    return create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )


@lru_cache(maxsize=1)
def get_session_factory():
    engine = get_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Session:
    """Context-manager compatible session. Use as: `with get_session() as s:`."""
    SessionLocal = get_session_factory()
    return SessionLocal()
```

- [ ] **Step 5: Implement `app/db/models.py`**

```python
"""SQLAlchemy ORM models."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TenantConfig(Base):
    __tablename__ = "tenant_config"

    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    wa_api_key_encrypted: Mapped[bytes] = mapped_column()  # type: ignore[type-arg]
    google_sheet_id: Mapped[str] = mapped_column(String, nullable=False)
    payment_provider: Mapped[str] = mapped_column(String, nullable=False, default="xendit")
    owner_wa_number: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )


class ChatLog(Base):
    __tablename__ = "chat_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    wa_number: Mapped[str] = mapped_column(String, nullable=False)
    intent: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("idx_thread", "thread_id"),
        Index("idx_tenant_time", "tenant_id", "timestamp"),
    )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_db_models.py -v`
Expected: 5 tests pass

---

## Task 5: Tenant & Chat Log Repositories

**Files:**
- Create: `app/db/tenant_repo.py`
- Create: `app/db/chat_log_repo.py`
- Test: `tests/test_repos.py`

- [ ] **Step 1: Write failing test `tests/test_repos.py`**

```python
"""Tests for tenant_repo and chat_log_repo."""
import base64
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.engine import get_engine, get_session_factory
from app.db.models import Base, ChatLog, TenantConfig


@pytest.fixture(autouse=True)
def reset_db():
    """Reset engine cache and create fresh in-memory DB per test."""
    get_engine.cache_clear()  # type: ignore[attr-defined]
    get_session_factory.cache_clear()  # type: ignore[attr-defined]

    # Build a fresh engine that points to in-memory
    from app.db.engine import get_engine as ge
    import app.db.engine as engine_mod

    engine_mod._engine = None  # type: ignore[attr-defined]

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    engine_mod._engine = eng  # type: ignore[attr-defined]

    yield

    eng.dispose()


def test_tenant_repo_insert_and_get():
    from app.db.tenant_repo import insert_tenant, get_tenant, decrypt_api_key
    from app.config import get_settings
    from app.services.crypto import encrypt_api_key

    settings = get_settings()
    encrypted = encrypt_api_key("wablas-key-xyz", settings.encryption_key)

    insert_tenant(
        tenant_id="demo",
        wa_api_key_encrypted=encrypted,
        google_sheet_id="sheet-abc",
        owner_wa_number="+6281234567890",
    )

    tenant = get_tenant("demo")
    assert tenant is not None
    assert tenant["tenant_id"] == "demo"
    assert tenant["google_sheet_id"] == "sheet-abc"
    assert decrypt_api_key(tenant["wa_api_key_encrypted"], settings.encryption_key) == "wablas-key-xyz"


def test_tenant_repo_not_found_returns_none():
    from app.db.tenant_repo import get_tenant

    tenant = get_tenant("nonexistent")
    assert tenant is None


def test_chat_log_repo_insert():
    from app.db.chat_log_repo import insert_chat_log

    log_id = insert_chat_log(
        thread_id="demo:+628999",
        tenant_id="demo",
        wa_number="+628999",
        intent="faq",
        confidence=0.85,
        response="Halo!",
        status="sent",
    )

    assert isinstance(log_id, int)
    assert log_id > 0


def test_chat_log_repo_insert_with_fallback_reason():
    from app.db.chat_log_repo import insert_chat_log

    log_id = insert_chat_log(
        thread_id="demo:+628999",
        tenant_id="demo",
        wa_number="+628999",
        intent="unclear",
        confidence=0.3,
        response=None,
        fallback_reason="low_confidence",
        status="fallback",
    )

    assert log_id > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_repos.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/db/tenant_repo.py`**

```python
"""Tenant config repository."""
from typing import TypedDict

from sqlalchemy.orm import Session

from app.db.engine import get_session
from app.db.models import TenantConfig


class TenantRecord(TypedDict):
    tenant_id: str
    wa_api_key_encrypted: bytes
    google_sheet_id: str
    payment_provider: str
    owner_wa_number: str


def insert_tenant(
    tenant_id: str,
    wa_api_key_encrypted: bytes,
    google_sheet_id: str,
    owner_wa_number: str,
    payment_provider: str = "xendit",
) -> None:
    """Insert a new tenant config row."""
    with get_session() as session:
        tenant = TenantConfig(
            tenant_id=tenant_id,
            wa_api_key_encrypted=wa_api_key_encrypted,
            google_sheet_id=google_sheet_id,
            owner_wa_number=owner_wa_number,
            payment_provider=payment_provider,
        )
        session.add(tenant)
        session.commit()


def get_tenant(tenant_id: str) -> TenantRecord | None:
    """Fetch tenant config. Returns None if not found."""
    with get_session() as session:
        tenant: TenantConfig | None = (
            session.query(TenantConfig).filter_by(tenant_id=tenant_id).first()
        )
        if tenant is None:
            return None
        return TenantRecord(
            tenant_id=tenant.tenant_id,
            wa_api_key_encrypted=tenant.wa_api_key_encrypted,
            google_sheet_id=tenant.google_sheet_id,
            payment_provider=tenant.payment_provider,
            owner_wa_number=tenant.owner_wa_number,
        )
```

- [ ] **Step 4: Implement `app/db/chat_log_repo.py`**

```python
"""Chat log repository."""
from datetime import datetime
from typing import Optional

from app.db.engine import get_session
from app.db.models import ChatLog


def insert_chat_log(
    thread_id: str,
    tenant_id: str,
    wa_number: str,
    status: str,
    intent: Optional[str] = None,
    confidence: Optional[float] = None,
    response: Optional[str] = None,
    fallback_reason: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> int:
    """Insert a chat log entry. Returns the new row id."""
    with get_session() as session:
        log = ChatLog(
            thread_id=thread_id,
            tenant_id=tenant_id,
            wa_number=wa_number,
            intent=intent,
            confidence=confidence,
            response=response,
            fallback_reason=fallback_reason,
            status=status,
            timestamp=timestamp or datetime.utcnow(),
        )
        session.add(log)
        session.commit()
        return log.id
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_repos.py -v`
Expected: 4 tests pass

> **Note**: The fixture `reset_db` uses module-level `_engine` to override the cached engine for tests. After this task, update `app/db/engine.py` to use a private `_engine` module variable so tests can swap it cleanly.

- [ ] **Step 6: Refactor `app/db/engine.py` to support test override**

Replace the `get_engine()` function and add a module-level `_engine` variable:

```python
"""SQLAlchemy engine and session factory."""
import os
from functools import lru_cache
from typing import Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine: Optional[Engine] = None


def _build_default_engine() -> Engine:
    settings = get_settings()
    db_path = settings.checkpointer_db_path
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )


def get_engine() -> Engine:
    """Return the cached engine (lazy-initialized). Tests can override via _engine var."""
    global _engine
    if _engine is None:
        _engine = _build_default_engine()
    return _engine


def reset_engine_for_testing(engine: Engine) -> None:
    """Test helper: replace the cached engine."""
    global _engine
    _engine = engine


@lru_cache(maxsize=1)
def get_session_factory():
    engine = get_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Session:
    """Context-manager compatible session."""
    SessionLocal = get_session_factory()
    return SessionLocal()
```

- [ ] **Step 7: Re-run repo tests to confirm**

Run: `pytest tests/test_repos.py -v`
Expected: 4 tests pass

---

## Task 6: Wablas Client Service

**Files:**
- Create: `app/services/wablas.py`
- Test: `tests/test_wablas.py`

- [ ] **Step 1: Write failing test `tests/test_wablas.py`**

```python
"""Tests for app.services.wablas."""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.wablas import WablasClient, WablasError


@pytest.fixture
def client():
    return WablasClient(
        base_url="https://api.wablas.com",
        api_key="test-key-xyz",
        device_id="device-abc",
    )


def test_send_message_makes_post_request(client):
    with patch("app.services.wablas.httpx.AsyncClient") as mock_client_cls:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {"status": "success", "message_id": "msg-123"}
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        import asyncio
        result = asyncio.run(
            client.send_message(phone="+6281234567890", message="Halo!")
        )

        assert result["status"] == "success"
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "v1/send-message" in call_args[0][0] or "send-message" in str(call_args)
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-key-xyz"


def test_send_message_retries_on_5xx(client):
    with patch("app.services.wablas.httpx.AsyncClient") as mock_client_cls:
        mock_response_fail = AsyncMock()
        mock_response_fail.status_code = 503
        mock_response_fail.raise_for_status.side_effect = Exception("503")

        mock_response_ok = AsyncMock()
        mock_response_ok.status_code = 200
        mock_response_ok.json = lambda: {"status": "ok"}
        mock_response_ok.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[mock_response_fail, mock_response_ok])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        import asyncio
        result = asyncio.run(
            client.send_message(phone="+628123", message="Hi")
        )

        assert result["status"] == "ok"
        assert mock_client.post.call_count == 2


def test_send_message_raises_after_max_retries(client):
    with patch("app.services.wablas.httpx.AsyncClient") as mock_client_cls:
        mock_response_fail = AsyncMock()
        mock_response_fail.status_code = 503
        mock_response_fail.raise_for_status.side_effect = Exception("503")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response_fail)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        import asyncio
        with pytest.raises(WablasError):
            asyncio.run(client.send_message(phone="+628123", message="Hi"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wablas.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/services/wablas.py`**

```python
"""Wablas API client adapter."""
import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class WablasError(Exception):
    """Raised when Wablas API call fails after retries."""


class WablasClient:
    """Async client for Wablas WhatsApp API.

    Endpoint: POST /api/v1/send-message
    Auth: Bearer <api_key> header
    Body: {"phone": "+62xxx", "message": "text"}
    """

    def __init__(self, base_url: str, api_key: str, device_id: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.device_id = device_id
        self.max_retries = 3

    async def send_message(self, phone: str, message: str) -> dict[str, Any]:
        """Send text message to a WhatsApp number. Returns API response dict.

        Retries 3x on 5xx with exponential backoff. Raises WablasError after exhaustion.
        """
        url = f"{self.base_url}/api/v1/send-message"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"phone": phone, "message": message}
        if self.device_id:
            payload["device_id"] = self.device_id

        last_exception: Exception | None = None

        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code >= 500:
                        raise WablasError(f"Wablas {response.status_code}")

                    response.raise_for_status()
                    return response.json()

                except (httpx.HTTPStatusError, WablasError, httpx.RequestError) as e:
                    last_exception = e
                    logger.warning(
                        "wablas_send_attempt_failed",
                        extra={"attempt": attempt, "phone": phone[-4:], "error": str(e)},
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.1 * (2 ** (attempt - 1)))

        raise WablasError(f"Failed after {self.max_retries} retries: {last_exception}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wablas.py -v`
Expected: 3 tests pass

---

## Task 7: Google Sheets Client Service

**Files:**
- Create: `app/services/sheets.py`
- Test: `tests/test_sheets.py`

- [ ] **Step 1: Write failing test `tests/test_sheets.py`**

```python
"""Tests for app.services.sheets."""
import time
from unittest.mock import MagicMock

import pytest

from app.services.sheets import GoogleSheetsClient, SheetsError


@pytest.fixture
def client(tmp_path):
    creds_path = tmp_path / "creds.json"
    creds_path.write_text("{}")
    return GoogleSheetsClient(
        credentials_json_path=str(creds_path),
        spreadsheet_id="sheet-abc",
    )


def test_read_faq_returns_rows(client, monkeypatch):
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[
            {"pertanyaan": "Harga?", "jawaban": "Rp 50.000"},
            {"pertanyaan": "Warna?", "jawaban": "Merah, Biru"},
        ]
    )

    with patch_object_gspread(mock_worksheet):
        rows = client.read_faq()
        assert len(rows) == 2
        assert rows[0]["pertanyaan"] == "Harga?"


def test_read_catalog_returns_rows(client):
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[
            {"nama_produk": "Kaos Polos", "harga": "50000", "ready": "Y", "deskripsi": "100% katun"},
        ]
    )

    with patch_object_gspread(mock_worksheet):
        rows = client.read_catalog()
        assert len(rows) == 1
        assert rows[0]["nama_produk"] == "Kaos Polos"


def test_lookup_faq_finds_match(client):
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[
            {"pertanyaan": "Berapa harga?", "jawaban": "Mulai Rp 50.000"},
            {"pertanyaan": "Ada warna merah?", "jawaban": "Ada, Ready stock"},
        ]
    )

    with patch_object_gspread(mock_worksheet):
        client.clear_cache()  # type: ignore[attr-defined]
        match = client.lookup_faq("harga berapa")
        assert match is not None
        assert "Rp 50.000" in match["jawaban"]


def test_lookup_faq_no_match_returns_none(client):
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[{"pertanyaan": "Halo", "jawaban": "Hai juga"}]
    )

    with patch_object_gspread(mock_worksheet):
        client.clear_cache()  # type: ignore[attr-defined]
        match = client.lookup_faq("xyzzy")
        assert match is None


# Helper
def patch_object_gspread(mock_worksheet):
    from contextlib import contextmanager

    @contextmanager
    def cm():
        from unittest.mock import patch
        with patch("app.services.sheets.gspread") as mock_gspread:
            mock_client = MagicMock()
            mock_sheet = MagicMock()
            mock_sheet.worksheet = MagicMock(return_value=mock_worksheet)
            mock_client.open_by_key = MagicMock(return_value=mock_sheet)
            mock_gspread.service_account = MagicMock(return_value=mock_client)
            yield

    return cm()


def test_60s_cache_avoids_recalling_api(client):
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_records = MagicMock(
        return_value=[{"pertanyaan": "Halo", "jawaban": "Hai"}]
    )

    with patch_object_gspread(mock_worksheet):
        client._cache_ttl_seconds = 60
        client.clear_cache()  # type: ignore[attr-defined]

        # First call
        client.read_faq()
        # Second call within TTL — should NOT call get_all_records again
        client.read_faq()

        # get_all_records only called once due to cache
        assert mock_worksheet.get_all_records.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sheets.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/services/sheets.py`**

```python
"""Google Sheets client adapter — reads FAQ & Katalog tabs."""
import logging
import time
from threading import Lock
from typing import Any

import gspread

logger = logging.getLogger(__name__)


class SheetsError(Exception):
    """Raised when Sheets API call fails."""


class GoogleSheetsClient:
    """Reads FAQ and Katalog tabs from a tenant's Google Sheet.

    Caches reads for 60 seconds per tab to avoid rate limits.
    """

    CACHE_TTL_SECONDS = 60

    def __init__(self, credentials_json_path: str, spreadsheet_id: str):
        self.credentials_json_path = credentials_json_path
        self.spreadsheet_id = spreadsheet_id
        self._client: Any = None
        self._spreadsheet: Any = None
        self._cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
        self._lock = Lock()

    def _get_spreadsheet(self):
        if self._spreadsheet is None:
            try:
                gc = gspread.service_account(filename=self.credentials_json_path)
                self._spreadsheet = gc.open_by_key(self.spreadsheet_id)
            except Exception as e:
                raise SheetsError(f"Failed to open sheet: {e}") from e
        return self._spreadsheet

    def _read_tab(self, tab_name: str) -> list[dict[str, str]]:
        """Read a tab with caching."""
        with self._lock:
            now = time.time()
            cached = self._cache.get(tab_name)
            if cached and (now - cached[0]) < self.CACHE_TTL_SECONDS:
                logger.debug("sheets_cache_hit", extra={"tab": tab_name})
                return cached[1]

            try:
                sheet = self._get_spreadsheet()
                worksheet = sheet.worksheet(tab_name)
                rows = worksheet.get_all_records()
                rows_list = [dict(r) for r in rows]
                self._cache[tab_name] = (now, rows_list)
                logger.info(
                    "sheets_read_ok",
                    extra={"tab": tab_name, "rows": len(rows_list)},
                )
                return rows_list
            except Exception as e:
                raise SheetsError(f"Failed to read tab {tab_name}: {e}") from e

    def read_faq(self) -> list[dict[str, str]]:
        return self._read_tab("FAQ")

    def read_catalog(self) -> list[dict[str, str]]:
        return self._read_tab("Katalog")

    def lookup_faq(self, message: str) -> dict[str, str] | None:
        """Simple keyword lookup. Returns first row whose 'pertanyaan' contains message keywords."""
        message_lower = message.lower()
        words = [w for w in message_lower.split() if len(w) >= 3]
        if not words:
            return None

        for row in self.read_faq():
            pertanyaan = (row.get("pertanyaan") or "").lower()
            if any(w in pertanyaan for w in words):
                return row
        return None

    def clear_cache(self) -> None:
        """Test helper: clear the cache."""
        with self._lock:
            self._cache.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_sheets.py -v`
Expected: 5 tests pass

---

## Task 8: Claude Haiku LLM Client

**Files:**
- Create: `app/services/llm.py`
- Test: `tests/test_llm.py`

- [ ] **Step 1: Write failing test `tests/test_llm.py`**

```python
"""Tests for app.services.llm."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.llm import ClaudeHaikuClient, LLMError


def test_classify_returns_intent_and_confidence():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text=json.dumps({
        "intent": "faq",
        "confidence": 0.85,
    }))]

    mock_message = MagicMock()
    mock_message.model_copy = MagicMock(return_value=mock_message)
    mock_message.__add__ = MagicMock(return_value=mock_message)

    with patch("app.services.llm.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        client = ClaudeHaikuClient(api_key="test-key")
        result = client.classify("Berapa harga kaos?")

        assert result["intent"] == "faq"
        assert result["confidence"] == 0.85


def test_classify_handles_invalid_json():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="not json")]

    with patch("app.services.llm.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        client = ClaudeHaikuClient(api_key="test-key")
        with pytest.raises(LLMError):
            client.classify("test")


def test_classify_validates_intent_values():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text=json.dumps({
        "intent": "invalid_intent",
        "confidence": 0.5,
    }))]

    with patch("app.services.llm.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        client = ClaudeHaikuClient(api_key="test-key")
        with pytest.raises(LLMError, match="Invalid intent"):
            client.classify("test")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/services/llm.py`**

```python
"""Claude Haiku client for intent classification."""
import json
import logging
from typing import Any

import anthropic

from app.graph.prompts import INTENT_CLASSIFICATION_SYSTEM, INTENT_CLASSIFICATION_USER

logger = logging.getLogger(__name__)

VALID_INTENTS = {"faq", "check_product", "confirm_order", "unclear"}


class LLMError(Exception):
    """Raised when LLM call fails or returns invalid output."""


class ClaudeHaikuClient:
    """Wraps Anthropic SDK for Claude Haiku intent classification."""

    MODEL = "claude-haiku-4-5"

    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)

    def classify(self, message: str) -> dict[str, Any]:
        """Classify user message intent. Returns {intent, confidence}.

        Raises LLMError if API fails or response is invalid.
        """
        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=128,
                system=INTENT_CLASSIFICATION_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": INTENT_CLASSIFICATION_USER.format(message=message),
                    }
                ],
            )

            text_block = next(
                (b for b in response.content if b.type == "text"),
                None,
            )
            if text_block is None:
                raise LLMError("No text block in response")

            result = json.loads(text_block.text)

            intent = result.get("intent")
            confidence = result.get("confidence")

            if intent not in VALID_INTENTS:
                raise LLMError(f"Invalid intent from LLM: {intent}")
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                raise LLMError(f"Invalid confidence from LLM: {confidence}")

            return {"intent": intent, "confidence": float(confidence)}

        except json.JSONDecodeError as e:
            raise LLMError(f"Invalid JSON from LLM: {e}") from e
        except anthropic.APIError as e:
            raise LLMError(f"Anthropic API error: {e}") from e
```

- [ ] **Step 4: Create `app/graph/__init__.py`**

```python
"""LangGraph state graph."""
```

- [ ] **Step 5: Create `app/graph/prompts.py`**

```python
"""Prompt templates for LLM calls."""

INTENT_CLASSIFICATION_SYSTEM = """You are an intent classifier for a WhatsApp customer service bot for an Indonesian UMKM seller.

Classify the buyer's message into ONE of these intents:
- "faq": general questions about price, shipping, store info, hours, payment methods, etc.
- "check_product": buyer asks about a specific product (stock, color, size, variant)
- "confirm_order": buyer wants to place or confirm an order
- "unclear": message is gibberish, too short, or off-topic

Respond ONLY with a JSON object in this exact format:
{"intent": "<one of the four>", "confidence": <float 0.0-1.0>}

Confidence reflects how certain you are. If the message is ambiguous, set confidence < 0.6."""

INTENT_CLASSIFICATION_USER = """Classify this buyer message:

\"{message}\""""
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_llm.py -v`
Expected: 3 tests pass

---

## Task 9: Signature Verification (Auth)

**Files:**
- Create: `app/auth/__init__.py`
- Create: `app/auth/signature.py`
- Test: `tests/test_signature.py`

- [ ] **Step 1: Create `app/auth/__init__.py`**

```python
"""Auth layer."""
```

- [ ] **Step 2: Write failing test `tests/test_signature.py`**

```python
"""Tests for app.auth.signature."""
import hmac
import hashlib

import pytest

from app.auth.signature import SignatureError, verify_wablas_signature


SECRET = "test-wablas-api-key-xyz"
BODY = b'{"phone": "+6281234567890", "message": "Halo"}'


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_valid_signature_returns_true():
    sig = _sign(BODY, SECRET)
    assert verify_wablas_signature(sig, BODY, SECRET) is True


def test_verify_invalid_signature_returns_false():
    sig = _sign(BODY, SECRET)
    assert verify_wablas_signature(sig, BODY, "wrong-secret") is False
    assert verify_wablas_signature("deadbeef", BODY, SECRET) is False


def test_verify_empty_signature_raises():
    with pytest.raises(SignatureError):
        verify_wablas_signature("", BODY, SECRET)


def test_verify_constant_time_compare():
    """Verify uses hmac.compare_digest (smoke test — just ensure no exception on equal length)."""
    sig = _sign(BODY, SECRET)
    # If we use hmac.compare_digest, valid signature returns True
    assert verify_wablas_signature(sig, BODY, SECRET) is True
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_signature.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement `app/auth/signature.py`**

```python
"""Wablas webhook signature verification.

Wablas sends an HMAC SHA-256 signature in the request header (typically X-Wablas-Signature
— exact name TBD, will be confirmed during implementation).

The signature is computed over the raw request body using the tenant's Wablas API key.
"""
import hmac
import hashlib


class SignatureError(Exception):
    """Raised when signature header is missing or malformed."""


def verify_wablas_signature(
    signature_header: str,
    request_body: bytes,
    secret: str,
) -> bool:
    """Verify a Wablas webhook signature using HMAC SHA-256 with constant-time compare.

    Returns True if signature is valid, False otherwise.
    Raises SignatureError if signature_header is missing/empty.
    """
    if not signature_header:
        raise SignatureError("Missing signature header")

    expected = hmac.new(
        secret.encode("utf-8"),
        request_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_signature.py -v`
Expected: 4 tests pass

---

## Task 10: LangGraph State & All Nodes

**Files:**
- Create: `app/graph/state.py`
- Create: `app/graph/nodes.py`
- Test: `tests/test_classify.py`
- Test: `tests/test_lookup.py`
- Test: `tests/test_fallback.py`

- [ ] **Step 1: Create `app/graph/state.py`**

```python
"""LangGraph state schema."""
from datetime import datetime
from typing import Literal, TypedDict

Action = Literal["reply", "fallback", "order"]
Intent = Literal["faq", "check_product", "confirm_order", "unclear"]


class ChatState(TypedDict, total=False):
    # Input
    tenant_id: str
    wa_number: str
    thread_id: str
    message_text: str
    timestamp: datetime

    # Classify output
    intent: Intent
    confidence: float

    # Lookup output
    catalog_answer: str | None
    product_match: dict | None

    # Compose output
    reply_text: str

    # Final action
    action: Action
    fallback_reason: str | None
```

- [ ] **Step 2: Write failing test `tests/test_classify.py`**

```python
"""Tests for classify_intent node."""
from unittest.mock import MagicMock

import pytest

from app.graph.nodes import classify_intent
from app.graph.state import ChatState
from app.services.llm import LLMError


def test_classify_intent_writes_intent_and_confidence():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "Berapa harga kaos?",
    }

    fake_llm = MagicMock()
    fake_llm.classify = MagicMock(return_value={"intent": "faq", "confidence": 0.85})

    result = classify_intent(state, llm_client=fake_llm)

    assert result["intent"] == "faq"
    assert result["confidence"] == 0.85


def test_classify_intent_low_confidence_returns_unclear():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "zzzqx",
    }

    fake_llm = MagicMock()
    fake_llm.classify = MagicMock(return_value={"intent": "faq", "confidence": 0.3})

    result = classify_intent(state, llm_client=fake_llm)

    # Original intent kept, but caller (graph router) checks confidence
    assert result["intent"] == "faq"
    assert result["confidence"] == 0.3


def test_classify_intent_llm_error_raises():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
    }

    fake_llm = MagicMock()
    fake_llm.classify = MagicMock(side_effect=LLMError("timeout"))

    with pytest.raises(LLMError):
        classify_intent(state, llm_client=fake_llm)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_classify.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement `app/graph/nodes.py` (initial version with classify_intent)**

```python
"""LangGraph nodes for OrderCloser Lite."""
import logging
from typing import Any

from app.db.chat_log_repo import insert_chat_log
from app.graph.state import ChatState
from app.services.llm import LLMError

logger = logging.getLogger(__name__)


def classify_intent(state: ChatState, llm_client: Any) -> dict:
    """Classify user message into one of 4 intents.

    Returns dict update for state: {intent, confidence}
    Raises LLMError if classification fails (caller decides whether to fallback).
    """
    try:
        result = llm_client.classify(state["message_text"])
        logger.info(
            "intent_classified",
            extra={
                "tenant_id": state["tenant_id"],
                "intent": result["intent"],
                "confidence": result["confidence"],
            },
        )
        return {"intent": result["intent"], "confidence": result["confidence"]}
    except LLMError as e:
        logger.error("intent_classification_failed", extra={"error": str(e)})
        raise


def lookup_catalog(state: ChatState, sheets_client: Any) -> dict:
    """Lookup answer in Sheets based on intent.

    For intent=faq: call sheets_client.lookup_faq()
    For intent=check_product: call sheets_client.read_catalog() and do simple keyword match
    Returns dict update: {catalog_answer, product_match} or empty dict if no match.
    """
    intent = state["intent"]

    if intent == "faq":
        match = sheets_client.lookup_faq(state["message_text"])
        if match is None:
            logger.info(
                "faq_no_match",
                extra={"tenant_id": state["tenant_id"], "thread_id": state["thread_id"]},
            )
            return {}
        return {"catalog_answer": match["jawaban"], "product_match": None}

    if intent == "check_product":
        products = sheets_client.read_catalog()
        message_lower = state["message_text"].lower()
        words = [w for w in message_lower.split() if len(w) >= 3]
        for product in products:
            nama = (product.get("nama_produk") or "").lower()
            if any(w in nama for w in words):
                return {
                    "catalog_answer": None,
                    "product_match": product,
                }
        return {}

    return {}
```

- [ ] **Step 5: Run classify test to verify it passes**

Run: `pytest tests/test_classify.py -v`
Expected: 3 tests pass

- [ ] **Step 6: Write failing test `tests/test_lookup.py`**

```python
"""Tests for lookup_catalog node."""
from unittest.mock import MagicMock

from app.graph.nodes import lookup_catalog
from app.graph.state import ChatState


def test_lookup_faq_finds_match():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "Berapa harga?",
        "intent": "faq",
    }

    fake_sheets = MagicMock()
    fake_sheets.lookup_faq = MagicMock(
        return_value={"pertanyaan": "Berapa harga?", "jawaban": "Mulai Rp 50.000"}
    )

    result = lookup_catalog(state, sheets_client=fake_sheets)

    assert result["catalog_answer"] == "Mulai Rp 50.000"
    assert result["product_match"] is None


def test_lookup_faq_no_match_returns_empty():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "xyzzy",
        "intent": "faq",
    }

    fake_sheets = MagicMock()
    fake_sheets.lookup_faq = MagicMock(return_value=None)

    result = lookup_catalog(state, sheets_client=fake_sheets)
    assert result == {}


def test_lookup_product_finds_match():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "Kaos ready ga?",
        "intent": "check_product",
    }

    fake_sheets = MagicMock()
    fake_sheets.read_catalog = MagicMock(
        return_value=[
            {"nama_produk": "Kaos Polos", "harga": "50000", "ready": "Y", "deskripsi": "Katun"},
            {"nama_produk": "Topi", "harga": "30000", "ready": "Y", "deskripsi": "Standar"},
        ]
    )

    result = lookup_catalog(state, sheets_client=fake_sheets)

    assert result["product_match"] is not None
    assert result["product_match"]["nama_produk"] == "Kaos Polos"
```

- [ ] **Step 7: Run lookup test to verify it passes**

Run: `pytest tests/test_lookup.py -v`
Expected: 3 tests pass

- [ ] **Step 8: Add remaining nodes (compose_reply, send_whatsapp, fallback_human)**

Append to `app/graph/nodes.py`:

```python
def compose_reply(state: ChatState) -> dict:
    """Compose reply text from state. Returns {reply_text, action}."""
    intent = state["intent"]

    if intent == "faq":
        if state.get("catalog_answer"):
            return {
                "reply_text": f"{state['catalog_answer']}",
                "action": "reply",
            }
        return _compose_fallback_message(state, reason="no_faq_match")

    if intent == "check_product":
        if state.get("product_match"):
            p = state["product_match"]
            ready = "✅ Ready stock" if p.get("ready") == "Y" else "❌ Habis"
            return {
                "reply_text": (
                    f"{p['nama_produk']} — {p.get('harga', '-')}\n"
                    f"{ready}\n"
                    f"{p.get('deskripsi', '')}"
                ),
                "action": "reply",
            }
        return _compose_fallback_message(state, reason="no_product_match")

    if intent == "confirm_order":
        return {
            "reply_text": (
                "Terima kasih ordernya! Owner akan follow up untuk konfirmasi "
                "pembayaran ya 🙏"
            ),
            "action": "order",
        }

    return _compose_fallback_message(state, reason="unknown_intent")


def _compose_fallback_message(state: ChatState, reason: str) -> dict:
    return {
        "reply_text": "Sedang kami cek, owner akan follow up ya 🙏",
        "action": "fallback",
        "fallback_reason": reason,
    }


async def send_whatsapp(state: ChatState, wablas_client: Any) -> dict:
    """Send reply_text to buyer via Wablas. Returns {} on success.

    Returns {action: "error", response: <error>} if all retries fail.
    Does NOT raise — caller must check return.
    """
    from app.services.wablas import WablasError

    try:
        await wablas_client.send_message(
            phone=state["wa_number"],
            message=state["reply_text"],
        )
        logger.info(
            "whatsapp_sent",
            extra={
                "tenant_id": state["tenant_id"],
                "thread_id": state["thread_id"],
            },
        )
        return {}
    except WablasError as e:
        logger.error(
            "whatsapp_send_failed",
            extra={
                "tenant_id": state["tenant_id"],
                "thread_id": state["thread_id"],
                "error": str(e),
            },
        )
        return {"action": "error"}


async def fallback_human(state: ChatState, wablas_client: Any) -> dict:
    """Forward original message to owner via Wablas. Also sends buyer acknowledgement.

    Caller MUST have already set fallback_reason before calling.
    Returns {} on success, {action: "error"} if Wablas fails.
    """
    from app.services.wablas import WablasError

    # Need owner_wa_number — but it's not in ChatState. Read from tenant repo.
    from app.db.tenant_repo import get_tenant

    tenant = get_tenant(state["tenant_id"])
    if tenant is None:
        logger.error(
            "fallback_tenant_not_found",
            extra={"tenant_id": state["tenant_id"]},
        )
        return {"action": "error"}

    owner_msg = (
        f"[FALLBACK] Pesan dari {state['wa_number']}:\n\n{state['message_text']}\n\n"
        f"Intent: {state.get('intent', 'n/a')}\n"
        f"Confidence: {state.get('confidence', 'n/a')}\n"
        f"Reason: {state.get('fallback_reason', 'n/a')}"
    )

    try:
        # 1. Send to owner
        await wablas_client.send_message(
            phone=tenant["owner_wa_number"],
            message=owner_msg,
        )
        # 2. Send acknowledgement to buyer
        await wablas_client.send_message(
            phone=state["wa_number"],
            message="Sedang kami cek, owner akan follow up ya 🙏",
        )
        logger.info(
            "fallback_triggered",
            extra={
                "tenant_id": state["tenant_id"],
                "thread_id": state["thread_id"],
                "reason": state.get("fallback_reason"),
            },
        )
        return {}
    except WablasError as e:
        logger.error("fallback_send_failed", extra={"error": str(e)})
        return {"action": "error"}


def write_chat_log(state: ChatState) -> dict:
    """Persist chat log entry to SQLite. Best-effort, never raises."""
    try:
        insert_chat_log(
            thread_id=state["thread_id"],
            tenant_id=state["tenant_id"],
            wa_number=state["wa_number"],
            intent=state.get("intent"),
            confidence=state.get("confidence"),
            response=state.get("reply_text"),
            fallback_reason=state.get("fallback_reason"),
            status=state.get("action", "error"),
        )
    except Exception as e:  # noqa: BLE001
        logger.error("chat_log_insert_failed", extra={"error": str(e)})
    return {}
```

- [ ] **Step 9: Write failing test `tests/test_fallback.py`**

```python
"""Tests for fallback_human and compose_reply fallback paths."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.graph.nodes import fallback_human, compose_reply
from app.graph.state import ChatState


def test_compose_reply_faq_with_answer():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "harga?",
        "intent": "faq",
        "catalog_answer": "Mulai Rp 50.000",
    }
    result = compose_reply(state)
    assert result["action"] == "reply"
    assert "Rp 50.000" in result["reply_text"]


def test_compose_reply_faq_no_match_triggers_fallback():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "xyzzy",
        "intent": "faq",
    }
    result = compose_reply(state)
    assert result["action"] == "fallback"
    assert result["fallback_reason"] == "no_faq_match"


def test_compose_reply_confirm_order():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "Saya order 1",
        "intent": "confirm_order",
    }
    result = compose_reply(state)
    assert result["action"] == "order"
    assert "Owner akan follow up" in result["reply_text"]


@pytest.mark.asyncio
async def test_fallback_human_sends_to_owner_and_buyer():
    fake_wablas = MagicMock()
    fake_wablas.send_message = AsyncMock(return_value={"status": "ok"})

    fake_tenant_repo = MagicMock()
    fake_tenant_repo.get_tenant = MagicMock(
        return_value={
            "tenant_id": "demo",
            "wa_api_key_encrypted": b"\x00" * 32,
            "google_sheet_id": "sheet-abc",
            "payment_provider": "xendit",
            "owner_wa_number": "+628111111",
        }
    )

    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "halo",
        "fallback_reason": "unclear",
    }

    with patch("app.graph.nodes.get_tenant", fake_tenant_repo.get_tenant):
        result = await fallback_human(state, wablas_client=fake_wablas)

    assert result == {}
    # Two calls: owner + buyer
    assert fake_wablas.send_message.call_count == 2
    owner_call = fake_wablas.send_message.call_args_list[0]
    assert owner_call[1]["phone"] == "+628111111"
    buyer_call = fake_wablas.send_message.call_args_list[1]
    assert buyer_call[1]["phone"] == "+628999"


@pytest.mark.asyncio
async def test_fallback_human_wablas_error():
    fake_wablas = MagicMock()
    fake_wablas.send_message = AsyncMock(side_effect=Exception("wablas down"))

    fake_tenant = {
        "tenant_id": "demo",
        "wa_api_key_encrypted": b"\x00" * 32,
        "google_sheet_id": "sheet-abc",
        "payment_provider": "xendit",
        "owner_wa_number": "+628111111",
    }

    with patch("app.graph.nodes.get_tenant", return_value=fake_tenant):
        state: ChatState = {
            "tenant_id": "demo",
            "wa_number": "+628999",
            "thread_id": "demo:+628999",
            "message_text": "halo",
            "fallback_reason": "unclear",
        }
        result = await fallback_human(state, wablas_client=fake_wablas)
        assert result["action"] == "error"
```

- [ ] **Step 10: Add pytest-asyncio configuration & run fallback tests**

Run: `pip install pytest-asyncio` (already in dev deps — verify install)

Run: `pytest tests/test_fallback.py -v`
Expected: 5 tests pass (3 compose_reply + 2 fallback_human)

---

## Task 11: Build LangGraph Graph

**Files:**
- Create: `app/graph/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write failing test `tests/test_graph.py`**

```python
"""Tests for app.graph.graph — verify routing logic."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.graph.graph import should_fallback, route_after_classify
from app.graph.state import ChatState


def test_should_fallback_low_confidence():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "faq",
        "confidence": 0.3,
    }
    assert should_fallback(state, threshold=0.6) is True


def test_should_fallback_unclear_intent():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "unclear",
        "confidence": 0.95,
    }
    assert should_fallback(state, threshold=0.6) is True


def test_should_not_fallback_high_confidence_faq():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "faq",
        "confidence": 0.9,
    }
    assert should_fallback(state, threshold=0.6) is False


def test_route_after_classify_returns_lookup_for_faq():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "faq",
        "confidence": 0.9,
    }
    assert route_after_classify(state) == "lookup_catalog"


def test_route_after_classify_returns_fallback_for_low_conf():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "faq",
        "confidence": 0.3,
    }
    assert route_after_classify(state) == "fallback_human"


def test_route_after_classify_returns_fallback_for_unclear():
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "unclear",
        "confidence": 0.95,
    }
    assert route_after_classify(state) == "fallback_human"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_graph.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/graph/graph.py`**

```python
"""LangGraph state graph assembly & routing functions."""
import logging

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.graph.nodes import (
    classify_intent,
    compose_reply,
    fallback_human,
    lookup_catalog,
    send_whatsapp,
    write_chat_log,
)
from app.graph.state import ChatState

logger = logging.getLogger(__name__)


def should_fallback(state: ChatState, threshold: float | None = None) -> bool:
    """Decide whether to route to fallback based on confidence & intent."""
    if threshold is None:
        threshold = get_settings().intent_confidence_threshold

    if state.get("intent") == "unclear":
        return True
    if state.get("confidence", 0.0) < threshold:
        return True
    return False


def route_after_classify(state: ChatState) -> str:
    """Route after classify_intent node."""
    return "fallback_human" if should_fallback(state) else "lookup_catalog"


def route_after_lookup(state: ChatState) -> str:
    """Route after lookup_catalog node. Fallback if lookup returned nothing for faq/product."""
    intent = state.get("intent")
    if intent == "faq" and not state.get("catalog_answer"):
        return "compose_reply_fallback"
    if intent == "check_product" and not state.get("product_match"):
        return "compose_reply_fallback"
    return "compose_reply"


async def _classify_node_async(state, llm_client):
    """Async wrapper for classify_intent (which is sync)."""
    return classify_intent(state, llm_client=llm_client)


async def _lookup_node_async(state, sheets_client):
    """Async wrapper for lookup_catalog."""
    return lookup_catalog(state, sheets_client=sheets_client)


async def _compose_async(state):
    return compose_reply(state)


async def _send_async(state, wablas_client):
    state.update(await send_whatsapp(state, wablas_client=wablas_client))
    return {}


async def _fallback_async(state, wablas_client):
    state.update(await fallback_human(state, wablas_client=wablas_client))
    return {}


async def _compose_fallback_node(state):
    """Compose fallback message (called when lookup returns nothing)."""
    return {
        "reply_text": "Sedang kami cek, owner akan follow up ya 🙏",
        "action": "fallback",
        "fallback_reason": (
            "no_faq_match" if state.get("intent") == "faq"
            else "no_product_match" if state.get("intent") == "check_product"
            else "no_match"
        ),
    }


def build_graph(llm_client, sheets_client, wablas_client):
    """Construct and compile the StateGraph.

    Flow:
      START -> classify -> (lookup OR fallback)
             lookup -> (compose OR compose_fallback)
             fallback -> END
             compose -> send -> log -> END
    """
    g = StateGraph(ChatState)

    # Add nodes
    g.add_node("classify_intent", lambda s: _classify_node_async(s, llm_client))
    g.add_node("lookup_catalog", lambda s: _lookup_node_async(s, sheets_client))
    g.add_node("compose_reply", _compose_async)
    g.add_node("compose_reply_fallback", _compose_fallback_node)
    g.add_node("send_whatsapp", lambda s: _send_async(s, wablas_client))
    g.add_node("fallback_human", lambda s: _fallback_async(s, wablas_client))
    g.add_node("write_chat_log", write_chat_log)

    # Edges
    g.add_edge(START, "classify_intent")
    g.add_conditional_edges(
        "classify_intent",
        route_after_classify,
        {"lookup_catalog": "lookup_catalog", "fallback_human": "fallback_human"},
    )
    g.add_conditional_edges(
        "lookup_catalog",
        route_after_lookup,
        {
            "compose_reply": "compose_reply",
            "compose_reply_fallback": "compose_reply_fallback",
        },
    )
    g.add_edge("compose_reply", "send_whatsapp")
    g.add_edge("compose_reply_fallback", "fallback_human")
    g.add_edge("send_whatsapp", "write_chat_log")
    g.add_edge("fallback_human", "write_chat_log")
    g.add_edge("write_chat_log", END)

    return g.compile()


# Create compiled graph at module level for easy injection
_compiled_graph = None


def get_compiled_graph(llm_client=None, sheets_client=None, wablas_client=None):
    """Get the compiled graph (lazy-init). Tests must inject clients."""
    global _compiled_graph
    if _compiled_graph is None:
        if llm_client is None or sheets_client is None or wablas_client is None:
            raise RuntimeError("Clients not injected — call build_graph() explicitly first")
        _compiled_graph = build_graph(llm_client, sheets_client, wablas_client)
    return _compiled_graph


def reset_compiled_graph_for_testing() -> None:
    """Test helper: reset cached compiled graph."""
    global _compiled_graph
    _compiled_graph = None
```

- [ ] **Step 4: Run graph tests to verify they pass**

Run: `pytest tests/test_graph.py -v`
Expected: 6 tests pass

---

## Task 12: FastAPI App & Webhook Endpoint

**Files:**
- Create: `app/main.py`
- Create: `app/webhook.py`
- Create: `app/health.py`
- Test: `tests/test_webhook.py`

- [ ] **Step 1: Create `app/health.py`**

```python
"""Health & readiness endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.config import get_settings
from app.db.engine import get_engine

router = APIRouter()


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz():
    checks = {}

    # Check SQLite
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["sqlite"] = "ok"
    except Exception as e:
        checks["sqlite"] = f"error: {e}"

    # Check Sheets (only if credentials path exists)
    import os
    settings = get_settings()
    if os.path.exists(settings.google_sheets_credentials_json_path):
        try:
            from app.services.sheets import GoogleSheetsClient, SheetsError
            client = GoogleSheetsClient(
                credentials_json_path=settings.google_sheets_credentials_json_path,
                spreadsheet_id="dummy",
            )
            # Just attempt to construct — real fetch will happen on first use
            checks["sheets_config"] = "ok"
        except Exception as e:
            checks["sheets_config"] = f"error: {e}"
    else:
        checks["sheets_config"] = "creds_not_found"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
```

- [ ] **Step 2: Write failing test `tests/test_webhook.py`**

```python
"""Tests for webhook endpoint."""
import base64
import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.services.crypto import encrypt_api_key


@pytest.fixture
def tenant_env(monkeypatch):
    """Set required env vars and insert a tenant row in in-memory DB."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(b"x" * 32).decode())
    monkeypatch.setenv("WABLAS_BASE_URL", "https://api.wablas.com")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "./secrets/sheets-sa.json")

    # Reset settings cache
    get_settings.cache_clear()  # type: ignore[attr-defined]

    yield


@pytest.fixture
def client(tenant_env):
    """Build a fresh FastAPI TestClient with in-memory DB."""
    from app.db import engine as engine_mod
    from app.db.models import Base
    from sqlalchemy import create_engine

    engine_mod._engine = None  # type: ignore[attr-defined]
    engine_mod.get_session_factory.cache_clear()  # type: ignore[attr-defined]

    in_mem = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(in_mem)
    engine_mod._engine = in_mem  # type: ignore[attr-defined]

    # Insert tenant
    settings = get_settings()
    encrypted = encrypt_api_key("wablas-secret-key", settings.encryption_key)
    from app.db.tenant_repo import insert_tenant
    insert_tenant(
        tenant_id="demo",
        wa_api_key_encrypted=encrypted,
        google_sheet_id="sheet-abc",
        owner_wa_number="+628111111",
    )

    from app.main import create_app
    app = create_app()
    return TestClient(app)


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_webhook_invalid_signature_returns_401(client):
    body = b'{"phone":"+6281234567890","message":"halo"}'
    response = client.post(
        "/webhook/whatsapp/demo",
        content=body,
        headers={"Content-Type": "application/json", "X-Wablas-Signature": "bad"},
    )
    assert response.status_code == 401


def test_webhook_missing_signature_returns_401(client):
    body = b'{"phone":"+6281234567890","message":"halo"}'
    response = client.post(
        "/webhook/whatsapp/demo",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 401


def test_webhook_tenant_not_found_returns_404(client):
    body = b'{"phone":"+6281234567890","message":"halo"}'
    signature = _sign(body, "wablas-secret-key")
    response = client.post(
        "/webhook/whatsapp/unknown-tenant",
        content=body,
        headers={"Content-Type": "application/json", "X-Wablas-Signature": signature},
    )
    assert response.status_code == 404


def test_webhook_malformed_payload_returns_422(client):
    body = b"not-json"
    signature = _sign(body, "wablas-secret-key")
    response = client.post(
        "/webhook/whatsapp/demo",
        content=body,
        headers={"Content-Type": "application/json", "X-Wablas-Signature": signature},
    )
    assert response.status_code == 422


def test_webhook_valid_signature_returns_200(client):
    body = b'{"phone":"+6281234567890","message":"berapa harga?"}'

    # Mock the graph clients
    fake_wablas = MagicMock()
    fake_wablas.send_message = AsyncMock(return_value={"status": "ok"})

    fake_sheets = MagicMock()
    fake_sheets.lookup_faq = MagicMock(
        return_value={"pertanyaan": "berapa harga", "jawaban": "Rp 50.000"}
    )

    fake_llm = MagicMock()
    fake_llm.classify = MagicMock(return_value={"intent": "faq", "confidence": 0.9})

    with patch("app.webhook.WablasClient", return_value=fake_wablas), \
         patch("app.webhook.GoogleSheetsClient", return_value=fake_sheets), \
         patch("app.webhook.ClaudeHaikuClient", return_value=fake_llm), \
         patch("app.webhook.get_compiled_graph") as mock_get_graph:
        from app.graph.graph import build_graph
        compiled = build_graph(
            llm_client=fake_llm,
            sheets_client=fake_sheets,
            wablas_client=fake_wablas,
        )
        mock_get_graph.return_value = compiled

        signature = _sign(body, "wablas-secret-key")
        response = client.post(
            "/webhook/whatsapp/demo",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Wablas-Signature": signature,
            },
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_webhook.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement `app/webhook.py`**

```python
"""Webhook endpoint for Wablas WhatsApp messages."""
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Path, Request

from app.auth.signature import SignatureError, verify_wablas_signature
from app.config import get_settings
from app.db.tenant_repo import get_tenant
from app.services.crypto import decrypt_api_key
from app.services.crypto import CryptoError

logger = logging.getLogger(__name__)
router = APIRouter()


# Lazy singletons for clients (re-instantiated per request with tenant-specific keys).
# For Fase 1 MVP, these are constructed per-request; Fase 3 will cache per-tenant.


@router.post("/webhook/whatsapp/{tenant_id}")
async def webhook_whatsapp(
    request: Request,
    tenant_id: str = Path(...),
    x_wablas_signature: str | None = Header(default=None),
):
    """Receive a WhatsApp message from Wablas, verify signature, run LangGraph."""
    raw_body = await request.body()

    # 1. Load tenant
    tenant = get_tenant(tenant_id)
    if tenant is None:
        logger.warning("tenant_not_found", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found")

    # 2. Decrypt API key
    try:
        settings = get_settings()
        wa_api_key = decrypt_api_key(tenant["wa_api_key_encrypted"], settings.encryption_key)
    except CryptoError as e:
        logger.error("api_key_decrypt_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Internal config error")

    # 3. Verify signature
    if not x_wablas_signature:
        raise HTTPException(status_code=401, detail="Missing signature header")

    try:
        valid = verify_wablas_signature(
            signature_header=x_wablas_signature,
            request_body=raw_body,
            secret=wa_api_key,
        )
    except SignatureError as e:
        raise HTTPException(status_code=401, detail=str(e))

    if not valid:
        logger.warning("invalid_signature", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 4. Parse payload
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON body")

    phone = payload.get("phone") or payload.get("sender")
    message = payload.get("message", "").strip()

    if not phone or not message:
        raise HTTPException(status_code=422, detail="Missing phone or message")

    # 5. Build & invoke graph
    from app.graph.graph import build_graph
    from app.services.llm import ClaudeHaikuClient
    from app.services.sheets import GoogleSheetsClient
    from app.services.wablas import WablasClient

    llm = ClaudeHaikuClient(api_key=settings.anthropic_api_key)
    sheets = GoogleSheetsClient(
        credentials_json_path=settings.google_sheets_credentials_json_path,
        spreadsheet_id=tenant["google_sheet_id"],
    )
    wablas = WablasClient(
        base_url=settings.wablas_base_url,
        api_key=wa_api_key,
    )

    graph = build_graph(
        llm_client=llm,
        sheets_client=sheets,
        wablas_client=wablas,
    )

    thread_id = f"{tenant_id}:{phone}"
    initial_state = {
        "tenant_id": tenant_id,
        "wa_number": phone,
        "thread_id": thread_id,
        "message_text": message,
    }

    try:
        await graph.ainvoke(initial_state, config={"configurable": {"thread_id": thread_id}})
    except Exception as e:
        logger.error(
            "graph_invoke_failed",
            extra={"tenant_id": tenant_id, "error": str(e)},
            exc_info=True,
        )
        # Still return 200 to Wablas — we tried
        return {"status": "error", "detail": str(e)}

    return {"status": "ok"}
```

- [ ] **Step 5: Implement `app/main.py`**

```python
"""FastAPI application entry point."""
import logging
import os

import structlog
from fastapi import FastAPI

from app.config import get_settings
from app.health import router as health_router
from app.webhook import router as webhook_router


def configure_logging(level: str) -> None:
    """Configure structured JSON logging."""
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()
    configure_logging(settings.log_level)

    # Ensure runtime dirs exist
    for d in ["./data", "./secrets"]:
        os.makedirs(d, exist_ok=True)

    app = FastAPI(
        title="OrderCloser Lite",
        version="0.1.0",
        description="AI agent for WhatsApp order closing (Fase 1 MVP)",
    )

    app.include_router(health_router)
    app.include_router(webhook_router)

    return app


# Module-level app for uvicorn
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 6: Run webhook tests**

Run: `pytest tests/test_webhook.py -v`
Expected: 5 tests pass

---

## Task 13: LangGraph Checkpointer Setup

**Files:**
- Create: `app/db/checkpointer.py`
- Modify: `app/webhook.py` (use checkpointer)
- Test: `tests/test_checkpointer.py`

- [ ] **Step 1: Write failing test `tests/test_checkpointer.py`**

```python
"""Tests for LangGraph SqliteSaver checkpointer."""
import tempfile
from pathlib import Path

import pytest


def test_get_checkpointer_returns_saver(tmp_path):
    from app.db.checkpointer import get_checkpointer, reset_checkpointer_for_testing

    db_path = str(tmp_path / "cp.db")
    reset_checkpointer_for_testing()

    cp = get_checkpointer(db_path=db_path)
    assert cp is not None


def test_checkpointer_persists_across_instances(tmp_path):
    from app.db.checkpointer import (
        get_checkpointer,
        reset_checkpointer_for_testing,
    )

    db_path = str(tmp_path / "cp.db")

    reset_checkpointer_for_testing()
    cp1 = get_checkpointer(db_path=db_path)

    # Save a state
    config = {"configurable": {"thread_id": "test-1"}}
    # SqliteSaver interface: use put/get_config or just verify it's a Saver
    assert hasattr(cp1, "put")
    assert hasattr(cp1, "get_tuple")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_checkpointer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `app/db/checkpointer.py`**

```python
"""LangGraph SqliteSaver checkpointer singleton."""
import os
from typing import Optional

from langgraph.checkpoint.sqlite import SqliteSaver

_checkpointer: Optional[SqliteSaver] = None
_current_db_path: Optional[str] = None


def get_checkpointer(db_path: str | None = None) -> SqliteSaver:
    """Get the SqliteSaver checkpointer singleton.

    Args:
        db_path: Path to SQLite file. Defaults to settings.checkpointer_db_path.

    Returns SqliteSaver instance.
    """
    global _checkpointer, _current_db_path

    if db_path is None:
        from app.config import get_settings
        db_path = get_settings().checkpointer_db_path

    if _checkpointer is None or _current_db_path != db_path:
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        _checkpointer = SqliteSaver.from_conn_string(db_path)
        _current_db_path = db_path

    return _checkpointer


def reset_checkpointer_for_testing() -> None:
    """Test helper: clear the cached checkpointer."""
    global _checkpointer, _current_db_path
    _checkpointer = None
    _current_db_path = None
```

- [ ] **Step 4: Modify `app/webhook.py` to use the checkpointer**

Update the `graph.ainvoke` call in `app/webhook.py` to include the checkpointer:

Find:
```python
graph = build_graph(
    llm_client=llm,
    sheets_client=sheets,
    wablas_client=wablas,
)
```

Replace with:
```python
graph = build_graph(
    llm_client=llm,
    sheets_client=sheets,
    wablas_client=wablas,
)

# Attach SQLite checkpointer for multi-turn state persistence
from app.db.checkpointer import get_checkpointer
checkpointer = get_checkpointer()

# Recompile graph with checkpointer (LangGraph pattern)
from langgraph.graph import StateGraph
from app.graph.state import ChatState
graph_with_cp = graph  # graph from build_graph doesn't take checkpointer param
# For Fase 1 MVP, we'll use graph.get_state()/update_state() with the checkpointer directly
```

Actually, for proper LangGraph 1.x integration, we need to compile with checkpointer. Let me update `build_graph` to accept an optional checkpointer.

Update `app/graph/graph.py` `build_graph()` function signature:

Find:
```python
def build_graph(llm_client, sheets_client, wablas_client):
```

Replace with:
```python
def build_graph(llm_client, sheets_client, wablas_client, checkpointer=None):
```

And inside, find `return g.compile()` and replace with:
```python
    if checkpointer is not None:
        return g.compile(checkpointer=checkpointer)
    return g.compile()
```

- [ ] **Step 5: Update `app/webhook.py` to pass checkpointer**

Find:
```python
    from app.graph.graph import build_graph
```

Update to import `get_checkpointer` and pass it:

```python
graph = build_graph(
    llm_client=llm,
    sheets_client=sheets,
    wablas_client=wablas,
    checkpointer=get_checkpointer(),
)
```

- [ ] **Step 6: Run checkpointer test to verify it passes**

Run: `pytest tests/test_checkpointer.py -v`
Expected: 2 tests pass

- [ ] **Step 7: Re-run all webhook tests to confirm no regression**

Run: `pytest tests/test_webhook.py -v`
Expected: 5 tests still pass

---

## Task 14: CLI Scripts (Encryption & Tenant Seed)

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/gen_encryption_key.py`
- Create: `scripts/seed_tenant.py`

- [ ] **Step 1: Create `scripts/__init__.py`**

```python
"""CLI scripts."""
```

- [ ] **Step 2: Create `scripts/gen_encryption_key.py`**

```python
"""Generate a random 32-byte encryption key (base64-encoded).

Run: python scripts/gen_encryption_key.py
"""
import base64
import os
import sys


def main() -> int:
    key = base64.b64encode(os.urandom(32)).decode()
    print(f"ENCRYPTION_KEY={key}")
    print()
    print("Add this to your .env file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Create `scripts/seed_tenant.py`**

```python
"""Insert a tenant config row into the database.

Usage:
    python scripts/seed_tenant.py \\
        --tenant demo \\
        --sheet-id YOUR_GOOGLE_SHEET_ID \\
        --wa-number +6281234567890 \\
        --api-key YOUR_WABLAS_API_KEY
"""
import argparse
import base64
import sys

from app.config import get_settings
from app.db.engine import get_engine
from app.db.models import Base
from app.db.tenant_repo import insert_tenant
from app.services.crypto import CryptoError, encrypt_api_key


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed tenant config")
    parser.add_argument("--tenant", required=True, help="Tenant ID (e.g. demo)")
    parser.add_argument("--sheet-id", required=True, help="Google Sheet ID")
    parser.add_argument(
        "--wa-number", required=True, help="Owner WhatsApp number (e.g. +6281234567890)"
    )
    parser.add_argument("--api-key", required=True, help="Wablas API key (will be encrypted)")
    parser.add_argument(
        "--payment-provider", default="xendit", help="Payment provider (reserved for Fase 2)"
    )
    args = parser.parse_args()

    # Ensure tables exist
    engine = get_engine()
    Base.metadata.create_all(engine)

    # Encrypt API key
    settings = get_settings()
    try:
        encrypted = encrypt_api_key(args.api_key, settings.encryption_key)
    except CryptoError as e:
        print(f"ERROR: Encryption failed: {e}", file=sys.stderr)
        print("Check that ENCRYPTION_KEY in .env is a valid base64-encoded 32-byte key.", file=sys.stderr)
        return 1

    # Insert
    insert_tenant(
        tenant_id=args.tenant,
        wa_api_key_encrypted=encrypted,
        google_sheet_id=args.sheet_id,
        owner_wa_number=args.wa_number,
        payment_provider=args.payment_provider,
    )

    print(f"✓ Tenant '{args.tenant}' inserted successfully.")
    print(f"  Sheet: {args.sheet_id}")
    print(f"  Owner WA: {args.wa_number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Verify scripts run**

Run: `python scripts/gen_encryption_key.py`
Expected: Output like `ENCRYPTION_KEY=base64-encoded-string`

Run: `python scripts/seed_tenant.py --help`
Expected: Help text displays

---

## Task 15: Documentation (Setup Guide & README)

**Files:**
- Create: `docs/setup.md`

- [ ] **Step 1: Create `docs/setup.md`**

```markdown
# Setup Guide

Step-by-step guide to get OrderCloser Lite running on your local machine.

## Prerequisites

- Python 3.11+
- ngrok (free) — https://ngrok.com/download
- Wablas account (free trial) — https://wablas.com
- Anthropic API key — https://console.anthropic.com
- Google Cloud project with Sheets API enabled

## Step 1: Clone & Install

```bash
git clone <repo-url> ordercloser-lite
cd ordercloser-lite
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Step 2: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here
WABLAS_BASE_URL=https://api.wablas.com
GOOGLE_SHEETS_CREDENTIALS_JSON_PATH=./secrets/sheets-sa.json
```

## Step 3: Generate Encryption Key

```bash
python scripts/gen_encryption_key.py
```

Copy the output (e.g., `ENCRYPTION_KEY=base64string==`) into `.env`.

## Step 4: Setup Google Sheets Service Account

1. Go to https://console.cloud.google.com
2. Create a new project (or select existing)
3. Enable **Google Sheets API** for the project
4. Go to **IAM & Admin → Service Accounts** → Create service account
5. Skip optional permissions, click Done
6. Click the new service account → **Keys** tab → **Add Key** → **Create new key** → JSON
7. Save as `secrets/sheets-sa.json`
8. Open your Google Sheet → Share → paste the service account email → give Editor access
9. Make sure your sheet has tabs named `Katalog`, `FAQ` (Order_Log reserved for Fase 2)

## Step 5: Setup Wablas Webhook

1. Login to https://wablas.com
2. Get your device ID and API key from dashboard
3. Configure webhook URL (use ngrok — see Step 6):
   `https://<your-ngrok-url>/webhook/whatsapp/demo`
4. Note Wablas signature verification header name in their docs (typically `X-Wablas-Signature`)

## Step 6: Run with ngrok

In terminal 1:
```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

In terminal 2:
```bash
ngrok http 8000
```

Copy the `https://...ngrok-free.app` URL into your Wablas webhook config.

## Step 7: Seed Tenant

```bash
python scripts/seed_tenant.py \
    --tenant demo \
    --sheet-id <your-google-sheet-id-from-url> \
    --wa-number +6281234567890 \
    --api-key <your-wablas-api-key>
```

## Step 8: Test

Send a WhatsApp message to your Wablas-connected number. Check logs:

```bash
# Terminal 1 logs should show:
# - intent_classified
# - whatsapp_sent OR fallback_triggered
```

## Step 9: Run Tests

```bash
pytest -v
```

## Troubleshooting

**"Tenant not found"** — run `python scripts/seed_tenant.py` again.

**"Invalid signature"** — verify Wablas webhook secret matches what you seeded.

**"Encryption key invalid"** — regenerate with `python scripts/gen_encryption_key.py`.

**Sheets API error** — verify the service account email has Editor access to the sheet.
```

---

## Task 16: Final Verification & Cleanup

**Files:**
- All files (review)

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: All tests pass (target: ~30 tests across 9 files)

- [ ] **Step 2: Run linting**

Run: `ruff check app/ tests/ scripts/`
Expected: No errors

- [ ] **Step 3: Run type checking**

Run: `mypy app/`
Expected: No errors (or only minor warnings)

- [ ] **Step 4: Verify app starts**

Run: `uvicorn app.main:app --port 8000`
Then: `curl http://localhost:8000/healthz`
Expected: `{"status":"ok"}`

Then: `curl http://localhost:8000/readyz`
Expected: JSON with checks status

- [ ] **Step 5: Verify all imports work**

Run: `python -c "from app.main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit (if using git)**

```bash
git add .
git commit -m "feat: OrderCloser Lite Fase 1 MVP — webhook, LangGraph, fallback, Wablas"
```

---

## Open Items Resolved During Implementation

During Task 13, this plan needs additional verification:
1. **Wablas exact signature header name** — confirm from Wablas docs at implementation time. The plan uses `X-Wablas-Signature` as default; update `app/webhook.py` if different.
2. **LangGraph SqliteSaver API** — verify `from_conn_string()` vs `SqliteSaver(connection)`. The plan assumes LangGraph 1.x API as documented at https://langchain-ai.github.io/langgraph/.
3. **Sheets service account email sharing** — user must do this step manually per `docs/setup.md` Step 4.

---

## Summary

After completing all 16 tasks, you will have:
- Working WhatsApp webhook with HMAC signature verification
- LangGraph state graph with 5 nodes (classify, lookup, compose, send, fallback)
- SQLite persistence for tenant config, chat logs, and conversation state
- Encrypted API key storage (AES-GCM)
- Multi-turn stateful conversations via SQLite checkpointer
- ~30 unit tests covering all logic
- Full setup documentation

**Next steps after Fase 1 MVP validation with 5-10 pilot clients:**
- Fase 2: Payment link integration (Xendit) — add `handle_order` node
- Fase 3: Auto-onboarding multi-tenant — auto-generate tenant rows + duplicate spreadsheets
