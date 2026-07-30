"""Tests for EmbeddingService — multilingual semantic vector generation."""
import numpy as np

from app.services.embeddings import EmbeddingService


def test_embed_text_returns_normalized_vector():
    """Verify embed_text returns a unit-norm float32 vector of dim 384."""
    service = EmbeddingService()
    vec = service.embed_text("kaos hitam ukuran L")
    assert vec.shape == (384,)
    assert vec.dtype == np.float32
    norm = np.linalg.norm(vec)
    assert 0.99 < norm < 1.01, f"vector should be unit-norm, got {norm}"


def test_cosine_similarity_identical_returns_one():
    """Verify cosine_similarity of a vector with itself is ~1.0."""
    service = EmbeddingService()
    vec = service.embed_text("garansi 7 hari")
    score = service.cosine_similarity(vec, vec)
    assert 0.99 < score < 1.01


def test_cosine_similarity_semantic():
    """Verify semantically related Indonesian phrases get high cosine sim."""
    service = EmbeddingService()
    vec1 = service.embed_text("produk rusak")
    vec2 = service.embed_text("barang ada cacat")
    score = service.cosine_similarity(vec1, vec2)
    assert score > 0.5, f"related phrases should score > 0.5, got {score}"