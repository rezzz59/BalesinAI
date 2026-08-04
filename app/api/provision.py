"""Provisioning API — self-service tenant onboarding for merchants.

Endpoints:
  POST /api/provision/validate-sheet   — inspect a Google Sheets URL, auto-detect
                                          FAQ/catalog tabs & columns, report counts.
  POST /api/provision/create-tenant    — create a tenant from a valid token + sheet.
  GET  /api/provision/status/{tenant}  — onboarding status (ready/error).
  POST /api/provision/tokens           — (admin) mint a single-use provisioning token.
  GET  /api/provision/tokens           — (admin) list tokens.

Merchant flow: admin mints a token → merchant opens /provision?token=... → fills
form → validate-sheet → create-tenant → bot live. No login required for the
merchant; token in the URL is the credential.
"""
import json as _json
import logging
import re
import secrets

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.db.tenant_repo import (
    consume_provisioning_token,
    create_provisioning_token,
    get_provisioning_token,
    get_tenant,
    list_tenants,
    update_onboarding_data,
    update_onboarding_status,
)
from app.services.bot_tester import dry_run_reply, score_tenant
from app.services.crypto import encrypt_api_key
from app.services.embedding_seeder import seed_tenant_embeddings
from app.services.sheets import GoogleSheetsClient, SheetsError, parse_sheet_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/provision", tags=["provisioning"])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or "tenant"


def _check_admin_auth(request: Request) -> None:
    """Guard admin endpoints with the webhook_auth_token (Bearer)."""
    auth = request.headers.get("Authorization", "")
    settings = get_settings()
    if not settings.webhook_auth_token:
        raise HTTPException(status_code=503, detail="Admin token not configured")
    if not auth.startswith("Bearer ") or auth[7:] != settings.webhook_auth_token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _build_sheets_client(spreadsheet_id: str) -> GoogleSheetsClient:
    settings = get_settings()
    return GoogleSheetsClient(
        credentials_json_path=settings.google_sheets_credentials_json_path,
        spreadsheet_id=spreadsheet_id,
    )


@router.post("/validate-sheet")
async def validate_sheet(request: Request):
    """Inspect a merchant's Google Sheets URL.

    Returns detected tabs with inferred types, FAQ/product row counts, the
    column mapping used, and any warnings (e.g. missing FAQ/catalog tab).
    """
    body = await request.json()
    sheet_url = (body.get("sheet_url") or "").strip()
    spreadsheet_id = parse_sheet_url(sheet_url)
    if not spreadsheet_id:
        raise HTTPException(status_code=400, detail="URL Google Sheets tidak valid. Gunakan link format /spreadsheets/d/...")

    client = _build_sheets_client(spreadsheet_id)
    try:
        tabs = client.discover_tabs()
        faq_rows = client.read_faq()
        catalog_rows = client.read_catalog()
    except SheetsError as e:
        raise HTTPException(status_code=400, detail=f"Gagal membaca spreadsheet: {e}")

    faq_tab = client.find_tab("faq")
    catalog_tab = client.find_tab("catalog")

    # Build the canonical column mapping actually used per detected tab.
    faq_sample = faq_rows[0] if faq_rows else {}
    catalog_sample = catalog_rows[0] if catalog_rows else {}
    faq_cols = [k for k in ("pertanyaan", "jawaban") if k in faq_sample]
    catalog_cols = [k for k in ("nama_produk", "harga", "ready", "deskripsi") if k in catalog_sample]

    warnings = []
    if faq_tab is None:
        warnings.append("Tab FAQ tidak ditemukan (cari tab bernama FAQ/QnA/Pertanyaan).")
    if catalog_tab is None:
        warnings.append("Tab Katalog tidak ditemukan (cari tab bernama Katalog/Produk/Product).")
    if faq_tab and not faq_cols:
        warnings.append("Tab FAQ ada tapi kolom pertanyaan/jawaban tidak terdeteksi.")
    if catalog_tab and not catalog_cols:
        warnings.append("Tab Katalog ada tapi kolom produk tidak terdeteksi.")

    return {
        "spreadsheet_id": spreadsheet_id,
        "tabs": tabs,
        "faq_tab": faq_tab,
        "catalog_tab": catalog_tab,
        "faq_count": len(faq_rows),
        "catalog_count": len(catalog_rows),
        "faq_columns": faq_cols,
        "catalog_columns": catalog_cols,
        "warnings": warnings,
        "ready": not warnings,
    }


@router.post("/create-tenant")
async def create_tenant(request: Request):
    """Create a tenant from a valid provisioning token + sheet URL.

    Body: {token, sheet_url, owner_wa_number, business_type, fonnte_api_key?,
           merchant_name?}
    Encrypts the Fonnte API key, persists the tenant, seeds FAQ/catalog
    embeddings, and marks the token as used.
    """
    body = await request.json()
    token = (body.get("token") or "").strip()
    sheet_url = (body.get("sheet_url") or "").strip()
    owner_wa_number = (body.get("owner_wa_number") or "").strip()
    business_type = (body.get("business_type") or "jualan").strip().lower()
    merchant_name = (body.get("merchant_name") or "").strip()
    fonnte_api_key = (body.get("fonnte_api_key") or "").strip()

    if not token:
        raise HTTPException(status_code=400, detail="Token tidak ditemukan. Gunakan link dari admin Anda.")
    if not owner_wa_number:
        raise HTTPException(status_code=400, detail="Nomor WA owner wajib diisi.")

    tok = get_provisioning_token(token)
    if tok is None:
        raise HTTPException(status_code=404, detail="Token tidak valid.")
    if tok["status"] != "pending":
        raise HTTPException(status_code=409, detail="Token sudah digunakan. Minta link baru dari admin.")
    if tok.get("expires_at"):
        from datetime import datetime, timezone
        try:
            expires = datetime.fromisoformat(tok["expires_at"])
        except ValueError:
            expires = None
        if expires is not None:
            # Strip tzinfo for naive-datetime comparison (SQLite returns naive datetimes)
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            expires_naive = expires.replace(tzinfo=None) if expires.tzinfo else expires
            if expires_naive < now_utc:
                raise HTTPException(status_code=410, detail="Token sudah kedaluwarsa.")

    spreadsheet_id = parse_sheet_url(sheet_url)
    if not spreadsheet_id:
        raise HTTPException(status_code=400, detail="URL Google Sheets tidak valid.")

    # Verify the sheet is actually readable before committing.
    client = _build_sheets_client(spreadsheet_id)
    try:
        faq_rows = client.read_faq()
        catalog_rows = client.read_catalog()
    except SheetsError as e:
        raise HTTPException(status_code=400, detail=f"Gagal membaca spreadsheet: {e}")

    settings = get_settings()
    key_to_encrypt = fonnte_api_key or settings.fonnte_api_key
    if not key_to_encrypt:
        raise HTTPException(status_code=400, detail="Fonnte API key belum dikonfigurasi. Hubungi admin.")
    encrypted = encrypt_api_key(key_to_encrypt, settings.encryption_key)

    tenant_id = f"{_slugify(merchant_name or tok['intended_merchant_name'] or 'tenant')}-{secrets.token_hex(2)}"

    from app.db.tenant_repo import insert_or_update_tenant

    insert_or_update_tenant(
        tenant_id=tenant_id,
        wa_api_key_encrypted=encrypted,
        google_sheet_id=spreadsheet_id,
        owner_wa_number=owner_wa_number,
        business_type=business_type,
        onboarding_status="seeding",
        onboarding_data={
            "sheet_url": sheet_url,
            "faq_count": len(faq_rows),
            "catalog_count": len(catalog_rows),
            "merchant_name": merchant_name or tok.get("intended_merchant_name", ""),
        },
    )

    # Seed embeddings (synchronous; 100-ish rows is fast on CPU).
    try:
        counts = seed_tenant_embeddings(tenant_id, client)
    except Exception as e:  # noqa: BLE001
        update_onboarding_status(tenant_id, "error")
        raise HTTPException(status_code=500, detail=f"Gagal seeding embedding: {e}")

    # Auto-validate: run the readiness battery against the freshly seeded bot.
    # If scoring fails, keep the tenant in "seeding_error" rather than killing
    # the whole request — the merchant still got a tenant, admin can inspect.
    readiness = None
    try:
        readiness = score_tenant(tenant_id)
    except Exception as e:  # noqa: BLE001
        logger.error(
            "readiness_scoring_failed",
            extra={"tenant_id": tenant_id, "error": str(e)},
        )
        update_onboarding_status(tenant_id, "seeding_error")
        consume_provisioning_token(token, tenant_id)
        return {
            "tenant_id": tenant_id,
            "status": "seeding_error",
            "webhook_url": "/webhook/whatsapp/",
            "embeddings": counts,
            "readiness": {"score": None, "status": "seeding_error", "warnings": ["Gagal menguji bot, hubungi admin."]},
        }

    status = readiness.get("status", "needs_review")
    update_onboarding_status(tenant_id, status)

    tenant_record = get_tenant(tenant_id)
    onboarding_data = {}
    if tenant_record:
        try:
            onboarding_data = _json.loads(tenant_record.get("onboarding_data") or "{}")
        except ValueError:
            onboarding_data = {}
    onboarding_data["readiness"] = readiness
    update_onboarding_data(tenant_id, onboarding_data)

    consume_provisioning_token(token, tenant_id)

    return {
        "tenant_id": tenant_id,
        "status": status,
        "webhook_url": "/webhook/whatsapp/",
        "embeddings": counts,
        "readiness": readiness,
    }


@router.post("/test-chat")
async def test_chat(request: Request):
    """Merchant-facing: preview how the bot replies without sending WhatsApp.

    Body: {tenant_id, message}. Runs the tenant's graph headlessly with a
    DryRunGateway (nothing is transmitted to the buyer or owner) and returns
    the composed reply plus intent/confidence/action diagnostics.
    """
    body = await request.json()
    tenant_id = (body.get("tenant_id") or "").strip()
    message = (body.get("message") or "").strip()

    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id wajib diisi.")
    if not message:
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong.")

    tenant = get_tenant(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant tidak ditemukan.")

    try:
        result = dry_run_reply(tenant_id, message)
    except Exception as e:  # noqa: BLE001
        logger.error(
            "test_chat_failed",
            extra={"tenant_id": tenant_id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail=f"Gagal memproses pesan: {e}")

    return {
        "tenant_id": tenant_id,
        "reply": result.get("reply_text", ""),
        "intent": result.get("intent"),
        "confidence": result.get("confidence"),
        "action": result.get("action"),
        "fallback_reason": result.get("fallback_reason"),
        "match_kind": result.get("match_kind"),
        "order_items": result.get("order_items"),
        "order_total": result.get("order_total"),
        "order_code": result.get("order_code"),
    }


@router.get("/status/{tenant_id}")
async def provisioning_status(tenant_id: str):
    """Return the onboarding status for a tenant."""
    tenant = get_tenant(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant tidak ditemukan.")
    return {
        "tenant_id": tenant_id,
        "status": tenant.get("onboarding_status", "pending"),
        "business_type": tenant.get("business_type", "jualan"),
    }


@router.post("/tokens")
async def mint_token(request: Request):
    """Admin: mint a single-use provisioning token."""
    _check_admin_auth(request)
    body = await request.json()
    merchant_name = (body.get("merchant_name") or "").strip()
    ttl_hours = int(body.get("ttl_hours") or 48)
    return create_provisioning_token(intended_merchant_name=merchant_name, ttl_hours=ttl_hours)


@router.get("/tokens")
async def list_tokens(request: Request):
    """Admin: list all provisioning tokens."""
    _check_admin_auth(request)
    from app.db.engine import get_session
    from app.db.models import ProvisioningToken
    with get_session() as session:
        rows = session.query(ProvisioningToken).all()
        return [
            {
                "token": r.token,
                "status": r.status,
                "intended_merchant_name": r.intended_merchant_name,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "created_tenant_id": r.created_tenant_id,
            }
            for r in rows
        ]


@router.get("/tenants")
async def provision_tenants(request: Request):
    """Admin: list all tenants."""
    _check_admin_auth(request)
    return {"tenants": list_tenants()}


@router.get("/orders")
async def provision_orders(request: Request, tenant_id: str = "", status: str = "", limit: int = 50):
    """Admin: list captured orders, optionally filtered by tenant/status."""
    _check_admin_auth(request)
    from app.db.order_repo import list_orders

    tenant = tenant_id.strip() or None
    status_val = status.strip() or None
    limit = max(1, min(200, limit))
    return {
        "orders": list_orders(
            tenant_id=tenant,
            status=status_val,
            limit=limit,
        )
    }


@router.patch("/orders/{order_id}/status")
async def provision_order_status(order_id: int, request: Request):
    """Admin: update an order's status (pending/confirmed/paid/done/cancelled)."""
    _check_admin_auth(request)
    from app.db.order_repo import update_order_status

    body = await request.json()
    status_val = (body.get("status") or "").strip()
    if status_val not in {"pending", "confirmed", "paid", "done", "cancelled"}:
        raise HTTPException(status_code=400, detail="Status tidak valid.")
    updated = update_order_status(tenant_id="", order_id=order_id, status=status_val)
    if updated is None:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan.")
    return {"status": "ok", "order": updated}
