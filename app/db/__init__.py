"""Database layer — SQLAlchemy models and repos."""
import logging

from sqlalchemy import text

from app.db.embeddings_repo import EmbeddingCacheRepo, get_embedding_repo, CachedEmbedding  # noqa: F401, F403
from app.db.engine import get_engine
from app.db.models import Base

logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    """Lightweight idempotent schema migrations for existing DBs.

    SQLAlchemy's create_all() adds missing tables but never adds a column to an
    existing table, so columns introduced after first deploy need a manual
    ALTER TABLE guarded by a PRAGMA check.
    """
    engine = get_engine()
    with engine.connect() as conn:
        cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(tenant_config)")).fetchall()
        }
        if "data_source" not in cols:
            conn.execute(text(
                "ALTER TABLE tenant_config ADD COLUMN data_source VARCHAR NOT NULL DEFAULT 'sheet'"
            ))
            conn.commit()
            logger.info("migration: added tenant_config.data_source")
        if "tier" not in cols:
            conn.execute(text(
                "ALTER TABLE tenant_config ADD COLUMN tier VARCHAR NOT NULL DEFAULT 'basic'"
            ))
            conn.commit()
            logger.info("migration: added tenant_config.tier")
        if "device_status" not in cols:
            conn.execute(text(
                "ALTER TABLE tenant_config ADD COLUMN device_status VARCHAR NOT NULL DEFAULT 'fresh'"
            ))
            conn.commit()
            logger.info("migration: added tenant_config.device_status")
        if "gateway_plan" not in cols:
            conn.execute(text(
                "ALTER TABLE tenant_config ADD COLUMN gateway_plan VARCHAR NOT NULL DEFAULT 'lite'"
            ))
            conn.commit()
            logger.info("migration: added tenant_config.gateway_plan")


def init_db() -> None:
    """Create DB tables based on ORM metadata. Idempotent — safe to call repeatedly."""
    Base.metadata.create_all(bind=get_engine())
    _run_migrations()


__all__ = ["init_db", "get_engine", "Base"]