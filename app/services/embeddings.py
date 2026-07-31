"""Local sentence-transformers wrapper for multilingual embedding.

Uses paraphrase-multilingual-MiniLM-L12-v2 (384-dim) which handles
Indonesian + English in a shared vector space.
"""
import numpy as np
from sentence_transformers import SentenceTransformer

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


class EmbeddingServiceError(Exception):
    """Raised when embedding generation fails."""

    pass

_service: "EmbeddingService | None" = None


def get_embedding_service() -> "EmbeddingService":
    """Return a process-singleton EmbeddingService (model loads once)."""
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service


class EmbeddingService:
    """Wraps sentence-transformers for offline multilingual embedding.

    All returned vectors are L2-normalized float32 (dim=384).
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model = SentenceTransformer(model_name, device="cpu")

    def embed_text(self, text: str) -> np.ndarray:
        """Return normalized 384-d float32 vector."""
        try:
            vec = self.model.encode(text, normalize_embeddings=True)
            return vec.astype(np.float32)
        except Exception as e:
            raise EmbeddingServiceError(f"embedding failed: {e}") from None

    def encode(self, text: str) -> np.ndarray:
        """Alias of embed_text (used by SemanticSearchClient)."""
        return self.embed_text(text)

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity for two unit-norm vectors is just their dot product."""
        return float(np.dot(a, b))
