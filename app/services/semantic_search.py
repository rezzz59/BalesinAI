"""Semantic search over cached FAQ, policy, and product catalog entries.

Queries are encoded into vectors using EmbeddingService and matched against
pre-computed embeddings stored in the embedding cache. Returns contextually
relevant FAQ items or catalog products that can be referenced in replies.
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List, Tuple, Union

import numpy as np

from app.db.embeddings_repo import CachedEmbedding, EmbeddingCacheRepo, get_embedding_repo
from app.services.embeddings import EmbeddingService, EmbeddingServiceError

logger = logging.getLogger(__name__)

# Valid sources for semantic search
VALID_SOURCES = ("faq", "policy", "catalog")


class SemanticSearchError(Exception):
    """Exception raised when semantic search fails."""

    pass


class SemanticSearchClient:
    """High-level client for semantic lookups across FAQ, policy, and catalog items.

    Uses an EmbeddingService to encode query text and then searches the local
    embedding cache for the nearest neighbors. The results are enriched with original
    text metadata to be used downstream (e.g., in composing a reply).
    """

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        repo: Optional[EmbeddingCacheRepo] = None,
    ):
        self._embedding_service = embedding_service or EmbeddingService()
        self._repo = repo or get_embedding_repo()

    @classmethod
    def from_defaults(cls) -> "SemanticSearchClient":
        """Convenience constructor using default services."""
        return cls()

    def search(
        self,
        query: str,
        tenant_id: str,
        source: str,
        limit: int = 3,
        min_similarity: float = 0.4,
    ) -> List[Dict[str, Any]]:
        """Perform semantic search on a single source.

        Args:
            query: User question or text to match.
            tenant_id: Isolation key for multi-tenant data.
            source: One of 'faq', 'policy', 'catalog'.
            limit: Maximum number of matches to return.
            min_similarity: Minimum cosine similarity threshold; lower values ignored.

        Returns:
            List of hit dictionaries with keys: 'id', 'row_id', 'text', 'similarity'.

        Raises:
            SemanticSearchError: If query encoding or DB access fails.
        """
        if source not in VALID_SOURCES:
            raise SemanticSearchError(f"invalid source {source!r}; one of {VALID_SOURCES}")

        try:
            # Encode query to vector
            query_vector = self._embedding_service.encode(query)  # shape (384,)
        except EmbeddingServiceError as e:
            raise SemanticSearchError(f"failed to encode query: {e}") from None

        try:
            # Find nearest cached embeddings
            hits: List[Tuple[CachedEmbedding, float]] = self._repo.search_nearest(
                tenant_id, source, query_vector, limit=limit
            )
        except Exception as e:
            raise SemanticSearchError(f"DB search failed: {e}") from None

        # Filter by threshold and build result list
        results: List[Dict[str, Any]] = []
        for emb, sim in hits:
            if sim < min_similarity:
                continue  # skip borderline noise
            results.append({
                "id": emb.id,
                "row_id": emb.row_id,
                "source": emb.source,
                "text": emb.text.strip(),
                "similarity": round(float(sim), 4),
                "updated_at": emb.updated_at.isoformat() if emb.updated_at else None,
            })

        logger.debug(f"search returned {len(results)} hits for tenant={tenant_id} source={source} q={query[:60]}...")
        return results

    def batch_search(
        self,
        queries: List[str],
        tenant_id: str,
        sources: Optional[List[str]] = None,
        limit: int = 3,
        min_similarity: float = 0.4,
    ) -> Dict[str, Any]:
        """Execute multiple semantic searches across one or more sources.

        Args:
            queries: List of user questions/texts.
            tenant_id: Tenant isolation key.
            sources: List of sources to search (all of VALID_SOURCES if omitted).
            limit: Max matches per query.
            min_similarity: Cosine similarity cutoff.

        Returns:
            A dict keyed by query string containing a list of hits for each query.
        """
        if sources is None:
            sources = list(VALID_SOURCES)

        results: Dict[str, Any] = {"queries": {}, "summary": {"total_hits": 0}}

        for query in queries:
            all_hits: List[Dict[str, Any]] = []
            for src in sources:
                try:
                    hits = self.search(query, tenant_id, src, limit=limit, min_similarity=min_similarity)
                    all_hits.extend(hits)
                except SemanticSearchError as e:
                    logger.warning(f"search error for query '{query[:20]}' source={src}: {e}")
            all_hits.sort(key=lambda x: x["similarity"], reverse=True)
            results["queries"][query] = all_hits
            results["summary"]["total_hits"] += len(all_hits)

        return results


# Helper functions for convenience (may be used by nodes directly)
def find_faq_matches(
    query: str,
    tenant_id: str,
    repo: Optional[EmbeddingCacheRepo] = None,
    embedding_service: Optional[EmbeddingService] = None,
    limit: int = 3,
    min_similarity: float = 0.4,
) -> List[Dict[str, Any]]:
    """Shortcut to search only the FAQ source."""
    client = SemanticSearchClient(embedding_service, repo)
    return client.search(query, tenant_id, source="faq", limit=limit, min_similarity=min_similarity)


def find_catalog_matches(
    sku: str,
    tenant_id: str,
    repo: Optional[EmbeddingCacheRepo] = None,
    embedding_service: Optional[EmbeddingService] = None,
    limit: int = 3,
    min_similarity: float = 0.4,
) -> List[Dict[str, Any]]:
    """Search the catalog source using a SKU/description string."""
    client = SemanticSearchClient(embedding_service, repo)
    return client.search(sku, tenant_id, source="catalog", limit=limit, min_similarity=min_similarity)


def find_policy_matches(
    query: str,
    tenant_id: str,
    repo: Optional[EmbeddingCacheRepo] = None,
    embedding_service: Optional[EmbeddingService] = None,
    limit: int = 3,
    min_similarity: float = 0.4,
) -> List[Dict[str, Any]]:
    """Search the policy source."""
    client = SemanticSearchClient(embedding_service, repo)
    return client.search(query, tenant_id, source="policy", limit=limit, min_similarity=min_similarity)
