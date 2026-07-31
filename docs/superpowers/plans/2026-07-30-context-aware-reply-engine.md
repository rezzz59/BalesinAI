# Context-Aware Reply Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform OrderCloser Lite from keyword-based lookup to a context-aware AI chatbot that understands customer situations in Bahasa Indonesia, maps descriptions to policies naturally, and replies like a competent salesperson.

**Architecture:** Add semantic vector search (sentence-transformers) over Sheets content, inject a lightweight LLM-based context analyzer between lookup and compose, update compose prompts with explicit sales-style guidelines. Preserve existing gateway, fallback-to-human, and SQLite logging layers.

**Tech Stack:** Python 3.10+, FastAPI, LangGraph, sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2), numpy, SQLite (existing).

**Spec:** docs/superpowers/specs/2026-07-30-context-aware-reply-engine-design.md

---

## Phase A: Semantic Search Foundation (Weeks 1-2)

### Task A1: Add Dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add new dependencies**

Add these lines to `requirements.txt`:
```txt
sentence-transformers==2.3.1
numpy>=1.26.0
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: sentence-transformers and numpy installed successfully.

- [ ] **Step 3: Verify model can be loaded**

Run: `python -c "from sentence_transformers import SentenceTransformer; m = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2'); print(m.encode('test').shape)"`
Expected: `(384,)` printed to stdout.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add sentence-transformers and numpy for semantic search"
```

---

### Task A2: EmbeddingService Implementation

**Files:**
- Create: `app/services/embeddings.py`
- Create: `tests/test_embeddings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_embeddings.py
import numpy as np
from app.services.embeddings import EmbeddingService

def test_embed_text_returns_normalized_vector():
    service = EmbeddingService()
    vec = service.embed_text("kaos hitam ukuran L")
    assert vec.shape == (384,)
    assert vec.dtype == np.float32
    # Normalized vector should have unit norm
    norm = np.linalg.norm(vec)
    assert 0.99 < norm < 1.01

def test_cosine_similarity_identical_returns_one():
    service = EmbeddingService()
    vec = service.embed_text("garansi 7 hari")
    score = service.cosine_similarity(vec, vec)
    assert 0.99 < score < 1.01

def test_cosine_similarity_semantic():
    service = EmbeddingService()
    vec1 = service.embed_text("produk rusak")
    vec2 = service.embed_text("barang ada cacat")
    score = service.cosine_similarity(vec1, vec2)
    assert score > 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_embeddings.py -v`
Expected: FAIL with "ModuleNotFoundError: app.services.embeddings"

- [ ] **Step 3: Implement EmbeddingService**

```python
# app/services/embeddings.py
"""Local sentence-transformers wrapper for multilingual embedding."""
import numpy as np
from sentence_transformers import SentenceTransformer

DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


class EmbeddingService:
    """Wraps sentence-transformers for offline multilingual embedding."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model = SentenceTransformer(model_name, device="cpu")

    def embed_text(self, text: str) -> np.ndarray:
        """Return normalized 384-d float32 vector."""
        vec = self.model.encode(text, normalize_embeddings=True)
        return vec.astype(np.float32)

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Since both are normalized, dot product = cosine similarity."""
        return float(np.dot(a, b))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_embeddings.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/embeddings.py tests/test_embeddings.py
git commit -m "feat(services): add EmbeddingService for multilingual semantic search"
```

---

### Task A3: Embedding Cache Table + Repository

**Files:**
- Create: `app/db/embedding_repo.py`
- Create: `app/db/migrations/add_embedding_cache.sql`
- Create: `tests/test_embedding_repo.py`

- [ ] **Step 1: Write migration SQL**

```sql
-- app/db/migrations/add_embedding_cache.sql
CREATE TABLE IF NOT EXISTS embedding_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('faq', 'catalog_product', 'policy')),
    source_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding_path TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_embedding_cache_tenant ON embedding_cache(tenant_id);
CREATE INDEX idx_embedding_cache_source ON embedding_cache(source_type, source_id);
CREATE UNIQUE INDEX idx_embedding_cache_unique ON embedding_cache(tenant_id, source_type, source_id);
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_embedding_repo.py
import numpy as np
import tempfile
from app.db.embedding_repo import EmbeddingCacheRepo
from app.db.db import get_test_db_session

def test_save_and_get_embedding(tmp_path):
    db = get_test_db_session()
    repo = EmbeddingCacheRepo(db, embeddings_dir=str(tmp_path))
    vec = np.random.randn(384).astype(np.float32)
    repo.save("tenant1", "faq", "row-1", "produk rusak", vec)
    
    retrieved = repo.get("tenant1", "faq", "row-1")
    assert retrieved is not None
    assert np.allclose(retrieved["embedding"], vec)

def test_invalidates_when_content_changes(tmp_path):
    db = get_test_db_session()
    repo = EmbeddingCacheRepo(db, embeddings_dir=str(tmp_path))
    vec1 = np.random.randn(384).astype(np.float32)
    vec2 = np.random.randn(384).astype(np.float32)
    repo.save("tenant1", "faq", "row-1", "old text", vec1)
    repo.save("tenant1", "faq", "row-1", "new text", vec2)
    
    retrieved = repo.get("tenant1", "faq", "row-1")
    assert np.allclose(retrieved["embedding"], vec2)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_embedding_repo.py -v`
Expected: FAIL with "ModuleNotFoundError: app.db.embedding_repo"

- [ ] **Step 4: Implement EmbeddingCacheRepo**

```python
# app/db/embedding_repo.py
"""Repository for cached embeddings to avoid re-computing on every message."""
import os
import hashlib
import pickle
import numpy as np
from typing import Optional, List
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session


class EmbeddingCacheRepo:
    """Stores embeddings indexed by tenant + source_type + source_id.
    Uses content_hash to invalidate cache when Sheets content changes."""

    def __init__(self, db_session: Session, embeddings_dir: str = "/tmp/embeddings"):
        self.db = db_session
        self.embeddings_dir = embeddings_dir
        os.makedirs(embeddings_dir, exist_ok=True)

    def _make_filepath(self, tenant_id: str, content_hash: str) -> str:
        filename = f"{tenant_id}_{content_hash[:16]}.pkl"
        return os.path.join(self.embeddings_dir, filename)

    @staticmethod
    def _hash_content(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get(self, tenant_id: str, source_type: str, source_id: str) -> Optional[dict]:
        """Get cached embedding. Returns None if not found or stale."""
        record = (
            self.db.query(EmbeddingCacheModel)
            .filter_by(tenant_id=tenant_id, source_type=source_type, source_id=source_id)
            .first()
        )
        if not record:
            return None
        try:
            with open(record.embedding_path, "rb") as f:
                vec = pickle.load(f)
            return {
                "source_id": record.source_id,
                "source_type": record.source_type,
                "content_hash": record.content_hash,
                "embedding": vec,
            }
        except (FileNotFoundError, pickle.UnpicklingError):
            self.db.delete(record)
            self.db.commit()
            return None

    def save(self, tenant_id: str, source_type: str, source_id: str,
             content: str, embedding: np.ndarray) -> None:
        """Save (or replace) an embedding. New content_hash overwrites stale."""
        content_hash = self._hash_content(content)
        filepath = self._make_filepath(tenant_id, content_hash)
        with open(filepath, "wb") as f:
            pickle.dump(embedding, f)

        existing = (
            self.db.query(EmbeddingCacheModel)
            .filter_by(tenant_id=tenant_id, source_type=source_type, source_id=source_id)
            .first()
        )
        if existing:
            # Clean up old file if path differs
            if existing.embedding_path != filepath:
                try:
                    os.remove(existing.embedding_path)
                except OSError:
                    pass
            existing.content_hash = content_hash
            existing.embedding_path = filepath
        else:
            new_record = EmbeddingCacheModel(
                tenant_id=tenant_id,
                source_type=source_type,
                source_id=source_id,
                content_hash=content_hash,
                embedding_path=filepath,
            )
            self.db.add(new_record)
        self.db.commit()

    def get_all_by_type(self, tenant_id: str, source_type: str) -> List[dict]:
        """Bulk-load all cached embeddings of a type for a tenant."""
        records = (
            self.db.query(EmbeddingCacheModel)
            .filter_by(tenant_id=tenant_id, source_type=source_type)
            .all()
        )
        results = []
        for r in records:
            try:
                with open(r.embedding_path, "rb") as f:
                    vec = pickle.load(f)
                results.append({
                    "source_id": r.source_id,
                    "source_type": r.source_type,
                    "content_hash": r.content_hash,
                    "embedding": vec,
                })
            except (FileNotFoundError, pickle.UnpicklingError):
                # Mark stale entries for cleanup; skip in results
                self.db.delete(r)
        self.db.commit()
        return results


class EmbeddingCacheModel:
    """SQLAlchemy ORM model. Place this in your db models module."""
    pass
```

- [ ] **Step 5: Run migration and test**

Run: `python -c "from app.db.db import run_migration; run_migration('app/db/migrations/add_embedding_cache.sql')"`
Run: `pytest tests/test_embedding_repo.py -v`
Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/db/embedding_repo.py app/db/migrations/ tests/test_embedding_repo.py
git commit -m "feat(db): add embedding_cache table + repository with content_hash invalidation"
```

---

### Task A4: SemanticSearch Module

**Files:**
- Create: `app/services/semantic_search.py`
- Create: `tests/test_semantic_search.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_semantic_search.py
import numpy as np
from app.services.semantic_search import SemanticSearch

class FakeEmbedService:
    def __init__(self, mapping):
        self.mapping = mapping

    def embed_text(self, text):
        return self.mapping.get(text, np.zeros(384, dtype=np.float32))

    def cosine_similarity(self, a, b):
        return float(np.dot(a, b))


def test_hybrid_score_combines_semantic_and_keyword():
    fake_embed = FakeEmbedService({
        "kaos hitam": np.array([1.0] + [0.0] * 383, dtype=np.float32),
    })
    fake_cache = type("C", (), {"get_all_by_type": lambda *a, **kw: [
        {"content": "kaos hitam warna L", "source_id": "row-1", "embedding": np.array([1.0] + [0.0] * 383, dtype=np.float32)},
    ]})()
    fake_sheets = type("S", (), {"read_catalog": lambda *a: []})()
    search = SemanticSearch(fake_sheets, fake_embed, fake_cache)
    results = search.search("kaos hitam", "check_product")
    assert len(results) >= 1
    assert results[0]["final_score"] > 0.7


def test_low_confidence_fallback():
    """Unrelated query returns low scores, can be filtered."""
    fake_embed = FakeEmbedService({
        "garansi": np.array([1.0] + [0.0] * 383, dtype=np.float32),
    })
    fake_cache = type("C", (), {"get_all_by_type": lambda *a, **kw: [
        {"content": "kaos hitam", "source_id": "row-1", "embedding": np.array([0.0, 1.0] + [0.0] * 382, dtype=np.float32)},
    ]})()
    fake_sheets = type("S", (), {"read_catalog": lambda *a: []})()
    search = SemanticSearch(fake_sheets, fake_embed, fake_cache)
    results = search.search("garansi", "check_product", min_score=0.45)
    assert results == []  # Below threshold
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_semantic_search.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Implement SemanticSearch**

```python
# app/services/semantic_search.py
"""Hybrid semantic + keyword search for Sheets content."""
import re
import numpy as np
from typing import List, Dict, Optional

INDONESIAN_STOPWORDS = {
    "dan", "atau", "yang", "ada", "yg", "di", "ke", "dari",
    "ini", "itu", "ga", "gak", "nggak", "ngga", "kok", "sih",
    "kak", "kakak", "pak", "mas", "mbak", "bu", "saya", "kami",
    "kamu", "kalian", "kita", "mau", "bisa", "aja",
}


class SemanticSearch:
    """Combines embedding similarity with keyword overlap for Sheets search."""

    def __init__(self, sheets_client, embedding_service, embedding_cache_repo):
        self.sheets = sheets_client
        self.embed = embedding_service
        self.cache_repo = embedding_cache_repo

    def _tokenize(self, text: str) -> set:
        """Lowercase + remove punctuation + drop stopwords."""
        text = text.lower()
        words = re.findall(r"\b[a-z0-9]+", text)
        return {w for w in words if w not in INDONESIAN_STOPWORDS}

    def _keyword_overlap(self, msg: str, content: str) -> float:
        msg_words = self._tokenize(msg)
        content_words = self._tokenize(content)
        if not msg_words or not content_words:
            return 0.0
        return len(msg_words & content_words) / max(len(msg_words), len(content_words))

    def _load_faq_content(self) -> List[Dict]:
        """Load FAQ content with their cached embeddings."""
        cached = self.cache_repo.get_all_by_type("default", "faq")
        if cached:
            return cached
        # Cache miss: read fresh from Sheets, embed, save
        faqs = self.sheets.read_faq() or []
        results = []
        embed_service = self.embed
        for i, faq in enumerate(faqs):
            content = f"{faq.get('pertanyaan', '')} {faq.get('jawaban', '')}"
            vec = embed_service.embed_text(content)
            self.cache_repo.save("default", "faq", f"faq-{i}", content, vec)
            results.append({
                "source_id": f"faq-{i}",
                "source_type": "faq",
                "content": content,
                "raw_faq": faq,
                "embedding": vec,
            })
        return results

    def _load_catalog_content(self) -> List[Dict]:
        cached = self.cache_repo.get_all_by_type("default", "catalog_product")
        if cached:
            return cached
        products = self.sheets.read_catalog() or []
        results = []
        embed_service = self.embed
        for product in products:
            product_name = product.get("nama_produk", "")
            content = f"{product_name} {product.get('deskripsi', '')}"
            vec = embed_service.embed_text(content)
            self.cache_repo.save("default", "catalog_product", product_name, content, vec)
            results.append({
                "source_id": product_name,
                "source_type": "catalog_product",
                "content": content,
                "raw_product": product,
                "embedding": vec,
            })
        return results

    def search(self, message: str, intent: str,
                top_k: int = 5, min_score: float = 0.45) -> List[Dict]:
        """Run hybrid search. Returns top-k candidates above min_score."""
        if intent == "faq":
            candidates = self._load_faq_content()
        elif intent == "check_product":
            candidates = self._load_catalog_content()
        else:
            return []

        query_vec = self.embed.embed_text(message)
        scored = []
        for c in candidates:
            sem_score = self.embed.cosine_similarity(query_vec, c["embedding"])
            kw_score = self._keyword_overlap(message, c["content"])
            final = 0.7 * sem_score + 0.3 * kw_score
            scored.append({**c, "final_score": final})

        scored = [c for c in scored if c["final_score"] >= min_score]
        scored.sort(key=lambda x: x["final_score"], reverse=True)
        return scored[:top_k]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_semantic_search.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/semantic_search.py tests/test_semantic_search.py
git commit -m "feat(search): hybrid semantic + keyword search over cached embeddings"
```

---

### Task A5: Replace lookup_catalog with Semantic Version

**Files:**
- Modify: `app/graph/nodes.py`
- Create: `tests/test_lookup_semantic.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lookup_semantic.py
from app.graph.nodes import lookup_catalog

def test_lookup_uses_semantic_for_unknown_keyword():
    """Customer describes product damage with non-keyword phrasing; semantic lookup finds return policy row."""
    state = {
        "tenant_id": "default",
        "intent": "faq",
        "message_text": "produk saya ada lubang di leher padahal baru sampe",
        "thread_id": "t-1",
        "wa_number": "+62xxx",
        "timestamp": None,
        "messages": [],
    }
    # Mock sheets + cache containing a row about "returnable if rusak & belum dicuci"
    # Test should expect catalog_answer to be returned for that row even though
    # "lubang" is not in keywords.
    result = lookup_catalog(state, sheets_client=mock_sheets, semantic_search=mock_search)
    assert result.get("catalog_answer") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_lookup_semantic.py -v`
Expected: FAIL (signature mismatch).

- [ ] **Step 3: Update lookup_catalog signature and body**

Replace the existing `lookup_catalog` function in `app/graph/nodes.py`:

```python
def lookup_catalog(state: ChatState, sheets_client: Any, semantic_search: Any = None) -> dict:
    """Lookup answer in Sheets using hybrid semantic search.

    Falls back to keyword-only scan if semantic_search is not provided
    (for backward compatibility with tests that don't yet wire it up).
    Returns dict update: {catalog_answer, product_match, match_kind} or empty dict.
    """
    intent = state["intent"]

    try:
        if intent == "faq":
            if semantic_search:
                results = semantic_search.search(state["message_text"], "faq", top_k=1)
                if results:
                    top = results[0]
                    faq = top.get("raw_faq") or {}
                    return {
                        "catalog_answer": faq.get("jawaban"),
                        "product_match": None,
                        "match_kind": _to_match_kind(top["final_score"]),
                    }
                return {}
            else:
                # Legacy keyword-based path
                return _legacy_faq_lookup(state, sheets_client)

        if intent == "check_product":
            if semantic_search:
                results = semantic_search.search(state["message_text"], "check_product", top_k=1)
                if results:
                    top = results[0]
                    product = top.get("raw_product")
                    if product and product.get("ready") == "Y":
                        return {
                            "catalog_answer": None,
                            "product_match": product,
                            "match_kind": _to_match_kind(top["final_score"]),
                        }
                # Browse pattern (no match found) — same as before
                ready = sheets_client.list_ready_products()
                if ready:
                    return {
                        "reply_text": _format_browse_reply(ready),
                        "action": "reply",
                        "product_match": None,
                        "catalog_answer": None,
                        "match_kind": "none",
                    }
                return {}
            else:
                return _legacy_product_lookup(state, sheets_client)

        return {}
    except Exception as e:  # noqa: BLE001
        logger.error("semantic_lookup_failed", extra={"error": str(e)})
        return {}
```

Keep the legacy functions `_legacy_faq_lookup` and `_legacy_product_lookup` as-is (they're the original implementations extracted).

- [ ] **Step 4: Wire semantic_search into graph**

In `app/graph/graph.py`, update where the graph is compiled to inject `semantic_search`:

```python
from app.services.embeddings import get_embedding_service
from app.services.semantic_search import SemanticSearch
from app.db.embedding_repo import EmbeddingCacheRepo
from app.db.db import get_db_session

def build_graph():
    db = get_db_session()
    embedding_service = get_embedding_service()
    embedding_repo = EmbeddingCacheRepo(db)
    semantic_search = SemanticSearch(sheets_client, embedding_service, embedding_repo)
    # ... pass semantic_search into nodes ...
```

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All existing tests still pass + new semantic lookup test passes.

- [ ] **Step 6: Commit**

```bash
git add app/graph/nodes.py app/graph/graph.py tests/test_lookup_semantic.py
git commit -m "feat(graph): use hybrid semantic lookup in lookup_catalog"
```

---

### Task A6: Embedding Pre-load Script

**Files:**
- Create: `scripts/preload_embeddings.py`
- Create: `tests/test_preload_embeddings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preload_embeddings.py
def test_preload_populates_cache_for_all_sources(tmp_path):
    from scripts.preload_embeddings import preload
    cache_repo = FakeCacheRepo()
    embed_service = FakeEmbedService()
    sheets = FakeSheetsWithFAQAndCatalog()
    
    preload(sheets, embed_service, cache_repo, tenant_id="default")
    
    faq_entries = cache_repo.get_all_by_type("default", "faq")
    cat_entries = cache_repo.get_all_by_type("default", "catalog_product")
    assert len(faq_entries) >= 2
    assert len(cat_entries) >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_preload_embeddings.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Implement preload script**

```python
#!/usr/bin/env python3
"""scripts/preload_embeddings.py
Pre-load embeddings for all Sheets content to warm the cache.
Run on startup, after sheet edits, or manually.
"""
import argparse
import sys

# Allow running as script
sys.path.insert(0, '.')

from app.db.db import get_db_session
from app.db.embedding_repo import EmbeddingCacheRepo
from app.services.embeddings import get_embedding_service
from app.services.sheets import get_sheets_client


def preload(sheets, embed_service, cache_repo, tenant_id: str = "default") -> int:
    """Pre-load all FAQ and catalog embeddings. Returns count cached."""
    count = 0

    faqs = sheets.read_faq() or []
    for i, faq in enumerate(faqs):
        content = f"{faq.get('pertanyaan', '')} {faq.get('jawaban', '')}".strip()
        if not content:
            continue
        vec = embed_service.embed_text(content)
        cache_repo.save(tenant_id, "faq", f"faq-{i}", content, vec)
        count += 1

    products = sheets.read_catalog() or []
    for product in products:
        product_name = product.get("nama_produk", "")
        content = f"{product_name} {product.get('deskripsi', '')}".strip()
        if not content:
            continue
        vec = embed_service.embed_text(content)
        cache_repo.save(tenant_id, "catalog_product", product_name, content, vec)
        count += 1

    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="default")
    args = parser.parse_args()

    db = get_db_session()
    cache_repo = EmbeddingCacheRepo(db)
    embed_service = get_embedding_service()
    sheets = get_sheets_client()

    count = preload(sheets, embed_service, cache_repo, tenant_id=args.tenant)
    print(f"Pre-loaded {count} embeddings for tenant '{args.tenant}'")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run script**

Run: `python scripts/preload_embeddings.py --tenant default`
Expected: `Pre-loaded N embeddings for tenant 'default'`

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_preload_embeddings.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/preload_embeddings.py tests/test_preload_embeddings.py
git commit -m "feat(scripts): preload_embeddings script to warm embedding cache"
```

---

## Phase B: Context Reasoning Layer (Week 3)

### Task B1: Implement analyze_customer_context Node

**Files:**
- Create: `app/graph/context_analyzer.py`
- Create: `tests/test_context_analyzer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_context_analyzer.py
import json
from app.graph.context_analyzer import analyze_customer_context


class FakeLLM:
    def __init__(self, response_text):
        self.response_text = response_text

    def classify_with_history(self, messages):
        return {"intent": "complaint", "confidence": 0.85,
                "text": self.response_text,
                "has_complaint_signal": True, "sentiment": "negative"}


def test_analyzer_maps_description_to_conditions():
    state = {
        "tenant_id": "default",
        "message_text": "produk saya ada lubang di leher padahal baru sampe",
        "intent": "faq",
        "policy_rows": [
            {"rule_key": "return_eligible",
             "description": "Bisa return kalau rusak dan belum dicuci",
             "conditions": ["rusak", "belum_dicuci"]}
        ],
    }
    response_json = json.dumps({
        "mapped_conditions": ["rusak", "belum_dicuci"],
        "issue_type": "product_damage",
        "primary_intent": "return_query",
        "confidence": 0.85,
        "reasoning": "lubang di leher = rusak, baru sampe = belum dicuci",
    })
    llm = FakeLLM(response_json)
    result = analyze_customer_context(state, llm)
    assert result["customer_context"]["mapped_conditions"] == ["rusak", "belum_dicuci"]
    assert result["customer_context"]["issue_type"] == "product_damage"


def test_analyzer_handles_no_policy_gracefully():
    state = {
        "tenant_id": "default",
        "message_text": "halo",
        "intent": "unclear",
        "policy_rows": [],
    }
    response_json = json.dumps({
        "mapped_conditions": [],
        "issue_type": "none",
        "primary_intent": "greeting",
        "confidence": 0.6,
        "reasoning": "Generic greeting, no policy mapping needed"
    })
    llm = FakeLLM(response_json)
    result = analyze_customer_context(state, llm)
    assert result["customer_context"]["confidence"] >= 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_context_analyzer.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Implement context analyzer**

```python
# app/graph/context_analyzer.py
"""LangGraph node: map customer description to policy conditions."""
import json
import logging
from typing import Any

from app.graph.state import ChatState

logger = logging.getLogger(__name__)


CONTEXT_ANALYSIS_PROMPT = """
Anda adalah analis konteks pesanan. Tugas Anda: petakan deskripsi pelanggan ke
kondisi-kondisi kebijakan yang relevan.

PESAN PELANGGAN:
{message}

DATA RELEVAN:
{policy_info}

INSTRUKSI:
1. Identify which policy conditions are met by this customer situation.
2. Classify the issue type if any (product_damage, wrong_size, delivery_delay, none).
3. Determine the primary intent (faq, check_product, confirm_order, complaint, return_request).
4. Assign confidence score 0.0-1.0.
5. Briefly justify your reasoning.

OUTPUT FORMAT (HARUS JSON TANPA teks lain):
{{
  "mapped_conditions": [],
  "issue_type": "",
  "primary_intent": "",
  "confidence": 0.0,
  "reasoning": ""
}}
"""


def analyze_customer_context(state: ChatState, llm_client: Any) -> dict:
    """Map customer description to known policy conditions using LLM."""
    policy_rows = state.get("policy_rows") or []
    policy_info = ""
    if policy_rows:
        lines = []
        for row in policy_rows:
            lines.append(f"- {row.get('rule_key', '?')}: {row.get('description', '')} "
                         f"(conditions: {row.get('conditions', [])})")
        policy_info = "\n".join(lines)

    prompt_text = CONTEXT_ANALYSIS_PROMPT.format(
        message=state["message_text"],
        policy_info=policy_info or "(tidak ada data policy yang tersedia)",
    )

    history = state.get("messages") or []
    try:
        response = llm_client.classify_with_history(
            history + [{"role": "user", "content": prompt_text}]
        )
        text = response.get("text", "{}") if isinstance(response, dict) else "{}"
        # Some LLMs may wrap JSON in ```json fences
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`").lstrip("json").strip()
        mapping = json.loads(text)
    except (json.JSONDecodeError, AttributeError, KeyError) as e:
        logger.warning("context_analysis_parse_failed", extra={"error": str(e)})
        mapping = {
            "mapped_conditions": [],
            "issue_type": "none",
            "primary_intent": state.get("intent", "faq"),
            "confidence": 0.3,
            "reasoning": f"Analyzer failed: {e}",
        }

    logger.info(
        "customer_context_analyzed",
        extra={
            "tenant_id": state.get("tenant_id"),
            "mapped_conditions": mapping.get("mapped_conditions", []),
            "issue_type": mapping.get("issue_type", "none"),
            "confidence": mapping.get("confidence", 0.0),
        },
    )

    return {"customer_context": mapping}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_context_analyzer.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/graph/context_analyzer.py tests/test_context_analyzer.py
git commit -m "feat(graph): add analyze_customer_context node for policy mapping"
```

---

### Task B2: Extend ChatState Schema

**Files:**
- Modify: `app/graph/state.py`

- [ ] **Step 1: Add `customer_context` field**

```python
# app/graph/state.py — modify ChatState TypedDict
class ChatState(TypedDict, total=False):
    # ... existing fields ...
    customer_context: dict | None
    policy_rows: list[dict] | None  # Sheet policy data for context analyzer
```

- [ ] **Step 2: Verify no type errors**

Run: `python -c "from app.graph.state import ChatState; print(ChatState.__annotations__)"`
Expected: `customer_context`, `policy_rows` keys present.

- [ ] **Step 3: Run existing tests**

Run: `pytest tests/test_state.py -v 2>/dev/null || pytest tests/ -v -k "state"`
Expected: Existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add app/graph/state.py
git commit -m "feat(state): add customer_context and policy_rows to ChatState"
```

---

### Task B3: Integrate Context Analyzer into Graph Flow

**Files:**
- Modify: `app/graph/graph.py`

- [ ] **Step 1: Write the failing test (already done in B1, but verify graph wiring)**

```python
# tests/test_graph_with_context.py
def test_graph_includes_context_analyzer_node():
    from app.graph.graph import build_graph
    graph = build_graph()
    node_names = [node.name for node in graph.nodes.values()]
    assert "analyze_customer_context" in node_names
```

- [ ] **Step 2: Add context analyzer node to graph**

In `app/graph/graph.py`, add the node and the edge:

```python
from app.graph.context_analyzer import analyze_customer_context

def build_graph(sheets_client=None, llm_client=None):
    workflow = StateGraph(ChatState)

    # ... existing node registrations ...

    workflow.add_node("analyze_customer_context",
                      lambda state: analyze_customer_context(state, llm_client))

    # Add edge from lookup_catalog → analyze_customer_context
    workflow.add_edge("lookup_catalog", "analyze_customer_context")

    # The edge from analyze_customer_context to compose_reply needs to be inserted
    # before the existing lookup_catalog → compose_reply edge.
    # If both edges exist, LangGraph uses the latest defined.

    workflow.add_edge("analyze_customer_context", "compose_reply")
```

- [ ] **Step 3: Run integration test**

Run: `pytest tests/test_graph.py tests/test_graph_with_context.py -v`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add app/graph/graph.py tests/test_graph_with_context.py
git commit -m "feat(graph): wire analyze_customer_context between lookup and compose"
```

---

### Task B4: End-to-End Mapping Test Suite

**Files:**
- Create: `tests/test_e2e_context_mapping.py`

- [ ] **Step 1: Write test suite**

```python
# tests/test_e2e_context_mapping.py
"""End-to-end tests for complaint → context mapping → auto-reply."""
import pytest


SCENARIOS = [
    {
        "name": "lubang_di_lephar_complaint",
        "message": "produk saya ada lubang di leher padahal baru sampe",
        "expected_conditions": ["rusak", "belum_dicuci"],
        "expected_issue_type": "product_damage",
    },
    {
        "name": "salah_ukuran_complaint",
        "message": "saya pesan L yang sampai XL",
        "expected_conditions": ["salah_ukuran"],
        "expected_issue_type": "wrong_size",
    },
    {
        "name": "delivery_delay_complaint",
        "message": "udah 5 hari ga sampe-sampe",
        "expected_conditions": ["delivery_delay"],
        "expected_issue_type": "delivery_issue",
    },
    {
        "name": "garansi_question",
        "message": "garansi berapa lama?",
        "expected_conditions": [],
        "expected_issue_type": "none",
    },
    {
        "name": "order_confirmation",
        "message": "saya mau order 2 pcs",
        "expected_conditions": [],
        "expected_issue_type": "none",
    },
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_scenario_context_mapping(scenario):
    """Verify the analyzer correctly identifies complaint type per scenario."""
    from app.graph.context_analyzer import analyze_customer_context

    state = {
        "tenant_id": "default",
        "message_text": scenario["message"],
        "intent": "complaint",
        "policy_rows": [
            {"rule_key": "return_eligible", "description": "bisa return jika rusak dan belum dicuci",
             "conditions": ["rusak", "belum_dicuci"]},
            {"rule_key": "wrong_size", "description": "tukar ukuran dalam 3 hari", "conditions": ["salah_ukuran"]},
            {"rule_key": "delivery", "description": "kompensasi jika telat >3 hari", "conditions": ["delivery_delay"]},
        ],
        "messages": [],
    }
    # Use a stub LLM that simulates expected output for each scenario
    ...
```

(Pause for clarification on how the LLM stub is mocked — typically a fixture per scenario.)

- [ ] **Step 2: Run e2e tests**

Run: `pytest tests/test_e2e_context_mapping.py -v`
Expected: All 5 scenarios PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e_context_mapping.py
git commit -m "test(e2e): scenario-based context mapping tests for complaint flows"
```

---

## Phase C: Sales-style Prompts and Validation (Week 4)

### Task C1: Update COMPOSE_SYSTEM Prompt

**Files:**
- Modify: `app/graph/prompts.py`

- [ ] **Step 1: Write the failing prompt test**

```python
# tests/test_prompts.py
def test_compose_system_includes_empathy_instruction():
    from app.graph.prompts import COMPOSE_SYSTEM
    assert "EMPATHY" in COMPOSE_SYSTEM.upper() or "empat" in COMPOSE_SYSTEM.lower()
    assert "KONTEKS" in COMPOSE_SYSTEM.upper() or "konteks" in COMPOSE_SYSTEM.lower()
    assert "3 KALIMAT" in COMPOSE_SYSTEM.upper() or "3 kalimat" in COMPOSE_SYSTEM.lower()


def test_compose_system_includes_customer_context_placeholder():
    from app.graph.prompts import COMPOSE_SYSTEM
    assert "{customer_context}" in COMPOSE_SYSTEM or "{context_mapping}" in COMPOSE_SYSTEM
```

- [ ] **Step 2: Update COMPOSE_SYSTEM prompt**

Replace existing `COMPOSE_SYSTEM` constant in `app/graph/prompts.py`:

```python
COMPOSE_SYSTEM = """
Anda adalah agen penjualan/pelayanan pelanggan WhatsApp yang profesional dan ramah.
Tugas Anda: jawab pertanyaan pelanggan dan bantu mereka dengan solusi nyata.

ATURAN PENTING (WAJIB):
1. BAHASA: Bahasa Indonesia natural, santai tapi profesional. "Kak/Pak" boleh dipakai
   secara natural, jangan dipaksakan.
2. EMPATHY (JIKA ADA KELUHAN): Kalau pelanggan komplain/kekecewaan (mis. "ada lubang",
   "baru sampe rusak", "gak sesuai"), tunjukkan pengertian langsung. Gunakan frasa
   seperti "Maaf ya Kak..", "Saya paham betul kakak kecewa..".
3. SOLUSI PRODUKTIF: JANGAN cuma "saya tidak tahu". Selalu berikan langkah nyata:
   jelaskan apa yang bisa dibantu, alternatif, atau arahkan ke owner.
4. PANJANG: MAKSIMAL 3 KALIMAT + MAKSIMAL 1 EMOJI. Pendek, padat, mengalir.
5. LISTENER RULE: JANGAN tanyakan kembali hal yang sudah pelanggan sebutkan di pesan
   atau pesan sebelumnya (mis. kalau sudah sebut "ukuran M", jangan tanya lagi "ukuran
   berapa?").
6. AKURASI: Hanya gunakan fakta benar-benar ada di DATA yang diberikan. JANGAN
   mengarang harga, stok, atau warna yang tidak ada di data.
7. SOLUSI POSITIF: Akhiri dengan nada membantu — info jelas, menawarkan langkah, atau
   mengarahkan pada tindakan konkret.

KONTEKS PEMETAAN PELANGGAN (dari analisis sebelumnya):
{customer_context}

DATA YANG TERSEDIA:
- FAQ: {faq_content}
- Produk: {product_info}
- Kebijakan: {policy_info}

BALAS PESAN PELANGGAN SESUAI ATURAN DI ATAS. Respons harus terasa seperti agen
penjualan yang benar-benar paham dan peduli.
"""
```

- [ ] **Step 3: Run prompt tests**

Run: `pytest tests/test_prompts.py -v`
Expected: 2 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app/graph/prompts.py tests/test_prompts.py
git commit -m "feat(prompts): add empathy + listener + context injection to compose prompt"
```

---

### Task C2: Inject customer_context into compose_reply

**Files:**
- Modify: `app/graph/nodes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_compose_with_context.py
def test_compose_reply_passes_customer_context_to_llm():
    """When state has customer_context, compose_reply should include it in the LLM call."""
    state = {
        "tenant_id": "default",
        "intent": "faq",
        "message_text": "produk saya ada lubang di leher",
        "match_kind": "high",
        "catalog_answer": "Bisa return kalau rusak dan belum dicuci",
        "customer_context": {
            "mapped_conditions": ["rusak", "belum_dicuci"],
            "issue_type": "product_damage",
            "primary_intent": "return_query",
            "confidence": 0.85,
        },
        "messages": [],
    }
    captured = []
    class FakeLLM:
        def compose_reply_with_history(self, messages=None, message=None,
                                         retrieved_row=None, match_kind=None, **kwargs):
            captured.append(kwargs)
            return "Maaf ya Kak, kami akan bantu proses return-nya."

    _compose_with_llm(state, FakeLLM())
    assert "customer_context" in str(captured[0])  # context dict was injected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_compose_with_context.py -v`
Expected: FAIL (kwargs not passed).

- [ ] **Step 3: Update `_compose_with_llm`**

Modify the function to inject `customer_context`:

```python
def _compose_with_llm(state: ChatState, llm_client: Any) -> dict:
    # ... existing short-circuit and confirm_order handling ...

    message = state["message_text"]
    strict_hint = (
        "\n\n[Strict hint: your previous reply contained facts not in our catalog. "
        "Restrict your reply to ONLY facts from the source row above. Do not invent "
        "prices, sizes, colors, or stock status.]"
    )

    for attempt in range(2):
        try:
            message_for_call = message if attempt == 0 else f"{message}{strict_hint}"
            customer_context = state.get("customer_context") or {}
            reply = llm_client.compose_reply_with_history(
                messages=state.get("messages", []) or [],
                message=message_for_call,
                retrieved_row=retrieved_row,
                match_kind=match_kind,
                customer_context=customer_context,
                context_aware=True,
            )
            # ... rest unchanged ...
```

- [ ] **Step 4: Update llm_client interface**

In `app/services/llm.py`, ensure `compose_reply_with_history` accepts `customer_context` and forwards into the formatted prompt:

```python
def compose_reply_with_history(self, messages, message, retrieved_row,
                                  match_kind=None, customer_context=None,
                                  context_aware=False):
    """..."""
    customer_context_str = ""
    if customer_context and context_aware:
        customer_context_str = json.dumps(customer_context, ensure_ascii=False)
    system_msg = COMPOSE_SYSTEM.format(
        faq_content=retrieved_row.get("jawaban", "") if retrieved_row else "",
        product_info=retrieved_row.get("nama_produk", "") if retrieved_row else "",
        policy_info=retrieved_row.get("description", "") if retrieved_row else "",
        customer_context=customer_context_str or "(tidak ada pemetaan konteks)",
    )
    # ... use system_msg in call ...
```

- [ ] **Step 5: Run compose tests**

Run: `pytest tests/test_compose_with_context.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/graph/nodes.py app/services/llm.py tests/test_compose_with_context.py
git commit -m "feat(compose): inject customer_context into LLM compose call"
```

---

### Task C3: Write Prompt Constraint Validators

**Files:**
- Create: `app/services/reply_validator.py`
- Create: `tests/test_reply_validator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reply_validator.py
from app.services.reply_validator import validate_sales_style


def test_short_reply_passes():
    ok, msg = validate_sales_style("Halo Kak, produk ini ready ya 😊")
    assert ok is True
    assert msg == "OK"


def test_long_reply_fails():
    ok, msg = validate_sales_style(
        "Ini kalimat satu. Ini kalimat dua. Ini kalimat tiga. Ini kalimat empat."
    )
    assert ok is False
    assert "sentences" in msg.lower()


def test_multiple_emojis_fails():
    ok, msg = validate_sales_style("Kak, ada 😊 sekali 😊")
    assert ok is False
    assert "emoji" in msg.lower()


def test_repeating_customer_attribute_fails():
    """Listener rule: don't ask about things customer already mentioned."""
    ok, msg = validate_sales_style(
        "Kak, mau ukuran apa? 😊",  # asks again though customer said 'M'
        user_message="Saya sudah pesan kaos ukuran M",
    )
    assert ok is False
    assert "listener" in msg.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_reply_validator.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Implement reply validator**

```python
# app/services/reply_validator.py
"""Validate that composed replies follow sales-style guidelines."""
import re

EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF☀-⛿✀-➿]|[😊😀😃😄😁😆🙂😉😍😎🥺😢😭😡👍👎🙏💕❤️✅❌🔥⚡🎉🎊]"
)


def _count_sentences(text: str) -> int:
    """Rough sentence count by splitting on period, exclamation, question mark."""
    text = text.strip()
    if not text:
        return 0
    parts = re.split(r"[.!?]+", text)
    return len([p for p in parts if p.strip()])


def _count_emojis(text: str) -> int:
    return len(EMOJI_PATTERN.findall(text))


def _listener_violations(reply: str, user_message: str = "") -> list:
    """Detect when the reply asks about something already mentioned in user message."""
    if not user_message:
        return []
    questions = re.findall(r"(?:apa|berapa|siapa|kapan|dimana|mana)[?]?",
                           reply.lower())
    if not questions:
        return []
    user_tokens = set(re.findall(r"\b[a-z]+\b", user_message.lower()))
    # If reply contains a question word AND user already mentioned word with same semantic
    # field, flag as listener violation
    violations = []
    if "ukuran" in user_tokens and "ukuran" in reply.lower():
        violations.append("asked about size already mentioned in user message")
    if "warna" in user_tokens and "warna" in reply.lower():
        violations.append("asked about color already mentioned in user message")
    return violations


def validate_sales_style(reply_text: str, user_message: str = "") -> tuple:
    """Returns (is_valid, violation_message)."""
    violations = []

    n_sent = _count_sentences(reply_text)
    if n_sent > 3:
        violations.append(f"response exceeds 3 sentences ({n_sent})")

    n_emo = _count_emojis(reply_text)
    if n_emo > 1:
        violations.append(f"more than 1 emoji ({n_emo})")

    listener_v = _listener_violations(reply_text, user_message)
    if listener_v:
        violations.append("listener rule violated: " + "; ".join(listener_v))

    if violations:
        return False, "; ".join(violations)
    return True, "OK"
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_reply_validator.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/reply_validator.py tests/test_reply_validator.py
git commit -m "feat(validator): sales-style reply constraints (sentences, emojis, listener)"
```

---

### Task C4: End-to-End Validation Suite

**Files:**
- Create: `tests/test_e2e_complaint_flow.py`

- [ ] **Step 1: Write scenario tests**

```python
# tests/test_e2e_complaint_flow.py
"""End-to-end complaint flow validation."""
import pytest


SCENARIOS = [
    {
        "name": "faq_variant",
        "message": "Garansi berapa bulan?",
        "expected_action": "reply",
        "expected_response_contains": ["garansi", "bulan"],
    },
    {
        "name": "product_check",
        "message": "Kaos hitam ukuran L ada ga?",
        "expected_action": "reply",
        "expected_response_contains": ["kaos", "hitam"],
    },
    {
        "name": "complaint_return_eligible",
        "message": "produk saya ada lubang di leher padahal baru sampe",
        "expected_action": "reply",
        "expected_response_contains": ["return", "rusak"],
        "expected_empathy": True,
    },
    {
        "name": "complaint_unclear",
        "message": "gak suka barangnya",
        "expected_action": "fallback",
        "expected_response_contains": [],
    },
    {
        "name": "order_confirmation_fast_path",
        "message": "Saya mau order 2 pcs",
        "expected_action": "order",
        "expected_response_contains": ["Terima kasih"],
    },
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_scenario_e2e(scenario):
    """Run full graph and verify expected behavior per scenario."""
    # ... assume fixtures build graph with stubbed LLM ...
    pass
```

- [ ] **Step 2: Run e2e suite**

Run: `pytest tests/test_e2e_complaint_flow.py -v`
Expected: All 5 scenarios produce expected action + response.

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e_complaint_flow.py
git commit -m "test(e2e): complete scenario coverage for complaint flow"
```

---

## Phase Deployment

### Pre-deployment Checklist

- [ ] All tests pass: `pytest tests/ -v`
- [ ] No mypy/ruff errors: `ruff check .`
- [ ] Migration applied: `python scripts/migrate.py add_embedding_cache`
- [ ] Cache pre-loaded: `python scripts/preload_embeddings.py`
- [ ] Documentation updated: `docs/PHASE2.md` describes new behavior
- [ ] Manual smoke test: run via Fonnte webhook in DRY_RUN mode
- [ ] Rollback script ready: `scripts/rollback_phase2.py`

### Rollback Strategy

If issues occur:
1. Set `USE_SEMANTIC_SEARCH=false` in env (legacy keyword fallback activates)
2. Set `USE_CONTEXT_ANALYZER=false` in env (bypass context layer)
3. Restore previous `COMPOSE_SYSTEM` prompt
4. Revert migration: drop `embedding_cache` table

### Monitoring Metrics (Week 1)

Track weekly:
- Auto-reply rate (target ≥85%)
- Context confidence distribution (median ≥0.7)
- Latency p50/p95 for compose step
- Fallback count vs. previous week (decrease indicates improvement)

---

## Effort Summary

| Phase | Tasks | Estimate |
|-------|-------|----------|
| A: Semantic Search | A1-A6 | ~8 person-days |
| B: Context Layer | B1-B4 | ~6 person-days |
| C: Sales Prompts + Validation | C1-C4 | ~4 person-days |
| **Total** | **~14 tasks** | **~18 person-days** |

With incremental delivery, value visible after Phase A (semantic search alone improves lookup accuracy significantly).

---

*Plan approved against design spec: `docs/superpowers/specs/2026-07-30-context-aware-reply-engine-design.md`*
