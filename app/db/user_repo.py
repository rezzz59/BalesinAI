"""User account + session repo (authentication)."""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from app.db.engine import get_session
from app.db.models import SessionToken, User

logger = logging.getLogger(__name__)

SESSION_TTL_HOURS = 24 * 30  # 30 days


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    ).hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    return hash_password(password, salt) == expected_hash


def create_user(email: str, password: str, full_name: str = "", tenant_id: str = "") -> User:
    """Create a user row. Raises ValueError on invalid email/password or duplicate."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("Email tidak valid.")
    if len(password or "") < 6:
        raise ValueError("Kata sandi minimal 6 karakter.")
    salt = secrets.token_hex(16)
    with get_session() as session:
        if session.query(User).filter_by(email=email).first():
            raise ValueError("Email sudah terdaftar. Silakan masuk.")
        user = User(
            email=email,
            full_name=(full_name or "").strip(),
            password_hash=hash_password(password, salt),
            password_salt=salt,
            tenant_id=tenant_id or "",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def get_user_by_email(email: str) -> User | None:
    email = (email or "").strip().lower()
    with get_session() as session:
        return session.query(User).filter_by(email=email).first()


def get_user_by_id(user_id: int) -> User | None:
    with get_session() as session:
        return session.get(User, user_id)


def validate_login(email: str, password: str) -> User | None:
    """Return the User if credentials are correct, else None."""
    user = get_user_by_email(email)
    if user is None:
        return None
    if not verify_password(password, user.password_salt, user.password_hash):
        return None
    return user


def update_user_tenant(user_id: int, tenant_id: str) -> None:
    with get_session() as session:
        user = session.get(User, user_id)
        if user:
            user.tenant_id = tenant_id or ""
            session.commit()


def create_session(user_id: int) -> SessionToken:
    token = secrets.token_urlsafe(32)
    with get_session() as session:
        row = SessionToken(
            token=token,
            user_id=user_id,
            expires_at=_utcnow() + timedelta(hours=SESSION_TTL_HOURS),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def get_session_user(token: str) -> User | None:
    """Resolve a session token to a User (validating expiry)."""
    if not token:
        return None
    with get_session() as session:
        row = session.get(SessionToken, token)
        if row is None:
            return None
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < _utcnow():
            session.delete(row)
            session.commit()
            return None
        user = session.get(User, row.user_id)
        return user


def delete_session(token: str) -> None:
    if not token:
        return
    with get_session() as session:
        row = session.get(SessionToken, token)
        if row:
            session.delete(row)
            session.commit()