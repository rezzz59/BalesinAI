"""Order repository — persistence for captured buyer orders."""
import json
import secrets
from datetime import datetime, timezone
from typing import Any

from app.db.engine import get_session
from app.db.models import Order


def generate_order_code() -> str:
    """Return a short, merchant-friendly, collision-resistant order reference."""
    return "C-" + secrets.token_hex(3).upper()


def insert_order(
    tenant_id: str,
    thread_id: str,
    wa_number: str,
    items: list[dict],
    total: float | None = None,
    buyer_name: str | None = None,
    buyer_address: str | None = None,
    notes: str | None = None,
    raw_message: str | None = None,
    status: str = "pending",
    order_code: str | None = None,
) -> dict:
    """Persist a new order. Returns the stored order dict (includes id + order_code)."""
    order_code = order_code or generate_order_code()
    with get_session() as session:
        order = Order(
            tenant_id=tenant_id,
            thread_id=thread_id,
            wa_number=wa_number,
            order_code=order_code,
            items=json.dumps(items or [], ensure_ascii=False),
            total=total,
            buyer_name=buyer_name,
            buyer_address=buyer_address,
            notes=notes,
            raw_message=raw_message,
            status=status,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return _order_to_dict(order)


def get_order(tenant_id: str, order_id: int | str) -> dict | None:
    """Return one order for a tenant by its numeric id, or None."""
    try:
        order_id = int(order_id)
    except (TypeError, ValueError):
        return None
    with get_session() as session:
        order = session.query(Order).filter_by(tenant_id=tenant_id, id=order_id).first()
        return _order_to_dict(order) if order else None


def get_order_by_code(tenant_id: str, order_code: str) -> dict | None:
    """Return one order for a tenant by its merchant-friendly code, or None."""
    with get_session() as session:
        order = session.query(Order).filter_by(tenant_id=tenant_id, order_code=order_code).first()
        return _order_to_dict(order) if order else None


def list_orders(
    tenant_id: str | None,
    limit: int = 50,
    status: str | None = None,
) -> list[dict]:
    """List recent orders, newest first. tenant_id=None or "" lists across all."""
    with get_session() as session:
        q = session.query(Order)
        if tenant_id:
            q = q.filter_by(tenant_id=tenant_id)
        if status:
            q = q.filter_by(status=status)
        rows = q.order_by(Order.created_at.desc()).limit(limit).all()
        return [_order_to_dict(o) for o in rows]


def update_order_status(tenant_id: str, order_id: int, status: str) -> dict | None:
    """Update an order's status. Returns the updated dict, or None if not found."""
    with get_session() as session:
        order = session.query(Order).filter_by(tenant_id=tenant_id, id=order_id).first()
        if order is None:
            return None
        order.status = status
        session.commit()
        session.refresh(order)
        return _order_to_dict(order)


def _order_to_dict(order: Order) -> dict[str, Any]:
    return {
        "id": order.id,
        "tenant_id": order.tenant_id,
        "thread_id": order.thread_id,
        "wa_number": order.wa_number,
        "order_code": order.order_code,
        "items": _loads_items(order.items),
        "total": order.total,
        "buyer_name": order.buyer_name,
        "buyer_address": order.buyer_address,
        "notes": order.notes,
        "status": order.status,
        "raw_message": order.raw_message,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


def _loads_items(items_text: str) -> list[dict]:
    """Parse the stored JSON items column, falling back to [] safely."""
    try:
        data = json.loads(items_text or "[]")
        return data if isinstance(data, list) else []
    except (TypeError, ValueError):
        return []