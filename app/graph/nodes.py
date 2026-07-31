"""LangGraph nodes for OrderCloser Lite."""
import logging
from typing import Any

from app.graph.state import ChatState
from app.services.llm import LLMError, LLMValidationError, validate_reply
from app.services.semantic_search import SemanticSearchClient, SemanticSearchError
from app.services.sheets import FAQ_MATCH_THRESHOLD, _score_faq_row

logger = logging.getLogger(__name__)


def _to_match_kind(score: float) -> str:
    """Bucket an overlap score into high/medium/none for downstream grading.

    Uses thresholds (0.5 high, otherwise >0 medium) so a 1/2 overlap (0.5)
    counts as a high-confidence FAQ match Ⲉ appropriate when the buyer asks a
    short, specific question.
    """
    if score >= 0.5:
        return "high"
    if score > 0.0:
        return "medium"
    return "none"


def fallback_reason_for(state: ChatState, threshold: float | None = None) -> str | None:
    """Derive a fallback_reason code from state, or None if no fallback applies.

    Priority order:
      1. complaint_signal — buyer escalation/escalation risk
      2. unclear — intent not classifiable
      3. low_confidence — below intent_confidence_threshold
      4. no_faq_match — FAQ lookup returned nothing (intent=faq)
      5. no_product_match — product lookup returned nothing (intent=check_product)

    Only one reason per call. Higher-priority reason wins.
    """
    from app.config import get_settings

    if threshold is None:
        threshold = get_settings().intent_confidence_threshold

    if state.get("has_complaint_signal"):
        return "complaint_signal"
    if state.get("intent") == "unclear":
        return "unclear"
    if state.get("confidence", 0.0) < threshold:
        return "low_confidence"

    intent = state.get("intent")
    if intent == "faq" and not state.get("catalog_answer"):
        return "no_faq_match"
    if intent == "check_product" and not state.get("product_match"):
        return "no_product_match"

    return None


def classify_intent(state: ChatState, llm_client: Any) -> dict:
    """Classify user message into one of 4 intents.

    Considers conversation history (state["messages"]) so intent can be inferred
    from multi-turn context, not just the latest message.

    Returns dict update for state: {intent, confidence, has_complaint_signal, sentiment}
    Raises LLMError if classification fails (caller decides whether to fallback).

    Empty/whitespace-only messages are handled here by setting intent to "unclear"
    and high confidence fallback.
    """
    # Handle empty/whitespace-only messages early
    message = state.get("message_text", "") or ""
    stripped_message = message.strip()
    if not stripped_message:
        logger.warning(
            "empty_message_detected",
            extra={
                "tenant_id": state["tenant_id"],
                "thread_id": state["thread_id"],
            },
        )
        # Classify as unclear intent to trigger fallback via should_fallback
        return {
            "intent": "unclear",
            "confidence": 1.0,  # confident it's unclear
            "has_complaint_signal": False,
            "sentiment": "neutral",
        }

    try:
        # Pass full conversation history so LLM can leverage multi-turn context
        messages = state.get("messages") or []
        result = llm_client.classify_with_history(messages)
        logger.info(
            "intent_classified",
            extra={
                "tenant_id": state["tenant_id"],
                "intent": result["intent"],
                "confidence": result["confidence"],
                "has_complaint_signal": result.get("has_complaint_signal", False),
                "history_turns": len(messages),
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


def lookup_catalog(
    state: ChatState,
    sheets_client: Any,
    semantic_search_client: SemanticSearchClient | None = None,
) -> dict:
    """Lookup answer in Sheets based on intent, with optional semantic boost.

    For intent=faq: call sheets_client.lookup_faq() and grade the match.
    For intent=check_product: read catalog via sheets_client.read_catalog(),
        then optionally narrow candidates with semantic_search_client. If no
        semantic client is provided, fall back to scanning every product with
        _score_faq_row. The candidate with the highest lexical overlap above
        FAQ_MATCH_THRESHOLD is returned.

    Returns dict update: {catalog_answer, product_match, match_kind} or empty
    dict if no match.
    """
    intent = state["intent"]

    try:
        if intent == "faq":
            match = sheets_client.lookup_faq(state["message_text"])
            if match is None:
                logger.info(
                    "faq_no_match",
                    extra={
                        "tenant_id": state["tenant_id"],
                        "thread_id": state["thread_id"],
                    },
                )
                return {}
            score = _score_faq_row(state["message_text"], match)
            return {
                "catalog_answer": match["jawaban"],
                "product_match": None,
                "match_kind": _to_match_kind(score),
            }

        if intent == "check_product":
            products = sheets_client.read_catalog()
            message = state["message_text"]

            # Optionally narrow candidate set via semantic search. If it fails
            # or returns no row_ids we can map, fall back to the full product
            # list so behaviour degrades gracefully.
            candidates = products
            if semantic_search_client is not None:
                try:
                    hits = semantic_search_client.search(
                        message,
                        tenant_id=state["tenant_id"],
                        source="catalog",
                        limit=3,
                    )
                except SemanticSearchError as e:
                    logger.warning(
                        "semantic_search_failed",
                        extra={
                            "tenant_id": state["tenant_id"],
                            "error": str(e),
                        },
                    )
                    hits = []

                if hits:
                    row_ids = {hit["row_id"] for hit in hits}
                    semantic_candidates = [
                        p
                        for p in products
                        if str(p.get("id") or p.get("nama_produk")) in row_ids
                    ]
                    if semantic_candidates:
                        candidates = semantic_candidates

            best_product: dict | None = None
            best_score = 0.0
            for product in candidates:
                combined = " ".join(
                    str(product.get(k) or "")
                    for k in ("nama_produk", "deskripsi")
                )
                score = _score_faq_row(message, {"text": combined})
                if score > best_score:
                    best_score = score
                    best_product = product
            if best_product is not None and best_score >= FAQ_MATCH_THRESHOLD:
                return {
                    "catalog_answer": None,
                    "product_match": best_product,
                    "match_kind": _to_match_kind(best_score),
                }
            # No specific product keyword matched — treat as a catalog-browse
            # request. List all ready products as a deterministic template reply
            # so we never invent details via LLM. If nothing is ready, fall
            # through to fallback (empty dict) so the owner gets notified.
            ready = sheets_client.list_ready_products()
            if ready:
                logger.info(
                    "catalog_browse_listed",
                    extra={
                        "tenant_id": state["tenant_id"],
                        "thread_id": state["thread_id"],
                        "count": len(ready),
                    },
                )
                return {
                    "reply_text": _format_browse_reply(ready),
                    "action": "reply",
                    "product_match": None,
                    "catalog_answer": None,
                    "match_kind": "none",
                }
            return {}

        return {}
    except Exception as e:  # noqa: BLE001
        logger.error(
            "sheets_lookup_failed",
            extra={
                "tenant_id": state["tenant_id"],
                "error": str(e),
            },
        )
        return {}


def compose_reply(state: ChatState, llm_client: Any) -> dict:
    """Compose reply text. Dispatches to LLM (via _compose_with_llm) or fallback path.

    Incorporates conversation history for context-aware responses.
    Updates state["messages"] with the assistant's reply after composition.

    Returns {reply_text, action} (action ∈ "reply" | "fallback" | "order").
    """
    return _compose_with_llm(state, llm_client)


def _compose_with_llm(state: ChatState, llm_client: Any) -> dict:
    """Orchestrate LLM compose + validate + 1 retry on validation failure + fallback.

    Order:
      1. confirm_order → short template reply (no LLM needed).
      2. Try LLM compose_reply once, validate reply against source row (or None).
      3. On validation failure: retry once with a stricter hint appended to message.
      4. On any LLMError: fall back to verbatim-xlsx reply (no retries).
      5. After 2 validation failures: fall back to verbatim-xlsx reply.
      6. Verbatim fallback returns the human-handoff message when there's no data.
    """
    # Short-circuit: if an upstream node already built the reply (e.g. catalog
    # browse list from lookup_catalog), return it verbatim — no LLM round-trip,
    # no risk of hallucination on multi-row output.
    if state.get("reply_text") and state.get("action") == "reply":
        # Note: reply already has LLM content; we'll append to messages after send
        return {"reply_text": state["reply_text"], "action": "reply"}

    intent = state["intent"]
    match_kind = state.get("match_kind") or "none"

    # Build the retrieved_row we pass to the LLM / validator. May be None
    # when lookup returned nothing (e.g., match_kind == "none").
    retrieved_row = _build_retrieved_row(state)

    # Get optional customer context for composing context-aware replies
    customer_context = state.get("customer_context")

    # 1. Order confirmation: short template, no LLM.
    if intent == "confirm_order":
        reply = (
            "Terima kasih ordernya! Owner akan follow up untuk konfirmasi "
            "pembayaran ya 🙏"
        )
        # Append user message to history, then add assistant reply
        messages = state.get("messages", []) or []
        return {
            "reply_text": reply,
            "action": "order",
            "messages": messages + [{"role": "user", "content": state["message_text"]}, {"role": "assistant", "content": reply}],
        }

    message = state["message_text"]
    strict_hint = (
        "\n\n[Strict hint: your previous reply contained facts not in our catalog. "
        "Restrict your reply to ONLY facts from the source row above. Do not invent "
        "prices, sizes, colors, or stock status.]"
    )

    # 2-5. Try up to 2 attempts (initial + 1 retry) before falling back.
    for attempt in range(2):
        try:
            message_for_call = message if attempt == 0 else f"{message}{strict_hint}"
            reply = llm_client.compose_reply_with_history(
                messages=state.get("messages", []) or [],
                message=message_for_call,
                retrieved_row=retrieved_row,
                match_kind=match_kind,
                customer_context=customer_context,  # Pass customer context for context-aware replies
            )
            validate_reply(reply, retrieved_row)
            # Append to conversation history before returning
            messages = (state.get("messages", []) or []) + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": reply},
            ]
            return {
                "reply_text": reply,
                "action": "reply",
                "messages": messages,
            }
        except LLMValidationError as e:
            logger.warning(
                "compose_validation_failed",
                extra={
                    "tenant_id": state["tenant_id"],
                    "attempt": attempt,
                    "error": str(e),
                },
            )
            # Loop continues to retry (or fall through to verbatim).
            continue
        except LLMError as e:
            logger.error(
                "compose_llm_failed",
                extra={"tenant_id": state["tenant_id"], "error": str(e)},
            )
            return _verbatim_fallback(state)

    # Validation failed twice → verbatim-xlsx reply (or human-handoff if no data).
    logger.warning(
        "compose_validation_failed_twice",
        extra={"tenant_id": state["tenant_id"]},
    )
    return _verbatim_fallback(state)


def _build_retrieved_row(state: ChatState) -> dict | None:
    """Build the source-row dict passed to the LLM and the validator.

    For FAQ: wrap catalog_answer as a 1-key dict so validate_reply can read it.
    For check_product: use the matched product dict directly.
    Returns None if neither is present (no-match path).
    """
    intent = state["intent"]
    if intent == "faq" and state.get("catalog_answer"):
        return {"pertanyaan": "(implicit FAQ)", "jawaban": state["catalog_answer"]}
    if state.get("product_match"):
        return state["product_match"]
    return None


def _verbatim_fallback(state: ChatState) -> dict:
    """Today's degraded-mode reply: build a reply directly from source row values.

    Wraps the raw FAQ answer in a polite, owner-handoff sentence so the buyer
    isn't left staring at an unattributed fragment of catalog text.
    """
    if state.get("catalog_answer"):
        return {
            "reply_text": (
                f"Halo Kak, kami catat dulu ya 🙏\n\n"
                f"{state['catalog_answer']}\n\n"
                f"Untuk detail yang lebih spesifik, kami akan forward ke owner ya Kak."
            ),
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


def _compose_fallback_message(state: ChatState, reason: str) -> dict:
    return {
        "reply_text": "Sedang kami cek, owner will follow up ya 🙏",
        "action": "fallback",
        "fallback_reason": reason,
    }


def _format_browse_reply(products: list[dict]) -> str:
    """Format a ready-product list for a buyer 'ada produk apa aja?' query.

    Catalog has many ready variants — listing all of them would explode the
    WhatsApp message. Group by product family, show a representative item
    per family plus variant count and price range, and offer to share more.

    Output format (deterministic, no LLM):
      opener
        family 1 — X varian ready (contoh: <name> Rp<min>-Rp<max>)
        family 2 — ...
      closing
    """
    families: dict[str, list[dict]] = {}
    for p in products:
        nama = (p.get("nama_produk") or "").strip()
        family = _extract_family(nama)
        families.setdefault(family, []).append(p)

    MAX_FAMILIES = 8
    family_names = sorted(families)
    shown = family_names[:MAX_FAMILIES]
    hidden = len(family_names) - len(shown)

    lines = ["Ini lineup yang ready ya kak 😊", ""]
    for family in shown:
        variants = families[family]
        prices = [int(v.get("harga")) for v in variants if str(v.get("harga", "")).isdigit()]
        sample = variants[0].get("nama_produk", "-")
        if prices:
            lo, hi = min(prices), max(prices)
            price_range = f"Rp{lo:,}" if lo == hi else f"Rp{lo:,}-Rp{hi:,}"
        else:
            price_range = "Harga cek via owner"
        lines.append(
            f"- {family}: {len(variants)} varian ready "
            f"(contoh: {sample}, {price_range})"
        )
    if hidden > 0:
        lines.append(f"- (+{hidden} kategori lain, sebut aja yang Kakak cari)")
    total = len(products)
    lines.append("")
    lines.append(
        f"Total ada {total} varian ready. Sebut aja nama produknya ya kak 😊"
    )
    return "\n".join(lines)


def _extract_family(nama: str) -> str:
    """Pull the product family from a full product name.

    Example: 'Kaos Oversize Crop - Hitam - Size L' -> 'Kaos Oversize Crop'
    Strategy: take leading words until we hit ' - ' or '-' alone, then strip
    trailing size/colour tokens. Falls back to first 3 words.
    """
    if not nama:
        return "Lainnya"
    head = nama.split(" - ")[0].strip()
    # Drop trailing size tokens like 'Size L', 'Size XXL'.
    for token in head.split():
        if token.lower().startswith("size"):
            head = head.split(token)[0].strip()
            break
    return head or " ".join(nama.split()[:3])


async def send_whatsapp(state: ChatState, gateway_client: Any) -> dict:
    """Send reply_text to buyer via WhatsApp gateway. Returns {} on success.

    Uses duck typing: client must have send_message(phone, message) method.
    Raises PhoneGatewayException if there's an error after retries.

    Returns {action: "error"} on failure.
    """
    from app.services.phone_gateway import PhoneGatewayException  # Local import to avoid circular deps

    try:
        await gateway_client.send_message(
            phone=state["wa_number"],
            message=state["reply_text"],
        )
        logger.info(
            "whatsapp_sent",
            extra={
                "tenant_id": state["tenant_id"],
                "thread_id": state["thread_id"],
            },
        )
        return {}
    except PhoneGatewayException as e:
        logger.error(
            "whatsapp_send_failed",
            extra={
                "tenant_id": state["tenant_id"],
                "thread_id": state["thread_id"],
                "error": str(e),
            },
        )
        return {"action": "error"}


async def fallback_human(state: ChatState, gateway_client: Any) -> dict:
    """Forward original message to owner via WhatsApp gateway. Also sends buyer acknowledgement.

    Uses duck typing: client must have send_message(phone, message) method.
    Raises PhoneGatewayException if there's an error after retries.

    If fallback_reason is not yet on state, derives it via fallback_reason_for().
    Returns {} on success, {action: "error"} on failure.
    """
    from app.services.phone_gateway import PhoneGatewayException  # Local import to avoid circular deps

    # Need owner_wa_number — but it's not in ChatState. Read from tenant repo.
    from app.db.tenant_repo import get_tenant

    fallback_reason = state.get("fallback_reason") or fallback_reason_for(state) or "n/a"
    sentiment = state.get("sentiment", "neutral")
    result: dict = {"action": "fallback", "fallback_reason": fallback_reason}

    tenant = get_tenant(state["tenant_id"])
    if tenant is None:
        logger.error(
            "fallback_tenant_not_found",
            extra={"tenant_id": state["tenant_id"]},
        )
        return {"action": "error"}

    owner_msg = (
        f"[FALLBACK] Pesan dari {state['wa_number']}:\n\n{state['message_text']}\n\n"
        f"Intent: {state.get('intent', 'n/a')}\n"
        f"Confidence: {state.get('confidence', 'n/a')}\n"
        f"Sentiment: {sentiment}\n"
        f"Reason: {fallback_reason}"
    )

    try:
        # 1. Send to owner
        await gateway_client.send_message(
            phone=tenant["owner_wa_number"],
            message=owner_msg,
        )
        # 2. Send acknowledgement to buyer
        await gateway_client.send_message(
            phone=state["wa_number"],
            message="Sedang kami cek, owner akan follow up ya 🙏",
        )
        logger.info(
            "fallback_triggered",
            extra={
                "tenant_id": state["tenant_id"],
                "thread_id": state["thread_id"],
                "reason": fallback_reason,
                "sentiment": sentiment,
            },
        )
        return result
    except PhoneGatewayException as e:
        logger.error("fallback_send_failed", extra={"error": str(e)})
        return {"action": "error"}


def write_chat_log(state: ChatState) -> dict:
    """Persist chat log entry to SQLite. Best-effort, never raises."""
    try:
        from app.db.chat_log_repo import insert_chat_log

        insert_chat_log(
            thread_id=state["thread_id"],
            tenant_id=state["tenant_id"],
            wa_number=state["wa_number"],
            intent=state.get("intent"),
            confidence=state.get("confidence"),
            response=state.get("reply_text"),
            fallback_reason=state.get("fallback_reason"),
            status=state.get("action", "error"),
        )
    except Exception as e:  # noqa: BLE001
        logger.error("chat_log_insert_failed", extra={"error": str(e)})
    return {}