# Multi-Signal Emitter Design Spec

> **Status:** Draft. Companion to `2026-07-30-multi-signal-emitter.md` (implementation plan).

## 1. Problem

Today's `classify_intent` is a **single-label gate**: it emits exactly one of `{faq, check_product, confirm_order, unclear}` plus a confidence float. Every downstream routing decision is keyed off that one label.

The bug that surfaced this gap: buyer writes "kekecilan min, nggak sesuai". The classifier labels this `faq` with high confidence (it looks like a sizing question). `lookup_catalog` returns the standard size-chart answer. `compose_reply` produces a polite-but-useless response ("here are the sizes we have"). The buyer gets no escalation, the owner never hears about it, the conversation dies.

This is one instance of a class of problems. Other instances:
- "harga kemahalan" → `faq` confidence 0.85, bot cheerfully sends the price again
- "warna nggak sesuai foto" → `check_product` confidence 0.9, bot sends the product row again
- "udah 3 hari nggak sampe" → `faq` confidence 0.7, bot links the shipping FAQ
- "saya mau refund" → `confirm_order` confidence 0.6, bot says "owner will follow up"

All of these need a human. None of them get one, because the classifier can't say so.

## 2. Solution: Multi-Signal Emitter (Prinsip #1, #2, #3)

### Prinsip #1 — Extend `classify` schema (multi-signal emitter)

Replace the 2-field output `{intent, confidence}` with a 4-field output:

```json
{
  "intent": "faq | check_product | confirm_order | unclear",
  "confidence": 0.0-1.0,
  "has_complaint_signal": true | false,
  "sentiment": "neutral | negative | positive"
}
```

Why these two extra fields and not others:

- **has_complaint_signal**: the single boolean that turns this from a routing problem into a routing *fact*. Any time the LLM sees the buyer expressing dissatisfaction, returning an item, asking for a refund, or describing a failed expectation, this is true. This is the only signal we need to flip routing from "answer" to "escalate" — and unlike `intent == "complaint"`, it composes with whatever else the message is (a complaint can also be a faq question: "harga kemahalan, ada diskon ga?").

- **sentiment**: secondary signal for owner triage. "Saya marah" vs "kekecilan tapi oke" both warrant escalation, but the first should page the owner immediately and the second can wait an hour. We don't act on sentiment in routing today; we just record it in the payload to the owner so they can prioritize.

What we're NOT doing in this PR:
- Entity extraction (Prinsip #4) — separate concern, separate phase
- Grounding/validation gate (Prinsip #5) — already exists in `validate_reply`
- A new LLM call — these fields come from the same call that already happens

### Prinsip #2 — Multi-signal escalation routing

Today, `should_fallback()` returns True only when `intent == "unclear"` or `confidence < threshold`. After this PR:

```python
def should_fallback(state, threshold=None):
    if state.get("intent") == "unclear":
        return True
    if state.get("confidence", 0.0) < threshold:
        return True
    if state.get("has_complaint_signal") is True:
        return True
    return False
```

This is the entire routing change. One line. Any time the classifier sees a complaint — regardless of what other intent it picked — we route to `fallback_human` instead of trying to answer.

The LLM already gets this signal cheaply; we just stop throwing it away.

### Prinsip #3 — Enriched fallback payload to owner

Today, the owner sees:
```
[FALLBACK] Pesan dari +628999:

kekecilan min, nggak sesuai

Intent: faq
Confidence: 0.85
Reason: no_faq_match
```

After this PR:
```
[FALLBACK] Pesan dari +628999:

kekecilan min, nggak sesuai

Intent: faq
Confidence: 0.85
Sentiment: negative
Reason: complaint_signal
```

`Reason: complaint_signal` is the new `fallback_reason` value. `Sentiment` is the new line. `Intent` and `Confidence` are unchanged.

This is the smallest payload change that gives the owner what they need: *what the buyer said, that they're upset, and why we didn't try to answer it ourselves*. They can prioritize and reply from there.

## 3. Trade-offs

### Why one LLM call, not three
Three concerns that could each be a separate call:
1. Intent classification
2. Complaint detection
3. Sentiment analysis

We chose to merge them into one structured-output call. Reasons:
- **Cost**: three calls = 3x latency, 3x tokens. One call with extended schema = 1x.
- **Consistency**: the same model run that sees "kekecilan" is the one that decides it's a complaint. Three calls could disagree.
- **Latency**: WhatsApp users won't wait 6+ seconds for a multi-stage pipeline. One ~1s call is acceptable.
- **Quality**: structured output with a JSON schema enforces consistency; the model can't accidentally output `intent: "complaint"` (not in the enum) and break routing.

### Why a boolean for complaint, not a new intent
Adding `complaint` to the intent enum would force a single label again — but complaint is orthogonal to intent. "Saya mau refund" can be `confirm_order` (the buyer wants to transact) or `unclear` (we don't know what they want). Bolting complaint onto intent loses information.

A separate boolean preserves the orthogonal signal and lets the routing logic OR them: "complaint OR low_conf OR unclear_intent → escalate".

### Why not classify sentiment first and act on it
We considered using sentiment directly (route negative-sentiment messages to owner regardless of intent). We rejected this because:
- Sentiment is noisy in Indonesian WhatsApp chat. "Nggak" alone is negative-ish but not actionable.
- Complaint is the *actionable* signal. Negative sentiment without complaint (e.g., "harga kok mahal ya, ada diskon?") is a legitimate faq question we *should* answer.
- Complaint captures the user's actual request: "I need a human." Sentiment is metadata.

Sentiment stays as payload metadata only — never as a routing trigger.

### Why we don't fix the underlying "kekecilan" problem
"Kekecilan" specifically means a sizing issue with a physical product — a return/refund situation that no amount of FAQ lookup will resolve. The proper fix would be entity extraction (Prinsip #4) to detect which product the buyer is complaining about, plus a return flow. That's a larger project. This PR gets the right *escalation* decision; the deeper product-aware return flow is follow-up work.

## 4. What stays the same

- **Intent enum**: `faq | check_product | confirm_order | unclear` — unchanged
- **Confidence field**: unchanged meaning
- **All routing for faq/check_product/confirm_order/unclear with low sentiment**: unchanged
- **`lookup_catalog` node**: unchanged
- **`compose_reply` node and validation gate**: unchanged
- **`send_whatsapp`, `write_chat_log`**: unchanged
- **MockLLMClient**: unchanged (defaults to `has_complaint_signal: false`, `sentiment: "neutral"` so existing tests keep working)
- **The buyer-facing reply text**: unchanged for non-complaint paths

## 5. What changes (file-by-file)

### `app/graph/state.py`
- Add 2 fields to `ChatState`:
  - `has_complaint_signal: bool | None`
  - `sentiment: Literal["neutral", "negative", "positive"] | None`

### `app/graph/prompts.py`
- Update `INTENT_CLASSIFICATION_SYSTEM` prompt:
  - Add instructions for the LLM to detect complaint signals (with examples)
  - Add instructions for sentiment classification (with examples)
  - Update the JSON format spec to include the two new fields

### `app/services/llm.py`
- **`AnthropicLLMClient.classify`**: extend JSON parsing to accept and return the two new fields. No schema enforcement needed (Anthropic accepts free JSON).
- **`GeminiLLMClient.classify`**: extend `response_schema` to include the two new fields as required properties. Add enum constraint for sentiment.
- **`MockLLMClient.classify`**: add the two fields with default neutral values. Add a method `_has_complaint_signal(msg)` that returns True for messages containing complaint keywords (`kekecilan`, `kemasihan`, `refund`, `komplain`, `ganti`, `rusak`, `salah`, `kembalian`, `balikin`, `tidak sesuai`, `nggak sesuai`, `ga sesuai`, `kecewa`, etc.) — only used by tests/dev, but makes local manual testing honest.
- **`ClassificationResult` type alias**: keep as `dict[str, Any]` so the schema change doesn't ripple through type signatures.

### `app/graph/nodes.py`
- **`classify_intent`**: pass through the two new fields from LLM result to state. Add a log field for `has_complaint_signal`.
- **`fallback_human`**: enrich the owner payload with `Sentiment:` line when sentiment is set; derive `fallback_reason` when it isn't already set on state (e.g. complaint_signal escalates before `_compose_fallback_node` runs).

### `app/graph/graph.py`
- **`should_fallback`**: add the `has_complaint_signal is True` check.
- **`fallback_reason_for`**: new helper. Returns the canonical reason string for a fallback — `complaint_signal`, `unclear_intent`, `low_confidence`, or `fallback` — ordered by specificity.

### Tests
- `tests/test_classify.py`: add cases for complaint signal + sentiment propagation.
- `tests/test_graph.py`: add `test_should_fallback_on_complaint_signal_*` cases. Update `_base_high_state()` if needed.
- `tests/test_fallback.py`: add case verifying owner payload contains sentiment line when present.
- `tests/test_llm.py`: update MockLLM expectations; add case for Anthropic-style and Gemini-style responses with new fields.

## 6. Out of scope (intentionally)

- **Prinsip #4 (entity extraction)**: separate phase
- **Prinsip #5 (validation gate beyond existing)**: already implemented as `validate_reply`
- **Per-tenant complaint thresholds**: one global behavior is fine for now
- **Multilingual signals**: bot is Indonesian-only today
- **Persisting sentiment/complaint to chat_log**: could be added later; for now it lives in the owner payload only

## 7. Risks

- **LLM may over-flag complaints**: e.g., "tidak ada masalah" might be flagged as a complaint signal. Mitigation: prompts include explicit "negative-without-issue" examples. Future iteration can add a confidence threshold on `has_complaint_signal` if needed.
- **Backward compat for logs**: existing chat_log rows don't have these fields. The repo (`insert_chat_log`) needs to accept None for the new fields or we extend the schema. We extend the schema in this PR.
- **Mock LLM defaults**: existing tests that don't care about complaint/sentiment will pass because defaults are False/neutral. We've verified by reading `test_graph.py` and `test_classify.py`.

## 8. Acceptance criteria

1. `classify_intent` returns `has_complaint_signal` and `sentiment` from the LLM.
2. A buyer message like "kekecilan min, nggak sesuai" routes to `fallback_human`, not `lookup_catalog`.
3. The owner payload includes the sentiment line when sentiment is set.
4. `fallback_reason == "complaint_signal"` is logged for complaint-routed fallbacks.
5. All existing tests pass without modification to their assertions (defaults preserve behavior).
6. `intent_confidence_threshold` continues to apply independently of complaint signals.
7. New unit tests cover: complaint routing, sentiment propagation, owner payload enrichment, and Mock LLM defaults.
