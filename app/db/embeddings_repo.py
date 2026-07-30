"""Embedding cache repository for caching and retrieving semantic vectors."""

import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Tuple

import numpy as np

from app.db.engine import get_session_factory
from app.db.models import EmbeddingCache


EMBED_DIM = 384


def _to_blob(vec: np.ndarray) -> bytes:
    """Convert a L2-normalized 384-dim float32 vector to a BLOB."""
    if vec.shape != (EMBED_DIM,) or vec.dtype != np.float32:
        raise ValueError(f"Expected ({EMBED_DIM},) float32 vector, got shape={vec.shape} dtype={vec.dtype}")
    return vec.tobytes()


def _from_blob(blob: bytes) -> np.ndarray:
    """Convert a BLOB back to a 384-dim float32 numpy array."""
    arr = np.frombuffer(blob, dtype=np.float32)
    if arr.shape != (EMBED_DIM,):
        raise ValueError(f"Invalid embedding length (expected {EMBED_DIM} floats)")
    return arr


def compute_content_hash(text: str) -> str:
    """Compute SHA-256 hex hash of normalized text for deduplication."""
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class CachedEmbedding:
    """Immutable DTO representing a cached embedding record."""

    __slots__ = ("id", "tenant_id", "source", "row_id", "content_hash", "embedding", "text", "updated_at")

    def __init__(
        self,
        id: int,
        tenant_id: str,
        source: str,
        row_id: str,
        content_hash: str,
        embedding: np.ndarray,
        text: str,
        updated_at: datetime,
    ):
        self.id = id
        self.tenant_id = tenant_id
        self.source = source
        self.row_id = row_id
        self.content_hash = content_hash
        self.embedding = embedding
        self.text = text
        self.updated_at = updated_at

    def __repr__(self) -> str:
        return f"<CachedEmbedding id={self.id} source={self.source} row_id={self.row_id}>"


class EmbeddingCacheRepo:
    """SQLite-backed repository for cached embeddings.

    Each row is a unique (tenant_id, source, row_id) tuple. If the same
    row_id is re-saved with a different content_hash, the row is updated.
    If saved with the same content_hash, the call is a no-op.
    """

    _VALID_SOURCES = ("faq", "policy", "catalog")

    def __init__(self, session_factory):
        self._factory = session_factory

    def save(self, tenant_id: str, source: str, row_id: str, text: str, embedding: np.ndarray) -> None:
        """Upsert a row. Updates content_hash/text/embedding if the row already exists."""
        if source not in self._VALID_SOURCES:
            raise ValueError(f"source must be one of {self._VALID_SOURCES}, got {source!r}")
        if embedding.shape != (EMBED_DIM,) or embedding.dtype != np.float32:
            raise ValueError("embedding must be a 384-dim float32 vector")

        content_hash = compute_content_hash(text)
        blob = _to_blob(embedding)

        with self._factory() as session:
            try:
                existing = (
                    session.query(EmbeddingCache)
                    .filter_by(tenant_id=tenant_id, source=source, row_id=row_id)
                    .first()
                )
                if existing is None:
                    session.add(EmbeddingCache(
                        tenant_id=tenant_id,
                        source=source,
                        row_id=row_id,
                        content_hash=content_hash,
                        embedding=blob,
                        text=text,
                        updated_at=datetime.now(timezone.utc),
                    ))
                else:
                    existing.content_hash = content_hash
                    existing.embedding = blob
                    existing.text = text
                    existing.updated_at = datetime.now(timezone.utc)
                session.commit()
            except Exception:
                session.rollback()
                raise

    def find_by_id(self, tenant_id: str, source: str, row_id: str) -> Optional[CachedEmbedding]:
        """Fetch the cached embedding for a (tenant, source, row_id). Returns None if missing."""
        with self._factory() as session:
            row = (
                session.query(EmbeddingCache)
                .filter_by(tenant_id=tenant_id, source=source, row_id=row_id)
                .first()
            )
            return self._to_dto(row)

    def find_by_hash(self, tenant_id: str, source: str, content_hash: str) -> Optional[CachedEmbedding]:
        """Find a cached entry that matches a given content hash."""
        with self._factory() as session:
            row = (
                session.query(EmbeddingCache)
                .filter_by(tenant_id=tenant_id, source=source, content_hash=content_hash)
                .first()
            )
            return self._to_dto(row)

    def list_by_source(self, tenant_id: str, source: str) -> List[CachedEmbedding]:
        """Return all cached entries for a given (tenant, source)."""
        with self._factory() as session:
            rows = (
                session.query(EmbeddingCache)
                .filter_by(tenant_id=tenant_id, source=source)
                .all()
            )
            return [self._to_dto(r) for r in rows if r is not None]

    def search_nearest(
        self,
        tenant_id: str,
        source: str,
        query_embedding: np.ndarray,
        limit: int = 5,
    ) -> List[Tuple[CachedEmbedding, float]]:
        """Return up to `limit` cached entries ranked by cosine similarity.

        Cosine similarity between two unit-norm vectors equals their dot product.
        Returns list of (CachedEmbedding, similarity) sorted desc.
        """
        if query_embedding.shape != (EMBED_DIM,) or query_embedding.dtype != np.float32:
            raise ValueError("query_embedding must be a 384-dim float32 vector")

        with self._factory() as session:
            rows = (
                session.query(EmbeddingCache)
                .filter_by(tenant_id=tenant_id, source=source)
                .all()
            )

            results: List[Tuple[CachedEmbedding, float]] = []
            for row in rows:
                vec = _from_blob(row.embedding)
                sim = float(np.dot(query_embedding, vec))
                results.append((self._to_dto(row), sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def invalidate_by_row(self, tenant_id: str, source: str, row_id: str) -> None:
        """Remove the cached entry for a specific (tenant, source, row_id)."""
        with self._factory() as session:
            try:
                (
                    session.query(EmbeddingCache)
                    .filter_by(tenant_id=tenant_id, source=source, row_id=row_id)
                    .delete(synchronize_session=False)
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

    def invalidate_by_hash(self, tenant_id: str, source: str, content_hash: str) -> None:
        """Remove all cached entries matching a given content hash."""
        with self._factory() as session:
            try:
                (
                    session.query(EmbeddingCache)
                    .filter_by(tenant_id=tenant_id, source=source, content_hash=content_hash)
                    .delete(synchronize_session=False)
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

    def _to_dto(self, row: EmbeddingCache | None) -> Optional[CachedEmbedding]:
        if row is None:
            return None
        return CachedEmbedding(
            id=row.id,
            tenant_id=row.tenant_id,
            source=row.source,
            row_id=row.row_id,
            content_hash=row.content_hash,
            embedding=_from_blob(row.embedding),
            text=row.text,
            updated_at=row.updated_at,
        )


def get_embedding_repo() -> EmbeddingCacheRepo:
    """Return a repository bound to the default application engine."""
    return EmbeddingCacheRepo(get_session_factory())
