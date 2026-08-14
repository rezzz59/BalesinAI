"""Tests for user auth: register, login, logout, session expiry, re-login, /me."""
import os
import tempfile

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine

import app.db.engine as engine_mod
from app.db.models import Base
from app.db import user_repo


@pytest.fixture(autouse=True)
def fresh_db():
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="auth_")
    os.close(fd)
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    engine_mod.reset_engine_for_testing(eng)
    yield
    eng.dispose()
    engine_mod.reset_engine_for_testing(None)
    try:
        os.unlink(db_path)
    except OSError:
        pass


def test_register_creates_user():
    user = user_repo.create_user("test1@balesin.ai", "password123", "Test User 1")
    assert user.id > 0
    assert user.email == "test1@balesin.ai"
    assert user.full_name == "Test User 1"
    assert user.password_hash != "password123"
    assert user.password_salt != ""


def test_register_duplicate_email_raises():
    user_repo.create_user("dup@balesin.ai", "password123")
    with pytest.raises(ValueError, match="sudah terdaftar"):
        user_repo.create_user("dup@balesin.ai", "password456")


def test_register_short_password_raises():
    with pytest.raises(ValueError, match="minimal 6"):
        user_repo.create_user("short@balesin.ai", "12345")


def test_register_invalid_email_raises():
    with pytest.raises(ValueError, match="Email tidak valid"):
        user_repo.create_user("not-an-email", "password123")


def test_validate_login_success():
    user_repo.create_user("login@balesin.ai", "password123", "Login User")
    user = user_repo.validate_login("login@balesin.ai", "password123")
    assert user is not None
    assert user.email == "login@balesin.ai"


def test_validate_login_wrong_password():
    user_repo.create_user("wrong@balesin.ai", "password123")
    assert user_repo.validate_login("wrong@balesin.ai", "wrong") is None


def test_validate_login_unknown_email():
    assert user_repo.validate_login("nobody@balesin.ai", "password123") is None


def test_validate_login_email_case_insensitive():
    user_repo.create_user("Case@balesin.ai", "password123")
    assert user_repo.validate_login("case@balesin.ai", "password123") is not None


def test_create_session_returns_valid_token():
    user = user_repo.create_user("sess@balesin.ai", "password123")
    session = user_repo.create_session(user.id)
    assert session.token != ""
    assert len(session.token) > 20
    resolved = user_repo.get_session_user(session.token)
    assert resolved is not None
    assert resolved.id == user.id


def test_get_session_user_invalid_token():
    assert user_repo.get_session_user("nonexistent-token") is None
    assert user_repo.get_session_user("") is None


def test_delete_session():
    user = user_repo.create_user("del@balesin.ai", "password123")
    session = user_repo.create_session(user.id)
    assert user_repo.get_session_user(session.token) is not None
    user_repo.delete_session(session.token)
    assert user_repo.get_session_user(session.token) is None


def test_delete_session_invalid_token_noop():
    user_repo.delete_session("nonexistent-token")
    user_repo.delete_session("")


def test_expired_session_returns_none_and_is_deleted():
    from app.db.models import SessionToken

    user = user_repo.create_user("exp@balesin.ai", "password123")
    session = user_repo.create_session(user.id)
    from app.db.engine import get_session

    with get_session() as sess:
        row = sess.get(SessionToken, session.token)
        row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        sess.commit()

    assert user_repo.get_session_user(session.token) is None
    with get_session() as sess:
        assert sess.get(SessionToken, session.token) is None


def test_relogin_after_logout():
    user = user_repo.create_user("relog@balesin.ai", "password123")
    s1 = user_repo.create_session(user.id)
    assert user_repo.get_session_user(s1.token) is not None
    user_repo.delete_session(s1.token)
    assert user_repo.get_session_user(s1.token) is None
    s2 = user_repo.create_session(user.id)
    assert user_repo.get_session_user(s2.token) is not None
    assert s2.token != s1.token


def test_multiple_sessions_same_user():
    user = user_repo.create_user("multi@balesin.ai", "password123")
    s1 = user_repo.create_session(user.id)
    s2 = user_repo.create_session(user.id)
    assert s1.token != s2.token
    assert user_repo.get_session_user(s1.token) is not None
    assert user_repo.get_session_user(s2.token) is not None


def test_update_user_tenant():
    user = user_repo.create_user("tenant@balesin.ai", "password123")
    assert user.tenant_id == ""
    user_repo.update_user_tenant(user.id, "my-tenant-123")
    updated = user_repo.get_user_by_id(user.id)
    assert updated.tenant_id == "my-tenant-123"


def test_hash_and_verify_password():
    h = user_repo.hash_password("mypw", "salt123")
    assert h != "mypw"
    assert user_repo.verify_password("mypw", "salt123", h) is True
    assert user_repo.verify_password("wrong", "salt123", h) is False
