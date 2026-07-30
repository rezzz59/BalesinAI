"""Tests for EmbeddingCacheRepo."""

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.embeddings_repo import (
    EmbeddingCacheRepo,
    _to_blob,
    _from_blob,
    compute_content_hash,
    EMBED_DIM,
)
from app.db.models import Base


@pytest.fixture
def engine(tmp_path):
    """Per-test SQLite engine with schema created."""
    db_path = tmp_path / "test_embeddings.db"
    eng = create_engine(f"sqlite:///{db_path}", echo=False, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def repo(factory):
    return EmbeddingCacheRepo(factory)


@pytest.fixture
def unit_vec():
    """384-dim unit-norm float32 vector."""
    vec = np.ones(EMBED_DIM, dtype=np.float32)
    return vec / np.linalg.norm(vec)


class TestEmbeddingUtils:
    def test_compute_content_hash_normalizes(self):
        h1 = compute_content_hash("  Hello World  ")
        h2 = compute_content_hash("hello world")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex length

    def test_compute_content_hash_different_text(self):
        assert compute_content_hash("a") != compute_content_hash("b")

    def test_blob_roundtrip(self, unit_vec):
        blob = _to_blob(unit_vec)
        restored = _from_blob(blob)
        np.testing.assert_array_equal(unit_vec, restored)

    def test_to_blob_invalid_shape(self):
        bad = np.ones(10, dtype=np.float32)
        with pytest.raises(ValueError):
            _to_blob(bad)

    def test_to_blob_invalid_dtype(self):
        bad = np.ones(EMBED_DIM, dtype=np.float64)
        with pytest.raises(ValueError):
            _to_blob(bad)

    def test_from_blob_invalid_length(self):
        with pytest.raises(ValueError):
            _from_blob(b"\x00" * 100)


class TestEmbeddingCacheRepoSave:
    def test_save_and_find_by_id(self, repo, unit_vec):
        text = "Garansi produk 7 hari"
        repo.save(tenant_id="t1", source="faq", row_id="faq_1", text=text, embedding=unit_vec)

        result = repo.find_by_id("t1", "faq", "faq_1")
        assert result is not None
        assert result.tenant_id == "t1"
        assert result.source == "faq"
        assert result.row_id == "faq_1"
        assert result.text == text
        assert result.content_hash == compute_content_hash(text)
        np.testing.assert_array_equal(result.embedding, unit_vec)

    def test_save_overwrites_same_row_id(self, repo):
        vec1 = np.ones(EMBED_DIM, dtype=np.float32)
        vec1 /= np.linalg.norm(vec1)
        vec2 = np.full(EMBED_DIM, -1.0, dtype=np.float32)
        vec2 /= np.linalg.norm(vec2)

        repo.save("t1", "faq", "faq_1", "text v1", vec1)
        repo.save("t1", "faq", "faq_1", "text v2", vec2)

        result = repo.find_by_id("t1", "faq", "faq_1")
        assert result.text == "text v2"
        np.testing.assert_array_equal(result.embedding, vec2)

    def test_save_invalid_source_raises(self, repo, unit_vec):
        with pytest.raises(ValueError):
            repo.save("t1", "invalid", "r1", "text", unit_vec)

    def test_save_invalid_vector_dtype_raises(self, repo):
        bad = np.ones(EMBED_DIM, dtype=np.float64)
        with pytest.raises(ValueError):
            repo.save("t1", "faq", "r1", "text", bad)

    def test_save_invalid_vector_shape_raises(self, repo):
        bad = np.ones(100, dtype=np.float32)
        with pytest.raises(ValueError):
            repo.save("t1", "faq", "r1", "text", bad)


class TestEmbeddingCacheRepoFind:
    def test_find_by_hash(self, repo, unit_vec):
        text = "Barang rusak"
        repo.save("t1", "faq", "faq_1", text, unit_vec)

        h = compute_content_hash(text)
        result = repo.find_by_hash("t1", "faq", h)
        assert result is not None
        assert result.row_id == "faq_1"

    def test_find_by_hash_missing(self, repo):
        result = repo.find_by_hash("t1", "faq", "missing_hash_xxx")
        assert result is None

    def test_find_by_id_missing(self, repo):
        result = repo.find_by_id("t1", "faq", "missing_row")
        assert result is None

    def test_tenant_isolation(self, repo, unit_vec):
        repo.save("t1", "faq", "faq_1", "x", unit_vec)
        repo.save("t2", "faq", "faq_1", "x", unit_vec)

        assert repo.find_by_id("t1", "faq", "faq_1") is not None
        assert repo.find_by_id("t2", "faq", "faq_1") is not None
        assert repo.find_by_id("t3", "faq", "faq_1") is None


class TestEmbeddingCacheRepoSearch:
    def test_search_nearest_returns_self_first(self, repo, unit_vec):
        repo.save("t1", "faq", "faq_1", "rusak", unit_vec)
        results = repo.search_nearest("t1", "faq", unit_vec, limit=5)
        assert len(results) == 1
        emb, sim = results[0]
        assert emb.row_id == "faq_1"
        assert 0.99 < sim < 1.01

    def test_search_nearest_orders_by_similarity(self, repo):
        vec_base = np.zeros(EMBED_DIM, dtype=np.float32)
        vec_base[0] = 1.0
        vec_near = vec_base.copy()
        vec_near[1] = 0.1
        vec_far = np.zeros(EMBED_DIM, dtype=np.float32)
        vec_far[100] = 1.0

        # All vectors must be unit-norm for cosine to behave correctly
        for v in (vec_base, vec_near, vec_far):
            v /= np.linalg.norm(v)

        repo.save("t1", "catalog", "a", "A", vec_base)
        repo.save("t1", "catalog", "b", "B", vec_near)
        repo.save("t1", "catalog", "c", "C", vec_far)

        results = repo.search_nearest("t1", "catalog", vec_base, limit=3)
        assert [r[0].row_id for r in results] == ["a", "b", "c"]
        sims = [r[1] for r in results]
        assert sims[0] > sims[1] > sims[2]

    def test_search_nearest_respects_limit(self, repo, unit_vec):
        for i in range(5):
            v = unit_vec.copy()
            v[i] = 2.0
            v /= np.linalg.norm(v)
            repo.save("t1", "catalog", f"row_{i}", f"text {i}", v)
        results = repo.search_nearest("t1", "catalog", unit_vec, limit=3)
        assert len(results) == 3

    def test_search_nearest_empty_source(self, repo, unit_vec):
        results = repo.search_nearest("t1", "catalog", unit_vec, limit=5)
        assert results == []

    def test_search_nearest_invalid_query_raises(self, repo):
        bad = np.ones(EMBED_DIM, dtype=np.float64)
        with pytest.raises(ValueError):
            repo.search_nearest("t1", "catalog", bad, limit=5)


class TestEmbeddingCacheRepoInvalidate:
    def test_invalidate_by_row(self, repo, unit_vec):
        repo.save("t1", "faq", "faq_1", "text", unit_vec)
        assert repo.find_by_id("t1", "faq", "faq_1") is not None

        repo.invalidate_by_row("t1", "faq", "faq_1")
        assert repo.find_by_id("t1", "faq", "faq_1") is None

    def test_invalidate_by_hash(self, repo, unit_vec):
        text = "barang rusak"
        repo.save("t1", "faq", "faq_1", text, unit_vec)
        h = compute_content_hash(text)
        assert repo.find_by_hash("t1", "faq", h) is not None

        repo.invalidate_by_hash("t1", "faq", h)
        assert repo.find_by_hash("t1", "faq", h) is None

    def test_invalidate_only_removes_target(self, repo, unit_vec):
        repo.save("t1", "faq", "faq_1", "alpha", unit_vec)
        repo.save("t1", "faq", "faq_2", "beta", unit_vec)

        repo.invalidate_by_row("t1", "faq", "faq_1")
        assert repo.find_by_id("t1", "faq", "faq_1") is None
        assert repo.find_by_id("t1", "faq", "faq_2") is not None
