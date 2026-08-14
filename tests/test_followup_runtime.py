"""Tests for anti-ghosting follow-up runtime loop and logic."""
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.db.models import ChatLog, TenantConfig
from app.services.followup import _process_followups, _trigger_followup


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import app.db.engine as engine_mod
    from sqlalchemy import create_engine
    from app.db.models import Base

    fd, db_path = tmp_path / "followup_test.db", None
    db_path = str(fd)
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    engine_mod.reset_engine_for_testing(eng)
    from app.db.engine import get_session
    yield get_session
    eng.dispose()
    engine_mod.reset_engine_for_testing(None)


@pytest.mark.asyncio
async def test_process_followups_triggers_on_stale_abandoned_chat(fresh_db, monkeypatch):
    import json
    
    tenant_id = "test-tenant"
    thread_id = "t-123"
    
    with fresh_db() as session:
        # Create tenant with 15 mins delay
        onboarding_data = json.dumps({"followup_delay_minutes": 15, "followup_prompt": "Are you still interested?"})
        t = TenantConfig(
            tenant_id=tenant_id,
            wa_api_key_encrypted=b"dummy",
            google_sheet_id="sheet-id",
            owner_wa_number="6281",
            onboarding_data=onboarding_data
        )
        session.add(t)
        
        # Create an abandoned chat from 20 mins ago (last status = replied, intent = faq)
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        c = ChatLog(
            thread_id=thread_id,
            tenant_id=tenant_id,
            wa_number="628999",
            intent="faq",
            status="replied",
            timestamp=stale_time
        )
        session.add(c)
        session.commit()
        
    triggered_logs = []
    async def mock_trigger(log, tc):
        triggered_logs.append(log.thread_id)
        
    monkeypatch.setattr("app.services.followup._trigger_followup", mock_trigger)
    monkeypatch.setattr("app.services.crypto.decrypt_api_key", lambda enc, key: "decrypted")
    
    await _process_followups()
    
    assert len(triggered_logs) == 1
    assert triggered_logs[0] == thread_id


@pytest.mark.asyncio
async def test_process_followups_ignores_fresh_chats(fresh_db, monkeypatch):
    import json
    
    with fresh_db() as session:
        t = TenantConfig(
            tenant_id="t-1",
            wa_api_key_encrypted=b"dummy",
            google_sheet_id="sheet-id",
            owner_wa_number="6281",
            onboarding_data=json.dumps({"followup_delay_minutes": 15, "followup_prompt": "Hi"})
        )
        session.add(t)
        
        # Chat from 5 mins ago (less than 15 mins delay)
        fresh_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        c = ChatLog(
            thread_id="t-123",
            tenant_id="t-1",
            wa_number="628999",
            intent="faq",
            status="replied",
            timestamp=fresh_time
        )
        session.add(c)
        session.commit()
        
    triggered = []
    monkeypatch.setattr("app.services.followup._trigger_followup", lambda l, tc: triggered.append(l))
    monkeypatch.setattr("app.services.crypto.decrypt_api_key", lambda enc, key: "decrypted")
    
    await _process_followups()
    assert len(triggered) == 0


@pytest.mark.asyncio
async def test_process_followups_ignores_already_followed_up(fresh_db, monkeypatch):
    import json
    
    with fresh_db() as session:
        t = TenantConfig(
            tenant_id="t-1",
            wa_api_key_encrypted=b"dummy",
            google_sheet_id="sheet-id",
            owner_wa_number="6281",
            onboarding_data=json.dumps({"followup_delay_minutes": 15, "followup_prompt": "Hi"})
        )
        session.add(t)
        
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        c = ChatLog(
            thread_id="t-123",
            tenant_id="t-1",
            wa_number="628999",
            intent="auto_followup", # Already followed up!
            status="replied",
            timestamp=stale_time
        )
        session.add(c)
        session.commit()
        
    triggered = []
    monkeypatch.setattr("app.services.followup._trigger_followup", lambda l, tc: triggered.append(l))
    monkeypatch.setattr("app.services.crypto.decrypt_api_key", lambda enc, key: "decrypted")
    
    await _process_followups()
    assert len(triggered) == 0


@pytest.mark.asyncio
async def test_process_followups_ignores_ordered_chats(fresh_db, monkeypatch):
    import json
    
    with fresh_db() as session:
        t = TenantConfig(
            tenant_id="t-1",
            wa_api_key_encrypted=b"dummy",
            google_sheet_id="sheet-id",
            owner_wa_number="6281",
            onboarding_data=json.dumps({"followup_delay_minutes": 15, "followup_prompt": "Hi"})
        )
        session.add(t)
        
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        c = ChatLog(
            thread_id="t-123",
            tenant_id="t-1",
            wa_number="628999",
            intent="confirm_order",
            status="ordered", # Order complete, no ghosting to follow up
            timestamp=stale_time
        )
        session.add(c)
        session.commit()
        
    triggered = []
    monkeypatch.setattr("app.services.followup._trigger_followup", lambda l, tc: triggered.append(l))
    monkeypatch.setattr("app.services.crypto.decrypt_api_key", lambda enc, key: "decrypted")
    
    await _process_followups()
    assert len(triggered) == 0


@pytest.mark.asyncio
async def test_trigger_followup_builds_synthetic_state_and_invokes_graph():
    from datetime import datetime, timezone
    
    log = ChatLog(
        thread_id="t-123",
        tenant_id="t-1",
        wa_number="628999",
        intent="faq",
        status="replied",
        timestamp=datetime.now(timezone.utc)
    )
    tc = {"prompt": "Are you still there?", "token": "dummy"}
    
    mock_graph = MagicMock()
    
    with patch("app.services.followup.get_compiled_graph", return_value=mock_graph), \
         patch("app.services.followup.get_safe_llm_client"), \
         patch("app.services.bot_tester._build_sheets_client"), \
         patch("app.services.followup.FonnteGateway"):
             
        await _trigger_followup(log, tc)
        
    assert mock_graph.invoke.call_count == 1
    state = mock_graph.invoke.call_args[0][0]
    
    assert state["tenant_id"] == "t-1"
    assert state["thread_id"] == "t-123"
    assert state["wa_number"] == "628999"
    assert state["intent"] == "auto_followup"
    assert "Are you still there?" in state["message_text"]
    assert state["message_text"].startswith("__SYSTEM_AUTO_FOLLOWUP__")
