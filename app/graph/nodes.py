"""LangGraph nodes for OrderCloser Lite."""
import logging
from typing import Any

from app.graph.state import ChatState
from app.services.llm import LLMError

logger = logging.getLogger(__name__)


def classify_intent(state: ChatState, llm_client: Any) -> dict:
    """Classify user message into one of 4 intents.

    Returns dict update for state: {intent, confidence}
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
            },
        )
        return {"intent": result["intent"], "confidence": result["confidence"]}
    except LLMError as e:
        logger.error("intent_classification_failed", extra={"error": str(e)})
        raise


def lookup_catalog(state: ChatState, sheets_client: Any) -> dict:
    """Lookup answer in Sheets based on intent.

    For intent=faq: call sheets_client.lookup_faq()
    For intent=check_product: call sheets_client.read_catalog() and do simple keyword match
    Returns dict update: {catalog_answer, product_match} or empty dict if no match.
    """
    intent = state["intent"]

    try:
        if intent == "faq":
            match = sheets_client.lookup_faq(state["message_text"])
            if match is None:
                logger.info(
                    "faq_no_match",
                    extra={"tenant_id": state["tenant_id"], "thread_id": state["thread_id"]},
                )
                return {}
            return {"catalog_answer": match["jawaban"], "product_match": None}

        if intent == "check_product":
            products = sheets_client.read_catalog()
            message_lower = state["message_text"].lower()
            words = [w for w in message_lower.split() if len(w) >= 3]
            for product in products:
                nama = (product.get("nama_produk") or "").lower()
                if any(w in nama for w in words):
                    return {
                        "catalog_answer": None,
                        "product_match": product,
                    }
            return {}

        return {}
    except Exception as e:  # noqa: BLE001
        logger.error(
            "sheets_lookup_failed",
            extra={"tenant_id": state["tenant_id"], "error": str(e)},
        )
        return {}


def compose_reply(state: ChatState) -> dict:
    """Compose reply text from state. Returns {reply_text, action}."""
    intent = state["intent"]

    if intent == "faq":
        if state.get("catalog_answer"):
            return {
                "reply_text": f"{state['catalog_answer']}",
                "action": "reply",
            }
        return _compose_fallback_message(state, reason="no_faq_match")

    if intent == "check_product":
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
        return _compose_fallback_message(state, reason="no_product_match")

    if intent == "confirm_order":
        return {
            "reply_text": (
                "Terima kasih ordernya! Owner akan follow up untuk konfirmasi "
                "pembayaran ya 🙏"
            ),
            "action": "order",
        }

    return _compose_fallback_message(state, reason="unknown_intent")


def _compose_fallback_message(state: ChatState, reason: str) -> dict:
    return {
        "reply_text": "Sedang kami cek, owner akan follow up ya 🙏",
        "action": "fallback",
        "fallback_reason": reason,
    }


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

    Caller MUST have already set fallback_reason before calling.
    Returns {} on success, {action: "error"} on failure.
    """
    from app.services.phone_gateway import PhoneGatewayException  # Local import to avoid circular deps

    # Need owner_wa_number — but it's not in ChatState. Read from tenant repo.
    from app.db.tenant_repo import get_tenant

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
        f"Reason: {state.get('fallback_reason', 'n/a')}"
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
                "reason": state.get("fallback_reason"),
            },
        )
        return {}
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