"""Per-conversation memory repository.

Powers multi-turn flows (Fase 3): a thread can carry state across messages —
the running order draft, the last product mentioned, etc. This is app-level
memory keyed by (tenant_id, thread_id), independent of the graph checkpointer,
so it works reliably across webhook invocations.
"""
import json
import logging
from typing import Any

from app.db.engine import get_session
from app.db.models import ConversationState

logger = logging.getLogger(__name__)


def get_conversation_state(tenant_id: str, thread_id: str) -> dict[str, Any]:
    """Return the saved conversation payload for a thread, or {} if none."""
    try:
        with get_session() as session:
            row = session.get(ConversationState, (tenant_id, thread_id))
            if row is None:
                return {}
            data = json.loads(row.data or "{}")
            return data if isinstance(data, dict) else {}
    except Exception as e:  # noqa: BLE001
        logger.error("conv_state_get_failed", extra={"tenant_id": tenant_id, "thread_id": thread_id, "error": str(e)})
        return {}


def save_conversation_state(tenant_id: str, thread_id: str, data: dict[str, Any]) -> None:
    """Upsert the conversation payload for a thread. Best-effort, never raises."""
    try:
        payload = json.dumps(data or {}, ensure_ascii=False)
        with get_session() as session:
            row = session.get(ConversationState, (tenant_id, thread_id))
            if row is None:
                session.add(
                    ConversationState(tenant_id=tenant_id, thread_id=thread_id, data=payload)
                )
            else:
                row.data = payload
            session.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("conv_state_save_failed", extra={"tenant_id": tenant_id, "thread_id": thread_id, "error": str(e)})


def merge_conversation_state(tenant_id: str, thread_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Load thread state, apply updates on top, save, and return the merged dict."""
    current = get_conversation_state(tenant_id, thread_id)
    merged = {**current, **updates}
    save_conversation_state(tenant_id, thread_id, merged)
    return merged


def clear_conversation_state(tenant_id: str, thread_id: str) -> None:
    """Remove all saved state for a thread."""
    try:
        with get_session() as session:
            row = session.get(ConversationState, (tenant_id, thread_id))
            if row is not None:
                session.delete(row)
                session.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("conv_state_clear_failed", extra={"tenant_id": tenant_id, "thread_id": thread_id, "error": str(e)})
