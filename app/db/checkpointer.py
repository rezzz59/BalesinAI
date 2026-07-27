"""SQLite-backed graph checkpoint saver for LangGraph.

Implements a minimal Saver interface that persists checkpoints in the existing DB engine.
The state is pickled for simplicity (only used internally; not exposed).
"""
import json
import logging
import pickle  # nosec - internal only
from typing import Any, Optional

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.engine import get_engine, get_session_factory
from app.db.models import Checkpoint

logger = logging.getLogger(__name__)


def _serialize_config(config: dict[str, Any]) -> str:
    """Convert config dict to a stable string key for DB lookup."""
    return json.dumps(config, sort_keys=True, default=str)


class SqliteCheckpointer:
    """SQLite-backed implementation of LangGraph's Saver interface.

    Methods:
        save(config, fnode_id, state): upsert checkpoint for (config, fnode_id).
        get(config, fnode_id): retrieve checkpoint state for (config, fnode_id), or None.

    Args:
        engine: Optional SQLAlchemy engine. If not provided, the default engine from
            `app.db.engine.get_engine()` is used.
    """

    def __init__(self, engine: Optional[Engine] = None):
        if engine is None:
            engine = get_engine()
        self._engine = engine
        self._factory = sessionmaker(bind=engine, expire_on_commit=False)

    def save(self, config: dict[str, Any], fnode_id: str, state: Any) -> None:
        """Persist a checkpoint.

        Args:
            config: langgraph config dict (e.g. {"configurable": {"thread_id": "..."}})
            fnode_id: identifier of the finishing node for this step
            state: picklable state object to persist
        """
        config_key = _serialize_config(config)
        pickled = pickle.dumps(state)
        session: Session = self._factory()
        try:
            existing = session.get(Checkpoint, (config_key, fnode_id))
            if existing:
                existing.state = pickled
            else:
                session.add(
                    Checkpoint(config_key=config_key, fnode_id=fnode_id, state=pickled)
                )
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("checkpoint_save_failed", extra={"error": str(e)})
            raise
        finally:
            session.close()

    def get(self, config: dict[str, Any], fnode_id: str) -> Any | None:
        """Retrieve a checkpoint state, or None if not present."""
        config_key = _serialize_config(config)
        session: Session = self._factory()
        try:
            row = session.get(Checkpoint, (config_key, fnode_id))
            if row is None:
                return None
            return pickle.loads(row.state)  # nosec - internal only
        finally:
            session.close()


__all__ = ["SqliteCheckpointer"]