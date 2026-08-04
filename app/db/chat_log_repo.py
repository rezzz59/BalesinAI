"""Chat log repository."""
from datetime import datetime
from typing import Optional

from app.db.engine import get_session
from app.db.models import ChatLog


def list_chat_logs(
    tenant_id: str,
    thread_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """List chat log entries, newest first. thread_id optional (per-conversation)."""
    with get_session() as session:
        q = session.query(ChatLog).filter_by(tenant_id=tenant_id)
        if thread_id:
            q = q.filter_by(thread_id=thread_id)
        rows = (
            q.order_by(ChatLog.id.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [
            {
                "id": r.id,
                "thread_id": r.thread_id,
                "wa_number": r.wa_number,
                "intent": r.intent,
                "confidence": r.confidence,
                "response": r.response,
                "fallback_reason": r.fallback_reason,
                "status": r.status,
                "user_message": r.user_message,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
        ]


def list_threads(tenant_id: str, limit: int = 30) -> list[dict]:
    """List distinct recent conversations (one entry per thread), newest first."""
    with get_session() as session:
        rows = (
            session.query(ChatLog)
            .filter_by(tenant_id=tenant_id)
            .order_by(ChatLog.id.desc())
            .all()
        )
        seen: dict[str, dict] = {}
        for r in rows:
            if r.thread_id not in seen:
                seen[r.thread_id] = {
                    "thread_id": r.thread_id,
                    "wa_number": r.wa_number,
                    "last_message": r.user_message,
                    "last_response": r.response,
                    "intent": r.intent,
                    "status": r.status,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                }
            if len(seen) >= limit:
                break
        return list(seen.values())


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
