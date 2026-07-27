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

    # Classify output
    intent: Intent
    confidence: float

    # Lookup output
    catalog_answer: str | None
    product_match: dict | None

    # Compose output
    reply_text: str

    # Final action
    action: Action
    fallback_reason: str | None