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
    blueprint_fallback: bool | None  # True when answered from industry blueprint
    photo_url: str | None  # Public URL of an uploaded product photo (Pro tier)

    # Compose output
    reply_text: str

    # Context analysis output (from analyze_customer_context)
    customer_context: dict | None  # {mapped_conditions, issue_type, primary_intent, confidence, reasoning}

    # Final action
    action: Action
    fallback_reason: str | None
    # FAQ lookup output (fast path)
    faq_match: str | None  # Set when FAQ lookup matches before LLM classify

    # Order capture output (intent=confirm_order path)
    order_id: int | None  # DB primary key of the captured order
    order_code: str | None  # Merchant-friendly reference code, e.g. "C-3F9D0A"
    order_items: list[dict] | None  # [{product, qty, price}]
    order_total: float | None

    # Order draft state (multi-turn order refinement)
    order_draft: list[dict] | None  # Draft items being built up: [{product, qty, price}]
    last_mentioned_product: str | None  # Product name from last check_product intent
