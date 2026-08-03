"""LangGraph state schema."""
from datetime import datetime
from typing import Literal, TypedDict

Action = Literal["reply", "fallback", "order", "error"]
Intent = Literal["faq", "check_product", "confirm_order", "unclear"]


class ChatState(TypedDict, total=False):
    # Input
    tenant_id: str
    wa_number: str
    thread_id: str
    message_text: str
    timestamp: datetime

    # Conversation history (for multi-turn context)
    messages: list[dict[str, str]]  # [{"role": "user|assistant", "content": str}, ...]

    # Classify output
    intent: Intent
    confidence: float
    has_complaint_signal: bool
    sentiment: Literal["positive", "neutral", "negative"]

    # Lookup output
    catalog_answer: str | None
    product_match: dict | None
    match_kind: str | None  # "high" | "medium" | "none" — set by lookup_catalog

    # Compose output
    reply_text: str

    # Context analysis output (from analyze_customer_context)
    customer_context: dict | None  # {mapped_conditions, issue_type, primary_intent, confidence, reasoning}

    # Final action
    action: Action
    fallback_reason: str | None
    # FAQ lookup output (fast path)
    faq_match: str | None  # Set when FAQ lookup matches before LLM classify
