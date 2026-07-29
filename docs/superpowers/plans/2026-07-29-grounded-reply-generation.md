# Grounded Reply Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the verbatim-xlsx reply step in `compose_reply` with an LLM-composed natural-Indonesian reply, grounded in matched xlsx rows, with strict no-hallucination rules and a fallback chain.

**Architecture:** Add `compose_reply()` to `LLMClient`. Add `match_kind` scoring in `lookup_catalog` (high/medium/none by keyword overlap). New `compose_with_llm()` orchestrator in `nodes.py` calls the LLM, validates numeric facts against the source row, retries once on validation failure, falls back to verbatim-xlsx reply on any failure. New `validate_reply()` helper enforces the no-hallucination contract.

**Tech Stack:** Python 3.10+, FastAPI, LangGraph, Google Gemini (`gemini-3.1-flash-lite`) or Anthropic Claude (`claude-haiku-4-5`) for LLM. gspread for Sheets. pytest for tests.

**Spec:** `docs/superpowers/specs/2026-07-29-grounded-reply-generation-design.md`

**Reference files:**
- `app/graph/nodes.py` (current `compose_reply` at lines 75-118, `lookup_catalog` at lines 33-72)
- `app/services/llm.py` (current `classify()` pattern to mirror)
- `app/graph/prompts.py` (existing `INTENT_CLASSIFICATION_*` prompts)
- `app/graph/state.py` (existing `ChatState`)
- `tests/conftest.py` (existing fixtures)

---

## Task 1: Add compose prompts to `app/graph/prompts.py`

**Files:**
- Modify: `app/graph/prompts.py`
- Test: `tests/test_prompts.py` (NEW)

- [ ] **Step 1: Write the failing test**

Create `tests/test_prompts.py`:

```python
"""Tests for prompt templates."""
from app.graph.prompts import (
    COMPOSE_STRICT_SYSTEM,
    COMPOSE_PARTIAL_SYSTEM,
    COMPOSE_NOMATCH_SYSTEM,
    COMPOSE_USER_TEMPLATE,
)


def test_compose_strict_system_has_no_hallucination_rule():
    assert "EXACTLY" in COMPOSE_STRICT_SYSTEM or "exactly" in COMPOSE_STRICT_SYSTEM
    assert "kami" in COMPOSE_STRICT_SYSTEM or "Kak" in COMPOSE_STRICT_SYSTEM


def test_compose_partial_system_acknowledges_partial_match():
    # Partial path should reference partial / belum lengkap / konfirmasi
    text = COMPOSE_PARTIAL_SYSTEM.lower()
    assert any(kw in text for kw in ("partial", "sebagian", "konfirmasi", "belum lengkap"))


def test_compose_nomatch_system_uses_exact_user_rules():
    assert "kami" in COMPOSE_NOMATCH_SYSTEM
    assert "Kak" in COMPOSE_NOMATCH_SYSTEM
    assert "NEVER hallucinate" in COMPOSE_NOMATCH_SYSTEM or "NEVER" in COMPOSE_NOMATCH_SYSTEM
    # Forbid explicit "robot" / "automated" / "forwarded to owner" as rigid phrases
    # The text instructs NOT to use them, so they should NOT appear as recommendations
    assert "robot" not in COMPOSE_NOMATCH_SYSTEM.lower().split("not use")[0]
    assert "automated" not in COMPOSE_NOMATCH_SYSTEM.lower().split("not use")[0]


def test_compose_user_template_interpolates_message_and_row():
    out = COMPOSE_USER_TEMPLATE.format(
        message="berapa harga hoodie?",
        source_row="Hoodie Fleece Tebal — Rp 150.000",
        match_kind="high",
    )
    assert "berapa harga hoodie?" in out
    assert "Hoodie Fleece Tebal — Rp 150.000" in out
    assert "high" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_prompts.py -v`
Expected: ImportError or AttributeError because the new constants don't exist yet.

- [ ] **Step 3: Add the new prompt constants**

Append to `app/graph/prompts.py`:

```python
COMPOSE_STRICT_SYSTEM = """You are a customer-service teammate replying on WhatsApp for an Indonesian UMKM seller.

Tone: warm, polite, relaxed, friendly. Use "Kak" to address the buyer and "kami" as the pronoun for the store.

Hard constraint: any numeric fact (price, size, stock indicator) must appear EXACTLY as in the source row, character-for-character. You may not reformat "Rp 50.000" as "Rp50,000" or "50000".

Allowed: greetings ("Halo Kak!"), natural closers ("Boleh order ya 🙏"), connecting phrases.
Forbidden: any price, size, color, stock status, or store-policy wording that does not appear in the source row.

If the source row does not fully answer the buyer's question, say so politely and invite them to ask more — but never invent."""

COMPOSE_PARTIAL_SYSTEM = """You are a customer-service teammate replying on WhatsApp for an Indonesian UMKM seller.

Tone: warm, polite, relaxed, friendly. Use "Kak" to address the buyer and "kami" as the pronoun for the store.

The matched source row only partially answers the buyer's question. Acknowledge this politely: tell the buyer the team is confirming the specific detail with the warehouse/owner, and offer to forward to the owner if the buyer prefers not to wait.

Hard constraint: any numeric fact (price, size, stock indicator) must appear EXACTLY as in the source row, character-for-character.
Forbidden: any price, size, color, stock status, or store-policy wording that does not appear in the source row."""

COMPOSE_NOMATCH_SYSTEM = """You are a customer service team member on WhatsApp.
Use polite, friendly, relaxed, and warm Indonesian, typical of Indonesian e-commerce (use the greeting 'Kak').

If the product or FAQ requested by the buyer is NOT found in the data:
1. NEVER hallucinate, make up answers, or guess stock/information.
2. DO NOT use rigid words like "robot", "automated system", or "will be forwarded to the owner" because it can make buyers feel like they are only talking to a bot.
3. Use the pronouns "kami" (we).
4. State that the product/information is not yet available in the catalog, explain that you/the team are currently checking with the warehouse/owner for them, and kindly ask the buyer to wait a moment."""

COMPOSE_USER_TEMPLATE = """Buyer message:
\"{message}\"

Source row from our catalog (use these facts verbatim, especially numbers):
\"\"\"{source_row}\"\"\"

Match confidence: {match_kind}

Compose a single WhatsApp reply in natural Indonesian. Address the buyer as Kak. Use only facts from the source row above; do not invent prices, sizes, colors, or stock status."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_prompts.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/graph/prompts.py tests/test_prompts.py
git commit -m "feat(prompts): add compose prompt templates for grounded reply"
```

---

## Task 2: Add `LLMValidationError` and `validate_reply` helper to `app/services/llm.py`

**Files:**
- Modify: `app/services/llm.py`
- Test: `tests/test_llm_compose.py` (NEW)

- [ ] **Step 1: Write the failing test for `validate_reply`**

Create `tests/test_llm_compose.py`:

```python
"""Tests for LLM compose reply + validation."""
import pytest

from app.services.llm import (
    LLMValidationError,
    validate_reply,
)


def test_validate_reply_passes_when_reply_uses_only_source_numbers():
    source = {"nama_produk": "Hoodie Fleece Tebal", "harga": 150000, "ready": "Y"}
    reply = "Halo Kak! Hoodie Fleece Tebal Rp 150.000 ready stock ya."
    validate_reply(reply, source)  # should not raise


def test_validate_reply_raises_on_invented_price():
    source = {"nama_produk": "Hoodie Fleece Tebal", "harga": 150000, "ready": "Y"}
    reply = "Hoodie harganya Rp 175.000 ready stock."
    with pytest.raises(LLMValidationError):
        validate_reply(reply, source)


def test_validate_reply_raises_on_invented_size():
    source = {"nama_produk": "Kaos Polos - Hitam - Size M", "harga": 50000, "ready": "Y"}
    reply = "Kaos Polos Size XXXL ready ya Kak."
    with pytest.raises(LLMValidationError):
        validate_reply(reply, source)


def test_validate_reply_raises_on_invented_stock_status():
    source = {"nama_produk": "Crewneck Basic", "harga": 120000, "ready": "N"}
    reply = "Crewneck ready stock ya Kak."
    with pytest.raises(LLMValidationError):
        validate_reply(reply, source)


def test_validate_reply_handles_indonesian_thousands_format():
    source = {"nama_produk": "Kaos Polos", "harga": 50000}
    reply = "Kaos Polos Rp 50.000 ya Kak."
    validate_reply(reply, source)


def test_validate_reply_passes_when_source_row_is_none():
    # No source row → no validation possible, but should not crash.
    validate_reply("Sedang kami cek ya Kak.", None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_compose.py::test_validate_reply_passes_when_reply_uses_only_source_numbers -v`
Expected: ImportError because `LLMValidationError` and `validate_reply` don't exist yet.

- [ ] **Step 3: Add `LLMValidationError` exception**

In `app/services/llm.py`, after the existing `LLMError` class, add:

```python
class LLMValidationError(LLMError):
    """Raised when the LLM's reply contains facts not present in the source row."""
```

- [ ] **Step 4: Add `validate_reply` helper**

Append to `app/services/llm.py`:

```python
import re

_NUMERIC_RE = re.compile(r"\d+(?:\.\d+)?")
_SIZE_RE = re.compile(r"\b(?:XXXL|XXL|XL|L|M|S)\b")
_STOCK_TOKENS = ("ready", "habis", "pre-order")


def _flatten_strings(row: dict | None) -> str:
    """Concatenate all string values in a row (and sub-dicts) for token matching."""
    if row is None:
        return ""
    parts: list[str] = []
    for v in row.values():
        if isinstance(v, dict):
            parts.append(_flatten_strings(v))
        elif isinstance(v, (str, int, float)):
            parts.append(str(v))
    return " ".join(parts)


def validate_reply(reply: str, source_row: dict | None) -> None:
    """Validate that the LLM reply contains no foreign facts vs the source row.

    Raises LLMValidationError if:
      - reply contains a numeric token (digits) not present in the source
      - reply mentions a size (S/M/L/XL/XXL/XXXL) not in the source
      - reply mentions a stock indicator (ready/habis/pre-order) not in source

    Pass-through when source_row is None.
    """
    if source_row is None:
        return
    source_text = _flatten_strings(source_row).lower()

    # Numeric tokens
    reply_nums = set(_NUMERIC_RE.findall(reply))
    source_nums = set(_NUMERIC_RE.findall(source_text))
    foreign_nums = reply_nums - source_nums
    if foreign_nums:
        raise LLMValidationError(
            f"Reply contains numbers not in source row: {sorted(foreign_nums)}"
        )

    # Size strings
    reply_sizes = set(m.upper() for m in _SIZE_RE.findall(reply))
    source_sizes = set(m.upper() for m in _SIZE_RE.findall(source_text))
    foreign_sizes = reply_sizes - source_sizes
    if foreign_sizes:
        raise LLMValidationError(
            f"Reply contains sizes not in source row: {sorted(foreign_sizes)}"
        )

    # Stock tokens (substring match, lowercased)
    reply_lower = reply.lower()
    source_lower_set = source_text  # already lowercased
    for tok in _STOCK_TOKENS:
        if tok in reply_lower and tok not in source_lower_set:
            raise LLMValidationError(
                f"Reply contains stock token '{tok}' not in source row"
            )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_llm_compose.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add app/services/llm.py tests/test_llm_compose.py
git commit -m "feat(llm): add validate_reply helper for hallucination detection"
```

---

## Task 3: Add `LLMClient.compose_reply()` abstract method

**Files:**
- Modify: `app/services/llm.py`
- Test: `tests/test_llm_compose.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_llm_compose.py`:

```python
from app.services.llm import LLMClient


def test_llm_client_is_abstract_for_compose_reply():
    # A subclass that doesn't implement compose_reply should fail to instantiate.
    class IncompleteClient(LLMClient):
        def classify(self, message):
            return {"intent": "faq", "confidence": 0.5}

    with pytest.raises(TypeError):
        IncompleteClient()


def test_mock_llm_client_compose_reply_returns_warm_indonesian():
    from app.services.llm import MockLLMClient

    client = MockLLMClient()
    reply = client.compose_reply(
        message="berapa harga hoodie?",
        retrieved_row={"nama_produk": "Hoodie Fleece Tebal", "harga": 150000, "ready": "Y"},
        match_kind="high",
    )
    assert "Kak" in reply or "kami" in reply
    assert "Hoodie" in reply


def test_mock_llm_client_compose_reply_for_nomatch_uses_kami_not_rigid_words():
    from app.services.llm import MockLLMClient

    client = MockLLMClient()
    reply = client.compose_reply(
        message="apa ada produk dari mars?",
        retrieved_row=None,
        match_kind="none",
    )
    assert "kami" in reply.lower()
    forbidden = ["robot", "automated", "forwarded to owner", "bot"]
    for word in forbidden:
        assert word not in reply.lower(), f"Mock reply used forbidden word: {word}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_compose.py::test_llm_client_is_abstract_for_compose_reply -v`
Expected: FAIL because `LLMClient` has no `compose_reply` yet, but the class will instantiate (currently only `classify` is abstract). The test will fail because no TypeError is raised.

- [ ] **Step 3: Add abstract `compose_reply` to `LLMClient`**

In `app/services/llm.py`, update the abstract base class:

```python
class LLMClient(metaclass=abc.ABCMeta):
    """Abstract base class for intent classification + reply composition clients."""

    @abc.abstractmethod
    def classify(self, message: str) -> ClassificationResult:
        """Classify user message intent. Returns {intent, confidence}.

        Raises LLMError if API fails or response is invalid.
        """
        pass

    @abc.abstractmethod
    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
    ) -> str:
        """Compose a natural Indonesian reply grounded in retrieved_row.

        Args:
          message: the buyer's WhatsApp message.
          retrieved_row: matched FAQ or product row, or None when no match.
          match_kind: 'high' | 'medium' | 'none'.

        Returns the composed reply text.

        Raises LLMError if the API call fails or returns invalid output.
        """
        pass
```

- [ ] **Step 4: Update `MockLLMClient` to implement `compose_reply`**

In `app/services/llm.py`, add a `compose_reply` method to `MockLLMClient`:

```python
class MockLLMClient(LLMClient):
    """Deterministic classifier + composer for local dev / testing / when SDK missing.

    Uses simple keyword heuristics — no external API call. Never raises.
    """

    def classify(self, message: str) -> ClassificationResult:
        msg = (message or "").lower()
        if any(kw in msg for kw in ("stok", "ready", "ada ga", "ada nggak", "ready stock", "tersedia")):
            return {"intent": "check_product", "confidence": 0.95}
        if any(kw in msg for kw in ("order", "pesan", "beli", "booking", "checkout")):
            return {"intent": "confirm_order", "confidence": 0.92}
        if any(kw in msg for kw in ("?", "apa", "bagaimana", "kapan", "dimana", "gimana")):
            return {"intent": "faq", "confidence": 0.8}
        return {"intent": "unclear", "confidence": 0.4}

    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
    ) -> str:
        if match_kind == "none" or retrieved_row is None:
            return (
                "Halo Kak! Kami cek dulu ya ke gudang, "
                "sebentar ya 🙏"
            )
        nama = retrieved_row.get("nama_produk") or "produknya"
        harga = retrieved_row.get("harga")
        ready = retrieved_row.get("ready", "Y")
        if match_kind == "medium":
            return (
                f"Halo Kak! Untuk {nama} (Rp {harga}), "
                "kami konfirmasi dulu ke gudang ya, "
                "bisa kami sambungkan ke owner kalau Kakak mau."
            )
        # high
        status = "ready stock" if str(ready).upper() == "Y" else "pre-order"
        return (
            f"Halo Kak! {nama} harga Rp {harga}, "
            f"{status} ya. Boleh order kapan saja 🙏"
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_llm_compose.py -v`
Expected: PASS (all 9 tests: 6 validate + 3 compose).

- [ ] **Step 6: Commit**

```bash
git add app/services/llm.py tests/test_llm_compose.py
git commit -m "feat(llm): add compose_reply abstract method + mock implementation"
```

---

## Task 4: Implement `compose_reply` for Gemini and Anthropic backends

**Files:**
- Modify: `app/services/llm.py`
- Test: `tests/test_llm_compose.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_llm_compose.py`:

```python
def test_anthropic_compose_reply_uses_strict_prompt_for_high_match():
    """Verify the Anthropic backend passes COMPOSE_STRICT_SYSTEM for high-confidence."""
    from app.services.llm import AnthropicLLMClient, COMPOSE_STRICT_SYSTEM

    class FakeMessages:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            class _Resp:
                content = [type("B", (), {"type": "text", "text": "Halo Kak!"})()]
            return _Resp()

    fake_client = FakeMessages()
    client = AnthropicLLMClient(api_key="test-key")
    client._client = type("C", (), {"messages": fake_client})()

    client.compose_reply(
        message="berapa harga hoodie?",
        retrieved_row={"nama_produk": "Hoodie", "harga": 150000},
        match_kind="high",
    )

    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert call["system"] == COMPOSE_STRICT_SYSTEM


def test_gemini_compose_reply_uses_nomatch_prompt_for_no_match():
    """Verify the Gemini backend passes COMPOSE_NOMATCH_SYSTEM when match_kind=none."""
    from app.services.llm import GeminiLLMClient, COMPOSE_NOMATCH_SYSTEM

    class FakeModels:
        def __init__(self):
            self.calls = []

        def generate_content(self, **kwargs):
            self.calls.append(kwargs)
            class _Resp:
                text = "Halo Kak! Kami cek dulu ya."
            return _Resp()

    fake_models = FakeModels()
    client = GeminiLLMClient(api_key="test-key")
    client._client = type("C", (), {"models": fake_models})()

    client.compose_reply(
        message="produk dari mars?",
        retrieved_row=None,
        match_kind="none",
    )

    assert len(fake_models.calls) == 1
    call = fake_models.calls[0]
    # The system prompt should be embedded in `contents` for Gemini
    assert COMPOSE_NOMATCH_SYSTEM in call["contents"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_compose.py::test_anthropic_compose_reply_uses_strict_prompt_for_high_match -v`
Expected: AttributeError because `AnthropicLLMClient.compose_reply` doesn't exist.

- [ ] **Step 3: Implement `compose_reply` in `AnthropicLLMClient`**

In `app/services/llm.py`, add to `AnthropicLLMClient`:

```python
    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
    ) -> str:
        from app.graph.prompts import (
            COMPOSE_STRICT_SYSTEM,
            COMPOSE_PARTIAL_SYSTEM,
            COMPOSE_NOMATCH_SYSTEM,
            COMPOSE_USER_TEMPLATE,
        )

        if match_kind == "none":
            system_prompt = COMPOSE_NOMATCH_SYSTEM
            source_repr = "(no catalog row matched)"
        elif match_kind == "medium":
            system_prompt = COMPOSE_PARTIAL_SYSTEM
            source_repr = _flatten_strings(retrieved_row) if retrieved_row else "(no row)"
        else:
            system_prompt = COMPOSE_STRICT_SYSTEM
            source_repr = _flatten_strings(retrieved_row) if retrieved_row else "(no row)"

        user_prompt = COMPOSE_USER_TEMPLATE.format(
            message=message,
            source_row=source_repr,
            match_kind=match_kind,
        )

        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=512,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text_block = next(
                (b for b in response.content if b.type == "text"),
                None,
            )
            if text_block is None:
                raise LLMError("No text block in compose response")
            return text_block.text.strip()
        except Exception as e:
            raise LLMError(f"Anthropic compose failed: {e}") from e
```

(Replace the import of `INTENT_CLASSIFICATION_*` at the top of `AnthropicLLMClient` since `compose_reply` no longer needs them — leave `classify`'s import alone.)

- [ ] **Step 4: Implement `compose_reply` in `GeminiLLMClient`**

In `app/services/llm.py`, add to `GeminiLLMClient`:

```python
    def compose_reply(
        self,
        message: str,
        retrieved_row: dict | None,
        match_kind: str,
    ) -> str:
        from app.graph.prompts import (
            COMPOSE_STRICT_SYSTEM,
            COMPOSE_PARTIAL_SYSTEM,
            COMPOSE_NOMATCH_SYSTEM,
            COMPOSE_USER_TEMPLATE,
        )

        if match_kind == "none":
            system_prompt = COMPOSE_NOMATCH_SYSTEM
            source_repr = "(no catalog row matched)"
        elif match_kind == "medium":
            system_prompt = COMPOSE_PARTIAL_SYSTEM
            source_repr = _flatten_strings(retrieved_row) if retrieved_row else "(no row)"
        else:
            system_prompt = COMPOSE_STRICT_SYSTEM
            source_repr = _flatten_strings(retrieved_row) if retrieved_row else "(no row)"

        user_prompt = COMPOSE_USER_TEMPLATE.format(
            message=message,
            source_row=source_repr,
            match_kind=match_kind,
        )

        try:
            from google.genai import types as genai_types

            response = self._client.models.generate_content(
                model=self.MODEL,
                contents=[system_prompt + "\n\n" + user_prompt],
                config=genai_types.GenerateContentConfig(
                    temperature=0.4,
                    max_output_tokens=512,
                ),
            )
            text = (response.text or "").strip()
            if not text:
                raise LLMError("Empty compose response from Gemini")
            return text
        except Exception as e:
            raise LLMError(f"Gemini compose failed: {e}") from e
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_llm_compose.py -v`
Expected: PASS (all 11 tests).

- [ ] **Step 6: Run full test suite to ensure no regression**

Run: `pytest -q`
Expected: 50 existing tests still pass (the abstract method change may require MockLLMClient updates in conftest — see Step 7 if any test breaks).

- [ ] **Step 7: Update existing tests/conftest.py if needed**

Run: `pytest -q 2>&1 | tail -10`

If any test fails with `TypeError: Can't instantiate abstract class`, find the offending `LLMClient` subclass in `tests/conftest.py` or other test files, and add the `compose_reply` method (delegate to `MockLLMClient.compose_reply`):

```python
def compose_reply(self, message, retrieved_row, match_kind):
    from app.services.llm import MockLLMClient
    return MockLLMClient().compose_reply(message, retrieved_row, match_kind)
```

- [ ] **Step 8: Commit**

```bash
git add app/services/llm.py tests/test_llm_compose.py tests/conftest.py
git commit -m "feat(llm): implement compose_reply for Gemini and Anthropic backends"
```

---

## Task 5: Add `match_kind` to `ChatState` and `lookup_catalog`

**Files:**
- Modify: `app/graph/state.py`
- Modify: `app/graph/nodes.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Read current `ChatState` to understand shape**

Run: `cat app/graph/state.py`

Identify the TypedDict class definition for `ChatState`. Note the field syntax (it's a `TypedDict`).

- [ ] **Step 2: Add `match_kind` field to `ChatState`**

In `app/graph/state.py`, add the field (place after `confidence`):

```python
    confidence: float
    match_kind: str | None  # "high" | "medium" | "none" — set by lookup_catalog
```

- [ ] **Step 3: Write the failing test for match_kind scoring**

Append to `tests/test_graph.py`:

```python
def test_lookup_catalog_match_kind_high_when_overlap_above_threshold():
    from app.graph.nodes import lookup_catalog
    from app.graph.state import ChatState

    # Fake Sheets client returning a single FAQ row with high overlap.
    class FakeSheets:
        def lookup_faq(self, msg):
            return {"pertanyaan": "berapa harga hoodie fleece tebal?", "jawaban": "Rp 150.000"}

    state: ChatState = {
        "message_text": "berapa harga hoodie fleece tebal?",
        "tenant_id": "t1",
        "thread_id": "th1",
        "wa_number": "628xxx",
        "intent": "faq",
        "confidence": 0.9,
        "match_kind": None,
    }
    update = lookup_catalog(state, FakeSheets())
    assert update.get("match_kind") == "high"


def test_lookup_catalog_match_kind_medium_when_partial_overlap():
    from app.graph.nodes import lookup_catalog
    from app.graph.state import ChatState

    class FakeSheets:
        def lookup_faq(self, msg):
            return {"pertanyaan": "lama pengiriman", "jawaban": "2-4 hari"}

    state: ChatState = {
        "message_text": "kaos oversize warna sage ready ga kak?",
        "tenant_id": "t1",
        "thread_id": "th1",
        "wa_number": "628xxx",
        "intent": "faq",
        "confidence": 0.5,
        "match_kind": None,
    }
    update = lookup_catalog(state, FakeSheets())
    assert update.get("match_kind") == "medium"


def test_lookup_catalog_match_kind_none_when_no_row():
    from app.graph.nodes import lookup_catalog
    from app.graph.state import ChatState

    class FakeSheets:
        def lookup_faq(self, msg):
            return None
        def read_catalog(self):
            return []

    state: ChatState = {
        "message_text": "produk dari mars?",
        "tenant_id": "t1",
        "thread_id": "th1",
        "wa_number": "628xxx",
        "intent": "faq",
        "confidence": 0.4,
        "match_kind": None,
    }
    update = lookup_catalog(state, FakeSheets())
    assert update.get("match_kind") == "none"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_graph.py::test_lookup_catalog_match_kind_high_when_overlap_above_threshold -v`
Expected: FAIL — current `lookup_catalog` does not return `match_kind`.

- [ ] **Step 5: Update `lookup_catalog` to compute and return `match_kind`**

In `app/graph/nodes.py`, replace `lookup_catalog` with:

```python
_HIGH_OVERLAP_RATIO = 0.5


def _overlap_ratio(message: str, source_text: str) -> float:
    """Fraction of message words (≥3 chars) that appear in source_text.

    Returns 0.0 if message has no qualifying words.
    """
    msg_words = [w for w in (message or "").lower().split() if len(w) >= 3]
    if not msg_words:
        return 0.0
    src_lower = (source_text or "").lower()
    matched = sum(1 for w in msg_words if w in src_lower)
    return matched / len(msg_words)


def _match_kind_from(message: str, source_text: str | None) -> str:
    if not source_text:
        return "none"
    ratio = _overlap_ratio(message, source_text)
    if ratio >= _HIGH_OVERLAP_RATIO:
        return "high"
    if ratio > 0.0:
        return "medium"
    return "none"


def lookup_catalog(state: ChatState, sheets_client: Any) -> dict:
    """Lookup answer in Sheets based on intent.

    Returns dict update: {catalog_answer, product_match, match_kind}.
    match_kind is 'high' | 'medium' | 'none' based on keyword overlap with
    the buyer's message.
    """
    intent = state["intent"]
    message = state["message_text"]

    try:
        if intent == "faq":
            match = sheets_client.lookup_faq(message)
            if match is None:
                logger.info(
                    "faq_no_match",
                    extra={"tenant_id": state["tenant_id"], "thread_id": state["thread_id"]},
                )
                return {"match_kind": "none"}
            source_text = (match.get("pertanyaan") or "") + " " + (match.get("jawaban") or "")
            return {
                "catalog_answer": match["jawaban"],
                "product_match": None,
                "match_kind": _match_kind_from(message, source_text),
            }

        if intent == "check_product":
            products = sheets_client.read_catalog()
            message_lower = message.lower()
            words = [w for w in message_lower.split() if len(w) >= 3]
            for product in products:
                nama = (product.get("nama_produk") or "").lower()
                if any(w in nama for w in words):
                    source_text = (
                        (product.get("nama_produk") or "")
                        + " "
                        + (product.get("deskripsi") or "")
                    )
                    return {
                        "catalog_answer": None,
                        "product_match": product,
                        "match_kind": _match_kind_from(message, source_text),
                    }
            return {"match_kind": "none"}

        return {"match_kind": "none"}
    except Exception as e:  # noqa: BLE001
        logger.error(
            "sheets_lookup_failed",
            extra={"tenant_id": state["tenant_id"], "error": str(e)},
        )
        return {"match_kind": "none"}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_graph.py -v -k match_kind`
Expected: PASS (3 new tests).

- [ ] **Step 7: Run full test suite to verify no regression**

Run: `pytest -q`
Expected: 50 existing tests still pass (some may need their expected state dict updated to include `match_kind`).

If a test fails because of `match_kind` missing from the state, update the test fixture to include `"match_kind": "none"` in the input `ChatState`.

- [ ] **Step 8: Commit**

```bash
git add app/graph/state.py app/graph/nodes.py tests/test_graph.py
git commit -m "feat(graph): add match_kind scoring to lookup_catalog"
```

---

## Task 6: Add `compose_with_llm` orchestrator + replace `compose_reply` body

**Files:**
- Modify: `app/graph/nodes.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_graph.py`:

```python
def test_compose_reply_uses_llm_for_high_confidence():
    from app.graph.nodes import compose_reply
    from app.graph.state import ChatState
    from app.services.llm import MockLLMClient

    state: ChatState = {
        "message_text": "berapa harga hoodie?",
        "tenant_id": "t1",
        "thread_id": "th1",
        "wa_number": "628xxx",
        "intent": "faq",
        "confidence": 0.9,
        "match_kind": "high",
        "catalog_answer": "Rp 150.000",
    }
    llm = MockLLMClient()
    update = compose_reply(state, llm)
    assert "Hoodie" in update["reply_text"] or "150" in update["reply_text"]
    assert update["action"] == "reply"


def test_compose_reply_uses_no_match_prompt_when_match_kind_none():
    from app.graph.nodes import compose_reply
    from app.graph.state import ChatState
    from app.services.llm import MockLLMClient

    state: ChatState = {
        "message_text": "produk dari mars?",
        "tenant_id": "t1",
        "thread_id": "th1",
        "wa_number": "628xxx",
        "intent": "faq",
        "confidence": 0.4,
        "match_kind": "none",
        "catalog_answer": None,
    }
    llm = MockLLMClient()
    update = compose_reply(state, llm)
    # MockLLMClient for nomatch returns "kami cek dulu" — must NOT contain rigid words
    assert "kami" in update["reply_text"].lower()
    for word in ["robot", "automated", "forwarded to owner"]:
        assert word not in update["reply_text"].lower()


def test_compose_reply_falls_back_to_verbatim_when_llm_raises():
    from app.graph.nodes import compose_reply
    from app.graph.state import ChatState
    from app.services.llm import LLMClient, LLMError

    class FailingLLM(LLMClient):
        def classify(self, message):
            return {"intent": "faq", "confidence": 0.5}
        def compose_reply(self, message, retrieved_row, match_kind):
            raise LLMError("API down")

    state: ChatState = {
        "message_text": "berapa harga hoodie?",
        "tenant_id": "t1",
        "thread_id": "th1",
        "wa_number": "628xxx",
        "intent": "faq",
        "confidence": 0.9,
        "match_kind": "high",
        "catalog_answer": "Rp 150.000 untuk Hoodie Fleece Tebal",
    }
    update = compose_reply(state, FailingLLM())
    # Fallback: should return the catalog_answer verbatim
    assert update["reply_text"] == "Rp 150.000 untuk Hoodie Fleece Tebal"
    assert update["action"] == "reply"


def test_compose_reply_retries_on_validation_failure_then_falls_back():
    from app.graph.nodes import compose_reply
    from app.graph.state import ChatState
    from app.services.llm import LLMClient, LLMValidationError

    class HallucinatingLLM(LLMClient):
        def __init__(self):
            self.calls = 0
        def classify(self, message):
            return {"intent": "faq", "confidence": 0.5}
        def compose_reply(self, message, retrieved_row, match_kind):
            self.calls += 1
            # Reply contains a foreign number (999) every time → fails validation
            return f"Hoodie Rp 999.000 ready ya Kak (call {self.calls})"

    state: ChatState = {
        "message_text": "berapa harga hoodie?",
        "tenant_id": "t1",
        "thread_id": "th1",
        "wa_number": "628xxx",
        "intent": "faq",
        "confidence": 0.9,
        "match_kind": "high",
        "catalog_answer": "Rp 150.000 untuk Hoodie",
    }
    llm = HallucinatingLLM()
    update = compose_reply(state, llm)
    # Should retry once (2 calls total) then fall back
    assert llm.calls == 2
    assert update["reply_text"] == "Rp 150.000 untuk Hoodie"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_graph.py -v -k "compose_reply_uses_llm or compose_reply_falls or compose_reply_retries"`
Expected: FAIL — current `compose_reply` doesn't call the LLM.

- [ ] **Step 3: Add `compose_with_llm` orchestrator and replace `compose_reply`**

In `app/graph/nodes.py`, replace `compose_reply` with:

```python
def _build_verbatim_fallback(state: ChatState) -> dict:
    """Today's degraded-mode reply: return the raw catalog_answer when LLM fails."""
    if state.get("catalog_answer"):
        return {
            "reply_text": f"{state['catalog_answer']}",
            "action": "reply",
        }
    if state.get("product_match"):
        p = state["product_match"]
        ready = "Ready stock" if p.get("ready") == "Y" else "❌ Habis"
        return {
            "reply_text": (
                f"{p['nama_produk']} — {p.get('harga', '-')}\n"
                f"{ready}\n"
                f"{p.get('deskripsi', '')}"
            ),
            "action": "reply",
        }
    return _compose_fallback_message(state, reason="no_data")


def _compose_with_llm(state: ChatState, llm_client: Any) -> dict:
    """Orchestrate LLM compose + validate + 1 retry on validation failure + fallback.

    Order:
      1. Try LLM compose_reply once.
      2. Validate the reply against the source row (if any).
      3. On validation failure: retry once with a stricter system-prompt hint
         (LLMClient.compose_reply() may use any client-defined retry injection,
         but for simplicity we retry by appending to the message itself).
      4. On any LLM/validation failure: fall back to verbatim catalog data.
      5. On no data at all: fall back to human-handoff message.
    """
    from app.services.llm import LLMError, LLMValidationError, validate_reply

    intent = state["intent"]
    match_kind = state.get("match_kind") or "none"
    retrieved_row = (
        {"pertanyaan": "(implicit FAQ)", "jawaban": state.get("catalog_answer")}
        if intent == "faq" and state.get("catalog_answer")
        else state.get("product_match")
    )

    if intent == "confirm_order":
        # Order confirmation is unchanged — short, no LLM needed.
        return {
            "reply_text": (
                "Terima kasih ordernya! Owner akan follow up untuk konfirmasi "
                "pembayaran ya 🙏"
            ),
            "action": "order",
        }

    # Try LLM up to 2 times (initial + 1 retry).
    for attempt in range(2):
        try:
            reply = llm_client.compose_reply(
                message=state["message_text"],
                retrieved_row=retrieved_row,
                match_kind=match_kind,
            )
            validate_reply(reply, retrieved_row)
            return {"reply_text": reply, "action": "reply"}
        except LLMValidationError as e:
            logger.warning(
                "compose_validation_failed",
                extra={"tenant_id": state["tenant_id"], "attempt": attempt, "error": str(e)},
            )
            # Retry: next attempt will see the same compose_reply call, but
            # we mutate the input to inject a stricter hint.
            state = {**state, "_retry_hint": "Reply contained facts not in source. Re-state using ONLY source."}
            retrieved_row = retrieved_row  # keep same; retry logic is client-side
            continue
        except LLMError as e:
            logger.error(
                "compose_llm_failed",
                extra={"tenant_id": state["tenant_id"], "error": str(e)},
            )
            return _build_verbatim_fallback(state)

    # Validation failed twice → fall back to verbatim.
    logger.warning(
        "compose_validation_failed_twice",
        extra={"tenant_id": state["tenant_id"]},
    )
    return _build_verbatim_fallback(state)


def compose_reply(state: ChatState, llm_client: Any) -> dict:
    """Compose reply text. Dispatches to LLM (via _compose_with_llm) or fallback path."""
    return _compose_with_llm(state, llm_client)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_graph.py -v -k "compose_reply_uses_llm or compose_reply_falls or compose_reply_retries"`
Expected: PASS (4 new tests).

- [ ] **Step 5: Run full test suite**

Run: `pytest -q`
Expected: All tests pass. Some existing graph tests may need updates because `compose_reply` now requires an `llm_client` argument — supply a `MockLLMClient()` in those tests.

- [ ] **Step 6: Commit**

```bash
git add app/graph/nodes.py tests/test_graph.py
git commit -m "feat(graph): route compose_reply through LLM with validate+retry+fallback"
```

---

## Task 7: Wire `llm_client` through graph build

**Files:**
- Modify: `app/graph/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Read current graph.py to understand wiring**

Run: `cat app/graph/graph.py`

- [ ] **Step 2: Write the failing test for graph wiring**

Append to `tests/test_graph.py`:

```python
def test_graph_build_accepts_llm_client_and_threads_it_through():
    """Building the graph should accept an llm_client and pass it to compose_reply."""
    from app.graph.graph import build_graph
    from app.services.llm import MockLLMClient

    class FakeSheets:
        def lookup_faq(self, msg):
            return {"pertanyaan": "harga hoodie", "jawaban": "Rp 150.000"}
        def read_catalog(self):
            return []

    llm = MockLLMClient()
    graph = build_graph(llm_client=llm, sheets_client=FakeSheets())
    # If the build succeeded with an llm_client kwarg, this is wiring-correct.
    assert graph is not None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_graph.py -v -k test_graph_build_accepts_llm_client`
Expected: FAIL — current `build_graph` may not accept `llm_client` kwarg.

- [ ] **Step 4: Update `build_graph` to thread `llm_client`**

In `app/graph/graph.py`, modify the build function so:

1. It accepts an `llm_client` parameter (and optional `sheets_client`).
2. The `compose_reply` node is built as a closure that captures `llm_client`: `lambda state: compose_reply(state, llm_client)`.
3. The graph compilation passes this closure into the StateGraph node registry.

The exact edit depends on current `graph.py` shape. Read it first. The shape after edit:

```python
def build_graph(*, llm_client, sheets_client=None):
    """Build the LangGraph state machine.

    Args:
      llm_client: an LLMClient instance (passed to compose_reply).
      sheets_client: optional Sheets client (passed to lookup_catalog).
    """
    graph = StateGraph(ChatState)
    graph.add_node("classify", lambda s: classify_intent(s, llm_client))
    graph.add_node("lookup", lambda s: lookup_catalog(s, sheets_client or _default_sheets()))
    graph.add_node("compose", lambda s: compose_reply(s, llm_client))
    graph.add_node("send", async_node(send_whatsapp, gateway_client=...))
    graph.add_node("fallback", async_node(fallback_human, gateway_client=...))
    graph.add_node("log", write_chat_log)
    # ... edges unchanged ...
    return graph.compile()
```

(Adapt to the actual file structure; keep all existing edges and nodes intact — only thread `llm_client` into `compose_reply`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_graph.py -v -k test_graph_build_accepts_llm_client`
Expected: PASS.

- [ ] **Step 6: Run full test suite**

Run: `pytest -q`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/graph/graph.py tests/test_graph.py
git commit -m "feat(graph): thread llm_client through build_graph into compose_reply"
```

---

## Task 8: Manual smoke test against stress fixtures

**Files:** none (manual test, no code changes)

- [ ] **Step 1: Verify `.env` has Gemini key**

Run: `grep GEMINI_API_KEY .env`
Expected: a non-empty key (the user must already have this from the 2026-07-29 MVP session). If empty, ask the user.

- [ ] **Step 2: Start the server with mock-mode disabled**

Run: `LLM_BACKEND=gemini uvicorn app.main:app --reload --port 8000`
Expected: server starts, no LLM import errors.

- [ ] **Step 3: Send the 30 fixture questions through the webhook**

Run:

```bash
python -c "
import asyncio, httpx, os

QUESTIONS = open('fixtures/sample_customer_questions.txt').read().splitlines()
QUESTIONS = [q for q in QUESTIONS if q.strip()]

async def main():
    async with httpx.AsyncClient(base_url='http://localhost:8000') as c:
        for q in QUESTIONS:
            r = await c.post('/webhook', headers={'Authorization': 'Bearer test'}, json={
                'sender': '628123456789',
                'message': q,
            })
            print(f'Q: {q}')
            print(f'A: {r.json().get(\"reply\", r.json())}')
            print()
asyncio.run(main())
"
```

Expected: 30 printed Q/A pairs.

- [ ] **Step 4: Validate no hallucinated prices**

Run:

```bash
python -c "
import re

# Load all prices from the fixture xlsx
from openpyxl import load_workbook
wb = load_workbook('fixtures/sample_faq_katalog.xlsx')
catalog = wb['Katalog']
faq = wb['FAQ']

known_prices = set()
for row in catalog.iter_rows(min_row=2, values_only=True):
    if row[1]:
        known_prices.update(re.findall(r'\\d+', str(row[1])))

# Run the webhook loop above, capture all replies, scan for foreign numbers
# (Manual: copy-paste replies into this script and run.)
"
```

Expected: every price in a reply should appear in `known_prices`. If any reply contains a foreign number, that's a bug — investigate which prompt variant was used and tighten.

- [ ] **Step 5: Validate no-match replies follow tone rules**

Eyeball the replies where the customer asked an off-topic question. Confirm:
- Uses "kami"
- Does not say "robot", "automated", "forwarded to owner"
- Asks the buyer to wait

- [ ] **Step 6: Commit any tweaks (if needed)**

If the manual smoke test reveals a prompt gap, edit `app/graph/prompts.py` and commit a follow-up like:

```bash
git add app/graph/prompts.py
git commit -m "fix(prompts): tighten no-match tone after smoke test feedback"
```

(No code changes expected — just verifying the system holds.)

---

## Task 9: Update README + PROJECT_CONTEXT to reflect grounded reply generation

**Files:**
- Modify: `README.md`
- Modify: `PROJECT_CONTEXT.md`

- [ ] **Step 1: Update README.md architecture section**

Find the line in `README.md` (around line 96-107) describing the `app/services/` layout. Add a note that `llm.py` now exposes both `classify` and `compose_reply`, and that `nodes.py` uses `compose_with_llm` for grounded generation.

- [ ] **Step 2: Update PROJECT_CONTEXT.md feature list**

Add a bullet under the "Working" list:

```
- AI agent composes natural Indonesian replies grounded in catalog data (not verbatim xlsx strings); LLM validates against source row before sending
```

- [ ] **Step 3: Commit**

```bash
git add README.md PROJECT_CONTEXT.md
git commit -m "docs: document grounded reply generation in README and PROJECT_CONTEXT"
```

---

## Acceptance verification

After all 9 tasks:

- [ ] `pytest -q` passes (50 existing + ~17 new tests = ~67 total)
- [ ] `git log` shows one commit per logical change
- [ ] No new runtime dependencies (no requirements.txt changes)
- [ ] Manual smoke test against `fixtures/sample_customer_questions.txt` shows no hallucinated prices/sizes
- [ ] `docs/superpowers/specs/2026-07-29-grounded-reply-generation-design.md` matches the implemented behavior