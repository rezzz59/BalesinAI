# Multi-Signal Emitter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the intent classifier to emit `has_complaint_signal` + `sentiment` alongside `intent` + `confidence`, and use those signals to (a) route complaint-bearing messages to the human fallback path and (b) enrich the owner's fallback payload with the sentiment so they can prioritize.

**Architecture:** One additional structured-output field set from the existing `classify()` LLM call. State schema gets two optional fields. Routing logic ORs `has_complaint_signal` into the existing fallback trigger. Owner payload gets one new line. No new LLM calls, no new nodes.

**Tech Stack:** Python 3.10, LangGraph, Anthropic Claude API, Google Gemini API (new google-genai SDK), pytest.

**Design Spec:** `docs/superpowers/specs/2026-07-30-multi-signal-emitter-design.md`

---

## File Structure

This change is small and contained. No file splits needed. Existing patterns respected: the `app/graph/state.py` + `app/graph/prompts.py` + `app/services/llm.py` + `app/graph/nodes.py` quartet is already organized by responsibility, and we touch each file only where its single responsibility requires.

| File | Change | Why |
|------|--------|-----|
| `app/graph/state.py` | Add 2 fields to `ChatState` | State schema needs to carry new signals |
| `app/graph/prompts.py` | Extend `INTENT_CLASSIFICATION_SYSTEM` | Prompt must instruct LLM to emit new fields |
| `app/services/llm.py` | Extend `AnthropicLLMClient.classify`, `GeminiLLMClient.classify`, `MockLLMClient.classify` | All three classifier backends must produce the new shape |
| `app/graph/nodes.py` | Pass through new fields in `classify_intent`; include sentiment in `fallback_human` owner payload | Node glue + owner message |
| `app/graph/graph.py` | OR `has_complaint_signal` into `should_fallback` | Routing logic |
| `tests/test_classify.py` | Add complaint/sentiment tests | Coverage for new node behavior |
| `tests/test_graph.py` | Add routing tests for complaint signal | Coverage for new routing |
| `tests/test_fallback.py` | Add owner payload test | Coverage for enriched message |
| `tests/test_llm.py` | Add LLM client coverage for new fields | Coverage per backend |

---

## Task 1: Extend ChatState with new signal fields

**Files:**
- Modify: `app/graph/state.py:1-31`

- [ ] **Step 1: Edit state.py to add the two new fields**

Add to `app/graph/state.py`:

```python
"""LangGraph state schema."""
from datetime import datetime
from typing import Literal, TypedDict

Action = Literal["reply", "fallback", "order", "error"]
Intent = Literal["faq", "check_product", "confirm_order", "unclear"]
Sentiment = Literal["neutral", "negative", "positive"]


class ChatState(TypedDict, total=False):
    # Input
    tenant_id: str
    wa_number: str
    thread_id: str
    message_text: str
    timestamp: datetime

    # Classify output
    intent: Intent
    confidence: float
    has_complaint_signal: bool
    sentiment: Sentiment

    # Lookup output
    catalog_answer: str | None
    product_match: dict | None
    match_kind: str | None  # "high" | "medium" | "none" — set by lookup_catalog

    # Compose output
    reply_text: str

    # Final action
    action: Action
    fallback_reason: str | None
```

The two new fields `has_complaint_signal` and `sentiment` are added to the "Classify output" block. They follow the existing pattern of `intent` and `confidence` (also `total=False`, optional in state).

- [ ] **Step 2: Verify state.py still parses**

Run: `python -c "from app.graph.state import ChatState; print('OK')"`
Expected: prints `OK`, no ImportError.

- [ ] **Step 3: Commit**

```bash
git add app/graph/state.py
git commit -m "feat(state): add has_complaint_signal + sentiment fields"
```

---

## Task 2: Update prompts.py to instruct LLM on new fields

**Files:**
- Modify: `app/graph/prompts.py:1-18`

- [ ] **Step 1: Replace INTENT_CLASSIFICATION_SYSTEM**

Replace `INTENT_CLASSIFICATION_SYSTEM` in `app/graph/prompts.py` with:

```python
INTENT_CLASSIFICATION_SYSTEM = """You are an intent classifier for a WhatsApp customer service bot for an Indonesian UMKM seller.

Classify the buyer's message into ONE of these intents:
- "faq": general questions about price, shipping, store info, hours, payment methods, etc.
- "check_product": buyer asks about a specific product (stock, color, size, variant)
- "confirm_order": buyer wants to place or confirm an order
- "unclear": message is gibberish, too short, or off-topic

In addition, you MUST report two extra signals:

1. "has_complaint_signal" (boolean):
   Set to TRUE if the buyer is expressing dissatisfaction, requesting a return/refund,
   describing a defect, or reporting that something didn't meet their expectations.
   Examples of TRUE:
     - "kekecilan min, nggak sesuai"
     - "harga kemahalan"
     - "warna nggak sesuai foto"
     - "udah 3 hari nggak sampe"
     - "saya mau refund"
     - "barang rusak"
     - "saya kecewa"
   Examples of FALSE:
     - "berapa harga kaos?" (legitimate question)
     - "apakah ready stock size L?" (legitimate question)
     - "harga kok 50rb ya?" (asking for info, no complaint)
     - "nggak ada masalah, cuma mau tanya" (explicit denial)

2. "sentiment" (one of "neutral", "negative", "positive"):
   Reflect the buyer's emotional tone overall.
   - "negative" if the buyer is upset, angry, disappointed, or frustrated.
   - "positive" if the buyer is happy, thanking, or praising.
   - "neutral" if there's no emotional charge (most questions count here).

Note: a legitimate-sounding question can still carry a complaint signal (e.g., "harga kemahalan"
is both a faq and a complaint). Report both signals independently — they are NOT mutually exclusive
with intent.

Respond ONLY with a JSON object in this exact format:
{"intent": "<one of the four>", "confidence": <float 0.0-1.0>, "has_complaint_signal": <bool>, "sentiment": "<neutral|negative|positive>"}

Confidence reflects how certain you are about the intent. If the message is ambiguous, set confidence < 0.6."""
```

`INTENT_CLASSIFICATION_USER` is unchanged.

- [ ] **Step 2: Verify prompts.py still parses**

Run: `python -c "from app.graph.prompts import INTENT_CLASSIFICATION_SYSTEM; print('OK')"`
Expected: prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add app/graph/prompts.py
git commit -m "feat(prompts): instruct classifier to emit complaint + sentiment signals"
```

---

## Task 3: Extend MockLLMClient with the new fields

**Files:**
- Modify: `app/services/llm.py:52-76` (`MockLLMClient`)

- [ ] **Step 1: Replace MockLLMClient.classify**

Replace the `MockLLMClient.classify` method in `app/services/llm.py` with:

```python
    def classify(self, message: str) -> ClassificationResult:
        msg = (message or "").lower()
        has_complaint = self._has_complaint_signal(msg)
        sentiment = "negative" if has_complaint else "neutral"
        if any(kw in msg for kw in ("stok", "ready", "ada ga", "ada nggak", "ready stock", "tersedia")):
            return {"intent": "check_product", "confidence": 0.95,
                    "has_complaint_signal": has_complaint, "sentiment": sentiment}
        if any(kw in msg for kw in ("order", "pesan", "beli", "booking", "checkout")):
            return {"intent": "confirm_order", "confidence": 0.92,
                    "has_complaint_signal": has_complaint, "sentiment": sentiment}
        if any(kw in msg for kw in ("?", "apa", "bagaimana", "kapan", "dimana", "gimana")):
            return {"intent": "faq", "confidence": 0.8,
                    "has_complaint_signal": has_complaint, "sentiment": sentiment}
        return {"intent": "unclear", "confidence": 0.4,
                "has_complaint_signal": has_complaint, "sentiment": sentiment}

    @staticmethod
    def _has_complaint_signal(msg: str) -> bool:
        """Heuristic complaint detection for dev/test. Real backend uses LLM.

        Only used by MockLLMClient — Anthropic and Gemini clients emit this
        signal from the structured-output prompt.
        """
        keywords = (
            "kekecilan", "kemasihan", "kemasihan", "refund", "komplain",
            "rusak", "salah", "kembalian", "balikin", "balik",
            "tidak sesuai", "nggak sesuai", "ga sesuai", "kecewa",
            "kemahalan", "mahal banget", "ganti", "tukar",
            "belum sampe", "belum sampai", "lama banget", "lama sekali",
        )
        return any(kw in msg for kw in keywords)
```

Keep `compose_reply` unchanged.

- [ ] **Step 2: Verify MockLLMClient returns new fields**

Run: `python -c "from app.services.llm import MockLLMClient; c = MockLLMClient(); print(c.classify('Berapa harga kaos?')); print(c.classify('kekecilan min'))"`
Expected:
```
{'intent': 'faq', 'confidence': 0.8, 'has_complaint_signal': False, 'sentiment': 'neutral'}
{'intent': 'faq', 'confidence': 0.8, 'has_complaint_signal': True, 'sentiment': 'negative'}
```

- [ ] **Step 3: Run existing tests to confirm no regressions**

Run: `python -m pytest tests/test_llm.py tests/test_classify.py -q`
Expected: all pass. (Mock defaults to complaint=False so the only change is two new keys appearing in the dict, which existing tests ignore.)

- [ ] **Step 4: Commit**

```bash
git add app/services/llm.py
git commit -m "feat(llm): MockLLMClient emits complaint + sentiment"
```

---

## Task 4: Extend AnthropicLLMClient.classify to emit new fields

**Files:**
- Modify: `app/services/llm.py:96-131` (`AnthropicLLMClient.classify`)

- [ ] **Step 1: Add new constants near top of AnthropicLLMClient**

Add these as class-level constants on `AnthropicLLMClient`:

```python
    VALID_SENTIMENTS = {"neutral", "negative", "positive"}
```

(Place inside the class body, right after the existing `MODEL = "claude-haiku-4-5"` line.)

- [ ] **Step 2: Replace AnthropicLLMClient.classify with the extended version**

Replace the method:

```python
    def classify(self, message: str) -> ClassificationResult:
        """Classify user message intent + complaint + sentiment."""
        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=128,
                system=INTENT_CLASSIFICATION_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": INTENT_CLASSIFICATION_USER.format(message=message),
                    }
                ],
            )

            text_block = next(
                (b for b in response.content if b.type == "text"),
                None,
            )
            if text_block is None:
                raise LLMError("No text block in response")

            result = json.loads(text_block.text)

            intent = result.get("intent")
            confidence = result.get("confidence")
            has_complaint_signal = result.get("has_complaint_signal", False)
            sentiment = result.get("sentiment", "neutral")

            if intent not in VALID_INTENTS:
                raise LLMError(f"Invalid intent from LLM: {intent}")
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                raise LLMError(f"Invalid confidence from LLM: {confidence}")
            if not isinstance(has_complaint_signal, bool):
                raise LLMError(f"Invalid has_complaint_signal from LLM: {has_complaint_signal}")
            if sentiment not in self.VALID_SENTIMENTS:
                raise LLMError(f"Invalid sentiment from LLM: {sentiment}")

            return {
                "intent": intent,
                "confidence": float(confidence),
                "has_complaint_signal": has_complaint_signal,
                "sentiment": sentiment,
            }

        except json.JSONDecodeError as e:
            raise LLMError(f"Invalid JSON from LLM: {e}") from e
```

- [ ] **Step 3: Verify AnthropicLLMClient imports still parse**

Run: `python -c "from app.services.llm import AnthropicLLMClient, VALID_INTENTS; print(VALID_INTENTS); print(AnthropicLLMClient.VALID_SENTIMENTS)"`
Expected: prints `{'faq', 'check_product', 'confirm_order', 'unclear'}` and `{'neutral', 'negative', 'positive'}`.

- [ ] **Step 4: Commit**

```bash
git add app/services/llm.py
git commit -m "feat(llm): AnthropicLLMClient validates + returns complaint + sentiment"
```

---

## Task 5: Extend GeminiLLMClient.classify with structured schema

**Files:**
- Modify: `app/services/llm.py:192-241` (`GeminiLLMClient.classify`)

- [ ] **Step 1: Update the Gemini response_schema in classify**

Replace the `response_schema={...}` block inside `GeminiLLMClient.classify` with:

```python
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "intent": {
                                "type": "STRING",
                                "enum": ["faq", "check_product", "confirm_order", "unclear"],
                            },
                            "confidence": {"type": "NUMBER"},
                            "has_complaint_signal": {"type": "BOOLEAN"},
                            "sentiment": {
                                "type": "STRING",
                                "enum": ["neutral", "negative", "positive"],
                            },
                        },
                        "required": ["intent", "confidence", "has_complaint_signal", "sentiment"],
                    },
```

- [ ] **Step 2: Replace the validation + return block in GeminiLLMClient.classify**

Replace the post-`json.loads` validation block with:

```python
            result = json.loads(text)
            intent = result.get("intent")
            confidence = result.get("confidence")
            has_complaint_signal = result.get("has_complaint_signal", False)
            sentiment = result.get("sentiment", "neutral")

            if intent not in VALID_INTENTS:
                raise LLMError(f"Invalid intent from LLM: {intent}")
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                raise LLMError(f"Invalid confidence from LLM: {confidence}")
            if not isinstance(has_complaint_signal, bool):
                raise LLMError(f"Invalid has_complaint_signal from LLM: {has_complaint_signal}")
            if sentiment not in {"neutral", "negative", "positive"}:
                raise LLMError(f"Invalid sentiment from LLM: {sentiment}")

            return {
                "intent": intent,
                "confidence": float(confidence),
                "has_complaint_signal": has_complaint_signal,
                "sentiment": sentiment,
            }
```

- [ ] **Step 3: Verify GeminiLLMClient imports parse**

Run: `python -c "from app.services.llm import GeminiLLMClient; print('OK')"`
Expected: prints `OK`.

- [ ] **Step 4: Commit**

```bash
git add app/services/llm.py
git commit -m "feat(llm): GeminiLLMClient schema requires complaint + sentiment"
```

---

## Task 6: Extend classify_intent node to propagate new fields

**Files:**
- Modify: `app/graph/nodes.py:26-45` (`classify_intent`)

- [ ] **Step 1: Update classify_intent to propagate new fields**

Replace the function:

```python
def classify_intent(state: ChatState, llm_client: Any) -> dict:
    """Classify user message into one of 4 intents.

    Returns dict update for state: {intent, confidence, has_complaint_signal, sentiment}
    Raises LLMError if classification fails (caller decides whether to fallback).
    """
    try:
        result = llm_client.classify(state["message_text"])
        logger.info(
            "intent_classified",
            extra={
                "tenant_id": state["tenant_id"],
                "intent": result["intent"],
                "confidence": result["confidence"],
                "has_complaint_signal": result.get("has_complaint_signal", False),
                "sentiment": result.get("sentiment", "neutral"),
            },
        )
        return {
            "intent": result["intent"],
            "confidence": result["confidence"],
            "has_complaint_signal": result.get("has_complaint_signal", False),
            "sentiment": result.get("sentiment", "neutral"),
        }
    except LLMError as e:
        logger.error("intent_classification_failed", extra={"error": str(e)})
        raise
```

The `.get(..., default)` on both read and write sides ensures that if a test mocks `llm_client.classify` to return only `{intent, confidence}`, the node still works (defaults to `False`/`neutral`).

- [ ] **Step 2: Run existing test_classify tests**

Run: `python -m pytest tests/test_classify.py -v`
Expected: all 3 existing tests pass (they don't assert on the new fields).

- [ ] **Step 3: Commit**

```bash
git add app/graph/nodes.py
git commit -m "feat(graph): classify_intent emits complaint + sentiment to state"
```

---

## Task 7: Add the complaint-signal routing decision in should_fallback

**Files:**
- Modify: `app/graph/graph.py:44-58` (`should_fallback`, `route_after_classify`)

- [ ] **Step 1: Extend should_fallback to OR complaint signal**

Replace the function in `app/graph/graph.py`:

```python
def should_fallback(state: ChatState, threshold: float | None = None) -> bool:
    """Decide whether to route to fallback based on confidence, intent, and signals."""
    if threshold is None:
        threshold = get_settings().intent_confidence_threshold

    if state.get("intent") == "unclear":
        return True
    if state.get("confidence", 0.0) < threshold:
        return True
    if state.get("has_complaint_signal") is True:
        return True
    return False
```

`route_after_classify` is unchanged — it already calls `should_fallback`.

- [ ] **Step 2: Run existing test_graph tests**

Run: `python -m pytest tests/test_graph.py -v`
Expected: all existing tests pass. None of them set `has_complaint_signal`, so `state.get("has_complaint_signal")` returns None, `None is True` is False, and the new check doesn't change behavior.

- [ ] **Step 3: Commit**

```bash
git add app/graph/graph.py
git commit -m "feat(graph): route complaint-signal messages to fallback"
```

---

## Task 8: Add fallback_reason_for helper + enrich fallback_human owner payload

**Files:**
- Modify: `app/graph/graph.py:44-58` (add `fallback_reason_for`)
- Modify: `app/graph/nodes.py` (`fallback_human` body)

- [ ] **Step 1: Add fallback_reason_for helper to app/graph/graph.py**

Append this function to `app/graph/graph.py` right after `should_fallback` (and before `route_after_classify`):

```python
def fallback_reason_for(state: ChatState, threshold: float | None = None) -> str:
    """Return the canonical reason for a fallback, ordered by specificity.

    Order matters: complaint_signal > unclear_intent > low_confidence > fallback.
    """
    if state.get("has_complaint_signal") is True:
        return "complaint_signal"
    if state.get("intent") == "unclear":
        return "unclear_intent"
    if threshold is None:
        threshold = get_settings().intent_confidence_threshold
    if state.get("confidence", 0.0) < threshold:
        return "low_confidence"
    return "fallback"
```

This function is the single source of truth for deriving a fallback reason. Both `_compose_fallback_node` (for lookup misses) and `fallback_human` (for signal-driven escalations) will share the same vocabulary through this helper.

- [ ] **Step 2: Update fallback_human in app/graph/nodes.py**

Replace the entire body of the existing `fallback_human` function with:

```python
async def fallback_human(state: ChatState, gateway_client: Any) -> dict:
    """Forward original message to owner via WhatsApp gateway. Also sends buyer acknowledgement.

    Uses duck typing: client must have send_message(phone, message) method.
    Returns {fallback_reason} on success, {action: "error"} on failure.

    If state already has fallback_reason set (e.g. by _compose_fallback_node),
    keeps that reason. Otherwise derives one from signals via fallback_reason_for().
    """
    from app.db.tenant_repo import get_tenant
    from app.services.phone_gateway import PhoneGatewayException
    from app.graph.graph import fallback_reason_for

    tenant = get_tenant(state["tenant_id"])
    if tenant is None:
        logger.error(
            "fallback_tenant_not_found",
            extra={"tenant_id": state["tenant_id"]},
        )
        return {"action": "error"}

    reason = state.get("fallback_reason") or fallback_reason_for(state)

    sentiment = state.get("sentiment")
    sentiment_line = f"Sentiment: {sentiment}\n" if sentiment else ""

    owner_msg = (
        f"[FALLBACK] Pesan dari {state['wa_number']}:\n\n{state['message_text']}\n\n"
        f"Intent: {state.get('intent', 'n/a')}\n"
        f"Confidence: {state.get('confidence', 'n/a')}\n"
        f"{sentiment_line}"
        f"Reason: {reason}"
    )

    try:
        await gateway_client.send_message(
            phone=tenant["owner_wa_number"],
            message=owner_msg,
        )
        await gateway_client.send_message(
            phone=state["wa_number"],
            message="Sedang kami cek, owner akan follow up ya 🙏",
        )
        logger.info(
            "fallback_triggered",
            extra={
                "tenant_id": state["tenant_id"],
                "thread_id": state["thread_id"],
                "reason": reason,
                "has_complaint_signal": state.get("has_complaint_signal", False),
                "sentiment": sentiment,
            },
        )
        return {"fallback_reason": reason}
    except PhoneGatewayException as e:
        logger.error("fallback_send_failed", extra={"error": str(e)})
        return {"action": "error", "fallback_reason": reason}
```

Notes on what changes:
- Reason is now derived from signals when not preset. `_compose_fallback_node` still sets `no_faq_match` / `no_product_match` / `no_match` for lookup-miss paths; complaint_signal escalation gets `"complaint_signal"`.
- Owner payload adds a `Sentiment: <value>\n` line **only when sentiment is set** (preserves old format for legacy fallbacks).
- Log fields extended for owner-triage debugging.

- [ ] **Step 3: Verify the existing fallback test still passes**

Run: `python -m pytest tests/test_fallback.py tests/test_graph.py -v`
Expected: existing tests pass. `test_built_graph_handles_no_faq_match_via_sync_invoke` asserts `result.get("fallback_reason") in ("no_faq_match", "no_match")` — those reasons are still produced by `_compose_fallback_node` and stored on state before `fallback_human` runs, so `state.get("fallback_reason") or fallback_reason_for(state)` correctly keeps the preset value.

- [ ] **Step 4: Commit**

```bash
git add app/graph/graph.py app/graph/nodes.py
git commit -m "feat(graph): fallback_reason derived from signals; owner payload includes sentiment"
```

---

## Task 9: Tests for complaint-signal routing

**Files:**
- Modify: `tests/test_graph.py:1-110` (append new tests)

- [ ] **Step 1: Append new routing tests to test_graph.py**

Append these tests at the end of `tests/test_graph.py`:

```python
# ---------------------------------------------------------------------------
# Multi-signal emitter — complaint + sentiment routing
# ---------------------------------------------------------------------------


def test_should_fallback_on_complaint_signal_even_with_high_confidence():
    """A complaint-bearing message must escalate regardless of confidence/intent."""
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "kekecilan min, nggak sesuai",
        "intent": "faq",
        "confidence": 0.95,
        "has_complaint_signal": True,
        "sentiment": "negative",
    }
    assert should_fallback(state, threshold=0.6) is True


def test_should_not_fallback_without_complaint_signal_at_high_confidence():
    """No complaint signal + high confidence → no fallback."""
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "berapa harga hoodie?",
        "intent": "faq",
        "confidence": 0.95,
        "has_complaint_signal": False,
        "sentiment": "neutral",
    }
    assert should_fallback(state, threshold=0.6) is False


def test_route_after_classify_returns_fallback_for_complaint_signal():
    """A complaint-bearing faq-classified message routes to fallback_human."""
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "warna nggak sesuai foto",
        "intent": "check_product",
        "confidence": 0.9,
        "has_complaint_signal": True,
        "sentiment": "negative",
    }
    assert route_after_classify(state) == "fallback_human"


def test_should_fallback_complaint_takes_precedence_over_low_confidence_threshold():
    """Complaint signal still escalates even when threshold check would pass
    (i.e., a complaint above threshold should still go to fallback)."""
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "faq",
        "confidence": 0.95,
        "has_complaint_signal": True,
        "sentiment": "negative",
    }
    # confidence (0.95) > threshold (0.6), so without complaint_signal this would
    # be False. With complaint_signal it must be True.
    assert should_fallback(state, threshold=0.6) is True


def test_fallback_reason_for_complaint_signal():
    from app.graph.graph import fallback_reason_for

    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "faq",
        "confidence": 0.95,
        "has_complaint_signal": True,
        "sentiment": "negative",
    }
    assert fallback_reason_for(state) == "complaint_signal"


def test_fallback_reason_for_unclear_intent():
    from app.graph.graph import fallback_reason_for

    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "zzz",
        "intent": "unclear",
        "confidence": 0.95,
        "has_complaint_signal": False,
        "sentiment": "neutral",
    }
    assert fallback_reason_for(state) == "unclear_intent"


def test_fallback_reason_for_low_confidence():
    from app.graph.graph import fallback_reason_for

    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "faq",
        "confidence": 0.3,
        "has_complaint_signal": False,
        "sentiment": "neutral",
    }
    # Pass threshold explicitly to avoid relying on settings default.
    assert fallback_reason_for(state, threshold=0.6) == "low_confidence"


def test_fallback_reason_for_plain_fallback():
    from app.graph.graph import fallback_reason_for

    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "test",
        "intent": "faq",
        "confidence": 0.95,
        "has_complaint_signal": False,
        "sentiment": "neutral",
    }
    # Above threshold, no complaint, clear intent → no reason.
    assert fallback_reason_for(state, threshold=0.6) == "fallback"
```

- [ ] **Step 2: Run new tests**

Run: `python -m pytest tests/test_graph.py -v -k "complaint or fallback_reason_for"`
Expected: 7 tests pass.

- [ ] **Step 3: Run full graph test file to confirm no regressions**

Run: `python -m pytest tests/test_graph.py -v`
Expected: all tests pass (existing + new).

- [ ] **Step 4: Commit**

```bash
git add tests/test_graph.py
git commit -m "test(graph): cover complaint-signal routing + fallback_reason derivation"
```

---

## Task 10: Tests for classify_intent propagation

**Files:**
- Modify: `tests/test_classify.py:1-58` (append new tests)

- [ ] **Step 1: Append new classify tests**

Append to `tests/test_classify.py`:

```python
def test_classify_intent_propagates_complaint_and_sentiment():
    """The node must pass through has_complaint_signal and sentiment from the LLM."""
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "kekecilan min",
    }

    fake_llm = MagicMock()
    fake_llm.classify = MagicMock(
        return_value={
            "intent": "faq",
            "confidence": 0.85,
            "has_complaint_signal": True,
            "sentiment": "negative",
        }
    )

    result = classify_intent(state, llm_client=fake_llm)
    assert result["intent"] == "faq"
    assert result["confidence"] == 0.85
    assert result["has_complaint_signal"] is True
    assert result["sentiment"] == "negative"


def test_classify_intent_defaults_when_llm_omits_new_fields():
    """Older test mocks may return only intent+confidence. Defaults must apply."""
    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "halo",
    }

    fake_llm = MagicMock()
    fake_llm.classify = MagicMock(return_value={"intent": "faq", "confidence": 0.85})

    result = classify_intent(state, llm_client=fake_llm)
    assert result["has_complaint_signal"] is False
    assert result["sentiment"] == "neutral"
```

- [ ] **Step 2: Run new tests**

Run: `python -m pytest tests/test_classify.py -v`
Expected: all 5 tests pass (3 existing + 2 new).

- [ ] **Step 3: Commit**

```bash
git add tests/test_classify.py
git commit -m "test(classify): propagate complaint + sentiment from LLM result"
```

---

## Task 11: Tests for fallback owner payload enrichment

**Files:**
- Modify: `tests/test_fallback.py:1-end` (append new tests)

- [ ] **Step 1: Read the existing test_fallback.py to understand its setup**

Run: `cat tests/test_fallback.py`

- [ ] **Step 2: Append a sentiment-payload test based on the existing pattern**

(Use the same mock/fixture pattern already in the file. The test should mock `gateway_client.send_message` and assert that the owner's message contains `Sentiment: negative` and `Reason: complaint_signal`.)

```python
@pytest.mark.asyncio
async def test_fallback_owner_payload_includes_sentiment_and_complaint_reason():
    """When complaint signal + sentiment are set, owner payload must include both."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.graph.nodes import fallback_human

    state: ChatState = {
        "tenant_id": "demo",
        "wa_number": "+628999",
        "thread_id": "demo:+628999",
        "message_text": "kekecilan min, nggak sesuai",
        "intent": "faq",
        "confidence": 0.85,
        "has_complaint_signal": True,
        "sentiment": "negative",
    }

    fake_tenant = {
        "tenant_id": "demo",
        "owner_wa_number": "+628111111",
    }
    fake_repo = MagicMock(return_value=fake_tenant)

    gateway = MagicMock()
    gateway.send_message = AsyncMock(return_value={"ok": True})

    with patch("app.db.tenant_repo.get_tenant", fake_repo):
        result = await fallback_human(state, gateway_client=gateway)

    # Two sends: one to owner, one to buyer ack.
    assert gateway.send_message.await_count == 2

    # Inspect the owner message (first call).
    owner_call = gateway.send_message.await_args_list[0]
    owner_msg = owner_call.kwargs.get("message") or owner_call.args[1]
    assert "Sentiment: negative" in owner_msg
    assert "Reason: complaint_signal" in owner_msg
    # Should also still include intent + confidence for owner context.
    assert "Intent: faq" in owner_msg
    assert "Confidence: 0.85" in owner_msg

    # Result should carry the derived reason so write_chat_log can persist it.
    assert result.get("fallback_reason") == "complaint_signal"
```

- [ ] **Step 3: Run new test**

Run: `python -m pytest tests/test_fallback.py::test_fallback_owner_payload_includes_sentiment_and_complaint_reason -v`
Expected: passes.

- [ ] **Step 4: Run full fallback test file**

Run: `python -m pytest tests/test_fallback.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_fallback.py
git commit -m "test(fallback): owner payload includes sentiment + complaint_signal reason"
```

---

## Task 12: Run full test suite, verify no regressions

**Files:** none (verification only)

- [ ] **Step 1: Run the full pytest suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Run a smoke test that exercises the end-to-end complaint path**

Run: `python -c "
from unittest.mock import MagicMock, AsyncMock, patch
from app.graph.graph import build_graph
from app.services.llm import MockLLMClient

class FakeSheets:
    def lookup_faq(self, msg): return None
    def read_catalog(self): return []

class FakeGateway:
    def __init__(self):
        self.sent = []
    async def send_message(self, *args, **kwargs):
        self.sent.append((args, kwargs))
        return {'ok': True}

fake_tenant = {'tenant_id': 'demo', 'owner_wa_number': '+628111111'}
fake_repo = MagicMock(return_value=fake_tenant)

graph = build_graph(
    llm_client=MockLLMClient(),
    sheets_client=FakeSheets(),
    gateway_client=FakeGateway(),
)

with patch('app.db.tenant_repo.get_tenant', fake_repo):
    state = {
        'tenant_id': 'demo',
        'wa_number': '+628999',
        'thread_id': 'demo:+628999',
        'message_text': 'kekecilan min, nggak sesuai',
    }
    result = graph.invoke(state)

print('action:', result.get('action'))
print('fallback_reason:', result.get('fallback_reason'))
print('reply_text:', result.get('reply_text'))
print('intent:', result.get('intent'))
print('sentiment:', result.get('sentiment'))
"
```
Expected output:
```
action: fallback
fallback_reason: complaint_signal
reply_text: Sedang kami cek, owner akan follow up ya 🙏
intent: faq
sentiment: negative
```

- [ ] **Step 3: Commit any leftover changes (should be none)**

If no changes: `git status` should show clean working tree.
If something changed: commit it.

---

## Self-Review Checklist

- [x] Each spec requirement mapped to a task:
  - Extended schema → Task 1, 2, 3, 4, 5, 6
  - Multi-signal escalation routing → Task 7
  - Enriched fallback payload → Task 8
  - Tests covering the above → Tasks 9, 10, 11
  - End-to-end verification → Task 12
- [x] No placeholders ("TBD", "implement later", etc.) — verified
- [x] Type consistency:
  - `has_complaint_signal: bool` (not `bool | None`) — verified across all tasks
  - `sentiment: Literal["neutral", "negative", "positive"]` — verified across all tasks
  - `fallback_reason_for` signature consistent in graph.py + nodes.py
  - `ClassificationResult` type alias left as `dict[str, Any]` to avoid ripple
- [x] DRY: `fallback_reason_for` defined once in graph.py, imported by nodes.py
- [x] YAGNI: no entity extraction, no validation gate changes, no new LLM calls, no graph restructure
- [x] TDD: each task adds tests (where applicable) and runs them
- [x] Frequent commits: one commit per task
