"""Database layer — SQLAlchemy models and repos."""
from app.db.embeddings_repo import EmbeddingCacheRepo, get_embedding_repo, CachedEmbedding  # noqa: F401, F403
from app.db.engine import get_engine
from app.db.models import Base


def init_db() -> None:
    """Create DB tables based on ORM metadata. Idempotent — safe to call repeatedly."""
    Base.metadata.create_all(bind=get_engine())


__all__ = ["init_db", "get_engine", "Base"]
