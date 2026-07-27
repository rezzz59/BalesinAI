"""Tests for app.db.engine and app.db.models."""
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import pytest

from app.db.engine import get_engine, get_session_factory
from app.db.models import Base, ChatLog, TenantConfig


@pytest.fixture
def in_memory_engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_base_metadata_creates_tables(in_memory_engine):
    inspector = inspect(in_memory_engine)
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