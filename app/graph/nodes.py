"""LangGraph nodes for OrderCloser Lite."""
import logging
import re
from typing import Any

from app.graph.state import ChatState
from app.services.llm import LLMError, LLMValidationError, validate_reply
from app.services.reply_validator import validate_sales_style
from app.services.semantic_search import SemanticSearchClient, SemanticSearchError
from app.services.sheets import FAQ_MATCH_THRESHOLD, _score_faq_row

logger = logging.getLogger(__name__)

# Deterministic confirm_order override: a message with a definite order verb
# PLUS a quantity is an order even when it ends with a price/total question
# (e.g. "mau pesan paket prasmanan a 100 porsi ... totalnya berapa ya?").
# The LLM sometimes classifies the trailing question as faq; this guard fixes
# that without touching genuine faq questions ("bisa pesan?", "cara order?").
_ORDER_VERBS = (
    "mau pesan", "saya pesan", "aku pesan", "kita pesan", "saya mau pesan",
    "mau order", "saya order", "aku order", "mau beli", "saya beli",
    "aku beli", "checkout", "booking",
)
_QTY_RE = re.compile(r"\d{1,3}\s*(?:porsi|pcs|unit|buah|biji|orang|pack|kotak|pax|kg|l)\b", re.IGNORECASE)


def _looks_like_order(message: str) -> bool:
    """True when a message states a definite order (verb + quantity).

    A verb negated by "belum" directly before it ("belum mau pesan",
    "belum mau beli") does not count — that is a price question, not an order.
    """
    msg = (message or "").lower()
    for v in _ORDER_VERBS:
        idx = msg.find(v)
        if idx == -1:
            continue
        if msg[max(0, idx - 8):idx].rstrip().endswith("belum"):
            continue
        if _QTY_RE.search(msg):
            return True
    return False


def _persona_for_tenant(tenant_id: str) -> str | None:
    """Resolve the store-persona instruction for a tenant's business_type.

    Best-effort: missing tenant or unknown business_type falls back to None so
    the generic compose prompt is used. Never raises.
    """
    try:
        from app.db.tenant_repo import get_tenant
        from app.graph.prompts import DEFAULT_PERSONA, PERSONA_TEMPLATES

        tenant = get_tenant(tenant_id)
        if tenant is None:
            return DEFAULT_PERSONA
        persona = PERSONA_TEMPLATES.get(tenant.get("business_type", "jualan"), DEFAULT_PERSONA)
        
        # Inject style profile and custom behavior if present
        import json as _json
        data = _json.loads(tenant.get("onboarding_data") or "{}")
        custom_behavior = data.get("custom_behavior", "").strip()
        
        if custom_behavior:
            persona = f"{persona}\n\nATURAN KHUSUS TOKO:\n{custom_behavior}"
            
        knowledge_text = data.get("knowledge_text", "").strip()
        if knowledge_text:
            persona = f"{persona}\n\nINFORMASI TAMBAHAN (SOP/FAQ):\n{knowledge_text}"
            
        welcome_message = data.get("welcome_message", "").strip()
        if welcome_message:
            persona = f"{persona}\n\nATURAN WELCOME MESSAGE:\nJika ini adalah chat pertama dari pelanggan (belum ada histori percakapan sebelumnya), Anda WAJIB mengawali balasan Anda dengan kalimat sapaan berikut persis seperti ini: \"{welcome_message}\""
            
        style = _style_profile_block(tenant)
        if style:
            persona = f"{persona}\n\n{style}"
        return persona
    except Exception as e:  # noqa: BLE001
        logger.warning("persona_resolve_failed", extra={"tenant_id": tenant_id, "error": str(e)})
        return None


def _style_profile_block(tenant: dict) -> str:
    """Build a 'gaya bicara toko' instruction block from the stored style_profile."""
    import json as _json

    try:
        data = _json.loads(tenant.get("onboarding_data") or "{}")
        sp = data.get("style_profile") or {}
        sp = sp.get("style_profile") if isinstance(sp, dict) else None
        if not isinstance(sp, dict):
            return ""
    except (ValueError, TypeError):
        return ""

    labels = [
        ("formality", "Tingkat formalitas"),
        ("emoji_density", "Penggunaan emoji"),
        ("sentence_length", "Panjang kalimat"),
        ("tone", "Nada bicara"),
    ]
    parts = [
        f"- {label}: {sp[k]}"
        for k, label in labels
        if isinstance(sp.get(k), str) and sp[k]
    ]
    phrases = [p for p in (sp.get("key_phrases") or []) if isinstance(p, str) and p.strip()]
    if phrases:
        parts.append("- Frasa khas: " + ", ".join(f'"{p}"' for p in phrases[:4]))
    if not parts:
        return ""
    return "GAYA BICARA TOKO (tiru gaya ini dalam setiap balasan):\n" + "\n".join(parts)


def _to_match_kind(score: float) -> str:
    """Bucket an overlap score into high/medium/none for downstream grading.

    Uses thresholds (0.5 high, otherwise >0 medium) so a 1/2 overlap (0.5)
    counts as a high-confidence FAQ match, appropriate when the buyer asks a
    short, specific question.
    """
    if score >= 0.5:
        return "high"
    if score > 0.0:
        return "medium"
    return "none"


def _lookup_blueprint_faq(message: str, tenant_id: str) -> dict | None:
    """Best-effort match a buyer question against the industry blueprint FAQ.

    Only fires when the tenant's own sheet had no FAQ match. Looks up the
    tenant's business_type, then scores the message against that industry's
    generic FAQ rows. Returns the best matching row above FAQ_MATCH_THRESHOLD,
    or None. Never raises.
    """
    try:
        from app.data.blueprints import BLUEPRINT_FAQS
        from app.db.tenant_repo import get_tenant
        from app.services.sheets import FAQ_MATCH_THRESHOLD, _score_faq_row

        tenant = get_tenant(tenant_id)
        if tenant is None:
            return None
        bt = (tenant.get("business_type") or "jualan").strip().lower()
        rows = BLUEPRINT_FAQS.get(bt) or BLUEPRINT_FAQS["jualan"]
        best: dict | None = None
        best_score = 0.0
        for row in rows:
            score = _score_faq_row(message, row)
            if score > best_score:
                best_score = score
                best = row
        if best is not None and best_score >= FAQ_MATCH_THRESHOLD:
            return best
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("blueprint_faq_failed", extra={"tenant_id": tenant_id, "error": str(e)})
        return None


def fallback_reason_for(state: ChatState, threshold: float | None = None) -> str | None:
    """Derive a fallback_reason code from state, or None if no fallback applies.

    Priority order:
      1. complaint_signal — buyer escalation/escalation risk
      2. objection_signal — buyer hesitation on price/cost
      3. unclear — intent not classifiable
      4. low_confidence — below intent_confidence_threshold
      5. no_faq_match — FAQ lookup returned nothing (intent=faq)
      6. no_product_match — product lookup returned nothing (intent=check_product)

    Only one reason per call. Higher-priority reason wins.
    """
    from app.config import get_settings

    if threshold is None:
        threshold = get_settings().intent_confidence_threshold

    if state.get("has_complaint_signal"):
        return "complaint_signal"
    if state.get("has_objection_signal"):
        return "objection_signal"
    if state.get("intent") == "unclear":
        return "unclear"
    if state.get("confidence", 0.0) < threshold:
        return "low_confidence"

    intent = state.get("intent")
    # faq doesn't instantly fallback anymore, LLM will handle it via knowledge_text
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
    
    if stripped_message.startswith("__SYSTEM_AUTO_FOLLOWUP__"):
        return {
            "intent": "auto_followup",
            "confidence": 1.0,
            "has_complaint_signal": False,
            "has_objection_signal": False,
            "sentiment": "neutral",
        }
        
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
            "has_objection_signal": False,
            "sentiment": "neutral",
        }

    try:
        # Pass full conversation history so LLM can leverage multi-turn context.
        # Ensure the current message is part of the history — on turn 1 the
        # history starts empty, and without the current message some backends
        # (AdaCode) would receive an empty request.
        messages = [m for m in (state.get("messages") or []) if isinstance(m, dict)]
        current_message = state.get("message_text", "")
        if current_message:
            if not messages or messages[-1].get("content") != current_message:
                messages = messages + [{"role": "user", "content": current_message}]
        result = llm_client.classify_with_history(messages)
        logger.info(
            "intent_classified",
            extra={
                "tenant_id": state["tenant_id"],
                "intent": result["intent"],
                "confidence": result["confidence"],
                "has_complaint_signal": result.get("has_complaint_signal", False),
                "has_objection_signal": result.get("has_objection_signal", False),
                "history_turns": len(messages),
            },
        )
        intent = result["intent"]
        if intent == "faq" and _looks_like_order(state.get("message_text", "")):
            intent = "confirm_order"
            result["confidence"] = max(result["confidence"], 0.9)
            logger.info(
                "order_intent_override",
                extra={"tenant_id": state["tenant_id"], "thread_id": state["thread_id"]},
            )
        return {
            "intent": intent,
            "confidence": result["confidence"],
            "has_complaint_signal": result.get("has_complaint_signal", False),
            "has_objection_signal": result.get("has_objection_signal", False),
            "sentiment": result.get("sentiment", "neutral"),
        }
    except LLMError as e:
        logger.error("intent_classification_failed", extra={"error": str(e)})
        raise


def _find_photo_url(tenant_id: str, product_name: str) -> str | None:
    """Look for an uploaded product photo whose filename matches the product name.

    Photos live in data/media/<tenant>/<slug>__<token>.<ext>. We match by slugging
    the product name and scanning filenames, returning a public URL (BASE_URL +
    path) that Fonnte can fetch to deliver an actual image to the buyer.
    Returns None if no photo is found (text-only reply).
    """
    import glob
    import os

    from app.config import get_settings

    if not product_name:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", str(product_name).strip().lower()).strip("-")
    if not slug:
        return None

    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    folder = os.path.join(base, "data", "media", tenant_id)
    pattern = os.path.join(folder, f"{slug}__*")
    matches = glob.glob(os.path.join(folder, f"{slug}.*")) + glob.glob(pattern)
    if not matches:
        return None
    filename = os.path.basename(matches[0])
    settings = get_settings()
    return f"{settings.base_url}/media/{tenant_id}/{filename}"


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
                # If FAQ yields no match, try searching the catalog. 
                # RAG strategy: the answer to "berapa harga kemeja?" is in the catalog row.
                products = sheets_client.read_catalog()
                best_cat_score = 0.0
                best_cat_product = None
                for product in products:
                    score = _score_faq_row(state["message_text"], product)
                    if score > best_cat_score:
                        best_cat_score = score
                        best_cat_product = product
                if best_cat_product is not None and best_cat_score >= FAQ_MATCH_THRESHOLD:
                    # RAG hybrid: use product catalog to answer FAQ (e.g. "harga kemeja?")
                    return {
                        "catalog_answer": None,
                        "product_match": best_cat_product,
                        "match_kind": _to_match_kind(best_cat_score),
                    }
                
                # Fall back to the industry blueprint (generic FAQ) so a store
                # that hasn't filled its sheet yet can still answer common
                # questions. Blueprint answers are deliberately generic and
                # never reference store-specific products/prices.
                blueprint_match = _lookup_blueprint_faq(state["message_text"], state["tenant_id"])
                if blueprint_match is not None:
                    score = _score_faq_row(state["message_text"], blueprint_match)
                    return {
                        "catalog_answer": blueprint_match["jawaban"],
                        "product_match": None,
                        "match_kind": _to_match_kind(score),
                        "blueprint_fallback": True,
                    }
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
                    "last_mentioned_product": best_product.get("nama_produk"),
                    "photo_url": _find_photo_url(state["tenant_id"], best_product.get("nama_produk", "")),
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
    persona = _persona_for_tenant(state["tenant_id"])

    # 1. Order confirmation: short template, no LLM.
    if intent == "confirm_order":
        reply = (
            "Order Kakak kami catat, terima kasih banyak! 🎉 "
            "Tim kami akan konfirmasi detailnya segera ya. "
            "Boleh tahu metode bayarnya mau pakai apa, Kak — transfer atau e-wallet? 😊"
        )
        # Append user message to history, then add assistant reply
        messages = state.get("messages", []) or []
        return {
            "reply_text": reply,
            "action": "order",
            "messages": messages + [{"role": "user", "content": state["message_text"]}, {"role": "assistant", "content": reply}],
        }
        
    if intent == "auto_followup":
        # The prompt is embedded in the message_text after the prefix
        msg = state.get("message_text", "")
        followup_prompt = msg.replace("__SYSTEM_AUTO_FOLLOWUP__", "").strip()
        sys_prompt = (
            "KONTEKS: Pelanggan tidak membalas pesan terakhir Anda selama beberapa waktu.\n"
            "TUGAS: Kirimkan SATU pesan follow-up yang ramah dan sopan untuk menarik kembali minat mereka.\n"
            f"INSTRUKSI KHUSUS DARI OWNER: {followup_prompt}\n\n"
            "Hard constraints:\n"
            "- JANGAN membahas hal teknis, cukup menyapa dengan ramah.\n"
            "- Balas dengan ringkas (1-2 kalimat pendek) namun luwes dan natural.\n"
            "- Gunakan sapaan 'Kak' dan kata ganti 'kami'."
        )
        try:
            reply = llm_client.compose_reply_with_history(
                messages=state.get("messages", []) or [],
                message="[SYSTEM] Buat pesan follow-up sekarang.",
                retrieved_row=None,
                match_kind="none",
                customer_context=None,
                persona=(persona or "") + "\n\n" + sys_prompt,
            )
            return {
                "reply_text": reply,
                "action": "reply",
                "messages": (state.get("messages", []) or []) + [
                    {"role": "assistant", "content": reply},
                ],
            }
        except Exception as e:
            logger.warning("followup_compose_failed", extra={"tenant_id": state["tenant_id"], "error": str(e)})
            return {"reply_text": "", "action": "error"}

    message = state["message_text"]
    strict_hint = (
        "\n\n[Strict hint: your previous reply contained facts not in our catalog. "
        "Restrict your reply to ONLY facts from the source row above. Do not invent "
        "prices, sizes, colors, or stock status.]"
    )
    style_hint = (
        "\n\n[Style hint: your reply must END with exactly ONE guiding question that "
        "invites the buyer to reply (and no more than one question in total). Never "
        "end with a plain statement, a price list, or passive thanks — otherwise the "
        "buyer will stop replying (ghosting). If the buyer already named a size, color, "
        "or variant, do NOT ask them to choose it again — acknowledge their choice and "
        "only ask the open detail that is still unknown.]"
    )

    # 2-5. Try up to 2 attempts (initial + 1 retry) before falling back.
    retry_hint = strict_hint
    for attempt in range(2):
        try:
            message_for_call = message if attempt == 0 else f"{message}{retry_hint}"
            reply = llm_client.compose_reply_with_history(
                messages=state.get("messages", []) or [],
                message=message_for_call,
                retrieved_row=retrieved_row,
                match_kind=match_kind,
                customer_context=customer_context,  # Pass customer context for context-aware replies
                persona=persona,  # Store-persona instruction per business_type
            )
            validate_reply(reply, retrieved_row)
            ok_style, style_msg = validate_sales_style(reply, message)
            if not ok_style:
                raise LLMValidationError(f"Sales style: {style_msg}")
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
            if "question" in str(e) or "emoji" in str(e) or "sentences" in str(e) or "listener" in str(e):
                retry_hint = style_hint
            logger.warning(
                "compose_validation_failed",
                extra={
                    "tenant_id": state["tenant_id"],
                    "attempt": attempt,
                    "error": str(e),
                },
            )
            print("VALIDATION ERROR:", str(e))
            print("REPLY WAS:", reply)
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
                f"Halo Kak, berikut info yang kami punya ya 😊\n\n"
                f"{state['catalog_answer']}\n\n"
                f"Kalau masih ada yang ingin ditanyakan, silakan sampaikan saja Kak — "
                f"kami cek dulu ke tim. Sekalian, Kakak sedang cari produk apa?"
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
        "reply_text": (
            "Mohon tunggu sebentar ya Kak, kami cek dulu ke tim. 😊 "
            "Sambil menunggu, boleh kami bantu cari yang lain?"
        ),
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
    lines.append(f"Total ada {total} varian ready. Mau dibantu cari yang mana, Kak? 😊")
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

    If a product photo_url was matched and the tenant is on the Pro/Enterprise
    tier, the photo is delivered first as an actual image (Fonnte `url`
    attachment) followed by the text reply. Basic tier stays text-only.

    Uses duck typing: client must have send_message(phone, message) and
    send_attachment(phone, url, caption) methods.
    Raises PhoneGatewayException if there's an error after retries.

    Returns {action: "error"} on failure.
    """
    from app.services.phone_gateway import (
        PhoneGatewayException,  # Local import to avoid circular deps
    )

    photo_url = state.get("photo_url")
    if photo_url:
        try:
            from app.db.tenant_repo import get_tenant

            tenant = get_tenant(state["tenant_id"])
            tier = (tenant or {}).get("tier", "basic")
            if tier in ("pro", "enterprise"):
                await gateway_client.send_attachment(
                    phone=state["wa_number"],
                    image_url=photo_url,
                    caption=state["reply_text"],
                )
                logger.info(
                    "whatsapp_sent_with_photo",
                    extra={"tenant_id": state["tenant_id"], "thread_id": state["thread_id"]},
                )
                return {}

        except Exception as e:  # noqa: BLE001
            logger.warning("whatsapp_photo_failed", extra={"tenant_id": state["tenant_id"], "error": str(e)})
            # fall through to text-only if the attachment path fails

    try:
        intro = ""
        history = state.get("messages") or []
        if not history:
            # First turn in this thread — introduce the virtual assistant once
            # (no privacy disclaimer, just a natural opener).
            intro = "Halo kak 👋 Saya asisten virtual dari toko ini. Langsung tanya saja produk, harga, atau stok ya ✨\n\n"
        await gateway_client.send_message(
            phone=state["wa_number"],
            message=intro + state["reply_text"],
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


def _notify_target(tenant: dict) -> str:
    """Resolve where owner notifications go: a personal WA number OR a group ID.

    Both are stored in owner_wa_number and passed through to the gateway as-is
    (Fonnte accepts either). Empty never happens for real tenants.
    """
    return (tenant.get("owner_wa_number") or "").strip()


def _digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _norm_wa(value: str) -> str:
    """Normalize a WA number to the international (62...) digit form.

    Handles '08...', '8...', '+628...', '628...' and strips any punctuation.
    Group IDs (all digits, no leading 0/62) pass through unchanged.
    """
    digits = _digits_only(value)
    if digits.startswith("0"):
        return "62" + digits[1:]
    return digits


def _is_self_notify(tenant: dict, target: str) -> bool:
    """True when the notification target IS the bot's own device number.

    If the admin runs the bot on their personal number and also sets it as the
    owner notification target, WhatsApp would notify itself. In that case we
    skip the WhatsApp owner message (the admin already sees the thread) and
    rely on the dashboard + chat log. Group IDs never collide with a device
    number, so a plain normalized-equality check is sufficient.
    """
    device_id = (tenant.get("fonnte_device_id") or "").strip()
    if not device_id or not target:
        return False
    return _norm_wa(device_id) == _norm_wa(target)


def _compose_owner_fallback_message(state: ChatState, fallback_reason: str, sentiment: str) -> str:
    """Build a plain-language WhatsApp notification for the owner.

    No technical jargon — the owner should understand at a glance why the bot
    couldn't handle the message and what to do next. Reason/category text is
    hardcoded to the few known values so it never reads robotic.
    """
    reason_text = {
        "unclear": "pesannya tidak masuk kategori pertanyaan biasa, jadi bot menyerahkannya ke Anda",
        "low_confidence": "bot tidak yakin memahami maksudnya, jadi lebih aman diserahkan ke Anda",
        "complaint_signal": "pelanggan tampak tidak senang/kecewa, sebaiknya segera Anda tangani",
        "objection_signal": "pelanggan ragu pada harga/biaya, sebaiknya Anda bantu pertimbangkan",
        "no_faq_match": "pertanyaannya belum ada di data jawaban yang tersedia",
        "no_product_match": "produk yang ditanyakan tidak ditemukan di katalog",
    }.get(fallback_reason, "bot belum bisa menjawabnya secara otomatis")

    intent_text = {
        "faq": "pertanyaan umum",
        "check_product": "pertanyaan tentang produk",
        "confirm_order": "pemesanan",
        "unclear": "pesan yang tidak jelas",
    }.get(state.get("intent", ""), "pesan")

    sentiment_text = {
        "negative": "pelanggan terkesan kurang puas",
        "positive": "pelanggan tampak ramah/positif",
        "neutral": "pelanggan bersikap netral",
    }.get(sentiment, "sentimen tidak terdeteksi")

    return (
        f"Ada pesan yang perlu Anda balas manual ya Kak 🙏\n\n"
        f"Pelanggan: {state['wa_number']}\n"
        f'Pesan: "{state["message_text"]}"\n\n'
        f"Alasan bot menyerahkannya: {reason_text}.\n\n"
        f"Jenis pesan: {intent_text}.\n"
        f"Catatan: {sentiment_text}.\n\n"
        f"Silakan balas langsung ke pelanggan di WhatsApp."
    )


async def fallback_human(state: ChatState, gateway_client: Any) -> dict:
    """Forward original message to owner via WhatsApp gateway. Also sends buyer acknowledgement.

    Uses duck typing: client must have send_message(phone, message) method.
    Raises PhoneGatewayException if there's an error after retries.

    If fallback_reason is not yet on state, derives it via fallback_reason_for().
    Returns {} on success, {action: "error"} on failure.

    Owner notification target = owner_wa_number (personal number OR group ID).
    Skipped when the target is the bot's own device (self-notify guard) — the
    admin already sees the buyer thread on that device, so only the buyer
    acknowledgement is sent and the thread is flagged for the dashboard.
    """
    # Need owner_wa_number — but it's not in ChatState. Read from tenant repo.
    from app.db.tenant_repo import get_tenant
    from app.services.phone_gateway import (
        PhoneGatewayException,  # Local import to avoid circular deps
    )

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

    owner_msg = _compose_owner_fallback_message(state, fallback_reason, sentiment)

    target = _notify_target(tenant)
    self_notify = _is_self_notify(tenant, target)

    try:
        # 1. Send to owner (skipped when the target is the bot's own device)
        if not self_notify:
            await gateway_client.send_message(
                phone=target,
                message=owner_msg,
            )
        # 2. Send acknowledgement to buyer
        if state.get("has_complaint_signal"):
            buyer_ack = (
                "Mohon maaf ya Kak atas ketidaknyamanannya 🙏 Kami cek dulu ke tim. "
                "Boleh dibantu, solusi seperti apa yang Kakak harapkan?"
            )
        elif state.get("has_objection_signal"):
            buyer_ack = (
                "Baik Kak, kami bantu pertimbangkan dulu ya 🙏 Boleh kami tahu, kira-kira "
                "budget Kakak di angka berapa? Nanti kami carikan opsi yang paling pas."
            )
        else:
            buyer_ack = (
                "Mohon tunggu sebentar ya Kak, kami cek dulu ke tim. 😊 "
                "Sambil menunggu, boleh kami bantu cari yang lain?"
            )
        await gateway_client.send_message(
            phone=state["wa_number"],
            message=buyer_ack,
        )
        logger.info(
            "fallback_triggered",
            extra={
                "tenant_id": state["tenant_id"],
                "thread_id": state["thread_id"],
                "reason": fallback_reason,
                "sentiment": sentiment,
                "self_notify": self_notify,
            },
        )
        return result
    except PhoneGatewayException as e:
        logger.error("fallback_send_failed", extra={"error": str(e)})
        return {"action": "error"}


async def capture_order(
    state: ChatState,
    sheets_client: Any,
    gateway_client: Any,
    persist_orders: bool = True,
) -> dict:
    """Extract, persist, and acknowledge an incoming order.

    Runs on intent == confirm_order. Steps:
      1. Read catalog + extract items/qty/price + buyer info (no LLM).
      2. If persist_orders, store the order in the orders table (best-effort).
      3. Notify the owner with a structured order summary (best-effort).
      4. Set reply_text = buyer confirmation with item list + total.

    Returns state updates: {reply_text, action:"order", order_id, order_code,
    order_items, order_total}. Never raises — on any failure it still produces a
    friendly acknowledgment and, when items couldn't be parsed, the owner is
    notified to follow up.
    """
    from app.services.order_extractor import (
        compute_total,
        extract_buyer_info,
        extract_items,
        merge_items,
    )

    tenant_id = state["tenant_id"]
    message = state.get("message_text", "") or ""

    # Carry the running order draft from previous turns so a buyer can refine
    # an order across messages ("saya mau kaos hitam" → "tambah hoodie 1").
    draft = [dict(i) for i in (state.get("order_draft") or [])]

    items: list[dict] = []
    buyer_name: str | None = None
    buyer_address: str | None = None
    total: float | None = None
    order_id: int | None = None
    order_code: str | None = None
    catering_meta: dict | None = None

    from app.db.tenant_repo import get_tenant as _get_tenant

    _tenant = _get_tenant(tenant_id)
    business_type = (_tenant or {}).get("business_type", "jualan")

    try:
        catalog = sheets_client.read_catalog() if persist_orders or True else []
        new_items = extract_items(message, catalog)
        items = merge_items(draft, new_items) if new_items else draft
        buyer_name, buyer_address = extract_buyer_info(message)
        total = compute_total(items)

        # Catering: add ongkir + DP + min-order + event-date rules.
        if business_type == "kuliner":
            from app.services.business_rules import catering_quote

            ongkir_rows = []
            try:
                ongkir_rows = sheets_client.read_ongkir()
            except Exception:  # noqa: BLE001
                ongkir_rows = []
            catering_meta = catering_quote(items, ongkir_rows, message)
            total = catering_meta["total"]
    except Exception as e:  # noqa: BLE001
        logger.error(
            "order_extraction_failed",
            extra={"tenant_id": tenant_id, "error": str(e)},
        )
        items, buyer_name, buyer_address, total = [], None, None, None

    # --- Order state machine: "diterima" only when every required field is in.
    # Anything less is a CONSULTATION reply (quote + ask the missing field) and
    # is never persisted as an order.
    size = (items[0].get("size") if items else None) or None
    color = (items[0].get("color") if items else None) or None
    if business_type == "kuliner":
        complete = bool(
            items
            and catering_meta
            and not catering_meta.get("needs_date")
            and catering_meta.get("min_order_gap", 0) == 0
        )
    elif business_type == "fashion":
        complete = bool(items) and bool(size) and bool(color) and all((i.get("qty") or 0) >= 1 for i in items)
    else:
        complete = bool(items)

    if complete:
        # Persist (best-effort) when enabled. Dry-run (test-chat) skips writes.
        try:
            from app.db.order_repo import insert_order

            stored = insert_order(
                tenant_id=tenant_id,
                thread_id=state["thread_id"],
                wa_number=state["wa_number"],
                items=items,
                total=total,
                buyer_name=buyer_name,
                buyer_address=buyer_address,
                raw_message=message,
                status="pending",
            )
            order_id = stored["id"]
            order_code = stored["order_code"]
            logger.info(
                "order_captured",
                extra={"tenant_id": tenant_id, "order_id": order_id, "order_code": order_code},
            )
        except Exception as e:  # noqa: BLE001
            logger.error("order_insert_failed", extra={"tenant_id": tenant_id, "error": str(e)})

        # Owner notification (best-effort, only when persisting real orders).
        # Skipped when the target is the bot's own device (self-notify guard).
        if persist_orders:
            try:
                tenant = get_tenant(tenant_id)
                if tenant is not None and not _is_self_notify(tenant, _notify_target(tenant)):
                    owner_msg = _format_owner_order_message(
                        state, items, total, buyer_name, buyer_address, order_code
                    )
                    await gateway_client.send_message(
                        phone=_notify_target(tenant),
                        message=owner_msg,
                    )
            except Exception as e:  # noqa: BLE001
                logger.error("order_owner_notify_failed", extra={"tenant_id": tenant_id, "error": str(e)})

    if catering_meta:
        from app.services.business_rules import format_catering_reply

        reply = format_catering_reply(catering_meta, items, confirmed=complete)
    elif complete:
        reply = _format_order_confirmation(
            message, items, total, buyer_name, buyer_address, order_code
        )
    else:
        reply = _format_order_consultation(items, size, color, business_type)
    return {
        "reply_text": reply,
        "action": "order" if complete else "reply",
        "order_id": order_id,
        "order_code": order_code,
        "order_items": items if complete else [],
        "order_total": total if complete else None,
        "order_draft": items if items else [],
        "catering_meta": catering_meta,
    }


def _format_price(price: float | None) -> str:
    if price is None:
        return "Rp ?"
    if price == int(price):
        return f"Rp {int(price):,}".replace(",", ".")
    return f"Rp {price:,.2f}".replace(",", ".")


def _format_order_confirmation(
    message: str,
    items: list[dict],
    total: float | None,
    buyer_name: str | None,
    buyer_address: str | None,
    order_code: str | None,
) -> str:
    """Buyer-facing acknowledgment for a COMPLETE order. If nothing was
    extracted (shouldn't happen — incomplete orders go to consultation), ask."""
    ref = f" ({order_code})" if order_code else ""
    if not items:
        return "Boleh disebutkan Kak, mau pesan yang mana dan berapa banyak?"
    lines = [f"Order diterima{ref}! 🎉", ""]
    for it in items:
        qty = it.get("qty", 1)
        price = it.get("price")
        variant = _variant_suffix(it)
        subtotal = _format_price(price * qty) if price is not None else None
        lines.append(f"• {it['product']}{variant} x{qty}" + (f" = {subtotal}" if subtotal else ""))
    if total is not None:
        lines.append("")
        lines.append(f"Total: {_format_price(total)}")
    if buyer_name:
        lines.append("")
        lines.append(f"Nama: {buyer_name}")
    if buyer_address:
        lines.append(f"Alamat: {buyer_address}")
    lines.append("")
    lines.append(
        "Order sudah kami catat, Kak 🙏 Tim kami akan konfirmasi pesanannya. "
        "Boleh tahu, Kakak mau bayar dengan metode apa — transfer atau e-wallet? 😊"
    )
    return "\n".join(lines)


def _variant_suffix(item: dict) -> str:
    """' (size L, hitam)' for a fashion item when the buyer named variants."""
    parts = [f"size {item['size']}" if item.get("size") else None,
             item.get("color") if item.get("color") else None]
    parts = [p for p in parts if p]
    return f" ({', '.join(parts)})" if parts else ""


def _format_order_consultation(
    items: list[dict],
    size: str | None,
    color: str | None,
    business_type: str,
) -> str:
    """CONSULTATION reply for an incomplete order — never 'diterima', never
    persisted. Asks only for the field that is actually missing."""
    if not items:
        if business_type == "kuliner":
            return "Boleh disebutkan Kak, mau pesan paket yang mana dan berapa porsi?"
        return "Boleh disebutkan Kak, mau pesan yang mana dan berapa banyak?"
    
    if business_type == "fashion":
        if not size and not color:
            return (
                f"Baik Kak, untuk {items[0]['product']}nya. "
                "Biar kami bantu siapkan, boleh diisi format ini ya Kak:\n\n"
                "Ukuran:\n"
                "Warna:\n"
                "Jumlah:\n"
            )
        if not size:
            return f"Untuk {items[0]['product']}nya mau ukuran apa ya, Kak?"
        if not color:
            return f"Untuk {items[0]['product']}nya mau warna apa ya, Kak?"
            
    if business_type == "kuliner":
        return (
            "Siap Kak! Untuk pesanannya, boleh dilengkapi dengan format ini ya:\n\n"
            "Pesanan & Jumlah:\n"
            "Tanggal Acara:\n"
            "Alamat Pengiriman:\n"
        )
        
    return "Untuk pesanannya, boleh dilengkapi dulu detailnya ya Kak, biar kami siapkan dengan benar."


def _format_owner_order_message(
    state: ChatState,
    items: list[dict],
    total: float | None,
    buyer_name: str | None,
    buyer_address: str | None,
    order_code: str | None,
) -> str:
    """Owner-facing structured order summary sent over WhatsApp."""
    ref = order_code or "-"
    lines = [f"🧾 ORDER BARU {ref}", f"Pelanggan: {state['wa_number']}", ""]
    if not items:
        lines.append("⚠️ Produk tidak bisa dideteksi otomatis:")
        lines.append(state.get("message_text", ""))
    else:
        for it in items:
            qty = it.get("qty", 1)
            price = it.get("price")
            subtotal = _format_price(price * qty) if price is not None else None
            lines.append(f"• {it['product']} x{qty}" + (f" = {subtotal}" if subtotal else ""))
        if total is not None:
            lines.append("")
            lines.append(f"Total: {_format_price(total)}")
    if buyer_name:
        lines.append(f"Nama: {buyer_name}")
    if buyer_address:
        lines.append(f"Alamat: {buyer_address}")
    lines.append("")
    lines.append(f"Pesan asli: {state.get('message_text', '')}")
    return "\n".join(lines)


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
            user_message=state.get("message_text"),
            status=state.get("action") or "error",
        )
    except Exception as e:  # noqa: BLE001
        logger.error("chat_log_insert_failed", extra={"error": str(e)})
    return {}

