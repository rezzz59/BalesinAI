# Grounded Reply Generation — Design Spec

**Status:** Draft for review (2026-07-29)
**Author:** brainstorming session with user
**Related:** MVP Phase 1 (Fonnte-only webhook agent), `docs/superpowers/specs/2026-07-27-ordercloser-lite-fase1-design.md`

## Problem

Today the OrderCloser Lite agent returns **verbatim strings** from the customer's Google Sheets:

- FAQ intent: returns the `jawaban` cell as-is (e.g. "Bisa untuk area Jabodetabek saja").
- `check_product` intent: string-formats the matched product's name/price/deskripsi.

Even though an LLM classifies intent, the **reply text itself never flows through the LLM**. Customers see template-shaped, sometimes stiff responses, which defeats the "AI agent that sounds like a human teammate" pitch.

The customer wants: **the xlsx is reference data only; the LLM composes the reply in natural Indonesian, but never invents facts**.

## Goals

1. Replace the verbatim-xlsx reply step with an LLM-composed reply.
2. **Never hallucinate** numeric facts (prices, sizes, stock status) — the LLM must use xlsx values verbatim where they exist.
3. Preserve today's tone: warm Indonesian, "kak" address, "kami" pronoun.
4. Preserve today's fallback: when no relevant row exists, the polite no-match reply followed by human handoff.
5. Reuse existing retrieval (keyword match in `app/services/sheets.py`) — no new infrastructure.
6. Cost: one extra LLM call per inbound message (today: 1 call; after: 2).

## Non-goals

- Conversation memory / multi-turn context (Phase 2 candidate; out of scope).
- Embedding-based retrieval / vector DB (overkill for 500 products).
- Switching the LLM backend (Gemini and Anthropic both support this design).
- Changing the webhook contract, Fonnte send path, or fallback-to-owner flow.

## Architecture

### Where the change lands

The `compose_reply` node in `app/graph/nodes.py` is the only production-code entry point that produces reply text today. It is replaced with a new `compose_with_llm` helper that:

1. Receives the `message_text`, `intent`, and `match_kind` (high / medium / none).
2. Receives the matched row from `lookup_catalog` (or `None`).
3. Selects a prompt template based on `match_kind`.
4. Calls `LLMClient.compose_reply(...)` and validates the result.
5. Returns `{reply_text, action}` (same shape as today).

The graph wiring (in `app/graph/graph.py`) does NOT change — only the implementation of one node.

### Confidence scoring

`lookup_catalog` already returns either a `catalog_answer` (FAQ) or a `product_match` (catalog). We add a `match_kind` field to `ChatState`:

- **high**: matched row's text contains at least 50% of the message's words (≥3 chars). Example: "berapa harga hoodie fleece?" vs FAQ row "Berapa harga hoodie fleece tebal?" → high.
- **medium**: matched row's text contains 1-49% of message words. Example: "kaos oversize boxy warna navy" vs FAQ row "Kaos oversize panjangnya sampai mana?" — overlap is small, partial answer at best.
- **none**: no row matched.

The threshold (50%) is a starting value and will be tuned after implementation using the stress-test fixtures (`fixtures/sample_customer_questions.txt`).

### Prompt variants

Three prompt templates live in `app/graph/prompts.py`.

#### `COMPOSE_STRICT_SYSTEM` (high-confidence path)

Used when a relevant row was matched and the keyword overlap is high. The LLM is told:

- Persona: customer-service teammate, WhatsApp, Indonesian UMKM seller.
- Tone: warm, polite, relaxed. Use "Kak" to address the buyer, "kami" as pronoun.
- **Hard constraint**: any numeric fact (price, size, stock indicator) must appear EXACTLY as in the source row.
- Allowed: natural greetings ("Halo Kak!"), closers ("Boleh order ya 🙏"), connecting phrases.
- Forbidden: any price, size, color, stock status, or store-policy wording that does not appear in the source row.
- If the source row does not fully answer the question, say so politely and invite the buyer to ask more — but never invent.

#### `COMPOSE_PARTIAL_SYSTEM` (medium-confidence path)

Same constraints as `COMPOSE_STRICT_SYSTEM`, plus:

- Acknowledge to the buyer that the team is confirming the specific detail with the warehouse/owner.
- Offer to forward the question to the owner if the buyer prefers not to wait.
- **Important**: still no hallucination. The LLM may only describe what the source row contains.

#### `COMPOSE_NOMATCH_SYSTEM` (no-match path)

The exact text the user provided in the brainstorm:

> You are a customer service team member on WhatsApp. Use polite, friendly, relaxed, and warm Indonesian, typical of Indonesian e-commerce (use the greeting 'Kak').
>
> If the product or FAQ requested by the buyer is NOT found in the data:
> 1. NEVER hallucinate, make up answers, or guess stock/information.
> 2. DO NOT use rigid words like "robot", "automated system", or "will be forwarded to the owner" because it can make buyers feel like they are only talking to a bot.
> 3. Use the pronouns "kami" (we).
> 4. State that the product/information is not yet available in the catalog, explain that you/the team are currently checking with the warehouse/owner for them, and kindly ask the buyer to wait a moment.

### LLMClient interface change

`app/services/llm.py` adds one abstract method:

```python
class LLMClient(abc.ABC):
    @abc.abstractmethod
    def compose_reply(self, message: str, retrieved_row: dict | None, match_kind: str) -> str:
        """Compose natural Indonesian reply grounded in retrieved_row (if any).

        Args:
          message: the buyer's WhatsApp message.
          retrieved_row: matched FAQ or product row, or None.
          match_kind: 'high' | 'medium' | 'none'.

        Returns the composed reply text. May raise LLMError.
        """
```

Implementations for `GeminiLLMClient` and `AnthropicLLMClient` mirror today's `classify()` structure (system prompt + user template, JSON config for Gemini, plain text for Anthropic). `MockLLMClient` gets a deterministic implementation that returns the input source row wrapped in simple text — fine for tests that don't exercise the LLM.

### Post-generation validation

A new helper `validate_reply(reply, source_row)` enforces the no-hallucination rule:

1. Extract numeric tokens from the reply (regex `r"\d+(?:\.\d+)?"`).
2. Extract numeric tokens from `source_row` (across all string fields).
3. If any numeric token in the reply is NOT in the source row, raise `LLMValidationError`.
4. Also check size strings (S/M/L/XL/XXL/XXXL) and stock indicators ("ready", "habis", "Y"/"N") similarly.

Validation is conservative — it errs on the side of false positives (rejecting safe replies). The trade-off is acceptable because the fallback path exists (see below).

### Error handling

Three failure modes, all handled gracefully:

| Failure | Behavior |
|---|---|
| `LLMClient.compose_reply` raises (network, API error, timeout) | Fall back to today's verbatim-xlsx reply (degraded mode). Same `reply_text` shape as pre-change MVP. |
| `validate_reply` raises `LLMValidationError` | Retry `compose_reply` once with a stricter system prompt appending: "Previous reply contained a number that is not in our data. Use ONLY data from the row provided." If the retry still fails validation, fall back to verbatim-xlsx reply. |
| All paths fail (LLM down, validation broken) | Today's `fallback_human` to owner still runs. Customer gets "Sedang kami cek, owner akan follow up ya 🙏". |

A single retry keeps the design simple and avoids runaway LLM calls. Tunable later if needed.

## Data flow

```
Webhook → classify_intent → lookup_catalog → compose_with_llm → send_whatsapp
                                    │
                                    └─→ returns {catalog_answer | product_match, match_kind}
                                              │
                                              └─→ compose_with_llm(message, row, match_kind)
                                                          │
                                                          ├─→ LLMClient.compose_reply
                                                          ├─→ validate_reply (1 retry on fail)
                                                          └─→ return {reply_text, action}
```

The shape of every node's input/output is preserved. Only the body of `compose_reply` changes.

## File-by-file changes

| File | Type | Notes |
|---|---|---|
| `app/graph/prompts.py` | MODIFY | Add `COMPOSE_STRICT_SYSTEM`, `COMPOSE_PARTIAL_SYSTEM`, `COMPOSE_NOMATCH_SYSTEM`, plus user templates that interpolate `{message}` and `{source_row}`. |
| `app/services/llm.py` | MODIFY | Add `compose_reply` to abstract base. Implement in `GeminiLLMClient`, `AnthropicLLMClient`, `MockLLMClient`. Add `LLMValidationError` exception. Add `validate_reply(reply, source_row)` helper. |
| `app/graph/state.py` | MODIFY | Add `match_kind: str \| None` to `ChatState`. |
| `app/graph/nodes.py` | MODIFY | `lookup_catalog` now also returns `match_kind`. `compose_reply` body replaced with a call to `compose_with_llm` helper. Helper handles retry+fallback. |
| `app/graph/nodes.py` (NEW helper) | ADD | `compose_with_llm(state, llm_client)` — wraps LLM call, validation, retry, fallback. |
| `tests/test_llm_compose.py` | NEW | Unit tests for `compose_reply` per backend, `validate_reply`, retry-on-validation-fail. |
| `tests/test_graph.py` | MODIFY | Update existing graph tests to expect LLM-shaped replies. Add tests for: high/medium/none match kinds, hallucination retry, fallback to verbatim-xlsx. |
| `tests/conftest.py` | MODIFY | Add `MockLLMClient` fixture that returns deterministic natural-language replies (not the input row verbatim, so tests verify orchestration not just data passthrough). |

No changes to: `app/main.py`, `app/config.py`, webhook auth, Fonnte client, fallback-to-owner, sheets client (lookup logic stays as-is), chat log persistence.

## Testing strategy

### Unit tests (no LLM)

- `validate_reply` — passes when reply contains only source numbers/sizes; raises when reply contains a foreign number; raises when reply contains a stock indicator not in source.
- `MockLLMClient.compose_reply` — returns deterministic warm Indonesian reply.
- Match-kind scoring (in `lookup_catalog` tests) — high/medium/none across known message/row pairs.

### Integration tests (with mocked LLM)

- Full graph run with `MockLLMClient`: high-confidence row → reply uses source row verbatim for facts, allows tone.
- Full graph run: medium-confidence → reply acknowledges partial match, no hallucination.
- Full graph run: no match → reply follows `COMPOSE_NOMATCH_SYSTEM` rules (no "bot"/"forwarded"/"automated"; uses "kami"; asks buyer to wait).
- LLM raises → graph falls back to verbatim xlsx reply.
- LLM reply fails validation → retry once, then fall back to verbatim xlsx.
- Validation retry succeeds → reply used as-is.

### Manual smoke test

Use `fixtures/sample_customer_questions.txt` (30 questions) against the live webhook with `LLM_BACKEND=gemini`. Verify:
- No reply contains a price not in `fixtures/sample_faq_katalog.xlsx`.
- No reply uses forbidden words ("bot", "automated system", "forwarded to owner") when match is none.
- Replies feel natural, not string-formatted.

## Open questions / future work

- Confidence threshold (50%) needs tuning after implementation. If too many medium-confidence paths land, raise to 70%. If too few, lower to 30%.
- The validation regex is conservative — Indonesian pricing like "Rp 50.000" or "Rp1.500.000" must pass through unchanged. Confirm regex covers these.
- Cost monitoring is not added in this scope — only the LLM call count. Phase 2 candidate: per-tenant call counters.
- The "kak" greeting in `COMPOSE_STRICT_SYSTEM` and the absence of it in `COMPOSE_PARTIAL_SYSTEM` are intentional (success tone vs partial-answer tone). Confirm with user feedback after manual smoke test.

## Acceptance criteria

- All 50 existing tests still pass.
- New tests (`test_llm_compose.py` + updated `test_graph.py`) all pass.
- Manual smoke test against `fixtures/sample_customer_questions.txt` shows no hallucinated prices/sizes.
- `git log` shows one atomic commit per logical change (per project workflow: prompts, llm client, nodes/state, tests).
- No new runtime dependencies.