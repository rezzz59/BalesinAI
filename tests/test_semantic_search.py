"""Tests for SemanticSearchClient and convenience helpers.

Uses an in-memory SQLite engine and a real EmbeddingService to exercise the full
stack: encode → cache lookup → similarity ranking → filtering.
"""

from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock, patch

from app.db.embeddings_repo import EmbeddingCacheRepo, EMBED_DIM
from app.db.models import Base
from app.services.embeddings import EmbeddingService, EmbeddingServiceError
from app.services.semantic_search import (
    SemanticSearchClient,
    SemanticSearchError,
    find_faq_matches,
    find_catalog_matches,
    find_policy_matches,
)


@pytest.fixture
def engine(tmp_path):
    db_path = tmp_path / "test_semantic.db"
    eng = create_engine(f"sqlite:///{db_path}", echo=False, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def repo(factory):
    return EmbeddingCacheRepo(factory)


@pytest.fixture
def embedding_service():
    return EmbeddingService()


class TestSemanticSearchClientInit:
    def test_default_constructor(self):
        client = SemanticSearchClient()
        assert client._repo is not None
        assert client._embedding_service is not None

    def test_explicit_constructor(self, repo, embedding_service):
        client = SemanticSearchClient(embedding_service=embedding_service, repo=repo)
        assert client._repo is repo
        assert client._embedding_service is embedding_service

    def test_invalid_source_raises(self, repo, embedding_service):
        client = SemanticSearchClient(embedding_service=embedding_service, repo=repo)
        with pytest.raises(SemanticSearchError, match="invalid source"):
            client.search("query", "t1", "bogus")


class TestSemanticSearchIntegration:
    """Full integration: real embed + repo search."""

    def test_search_empty_cache(self, repo, embedding_service):
        client = SemanticSearchClient(embedding_service=embedding_service, repo=repo)
        results = client.search("hello", "t1", "faq")
        assert results == []

    def test_single_hit_with_high_similarity(self, repo, embedding_service, unit_vec):
        """Use an embedding vector that will be a perfect match when searching with a similar vector."""
        # Store an item with an exact direction vector
        repo.save("t1", "faq", "faq_1", "Test FAQ text", unit_vec)

        client = SemanticSearchClient(embedding_service=embedding_service, repo=repo)
        # Generate a query that yields exactly unit_vec using a known mapping trick:
        # The actual embedding of any random string won't be unit_vec, so use the same vector
        # as a mock to bypass encoding:
        mock_vec = unit_vec.copy()

        # Patch encode to return our known vector to guarantee we get a hit
        with patch.object(client._embedding_service, "encode", return_value=mock_vec):
            results = client.search("any query", "t1", "faq", min_similarity=0.9)

        assert len(results) == 1
        assert results[0]["row_id"] == "faq_1"

    def test_limit_respected(self, repo, embedding_service):
        """Ensure search returns at most 'limit' items."""
        vec_unit = np.ones(EMBED_DIM, dtype=np.float32) / np.sqrt(EMBED_DIM)
        for i in range(10):
            repo.save("t1", "faq", f"fa{i}", f"FAQ {i}", vec_unit)

        client = SemanticSearchClient(embedding_service=embedding_service, repo=repo)
        with patch.object(client._embedding_service, "encode", return_value=vec_unit):
            results = client.search("hello", "t1", "faq", limit=3)

        assert len(results) == 3

    def test_cosine_similarity_ranking(self, repo, embedding_service):
        """Verify that more similar vectors are ranked higher."""
        # Create three embeddings: one perfect, one slightly less similar, one orthogonal
        perfect = np.ones(EMBED_DIM, dtype=np.float32) / np.sqrt(EMBED_DIM)
        # Slightly perturbed: set one element different then re-normalize
        perturbed = perfect.copy()
        perturbed[0] -= 0.2
        perturbed /= np.linalg.norm(perturbed)
        orthogonal = np.zeros(EMBED_DIM, dtype=np.float32)
        orthogonal[0] = 1.0  # very different from perfect/perturbed

        repo.save("t1", "faq", "perfect", "Perfect match", perfect)
        repo.save("t1", "faq", "perturbed", "Perturbed match", perturbed)
        repo.save("t1", "faq", "orthogonal", "No match", orthogonal)

        client = SemanticSearchClient(embedding_service=embedding_service, repo=repo)
        with patch.object(client._embedding_service, "encode", return_value=perfect):
            results = client.search("hello", "t1", "faq", min_similarity=0.0)

        rows = [r["row_id"] for r in results]
        # Perfect should be first, then perturbed, then possibly orthogonal (similarity could be near zero)
        assert "perfect" in rows
        assert rows.index("perfect") < rows.index("perturbed") if "perturbed" in rows else True

    def test_tenant_isolation(self, repo, embedding_service):
        """Ensure searches respect tenant boundaries."""
        vec = np.ones(EMBED_DIM, dtype=np.float32) / np.sqrt(EMBED_DIM)
        repo.save("tenantA", "faq", "f1", "Tenant A content", vec)
        repo.save("tenantB", "faq", "f1", "Tenant B content", vec)

        client = SemanticSearchClient(embedding_service=embedding_service, repo=repo)
        with patch.object(client._embedding_service, "encode", return_value=vec):
            a_results = client.search("hello", "tenantA", "faq")
            b_results = client.search("hello", "tenantB", "faq")

        assert len(a_results) == 1
        assert len(b_results) == 1
        assert a_results[0]["text"] != b_results[0]["text"]

    def test_minimum_similarity_filtering(self, repo, embedding_service):
        """Items below min_similarity are excluded."""
        perfect = np.ones(EMBED_DIM, dtype=np.float32) / np.sqrt(EMBED_DIM)
        ortho = np.zeros(EMBED_DIM, dtype=np.float32)
        ortho[0] = 1.0

        repo.save("t1", "faq", "good", "Good match", perfect)
        repo.save("t1", "faq", "bad", "Bad match", ortho)

        client = SemanticSearchClient(embedding_service=embedding_service, repo=repo)
        with patch.object(client._embedding_service, "encode", return_value=perfect):
            # Very high threshold should only return the good match
            results = client.search("hello", "t1", "faq", min_similarity=0.99)

        assert len(results) == 1
        assert results[0]["row_id"] == "good"
        # With lower threshold both might appear (cosine ortho vs perfect is 0)
        results_low = client.search("hello", "t1", "faq", min_similarity=0.0)
        assert len(results_low) >= 1

    def test_batch_search_aggregates(self, repo, embedding_service):
        """batch_search aggregates results across queries and sources."""
        v = np.ones(EMBED_DIM, dtype=np.float32) / np.sqrt(EMBED_DIM)
        repo.save("t1", "faq", "f1", "FAQ here", v)
        repo.save("t1", "catalog", "c1", "Cat entry", v)

        client = SemanticSearchClient(embedding_service=embedding_service, repo=repo)
        with patch.object(client._embedding_service, "encode", return_value=v):
            resp = client.batch_search(["q1"], "t1", sources=["faq", "catalog"], min_similarity=0.0)

        assert "queries" in resp
        assert "summary" in resp
        assert "q1" in resp["queries"]
        hits = resp["queries"]["q1"]
        assert len(hits) >= 2  # one from each source
        assert resp["summary"]["total_hits"] >= 2

    def test_encoding_error_wrapped(self, repo):
        """Encoding failures from the service are wrapped into SemanticSearchError."""
        class FailingService:
            def encode(self, text, **kwargs):
                raise EmbeddingServiceError("no model")

        client = SemanticSearchClient(embedding_service=FailingService(), repo=repo)
        with pytest.raises(SemanticSearchError, match="failed to encode query"):
            client.search("hello", "t1", "faq")


def find_mock_client(mock_encode, mock_repo_factory):
    """Helper to construct a client without loading sentence-transformers."""
    class MockSvc:
        def encode(self, text):
            return mock_encode(text)
    client = SemanticSearchClient(embedding_service=MockSvc(), repo=mock_repo_factory())
    return client


class TestConvenienceFunctions:
    @pytest.fixture
    def unit_vec(self):
        return np.ones(EMBED_DIM, dtype=np.float32) / np.sqrt(EMBED_DIM)

    def test_find_faq_matches(self, repo, embedding_service, unit_vec):
        """find_faq_matches should return at least one match when an item exists."""
        repo.save("t1", "faq", "f1", "Garansi 7 hari", unit_vec)
        client = SemanticSearchClient(embedding_service=embedding_service, repo=repo)
        with patch.object(client._embedding_service, "encode", return_value=unit_vec):
            results = find_faq_matches("garansi", "t1", repo=repo, embedding_service=embedding_service)
        assert len(results) >= 1
        assert any("garansi" in r["text"].lower() for r in results)

    def test_find_catalog_matches(self, repo, embedding_service, unit_vec):
        repo.save("t1", "catalog", "SKU123", "Smartphone Premium", unit_vec)
        client = SemanticSearchClient(embedding_service=embedding_service, repo=repo)
        with patch.object(client._embedding_service, "encode", return_value=unit_vec):
            results = find_catalog_matches("smartphone premium", "t1", repo=repo, embedding_service=embedding_service)
        assert len(results) >= 1
        assert any("smartphone" in r["text"].lower() for r in results)

    def test_find_policy_matches(self, repo, embedding_service, unit_vec):
        repo.save("t1", "policy", "POL1", "Kebijakan pengembalian", unit_vec)
        client = SemanticSearchClient(embedding_service=embedding_service, repo=repo)
        with patch.object(client._embedding_service, "encode", return_value=unit_vec):
            results = find_policy_matches("pengembalian", "t1", repo=repo, embedding_service=embedding_service)
        assert len(results) >= 1
        assert any("pengembalian" in r["text"].lower() for r in results)


@pytest.fixture
def unit_vec():
    return np.ones(EMBED_DIM, dtype=np.float32) / np.sqrt(EMBED_DIM)