"""Ghosting follow-up sender (anti-ghosting touchpoints).

Scans threads where the bot sent an offer/price reply and the buyer went
silent, then sends the scheduled reminder based on time since last activity:

  Touchpoint 1  (>=24h)   social proof, echo the product, open question
  Touchpoint 2  (>=72h)   neutral availability nudge + product echo
  Touchpoint 3  (>=144h)  soft exit, close the loop

Marketing rules baked in:
  - follow up only on real leads (last buyer intent faq/check_product/order)
  - echo the product the buyer asked about (matched against catalog names)
  - end with an open question, not a yes/no
  - send only in prime windows 10-12 / 18-21 WIB (Asia/Jakarta)

Run on a cron:  `0 0,6,12,18 * * *  cd <repo> && .venv/bin/python scripts/send_follow_ups.py --send`
Defaults to DRY-RUN (prints what would be sent). Pass --send to actually send.
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db.chat_log_repo import insert_chat_log, list_chat_logs  # noqa: E402
from app.db.conversation_repo import get_conversation_state, merge_conversation_state  # noqa: E402
from app.db.order_repo import list_orders  # noqa: E402
from app.db.tenant_repo import get_tenant, list_tenants  # noqa: E402
from app.services.crypto import decrypt_api_key  # noqa: E402
from app.services.fonnte import FonnteGateway  # noqa: E402

logger = logging.getLogger("send_follow_ups")
WIB = ZoneInfo("Asia/Jakarta")

TP1_HOURS = 24
TP2_HOURS = 72
TP3_HOURS = 144

LEAD_INTENTS = {"faq", "check_product", "confirm_order"}

TP_TEMPLATES = {
    1: "Halo {sapaan}, sekadar berbagi, kemarin pelanggan kami yang pakai {produk} sangat puas karena... Oh ya, ada bagian dari rincian kemarin yang ingin Kakak sesuaikan?",
    2: "Halo {sapaan}, sekadar kabar, {produk} yang kemarin Kakak tanyakan masih bisa kami bantu amankan. Mau saya bantu proseskan, atau ada yang perlu disesuaikan dulu?",
    3: "Halo {sapaan}, sepertinya Kakak sedang sibuk ya. Percakapan ini saya simpan dulu ya Kak. Jika nanti Kakak butuh bantuan kustomisasi menu/ukuran lagi, cukup balas chat ini kapan saja. Terima kasih Kak!",
}

# per-tenant catalog name cache for product echo
_catalog_names_cache: dict[str, list[str]] = {}


def _sapaan(nama: str) -> str:
    return f"Kak {nama}" if nama else "Kak"


def _produk(tp: int, name: str) -> str:
    if not name:
        return "menu/produk ini" if tp == 1 else "pesanan"
    return f"produk {name}"


def _due_touchpoint(hours: float, sent: int) -> int:
    if hours < TP1_HOURS or sent >= 3:
        return 0
    if sent < 1 and hours >= TP1_HOURS:
        return 1
    if sent < 2 and hours >= TP2_HOURS:
        return 2
    if sent < 3 and hours >= TP3_HOURS:
        return 3
    return 0


def _in_send_window(now: datetime | None = None) -> bool:
    """Prime-time windows 10-12 and 18-21 WIB."""
    now = now or datetime.now(WIB)
    h = now.astimezone(WIB).hour
    return 10 <= h < 12 or 18 <= h < 21


def _match_product(names: list[str], text: str) -> str:
    """First catalog name whose lowercase form appears in the text, or ''."""
    low = (text or "").lower()
    for n in names:
        if n and n.lower() in low:
            return n
    return ""


def _catalog_names(tenant_id: str) -> list[str]:
    if tenant_id in _catalog_names_cache:
        return _catalog_names_cache[tenant_id]
    names: list[str] = []
    try:
        from app.services.bot_tester import _build_sheets_client

        rows = _build_sheets_client(tenant_id).read_catalog()
        names = [str(r.get("nama_produk") or "").strip() for r in rows if r.get("nama_produk")]
    except Exception as e:  # noqa: BLE001
        logger.warning("catalog_fetch_failed", extra={"tenant_id": tenant_id, "error": str(e)})
    _catalog_names_cache[tenant_id] = names
    return names


def _buyer_name(tenant_id: str, thread_id: str) -> str:
    name = get_conversation_state(tenant_id, thread_id).get("buyer_name")
    if name:
        return name
    for o in list_orders(tenant_id, limit=20):
        if o.get("thread_id") == thread_id and o.get("buyer_name"):
            return o["buyer_name"]
    return ""


def _parse_dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def _threads_silent_since(tenant_id: str, min_hours: float) -> list[dict]:
    """Threads where the last row is a bot reply (buyer silent since then)."""
    logs = list_chat_logs(tenant_id, limit=5000)
    by_thread: dict[str, list[dict]] = {}
    for r in logs:
        by_thread.setdefault(r["thread_id"], []).append(r)
    out = []
    now = datetime.now(timezone.utc)
    for tid, rows in by_thread.items():
        rows.sort(key=lambda r: r["id"])
        last = rows[-1]
        if not last.get("response") or last.get("status") not in ("reply", "order"):
            continue  # last speaker was not the bot with a real offer
        last_buyer = next((r for r in reversed(rows) if r.get("user_message")), None)
        if not last_buyer or last_buyer.get("intent") not in LEAD_INTENTS:
            continue  # real lead only — skip greetings/off-topic chats
        ts = _parse_dt(last["timestamp"])
        if not ts:
            continue
        ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        hours = (now - ts).total_seconds() / 3600.0
        if hours < min_hours:
            continue
        sent = int(get_conversation_state(tenant_id, tid).get("followup_touchpoint", 0) or 0)
        tp = _due_touchpoint(hours, sent)
        if not tp:
            continue
        out.append({
            "thread_id": tid,
            "wa_number": last["wa_number"],
            "hours": hours,
            "touchpoint": tp,
            "sent": sent,
            "last_buyer_msg": last_buyer.get("user_message", ""),
            "last_bot_resp": last.get("response", ""),
        })
    return out


async def _send(tenant_id: str, thread: dict, dry_run: bool) -> None:
    tp = thread["touchpoint"]
    product = _match_product(_catalog_names(tenant_id), thread["last_buyer_msg"] + " " + thread["last_bot_resp"])
    msg = TP_TEMPLATES[tp].format(sapaan=_sapaan(_buyer_name(tenant_id, thread["thread_id"])), produk=_produk(tp, product))
    if not _in_send_window():
        print(f"[deferred] {tenant_id} | {thread['thread_id']} | TP{tp} ({thread['hours']:.0f}h) di luar jam wajar 10-12/18-21 WIB")
        return
    if dry_run:
        print(f"[dry-run] {tenant_id} | {thread['thread_id']} | TP{tp} ({thread['hours']:.0f}h) -> {thread['wa_number']}\n  {msg}\n")
        return
    tenant = get_tenant(tenant_id)
    if not tenant:
        return
    key = tenant.get("wa_api_key_encrypted") or b""
    if not key:
        print(f"[skip] {tenant_id} | no gateway key")
        return
    gateway = FonnteGateway(api_key=decrypt_api_key(key, get_settings().encryption_key))
    await gateway.send_message(phone=thread["wa_number"], message=msg)
    merge_conversation_state(
        tenant_id,
        thread["thread_id"],
        {"followup_touchpoint": tp, "followup_sent_at": datetime.now(timezone.utc).isoformat()},
    )
    insert_chat_log(
        thread_id=thread["thread_id"],
        tenant_id=tenant_id,
        wa_number=thread["wa_number"],
        status="reply",
        response=msg,
    )
    print(f"[sent] {tenant_id} | {thread['thread_id']} | TP{tp}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Anti-ghosting follow-up sender")
    ap.add_argument("--send", action="store_true", help="actually send via Fonnte (default: dry-run)")
    ap.add_argument("--tenant", default="", help="only scan this tenant_id")
    ap.add_argument("--hours", type=float, default=TP1_HOURS, help="minimum silent hours to consider (default 24)")
    args = ap.parse_args()

    tenants = [get_tenant(args.tenant)] if args.tenant else list_tenants()
    pending = 0
    for tenant in tenants:
        if not tenant:
            continue
        tid = tenant.get("tenant_id")
        if not tid:
            continue
        for t in _threads_silent_since(tid, args.hours):
            pending += 1
            asyncio.run(_send(tid, t, dry_run=not args.send))
    print(f"Total follow-ups {'sent' if args.send else 'would be sent'}: {pending}")


if __name__ == "__main__":
    main()
