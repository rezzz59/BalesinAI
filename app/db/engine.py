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


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the cached engine (lazy-initialized). Tests can clear via cache_clear()."""
    global _engine
    if _engine is None:
        _engine = _build_default_engine()
    return _engine


def reset_engine_for_testing(engine: Engine) -> None:
    """Test helper: replace the cached engine. Call get_engine.cache_clear() afterwards."""
    global _engine
    _engine = engine
    get_engine.cache_clear()


def get_session_factory():
    engine = get_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Session:
    """Context-manager compatible session."""
    SessionLocal = get_session_factory()
    return SessionLocal()