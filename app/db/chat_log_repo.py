"""Chat log repository."""
from datetime import datetime
from typing import Optional

from app.db.engine import get_session
from app.db.models import ChatLog


def insert_chat_log(
    thread_id: str,
    tenant_id: str,
    wa_number: str,
    status: str,
    intent: Optional[str] = None,
    confidence: Optional[float] = None,
    response: Optional[str] = None,
    fallback_reason: Optional[str] = None,
    user_message: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> int:
    """Insert a chat log entry. Returns the new row id."""
    with get_session() as session:
        log = ChatLog(
            thread_id=thread_id,
            tenant_id=tenant_id,
            wa_number=wa_number,
            intent=intent,
            confidence=confidence,
            response=response,
            fallback_reason=fallback_reason,
            user_message=user_message,
            status=status,
            timestamp=timestamp or datetime.utcnow(),
        )
        session.add(log)
        session.commit()
        return log.id
