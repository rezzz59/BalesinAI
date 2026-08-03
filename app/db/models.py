"""SQLAlchemy ORM models."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, Integer, LargeBinary, String, Text
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
    user_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("idx_thread", "thread_id"),
        Index("idx_tenant_time", "tenant_id", "timestamp"),
    )


class Checkpoint(Base):
    """Stores graph checkpoints for resume/persistence.

    Keyed by (config, fnode_id) similar to LangGraph's saver interface.
    """
    __tablename__ = "checkpoint"

    config_key: Mapped[str] = mapped_column(String, primary_key=True)  # serialized JSON of config
    fnode_id: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[bytes] = mapped_column()  # Pickled state for simplicity
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (Index("idx_config_fnode", "config_key", "fnode_id"),)


class EmbeddingCache(Base):
    """Cached embedding for FAQ, product catalog, or policy rows. Enables fast
    semantic lookups without re-computing embeddings on every query.

    Each row stores: the source type + unique identifier, content hash, and a 384-dim
    float32 vector stored as BLOB. All rows are L2-normalized, so cosine similarity
    equals dot product.
    """

    __tablename__ = "embedding_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)  # 'faq'|'policy'|'catalog'
    row_id: Mapped[str] = mapped_column(String, nullable=False, index=True)  # unique key within source
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 of text
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # 384 x float32 = 1536 bytes
    text: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    __table_args__ = (
        Index("idx_embedding_lookup", "tenant_id", "source", "content_hash"),
        Index("idx_embedding_source", "tenant_id", "source", "row_id"),
    )
