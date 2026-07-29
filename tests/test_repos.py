"""Tests for tenant_repo and chat_log_repo."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import pytest

import app.db.engine as engine_mod
from app.db.models import Base


@pytest.fixture(autouse=True)
def reset_db():
    """Reset engine and create fresh in-memory DB per test."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    engine_mod.reset_engine_for_testing(eng)
    yield
    eng.dispose()


def test_tenant_repo_insert_and_get():
    from app.db.tenant_repo import insert_tenant, get_tenant
    from app.config import get_settings
    from app.services.crypto import encrypt_api_key

    settings = get_settings()
    encrypted = encrypt_api_key("fonnte-token-xyz", settings.encryption_key)

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
    assert (
        decrypt_api_key(tenant["wa_api_key_encrypted"], settings.encryption_key)  # noqa: F821
        == "fonnte-token-xyz"
    )


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


# Local alias to satisfy the assertion above (decrypt_api_key is imported lazily).
def decrypt_api_key(encrypted: bytes, key: str) -> str:
    from app.services.crypto import decrypt_api_key as _decrypt

    return _decrypt(encrypted, key)