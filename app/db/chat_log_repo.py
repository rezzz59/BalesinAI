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
    """List distinct recent conversations (one entry per thread), newest first.

    Each entry includes `needs_attention`: True when the last exchange is a
    fallback/complaint, or the last inbound message has no bot response yet —
    i.e. an admin may need to answer. Used by the web inbox to pre-filter
    "perlu dibalas" without the admin checking each thread.
    """
    with get_session() as session:
        rows = (
            session.query(ChatLog)
            .filter_by(tenant_id=tenant_id)
            .order_by(ChatLog.id.asc())
            .all()
        )
        seen: dict[str, dict] = {}
        for r in rows:
            cur = seen.get(r.thread_id)
            if cur is None:
                cur = {
                    "thread_id": r.thread_id,
                    "wa_number": r.wa_number,
                    "last_message": None,
                    "last_response": None,
                    "intent": r.intent,
                    "status": r.status,
                    "fallback_reason": r.fallback_reason,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "needs_attention": False,
                }
                seen[r.thread_id] = cur
            # Track the most recent inbound message and its bot response.
            if r.user_message:
                cur["last_message"] = r.user_message
                cur["intent"] = r.intent
                cur["status"] = r.status
                cur["fallback_reason"] = r.fallback_reason
                cur["timestamp"] = r.timestamp.isoformat() if r.timestamp else None
            if r.response:
                cur["last_response"] = r.response
            # Mark attention when the bot asked the owner to step in.
            if r.status == "fallback" or (r.fallback_reason and r.fallback_reason != "no_match" and r.fallback_reason != "n/a"):
                cur["needs_attention"] = True
            # Or when the latest inbound message has no bot response yet.
            if r.user_message and not r.response and r.status in ("reply", "fallback", "order"):
                cur["needs_attention"] = True
            if len(seen) >= limit * 2:  # keep iterating to fill attention flags
                continue
        # Trim to limit, newest first.
        ordered = sorted(seen.values(), key=lambda t: t["timestamp"] or "", reverse=True)
        return ordered[:limit]


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
